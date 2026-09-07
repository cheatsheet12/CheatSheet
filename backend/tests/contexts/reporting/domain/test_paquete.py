"""El dominio del paquete contable y del enlace del contador (HU-E10-04 … HU-E10-06).

Las tres reglas que este archivo protege, y por qué están en el agregado y no en la pantalla:

1. **No se activa el envío sin email del contador** (tercer criterio de HU-E10-04, textual).
   Activar sin destinatario produce un envío mensual que no llega a ningún lado y que nadie
   nota hasta que el contador pregunta.
2. **Revocar corta de inmediato** (HU-E10-05 RN-03). Sin «a partir de» y sin gracia.
3. **Un acceso no vigente no se cuenta** (HU-E10-06 RN-03). Contar un acceso que no ocurrió
   haría que el número dejara de significar «cuántas veces entró el contador».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.reporting.domain.paquete import (
    CONTENIDO_COMPLETO,
    MENSAJE_SIN_EMAIL,
    ConfiguracionDelPaquete,
    ContenidoDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def _configuracion(**cambios: object) -> ConfiguracionDelPaquete:
    datos: dict[str, object] = {"empresa_id": EmpresaId(uuid4())}
    datos.update(cambios)
    return ConfiguracionDelPaquete(**datos)  # type: ignore[arg-type]


def _token(**cambios: object) -> TokenDeAccesoContable:
    datos: dict[str, object] = {
        "id": uuid4(),
        "paquete_id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "valor_hash": "a" * 64,
        "email_contador": "contador@estudio.com.ar",
        "vencimiento": AHORA + timedelta(days=30),
    }
    datos.update(cambios)
    return TokenDeAccesoContable(**datos)  # type: ignore[arg-type]


class TestConfiguracion:
    def test_por_defecto_lleva_todo_el_contenido(self) -> None:
        """Quitar cosas del paquete es una decisión que alguien tiene que tomar."""
        assert _configuracion().contenido == CONTENIDO_COMPLETO

    def test_no_se_activa_sin_email(self) -> None:
        with pytest.raises(InvarianteViolada) as error:
            _configuracion().activar(AHORA)
        assert str(error.value) == MENSAJE_SIN_EMAIL

    def test_se_activa_con_email(self) -> None:
        configuracion = _configuracion()
        configuracion.asignar_contador("Contador@Estudio.com.ar ", AHORA)
        configuracion.activar(AHORA)
        assert configuracion.activo
        # Normalizado: el mismo contador escrito de dos formas es el mismo contador.
        assert configuracion.email_contador == "contador@estudio.com.ar"

    def test_un_email_invalido_se_rechaza(self) -> None:
        with pytest.raises(EntradaInvalida):
            _configuracion().asignar_contador("no-es-un-email", AHORA)

    def test_el_dia_va_del_1_al_28(self) -> None:
        """Febrero existe: un envío programado para el 30 no saldría nunca en febrero."""
        with pytest.raises(EntradaInvalida):
            _configuracion(dia_de_envio=30)

    def test_sin_formatos_no_hay_paquete(self) -> None:
        with pytest.raises(EntradaInvalida):
            _configuracion(formatos=frozenset())

    def test_proximo_envio_es_none_si_esta_desactivado(self) -> None:
        assert _configuracion().proximo_envio(AHORA) is None

    def test_proximo_envio_de_este_mes(self) -> None:
        configuracion = _configuracion(dia_de_envio=20, email_contador="c@e.com")
        configuracion.activar(AHORA)
        assert configuracion.proximo_envio(AHORA) == datetime(2026, 3, 20, tzinfo=UTC)

    def test_proximo_envio_salta_al_mes_siguiente_si_ya_paso(self) -> None:
        configuracion = _configuracion(dia_de_envio=5, email_contador="c@e.com")
        configuracion.activar(AHORA)
        assert configuracion.proximo_envio(AHORA) == datetime(2026, 4, 5, tzinfo=UTC)

    def test_configurar_revalida(self) -> None:
        configuracion = _configuracion()
        with pytest.raises(EntradaInvalida):
            configuracion.configurar(
                dia_de_envio=31,
                formatos=frozenset({"PDF"}),
                contenido=CONTENIDO_COMPLETO,
                momento=AHORA,
            )

    def test_desactivar(self) -> None:
        configuracion = _configuracion(email_contador="c@e.com")
        configuracion.activar(AHORA)
        configuracion.desactivar(AHORA)
        assert not configuracion.activo


class TestPaquete:
    def test_etiqueta(self) -> None:
        paquete = PaqueteContable(
            id=uuid4(), empresa_id=EmpresaId(uuid4()), periodo_anio=2026, periodo_mes=3
        )
        assert paquete.etiqueta == "2026-03"
        assert not paquete.esta_disponible

    def test_los_importes_viajan_como_texto(self) -> None:
        """Un `float` en un JSONB está mal en el cuarto decimal, que es donde vive un centavo."""
        paquete = PaqueteContable(
            id=uuid4(), empresa_id=EmpresaId(uuid4()), periodo_anio=2026, periodo_mes=3
        )
        paquete.registrar_totales(ContenidoDelPaquete.FACTURAS.value, 3, Decimal("12500.55"))
        assert paquete.totales_por_tipo["FACTURAS"] == {"cantidad": "3", "total": "12500.55"}

    def test_un_mes_invalido_no_existe(self) -> None:
        with pytest.raises(EntradaInvalida):
            PaqueteContable(
                id=uuid4(), empresa_id=EmpresaId(uuid4()), periodo_anio=2026, periodo_mes=0
            )


class TestToken:
    def test_vigente(self) -> None:
        assert _token().esta_vigente(AHORA)

    def test_revocar_corta_de_inmediato(self) -> None:
        token = _token()
        token.revocar()
        assert not token.esta_vigente(AHORA)

    def test_vencido(self) -> None:
        token = _token(vencimiento=AHORA - timedelta(seconds=1))
        assert not token.esta_vigente(AHORA)

    def test_cuenta_los_accesos(self) -> None:
        token = _token()
        token.registrar_acceso(AHORA)
        token.registrar_acceso(AHORA)
        assert token.accesos == 2

    def test_un_acceso_que_no_ocurrio_no_se_cuenta(self) -> None:
        token = _token()
        token.revocar()
        with pytest.raises(InvarianteViolada):
            token.registrar_acceso(AHORA)
        assert token.accesos == 0

    def test_un_email_invalido_no_construye_token(self) -> None:
        with pytest.raises(EntradaInvalida):
            _token(email_contador="arroba-nada@")
