"""The processing guarantees of ADR-009, tested without a broker."""

from __future__ import annotations

import pytest
from cheatsheet.platform.cache import RegistroDeIdempotenciaEnMemoria
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.workers import base
from cheatsheet.workers.base import AnteUnaFalla, EjecutorIdempotente, PoliticaDeReintentos
from redis.exceptions import RedisError
from structlog.testing import capture_logs

from tests.logs import logger_nuevo


@pytest.mark.asyncio
async def test_la_misma_clave_no_repite_el_efecto(empresa_id: EmpresaId):
    """The one guarantee that keeps a retried task from charging a customer twice."""
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo="cobrar", payload={"monto": "100.00"}
    )
    ejecuciones: list[int] = []

    async def efecto() -> str:
        ejecuciones.append(1)
        return "hecho"

    primero = await ejecutor.ejecutar(clave, efecto, ante_una_falla=AnteUnaFalla.LIBERAR)
    segundo = await ejecutor.ejecutar(clave, efecto, ante_una_falla=AnteUnaFalla.LIBERAR)

    assert primero == "hecho"
    assert segundo is None
    assert len(ejecuciones) == 1


@pytest.mark.asyncio
async def test_claves_distintas_ejecutan_cada_una(empresa_id: EmpresaId):
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    ejecuciones: list[int] = []

    async def efecto() -> None:
        ejecuciones.append(1)

    for monto in ("100.00", "200.00"):
        clave = ClaveDeIdempotencia.de(
            empresa_id=empresa_id, tipo="cobrar", payload={"monto": monto}
        )
        await ejecutor.ejecutar(clave, efecto, ante_una_falla=AnteUnaFalla.LIBERAR)

    assert len(ejecuciones) == 2


class _FalloDeEfecto(Exception):
    """The effect's own failure, as opposed to the registry's."""


def _clave(empresa_id: EmpresaId) -> ClaveDeIdempotencia:
    return ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="enviar", payload={"id": 1})


class _EfectoQueFallaUnaVez:
    """Raises on the first call and succeeds afterwards — a transient outage."""

    def __init__(self) -> None:
        self.llamadas = 0

    async def __call__(self) -> str:
        self.llamadas += 1
        if self.llamadas == 1:
            raise _FalloDeEfecto("el proveedor no respondio")
        return "hecho"


@pytest.mark.asyncio
async def test_con_liberar_un_efecto_que_falla_deja_la_clave_libre(empresa_id: EmpresaId):
    """Caso 2. The retry of a failed attempt has to run the effect again."""
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    efecto = _EfectoQueFallaUnaVez()

    with pytest.raises(_FalloDeEfecto):
        await ejecutor.ejecutar(_clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.LIBERAR)
    reintento = await ejecutor.ejecutar(
        _clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.LIBERAR
    )

    assert reintento == "hecho"
    assert efecto.llamadas == 2


@pytest.mark.asyncio
async def test_con_liberar_un_efecto_exitoso_sigue_sin_repetirse(empresa_id: EmpresaId):
    """Releasing is for failures only: success keeps the key."""
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    efecto = _EfectoQueFallaUnaVez()
    efecto.llamadas = 1  # skip the failing first call

    await ejecutor.ejecutar(_clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.LIBERAR)
    repetido = await ejecutor.ejecutar(
        _clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.LIBERAR
    )

    assert repetido is None
    assert efecto.llamadas == 2


@pytest.mark.asyncio
async def test_con_retener_un_efecto_que_falla_deja_la_clave_tomada(empresa_id: EmpresaId):
    """Caso 4. The guarantee a future `Cobro` needs: an effect that may have half
    happened is never silently repeated."""
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    efecto = _EfectoQueFallaUnaVez()

    with pytest.raises(_FalloDeEfecto):
        await ejecutor.ejecutar(_clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.RETENER)
    reintento = await ejecutor.ejecutar(
        _clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.RETENER
    )

    assert reintento is None
    assert efecto.llamadas == 1


class _RegistroQueNoPuedeLiberar(RegistroDeIdempotenciaEnMemoria):
    async def liberar(self, clave: ClaveDeIdempotencia) -> None:
        del clave
        raise RedisError("Redis no responde")


@pytest.mark.asyncio
async def test_si_liberar_falla_sube_la_excepcion_original(
    empresa_id: EmpresaId, monkeypatch: pytest.MonkeyPatch
):
    """Caso 5. The caller (Celery) must see the effect's error, not Redis's, and the
    operator must see that the key stayed taken."""
    logger_nuevo(monkeypatch, base)
    ejecutor = EjecutorIdempotente(_RegistroQueNoPuedeLiberar())

    with capture_logs() as registros, pytest.raises(_FalloDeEfecto):
        await ejecutor.ejecutar(
            _clave(empresa_id), _EfectoQueFallaUnaVez(), ante_una_falla=AnteUnaFalla.LIBERAR
        )

    avisos = [r for r in registros if r["event"] == "liberacion_de_idempotencia_fallida"]
    assert len(avisos) == 1
    assert avisos[0]["causa"] == "RedisError"


@pytest.mark.asyncio
async def test_una_cancelacion_no_libera_la_clave(empresa_id: EmpresaId):
    """The outcome is unknown when the task is cancelled mid-effect: do not repeat it."""
    import asyncio

    registro = RegistroDeIdempotenciaEnMemoria()
    ejecutor = EjecutorIdempotente(registro)

    async def efecto() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await ejecutor.ejecutar(_clave(empresa_id), efecto, ante_una_falla=AnteUnaFalla.LIBERAR)

    assert await registro.registrar_si_es_nueva(_clave(empresa_id)) is False


def test_el_orden_de_las_claves_del_payload_no_cambia_la_huella(empresa_id: EmpresaId):
    """The same delivery serialised differently is still the same delivery."""
    una = ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="t", payload={"a": 1, "b": 2})
    otra = ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="t", payload={"b": 2, "a": 1})

    assert una == otra


def test_tenants_distintos_nunca_comparten_clave():
    """Otherwise one company's webhook would suppress another company's."""
    from uuid import uuid4

    payload = {"evento": "payment.updated"}
    una = ClaveDeIdempotencia.de(empresa_id=EmpresaId(uuid4()), tipo="t", payload=payload)
    otra = ClaveDeIdempotencia.de(empresa_id=EmpresaId(uuid4()), tipo="t", payload=payload)

    assert una != otra


def test_la_espera_crece_y_nunca_supera_el_techo():
    politica = PoliticaDeReintentos(max_intentos=5, espera_base=2.0, espera_maxima=10.0)

    for intento in range(1, 6):
        assert 0.0 <= politica.espera_para(intento) <= 10.0


def test_la_espera_exige_un_intento_valido():
    with pytest.raises(ValueError, match="arranca en 1"):
        PoliticaDeReintentos().espera_para(0)


def test_los_intentos_se_agotan_en_el_maximo():
    politica = PoliticaDeReintentos(max_intentos=3)

    assert politica.agoto_los_intentos(2) is False
    assert politica.agoto_los_intentos(3) is True
