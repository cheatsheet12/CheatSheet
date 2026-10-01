"""HU-E4-05 vista desde la capa de aplicación: lo que el panel guarda y lo que rechaza.

Archivo nuevo porque `test_clientes.py` y `test_categorias.py` ya pasan de 400 líneas.

Tres cosas se fijan:

- **El nombre sale normalizado del alta** (RN-07), con el CUIT que decide si es persona o
  razón social (RN-03).
- **Editar usa el CUIT nuevo para normalizar** el nombre que viene en la misma edición.
- **La unicidad de categoría se evalúa sobre el nombre normalizado** (RN-04): «VIP   GOLD»
  choca con «Vip gold», que la búsqueda cruda no encontraba.

El email y el WhatsApp ya estaban normalizados por sus value objects (RN-05); se dejan dos
tests de caracterización para que no se pierdan.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.application.categorias import (
    EditarCategoria,
    RegistrarCategoria,
)
from cheatsheet.contexts.master_data.application.clientes import (
    DatosDeCliente,
    EditarCliente,
    RegistrarCliente,
    VistaDeCliente,
)
from cheatsheet.contexts.master_data.application.errors import CategoriaDuplicada, ClienteDuplicado
from cheatsheet.contexts.master_data.domain.categoria import MENSAJE_DUPLICADA, CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import (
    CUIT_VALIDO,
    OTRO_CUIT_VALIDO,
    PublicadorFalso,
    RepositorioCategoriaEnMemoria,
    RepositorioClienteEnMemoria,
    padron_sin_conectar,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)


async def _alta(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso, datos: DatosDeCliente
) -> VistaDeCliente:
    return await RegistrarCliente(
        clientes=clientes, padron=padron_sin_conectar(), publicador=publicador, reloj=RELOJ
    ).ejecutar(empresa_id=EMPRESA, usuario_id=USUARIO, rol=RolUsuario.OPERADOR, datos=datos)


async def _categoria(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso, nombre: str
) -> CategoriaEmpresa:
    return await RegistrarCategoria(
        categorias=categorias, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        nombre=nombre,
        aplica_a=AmbitoDeCategoria.CLIENTE,
    )


# --- Clientes ------------------------------------------------------------------------


async def test_el_alta_de_una_persona_guarda_el_nombre_normalizado(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    vista = await _alta(clientes, publicador, DatosDeCliente(nombre="JUAN CARLOS DE LA CRUZ"))

    assert vista.cliente.nombre == "Juan Carlos de la Cruz"


async def test_el_alta_con_cuit_de_empresa_guarda_razon_social(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    vista = await _alta(
        clientes,
        publicador,
        DatosDeCliente(nombre="ferreteria lopez s.r.l.", cuit=CUIT_VALIDO),
    )

    assert vista.cliente.nombre == "Ferreteria Lopez S.R.L."


async def test_email_y_whatsapp_ya_estaban_normalizados(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """RN-05, caracterización: se citan, no se rehacen."""
    vista = await _alta(
        clientes,
        publicador,
        DatosDeCliente(
            nombre="Ana Perez",
            contacto_email="Ana@Mail.COM",
            contacto_whatsapp="+54 9 11 1234-5678",
        ),
    )

    assert str(vista.cliente.contacto_email) == "ana@mail.com"
    assert str(vista.cliente.contacto_whatsapp) == "5491112345678"


async def test_editar_con_un_cuit_nuevo_normaliza_el_nombre_como_razon_social(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """Hallazgo 1: el CUIT se carga **antes** de renombrar, no después."""
    alta = await _alta(clientes, publicador, DatosDeCliente(nombre="Ferreteria Lopez"))

    vista = await EditarCliente(
        clientes=clientes, padron=padron_sin_conectar(), publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=alta.cliente.id,
        datos=DatosDeCliente(nombre="IBM ARGENTINA SA", cuit=CUIT_VALIDO),
    )

    assert vista.cliente.nombre == "IBM Argentina SA"


async def test_un_cuit_con_guiones_choca_con_el_mismo_cuit_en_digitos(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """HU-E4-01 RN-05, caracterización: la unicidad se evalúa sobre el CUIT normalizado."""
    await _alta(clientes, publicador, DatosDeCliente(nombre="Uno", cuit=OTRO_CUIT_VALIDO))

    with pytest.raises(ClienteDuplicado, match=r"Ya existe un cliente con ese CUIT."):
        await _alta(clientes, publicador, DatosDeCliente(nombre="Dos", cuit="20-12345678-6"))


# --- Categorías ----------------------------------------------------------------------


async def test_una_categoria_en_mayusculas_choca_con_la_existente(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _categoria(categorias, publicador, "Vip")

    with pytest.raises(CategoriaDuplicada, match=MENSAJE_DUPLICADA):
        await _categoria(categorias, publicador, "VIP")


async def test_el_espacio_doble_no_esquiva_la_unicidad(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _categoria(categorias, publicador, "Vip gold")

    with pytest.raises(CategoriaDuplicada, match=MENSAJE_DUPLICADA):
        await _categoria(categorias, publicador, "VIP   GOLD")


async def test_renombrar_tambien_busca_por_el_nombre_normalizado(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _categoria(categorias, publicador, "Vip gold")
    otra = await _categoria(categorias, publicador, "Mayorista")

    with pytest.raises(CategoriaDuplicada, match=MENSAJE_DUPLICADA):
        await EditarCategoria(categorias=categorias, publicador=publicador, reloj=RELOJ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            categoria_id=otra.id,
            nombre="VIP  GOLD",
            aplica_a=AmbitoDeCategoria.CLIENTE,
        )
