"""El paquete contable y el acceso del contador (HU-E10-04, HU-E10-05, HU-E10-06).

Tres historias, un mismo objeto: una **carpeta cerrada de un mes** que sale sola y que alguien
de afuera puede descargar sin tener cuenta.

Las decisiones que gobiernan este archivo:

- **Configurar el envío es exclusivo del Administrador** (HU-E10-04 RN-04, textual), y el
  acceso del contador también: el actor de HU-E10-05 es el Administrador y lo que se comparte
  es la documentación fiscal completa de la empresa. El Operador genera reportes sueltos
  (HU-E10-03) y no reparte llaves.

- **El paquete de un mes vacío se genera igual.** Al revés que el reporte suelto, que se niega
  (`SinDatosEnElPeriodo`): un contador que no recibe nada no puede distinguir «no hubo
  actividad» de «el sistema no lo mandó», y esa diferencia es la única razón por la que el
  envío automático existe.

- **El enlace se emite una sola vez.** Lo que se guarda es el hash; el valor en claro sale en
  el mail y nadie más lo vuelve a ver, ni siquiera el administrador que lo mandó. Si se
  perdió, se revoca y se invita de nuevo — que además es lo que deja rastro.

- **Un contador activo por empresa** (HU-E10-05 RN-04). Invitar a otro sin revocar levanta:
  «quién tiene acceso» tiene que tener una respuesta y no una lista.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.reporting.application.errors import (
    AccesoNoDisponible,
    ContadorYaInvitado,
    GeneracionFallida,
    PaqueteInexistente,
)
from cheatsheet.contexts.reporting.application.generacion import serializar
from cheatsheet.contexts.reporting.application.ports import (
    FilaDeReporte,
    PortArchivos,
    PortAvisoAlContador,
    PortBitacora,
    PortCobranzas,
    PortFacturacion,
    PortRepositorioPaquetes,
    PortRepositorioTokens,
    PortTokenDeAcceso,
    TotalesDeFacturacion,
)
from cheatsheet.contexts.reporting.domain.paquete import (
    CONTENIDO_COMPLETO,
    MENSAJE_ACCESO_NO_DISPONIBLE,
    VIGENCIA_DEL_ENLACE,
    ConfiguracionDelPaquete,
    ContenidoDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import (
    FORMATOS_POR_TIPO,
    FormatoReporte,
    Periodo,
    TipoReporte,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

logger = obtener_logger(__name__)

MOTIVO_SOLO_ADMINISTRADOR = "Solo un Administrador puede configurar el paquete contable"
TIPO_MIME_DEL_PAQUETE = "application/zip"

#: Qué reporte es cada contenido del paquete (HU-E10-04 RN-03).
#:
#: Facturas y notas de crédito salen del mismo reporte porque salen de la misma tabla; lo que
#: las separa es el filtro, no el tipo — y por eso el ACL de facturación recibe
#: `solo_notas_de_credito` en vez de que este módulo parta una lista mezclada mirando texto.
REPORTE_DE: dict[ContenidoDelPaquete, TipoReporte] = {
    ContenidoDelPaquete.FACTURAS: TipoReporte.FACTURACION,
    ContenidoDelPaquete.NOTAS_DE_CREDITO: TipoReporte.FACTURACION,
    ContenidoDelPaquete.REPORTE_DE_COBROS: TipoReporte.COBROS,
    ContenidoDelPaquete.LOG_DE_OPERACIONES: TipoReporte.OPERACIONES,
    ContenidoDelPaquete.RESUMEN_EJECUTIVO: TipoReporte.RESUMEN_EJECUTIVO,
}

#: Cómo se llama cada uno adentro del ZIP. En minúsculas y sin acentos: el archivo lo abre un
#: contador en su máquina, y un nombre con eñes viaja mal entre Windows, macOS y un correo.
NOMBRE_DE: dict[ContenidoDelPaquete, str] = {
    ContenidoDelPaquete.FACTURAS: "facturas",
    ContenidoDelPaquete.NOTAS_DE_CREDITO: "notas-de-credito",
    ContenidoDelPaquete.REPORTE_DE_COBROS: "cobros",
    ContenidoDelPaquete.LOG_DE_OPERACIONES: "operaciones",
    ContenidoDelPaquete.RESUMEN_EJECUTIVO: "resumen-ejecutivo",
}


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMINISTRADOR)


def periodo_cerrado(ahora: datetime) -> Periodo:
    """El mes anterior al que corre (HU-E10-04 RN-01: «los datos del mes cerrado»).

    El mes **cerrado** y no el corriente: un paquete armado el día 5 con el mes en curso
    llevaría cinco días de datos y se llamaría igual que el completo.
    """
    primero = ahora.date().replace(day=1)
    anterior = primero - timedelta(days=1)
    return Periodo.del_mes(anterior.year, anterior.month)


@dataclass(frozen=True, slots=True)
class EstadoDelContador:
    """Lo que PAN-REP-02 muestra sobre el acceso externo (HU-E10-05).

    **Sin el valor del enlace.** No está porque no existe: lo que se guarda es su hash. La
    pantalla dice «Invitado con acceso limitado», que es exactamente lo que el criterio pide.
    """

    email: str | None
    invitado: bool
    vence: datetime | None
    accesos: int


@dataclass(frozen=True, slots=True)
class VistaDeConfiguracion:
    """PAN-REP-02 entera: el envío, su próxima fecha y el estado del contador."""

    configuracion: ConfiguracionDelPaquete
    proximo_envio: datetime | None
    contador: EstadoDelContador


class VerConfiguracionDelPaquete:
    """Primer criterio de HU-E10-04: estado, día, formato y contenido.

    Si nunca se configuró, devuelve la configuración por defecto **sin persistirla**. Una fila
    escrita por el solo hecho de mirar una pantalla convierte una consulta en una escritura, y
    después nadie sabe si el 5 lo eligió alguien o lo puso el sistema.
    """

    def __init__(self, *, paquetes: PortRepositorioPaquetes, tokens: PortRepositorioTokens) -> None:
        self._paquetes = paquetes
        self._tokens = tokens

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> VistaDeConfiguracion:
        configuracion = await self._paquetes.configuracion() or ConfiguracionDelPaquete(
            empresa_id=empresa_id
        )
        token = await self._tokens.activo_de_la_empresa()
        return VistaDeConfiguracion(
            configuracion=configuracion,
            proximo_envio=configuracion.proximo_envio(ahora),
            contador=EstadoDelContador(
                email=configuracion.email_contador,
                invitado=token is not None and token.esta_vigente(ahora),
                vence=token.vencimiento if token is not None else None,
                accesos=token.accesos if token is not None else 0,
            ),
        )


class ConfigurarPaquete:
    """HU-E10-04: día, formatos, contenido, email del contador y el interruptor.

    Una sola operación y no cinco `PATCH`: la pantalla es un formulario con un botón, y
    partirla en cinco rutas dejaría estados intermedios donde el envío está activo con un día
    que el usuario todavía no confirmó.
    """

    def __init__(
        self, *, paquetes: PortRepositorioPaquetes, publicador: PublicadorDeEventos
    ) -> None:
        self._paquetes = paquetes
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        dia_de_envio: int,
        formatos: frozenset[str],
        contenido: frozenset[ContenidoDelPaquete],
        email_contador: str | None,
        activo: bool,
        ahora: datetime,
    ) -> ConfiguracionDelPaquete:
        _exigir_administrador(rol)

        configuracion = await self._paquetes.configuracion() or ConfiguracionDelPaquete(
            empresa_id=empresa_id
        )
        if email_contador is not None:
            configuracion.asignar_contador(email_contador, ahora)
        configuracion.configurar(
            dia_de_envio=dia_de_envio,
            formatos=formatos,
            contenido=contenido or CONTENIDO_COMPLETO,
            momento=ahora,
        )
        # Activar va último y por su propio método: es el que levanta el mensaje textual del
        # tercer criterio cuando falta el email, y hacerlo antes de guardar el email nuevo lo
        # levantaría sobre datos viejos.
        if activo:
            configuracion.activar(ahora)
        else:
            configuracion.desactivar(ahora)

        await self._paquetes.guardar_configuracion(configuracion)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion="configurar_paquete_contable",
                entidad_afectada=f"ConfiguracionDelPaquete:{empresa_id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return configuracion


class ListarPaquetes:
    """Los paquetes ya armados, del más nuevo al más viejo. Lo que ve el contador y el panel."""

    def __init__(self, paquetes: PortRepositorioPaquetes) -> None:
        self._paquetes = paquetes

    async def ejecutar(self, *, limite: int = 24) -> list[PaqueteContable]:
        return await self._paquetes.listar(limite=limite)


class GenerarPaqueteContable:
    """HU-E10-04. Arma el ZIP del período y lo deja disponible.

    Lo usan dos llamadores: el barrido mensual y el botón «generar paquete de prueba» del
    cuarto criterio. Es el mismo caso de uso a propósito — un paquete de prueba que se armara
    por otro camino probaría otra cosa que la que se manda.

    **Rearma el paquete si ya existía.** Un mes tiene un paquete (índice único), y volver a
    generar reemplaza su archivo en lugar de fallar: es lo que hace que el botón de prueba se
    pueda apretar dos veces, y lo que permite rehacer un paquete cuyo archivo se perdió.
    """

    def __init__(
        self,
        *,
        paquetes: PortRepositorioPaquetes,
        facturacion: PortFacturacion,
        cobranzas: PortCobranzas,
        bitacora: PortBitacora,
        archivos: PortArchivos,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._paquetes = paquetes
        self._facturacion = facturacion
        self._cobranzas = cobranzas
        self._bitacora = bitacora
        self._archivos = archivos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId | None,
        periodo: Periodo,
        contenido: frozenset[ContenidoDelPaquete],
        formatos: frozenset[str],
        ahora: datetime,
    ) -> PaqueteContable:
        anio, mes = periodo.desde.year, periodo.desde.month
        paquete = await self._paquetes.del_periodo(anio, mes)
        if paquete is None:
            paquete = PaqueteContable(
                id=uuid4(),
                empresa_id=empresa_id,
                periodo_anio=anio,
                periodo_mes=mes,
                created_at=ahora,
            )
            await self._paquetes.agregar(paquete)

        archivos = await self._armar_contenido(periodo, contenido, formatos, paquete)
        try:
            clave = f"paquetes/{empresa_id}/{paquete.etiqueta}.zip"
            referencia = await self._archivos.guardar(
                clave=clave, contenido=_comprimir(archivos), tipo=TIPO_MIME_DEL_PAQUETE
            )
        except Exception as fallo:
            # `Exception` acotada por el motivo, como en `GenerarReporte`: el adaptador de
            # almacenamiento levanta lo que levante su SDK, y enumerarlo acá ataría este caso
            # de uso a su infraestructura.
            logger.warning("paquete_no_generado", periodo=paquete.etiqueta)
            raise GeneracionFallida("No se pudo generar el paquete contable") from fallo

        paquete.referencia_archivo = referencia
        await self._paquetes.guardar(paquete)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion="generar_paquete_contable",
                entidad_afectada=f"PaqueteContable:{paquete.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return paquete

    async def _armar_contenido(
        self,
        periodo: Periodo,
        contenido: frozenset[ContenidoDelPaquete],
        formatos: frozenset[str],
        paquete: PaqueteContable,
    ) -> dict[str, bytes]:
        """Un archivo por contenido y por formato, y los totales que los describen.

        **Un contenido sin filas no produce archivo, pero sí produce total.** Un CSV con sólo
        el encabezado le hace perder tiempo a quien lo abre; el total en cero, en cambio, es
        justamente lo que dice que ese mes no hubo notas de crédito.
        """
        totales = await self._facturacion.totales(periodo)
        armados: dict[str, bytes] = {}

        for item in sorted(contenido, key=lambda uno: uno.value):
            filas = await self._filas_de(item, periodo)
            paquete.registrar_totales(item.value, len(filas), _monto_de(item, totales))
            if not filas:
                continue
            for formato in _formatos_de(REPORTE_DE[item], formatos):
                armados[f"{NOMBRE_DE[item]}.{formato.value.lower()}"] = serializar(filas, formato)
        return armados

    async def _filas_de(self, item: ContenidoDelPaquete, periodo: Periodo) -> list[FilaDeReporte]:
        if item is ContenidoDelPaquete.REPORTE_DE_COBROS:
            return await self._cobranzas.filas(periodo)
        if item is ContenidoDelPaquete.LOG_DE_OPERACIONES:
            return await self._bitacora.filas(periodo)
        if item is ContenidoDelPaquete.NOTAS_DE_CREDITO:
            return await self._facturacion.filas(periodo, solo_notas_de_credito=True)
        if item is ContenidoDelPaquete.FACTURAS:
            return await self._facturacion.filas(periodo, solo_notas_de_credito=False)
        return await self._facturacion.filas(periodo)


class InvitarContador:
    """HU-E10-05. Emite el enlace, lo manda por mail y guarda su hash.

    El token queda atado al **último paquete**, que es lo que el DER modela y lo que el
    contador va a buscar. Si la empresa todavía no tiene ninguno, no se inventa uno vacío: se
    contesta que no hay paquete, porque compartir una carpeta que no existe es prometer algo
    que el enlace no puede cumplir.
    """

    def __init__(
        self,
        *,
        paquetes: PortRepositorioPaquetes,
        tokens: PortRepositorioTokens,
        generador: PortTokenDeAcceso,
        aviso: PortAvisoAlContador,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._paquetes = paquetes
        self._tokens = tokens
        self._generador = generador
        self._aviso = aviso
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        email: str,
        nombre_de_la_empresa: str,
        base_del_enlace: str,
        ahora: datetime,
    ) -> str:
        """Devuelve **el enlace en claro**, que existe sólo en esta vuelta."""
        _exigir_administrador(rol)

        vigente = await self._tokens.activo_de_la_empresa()
        if vigente is not None and vigente.esta_vigente(ahora):
            raise ContadorYaInvitado(
                "Ya hay un contador con acceso. Revocá el acceso actual antes de invitar a otro."
            )

        paquetes = await self._paquetes.listar(limite=1)
        if not paquetes:
            raise PaqueteInexistente(
                "Todavía no hay ningún paquete contable para compartir. Generá uno primero."
            )

        valor = self._generador.emitir()
        token = TokenDeAccesoContable(
            id=uuid4(),
            paquete_id=paquetes[0].id,
            empresa_id=empresa_id,
            valor_hash=self._generador.hashear(valor),
            email_contador=email.strip().lower(),
            vencimiento=ahora + VIGENCIA_DEL_ENLACE,
            created_at=ahora,
        )
        await self._tokens.agregar(token)

        enlace = f"{base_del_enlace.rstrip('/')}/{valor}"
        await self._aviso.enviar_enlace(
            email=token.email_contador,
            enlace=enlace,
            empresa=nombre_de_la_empresa,
            vence=token.vencimiento,
        )
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion="invitar_contador",
                entidad_afectada=f"TokenDeAccesoContable:{token.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return enlace


class RevocarAccesoDelContador:
    """HU-E10-05 RN-03: invalida el enlace **de inmediato**."""

    def __init__(self, *, tokens: PortRepositorioTokens, publicador: PublicadorDeEventos) -> None:
        self._tokens = tokens
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        ahora: datetime,
    ) -> None:
        _exigir_administrador(rol)

        token = await self._tokens.activo_de_la_empresa()
        if token is None:
            # Nada que revocar es un resultado, no un error: el botón de una pantalla que se
            # dejó abierta mientras otro administrador revocaba no tiene por qué explotar.
            return
        token.revocar()
        await self._tokens.guardar(token)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion="revocar_acceso_del_contador",
                entidad_afectada=f"TokenDeAccesoContable:{token.id}",
                resultado=Resultado.COMPLETADO,
            )
        )


@dataclass(frozen=True, slots=True)
class AccesoDelContador:
    """Lo que hay del otro lado del enlace: los paquetes, y nada más.

    **No lleva clientes, ni comprobantes, ni cobros** (HU-E10-06 RN-02). Lo que el contador ve
    es lo que este objeto contiene, y por eso es lo que hay que leer para saber qué ve.
    """

    empresa_id: EmpresaId
    paquetes: list[PaqueteContable]
    vence: datetime


class AccederComoContador:
    """HU-E10-06. Valida el enlace, cuenta el acceso y devuelve los paquetes.

    **Cuenta el acceso antes de devolver nada** (RN-03). Contarlo después dejaría sin registrar
    justo los accesos que terminaron en error, que son los que uno querría poder mirar.

    El mensaje de un enlace vencido y el de uno revocado son **el mismo** (`AccesoNoDisponible`,
    texto de la historia): distinguirlos le diría a quien probó un enlace ajeno si alguna vez
    existió.
    """

    def __init__(
        self,
        *,
        tokens: PortRepositorioTokens,
        paquetes: PortRepositorioPaquetes,
        generador: PortTokenDeAcceso,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._tokens = tokens
        self._paquetes = paquetes
        self._generador = generador
        self._publicador = publicador

    async def ejecutar(self, *, valor: str, ahora: datetime) -> AccesoDelContador:
        token = await self._tokens.buscar_por_hash(self._generador.hashear(valor))
        if token is None or not token.esta_vigente(ahora):
            raise AccesoNoDisponible(MENSAJE_ACCESO_NO_DISPONIBLE)

        token.registrar_acceso(ahora)
        await self._tokens.guardar(token)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=token.empresa_id,
                # Sin usuario: el contador no tiene cuenta. Lo que lo identifica en la bitácora
                # es la entidad afectada —el token— y su email, que está en la fila.
                usuario_id=None,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion="acceso_del_contador",
                entidad_afectada=f"TokenDeAccesoContable:{token.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return AccesoDelContador(
            empresa_id=token.empresa_id,
            paquetes=await self._paquetes.listar(),
            vence=token.vencimiento,
        )


class DescargarPaquete:
    """Los bytes del ZIP. Lo usan el panel y el contador, con el mismo control: el paquete
    tiene que existir en **esta** empresa y tener archivo.

    Que el contador llegue acá sólo después de `AccederComoContador` no es un detalle de
    ruteo: la sesión con la que corre esta consulta está acotada a la empresa que el token
    resolvió, así que pedir el id de un paquete ajeno no devuelve nada.
    """

    def __init__(self, *, paquetes: PortRepositorioPaquetes, archivos: PortArchivos) -> None:
        self._paquetes = paquetes
        self._archivos = archivos

    async def ejecutar(self, paquete_id: UUID) -> tuple[bytes, str, str]:
        """Devuelve `(contenido, tipo MIME, nombre sugerido)`."""
        paquete = await self._paquetes.buscar_por_id(paquete_id)
        if paquete is None:
            raise PaqueteInexistente("El paquete contable no existe")
        if paquete.referencia_archivo is None:
            raise PaqueteInexistente("El paquete contable todavía no tiene archivo")
        contenido = await self._archivos.leer(paquete.referencia_archivo)
        return contenido, TIPO_MIME_DEL_PAQUETE, f"paquete-{paquete.etiqueta}.zip"


def _formatos_de(tipo: TipoReporte, elegidos: frozenset[str]) -> list[FormatoReporte]:
    """Los formatos en que sale un contenido: los elegidos que el tipo admite.

    **Si el tipo no admite ninguno de los elegidos, sale en los suyos.** Alguien que configuró
    «sólo XML» no está pidiendo que el reporte de cobros —que sólo existe en CSV— desaparezca
    del paquete; está diciendo qué prefiere cuando hay opción.
    """
    admitidos = FORMATOS_POR_TIPO[tipo]
    pedidos = [uno for uno in sorted(admitidos, key=lambda f: f.value) if uno.value in elegidos]
    return pedidos or sorted(admitidos, key=lambda f: f.value)


def _monto_de(item: ContenidoDelPaquete, totales: TotalesDeFacturacion) -> Decimal:
    """El importe que se anota junto a la cantidad, cuando el contenido tiene importe.

    El log de operaciones no lo tiene —son eventos, no plata— y cero es la respuesta honesta.
    Los importes de facturación salen de los totales que el ACL ya calculó, y no de sumar las
    filas de texto del CSV: reconstruir un total sumando cadenas es exactamente donde aparece
    el centavo que no cierra.
    """
    if item is ContenidoDelPaquete.FACTURAS:
        return totales.facturas
    if item is ContenidoDelPaquete.NOTAS_DE_CREDITO:
        return totales.notas
    if item is ContenidoDelPaquete.RESUMEN_EJECUTIVO:
        return totales.total
    return Decimal("0.00")


def _comprimir(archivos: dict[str, bytes]) -> bytes:
    """El ZIP, determinista.

    `ZIP_DEFLATED` y no `ZIP_STORED`: lo que va adentro son CSV, que comprimen a una fracción,
    y lo que viaja es un adjunto de correo.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_:
        for nombre in sorted(archivos):
            zip_.writestr(nombre, archivos[nombre])
    return buffer.getvalue()


__all__ = [
    "NOMBRE_DE",
    "REPORTE_DE",
    "TIPO_MIME_DEL_PAQUETE",
    "AccederComoContador",
    "AccesoDelContador",
    "ConfigurarPaquete",
    "DescargarPaquete",
    "EstadoDelContador",
    "GenerarPaqueteContable",
    "InvitarContador",
    "ListarPaquetes",
    "RevocarAccesoDelContador",
    "VerConfiguracionDelPaquete",
    "VistaDeConfiguracion",
    "periodo_cerrado",
]
