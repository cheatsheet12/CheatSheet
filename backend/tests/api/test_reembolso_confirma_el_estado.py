"""`POST /cobros/{id}/reembolso` tiene que **confirmar** lo que escribe antes de fallar (H1).

`unidad_de_trabajo` confirma solo si el cuerpo del `async for` termina **sin levantar**. Un
reembolso que MercadoPago rechaza escribe el rechazo y su evento `ERROR` y después tiene que
contestar 422: si la ruta levanta adentro del ciclo, el rechazo se descarta y el administrador
no se entera. Peor: si MercadoPago no contesta, la marca de «en proceso» se perdería aunque la
plata pudiera haber salido, y un reintento mandaría **otra** clave de idempotencia.

Estos tests corren sin base de datos. Reemplazan la unidad de trabajo por un doble que
reproduce su único contrato relevante (confirma si y solo si el cuerpo termina limpio) sobre un
almacén con **dos versiones**: lo confirmado y lo que la unidad en curso escribió. Los casos de
uso son los reales; lo que se doblan son los puertos. La prueba contra PostgreSQL vive en
`tests/integracion/test_api_reembolsos.py`.

Los dobles se validan solos (`test_el_doble_no_confirma_si_el_cuerpo_levanta`): así el rojo de
los demás viene de la ruta y no de un doble roto.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.routers import reembolsos
from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago, MedioDePago
from cheatsheet.contexts.payments.domain.reembolso import Reembolso
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario
from fastapi import FastAPI, Request

from tests.conftest import INSTANTE_FIJO, settings_de_prueba

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())


@dataclass
class Almacen:
    """Lo **confirmado** y lo que la unidad en curso escribió. Una unidad que no confirma pierde
    lo segundo: es exactamente lo que pasa con una transacción que se descarta."""

    confirmado_cobros: dict[UUID, Cobro] = field(default_factory=dict)
    confirmado_filas: list[Reembolso] = field(default_factory=list)
    confirmado_eventos: list[EventoDeDominio] = field(default_factory=list)
    cobros: dict[UUID, Cobro] = field(default_factory=dict)
    filas: list[Reembolso] = field(default_factory=list)
    eventos: list[EventoDeDominio] = field(default_factory=list)
    unidades_abiertas: int = 0
    unidades_confirmadas: int = 0

    def abrir(self) -> None:
        self.unidades_abiertas += 1
        self.cobros = copy.deepcopy(self.confirmado_cobros)
        self.filas = list(self.confirmado_filas)
        self.eventos = list(self.confirmado_eventos)

    def confirmar(self) -> None:
        self.unidades_confirmadas += 1
        self.confirmado_cobros = self.cobros
        self.confirmado_filas = self.filas
        self.confirmado_eventos = self.eventos

    def acciones(self, accion: str) -> list[EventoAuditable]:
        return [
            e
            for e in self.confirmado_eventos
            if isinstance(e, EventoAuditable) and e.accion == accion
        ]


class CobrosDeLaUnidad:
    def __init__(self, almacen: Almacen) -> None:
        self._almacen = almacen

    async def buscar_para_actualizar(self, cobro_id: UUID) -> Cobro | None:
        return self._almacen.cobros.get(cobro_id)

    async def guardar(self, cobro: Cobro) -> None:
        self._almacen.cobros[cobro.id] = cobro


class ReembolsosDeLaUnidad:
    def __init__(self, almacen: Almacen) -> None:
        self._almacen = almacen

    async def agregar(self, reembolso: Reembolso) -> None:
        self._almacen.filas.append(reembolso)

    async def de_cobro(self, cobro_id: UUID) -> list[Reembolso]:
        return [f for f in self._almacen.filas if f.cobro_id == cobro_id]

    async def buscar_por_id(self, reembolso_id: UUID) -> Reembolso | None:
        return next((f for f in self._almacen.filas if f.id == reembolso_id), None)


class PublicadorDeLaUnidad:
    def __init__(self, almacen: Almacen) -> None:
        self._almacen = almacen

    async def publicar(self, evento: EventoDeDominio) -> None:
        self._almacen.eventos.append(evento)


@dataclass(frozen=True)
class _Unidad:
    almacen: Almacen
    reloj: RelojFijo
    publicador: PublicadorDeLaUnidad


async def _unidad_doble(almacen: Almacen) -> AsyncIterator[_Unidad]:
    """Imita `sesion_de_empresa`: el commit está **después** del `yield`.

    Si el cuerpo del consumidor levanta, el generador nunca se reanuda y la línea del commit no se
    alcanza: es exactamente el comportamiento que hace perder lo escrito.
    """
    almacen.abrir()
    yield _Unidad(almacen, RelojFijo(INSTANTE_FIJO), PublicadorDeLaUnidad(almacen))
    almacen.confirmar()


class PasarelaDeLaPrueba:
    """Responde lo que se le dijo, anota la clave y ve **lo confirmado** al ser llamada."""

    def __init__(self, almacen: Almacen) -> None:
        self._almacen = almacen
        self.respuesta: RespuestaDeReembolso | PasarelaNoDisponible = RespuestaDeReembolso(
            estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-1"
        )
        self.pedidos: list[tuple[str, Decimal, UUID]] = []
        #: Lo que estaba **confirmado** del cobro cuando MercadoPago fue llamado.
        self.confirmado_al_llamar: list[tuple[bool, UUID | None]] = []

    async def reembolsar(
        self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal, clave: UUID
    ) -> RespuestaDeReembolso:
        del empresa_id
        self.pedidos.append((payment_id, monto, clave))
        cobro = next(iter(self._almacen.confirmado_cobros.values()))
        self.confirmado_al_llamar.append(
            (cobro.reembolso_en_proceso, cobro.reembolso_clave_idempotencia)
        )
        if isinstance(self.respuesta, PasarelaNoDisponible):
            raise self.respuesta
        return self.respuesta

    async def consultar_reembolso(
        self, *, empresa_id: EmpresaId, payment_id: str, refund_id: str
    ) -> RespuestaDeReembolso:
        raise NotImplementedError  # pragma: no cover - estas pruebas no consultan


class SaldosDeLaPrueba:
    async def registrar_reembolso(self, comprobante_id: UUID, monto: Decimal) -> None:
        del comprobante_id, monto  # el cobro de la prueba no tiene comprobante: no se llama


def _cobro_pagado() -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1000.00"),
        descripcion="Consulta",
        vence_el=INSTANTE_FIJO + timedelta(days=30),
        created_at=INSTANTE_FIJO - timedelta(days=5),
    )
    cobro.asignar_link(
        LinkDePago(preference_id="pref-1", url="https://mp.com/pref-1"),
        INSTANTE_FIJO - timedelta(days=5),
    )
    cobro.aprobar(payment_id="pago-1", ahora=INSTANTE_FIJO - timedelta(days=1))
    return cobro


@dataclass
class Montaje:
    app: FastAPI
    almacen: Almacen
    pasarela: PasarelaDeLaPrueba
    cobro: Cobro


def _montar(monkeypatch: pytest.MonkeyPatch, rol: RolUsuario = RolUsuario.ADMINISTRADOR) -> Montaje:
    almacen = Almacen()
    cobro = _cobro_pagado()
    almacen.confirmado_cobros[cobro.id] = cobro
    pasarela = PasarelaDeLaPrueba(almacen)

    class PiezasFalsas:
        def __init__(self, unidad: _Unidad) -> None:
            self.cobros = CobrosDeLaUnidad(unidad.almacen)
            self.reembolsos = ReembolsosDeLaUnidad(unidad.almacen)

        @classmethod
        def armar(cls, unidad: _Unidad) -> PiezasFalsas:
            return cls(unidad)

    def unidad_de_trabajo(*_: Any) -> AsyncIterator[_Unidad]:
        return _unidad_doble(almacen)

    monkeypatch.setattr(reembolsos, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(reembolsos, "Cobros", PiezasFalsas)
    monkeypatch.setattr(reembolsos, "armar_pasarela", lambda *_: pasarela)
    monkeypatch.setattr(reembolsos, "armar_saldos", lambda *_: SaldosDeLaPrueba())

    settings = settings_de_prueba()
    recursos = Recursos(
        settings=settings,
        engine=None,  # type: ignore[arg-type]  # nunca se toca: todo lo que lo usaría está doblado
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    app = FastAPI()
    registrar_manejadores(app)

    @app.middleware("http")
    async def _actor(
        request: Request, siguiente: Callable[[Request], Awaitable[Any]]
    ) -> Any:  # el que autentica de verdad es `EmpresaMiddleware`; acá solo se declara quién es
        request.state.empresa_id = EMPRESA
        request.state.usuario_id = USUARIO
        request.state.rol = rol.value
        return await siguiente(request)

    app.include_router(reembolsos.crear_router(recursos))
    return Montaje(app, almacen, pasarela, cobro)


def _cliente(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _post(
    montaje: Montaje, ruta: str, cuerpo: dict[str, str] | None = None
) -> httpx.Response:
    async with _cliente(montaje.app) as cliente:
        return await cliente.post(f"/cobros/{montaje.cobro.id}{ruta}", json=cuerpo or {})


def _confirmado(montaje: Montaje) -> Cobro:
    return montaje.almacen.confirmado_cobros[montaje.cobro.id]


# ------------------------------------------------------------------ el doble se valida solo


async def _cuerpo_que_levanta(almacen: Almacen) -> None:
    async for unidad in _unidad_doble(almacen):
        unidad.almacen.cobros.clear()
        raise ValueError("x")


async def test_el_doble_no_confirma_si_el_cuerpo_levanta() -> None:
    """Guarda del doble: un cuerpo que levanta no confirma, o el rojo de abajo no prueba nada."""
    almacen = Almacen()

    with pytest.raises(ValueError, match="x"):
        await _cuerpo_que_levanta(almacen)

    assert almacen.unidades_abiertas == 1
    assert almacen.unidades_confirmadas == 0
    assert almacen.confirmado_eventos == []


# ------------------------------------------------------------------ H1: el rechazo queda escrito


async def test_un_rechazo_confirma_el_estado_y_el_evento_y_responde_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 11 (H1): el motivo de MercadoPago llega a la pantalla **y** queda escrito."""
    montaje = _montar(monkeypatch)
    montaje.pasarela.respuesta = RespuestaDeReembolso(
        estado=EstadoDeReembolso.RECHAZADO, motivo="Refund not supported (4295)"
    )

    respuesta = await _post(montaje, "/reembolso", {"monto": "400.00"})

    assert respuesta.status_code == 422
    assert respuesta.json()["error"] == "ReembolsoRechazado"
    assert "Refund not supported (4295)" in respuesta.json()["detalle"]
    cobro = _confirmado(montaje)
    assert not cobro.reembolso_en_proceso
    assert cobro.estado is EstadoCobro.APROBADO
    [evento] = montaje.almacen.acciones("rechazar_reembolso")
    assert evento.resultado is Resultado.ERROR
    assert montaje.almacen.unidades_confirmadas == 2


# ------------------------------------------------------------------ H1: la marca se confirma antes


async def test_la_solicitud_y_su_clave_estan_confirmadas_cuando_se_llama_a_mercadopago(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La razón de las dos transacciones: lo que MercadoPago recibe ya está escrito."""
    montaje = _montar(monkeypatch)

    respuesta = await _post(montaje, "/reembolso", {"monto": "400.00"})

    assert respuesta.status_code == 200
    [(en_proceso, clave_confirmada)] = montaje.pasarela.confirmado_al_llamar
    assert en_proceso is True
    assert clave_confirmada is not None
    assert montaje.pasarela.pedidos[0][2] == clave_confirmada
    assert respuesta.json()["estado"] == "REEMBOLSADO_PARCIAL"
    assert respuesta.json()["monto_reembolsado"] == "400.00"


async def test_sin_respuesta_de_mercadopago_la_marca_y_la_clave_sobreviven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 12 (H1): la plata puede haber salido. 200 «en proceso», la clave escrita y un evento
    `ERROR` que avisa."""
    montaje = _montar(monkeypatch)
    montaje.pasarela.respuesta = PasarelaNoDisponible("MercadoPago no respondio")

    respuesta = await _post(montaje, "/reembolso", {"monto": "400.00"})

    assert respuesta.status_code == 200
    assert respuesta.json()["reembolso_en_proceso"] is True
    assert respuesta.json()["reembolso_en_proceso_monto"] == "400.00"
    cobro = _confirmado(montaje)
    assert cobro.reembolso_en_proceso
    assert cobro.reembolso_clave_idempotencia == montaje.pasarela.pedidos[0][2]
    [evento] = montaje.almacen.acciones("reembolso_sin_confirmar")
    assert evento.resultado is Resultado.ERROR


async def test_actualizar_estado_reenvia_con_la_misma_clave_que_quedo_escrita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El reintento manda la clave guardada, nunca una nueva (el bug del doble reembolso)."""
    montaje = _montar(monkeypatch)
    montaje.pasarela.respuesta = PasarelaNoDisponible("MercadoPago no respondio")
    await _post(montaje, "/reembolso", {"monto": "400.00"})
    montaje.pasarela.respuesta = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-1"
    )

    respuesta = await _post(montaje, "/reembolso/actualizacion")

    assert respuesta.status_code == 200
    claves = [c for _, _, c in montaje.pasarela.pedidos]
    assert len(claves) == 2
    assert claves[0] == claves[1]
    assert respuesta.json()["estado"] == "REEMBOLSADO_PARCIAL"
    assert len(montaje.almacen.confirmado_filas) == 1


# ------------------------------------------------------------------ lo que sigue descartando


async def test_un_rechazo_de_la_solicitud_no_escribe_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un monto de más se rechaza en T1 **sin escribir**: ahí sí corresponde descartar."""
    montaje = _montar(monkeypatch)

    respuesta = await _post(montaje, "/reembolso", {"monto": "1000.01"})

    assert respuesta.status_code == 422
    assert montaje.almacen.unidades_confirmadas == 0
    assert montaje.pasarela.pedidos == []
    assert not _confirmado(montaje).reembolso_en_proceso


async def test_con_un_reembolso_en_vuelo_otra_solicitud_es_un_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)
    montaje.pasarela.respuesta = PasarelaNoDisponible("MercadoPago no respondio")
    await _post(montaje, "/reembolso", {"monto": "100.00"})

    respuesta = await _post(montaje, "/reembolso", {"monto": "100.00"})

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "ReembolsoEnProceso"
    assert len(montaje.pasarela.pedidos) == 1


async def test_un_operador_no_reembolsa(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch, RolUsuario.OPERADOR)

    respuesta = await _post(montaje, "/reembolso", {"monto": "100.00"})

    assert respuesta.status_code == 403
    assert montaje.almacen.unidades_confirmadas == 0
    assert montaje.pasarela.pedidos == []


async def test_actualizar_sin_nada_en_vuelo_no_llama_a_nadie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _post(montaje, "/reembolso/actualizacion")

    assert respuesta.status_code == 200
    assert respuesta.json()["reembolso_en_proceso"] is False
    assert montaje.pasarela.pedidos == []


# ------------------------------------------------------------------ manual y corrección


def _por_transferencia(montaje: Montaje) -> None:
    montaje.cobro.medio_de_pago = MedioDePago.TRANSFERENCIA
    montaje.almacen.confirmado_cobros[montaje.cobro.id].medio_de_pago = MedioDePago.TRANSFERENCIA


async def test_el_registro_manual_y_su_correccion_confirman_lo_que_escriben(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Las dos rutas restantes: una sola unidad cada una, y confirmada."""
    montaje = _montar(monkeypatch)
    _por_transferencia(montaje)
    hoy = INSTANTE_FIJO.date().isoformat()

    registrado = await _post(
        montaje,
        "/reembolsos",
        {"monto": "300.00", "fecha": hoy, "referencia": "OP-1", "motivo": "Devolucion"},
    )

    assert registrado.status_code == 200, registrado.text
    assert registrado.json()["estado"] == "REEMBOLSADO_PARCIAL"
    [fila] = montaje.almacen.confirmado_filas
    assert _confirmado(montaje).monto_reembolsado == Decimal("300.00")

    corregido = await _post(
        montaje, f"/reembolsos/{fila.id}/correccion", {"motivo": "Se cargo por error"}
    )

    assert corregido.status_code == 200, corregido.text
    assert corregido.json()["estado"] == "APROBADO"
    assert len(montaje.almacen.confirmado_filas) == 2
    assert montaje.almacen.unidades_confirmadas == 2
    assert len(montaje.almacen.acciones("corregir_reembolso")) == 1
    otra_vez = await _post(
        montaje, f"/reembolsos/{fila.id}/correccion", {"motivo": "Otra vez por error"}
    )
    assert otra_vez.status_code == 409
    assert otra_vez.json()["error"] == "ReembolsoNoCorregible"


async def test_el_registro_manual_sobre_un_link_es_un_409(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _post(
        montaje,
        "/reembolsos",
        {
            "monto": "300.00",
            "fecha": INSTANTE_FIJO.date().isoformat(),
            "motivo": "Devolucion",
        },
    )

    assert respuesta.status_code == 409
    assert montaje.almacen.unidades_confirmadas == 0
