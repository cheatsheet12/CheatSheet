"""The use cases of HU-E3-01 and HU-E3-02 — proposing a mapping and confirming it.

**The destination attributes come from `master_data`'s own vocabulary**, listed here as
constants rather than reflected off the aggregates. Reflection would couple the model's
answer to a field rename in another context, and rule R3 forbids reaching into
`master_data/domain` anyway. The list is short and changes when a story changes it.

**The header fingerprint is a hash of the column names, in order.** RN-02 wants the mapping
reused «mientras la estructura no cambie», so the fingerprint has to change when and only
when the structure does. Order is included because a spreadsheet whose columns were
reordered is a spreadsheet whose data lands in different fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.errors import VinculoInexistente
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    PlanillaLeida,
    PortAlmacenamientoDeArchivos,
    PortLectorDePlanilla,
    PortModeloDeLenguaje,
    PortRepositorioMapeo,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import (
    EntradaDeMapeo,
    Mapeo,
    NivelDeConfianza,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: What a spreadsheet column can map to. The vocabulary of `master_data`, restated -- see
#: the module docstring on why this is a list and not reflection.
ATRIBUTOS_DE_CLIENTE: tuple[str, ...] = (
    "nombre",
    "cuit",
    "condicion_iva",
    "contacto_whatsapp",
    "contacto_email",
)
ATRIBUTOS_DE_SERVICIO: tuple[str, ...] = (
    "nombre",
    "precio",
    "alicuota_iva",
    "agendable",
    "duracion_estandar_min",
)

#: Without these, a processed row produces a record nobody can use: a customer with no
#: name, a service with no price. HU-E3-02 RN-02 blocks confirmation until they are fed.
OBLIGATORIOS_DE_CLIENTE = frozenset({"nombre"})
OBLIGATORIOS_DE_SERVICIO = frozenset({"nombre", "precio"})


def huella_de(columnas: tuple[str, ...]) -> str:
    """RN-02's `huella_encabezado`: identifies a structure, not a spreadsheet.

    Case and surrounding whitespace are normalised away -- `Nombre` and `nombre ` are the
    same column to a person, and treating them as a structural change would pause the sync
    every time somebody tidied a header. Order is **not** normalised: reordered columns are
    a different structure, because the data lands in different fields.
    """
    canonico = "".join(columna.strip().lower() for columna in columnas)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VistaDeMapeo:
    """What PAN-ING-02 renders: the mapping plus what is missing to confirm it."""

    mapeo: Mapeo
    faltantes: tuple[str, ...]
    #: True when the model answered. False covers two very different endings, which is why
    #: `reutilizado` exists next to it: the model failed, or it was never asked.
    propuesto_por_el_modelo: bool
    #: True when RN-02's fingerprint found a stored mapping and the model was not called.
    #: «No pudimos proponerlo» y «ya lo teníamos» son cosas distintas para alguien mirando
    #: una tabla llena de «Sin asignar», y un solo booleano las decía igual.
    reutilizado: bool = False

    @property
    def puede_confirmarse(self) -> bool:
        return not self.faltantes


class ProponerMapeo:
    """HU-E3-01 — the model reads the headers and proposes; the user decides.

    **Reuse first** (RN-02): if a mapping with this fingerprint exists, it is returned
    untouched and the model is not called. That is the third acceptance criterion, and it
    is also what keeps a daily sync from paying for a model call every morning.
    """

    def __init__(
        self,
        *,
        mapeos: PortRepositorioMapeo,
        vinculos: PortRepositorioVinculo,
        modelo: PortModeloDeLenguaje,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._mapeos = mapeos
        self._vinculos = vinculos
        self._modelo = modelo
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        vinculo_id: UUID,
        columnas: tuple[str, ...],
        ejemplos: dict[str, str] | None = None,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> VistaDeMapeo:
        if not columnas:
            raise EntradaInvalida("La planilla no tiene encabezados que mapear")

        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")

        huella = huella_de(columnas)
        atributos = ATRIBUTOS_DE_SERVICIO if para_servicios else ATRIBUTOS_DE_CLIENTE
        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE

        existente = await self._mapeos.buscar_por_huella(huella)
        if existente is not None:
            vinculo.asignar_mapeo(existente.id, ahora=ahora)
            await self._vinculos.actualizar(vinculo)
            return VistaDeMapeo(
                mapeo=existente,
                faltantes=existente.faltantes(obligatorios),
                propuesto_por_el_modelo=False,
                reutilizado=True,
            )

        # The model sees column names and the destination vocabulary. Nothing else: the
        # samples below are read from the sheet and never leave this process (D12).
        propuestas = await self._modelo.proponer_mapeo(columnas=columnas, atributos=atributos)
        por_columna = {p.columna: p for p in propuestas}

        mapeo = Mapeo(
            id=uuid4(),
            empresa_id=empresa_id,
            huella_encabezado=huella,
            entradas=[
                _entrada(columna, por_columna.get(columna), (ejemplos or {}).get(columna))
                for columna in columnas
            ],
            created_at=ahora,
            updated_at=ahora,
        )
        await self._mapeos.agregar(mapeo)

        vinculo.asignar_mapeo(mapeo.id, ahora=ahora)
        await self._vinculos.actualizar(vinculo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="proponer_mapeo",
                entidad_afectada=f"Mapeo:{mapeo.id}",
                # The proposal succeeded even when the model did not answer: the screen
                # gets a mapping to work on either way. What failed, if anything, is in
                # the adapter's log, not in the business record.
                resultado=Resultado.COMPLETADO,
            )
        )
        return VistaDeMapeo(
            mapeo=mapeo,
            faltantes=mapeo.faltantes(obligatorios),
            propuesto_por_el_modelo=bool(propuestas),
        )


def _entrada(columna: str, propuesta: object, ejemplo: str | None) -> EntradaDeMapeo:
    """One column's entry. No proposal means `Sin asignar` with a zero score.

    That is the degradation path of ADR-0007 made concrete: when the model does not
    answer, every column arrives unassigned and the user maps by hand — which is exactly
    the state RN-03 already defines for low confidence, so the screen needs nothing new.
    """
    score = getattr(propuesta, "score", Decimal("0"))
    atributo = getattr(propuesta, "atributo", None)
    # RN-03: below the threshold the column is `Sin asignar`, whatever the model said.
    if NivelDeConfianza.desde_score(score).requiere_revision:
        atributo = None
    return EntradaDeMapeo(
        id=uuid4(), columna_origen=columna, atributo_destino=atributo, score=score, ejemplo=ejemplo
    )


class CorregirMapeo:
    """HU-E3-02 RN-01 — the user fixes an assignment before confirming."""

    def __init__(self, mapeos: PortRepositorioMapeo) -> None:
        self._mapeos = mapeos

    async def ejecutar(
        self,
        *,
        mapeo_id: UUID,
        rol: RolUsuario,
        columna: str,
        atributo: str | None,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> VistaDeMapeo:
        _exigir_que_pueda_mapear(rol)
        mapeo = await self._exigir(mapeo_id)

        atributos = ATRIBUTOS_DE_SERVICIO if para_servicios else ATRIBUTOS_DE_CLIENTE
        if atributo is not None and atributo not in atributos:
            raise EntradaInvalida(f"'{atributo}' no es un campo del sistema")

        mapeo.corregir(columna=columna, atributo=atributo, ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE
        return VistaDeMapeo(
            mapeo=mapeo, faltantes=mapeo.faltantes(obligatorios), propuesto_por_el_modelo=False
        )

    async def _exigir(self, mapeo_id: UUID) -> Mapeo:
        mapeo = await self._mapeos.buscar_por_id(mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo no existe")
        return mapeo


class ConfirmarMapeo:
    """HU-E3-02 RN-03 — confirming is what unlocks the processing of the spreadsheet."""

    def __init__(self, *, mapeos: PortRepositorioMapeo, publicador: PublicadorDeEventos) -> None:
        self._mapeos = mapeos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        mapeo_id: UUID,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> Mapeo:
        _exigir_que_pueda_mapear(rol)

        mapeo = await self._mapeos.buscar_por_id(mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo no existe")

        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE
        mapeo.confirmar(obligatorios=obligatorios, ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="confirmar_mapeo",
                entidad_afectada=f"Mapeo:{mapeo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return mapeo


class ReabrirMapeo:
    """Volver a revisar un mapeo confirmado, sin perder lo ya asignado.

    `Mapeo.corregir` se niega sobre un mapeo validado y dice qué hacer en su lugar —«para
    cambiarlo hay que revisarlo de nuevo»—, pero hasta acá esa salida no existía para una
    persona: `nueva_version` sólo la llamaba la sincronización automática al detectar que
    la estructura cambió. La pantalla decía qué hacer y no ofrecía cómo.

    **Las entradas se conservan.** Es lo mismo que decide `nueva_version`: la mayor parte
    de una planilla que cambió sigue siendo la misma planilla, y rehacer cuarenta
    asignaciones por una columna es cómo una revisión se convierte en un abandono.

    **No toca lo ya procesado.** Las filas que entraron con la versión anterior están en el
    catálogo y ahí se quedan; lo que cambia es con qué mapeo se va a leer la planilla la
    próxima vez.
    """

    def __init__(self, *, mapeos: PortRepositorioMapeo, publicador: PublicadorDeEventos) -> None:
        self._mapeos = mapeos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        mapeo_id: UUID,
        ahora: datetime,
    ) -> Mapeo:
        _exigir_que_pueda_mapear(rol)

        mapeo = await self._mapeos.buscar_por_id(mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo no existe")
        if not mapeo.esta_confirmado:
            # Reabrir un borrador no significa nada: ya se puede editar. Decirlo es mejor
            # que subir la version en silencio y que el numero deje de contar revisiones.
            raise EntradaInvalida("Este mapeo todavia no fue confirmado: ya se puede editar")

        mapeo.nueva_version(ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="reabrir_mapeo",
                entidad_afectada=f"Mapeo:{mapeo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return mapeo


def _exigir_que_pueda_mapear(rol: RolUsuario) -> None:
    """HU-E3-01 and HU-E3-02: «Administrador u Operador». Solo Lectura looks.

    Wider than HU-E2-04, which is the Administrador alone -- and that difference is the
    stories', not an oversight: linking a spreadsheet decides where the catalogue comes
    from, while mapping its columns is day-to-day work.
    """
    if rol is RolUsuario.SOLO_LECTURA:
        raise EntradaInvalida("Un usuario de Solo Lectura no puede modificar el mapeo")


@dataclass(frozen=True, slots=True)
class ColumnaConEjemplo:
    """Una columna de la planilla y un valor real de esa columna.

    El ejemplo existe por el primer criterio de HU-E3-02: la pantalla de revisión muestra
    un dato de muestra al lado de cada columna para que la persona pueda decidir si la
    asignación tiene sentido. Viaja junto al nombre porque se leen del mismo archivo en la
    misma pasada, y separarlos obligaría a leerlo dos veces.
    """

    nombre: str
    ejemplo: str | None


class LeerEncabezados:
    """Los encabezados de una planilla vinculada, con un ejemplo de cada columna.

    Es el paso que faltaba entre subir el archivo y proponer el mapeo: `ProponerMapeo`
    recibe las columnas ya leídas —porque no le importa de dónde salieron, y así se lo
    puede probar sin un archivo— y alguien tiene que leerlas.

    **El ejemplo sale de la primera fila con contenido, no de la primera fila.** Una
    planilla real suele traer una fila en blanco bajo el encabezado, y mostrar una columna
    de ejemplos vacíos convierte la ayuda en ruido.

    **Nada de esto llega al modelo.** `ProponerMapeo` recibe los ejemplos y los guarda en
    la entrada del mapeo para la pantalla; al modelo le manda sólo los nombres. Es la
    decisión D12, y el test que la protege vive en `test_mapeos.py`.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        almacenamiento: PortAlmacenamientoDeArchivos,
        lector: PortLectorDePlanilla,
    ) -> None:
        self._vinculos = vinculos
        self._almacenamiento = almacenamiento
        self._lector = lector

    async def ejecutar(self, *, vinculo_id: UUID) -> tuple[ColumnaConEjemplo, ...]:
        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")
        if vinculo.archivo is None:
            # Google Sheets y Excel Online se leen por su propio adaptador, no de R2. Que
            # esta ruta no los cubra es una limitación honesta y no un error del usuario.
            raise EntradaInvalida(
                "Sólo se pueden leer los encabezados de una planilla subida como archivo"
            )

        contenido = await self._almacenamiento.leer(vinculo.archivo.clave)
        planilla = self._lector.leer(contenido=contenido, nombre=vinculo.archivo.nombre_original)
        return tuple(
            ColumnaConEjemplo(nombre=columna, ejemplo=_primer_ejemplo(planilla, columna))
            for columna in planilla.columnas
        )


def _primer_ejemplo(planilla: PlanillaLeida, columna: str) -> str | None:
    """El primer valor no vacío de la columna, o `None` si la columna está vacía entera."""
    for fila in planilla.filas:
        valor = fila.celdas.get(columna, "").strip()
        if valor:
            return valor
    return None
