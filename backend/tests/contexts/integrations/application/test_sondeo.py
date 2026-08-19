"""El sondeo de integraciones pendientes — casos 17 a 20 del plan.

Contra dobles, con el reloj congelado: lo que se prueba acá es **cuándo** el caso de uso
audita y cuándo devuelve un desenlace, que es lo que después decide si sale un mail.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.application.sondeo import (
    MOTIVO_VENCIDO,
    SondearIntegracionesPendientes,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
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
    RepositorioIntegracionesEnMemoria,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
CREDENCIAL = CredencialCifrada(contenido=b"cifrado:token", algoritmo="FALSO/v1")
IDENTIFICADORES = {"phone_number_id": "109876543210987"}


def _pendiente(desde: datetime = INSTANTE_FIJO) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        sistema=SistemaExterno.WHATSAPP,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=desde,
        estado=EstadoDeConexion.PENDIENTE,
        detalle="Meta esta revisando el numero",
        parametros=dict(IDENTIFICADORES),
    )


def _sondeo(
    integraciones: RepositorioIntegracionesEnMemoria,
    publicador: PublicadorFalso,
    verificador: VerificadorProgramado,
    *,
    ahora: datetime = INSTANTE_FIJO,
    maximo_dias: int = 7,
) -> SondearIntegracionesPendientes:
    registro = RegistroFalso(
        {
            SistemaExterno.WHATSAPP: ParDeAdaptadores(
                conector=ConectorProgramado(), verificador=verificador
            )
        }
    )
    return SondearIntegracionesPendientes(
        integraciones=integraciones,
        cifrado=CifradoFalso(),
        adaptadores=registro,
        publicador=publicador,
        reloj=RelojFijo(ahora),
        timeout_segundos=1,
        maximo_dias=maximo_dias,
    )


async def _correr(
    verificador: VerificadorProgramado,
    *,
    configuracion: ConfiguracionDeIntegracion | None = None,
    ahora: datetime = INSTANTE_FIJO,
    maximo_dias: int = 7,
) -> tuple[list[object], PublicadorFalso, ConfiguracionDeIntegracion]:
    configuracion = configuracion or _pendiente()
    integraciones = RepositorioIntegracionesEnMemoria()
    await integraciones.agregar(configuracion)
    publicador = PublicadorFalso()

    desenlaces = await _sondeo(
        integraciones, publicador, verificador, ahora=ahora, maximo_dias=maximo_dias
    ).ejecutar(empresa_id=EMPRESA)

    return list(desenlaces), publicador, configuracion


def _auditorias(publicador: PublicadorFalso) -> list[EventoAuditable]:
    return [e for e in publicador.eventos if isinstance(e, EventoAuditable)]


async def test_el_sondeo_que_aprueba_conecta_audita_una_vez_y_devuelve_un_desenlace() -> None:
    """Caso 17. Segundo criterio de aceptación de HU-E2-03."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(
            EstadoDeConexion.CONECTADO, None, {"display_name": "Panaderia"}
        )
    )

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.CONECTADO
    assert configuracion.parametros["display_name"] == "Panaderia"
    # Los identificadores que cargó el Administrador siguen ahí: se fusiona, no se pisa.
    assert configuracion.parametros["phone_number_id"] == IDENTIFICADORES["phone_number_id"]
    assert len(desenlaces) == 1
    assert len(_auditorias(publicador)) == 1


async def test_el_sondeo_que_rechaza_deja_el_motivo_y_devuelve_un_desenlace() -> None:
    """Caso 18. Tercer criterio: se notifica el motivo y queda sin conectar."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(
            EstadoDeConexion.NO_CONECTADO, "Meta rechazo el nombre para mostrar"
        )
    )

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.NO_CONECTADO
    assert configuracion.detalle_estado == "Meta rechazo el nombre para mostrar"
    assert len(desenlaces) == 1
    assert len(_auditorias(publicador)) == 1


async def test_el_sondeo_que_sigue_pendiente_no_audita_ni_avisa() -> None:
    """Caso 19. Es el desenlace más frecuente: 48 sondeos por día por número.

    Auditar cada uno convertiría el Log de Operaciones en un latido, y HU-E12-01 —que
    filtra ese log por módulo— tendría que aprender a ignorar su entrada más común.
    """
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.PENDIENTE, "Meta sigue revisando")
    )

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.PENDIENTE
    assert desenlaces == []
    assert _auditorias(publicador) == []


async def test_un_proveedor_caido_no_saca_a_la_integracion_de_pendiente() -> None:
    """Meta no rechazó nada: se cayó la red. Inventar un rechazo sería un dato falso."""
    verificador = VerificadorProgramado(excepcion=ProveedorNoDisponible("sin ruta"))

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.PENDIENTE
    assert configuracion.detalle_estado == "sin ruta"
    assert desenlaces == []
    assert _auditorias(publicador) == []


async def test_un_timeout_tampoco_la_saca_de_pendiente() -> None:
    verificador = VerificadorProgramado(demora=5)

    _, _, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.PENDIENTE


async def test_pasado_el_maximo_se_deja_de_esperar_y_se_marca_sin_conectar() -> None:
    """Caso 20. Decisión D-e: siete días, más del doble del techo de RN-02.

    Sin tope, una fila que Meta nunca contesta se sondea para siempre: la empresa queda
    con una tarea eterna y el Administrador con una pantalla que nunca cambia.
    """
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.PENDIENTE)
    )

    desenlaces, publicador, configuracion = await _correr(
        verificador, ahora=INSTANTE_FIJO + timedelta(days=7)
    )

    assert configuracion.estado is EstadoDeConexion.NO_CONECTADO
    assert configuracion.detalle_estado == MOTIVO_VENCIDO
    assert len(desenlaces) == 1
    assert len(_auditorias(publicador)) == 1
    # Y no se le preguntó a Meta: ya se decidió dejar de esperar.
    assert verificador.llamadas == 0


async def test_una_integracion_conectada_no_entra_en_el_sondeo() -> None:
    """El sondeo lee sólo las pendientes; verificar todo cada 30 minutos sería otra cosa."""
    conectada = ConfiguracionDeIntegracion.conectar(
        id=uuid4(),
        empresa_id=EMPRESA,
        sistema=SistemaExterno.ARCA,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=INSTANTE_FIJO,
    )
    integraciones = RepositorioIntegracionesEnMemoria()
    await integraciones.agregar(conectada)
    verificador = VerificadorProgramado()

    desenlaces = await _sondeo(integraciones, PublicadorFalso(), verificador).ejecutar(
        empresa_id=EMPRESA
    )

    assert desenlaces == []
    assert verificador.llamadas == 0


async def test_el_evento_de_auditoria_no_lleva_usuario_porque_nadie_lo_pidio() -> None:
    """Lo hizo el programador de tareas. `usuario_id=None` es el valor honesto."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.CONECTADO)
    )

    _, publicador, _ = await _correr(verificador)

    evento = _auditorias(publicador)[0]
    assert evento.usuario_id is None
    assert evento.direccion_ip is None
    assert evento.empresa_id == EMPRESA
