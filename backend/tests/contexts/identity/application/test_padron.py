"""La deuda D1, del lado de `identity` — casos 15 a 21 del plan.

Tres comportamientos y una regla que los cruza a los tres: **no encontrar y no poder
preguntar son cosas distintas**. El primero bloquea al Administrador; el segundo no puede,
porque la situación normal apenas termina el onboarding es justamente que no se puede
preguntar — todavía no hay certificado.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.errors import (
    CuitInexistenteEnPadron,
    PermisoDenegado,
)
from cheatsheet.contexts.identity.application.onboarding import CompletarDatosDeEmpresa
from cheatsheet.contexts.identity.application.padron import (
    ACCION_CERTIFICADO_AJENO,
    ACCION_CUIT_INEXISTENTE,
    ConsultarPadronDeCuit,
    EstadoDeConsulta,
    RevalidarDatosFiscales,
)
from cheatsheet.contexts.identity.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email, RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import (
    CUIT_VALIDO,
    PublicadorFalso,
    RepositorioEmpresaEnMemoria,
)

pytestmark = pytest.mark.asyncio

USUARIO = UsuarioId(uuid4())
#: 20-12345678-9 — el que declara el certificado de las fixtures de ARCA.
OTRO_CUIT = "20123456789"

DEL_PADRON = DatosFiscalesDePadron(
    razon_social="PANADERIA DONA ROSA SRL",
    condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
    activo=True,
)


class PadronFalso:
    """Implements `PortPadron`. Tres desenlaces, que es todo el vocabulario del puerto."""

    def __init__(
        self,
        *,
        datos: DatosFiscalesDePadron | None = DEL_PADRON,
        excepcion: Exception | None = None,
    ) -> None:
        self.datos = datos
        self.excepcion = excepcion
        self.llamadas = 0
        self.ultimo_cuit: str | None = None

    async def consultar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosFiscalesDePadron | None:
        del empresa_id
        self.llamadas += 1
        self.ultimo_cuit = cuit
        if self.excepcion is not None:
            raise self.excepcion
        return self.datos


def _empresa(*, con_datos: bool = True) -> Empresa:
    empresa = Empresa(id=EmpresaId(uuid4()))
    if con_datos:
        empresa.completar_datos_fiscales(
            razon_social="Panaderia Dona Rosa",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.MONOTRIBUTO,
            nombre_responsable="Rosa Diaz",
            email_contacto=Email("rosa@panaderia.com"),
        )
    return empresa


async def _con_empresa(empresa: Empresa) -> RepositorioEmpresaEnMemoria:
    empresas = RepositorioEmpresaEnMemoria()
    await empresas.agregar(empresa)
    return empresas


def _auditorias(publicador: PublicadorFalso) -> list[EventoAuditable]:
    return [e for e in publicador.eventos if isinstance(e, EventoAuditable)]


# --- ConsultarPadronDeCuit ---------------------------------------------------


async def test_la_consulta_devuelve_los_tres_estados_por_separado() -> None:
    """Caso 21 y su contexto: la pantalla tiene que mostrar tres mensajes, no dos."""
    encontrado = await ConsultarPadronDeCuit(padron=PadronFalso()).ejecutar(
        empresa_id=EmpresaId(uuid4()), cuit=CUIT_VALIDO, rol=RolUsuario.ADMINISTRADOR
    )
    no_encontrado = await ConsultarPadronDeCuit(padron=PadronFalso(datos=None)).ejecutar(
        empresa_id=EmpresaId(uuid4()), cuit=CUIT_VALIDO, rol=RolUsuario.ADMINISTRADOR
    )
    sin_arca = await ConsultarPadronDeCuit(
        padron=PadronFalso(excepcion=PadronNoDisponible("ARCA no esta conectada"))
    ).ejecutar(empresa_id=EmpresaId(uuid4()), cuit=CUIT_VALIDO, rol=RolUsuario.ADMINISTRADOR)

    assert encontrado.estado is EstadoDeConsulta.ENCONTRADO
    assert encontrado.datos is not None
    assert no_encontrado.estado is EstadoDeConsulta.NO_ENCONTRADO
    assert sin_arca.estado is EstadoDeConsulta.NO_DISPONIBLE
    assert sin_arca.motivo is not None


async def test_un_operador_no_puede_consultar_el_padron() -> None:
    """Caso 21. HU-E1-02 es del Administrador, y cada consulta gasta un pedido en ARCA."""
    padron = PadronFalso()

    with pytest.raises(PermisoDenegado):
        await ConsultarPadronDeCuit(padron=padron).ejecutar(
            empresa_id=EmpresaId(uuid4()), cuit=CUIT_VALIDO, rol=RolUsuario.OPERADOR
        )

    assert padron.llamadas == 0


# --- CompletarDatosDeEmpresa -------------------------------------------------


async def _guardar(empresa: Empresa, padron: PadronFalso | None) -> RepositorioEmpresaEnMemoria:
    empresas = await _con_empresa(empresa)
    await CompletarDatosDeEmpresa(
        empresas=empresas, publicador=PublicadorFalso(), padron=padron
    ).ejecutar(
        empresa_id=empresa.id,
        usuario_id=USUARIO,
        razon_social="Panaderia Dona Rosa",
        cuit=CUIT(CUIT_VALIDO),
        condicion_iva=CondicionIVA.MONOTRIBUTO,
        nombre_responsable="Rosa Diaz",
        email_contacto=Email("rosa@panaderia.com"),
        ahora=INSTANTE_FIJO,
    )
    return empresas


async def test_un_cuit_que_arca_desconoce_bloquea_el_guardado() -> None:
    """Caso 15. RN-01 al pie de la letra, en el único momento en que se puede aplicar."""
    empresa = _empresa(con_datos=False)
    empresas = await _con_empresa(empresa)

    with pytest.raises(CuitInexistenteEnPadron):
        await CompletarDatosDeEmpresa(
            empresas=empresas, publicador=PublicadorFalso(), padron=PadronFalso(datos=None)
        ).ejecutar(
            empresa_id=empresa.id,
            usuario_id=USUARIO,
            razon_social="Panaderia Dona Rosa",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.MONOTRIBUTO,
            nombre_responsable="Rosa Diaz",
            email_contacto=Email("rosa@panaderia.com"),
            ahora=INSTANTE_FIJO,
        )

    assert empresas.empresas[empresa.id].cuit is None


async def test_si_el_padron_no_esta_disponible_se_guarda_igual() -> None:
    """Caso 16, y es el camino de todos los días hasta que la empresa conecta ARCA."""
    empresa = _empresa(con_datos=False)

    empresas = await _guardar(empresa, PadronFalso(excepcion=PadronNoDisponible("sin ARCA")))

    assert empresas.empresas[empresa.id].cuit is not None


async def test_sin_padron_conectado_el_caso_de_uso_se_comporta_como_antes() -> None:
    """El onboarding del épico 1, intacto: `padron=None` es el paso 2 de siempre."""
    empresa = _empresa(con_datos=False)

    empresas = await _guardar(empresa, None)

    assert empresas.empresas[empresa.id].onboarding_completo is False  # faltan los terminos
    assert empresas.empresas[empresa.id].datos_fiscales_completos


# --- RevalidarDatosFiscales --------------------------------------------------


async def _revalidar(
    empresa: Empresa,
    padron: PadronFalso,
    *,
    cuit_declarado: str | None = None,
) -> tuple[object, PublicadorFalso, RepositorioEmpresaEnMemoria]:
    empresas = await _con_empresa(empresa)
    publicador = PublicadorFalso()
    aviso = await RevalidarDatosFiscales(
        empresas=empresas, padron=padron, publicador=publicador
    ).ejecutar(
        empresa_id=empresa.id,
        ahora=INSTANTE_FIJO,
        cuit_declarado=cuit_declarado,
        usuario_id=USUARIO,
    )
    return aviso, publicador, empresas


async def test_completa_solo_los_campos_vacios() -> None:
    """Caso 17. El autocompletado del criterio de aceptación 1, llegando tarde pero llegando."""
    empresa = Empresa(id=EmpresaId(uuid4()), cuit=CUIT(CUIT_VALIDO))

    aviso, _, empresas = await _revalidar(empresa, PadronFalso())

    guardada = empresas.empresas[empresa.id]
    assert guardada.razon_social == "PANADERIA DONA ROSA SRL"
    assert guardada.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO
    assert aviso is None


async def test_no_pisa_una_razon_social_ya_cargada() -> None:
    """Caso 18. Nadie está mirando esta corrida: reescribir el nombre sería una sorpresa."""
    empresa = _empresa()

    aviso, _, empresas = await _revalidar(empresa, PadronFalso())

    guardada = empresas.empresas[empresa.id]
    assert guardada.razon_social == "Panaderia Dona Rosa"
    # La condición sí difiere, y eso se informa en vez de corregirse solo.
    assert aviso is not None


async def test_un_cuit_inexistente_avisa_y_queda_en_la_bitacora() -> None:
    empresa = _empresa()

    aviso, publicador, _ = await _revalidar(empresa, PadronFalso(datos=None))

    assert aviso is not None
    evento = _auditorias(publicador)[0]
    assert evento.accion == ACCION_CUIT_INEXISTENTE
    assert evento.resultado is Resultado.ERROR


async def test_el_certificado_de_otro_cuit_se_detecta_antes_de_preguntar() -> None:
    """Caso 19. Sale casi gratis y evita emitir el primer comprobante a nombre equivocado."""
    empresa = _empresa()
    padron = PadronFalso()

    aviso, publicador, _ = await _revalidar(empresa, padron, cuit_declarado=OTRO_CUIT)

    assert aviso is not None
    assert _auditorias(publicador)[0].accion == ACCION_CERTIFICADO_AJENO
    # No se consultó: el desajuste ya es motivo suficiente y ahorra un pedido a ARCA.
    assert padron.llamadas == 0


async def test_un_certificado_del_mismo_cuit_con_guiones_no_es_un_desajuste() -> None:
    """El certificado escribe `CUIT 30712345671`; el formulario, `30-71234567-1`."""
    empresa = _empresa()

    aviso, _, _ = await _revalidar(empresa, PadronFalso(), cuit_declarado="30-71234567-1")

    assert aviso is not None  # difiere la condicion de IVA, no el CUIT
    assert "otro CUIT" not in aviso.motivo  # type: ignore[attr-defined]


async def test_un_certificado_sin_cuit_no_cuenta_como_desajuste() -> None:
    """`conexion-arca` nunca bloqueó una conexión por eso, así que acá tampoco."""
    empresa = Empresa(id=EmpresaId(uuid4()), cuit=CUIT(CUIT_VALIDO))

    aviso, _, _ = await _revalidar(empresa, PadronFalso(), cuit_declarado=None)

    assert aviso is None


async def test_un_cuit_dado_de_baja_avisa_sin_bloquear_nada() -> None:
    empresa = Empresa(id=EmpresaId(uuid4()), cuit=CUIT(CUIT_VALIDO))
    dado_de_baja = DatosFiscalesDePadron(
        razon_social="EX EMPRESA SRL", condicion_iva=None, activo=False
    )

    aviso, _, empresas = await _revalidar(empresa, PadronFalso(datos=dado_de_baja))

    assert aviso is not None
    assert "no esta activo" in aviso.motivo  # type: ignore[attr-defined]
    assert empresas.empresas[empresa.id].razon_social == "EX EMPRESA SRL"


async def test_si_arca_no_responde_la_revalidacion_calla() -> None:
    """El certificado acaba de ser aceptado; un aviso acá enseñaría a ignorar los avisos."""
    empresa = _empresa()

    aviso, publicador, _ = await _revalidar(
        empresa, PadronFalso(excepcion=PadronNoDisponible("ARCA no responde"))
    )

    assert aviso is None
    assert _auditorias(publicador) == []


async def test_la_bitacora_registra_el_hallazgo_y_no_lo_que_dijo_arca() -> None:
    """Caso 20. Lo que ARCA contesta es el nombre real y la situación fiscal de alguien."""
    empresa = _empresa()

    _, publicador, _ = await _revalidar(empresa, PadronFalso(datos=None))

    evento = _auditorias(publicador)[0]
    assert evento.entidad_afectada == f"Empresa:{empresa.id}"
    assert evento.usuario_id == USUARIO
    assert "PANADERIA" not in evento.accion
