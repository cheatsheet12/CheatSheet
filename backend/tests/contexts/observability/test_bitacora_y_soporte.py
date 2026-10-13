"""La bitácora consultable (HU-E12-01, HU-E12-02) y las solicitudes de soporte (HU-E9-03).

Lo que este archivo fija:

- **Solo Lectura no accede a la bitácora**, ni al listado ni al detalle. El guarda vive en el
  caso de uso y no en el router, que es lo que PRU-09 enseñó.
- **El timeline es la bitácora filtrada por entidad**, y la duración es la distancia entre el
  primer paso y el último. Una operación que dejó una sola fila **no tiene duración**: «0 ms»
  sería afirmar algo que nadie midió.
- **El asunto y la descripción son obligatorios**, con la frase textual del criterio, y la
  invariante vive en el agregado — así no hay forma de construir una solicitud vacía.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.consultas import (
    ContarOperaciones,
    ListarOperaciones,
    VerOperacion,
)
from cheatsheet.contexts.observability.application.errors import (
    AccesoALaBitacoraDenegado,
    OperacionInexistente,
)
from cheatsheet.contexts.observability.application.ports import FiltrosDeBitacora
from cheatsheet.contexts.observability.application.soporte import (
    AbrirSolicitudDeSoporte,
    ListarSolicitudes,
)
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import (
    MENSAJE_CAMPOS_OBLIGATORIOS,
    EstadoDeSolicitud,
    PrioridadDeSoporte,
    SolicitudDeSoporte,
)
from cheatsheet.shared.auditoria import Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


class RegistrosEnMemoria:
    def __init__(self, *registros: RegistroDeAuditoria) -> None:
        self.registros = list(registros)

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        self.registros.append(registro)

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        return next((uno for uno in self.registros if uno.evento_id == evento_id), None)

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None:
        return next((uno for uno in self.registros if uno.id == registro_id), None)

    async def listar(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        encontrados = self._acotados(filtros)
        desde = filtros.desplazamiento
        return encontrados[desde : desde + filtros.limite]

    async def listar_de_entidad(self, entidad: str) -> list[RegistroDeAuditoria]:
        de_la_entidad = [uno for uno in self.registros if uno.entidad_afectada == entidad]
        return sorted(de_la_entidad, key=lambda uno: uno.timestamp)

    async def contar(self, filtros: FiltrosDeBitacora) -> int:
        return len(self._acotados(filtros))

    def _acotados(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        return [
            uno
            for uno in self.registros
            if (not filtros.modulos or uno.modulo in filtros.modulos)
            and (not filtros.resultados or uno.resultado in filtros.resultados)
            and (not filtros.iniciadores or uno.iniciador in filtros.iniciadores)
            and _coincide_con_la_busqueda(uno, filtros)
        ]


def _coincide_con_la_busqueda(uno: RegistroDeAuditoria, filtros: FiltrosDeBitacora) -> bool:
    if filtros.texto is None and not filtros.clientes:
        return True
    texto = (filtros.texto or "").lower()
    por_texto = bool(texto) and (
        texto in uno.accion.lower() or texto in uno.entidad_afectada.lower()
    )
    ids = {str(cliente) for cliente in filtros.clientes}
    por_cliente = uno.entidad_afectada in {f"cliente:{cliente}" for cliente in ids} or (
        (uno.detalle or {}).get("cliente_id") in ids
    )
    return por_texto or por_cliente


class SolicitudesEnMemoria:
    def __init__(self, *solicitudes: SolicitudDeSoporte) -> None:
        self.solicitudes = list(solicitudes)

    async def agregar(self, solicitud: SolicitudDeSoporte) -> None:
        self.solicitudes.append(solicitud)

    async def guardar(self, solicitud: SolicitudDeSoporte) -> None:
        self.solicitudes = [
            solicitud if una.id == solicitud.id else una for una in self.solicitudes
        ]

    async def buscar_por_id(self, solicitud_id: UUID) -> SolicitudDeSoporte | None:
        return next((una for una in self.solicitudes if una.id == solicitud_id), None)

    async def listar(
        self, *, solo_abiertas: bool = False, limite: int = 50
    ) -> list[SolicitudDeSoporte]:
        encontradas = self.solicitudes
        if solo_abiertas:
            encontradas = [una for una in encontradas if una.esta_abierta]
        return encontradas[:limite]


def _registro(
    *,
    accion: str = "emitir_comprobante",
    entidad: str = "Comprobante:1",
    modulo: Modulo = Modulo.BILLING,
    resultado: Resultado = Resultado.COMPLETADO,
    iniciador: Iniciador = Iniciador.USUARIO,
    minutos: int = 0,
    detalle: dict[str, str] | None = None,
) -> RegistroDeAuditoria:
    return RegistroDeAuditoria(
        id=uuid4(),
        evento_id=uuid4(),
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        modulo=modulo,
        accion=accion,
        entidad_afectada=entidad,
        resultado=resultado,
        direccion_ip=None,
        iniciador=iniciador,
        detalle=detalle,
        timestamp=AHORA + timedelta(minutes=minutos),
    )


class TestPermisos:
    @pytest.mark.asyncio
    async def test_solo_lectura_no_ve_la_bitacora(self) -> None:
        with pytest.raises(AccesoALaBitacoraDenegado):
            await ListarOperaciones(RegistrosEnMemoria()).ejecutar(rol=RolUsuario.SOLO_LECTURA)

    @pytest.mark.asyncio
    async def test_solo_lectura_tampoco_ve_el_detalle(self) -> None:
        with pytest.raises(AccesoALaBitacoraDenegado):
            await VerOperacion(RegistrosEnMemoria()).ejecutar(uuid4(), rol=RolUsuario.SOLO_LECTURA)

    @pytest.mark.asyncio
    async def test_el_operador_si(self) -> None:
        registros = RegistrosEnMemoria(_registro())
        assert len(await ListarOperaciones(registros).ejecutar(rol=RolUsuario.OPERADOR)) == 1

    @pytest.mark.asyncio
    async def test_sin_rol_es_el_llamador_interno(self) -> None:
        """El reporte de operaciones del épico 9, que ya comprobó el permiso de quien pidió."""
        registros = RegistrosEnMemoria(_registro())
        assert len(await ListarOperaciones(registros).ejecutar()) == 1


class TestFiltros:
    @pytest.mark.asyncio
    async def test_por_modulo(self) -> None:
        registros = RegistrosEnMemoria(
            _registro(modulo=Modulo.BILLING), _registro(modulo=Modulo.PAYMENTS)
        )

        encontrados = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(modulos=(Modulo.PAYMENTS,)), rol=RolUsuario.ADMINISTRADOR
        )

        assert [uno.modulo for uno in encontrados] == [Modulo.PAYMENTS]

    @pytest.mark.asyncio
    async def test_por_iniciador_ia(self) -> None:
        """El criterio textual: «veo sólo las operaciones ejecutadas por el agente»."""
        registros = RegistrosEnMemoria(
            _registro(iniciador=Iniciador.IA), _registro(iniciador=Iniciador.USUARIO)
        )

        encontrados = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(iniciadores=(Iniciador.IA,)), rol=RolUsuario.ADMINISTRADOR
        )

        assert [uno.iniciador for uno in encontrados] == [Iniciador.IA]

    @pytest.mark.asyncio
    async def test_por_estado(self) -> None:
        registros = RegistrosEnMemoria(
            _registro(resultado=Resultado.ERROR), _registro(resultado=Resultado.COMPLETADO)
        )

        encontrados = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(resultados=(Resultado.ERROR,)), rol=RolUsuario.ADMINISTRADOR
        )

        assert [uno.resultado for uno in encontrados] == [Resultado.ERROR]

    @pytest.mark.asyncio
    async def test_la_busqueda_mira_accion_y_entidad(self) -> None:
        registros = RegistrosEnMemoria(
            _registro(accion="sincronizar_planilla", entidad="Planilla:abc"),
            _registro(accion="emitir_comprobante", entidad="Comprobante:1"),
        )

        por_accion = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(texto="sincronizar"), rol=RolUsuario.ADMINISTRADOR
        )
        por_entidad = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(texto="Planilla"), rol=RolUsuario.ADMINISTRADOR
        )

        assert len(por_accion) == 1
        assert por_accion[0].id == por_entidad[0].id

    @pytest.mark.asyncio
    async def test_buscar_un_cliente_trae_su_alta_y_sus_turnos(self) -> None:
        """#176 (HU-E12-01 RN-03): «busco por cliente — filtra las operaciones relacionadas».

        La pantalla resuelve el nombre contra `master_data` y manda los ids; la bitácora trae
        las operaciones sobre `Cliente:<id>` y las que guardan ese `cliente_id` en su detalle.
        """
        cliente, otro = uuid4(), uuid4()
        registros = RegistrosEnMemoria(
            _registro(accion="cliente_registrado", entidad=f"cliente:{cliente}"),
            _registro(
                accion="reservar_turno",
                entidad="Turno:t1",
                detalle={"cliente_id": str(cliente)},
            ),
            _registro(
                accion="reservar_turno",
                entidad="Turno:t2",
                detalle={"cliente_id": str(otro)},
            ),
            _registro(accion="emitir_comprobante", entidad="Comprobante:1"),
        )

        encontrados = await ListarOperaciones(registros).ejecutar(
            FiltrosDeBitacora(texto="Ana", clientes=(cliente,)), rol=RolUsuario.ADMINISTRADOR
        )

        assert {uno.entidad_afectada for uno in encontrados} == {
            f"cliente:{cliente}",
            "Turno:t1",
        }

    @pytest.mark.asyncio
    async def test_contar_no_pagina(self) -> None:
        """El total del paginador cuenta todo lo que coincide, no la página que se muestra."""
        registros = RegistrosEnMemoria(*[_registro() for _ in range(5)])

        assert await ContarOperaciones(registros).ejecutar(FiltrosDeBitacora(limite=2)) == 5
        assert len(await ListarOperaciones(registros).ejecutar(FiltrosDeBitacora(limite=2))) == 2


class TestDetalle:
    @pytest.mark.asyncio
    async def test_el_timeline_son_los_pasos_de_la_misma_entidad(self) -> None:
        validar = _registro(accion="validar", minutos=0)
        enviar = _registro(accion="enviar_a_arca", minutos=1)
        autorizar = _registro(accion="autorizar", minutos=3)
        otra = _registro(entidad="Comprobante:2", accion="validar", minutos=0)
        registros = RegistrosEnMemoria(autorizar, validar, enviar, otra)

        detalle = await VerOperacion(registros).ejecutar(autorizar.id, rol=RolUsuario.ADMINISTRADOR)

        assert [uno.accion for uno in detalle.timeline] == ["validar", "enviar_a_arca", "autorizar"]
        assert detalle.duracion == timedelta(minutes=3)

    @pytest.mark.asyncio
    async def test_una_operacion_de_un_solo_paso_no_tiene_duracion(self) -> None:
        """«0 ms» sería afirmar algo que nadie midió."""
        uno = _registro(entidad="Cliente:1")
        detalle = await VerOperacion(RegistrosEnMemoria(uno)).ejecutar(
            uno.id, rol=RolUsuario.ADMINISTRADOR
        )

        assert detalle.duracion is None
        assert not detalle.tiene_detalle

    @pytest.mark.asyncio
    async def test_senala_el_paso_que_fallo(self) -> None:
        ok = _registro(accion="validar", minutos=0)
        mal = _registro(accion="enviar_a_arca", resultado=Resultado.ERROR, minutos=1)
        registros = RegistrosEnMemoria(ok, mal)

        detalle = await VerOperacion(registros).ejecutar(mal.id, rol=RolUsuario.ADMINISTRADOR)

        assert detalle.paso_con_error is not None
        assert detalle.paso_con_error.accion == "enviar_a_arca"

    @pytest.mark.asyncio
    async def test_muestra_lo_que_la_operacion_registro(self) -> None:
        """HU-E12-02 RN-02: para una operación fiscal, el CAE y el estado."""
        con_cae = _registro(
            accion="autorizar", detalle={"cae": "70123456789012", "estado": "AUTORIZADO"}
        )
        detalle = await VerOperacion(RegistrosEnMemoria(con_cae)).ejecutar(
            con_cae.id, rol=RolUsuario.ADMINISTRADOR
        )

        assert detalle.tiene_detalle
        assert detalle.registro.detalle == {"cae": "70123456789012", "estado": "AUTORIZADO"}

    @pytest.mark.asyncio
    async def test_una_operacion_inexistente(self) -> None:
        with pytest.raises(OperacionInexistente):
            await VerOperacion(RegistrosEnMemoria()).ejecutar(uuid4(), rol=RolUsuario.ADMINISTRADOR)


class TestSoporte:
    async def _abrir(
        self,
        solicitudes: SolicitudesEnMemoria,
        *,
        rol: RolUsuario = RolUsuario.ADMINISTRADOR,
        asunto: str = "No puedo emitir",
        descripcion: str = "ARCA rechaza todo desde ayer",
    ) -> SolicitudDeSoporte:
        return await AbrirSolicitudDeSoporte(
            solicitudes=solicitudes, publicador=PublicadorFalso()
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            asunto=asunto,
            descripcion=descripcion,
            prioridad=PrioridadDeSoporte.ALTA,
            ahora=AHORA,
        )

    @pytest.mark.asyncio
    async def test_queda_abierta(self) -> None:
        solicitudes = SolicitudesEnMemoria()

        solicitud = await self._abrir(solicitudes)

        assert solicitud.estado is EstadoDeSolicitud.ABIERTA
        assert solicitud.esta_abierta
        assert len(await ListarSolicitudes(solicitudes).ejecutar(solo_abiertas=True)) == 1

    @pytest.mark.asyncio
    async def test_sin_asunto_da_la_frase_de_la_historia(self) -> None:
        with pytest.raises(EntradaInvalida) as error:
            await self._abrir(SolicitudesEnMemoria(), asunto="   ")
        assert str(error.value) == MENSAJE_CAMPOS_OBLIGATORIOS

    @pytest.mark.asyncio
    async def test_sin_descripcion_tambien(self) -> None:
        with pytest.raises(EntradaInvalida) as error:
            await self._abrir(SolicitudesEnMemoria(), descripcion="")
        assert str(error.value) == MENSAJE_CAMPOS_OBLIGATORIOS

    @pytest.mark.asyncio
    async def test_el_operador_no_abre_solicitudes(self) -> None:
        with pytest.raises(OperacionNoPermitida):
            await self._abrir(SolicitudesEnMemoria(), rol=RolUsuario.OPERADOR)

    @pytest.mark.asyncio
    async def test_deja_rastro_en_la_bitacora(self) -> None:
        publicador = PublicadorFalso()
        await AbrirSolicitudDeSoporte(
            solicitudes=SolicitudesEnMemoria(), publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            asunto="Consulta",
            descripcion="Una duda",
            prioridad=PrioridadDeSoporte.BAJA,
            ahora=AHORA,
        )

        assert [getattr(uno, "accion", "") for uno in publicador.eventos] == [
            "abrir_solicitud_de_soporte"
        ]

    def test_una_solicitud_cerrada_no_se_reabre(self) -> None:
        """Reabrirla perdería la fecha en que se resolvió, que es lo que mide a soporte."""
        solicitud = SolicitudDeSoporte(
            id=uuid4(),
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            asunto="Algo",
            descripcion="Algo más",
        )
        solicitud.cambiar_estado(EstadoDeSolicitud.CERRADA, AHORA)

        with pytest.raises(InvarianteViolada):
            solicitud.cambiar_estado(EstadoDeSolicitud.ABIERTA, AHORA)
