"""Corregir en el sistema una fila que falló al importar (unidad correccion-de-filas-con-error).

HU-E3-06 se pensó para corregir en la planilla de origen y reprocesar. Quien ve «El dígito
verificador del CUIT no es correcto» quiere arreglarlo ahí mismo, y esta unidad se lo permite en
dos pasos que el usuario ve como uno:

1. **`LeerFilaConError`** trae los valores de la fila. Salen **del archivo y no de la base**: el
   sistema nunca guardó la fila, sólo su número y el motivo. Se lee el archivo subido, se toma la
   fila por número y se le aplica el mapeo **del procesamiento** (no el vigente de la planilla,
   que pudo cambiar después): lo editable son los campos del sistema —Nombre, CUIT— y no las
   columnas crudas.
2. **`CorregirFila`** ingiere los valores editados por el mismo `PortIngestaDeCatalogo` que usa el
   procesamiento. **Ninguna regla de validación se repite acá**: `master_data` decide qué es un
   cliente válido, y si rechaza la fila el motivo sube tal cual para que la pantalla lo muestre.

**La corrección rechazada no deja nada escrito.** El caso de uso levanta antes de tocar el
agregado, y la unidad de trabajo descarta la transacción cuando el cuerpo levanta.

**La bitácora no lleva los valores.** Son CUIT, teléfonos y correos: el evento dice qué carga y
qué fila, nunca qué se escribió.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.mapeos import (
    ATRIBUTOS_DE_CLIENTE,
    ATRIBUTOS_DE_SERVICIO,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    FilaParaIngerir,
    PortAlmacenamientoDeArchivos,
    PortIngestaDeCatalogo,
    PortLectorDePlanilla,
    PortRepositorioMapeo,
    PortRepositorioProcesamiento,
)
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import ProcesamientoDePlanilla
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: Los campos que se pueden escribir: el vocabulario de `master_data`, con `nombre` una sola vez.
ATRIBUTOS_CORREGIBLES: frozenset[str] = frozenset(ATRIBUTOS_DE_CLIENTE + ATRIBUTOS_DE_SERVICIO)

MOTIVO_SIN_PERMISO = "Un usuario de Solo Lectura no puede corregir filas"
MOTIVO_SIN_ARCHIVO = (
    "Esta carga no se leyó de un archivo subido, así que sus filas no se pueden corregir acá"
)


@dataclass(frozen=True, slots=True)
class CampoDeFila:
    """Un campo del sistema y el valor que tiene la fila en el archivo (puede estar vacío)."""

    atributo: str
    valor: str


@dataclass(frozen=True, slots=True)
class VistaDeFilaConError:
    """Lo que el panel necesita para abrir el editor de una fila."""

    numero_fila: int
    motivo: str
    campos: tuple[CampoDeFila, ...]


def _error_pendiente(procesamiento: ProcesamientoDePlanilla, numero_fila: int) -> str:
    """El motivo del error pendiente de esa fila, o `EntradaInvalida` si no hay uno.

    Lo comparten las dos operaciones, y es lo que impide corregir dos veces la misma fila (que
    la importaría dos veces) o una fila que nunca falló.
    """
    for error in procesamiento.errores_pendientes:
        if error.numero_fila == numero_fila:
            return error.motivo
    raise EntradaInvalida(f"La fila {numero_fila} no tiene un error pendiente de corregir")


async def _buscar(
    procesamientos: PortRepositorioProcesamiento, procesamiento_id: UUID
) -> ProcesamientoDePlanilla:
    procesamiento = await procesamientos.buscar_por_id(procesamiento_id)
    if procesamiento is None:
        raise EntradaInvalida("El procesamiento no existe")
    return procesamiento


class LeerFilaConError:
    """Los valores de una fila que falló, listos para editar. Todos los roles miran."""

    def __init__(
        self,
        *,
        procesamientos: PortRepositorioProcesamiento,
        mapeos: PortRepositorioMapeo,
        almacenamiento: PortAlmacenamientoDeArchivos,
        lector: PortLectorDePlanilla,
    ) -> None:
        self._procesamientos = procesamientos
        self._mapeos = mapeos
        self._almacenamiento = almacenamiento
        self._lector = lector

    async def ejecutar(self, *, procesamiento_id: UUID, numero_fila: int) -> VistaDeFilaConError:
        procesamiento = await _buscar(self._procesamientos, procesamiento_id)
        motivo = _error_pendiente(procesamiento, numero_fila)
        if procesamiento.referencia_archivo is None:
            raise EntradaInvalida(MOTIVO_SIN_ARCHIVO)

        mapeo = await self._mapeos.buscar_por_id(procesamiento.mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo de esta carga ya no existe")

        contenido = await self._almacenamiento.leer(procesamiento.referencia_archivo)
        # La clave termina en la extensión del archivo, que es lo único que el lector mira.
        planilla = self._lector.leer(contenido=contenido, nombre=procesamiento.referencia_archivo)
        fila = next((f for f in planilla.filas if f.numero == numero_fila), None)
        if fila is None:
            raise EntradaInvalida(f"La fila {numero_fila} ya no está en el archivo")

        campos: list[CampoDeFila] = []
        vistos: set[str] = set()
        for entrada in mapeo.entradas:
            atributo = entrada.atributo_destino
            if atributo is None or atributo in vistos:
                continue
            vistos.add(atributo)
            campos.append(
                CampoDeFila(
                    atributo=atributo, valor=fila.celdas.get(entrada.columna_origen, "").strip()
                )
            )
        return VistaDeFilaConError(numero_fila=numero_fila, motivo=motivo, campos=tuple(campos))


class CorregirFila:
    """Importa los valores corregidos de una fila y deja su error como corregido."""

    def __init__(
        self,
        *,
        procesamientos: PortRepositorioProcesamiento,
        catalogo: PortIngestaDeCatalogo,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._procesamientos = procesamientos
        self._catalogo = catalogo
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        procesamiento_id: UUID,
        numero_fila: int,
        valores: dict[str, str],
        ahora: datetime,
    ) -> ProcesamientoDePlanilla:
        # El permiso viaja con la operación y no sólo con el router: PRU-09 lo demostró.
        if rol is RolUsuario.SOLO_LECTURA:
            raise EntradaInvalida(MOTIVO_SIN_PERMISO)

        limpios = _limpiar(valores)
        procesamiento = await _buscar(self._procesamientos, procesamiento_id)
        # Antes de ingerir: una fila sin error pendiente no se vuelve a importar.
        _error_pendiente(procesamiento, numero_fila)

        # Si `master_data` rechaza la fila levanta `ErrorDeDominio` con su motivo, y no se
        # escribió nada: ni el catálogo ni el procesamiento.
        await self._catalogo.ingerir(
            empresa_id=empresa_id, fila=FilaParaIngerir(valores=limpios), ahora=ahora
        )

        procesamiento.corregir_fila(numero_fila=numero_fila, ahora=ahora)
        await self._procesamientos.actualizar(procesamiento)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="corregir_fila_de_carga",
                # La carga, no los valores: son CUIT y teléfonos.
                entidad_afectada=f"ProcesamientoDePlanilla:{procesamiento.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return procesamiento


def _limpiar(valores: dict[str, str]) -> dict[str, str]:
    """Sólo campos conocidos, sin espacios, y sin los vacíos: un campo vacío es «no hay dato»."""
    desconocidos = sorted(set(valores) - ATRIBUTOS_CORREGIBLES)
    if desconocidos:
        raise EntradaInvalida(f"El campo {desconocidos[0]} no se reconoce")
    limpios = {atributo: valor.strip() for atributo, valor in valores.items() if valor.strip()}
    if not limpios:
        raise EntradaInvalida("No hay ningún dato para importar")
    return limpios
