"""El centro de notificaciones (HU-E11-03) y quién lo llena.

Lo que este archivo fija:

- **Se notifica lo que salió mal, y nada más.** Un aviso por cada operación exitosa es un
  centro que nadie mira, y un centro que nadie mira hace que la vez que sí importaba pase
  desapercibida.
- **Quién recibe qué sale de las preferencias** (RN-02), no del rol.
- **Un fallo notificando no rompe la operación que lo produjo.** El suscriptor se traga su
  propio error a propósito: un cobro confirmado no se deshace porque no se pudo escribir un
  aviso en el panel.
- **Una notificación ajena no se marca leída.** RLS acota a la empresa, no a la persona.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.errors import NotificacionInexistente
from cheatsheet.contexts.observability.application.notificaciones import (
    ContarNoLeidas,
    ListarNotificaciones,
    MarcarComoLeida,
    NotificarPorEventos,
)
from cheatsheet.contexts.observability.domain.notificacion import Notificacion, Severidad
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
ANA = UsuarioId(uuid4())
BRUNO = UsuarioId(uuid4())


class RepositorioEnMemoria:
    def __init__(self, *notificaciones: Notificacion) -> None:
        self.notificaciones: list[Notificacion] = list(notificaciones)
        self.falla = False

    async def agregar(self, notificacion: Notificacion) -> None:
        if self.falla:
            raise RuntimeError("la base no responde")
        self.notificaciones.append(notificacion)

    async def guardar(self, notificacion: Notificacion) -> None:
        self.notificaciones = [
            notificacion if una.id == notificacion.id else una for una in self.notificaciones
        ]

    async def buscar_por_id(self, notificacion_id: UUID) -> Notificacion | None:
        return next((una for una in self.notificaciones if una.id == notificacion_id), None)

    async def listar_de(
        self, destinatario_id: UsuarioId, *, solo_no_leidas: bool = False, limite: int = 50
    ) -> list[Notificacion]:
        encontradas = [una for una in self.notificaciones if una.destinatario_id == destinatario_id]
        if solo_no_leidas:
            encontradas = [una for una in encontradas if not una.leida]
        return encontradas[:limite]

    async def contar_no_leidas(self, destinatario_id: UsuarioId) -> int:
        return len(await self.listar_de(destinatario_id, solo_no_leidas=True))


class DestinatariosFalsos:
    def __init__(self, **por_categoria: list[UsuarioId]) -> None:
        self.por_categoria = por_categoria

    async def suscriptos_a(self, categoria: str) -> list[UsuarioId]:
        return self.por_categoria.get(categoria, [])


def _notificacion(destinatario: UsuarioId = ANA, *, leida: bool = False) -> Notificacion:
    return Notificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        destinatario_id=destinatario,
        categoria="COBROS",
        severidad=Severidad.ALTA,
        cuerpo="«confirmar_pago» falló sobre Cobro:1.",
        leida=leida,
        created_at=AHORA,
    )


def _evento(
    *, resultado: Resultado = Resultado.ERROR, modulo: Modulo = Modulo.PAYMENTS
) -> EventoAuditable:
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=EMPRESA,
        ocurrido_en=AHORA,
        modulo=modulo,
        accion="confirmar_pago",
        entidad_afectada="Cobro:1",
        resultado=resultado,
    )


class TestDominio:
    def test_una_alta_sin_leer_se_destaca(self) -> None:
        assert _notificacion().se_destaca

    def test_una_alta_ya_leida_deja_de_destacarse(self) -> None:
        """Seguir destacándola es cómo una pantalla enseña a ignorar lo que destaca."""
        assert not _notificacion(leida=True).se_destaca

    def test_marcar_leida_es_idempotente(self) -> None:
        notificacion = _notificacion()
        notificacion.marcar_leida()
        notificacion.marcar_leida()
        assert notificacion.leida

    def test_una_notificacion_sin_cuerpo_no_existe(self) -> None:
        with pytest.raises(EntradaInvalida):
            Notificacion(
                id=uuid4(),
                empresa_id=EMPRESA,
                destinatario_id=ANA,
                categoria="COBROS",
                severidad=Severidad.BAJA,
                cuerpo="   ",
            )


class TestBandeja:
    @pytest.mark.asyncio
    async def test_lista_solo_lo_propio(self) -> None:
        repositorio = RepositorioEnMemoria(_notificacion(ANA), _notificacion(BRUNO))

        de_ana = await ListarNotificaciones(repositorio).ejecutar(destinatario_id=ANA)

        assert [una.destinatario_id for una in de_ana] == [ANA]

    @pytest.mark.asyncio
    async def test_cuenta_las_no_leidas(self) -> None:
        repositorio = RepositorioEnMemoria(
            _notificacion(ANA), _notificacion(ANA, leida=True), _notificacion(BRUNO)
        )

        assert await ContarNoLeidas(repositorio).ejecutar(ANA) == 1

    @pytest.mark.asyncio
    async def test_marcar_leida(self) -> None:
        una = _notificacion(ANA)
        repositorio = RepositorioEnMemoria(una)

        marcada = await MarcarComoLeida(repositorio).ejecutar(
            notificacion_id=una.id, destinatario_id=ANA
        )

        assert marcada.leida
        assert await ContarNoLeidas(repositorio).ejecutar(ANA) == 0

    @pytest.mark.asyncio
    async def test_la_notificacion_de_otro_no_se_toca(self) -> None:
        """Y da la misma respuesta que una inexistente: el id de una ajena no se confirma."""
        de_bruno = _notificacion(BRUNO)
        repositorio = RepositorioEnMemoria(de_bruno)

        with pytest.raises(NotificacionInexistente):
            await MarcarComoLeida(repositorio).ejecutar(
                notificacion_id=de_bruno.id, destinatario_id=ANA
            )
        assert not de_bruno.leida

    @pytest.mark.asyncio
    async def test_una_inexistente_da_lo_mismo(self) -> None:
        with pytest.raises(NotificacionInexistente):
            await MarcarComoLeida(RepositorioEnMemoria()).ejecutar(
                notificacion_id=uuid4(), destinatario_id=ANA
            )


class TestSuscriptor:
    @pytest.mark.asyncio
    async def test_un_error_notifica_a_los_suscriptos(self) -> None:
        repositorio = RepositorioEnMemoria()
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio,
            destinatarios=DestinatariosFalsos(COBROS=[ANA, BRUNO]),
        )

        await suscriptor.manejar(_evento())

        assert len(repositorio.notificaciones) == 2
        assert {una.destinatario_id for una in repositorio.notificaciones} == {ANA, BRUNO}
        assert repositorio.notificaciones[0].severidad is Severidad.ALTA

    @pytest.mark.asyncio
    async def test_una_operacion_exitosa_no_notifica_nada(self) -> None:
        repositorio = RepositorioEnMemoria()
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio, destinatarios=DestinatariosFalsos(COBROS=[ANA])
        )

        await suscriptor.manejar(_evento(resultado=Resultado.COMPLETADO))

        assert repositorio.notificaciones == []

    @pytest.mark.asyncio
    async def test_nadie_suscripto_no_es_un_error(self) -> None:
        repositorio = RepositorioEnMemoria()
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio, destinatarios=DestinatariosFalsos()
        )

        await suscriptor.manejar(_evento())

        assert repositorio.notificaciones == []

    @pytest.mark.asyncio
    async def test_el_modulo_decide_la_categoria(self) -> None:
        repositorio = RepositorioEnMemoria()
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio,
            destinatarios=DestinatariosFalsos(SINCRONIZACION=[ANA]),
        )

        await suscriptor.manejar(_evento(modulo=Modulo.SPREADSHEET_SYNC))

        assert [una.categoria for una in repositorio.notificaciones] == ["SINCRONIZACION"]

    @pytest.mark.asyncio
    async def test_un_fallo_notificando_no_rompe_la_operacion(self) -> None:
        """La decisión del módulo, comprobada: el suscriptor **no** propaga.

        Si propagara, un cobro confirmado se deshacería porque no se pudo escribir un aviso en
        el panel — y el aviso existe justamente para contar lo que pasó.
        """
        repositorio = RepositorioEnMemoria()
        repositorio.falla = True
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio, destinatarios=DestinatariosFalsos(COBROS=[ANA])
        )

        await suscriptor.manejar(_evento())

        assert repositorio.notificaciones == []

    @pytest.mark.asyncio
    async def test_un_evento_que_no_es_auditable_pasa_de_largo(self) -> None:
        from cheatsheet.shared.events import EventoDeDominio

        repositorio = RepositorioEnMemoria()
        suscriptor = NotificarPorEventos(
            notificaciones=repositorio, destinatarios=DestinatariosFalsos(COBROS=[ANA])
        )

        await suscriptor.manejar(
            EventoDeDominio(evento_id=uuid4(), empresa_id=EMPRESA, ocurrido_en=AHORA)
        )

        assert repositorio.notificaciones == []
