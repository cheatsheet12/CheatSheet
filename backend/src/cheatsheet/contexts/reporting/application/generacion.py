"""Generar y descargar reportes (HU-E10-03).

**Administrador y Operador generan**; el contador externo y Solo Lectura miran el tablero pero
no piden archivos. Los guardas viven acá y no sólo en el router.

Tres cosas del archivo:

- **Se comprueba que haya datos antes de crear la fila** (segundo criterio). Un `Reporte` que
  nace fallido porque el mes estaba vacío es ruido en el historial que el último criterio pide
  mostrar.

- **La generación es síncrona.** El estado `EN_CURSO` existe en el DER y se usa, pero el
  archivo se arma dentro del request: un CSV de un mes de una PyME son kilobytes. Encolarlo
  agregaría un worker, una cola y una pantalla de espera para ahorrar medio segundo. Está
  anotado en los pendientes por si algún día deja de ser cierto — y el estado ya está para
  cuando pase.

- **Un fallo deja la fila en `FALLIDO`, no la borra.** Es la evidencia de que hubo un problema.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.reporting.application.errors import (
    GeneracionFallida,
    ReporteInexistente,
    ReporteNoDescargable,
    SinDatosEnElPeriodo,
)
from cheatsheet.contexts.reporting.application.ports import (
    FilaDeReporte,
    PortArchivos,
    PortBitacora,
    PortCobranzas,
    PortFacturacion,
    PortRepositorioReportes,
)
from cheatsheet.contexts.reporting.domain.reporte import (
    MENSAJE_SIN_DATOS,
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import OperacionNoPermitida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

logger = obtener_logger(__name__)

MOTIVO_SIN_PERMISO = "Solo un Administrador u Operador puede generar reportes"

#: El tipo MIME de cada formato, para que la descarga se abra con lo que corresponde.
TIPOS_MIME: dict[FormatoReporte, str] = {
    FormatoReporte.CSV: "text/csv; charset=utf-8",
    FormatoReporte.XML: "application/xml; charset=utf-8",
    FormatoReporte.PDF: "application/pdf",
}


def _exigir_gestor(rol: RolUsuario) -> None:
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise OperacionNoPermitida(MOTIVO_SIN_PERMISO)


class ListarReportes:
    """El historial del último criterio de HU-E10-03: tipo, formato y período."""

    def __init__(self, reportes: PortRepositorioReportes) -> None:
        self._reportes = reportes

    async def ejecutar(self) -> list[Reporte]:
        return await self._reportes.listar()


class GenerarReporte:
    """HU-E10-03. Arma el archivo, lo guarda y deja el reporte listo para descargar.

    Levanta `GeneracionFallida` **después** de guardar la fila en `FALLIDO`: quien abre la
    transacción tiene que confirmarla antes de relanzar, o la fila se pierde (D65).
    """

    def __init__(
        self,
        *,
        reportes: PortRepositorioReportes,
        facturacion: PortFacturacion,
        cobranzas: PortCobranzas,
        bitacora: PortBitacora,
        archivos: PortArchivos,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._reportes = reportes
        self._facturacion = facturacion
        self._cobranzas = cobranzas
        self._bitacora = bitacora
        self._archivos = archivos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        tipo: TipoReporte,
        formato: FormatoReporte,
        periodo: Periodo,
        ahora: datetime,
    ) -> Reporte:
        _exigir_gestor(rol)

        filas = await self._filas_de(tipo, periodo)
        if not filas:
            # Antes de crear la fila. Ver el docstring del módulo.
            raise SinDatosEnElPeriodo(MENSAJE_SIN_DATOS)

        reporte = Reporte(
            id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            tipo=tipo,
            formato=formato,
            periodo=periodo,
            created_at=ahora,
        )
        await self._reportes.agregar(reporte)
        reporte.empezar()
        await self._reportes.guardar(reporte)

        try:
            contenido = serializar(filas, formato)
            clave = f"reportes/{empresa_id}/{reporte.id}.{formato.value.lower()}"
            referencia = await self._archivos.guardar(
                clave=clave, contenido=contenido, tipo=TIPOS_MIME[formato]
            )
        except Exception as fallo:
            # `Exception` acotada por el motivo: el adaptador de almacenamiento puede levantar
            # lo que su SDK levante, y enumerarlos acá acoplaría este caso de uso a su
            # infraestructura. Lo que importa es que **la fila quede en `FALLIDO`** y no
            # desaparezca.
            reporte.fallar()
            await self._reportes.guardar(reporte)
            logger.warning("reporte_no_generado", reporte_id=str(reporte.id))
            raise GeneracionFallida("No se pudo generar el archivo del reporte") from fallo

        reporte.completar(referencia)
        await self._reportes.guardar(reporte)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.REPORTING,
                accion=f"generar_reporte:{tipo.value}",
                entidad_afectada=f"Reporte:{reporte.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return reporte

    async def _filas_de(self, tipo: TipoReporte, periodo: Periodo) -> list[FilaDeReporte]:
        if tipo is TipoReporte.COBROS:
            return await self._cobranzas.filas(periodo)
        if tipo is TipoReporte.OPERACIONES:
            return await self._bitacora.filas(periodo)
        # `FACTURACION` y `RESUMEN_EJECUTIVO` salen de los mismos comprobantes: el resumen es
        # una vista distinta del mismo dato, no otro dato.
        return await self._facturacion.filas(periodo)


class DescargarReporte:
    """Los bytes del archivo, si el reporte está listo y tiene uno."""

    def __init__(self, reportes: PortRepositorioReportes, archivos: PortArchivos) -> None:
        self._reportes = reportes
        self._archivos = archivos

    async def ejecutar(self, reporte_id: UUID) -> tuple[bytes, str, str]:
        """Devuelve `(contenido, tipo MIME, nombre sugerido)`."""
        reporte = await self._reportes.buscar_por_id(reporte_id)
        if reporte is None:
            raise ReporteInexistente("El reporte no existe")
        if not reporte.es_descargable or reporte.referencia_archivo is None:
            raise ReporteNoDescargable("El reporte todavía no está disponible para descargar")

        contenido = await self._archivos.leer(reporte.referencia_archivo)
        nombre = (
            f"{reporte.tipo.value.lower()}-{reporte.periodo.desde:%Y%m%d}-"
            f"{reporte.periodo.hasta:%Y%m%d}.{reporte.formato.value.lower()}"
        )
        return contenido, TIPOS_MIME[reporte.formato], nombre


def serializar(filas: list[FilaDeReporte], formato: FormatoReporte) -> bytes:
    """Las filas, en el formato pedido.

    **CSV con `;` y BOM.** Excel en español interpreta la coma como separador decimal, así que
    un CSV con comas abre en una sola columna en la máquina del contador; y sin BOM, los
    acentos salen rotos. Las dos cosas se descubren cuando alguien abre el archivo, no antes.
    """
    if formato is FormatoReporte.CSV:
        return _a_csv(filas)
    if formato is FormatoReporte.XML:
        return _a_xml(filas)
    return _a_pdf(filas)


def _a_csv(filas: list[FilaDeReporte]) -> bytes:
    import csv
    import io

    salida = io.StringIO()
    columnas = list(filas[0].valores)
    escritor = csv.DictWriter(salida, fieldnames=columnas, delimiter=";", lineterminator="\n")
    escritor.writeheader()
    for fila in filas:
        escritor.writerow(fila.valores)
    return b"\xef\xbb\xbf" + salida.getvalue().encode("utf-8")


def _a_xml(filas: list[FilaDeReporte]) -> bytes:
    """XML plano, con los valores escapados.

    Se arma con `ElementTree` y no concatenando cadenas: un nombre de cliente con un `&` es
    entrada de un usuario, y concatenar produciría un XML roto que el contador no puede abrir.
    """
    from xml.etree.ElementTree import Element, SubElement, tostring

    raiz = Element("reporte")
    for fila in filas:
        nodo = SubElement(raiz, "fila")
        for clave, valor in fila.valores.items():
            SubElement(nodo, clave).text = valor
    cuerpo: bytes = tostring(raiz, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + cuerpo


def _a_pdf(filas: list[FilaDeReporte]) -> bytes:
    """El resumen ejecutivo, en una página.

    Usa el mismo `reportlab` que el comprobante imprimible del épico 5, y por el mismo motivo:
    ya está, es liviano, y no pide un navegador para maquetar una página.
    """
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer, pagesize=A4)
    _, alto = A4
    y = alto - 25 * mm

    lienzo.setFont("Helvetica-Bold", 14)
    lienzo.drawString(20 * mm, y, "Resumen ejecutivo")
    y -= 12 * mm

    lienzo.setFont("Helvetica", 9)
    for fila in filas[:40]:
        # Cuarenta filas es una página. Un resumen que se pasa de largo dejó de ser un
        # resumen, y el listado completo se pide en CSV.
        texto = "  ".join(f"{clave}: {valor}" for clave, valor in fila.valores.items())
        lienzo.drawString(20 * mm, y, texto[:110])
        y -= 6 * mm
        if y < 20 * mm:
            break

    lienzo.showPage()
    lienzo.save()
    return buffer.getvalue()


__all__ = [
    "TIPOS_MIME",
    "DescargarReporte",
    "GenerarReporte",
    "ListarReportes",
    "serializar",
]
