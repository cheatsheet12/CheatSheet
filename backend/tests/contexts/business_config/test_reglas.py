"""HU-E11-01 — las reglas de negocio parametrizables.

Lo que se prueba acá es la **decisión D24**: el JSONB no está validado por el esquema, así que
la validación tiene que estar en el dominio y tiene que romper **al leer**. Un `KeyError` a la
mitad de un barrido que ya mandó tres mensajes es peor que un error al construir.

Y lo que hace que HS-T3 funcione siempre: **sin regla configurada hay un default**. Una
empresa que nunca entró a PAN-CFG-RN no puede quedarse sin recordatorios y sin enterarse.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.business_config.application.errors import ReglaInexistente
from cheatsheet.contexts.business_config.application.reglas import (
    MOTIVO_SOLO_ADMIN,
    CambiarEstadoDeRegla,
    ConfigurarEscalamiento,
    ConsultarReglasVigentes,
    ListarReglas,
)
from cheatsheet.contexts.business_config.domain.regla import (
    ESCALAMIENTO_POR_DEFECTO,
    MAXIMO_DE_PASOS,
    MENSAJE_DIAS_INVALIDOS,
    CanalNotificacion,
    ConfiguracionDeEscalamiento,
    PasoDeEscalamiento,
    ReglaDeNegocio,
    TipoRegla,
    resolver,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())


class ReglasFalsas:
    def __init__(self) -> None:
        self.guardadas: dict[UUID, ReglaDeNegocio] = {}

    async def agregar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def guardar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None:
        return self.guardadas.get(regla_id)

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        todas = list(self.guardadas.values())
        return [una for una in todas if tipo is None or una.tipo is tipo]


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _cadena(*dias: int) -> ConfiguracionDeEscalamiento:
    return ConfiguracionDeEscalamiento(
        pasos=tuple(PasoDeEscalamiento(dias=uno, canal=CanalNotificacion.WHATSAPP) for uno in dias)
    )


def _regla(
    configuracion: dict[str, Any] | None = None,
    *,
    prioridad: int = 0,
    activa: bool = True,
    creada: datetime = AHORA,
) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EMPRESA,
        tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
        configuracion=configuracion or _cadena(3, 7).como_json(),
        created_at=creada,
        prioridad=prioridad,
        activa=activa,
    )


# --------------------------------------------------------------------- el value object


def test_los_pasos_se_guardan_ordenados_por_dia() -> None:
    """La normalización es del dominio y no de quien la carga.

    El barrido de HS-T3 recorre la lista de menor a mayor: una configuración escrita al revés
    haría que la cadena empezara por el último recordatorio.
    """
    cadena = _cadena(15, 3, 7)

    assert [paso.dias for paso in cadena.pasos] == [3, 7, 15]


def test_un_paso_de_cero_dias_usa_el_texto_de_la_historia() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _cadena(0)

    assert str(exc.value) == MENSAJE_DIAS_INVALIDOS


def test_dos_pasos_el_mismo_dia_se_rechazan() -> None:
    """Serían dos mensajes seguidos por la misma deuda."""
    with pytest.raises(EntradaInvalida):
        _cadena(3, 3)


def test_una_cadena_vacia_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida):
        ConfiguracionDeEscalamiento(pasos=())


def test_hay_un_tope_de_pasos() -> None:
    """No sale de ninguna historia: sale de que veinte mensajes por una deuda es acoso."""
    with pytest.raises(EntradaInvalida):
        _cadena(*range(1, MAXIMO_DE_PASOS + 2))


def test_la_configuracion_sobrevive_a_la_ida_y_vuelta_por_json() -> None:
    cadena = _cadena(3, 7, 15)

    assert ConfiguracionDeEscalamiento.desde_json(cadena.como_json()) == cadena


@pytest.mark.parametrize(
    "crudo",
    [
        {},
        {"pasos": "tres"},
        {"pasos": [{"dias": 3}]},
        {"pasos": [{"dias": 3, "canal": "PALOMA"}]},
        {"pasos": ["tres dias"]},
    ],
)
def test_una_fila_mal_formada_falla_al_leer(crudo: dict[str, Any]) -> None:
    """**Decisión D24.** La validación no está en el esquema, así que tiene que estar acá.

    Y tiene que romper al leer: un `KeyError` a la mitad de un barrido que ya mandó tres
    mensajes es mucho peor que un error al construir.
    """
    with pytest.raises(EntradaInvalida):
        ConfiguracionDeEscalamiento.desde_json(crudo)


def test_pedir_un_paso_que_no_existe_devuelve_nada() -> None:
    cadena = _cadena(3, 7)

    assert cadena.paso_numero(1) is not None
    assert cadena.paso_numero(3) is None
    # Contando desde 1: «paso 0» no significa nada para quien lea la columna.
    assert cadena.paso_numero(0) is None


# --------------------------------------------------------------------- la resolución


def test_gana_la_de_mayor_prioridad() -> None:
    """RN-05."""
    baja = _regla(prioridad=1)
    alta = _regla(prioridad=9)

    assert resolver([baja, alta], TipoRegla.ESCALAMIENTO_DE_COBRO) is alta


def test_a_igual_prioridad_gana_la_mas_reciente() -> None:
    """El desempate importa: dos reglas con la misma prioridad es algo que alguien va a armar
    sin querer, y «la que se cargó después» es la que menos sorprende."""
    vieja = _regla(creada=datetime(2026, 1, 1, tzinfo=UTC))
    nueva = _regla(creada=datetime(2026, 9, 1, tzinfo=UTC))

    assert resolver([vieja, nueva], TipoRegla.ESCALAMIENTO_DE_COBRO) is nueva


def test_una_regla_desactivada_no_se_considera() -> None:
    """RN-04: deja de aplicarse de inmediato."""
    apagada = _regla(prioridad=9, activa=False)
    encendida = _regla(prioridad=1)

    assert resolver([apagada, encendida], TipoRegla.ESCALAMIENTO_DE_COBRO) is encendida


def test_una_regla_de_otro_tipo_no_se_considera() -> None:
    otra = _regla()
    otra.tipo = TipoRegla.POLITICA_DE_TURNO

    assert resolver([otra], TipoRegla.ESCALAMIENTO_DE_COBRO) is None


def test_interpretar_una_regla_del_tipo_equivocado_falla() -> None:
    regla = _regla()
    regla.tipo = TipoRegla.POLITICA_DE_TURNO

    with pytest.raises(EntradaInvalida):
        regla.interpretada_como_escalamiento()


# --------------------------------------------------------------------- los casos de uso


@pytest.mark.asyncio
async def test_configurar_crea_la_regla_la_primera_vez() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()

    regla = await ConfigurarEscalamiento(reglas=reglas, publicador=publicador).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        configuracion=_cadena(3, 7),
        ahora=AHORA,
    )

    assert reglas.guardadas[regla.id] is regla
    assert len(publicador.eventos) == 1


@pytest.mark.asyncio
async def test_configurar_dos_veces_reemplaza_en_vez_de_acumular() -> None:
    """Una empresa tiene **una** cadena de escalamiento, no un catálogo de cadenas.

    Si cada guardado creara una fila, la resolución por prioridad tendría que desempatar
    entre versiones de lo mismo y la pantalla mostraría cinco reglas donde hay una.
    """
    reglas = ReglasFalsas()
    configurar = ConfigurarEscalamiento(reglas=reglas, publicador=PublicadorFalso())

    await configurar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        configuracion=_cadena(3, 7),
        ahora=AHORA,
    )
    await configurar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        configuracion=_cadena(5, 10, 20),
        ahora=AHORA,
    )

    assert len(reglas.guardadas) == 1
    unica = next(iter(reglas.guardadas.values()))
    assert [paso.dias for paso in unica.interpretada_como_escalamiento().pasos] == [5, 10, 20]


@pytest.mark.asyncio
async def test_guardar_una_regla_apagada_la_reactiva() -> None:
    """Quien edita una regla apagada está queriendo usarla; dejarla apagada sería guardar
    algo que no tiene efecto sin decirlo."""
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(activa=False))

    regla = await ConfigurarEscalamiento(reglas=reglas, publicador=PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        configuracion=_cadena(5),
        ahora=AHORA,
    )

    assert regla.activa


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_solo_el_administrador_configura(rol: RolUsuario) -> None:
    with pytest.raises(OperacionNoPermitida) as exc:
        await ConfigurarEscalamiento(reglas=ReglasFalsas(), publicador=PublicadorFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            configuracion=_cadena(3),
            ahora=AHORA,
        )

    assert str(exc.value) == MOTIVO_SOLO_ADMIN


@pytest.mark.asyncio
async def test_desactivar_una_regla_inexistente_falla() -> None:
    with pytest.raises(ReglaInexistente):
        await CambiarEstadoDeRegla(reglas=ReglasFalsas(), publicador=PublicadorFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            regla_id=uuid4(),
            activa=False,
            ahora=AHORA,
        )


@pytest.mark.asyncio
async def test_listar_incluye_las_inactivas() -> None:
    """La pantalla las muestra con su estado (RN-01), así que filtrarlas acá obligaría a un
    segundo método para lo mismo."""
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(activa=False))

    assert len(await ListarReglas(reglas).ejecutar()) == 1


# --------------------------------------------------------------------- el Open Host Service


@pytest.mark.asyncio
async def test_sin_regla_configurada_rige_el_default_y_se_dice() -> None:
    """**Lo que hace que HS-T3 funcione siempre.**

    Devolver «nada» obligaría a cada consumidor a decidir qué hacer sin cadena, y una empresa
    que nunca entró a PAN-CFG-RN se quedaría sin recordatorios sin enterarse.
    """
    vigentes = await ConsultarReglasVigentes(ReglasFalsas()).ejecutar(empresa_id=EMPRESA)

    assert vigentes.escalamiento == ESCALAMIENTO_POR_DEFECTO
    assert not vigentes.configurada


@pytest.mark.asyncio
async def test_con_regla_configurada_rige_esa() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_cadena(5, 10).como_json()))

    vigentes = await ConsultarReglasVigentes(reglas).ejecutar(empresa_id=EMPRESA)

    assert [paso.dias for paso in vigentes.escalamiento.pasos] == [5, 10]
    assert vigentes.configurada


@pytest.mark.asyncio
async def test_con_la_regla_apagada_vuelve_el_default() -> None:
    """RN-04, visto desde el consumidor: desactivar deja de aplicar de inmediato."""
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_cadena(5, 10).como_json(), activa=False))

    vigentes = await ConsultarReglasVigentes(reglas).ejecutar(empresa_id=EMPRESA)

    assert vigentes.escalamiento == ESCALAMIENTO_POR_DEFECTO
    assert not vigentes.configurada
