"""El canal conversacional contra el motor.

**Dos cosas no se pueden probar con un doble**, y son las dos que este archivo prueba:

1. **La búsqueda por significado.** El operador `<=>` de `pgvector` y el orden que produce son
   del motor. Un doble que ordenara en Python probaría la imitación; y peor, pasaría el día que
   la consulta real estuviera mal escrita. Acá se guardan vectores de verdad, se busca de
   verdad, y se verifica **al revés**: una FAQ sin vector no aparece nunca, por más que su
   texto sea idéntico al de la pregunta.

2. **La idempotencia del webhook de Meta.** Es un índice único parcial, y lo que garantiza es
   que dos requests concurrentes no puedan escribir el mismo mensaje. Como en el épico 6 con
   `mp_payment_id`, el test se hace con dos transacciones y se verifica sacando el índice.

Más el aislamiento entre empresas sobre las cuatro tablas nuevas, que es lo que hace que la
conversación de un cliente no se filtre a otra PyME.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.dialogo import (
    Dialogo,
    OpcionDeHorario,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    PedidoDeTurno,
    ReferenciaDeDia,
)
from cheatsheet.contexts.conversational.infrastructure.canal import EmbeddingsSimulados
from cheatsheet.contexts.conversational.infrastructure.repositories import (
    RepositorioConversacionPostgres,
    RepositorioEscalamientoPostgres,
    RepositorioFAQPostgres,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'AGENTE', true, :ahora, :ahora)"
)
QUITAR_INDICE = text("DROP INDEX uq_mensaje_externo_id")
PONER_INDICE = text(
    "CREATE UNIQUE INDEX uq_mensaje_externo_id ON mensaje (empresa_id, externo_id) "
    "WHERE externo_id IS NOT NULL AND externo_id <> ''"
)


class Escenario:
    def __init__(self, empresa_id: EmpresaId, cliente_id: uuid.UUID) -> None:
        self.empresa_id = empresa_id
        self.cliente_id = cliente_id
        self.conversacion_id = uuid.uuid4()

    def hilo(self) -> Conversacion:
        return Conversacion(
            id=self.conversacion_id,
            empresa_id=self.empresa_id,
            cliente_id=self.cliente_id,
            created_at=AHORA,
        )

    def mensaje(self, *, externo_id: str, texto: str = "hola") -> Mensaje:
        return Mensaje(
            id=uuid.uuid4(),
            conversacion_id=self.conversacion_id,
            empresa_id=self.empresa_id,
            direccion=DireccionMensaje.ENTRANTE,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=texto,
            momento=AHORA,
            externo_id=externo_id,
        )

    def faq(self, pregunta: str, respuesta: str) -> FAQ:
        return FAQ(
            id=uuid.uuid4(),
            empresa_id=self.empresa_id,
            pregunta=pregunta,
            respuesta=respuesta,
            created_at=AHORA,
            updated_at=AHORA,
        )


async def _escenario(
    engine_dueno: AsyncEngine, sesiones: async_sessionmaker[AsyncSession]
) -> Escenario:
    empresa_id = EmpresaId(uuid.uuid4())
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    escenario = Escenario(empresa_id, cliente_id)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioConversacionPostgres(sesion).agregar(escenario.hilo())
    return escenario


class TestBusquedaPorSignificado:
    async def test_encuentra_la_faq_mas_parecida_y_ordena_por_distancia(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """El operador `<=>` de `pgvector`, contra el motor.

        Los vectores los produce el doble determinista: no entiende significados, así que lo
        que se afirma es la **mecánica** —que el vector viaje, que la consulta ordene, que la
        similitud vuelva— y no una capacidad semántica que este doble no tiene.
        """
        escenario = await _escenario(engine_dueno, sesiones)
        embeddings = EmbeddingsSimulados()
        precio = escenario.faq("¿Cuánto sale un corte?", "Sale $8000.")
        horario = escenario.faq("¿A qué hora abren?", "De 9 a 18.")

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioFAQPostgres(sesion)
            for faq in (precio, horario):
                await repositorio.agregar(faq)
                await repositorio.guardar_vector(faq, await embeddings.vectorizar(faq.pregunta))

        # Se busca con el vector exacto de una de las dos: tiene que salir primera, con
        # similitud 1 (o casi, por el redondeo del literal a ocho decimales).
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            encontradas = await RepositorioFAQPostgres(sesion).buscar_por_significado(
                await embeddings.vectorizar(precio.pregunta), limite=2
            )

        assert encontradas[0].faq.id == precio.id
        assert encontradas[0].similitud > 0.99
        assert encontradas[0].similitud > encontradas[1].similitud

    async def test_una_faq_sin_vector_no_aparece_nunca(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """La verificación al revés: **sin vector, no hay búsqueda por significado.**

        Es lo que hace que el test de arriba sea evidencia. Una FAQ guardada mientras el
        proveedor de embeddings estaba caído existe, se lee y se edita — pero no se encuentra,
        que es exactamente lo que la pantalla dice con `sin_indexar`.
        """
        escenario = await _escenario(engine_dueno, sesiones)
        embeddings = EmbeddingsSimulados()
        sin_vector = escenario.faq("¿Cuánto sale un corte?", "Sale $8000.")

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioFAQPostgres(sesion).agregar(sin_vector)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioFAQPostgres(sesion)
            encontradas = await repositorio.buscar_por_significado(
                await embeddings.vectorizar(sin_vector.pregunta)
            )
            pendientes = await repositorio.pendientes_de_indexar()

        assert encontradas == []
        # Y el barrido la ve, que es cómo se recupera.
        assert [una.id for una in pendientes] == [sin_vector.id]

    async def test_el_vector_sobrevive_al_viaje_y_marca_la_version_del_modelo(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """`embedding_modelo_version` es lo que permite migrar de modelo sin mezclar espacios."""
        escenario = await _escenario(engine_dueno, sesiones)
        embeddings = EmbeddingsSimulados()
        faq = escenario.faq("¿Aceptan tarjeta?", "Sí, débito y crédito.")

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioFAQPostgres(sesion)
            await repositorio.agregar(faq)
            faq.marcar_indexada(embeddings.version, AHORA)
            await repositorio.guardar_vector(faq, await embeddings.vectorizar(faq.pregunta))

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            leida = await RepositorioFAQPostgres(sesion).buscar_por_id(faq.id)

        assert leida is not None
        assert leida.embedding_modelo_version == embeddings.version
        assert not leida.embedding_obsoleto


class TestIdempotenciaDelWebhook:
    async def test_dos_llegadas_simultaneas_del_mismo_mensaje_dejan_una_fila(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """El índice único parcial, con dos transacciones de verdad.

        Meta reintenta y a veces las dos entregas se solapan. Sin el índice, las dos entrarían:
        ninguna ve a la otra hasta que la primera hace commit.
        """
        escenario = await _escenario(engine_dueno, sesiones)

        async def guardar() -> str:
            try:
                async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                    await RepositorioMensajePostgres(sesion).agregar(
                        escenario.mensaje(externo_id="wamid-repetido")
                    )
            except IntegrityError:
                return "rechazado"
            return "guardado"

        resultados = await asyncio.gather(guardar(), guardar())

        assert sorted(resultados) == ["guardado", "rechazado"]
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            cuantos = await sesion.execute(text("SELECT count(*) FROM mensaje"))
        assert cuantos.scalar_one() == 1

    async def test_sin_el_indice_las_dos_entran(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """La verificación al revés. El índice se repone al final, pase lo que pase."""
        escenario = await _escenario(engine_dueno, sesiones)

        async with engine_dueno.begin() as conexion:
            await conexion.execute(QUITAR_INDICE)
        try:
            for _ in range(2):
                async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                    await RepositorioMensajePostgres(sesion).agregar(
                        escenario.mensaje(externo_id="wamid-repetido")
                    )

            async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                cuantos = await sesion.execute(text("SELECT count(*) FROM mensaje"))
            assert cuantos.scalar_one() == 2
        finally:
            async with engine_dueno.begin() as conexion:
                await conexion.execute(text("DELETE FROM mensaje"))
                await conexion.execute(PONER_INDICE)

    async def test_dos_mensajes_nuestros_sin_id_externo_no_son_un_duplicado(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """El índice es **parcial** por esto.

        Un saliente que WhatsApp no llegó a aceptar no tiene id externo, y dos de ésos son dos
        mensajes distintos. Sin la cláusula `WHERE`, el segundo intento fallido de enviar
        rompería la transacción.
        """
        escenario = await _escenario(engine_dueno, sesiones)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioMensajePostgres(sesion)
            await repositorio.agregar(escenario.mensaje(externo_id=""))
            await repositorio.agregar(escenario.mensaje(externo_id=""))

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            cuantos = await sesion.execute(text("SELECT count(*) FROM mensaje"))
        assert cuantos.scalar_one() == 2

    async def test_el_estado_de_entrega_y_su_motivo_sobreviven_al_guardado(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """U7: el callback `failed` encuentra el mensaje por su `wamid` y deja el motivo."""
        escenario = await _escenario(engine_dueno, sesiones)
        saliente = escenario.mensaje(externo_id="wamid-saliente")
        saliente.direccion = DireccionMensaje.SALIENTE
        saliente.origen = OrigenDelMensaje.AGENTE
        saliente.estado_entrega = EstadoEntrega.ENVIADO
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioMensajePostgres(sesion).agregar(saliente)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioMensajePostgres(sesion)
            encontrado = await repositorio.buscar_por_externo_id("wamid-saliente")
            assert encontrado is not None
            encontrado.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131047")
            await repositorio.guardar(encontrado)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            leido = await RepositorioMensajePostgres(sesion).buscar_por_externo_id("wamid-saliente")
        assert leido is not None
        assert leido.estado_entrega is EstadoEntrega.FALLIDO
        assert leido.motivo_de_falla == "131047"

    async def test_el_wamid_de_otra_empresa_no_se_encuentra(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """U7, caso 10 del lado de `mensaje`: RLS hace que un `wamid` ajeno no exista."""
        una = await _escenario(engine_dueno, sesiones)
        otra = await _escenario(engine_dueno, sesiones)
        async with sesion_de_empresa(sesiones, una.empresa_id) as sesion:
            await RepositorioMensajePostgres(sesion).agregar(una.mensaje(externo_id="wamid-de-a"))

        async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
            ajeno = await RepositorioMensajePostgres(sesion).buscar_por_externo_id("wamid-de-a")

        assert ajeno is None


class TestAislamiento:
    async def test_una_empresa_no_ve_las_conversaciones_de_otra(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """RLS sobre las cuatro tablas nuevas.

        Una conversación de WhatsApp es lo que un cliente le contó a una PyME. Si se filtrara,
        se filtraría eso — y es la clase de dato que no se puede desfiltrar.
        """
        una = await _escenario(engine_dueno, sesiones)
        otra = await _escenario(engine_dueno, sesiones)

        async with sesion_de_empresa(sesiones, una.empresa_id) as sesion:
            await RepositorioMensajePostgres(sesion).agregar(una.mensaje(externo_id="wamid-a"))
            await RepositorioEscalamientoPostgres(sesion).agregar(
                Escalamiento(
                    id=uuid.uuid4(),
                    conversacion_id=una.conversacion_id,
                    empresa_id=una.empresa_id,
                    motivo=MOTIVO_BAJA_CONFIANZA,
                    created_at=AHORA,
                    updated_at=AHORA,
                )
            )
            await RepositorioFAQPostgres(sesion).agregar(
                una.faq("¿Cuánto sale?", "Depende del servicio.")
            )

        async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
            for tabla in ("mensaje", "escalamiento", "faq"):
                cuantos = await sesion.execute(text(f"SELECT count(*) FROM {tabla}"))  # noqa: S608
                assert cuantos.scalar_one() == 0, tabla
            # Su propia conversación sí la ve: una sola, la suya.
            hilos = await sesion.execute(text("SELECT count(*) FROM conversacion"))
            assert hilos.scalar_one() == 1

    async def test_el_escalamiento_abierto_es_lo_que_marca_el_hilo_como_escalado(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """HU-E9-01 RN-01, contra el motor: la condición se **deriva**, no se guarda."""
        escenario = await _escenario(engine_dueno, sesiones)
        escalamiento = Escalamiento(
            id=uuid.uuid4(),
            conversacion_id=escenario.conversacion_id,
            empresa_id=escenario.empresa_id,
            motivo=MOTIVO_BAJA_CONFIANZA,
            created_at=AHORA,
            updated_at=AHORA,
        )

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            await RepositorioEscalamientoPostgres(sesion).agregar(escalamiento)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioEscalamientoPostgres(sesion)
            abierto = await repositorio.abierto_de(escenario.conversacion_id)
            assert abierto is not None
            abierto.resolver(AHORA)
            await repositorio.guardar(abierto)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            despues = await RepositorioEscalamientoPostgres(sesion).abierto_de(
                escenario.conversacion_id
            )
            hilos = await RepositorioConversacionPostgres(sesion).listar(solo_escaladas=True)

        assert despues is None
        # Y el hilo deja de estar en la bandeja **sin que nadie le haya tocado un estado**.
        assert hilos == []


def un_dialogo() -> Dialogo:
    servicio_id = uuid.uuid4()
    return Dialogo.nuevo(
        PasoDelDialogo.ELEGIR_HORARIO,
        AHORA,
        opciones=(
            OpcionDeHorario(
                inicio=AHORA + timedelta(days=1),
                servicio_id=servicio_id,
                recursos=(uuid.uuid4(), uuid.uuid4()),
            ),
        ),
        servicio_id=servicio_id,
        pedido=PedidoDeTurno(
            accion=AccionDeTurno.RESERVAR,
            cuandos=(Cuando(ReferenciaDeDia.MANANA),),
            momento=MomentoDelDia.TARDE,
        ),
    )


class TestElDialogoEnLaBase:
    """T2, casos 31 y 35: el `Dialogo` viaja a una columna `jsonb` y vuelve igual."""

    async def test_el_dialogo_se_guarda_y_se_lee_igual(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        escenario = await _escenario(engine_dueno, sesiones)
        dialogo = un_dialogo()

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioConversacionPostgres(sesion)
            hilo = await repositorio.buscar_por_id(escenario.conversacion_id)
            assert hilo is not None
            hilo.abrir_dialogo(dialogo)
            await repositorio.guardar(hilo)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            leido = await RepositorioConversacionPostgres(sesion).buscar_por_id(
                escenario.conversacion_id
            )

        assert leido is not None
        assert leido.dialogo == dialogo

    async def test_cerrar_el_dialogo_lo_deja_en_null(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        escenario = await _escenario(engine_dueno, sesiones)
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioConversacionPostgres(sesion)
            hilo = await repositorio.buscar_por_id(escenario.conversacion_id)
            assert hilo is not None
            hilo.abrir_dialogo(un_dialogo())
            await repositorio.guardar(hilo)
            hilo.cerrar_dialogo()
            await repositorio.guardar(hilo)

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            crudo = await sesion.execute(text("SELECT dialogo FROM conversacion"))

        assert crudo.scalar_one() is None

    async def test_un_json_de_version_desconocida_se_lee_como_sin_dialogo(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """Caso 35: nunca se reserva sobre algo que no se pudo leer."""
        escenario = await _escenario(engine_dueno, sesiones)
        async with engine_dueno.begin() as conexion:
            await conexion.execute(
                text("UPDATE conversacion SET dialogo = CAST(:json AS jsonb) WHERE id = :id"),
                {
                    "json": '{"version": 99, "paso": "ELEGIR_HORARIO"}',
                    "id": escenario.conversacion_id,
                },
            )

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            leido = await RepositorioConversacionPostgres(sesion).buscar_por_id(
                escenario.conversacion_id
            )

        assert leido is not None
        assert leido.dialogo is None

    async def test_el_dialogo_de_una_empresa_no_lo_ve_otra(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """Caso 31: el diálogo vive bajo la RLS de `conversacion`."""
        una = await _escenario(engine_dueno, sesiones)
        otra = await _escenario(engine_dueno, sesiones)
        async with sesion_de_empresa(sesiones, una.empresa_id) as sesion:
            repositorio = RepositorioConversacionPostgres(sesion)
            hilo = await repositorio.buscar_por_id(una.conversacion_id)
            assert hilo is not None
            hilo.abrir_dialogo(un_dialogo())
            await repositorio.guardar(hilo)

        async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
            ajeno = await RepositorioConversacionPostgres(sesion).buscar_por_id(una.conversacion_id)
            filas = await sesion.execute(text("SELECT count(dialogo) FROM conversacion"))

        assert ajeno is None
        assert filas.scalar_one() == 0


class TestUnMensajePorVez:
    async def test_el_segundo_pedido_del_hilo_espera_al_primero(
        self, sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
    ) -> None:
        """T10: `abierta_de(bloquear=True)` es un `SELECT … FOR UPDATE` de la conversación.

        Con la fila tomada por una transacción, la segunda **espera** hasta que la primera termina
        y entonces lee lo que la primera dejó. Es lo que hace que «1» y «2», casi simultáneos, no
        reserven dos turnos: el segundo lee el diálogo ya consumido.
        """
        escenario = await _escenario(engine_dueno, sesiones)
        primera_tomo_el_hilo = asyncio.Event()
        puede_terminar = asyncio.Event()
        orden: list[str] = []

        async def primera() -> None:
            async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                repositorio = RepositorioConversacionPostgres(sesion)
                hilo = await repositorio.abierta_de(escenario.cliente_id, bloquear=True)
                assert hilo is not None
                hilo.abrir_dialogo(un_dialogo())
                await repositorio.guardar(hilo)
                primera_tomo_el_hilo.set()
                await puede_terminar.wait()
                orden.append("primera termina")

        async def segunda() -> Dialogo | None:
            await primera_tomo_el_hilo.wait()
            async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
                hilo = await RepositorioConversacionPostgres(sesion).abierta_de(
                    escenario.cliente_id, bloquear=True
                )
                orden.append("segunda lee")
                assert hilo is not None
                return hilo.dialogo

        tarea_primera = asyncio.create_task(primera())
        tarea_segunda = asyncio.create_task(segunda())
        await primera_tomo_el_hilo.wait()
        await asyncio.sleep(0.5)
        # La segunda sigue esperando: la fila está tomada.
        assert not tarea_segunda.done()
        puede_terminar.set()
        dialogo_que_leyo = await asyncio.wait_for(tarea_segunda, timeout=10)
        await tarea_primera

        assert orden == ["primera termina", "segunda lee"]
        assert dialogo_que_leyo is not None  # lo que la primera dejó, ya confirmado
