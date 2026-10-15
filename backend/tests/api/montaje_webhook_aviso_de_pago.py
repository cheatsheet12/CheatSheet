"""El montaje de los tests del aviso de cobro confirmado: el webhook de MercadoPago de punta a punta.

Todo lo que habla con una base es un doble en memoria; lo que habla con Meta es el cliente real de
`conversational` sobre un `httpx.MockTransport`. La unidad de trabajo imita lo que importa de la
real: **solo confirma si el cuerpo del `async for` termina**, y anota cada confirmación para poder
afirmar que el aviso sale después del commit del pago.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.routers import webhooks
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from fastapi import FastAPI

from tests.api.montaje_avisos_de_turno_reales import EnMemoria, Meta, canal_real
from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.conversational.application.dobles import sin_savepoint
from tests.contexts.payments.application.test_confirmacion import (
    CobrosFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491155550000"
NOMBRE = "Rosa Diaz"
RUTA = f"/webhooks/mercadopago/{EMPRESA}"
PAYMENT_ID = "pago-1"
AHORA = INSTANTE_FIJO
WAMID = "wamid.COBRO"
CONTACTO = ContactoDeCobro(nombre=NOMBRE, telefono=TELEFONO)


class MetaQueMiraElCommit(Meta):
    """Un Meta falso que anota cuántas unidades de trabajo ya habían confirmado al ser llamado."""

    def __init__(self, montaje: Montaje, *respuestas: httpx.Response) -> None:
        super().__init__(*respuestas)
        self._montaje = montaje

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self._montaje.confirmadas_al_llamar_a_meta.append(len(self._montaje.confirmadas))
        return super().__call__(pedido)


class ContactosFalsos:
    def __init__(self, contacto: ContactoDeCobro | None) -> None:
        self._contacto = contacto

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        return self._contacto


class SinPlantillas:
    async def para(self, codigo: str, variables: Mapping[str, str]) -> None:
        del codigo, variables


@dataclass
class Montaje:
    app: FastAPI
    cobros: CobrosFalsos
    pasarela: PasarelaFalsa
    hilos: EnMemoria
    #: Una entrada por unidad de trabajo que **terminó** (hizo commit), en orden.
    confirmadas: list[str] = field(default_factory=list)
    #: Con qué empresa se armó el canal de mensajería.
    canales_de: list[EmpresaId] = field(default_factory=list)
    confirmadas_al_llamar_a_meta: list[int] = field(default_factory=list)
    meta: Meta = field(default_factory=Meta)
    #: Si no es `None`, `armar_mensajeria` levanta esto en vez de armar el canal.
    falla_al_armar_el_canal: Exception | None = None


def un_cobro(*, turno_id: UUID | None = None, monto: str = "1210.00") -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA - timedelta(days=1),
        turno_id=turno_id,
    )
    cobro.asignar_link(LinkDePago(preference_id="pref-1", url="https://mp.example/c/1"), AHORA)
    return cobro


async def montar(
    monkeypatch: pytest.MonkeyPatch,
    *respuestas_de_meta: httpx.Response,
    contacto: ContactoDeCobro | None = CONTACTO,
    estado_del_pago: str = "approved",
    con_cobro: Cobro | None = None,
) -> Montaje:
    cobro = con_cobro if con_cobro is not None else un_cobro()
    cobros = CobrosFalsos()
    await cobros.agregar(cobro)
    montaje = Montaje(
        FastAPI(),
        cobros,
        PasarelaFalsa(estado=estado_del_pago, cobro_id=cobro.id),
        EnMemoria(),
    )
    montaje.meta = MetaQueMiraElCommit(
        montaje,
        *(respuestas_de_meta or (httpx.Response(200, json={"messages": [{"id": WAMID}]}),)),
    )
    publicador = PublicadorFalso()

    async def unidad_de_trabajo(
        _recursos: object, empresa_id: EmpresaId
    ) -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(
            sesion=SimpleNamespace(begin_nested=sin_savepoint),
            publicador=publicador,
            reloj=RelojFijo(INSTANTE_FIJO),
            empresa_id=empresa_id,
        )
        montaje.confirmadas.append("unidad")  # solo si el cuerpo del `async for` terminó

    async def armar_mensajeria(
        _unidad: object, _settings: object, *, empresa_id: EmpresaId
    ) -> object:
        montaje.canales_de.append(empresa_id)
        if montaje.falla_al_armar_el_canal is not None:
            raise montaje.falla_al_armar_el_canal
        return canal_real(montaje.meta)

    class _Cobros:
        cobros = montaje.cobros

        @classmethod
        def armar(cls, _unidad: object) -> type[_Cobros]:
            return cls

    class _Conversaciones:
        conversaciones = montaje.hilos.conversaciones
        mensajes = montaje.hilos.mensajes

        @classmethod
        def armar(cls, _unidad: object) -> type[_Conversaciones]:
            return cls

    monkeypatch.setattr(webhooks, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(webhooks, "Cobros", _Cobros)
    monkeypatch.setattr(webhooks, "armar_pasarela", lambda _unidad, _settings: montaje.pasarela)
    monkeypatch.setattr(webhooks, "armar_saldos", lambda _unidad: SaldosFalsos())
    for nombre, valor in {
        "unidad_de_trabajo": unidad_de_trabajo,
        "armar_mensajeria": armar_mensajeria,
        "Conversaciones": _Conversaciones,
        "armar_contactos": lambda _unidad: ContactosFalsos(contacto),
        "armar_plantillas_aprobadas": lambda _unidad: SinPlantillas(),
    }.items():
        monkeypatch.setattr(f"cheatsheet.api.avisos_de_cobro.{nombre}", valor)

    recursos = Recursos(
        settings=settings_de_prueba(),
        engine=None,  # type: ignore[arg-type]
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    registrar_manejadores(montaje.app)
    montaje.app.include_router(webhooks.crear_router(recursos))
    return montaje


async def notificar(montaje: Montaje, payment_id: str = PAYMENT_ID) -> httpx.Response:
    """Una notificación de pago de MercadoPago, firmada como la firma el cuerpo crudo."""
    secreto = settings_de_prueba().mercadopago_webhook_secret
    crudo = json.dumps({"type": "payment", "data": {"id": payment_id}}).encode()
    firma = hmac.new(secreto.encode(), crudo, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.post(
            RUTA, content=crudo, headers={"x-signature": f"ts=1760000000,v1={firma}"}
        )


__all__ = ["AHORA", "NOMBRE", "PAYMENT_ID", "TELEFONO", "WAMID", "Montaje", "montar", "notificar"]
