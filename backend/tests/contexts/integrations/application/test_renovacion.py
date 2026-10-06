"""HU-E2-02 RN-03 — el barrido diario que renueva antes de que venza.

Dos reglas se prueban acá, y son opuestas:

- **un rechazo del proveedor desconecta** — el refresh token ya no vale y hay que avisar;
- **un proveedor caído no desconecta nada** — no aprendimos nada, y la credencial que
  tenemos es la que funcionaba ayer.

Confundirlas significa que una tarde mala de MercadoPago deja a todas las empresas sin
poder cobrar, con un mail cada una diciendo que revoquen algo que nadie revocó.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.renovacion import (
    ACCION_RENOVADA,
    RenovarCredenciales,
    vencimiento_de,
)
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_VENCIMIENTO,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    CifradoFalso,
    ConectorProgramado,
    PublicadorFalso,
    RegistroFalso,
    RenovadorProgramado,
    RepositorioIntegracionesEnMemoria,
    VerificadorProgramado,
    configuracion_conectada,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
MARGEN_DIAS = 15


def _auditorias(publicador: PublicadorFalso) -> list[EventoAuditable]:
    return [e for e in publicador.eventos if isinstance(e, EventoAuditable)]


def _vence_en(dias: int) -> dict[str, str]:
    return {CLAVE_VENCIMIENTO: (INSTANTE_FIJO + timedelta(days=dias)).isoformat()}


async def _armar(
    renovador: RenovadorProgramado | None,
    *,
    parametros: dict[str, str] | None = None,
    estado: EstadoDeConexion = EstadoDeConexion.CONECTADO,
    sistema: SistemaExterno = SistemaExterno.MERCADOPAGO,
) -> tuple[RenovarCredenciales, RepositorioIntegracionesEnMemoria, PublicadorFalso]:
    integraciones = RepositorioIntegracionesEnMemoria()
    await integraciones.agregar(
        configuracion_conectada(
            EMPRESA, sistema, estado=estado, parametros=dict(parametros or _vence_en(1))
        )
    )
    publicador = PublicadorFalso()
    registro = RegistroFalso(
        {
            sistema: ParDeAdaptadores(
                conector=ConectorProgramado(),
                verificador=VerificadorProgramado(),
                renovador=renovador,
            )
        }
    )
    caso = RenovarCredenciales(
        integraciones=integraciones,
        cifrado=CifradoFalso(),
        adaptadores=registro,
        publicador=publicador,
        reloj=RelojFijo(INSTANTE_FIJO),
        margen_dias=MARGEN_DIAS,
    )
    return caso, integraciones, publicador


async def test_lo_que_vence_lejos_no_se_toca() -> None:
    """Caso 16. Renovar todos los días sería llamar al proveedor 180 veces por nada."""
    renovador = RenovadorProgramado()
    caso, _, publicador = await _armar(renovador, parametros=_vence_en(180))

    assert await caso.ejecutar(empresa_id=EMPRESA) == []
    assert renovador.llamadas == 0
    assert publicador.eventos == []


async def test_dentro_del_margen_se_renueva_y_se_reescribe_cifrada() -> None:
    """Caso 17. Y el vencimiento avanza, que es lo que hace que mañana no se repita."""
    renovador = RenovadorProgramado(parametros=_vence_en(180))
    caso, integraciones, publicador = await _armar(renovador, parametros=_vence_en(3))

    assert await caso.ejecutar(empresa_id=EMPRESA) == []

    guardada = await integraciones.buscar(EMPRESA, SistemaExterno.MERCADOPAGO)
    assert guardada is not None
    assert guardada.credencial.contenido == b"cifrado:acceso-nuevo\nrefresco-nuevo"
    assert guardada.parametros[CLAVE_VENCIMIENTO] == _vence_en(180)[CLAVE_VENCIMIENTO]
    assert guardada.esta_conectada
    # Nadie recibe un mail porque todo salió bien, pero la bitácora sí lo registra: se
    # reemplazó una credencial guardada.
    assert [e.accion for e in _auditorias(publicador)] == [
        f"Integracion {SistemaExterno.MERCADOPAGO.value}: {ACCION_RENOVADA}"
    ]


async def test_la_credencial_llega_descifrada_al_adaptador() -> None:
    """Punto 3 de ADR-0003: el texto cifrado no sale del contexto, ni entra al adaptador."""
    renovador = RenovadorProgramado()
    caso, _, _ = await _armar(renovador)

    await caso.ejecutar(empresa_id=EMPRESA)

    assert renovador.recibida == b"secreto"


async def test_un_rechazo_desconecta_y_produce_un_desenlace() -> None:
    """Caso 18. RN-03: inactiva y se avisa. El desenlace es lo que la tarea manda por mail."""
    renovador = RenovadorProgramado(excepcion=ConexionRechazada("el acceso fue revocado"))
    caso, integraciones, publicador = await _armar(renovador)

    desenlaces = await caso.ejecutar(empresa_id=EMPRESA)

    assert len(desenlaces) == 1
    assert desenlaces[0].estado is EstadoDeConexion.NO_CONECTADO
    assert desenlaces[0].detalle == "el acceso fue revocado"
    guardada = await integraciones.buscar(EMPRESA, SistemaExterno.MERCADOPAGO)
    assert guardada is not None
    assert not guardada.esta_conectada
    assert len(publicador.eventos) == 1


async def test_un_proveedor_caido_no_desconecta_a_nadie() -> None:
    """Caso 19. La regla del módulo, dicha por el test que más importa de este archivo."""
    renovador = RenovadorProgramado(excepcion=ProveedorNoDisponible("timeout"))
    caso, integraciones, publicador = await _armar(renovador)

    assert await caso.ejecutar(empresa_id=EMPRESA) == []

    guardada = await integraciones.buscar(EMPRESA, SistemaExterno.MERCADOPAGO)
    assert guardada is not None
    assert guardada.esta_conectada
    assert publicador.eventos == []


async def test_una_integracion_ya_inactiva_no_se_reintenta_todos_los_dias() -> None:
    """El Administrador ya fue avisado y tiene que reconectar: insistir no cambia nada."""
    renovador = RenovadorProgramado()
    caso, _, _ = await _armar(renovador, estado=EstadoDeConexion.NO_CONECTADO)

    assert await caso.ejecutar(empresa_id=EMPRESA) == []
    assert renovador.llamadas == 0


async def test_una_integracion_en_atencion_si_se_renueva() -> None:
    """Atención es «anda y hay algo que mirar», no «se terminó»: su token igual vence."""
    renovador = RenovadorProgramado()
    caso, _, _ = await _armar(renovador, estado=EstadoDeConexion.ATENCION)

    await caso.ejecutar(empresa_id=EMPRESA)

    assert renovador.llamadas == 1


async def test_sin_fecha_legible_se_renueva_una_vez_y_se_repara() -> None:
    """Una fecha ilegible es como deja de vigilarse una integración sin que nadie se entere.

    Se renueva ahora, y la renovación escribe una fecha válida — así que se arregla sola
    en lugar de acumular.
    """
    renovador = RenovadorProgramado(parametros=_vence_en(180))
    caso, integraciones, _ = await _armar(renovador, parametros={CLAVE_VENCIMIENTO: "ayer"})

    await caso.ejecutar(empresa_id=EMPRESA)

    assert renovador.llamadas == 1
    guardada = await integraciones.buscar(EMPRESA, SistemaExterno.MERCADOPAGO)
    assert guardada is not None
    assert vencimiento_de(guardada) is not None


async def test_arca_no_entra_en_este_barrido() -> None:
    """Su certificado lo renueva la empresa en el sitio de ARCA, no nosotros."""
    renovador = RenovadorProgramado()
    caso, _, _ = await _armar(renovador, sistema=SistemaExterno.ARCA)

    assert await caso.ejecutar(empresa_id=EMPRESA) == []
    assert renovador.llamadas == 0


async def test_sin_renovador_registrado_no_pasa_nada() -> None:
    """El sistema simulado genérico ya no existe, pero un registro incompleto no rompe."""
    caso, _, _ = await _armar(None)

    assert await caso.ejecutar(empresa_id=EMPRESA) == []
