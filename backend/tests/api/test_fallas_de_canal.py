"""La raíz traduce los errores tipados del canal a la excepción de `payments` (U7, D2).

`conversational` levanta `MensajeRechazado`, `MensajeriaSaturada`, `EnvioIncierto` y
`CanalNoConectado`; el adaptador de recordatorios no puede importarlos (R3) y necesita el motivo
para PAN-COB-02. El envoltorio vive en `api/` y lo traduce a `FallaDelCanal(codigo)`.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from cheatsheet.api.fallas_de_canal import CanalConFallasTraducidas
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.payments.application.ports_envio import FallaDelCanal

pytestmark = pytest.mark.asyncio


class _Canal:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        if self._error is not None:
            raise self._error
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        if self._error is not None:
            raise self._error
        return "wamid.PLANTILLA"


async def test_lo_que_sale_bien_pasa_sin_cambios() -> None:
    canal = CanalConFallasTraducidas(_Canal(), FallaDelCanal)

    assert await canal.enviar(telefono="1", texto="hola") == "wamid.TEXTO"
    assert (
        await canal.enviar_plantilla(telefono="1", nombre="n", idioma="es_AR", parametros={})
        == "wamid.PLANTILLA"
    )


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (MensajeRechazado("no", codigo=131047), "131047"),
        (MensajeriaSaturada("no"), "SATURADA"),
        (EnvioIncierto("no"), "INCIERTO"),
        (CanalNoConectado("no"), "SIN_CANAL"),
    ],
)
async def test_los_errores_tipados_del_canal_pasan_a_la_falla_local_con_su_codigo(
    error: Exception, codigo: str
) -> None:
    canal = CanalConFallasTraducidas(_Canal(error=error), FallaDelCanal)

    with pytest.raises(FallaDelCanal) as texto:
        await canal.enviar(telefono="1", texto="hola")
    with pytest.raises(FallaDelCanal) as plantilla:
        await canal.enviar_plantilla(telefono="1", nombre="n", idioma="es_AR", parametros={})

    assert texto.value.codigo == codigo
    assert plantilla.value.codigo == codigo
    assert texto.value.__cause__ is error


async def test_una_excepcion_que_no_es_del_canal_se_propaga_tal_cual() -> None:
    canal = CanalConFallasTraducidas(_Canal(error=RuntimeError("otra cosa")), FallaDelCanal)

    with pytest.raises(RuntimeError):
        await canal.enviar(telefono="1", texto="hola")


async def test_el_adaptador_de_recordatorios_deja_el_codigo_de_meta_a_traves_del_envoltorio() -> (
    None
):
    """De punta a punta: el código 131047 de Meta llega a `ResultadoDeEnvio.codigo`."""
    from datetime import UTC, datetime
    from decimal import Decimal
    from uuid import UUID, uuid4

    from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro
    from cheatsheet.contexts.payments.domain.cobro import Cobro
    from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
    from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorWhatsApp
    from cheatsheet.shared.empresa import EmpresaId

    class Contactos:
        async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro:
            del cliente_id
            return ContactoDeCobro(nombre="Rosa", telefono="5491155550000")

    class SinPlantillas:
        async def para(self, codigo: str, variables: object) -> None:
            del codigo, variables

    ahora = datetime(2026, 10, 7, tzinfo=UTC)
    empresa = EmpresaId(uuid4())
    cobro = Cobro(
        id=uuid4(),
        empresa_id=empresa,
        cliente_id=uuid4(),
        monto=Decimal("10.00"),
        descripcion="Consulta",
        vence_el=ahora,
        created_at=ahora,
    )
    envio = EnvioPorWhatsApp(
        CanalConFallasTraducidas(
            _Canal(error=MensajeRechazado("no", codigo=131047)), FallaDelCanal
        ),
        Contactos(),
        SinPlantillas(),
    )

    resultado = await envio.enviar(empresa_id=empresa, cobro=cobro, canal="WHATSAPP", paso=1)

    assert resultado.estado is EstadoEntrega.FALLIDO
    assert resultado.codigo == "131047"
