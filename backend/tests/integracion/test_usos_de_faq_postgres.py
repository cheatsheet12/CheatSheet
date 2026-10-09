"""Los usos de las FAQ contra el motor (ADR-0012, unidad `usos-de-faq-por-periodo`).

Lo que un doble no puede probar, y por eso corre contra PostgreSQL:

1. **El alta es una fila nueva y no toca la FAQ.** Dos respuestas simultáneas cuentan dos, y una
   respuesta del agente que se cruza con una edición del administrador no le pisa la edición.
2. **RLS y solo-inserción** sobre `faq_uso`, y la acción `ON DELETE SET NULL` sobre una tabla
   sin `UPDATE` para el rol de la aplicación: la ejecuta PostgreSQL con los permisos del dueño,
   y acá se verifica en vez de asumirse.
3. **Los límites del mes en hora de Argentina llegan bien a SQL.**

Se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cheatsheet.contexts.conversational.application.contexto import ContextoDelMensaje
from cheatsheet.contexts.conversational.application.faqs import ListarFAQs
from cheatsheet.contexts.conversational.application.respuesta_por_faq import RespuestaPorFAQ
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.faq import FAQ
from cheatsheet.contexts.conversational.domain.uso_de_faq import ConteoDeUsos, UsoDeFAQ
from cheatsheet.contexts.conversational.infrastructure.canal import EmbeddingsSimulados
from cheatsheet.contexts.conversational.infrastructure.repositories import (
    RepositorioFAQPostgres,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.contexts.conversational.infrastructure.usos_de_faq import (
    RepositorioUsosDeFAQPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.zona_horaria import MesCalendario
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.conversational.application.dobles import MensajeriaEnMemoria
from tests.integracion.conftest import requiere_base
from tests.integracion.test_conversacional_postgres import Escenario, _escenario

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 15, 15, 0, tzinfo=UTC)
TELEFONO = "5491112345678"

Sesiones = async_sessionmaker[AsyncSession]


async def _con_faq(
    engine_dueno: AsyncEngine, sesiones: Sesiones, **cambios: object
) -> tuple[Escenario, FAQ]:
    """Un escenario con una FAQ ya guardada. Devuelve `(escenario, faq)`."""
    escenario = await _escenario(engine_dueno, sesiones)
    faq = escenario.faq("¿Cuánto sale un corte?", "Sale $8000.")
    for campo, valor in cambios.items():
        setattr(faq, campo, valor)
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioFAQPostgres(sesion).agregar(faq)
    return escenario, faq


async def _usar(
    sesiones: Sesiones,
    escenario: Escenario,
    faq_id: uuid.UUID,
    cuando: datetime,
    *,
    externo_id: str | None = None,
) -> uuid.UUID:
    """Un mensaje saliente y el uso que lo cita, en una transacción. Devuelve el `mensaje_id`."""
    mensaje = escenario.mensaje(externo_id=externo_id or f"wamid-{uuid.uuid4()}")
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioMensajePostgres(sesion).agregar(mensaje)
        await RepositorioUsosDeFAQPostgres(sesion).registrar(
            UsoDeFAQ(
                id=uuid.uuid4(),
                empresa_id=escenario.empresa_id,
                faq_id=faq_id,
                mensaje_id=mensaje.id,
                usado_en=cuando,
            )
        )
    return mensaje.id


async def _conteos(
    sesiones: Sesiones, escenario: Escenario, ahora: datetime = AHORA
) -> dict[uuid.UUID, ConteoDeUsos]:
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        return await RepositorioUsosDeFAQPostgres(sesion).conteos(MesCalendario.del_instante(ahora))


class TestElAltaNoTocaLaFAQ:
    async def test_responder_no_pisa_una_edicion_confirmada_en_medio(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 11. El administrador edita y confirma entre la búsqueda y el `COMMIT` del agente.

        Antes, el agente reescribía toda la fila de la FAQ con lo que había leído y la edición
        se perdía. Ahora solo inserta una fila en `faq_uso`.
        """
        escenario, faq = await _con_faq(engine_dueno, sesiones)
        embeddings = EmbeddingsSimulados()
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioFAQPostgres(sesion).guardar_vector(
                faq, await embeddings.vectorizar(faq.pregunta)
            )

        async def editar_en_otra_sesion() -> None:
            async with sesion_de_empresa(sesiones, escenario.empresa_id) as otra:
                repositorio = RepositorioFAQPostgres(otra)
                editada = await repositorio.buscar_por_id(faq.id)
                assert editada is not None
                editada.editar(
                    pregunta="¿Cuánto cuesta cortarse?", respuesta="$9000", momento=AHORA
                )
                await repositorio.guardar(editada)

        class MensajeriaConEdicionEnMedio(MensajeriaEnMemoria):
            async def enviar(self, *, telefono: str, texto: str) -> str:
                await editar_en_otra_sesion()
                return await super().enviar(telefono=telefono, texto=texto)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            conversacion = escenario.hilo()
            contexto = ContextoDelMensaje(
                escenario.empresa_id, conversacion, escenario.cliente_id, TELEFONO, AHORA
            )
            respuesta = RespuestaPorFAQ(
                faqs=RepositorioFAQPostgres(sesion),
                usos=RepositorioUsosDeFAQPostgres(sesion),
                embeddings=embeddings,
                salida=SalidaAlCliente(
                    mensajes=RepositorioMensajePostgres(sesion),
                    mensajeria=MensajeriaConEdicionEnMedio(),
                ),
            )
            assert await respuesta.responder(contexto, faq.pregunta) == faq.respuesta

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            leida = await RepositorioFAQPostgres(sesion).buscar_por_id(faq.id)
        assert leida is not None
        assert (leida.pregunta, leida.respuesta) == ("¿Cuánto cuesta cortarse?", "$9000")
        assert (await _conteos(sesiones, escenario))[faq.id].este_mes == 1

    async def test_dos_respuestas_simultaneas_cuentan_dos(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 12. Hoy el equivalente con `guardar` pierde un incremento."""
        escenario, faq = await _con_faq(engine_dueno, sesiones)

        await asyncio.gather(
            _usar(sesiones, escenario, faq.id, AHORA), _usar(sesiones, escenario, faq.id, AHORA)
        )

        assert (await _conteos(sesiones, escenario))[faq.id].desde_el_seguimiento == 2

    async def test_registrar_dos_veces_el_mismo_mensaje_deja_un_uso(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """`ON CONFLICT (mensaje_id) DO NOTHING`: el alta es idempotente por mensaje."""
        escenario, faq = await _con_faq(engine_dueno, sesiones)
        mensaje_id = await _usar(sesiones, escenario, faq.id, AHORA)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioUsosDeFAQPostgres(sesion).registrar(
                UsoDeFAQ(uuid.uuid4(), escenario.empresa_id, faq.id, mensaje_id, AHORA)
            )

        assert (await _conteos(sesiones, escenario))[faq.id].desde_el_seguimiento == 1


class TestAislamiento:
    async def test_una_empresa_no_ve_ni_escribe_los_usos_de_otra(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 15. RLS: sin `app.current_empresa` de A, `faq_uso` de A no se lee ni se inserta."""
        una, faq = await _con_faq(engine_dueno, sesiones)
        otra = await _escenario(engine_dueno, sesiones)
        mensaje_id = await _usar(sesiones, una, faq.id, AHORA)

        async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
            cuantos = await sesion.execute(text("SELECT count(*) FROM faq_uso"))
            assert cuantos.scalar_one() == 0
            assert (
                await RepositorioUsosDeFAQPostgres(sesion).conteos(
                    MesCalendario.del_instante(AHORA)
                )
                == {}
            )

        with pytest.raises(DBAPIError):
            async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
                await RepositorioUsosDeFAQPostgres(sesion).registrar(
                    UsoDeFAQ(uuid.uuid4(), una.empresa_id, faq.id, mensaje_id, AHORA)
                )

    async def test_la_aplicacion_solo_puede_leer_e_insertar(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Solo-inserción, como `reembolso`: ni `UPDATE` ni `DELETE`."""
        escenario, faq = await _con_faq(engine_dueno, sesiones)
        await _usar(sesiones, escenario, faq.id, AHORA)

        for sentencia in ("UPDATE faq_uso SET usado_en = now()", "DELETE FROM faq_uso"):
            with pytest.raises(DBAPIError):
                async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                    await sesion.execute(text(sentencia))


class TestBorrarUnaFAQ:
    async def test_los_usos_de_una_faq_borrada_siguen_contando_para_la_empresa(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 16. `SET NULL` corre como el dueño de la tabla: la aplicación no tiene `UPDATE`."""
        escenario, borrada = await _con_faq(engine_dueno, sesiones)
        otra = escenario.faq("¿Aceptan tarjeta?", "Sí.")
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioFAQPostgres(sesion).agregar(otra)
        for _ in range(2):
            await _usar(sesiones, escenario, borrada.id, AHORA)
        await _usar(sesiones, escenario, otra.id, AHORA)

        async def participacion() -> tuple[int, int]:
            async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                repositorio = RepositorioUsosDeFAQPostgres(sesion)
                desde, hasta = AHORA - timedelta(days=1), AHORA + timedelta(days=1)
                return (
                    await repositorio.contar(desde=desde, hasta=hasta, faq_id=otra.id),
                    await repositorio.contar(desde=desde, hasta=hasta, faq_id=None),
                )

        antes = await participacion()
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioFAQPostgres(sesion).eliminar(borrada.id)
        despues = await participacion()

        assert antes == despues == (1, 3)
        assert list(await _conteos(sesiones, escenario)) == [otra.id]
        async with engine_dueno.connect() as conexion:
            sin_faq = await conexion.execute(
                text("SELECT count(*) FROM faq_uso WHERE empresa_id = :e AND faq_id IS NULL"),
                {"e": escenario.empresa_id},
            )
        assert sin_faq.scalar_one() == 2


class TestLosMeses:
    async def test_la_frontera_argentina_llega_bien_a_sql(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 17. `02:59Z` del 1/11 es octubre en Argentina; `03:00Z`, noviembre."""
        escenario, faq = await _con_faq(engine_dueno, sesiones)
        await _usar(sesiones, escenario, faq.id, datetime(2026, 11, 1, 2, 59, tzinfo=UTC))
        await _usar(sesiones, escenario, faq.id, datetime(2026, 11, 1, 3, 0, tzinfo=UTC))

        conteo = (await _conteos(sesiones, escenario, datetime(2026, 11, 15, tzinfo=UTC)))[faq.id]

        assert (conteo.este_mes, conteo.mes_anterior) == (1, 1)

    async def test_el_total_suma_la_linea_de_base_y_los_eventos(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 19. Migrada con 47 usos anteriores y 3 eventos: total 50, este mes 3."""
        escenario, faq = await _con_faq(engine_dueno, sesiones, usos_anteriores=47)
        for _ in range(3):
            await _usar(sesiones, escenario, faq.id, AHORA)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            (vista,) = await ListarFAQs(
                RepositorioFAQPostgres(sesion), RepositorioUsosDeFAQPostgres(sesion)
            ).ejecutar(ahora=AHORA)

        assert (vista.usos_total, vista.conteo.este_mes) == (50, 3)

    async def test_un_mes_vacio_y_una_empresa_sin_usos_dan_ceros(
        self, sesiones: Sesiones, engine_dueno: AsyncEngine
    ) -> None:
        """Caso 18. Sin eventos no hay filas: `ListarFAQs` los completa con ceros."""
        escenario, faq = await _con_faq(engine_dueno, sesiones)
        await _usar(sesiones, escenario, faq.id, AHORA - timedelta(days=40))

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            (vista,) = await ListarFAQs(
                RepositorioFAQPostgres(sesion), RepositorioUsosDeFAQPostgres(sesion)
            ).ejecutar(ahora=AHORA)

        assert (vista.conteo.este_mes, vista.conteo.mes_anterior) == (0, 1)
