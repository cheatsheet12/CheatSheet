"""Generar y descargar un reporte (HU-E10-03).

Lo que se prueba acá:

- **Un período sin datos no crea una fila.** El segundo criterio de la historia pide un
  mensaje, y el historial del último criterio no tiene por qué llenarse de reportes fallidos
  que nadie pidió.
- **Un fallo del almacenamiento deja la fila en `FALLIDO`**, no la borra: es la evidencia que
  alguien va a buscar cuando pregunte por qué su contador no recibió nada.
- **El CSV sale con `;` y con BOM.** Se descubre cuando el contador abre el archivo, no antes:
  Excel en español interpreta la coma como separador decimal, y sin BOM los acentos salen rotos.
- **Solo Lectura no genera.** El guarda vive en el caso de uso, no en el router — que es lo que
  PRU-09 enseñó.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.reporting.application.errors import (
    GeneracionFallida,
    ReporteInexistente,
    ReporteNoDescargable,
    SinDatosEnElPeriodo,
)
from cheatsheet.contexts.reporting.application.generacion import (
    DescargarReporte,
    GenerarReporte,
    ListarReportes,
    serializar,
)
from cheatsheet.contexts.reporting.application.ports import FilaDeReporte, TotalesDeFacturacion
from cheatsheet.contexts.reporting.domain.reporte import (
    MENSAJE_SIN_DATOS,
    EstadoReporte,
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.reporting.application.dobles import (
    ArchivosEnMemoria,
    BitacoraFalsa,
    CobranzasFalsas,
    FacturacionFalsa,
    PublicadorEnMemoria,
    RepositorioReportesEnMemoria,
)

AHORA = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
MARZO = Periodo.del_mes(2026, 3)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())

FILAS = [
    FilaDeReporte({"fecha": "05/03/2026", "cliente": "Ferretería Ñandú", "total": "12500.55"}),
    FilaDeReporte({"fecha": "12/03/2026", "cliente": "Kiosco El Sol", "total": "3000.00"}),
]


class Escenario:
    def __init__(self, *, filas: list[FilaDeReporte] | None = None) -> None:
        self.reportes = RepositorioReportesEnMemoria()
        self.archivos = ArchivosEnMemoria()
        self.publicador = PublicadorEnMemoria()
        self.facturacion = FacturacionFalsa(
            totales=TotalesDeFacturacion(
                total=Decimal("15500.55"), cantidad=2, por_tipo={}, por_semana={}
            ),
            filas=filas if filas is not None else FILAS,
        )

    def caso(self) -> GenerarReporte:
        return GenerarReporte(
            reportes=self.reportes,
            facturacion=self.facturacion,
            cobranzas=CobranzasFalsas(),
            bitacora=BitacoraFalsa(),
            archivos=self.archivos,
            publicador=self.publicador,
        )

    async def generar(
        self,
        *,
        rol: RolUsuario = RolUsuario.ADMINISTRADOR,
        tipo: TipoReporte = TipoReporte.FACTURACION,
        formato: FormatoReporte = FormatoReporte.CSV,
    ) -> Reporte:
        return await self.caso().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            tipo=tipo,
            formato=formato,
            periodo=MARZO,
            ahora=AHORA,
        )


class TestGenerar:
    @pytest.mark.asyncio
    async def test_deja_el_reporte_listo_y_descargable(self) -> None:
        escenario = Escenario()
        reporte = await escenario.generar()
        assert reporte.estado is EstadoReporte.LISTO
        assert reporte.es_descargable
        assert reporte.referencia_archivo in escenario.archivos.guardados

    @pytest.mark.asyncio
    async def test_un_periodo_sin_datos_no_crea_la_fila(self) -> None:
        escenario = Escenario(filas=[])
        with pytest.raises(SinDatosEnElPeriodo) as error:
            await escenario.generar()
        assert str(error.value) == MENSAJE_SIN_DATOS
        assert escenario.reportes.reportes == {}

    @pytest.mark.asyncio
    async def test_un_fallo_del_almacenamiento_deja_la_fila_en_fallido(self) -> None:
        escenario = Escenario()
        escenario.archivos.falla = True
        with pytest.raises(GeneracionFallida):
            await escenario.generar()
        guardados = list(escenario.reportes.reportes.values())
        assert [uno.estado for uno in guardados] == [EstadoReporte.FALLIDO]

    @pytest.mark.asyncio
    async def test_solo_lectura_no_genera(self) -> None:
        escenario = Escenario()
        with pytest.raises(OperacionNoPermitida):
            await escenario.generar(rol=RolUsuario.SOLO_LECTURA)
        assert escenario.reportes.reportes == {}

    @pytest.mark.asyncio
    async def test_el_operador_si_genera(self) -> None:
        reporte = await Escenario().generar(rol=RolUsuario.OPERADOR)
        assert reporte.esta_listo

    @pytest.mark.asyncio
    async def test_deja_rastro_en_la_bitacora(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        acciones = [getattr(uno, "accion", "") for uno in escenario.publicador.eventos]
        assert acciones == ["generar_reporte:FACTURACION"]


class TestDescargar:
    @pytest.mark.asyncio
    async def test_devuelve_los_bytes_con_su_tipo_y_su_nombre(self) -> None:
        escenario = Escenario()
        reporte = await escenario.generar()
        contenido, tipo, nombre = await DescargarReporte(
            escenario.reportes, escenario.archivos
        ).ejecutar(reporte.id)
        assert contenido.startswith(b"\xef\xbb\xbf")
        assert tipo.startswith("text/csv")
        assert nombre == "facturacion-20260301-20260331.csv"

    @pytest.mark.asyncio
    async def test_un_reporte_inexistente(self) -> None:
        escenario = Escenario()
        with pytest.raises(ReporteInexistente):
            await DescargarReporte(escenario.reportes, escenario.archivos).ejecutar(uuid4())

    @pytest.mark.asyncio
    async def test_un_reporte_que_no_termino_no_se_descarga(self) -> None:
        escenario = Escenario()
        escenario.archivos.falla = True
        with pytest.raises(GeneracionFallida):
            await escenario.generar()
        fallido = next(iter(escenario.reportes.reportes.values()))
        with pytest.raises(ReporteNoDescargable):
            await DescargarReporte(escenario.reportes, escenario.archivos).ejecutar(fallido.id)


class TestHistorial:
    @pytest.mark.asyncio
    async def test_lista_lo_generado(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        assert len(await ListarReportes(escenario.reportes).ejecutar()) == 1


class TestSerializacion:
    def test_el_csv_usa_punto_y_coma_y_bom(self) -> None:
        """Las dos cosas se descubren cuando alguien abre el archivo, no antes."""
        salida = serializar(FILAS, FormatoReporte.CSV).decode("utf-8-sig")
        assert salida.splitlines()[0] == "fecha;cliente;total"
        assert "12500.55" in salida

    def test_el_xml_escapa_lo_que_escribio_un_usuario(self) -> None:
        """Un nombre de cliente con un `&` produciría un XML que el contador no puede abrir."""
        filas = [FilaDeReporte({"cliente": "Pérez & Hijos", "total": "1.00"})]
        salida = serializar(filas, FormatoReporte.XML).decode("utf-8")
        assert "&amp;" in salida
        assert "Pérez & Hijos" not in salida

    def test_el_pdf_sale_como_pdf(self) -> None:
        salida = serializar(FILAS, FormatoReporte.PDF)
        assert salida.startswith(b"%PDF")
