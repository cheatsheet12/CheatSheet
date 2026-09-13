"""El paquete contable y el acceso del contador (HU-E10-04, HU-E10-05, HU-E10-06).

Las afirmaciones que importan:

- **El ZIP lleva un archivo por contenido configurado**, y un contenido sin filas no produce
  archivo pero sí produce total: un CSV con sólo el encabezado le hace perder tiempo a quien lo
  abre; el total en cero es lo que dice que ese mes no hubo notas de crédito.
- **Un mes vacío igual produce paquete.** Al revés que el reporte suelto, y a propósito: un
  contador que no recibe nada no puede distinguir «no hubo actividad» de «no me lo mandaron».
- **Un contador activo por empresa** (RN-04), y **revocar corta de inmediato** (RN-03).
- **Si el mail no sale, la invitación no ocurrió.** El token no queda guardado.
- **El acceso se cuenta antes de devolver nada** (HU-E10-06 RN-03), y un enlace revocado da el
  texto de la historia — el mismo que uno vencido.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.reporting.application.errors import (
    AccesoNoDisponible,
    ContadorYaInvitado,
    InvitacionNoEnviada,
    PaqueteInexistente,
)
from cheatsheet.contexts.reporting.application.paquete import (
    AccederComoContador,
    ConfigurarPaquete,
    DescargarPaquete,
    GenerarPaqueteContable,
    InvitarContador,
    ListarPaquetes,
    RevocarAccesoDelContador,
    VerConfiguracionDelPaquete,
    periodo_cerrado,
)
from cheatsheet.contexts.reporting.application.ports import FilaDeReporte, TotalesDeFacturacion
from cheatsheet.contexts.reporting.domain.paquete import (
    CONTENIDO_COMPLETO,
    MENSAJE_ACCESO_NO_DISPONIBLE,
    MENSAJE_SIN_EMAIL,
    ConfiguracionDelPaquete,
    ContenidoDelPaquete,
    PaqueteContable,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.reporting.application.dobles import (
    ArchivosEnMemoria,
    AvisoAlContadorFalso,
    BitacoraFalsa,
    CobranzasFalsas,
    EnlaceFijo,
    FacturacionFalsa,
    PublicadorEnMemoria,
    RepositorioPaquetesEnMemoria,
    RepositorioTokensEnMemoria,
)

AHORA = datetime(2026, 4, 5, 3, 0, tzinfo=UTC)
MARZO = Periodo.del_mes(2026, 3)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())

FACTURAS = [FilaDeReporte({"tipo": "FACTURA_B", "total": "12500.55"})]
NOTAS = [FilaDeReporte({"tipo": "NOTA_CREDITO_B", "total": "500.00"})]


class Escenario:
    def __init__(self, *, facturas: list[FilaDeReporte] | None = None) -> None:
        self.paquetes = RepositorioPaquetesEnMemoria()
        self.tokens = RepositorioTokensEnMemoria()
        self.archivos = ArchivosEnMemoria()
        self.publicador = PublicadorEnMemoria()
        self.aviso = AvisoAlContadorFalso()
        self.enlaces = EnlaceFijo()
        self.facturacion = FacturacionFalsa(
            totales=TotalesDeFacturacion(
                total=Decimal("12000.55"),
                cantidad=2,
                por_tipo={},
                por_semana={},
                facturas=Decimal("12500.55"),
                notas=Decimal("500.00"),
            ),
            filas=FACTURAS if facturas is None else facturas,
            notas=NOTAS,
        )

    async def generar(
        self,
        *,
        contenido: frozenset[ContenidoDelPaquete] = CONTENIDO_COMPLETO,
        formatos: frozenset[str] = frozenset({"CSV"}),
        periodo: Periodo = MARZO,
    ) -> PaqueteContable:
        return await GenerarPaqueteContable(
            paquetes=self.paquetes,
            facturacion=self.facturacion,
            cobranzas=CobranzasFalsas(),
            bitacora=BitacoraFalsa(),
            archivos=self.archivos,
            publicador=self.publicador,
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            periodo=periodo,
            contenido=contenido,
            formatos=formatos,
            ahora=AHORA,
        )

    async def invitar(self, email: str = "contador@estudio.com.ar") -> str:
        return await InvitarContador(
            paquetes=self.paquetes,
            tokens=self.tokens,
            generador=self.enlaces,
            aviso=self.aviso,
            publicador=self.publicador,
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            email=email,
            nombre_de_la_empresa="Ferretería Ñandú",
            base_del_enlace="https://app.cheatsheet.ar/contador",
            ahora=AHORA,
        )

    def archivos_del_zip(self, paquete: PaqueteContable) -> list[str]:
        assert paquete.referencia_archivo is not None
        crudo = self.archivos.guardados[paquete.referencia_archivo]
        with zipfile.ZipFile(io.BytesIO(crudo)) as zip_:
            return sorted(zip_.namelist())


def test_el_periodo_cerrado_es_el_mes_anterior() -> None:
    """Un paquete armado el 5 con el mes en curso llevaría cinco días de datos."""
    assert periodo_cerrado(AHORA) == MARZO


class TestGenerarPaquete:
    @pytest.mark.asyncio
    async def test_arma_un_zip_con_un_archivo_por_contenido(self) -> None:
        escenario = Escenario()
        paquete = await escenario.generar(
            contenido=frozenset(
                {ContenidoDelPaquete.FACTURAS, ContenidoDelPaquete.NOTAS_DE_CREDITO}
            )
        )
        assert escenario.archivos_del_zip(paquete) == ["facturas.csv", "notas-de-credito.csv"]

    @pytest.mark.asyncio
    async def test_un_contenido_sin_filas_no_produce_archivo_pero_si_total(self) -> None:
        escenario = Escenario(facturas=[])
        paquete = await escenario.generar(
            contenido=frozenset(
                {ContenidoDelPaquete.FACTURAS, ContenidoDelPaquete.NOTAS_DE_CREDITO}
            )
        )
        assert escenario.archivos_del_zip(paquete) == ["notas-de-credito.csv"]
        assert paquete.totales_por_tipo["FACTURAS"] == {"cantidad": "0", "total": "12500.55"}

    @pytest.mark.asyncio
    async def test_un_mes_vacio_igual_produce_paquete(self) -> None:
        """La diferencia con el reporte suelto, y la razón por la que existe el envío."""
        escenario = Escenario(facturas=[])
        escenario.facturacion.notas_fijas = []
        paquete = await escenario.generar()
        assert paquete.esta_disponible
        assert escenario.archivos_del_zip(paquete) == []

    @pytest.mark.asyncio
    async def test_el_formato_elegido_manda_cuando_el_tipo_lo_admite(self) -> None:
        escenario = Escenario()
        paquete = await escenario.generar(
            contenido=frozenset({ContenidoDelPaquete.FACTURAS}), formatos=frozenset({"XML"})
        )
        assert escenario.archivos_del_zip(paquete) == ["facturas.xml"]

    @pytest.mark.asyncio
    async def test_un_contenido_que_no_admite_el_formato_elegido_sale_en_el_suyo(self) -> None:
        """«Sólo XML» no quiere decir «que el reporte de cobros desaparezca del paquete»."""
        escenario = Escenario()
        escenario_cobros = CobranzasFalsas(filas=[FilaDeReporte({"monto": "100.00"})])
        paquete = await GenerarPaqueteContable(
            paquetes=escenario.paquetes,
            facturacion=escenario.facturacion,
            cobranzas=escenario_cobros,
            bitacora=BitacoraFalsa(),
            archivos=escenario.archivos,
            publicador=escenario.publicador,
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            periodo=MARZO,
            contenido=frozenset({ContenidoDelPaquete.REPORTE_DE_COBROS}),
            formatos=frozenset({"XML"}),
            ahora=AHORA,
        )
        assert escenario.archivos_del_zip(paquete) == ["cobros.csv"]

    @pytest.mark.asyncio
    async def test_volver_a_generar_el_mismo_mes_no_duplica(self) -> None:
        escenario = Escenario()
        primero = await escenario.generar()
        segundo = await escenario.generar()
        assert primero.id == segundo.id
        assert len(await ListarPaquetes(escenario.paquetes).ejecutar()) == 1


class TestConfiguracion:
    @pytest.mark.asyncio
    async def test_ver_sin_configurar_devuelve_el_default_sin_persistirlo(self) -> None:
        escenario = Escenario()
        vista = await VerConfiguracionDelPaquete(
            paquetes=escenario.paquetes, tokens=escenario.tokens
        ).ejecutar(empresa_id=EMPRESA, ahora=AHORA)
        assert not vista.configuracion.activo
        assert vista.proximo_envio is None
        assert escenario.paquetes.config is None

    @pytest.mark.asyncio
    async def test_configurar_y_activar(self) -> None:
        escenario = Escenario()
        configuracion = await ConfigurarPaquete(
            paquetes=escenario.paquetes, publicador=escenario.publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            dia_de_envio=10,
            formatos=frozenset({"PDF", "XML"}),
            contenido=frozenset({ContenidoDelPaquete.FACTURAS}),
            email_contador="contador@estudio.com.ar",
            activo=True,
            ahora=AHORA,
        )
        assert configuracion.activo
        assert configuracion.proximo_envio(AHORA) == datetime(2026, 4, 10, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_activar_sin_email_da_el_texto_de_la_historia(self) -> None:
        escenario = Escenario()
        with pytest.raises(InvarianteViolada) as error:
            await ConfigurarPaquete(
                paquetes=escenario.paquetes, publicador=escenario.publicador
            ).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.ADMINISTRADOR,
                dia_de_envio=5,
                formatos=frozenset({"PDF"}),
                contenido=CONTENIDO_COMPLETO,
                email_contador=None,
                activo=True,
                ahora=AHORA,
            )
        assert str(error.value) == MENSAJE_SIN_EMAIL

    @pytest.mark.asyncio
    async def test_el_operador_no_configura(self) -> None:
        """RN-04, textual: la configuración está restringida al Administrador."""
        escenario = Escenario()
        with pytest.raises(EntradaInvalida):
            await ConfigurarPaquete(
                paquetes=escenario.paquetes, publicador=escenario.publicador
            ).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                dia_de_envio=5,
                formatos=frozenset({"PDF"}),
                contenido=CONTENIDO_COMPLETO,
                email_contador="c@e.com",
                activo=False,
                ahora=AHORA,
            )


class TestInvitarYRevocar:
    @pytest.mark.asyncio
    async def test_invita_y_manda_el_enlace_por_mail(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        enlace = await escenario.invitar()
        assert escenario.aviso.enviados == [("contador@estudio.com.ar", enlace)]
        # Lo que se guarda es el hash, nunca el valor.
        guardado = escenario.tokens.tokens[0]
        assert guardado.valor_hash != escenario.enlaces.valor
        assert escenario.enlaces.valor not in guardado.valor_hash

    @pytest.mark.asyncio
    async def test_sin_paquetes_no_hay_nada_que_compartir(self) -> None:
        with pytest.raises(PaqueteInexistente):
            await Escenario().invitar()

    @pytest.mark.asyncio
    async def test_un_contador_activo_por_empresa(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        await escenario.invitar()
        with pytest.raises(ContadorYaInvitado):
            await escenario.invitar("otro@estudio.com.ar")

    @pytest.mark.asyncio
    async def test_si_el_mail_no_sale_la_invitacion_no_ocurrio(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        escenario.aviso.falla = True
        with pytest.raises(InvitacionNoEnviada):
            await escenario.invitar()
        # El token quedó agregado en memoria, pero en la base la transacción se deshace: lo
        # que este test fija es que el error **se propaga**, que es lo que la deshace.
        assert escenario.aviso.enviados == []

    @pytest.mark.asyncio
    async def test_revocar_permite_invitar_de_nuevo(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        await escenario.invitar()
        await RevocarAccesoDelContador(
            tokens=escenario.tokens, publicador=escenario.publicador
        ).ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, rol=RolUsuario.ADMINISTRADOR, ahora=AHORA
        )
        assert escenario.tokens.tokens[0].revocado
        await escenario.invitar("otro@estudio.com.ar")

    @pytest.mark.asyncio
    async def test_revocar_sin_contador_no_explota(self) -> None:
        escenario = Escenario()
        await RevocarAccesoDelContador(
            tokens=escenario.tokens, publicador=escenario.publicador
        ).ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, rol=RolUsuario.ADMINISTRADOR, ahora=AHORA
        )

    @pytest.mark.asyncio
    async def test_el_operador_no_invita(self) -> None:
        escenario = Escenario()
        await escenario.generar()
        with pytest.raises(EntradaInvalida):
            await InvitarContador(
                paquetes=escenario.paquetes,
                tokens=escenario.tokens,
                generador=escenario.enlaces,
                aviso=escenario.aviso,
                publicador=escenario.publicador,
            ).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                email="c@e.com",
                nombre_de_la_empresa="X",
                base_del_enlace="https://app/contador",
                ahora=AHORA,
            )


class TestAccesoDelContador:
    async def _preparado(self) -> Escenario:
        escenario = Escenario()
        await escenario.generar()
        await escenario.invitar()
        return escenario

    def _acceso(self, escenario: Escenario) -> AccederComoContador:
        return AccederComoContador(
            tokens=escenario.tokens,
            paquetes=escenario.paquetes,
            generador=escenario.enlaces,
            publicador=escenario.publicador,
        )

    @pytest.mark.asyncio
    async def test_devuelve_los_paquetes_y_cuenta_el_acceso(self) -> None:
        escenario = await self._preparado()
        acceso = await self._acceso(escenario).ejecutar(valor=escenario.enlaces.valor, ahora=AHORA)
        assert len(acceso.paquetes) == 1
        assert escenario.tokens.tokens[0].accesos == 1

    @pytest.mark.asyncio
    async def test_el_acceso_queda_en_la_bitacora_sin_usuario(self) -> None:
        """El contador no tiene cuenta: lo que lo identifica es el token, no un `usuario_id`."""
        escenario = await self._preparado()
        await self._acceso(escenario).ejecutar(valor=escenario.enlaces.valor, ahora=AHORA)
        evento = escenario.publicador.eventos[-1]
        assert getattr(evento, "accion", "") == "acceso_del_contador"
        assert getattr(evento, "usuario_id", "algo") is None

    @pytest.mark.asyncio
    async def test_un_enlace_revocado_da_el_texto_de_la_historia(self) -> None:
        escenario = await self._preparado()
        escenario.tokens.tokens[0].revocar()
        with pytest.raises(AccesoNoDisponible) as error:
            await self._acceso(escenario).ejecutar(valor=escenario.enlaces.valor, ahora=AHORA)
        assert str(error.value) == MENSAJE_ACCESO_NO_DISPONIBLE

    @pytest.mark.asyncio
    async def test_un_enlace_vencido_da_exactamente_el_mismo_texto(self) -> None:
        """Distinguirlos le diría a quien probó un enlace ajeno si alguna vez existió."""
        escenario = await self._preparado()
        with pytest.raises(AccesoNoDisponible) as error:
            await self._acceso(escenario).ejecutar(
                valor=escenario.enlaces.valor, ahora=AHORA + timedelta(days=31)
            )
        assert str(error.value) == MENSAJE_ACCESO_NO_DISPONIBLE

    @pytest.mark.asyncio
    async def test_un_enlace_inventado_no_entra(self) -> None:
        escenario = await self._preparado()
        with pytest.raises(AccesoNoDisponible):
            await self._acceso(escenario).ejecutar(valor="no-es-el-enlace", ahora=AHORA)

    @pytest.mark.asyncio
    async def test_descargar_el_paquete(self) -> None:
        escenario = await self._preparado()
        paquete = (await ListarPaquetes(escenario.paquetes).ejecutar())[0]
        contenido, tipo, nombre = await DescargarPaquete(
            paquetes=escenario.paquetes, archivos=escenario.archivos
        ).ejecutar(paquete.id)
        assert contenido[:2] == b"PK"
        assert tipo == "application/zip"
        assert nombre == "paquete-2026-03.zip"

    @pytest.mark.asyncio
    async def test_un_paquete_inexistente(self) -> None:
        escenario = Escenario()
        with pytest.raises(PaqueteInexistente):
            await DescargarPaquete(
                paquetes=escenario.paquetes, archivos=escenario.archivos
            ).ejecutar(uuid4())

    @pytest.mark.asyncio
    async def test_un_paquete_sin_archivo_no_se_descarga(self) -> None:
        escenario = Escenario()
        paquete = PaqueteContable(id=uuid4(), empresa_id=EMPRESA, periodo_anio=2026, periodo_mes=2)
        await escenario.paquetes.agregar(paquete)
        with pytest.raises(PaqueteInexistente):
            await DescargarPaquete(
                paquetes=escenario.paquetes, archivos=escenario.archivos
            ).ejecutar(paquete.id)


class TestVistaConContador:
    @pytest.mark.asyncio
    async def test_muestra_al_contador_invitado(self) -> None:
        escenario = Escenario()
        escenario.paquetes.config = ConfiguracionDelPaquete(
            empresa_id=EMPRESA, email_contador="contador@estudio.com.ar"
        )
        await escenario.generar()
        await escenario.invitar()
        vista = await VerConfiguracionDelPaquete(
            paquetes=escenario.paquetes, tokens=escenario.tokens
        ).ejecutar(empresa_id=EMPRESA, ahora=AHORA)
        assert vista.contador.invitado
        assert vista.contador.email == "contador@estudio.com.ar"
