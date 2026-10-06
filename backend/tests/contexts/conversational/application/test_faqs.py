"""Los conteos de uso de las FAQ y el detalle antes/después de la edición (ADR-0012)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import FAQInexistente
from cheatsheet.contexts.conversational.application.faqs import (
    MOTIVO_SOLO_ADMIN,
    CrearFAQ,
    EditarFAQ,
    EliminarFAQ,
    FAQConUsos,
    ListarFAQs,
    VerUsoDeFAQ,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ
from cheatsheet.contexts.conversational.domain.uso_de_faq import MotivoSinComparacion, UsoDeFAQ
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.conversational.application.dobles import (
    EmbeddingsEnMemoria,
    PublicadorEnMemoria,
    RepositorioFAQEnMemoria,
    UsosDeFAQEnMemoria,
)

pytestmark = pytest.mark.asyncio

ART = timezone(timedelta(hours=-3))
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
ADMIN = RolUsuario.ADMINISTRADOR
AHORA = datetime(2026, 10, 15, 15, 0, tzinfo=UTC)


def una_faq(**cambios: object) -> FAQ:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "pregunta": "¿Cuánto sale un corte?",
        "respuesta": "Un corte sale $8000.",
        "created_at": AHORA - timedelta(days=100),
        "seguimiento_desde": AHORA - timedelta(days=100),
    }
    base.update(cambios)
    return FAQ(**base)  # type: ignore[arg-type]


async def usar(usos: UsosDeFAQEnMemoria, faq_id: UUID, cuando: datetime, veces: int = 1) -> None:
    for _ in range(veces):
        await usos.registrar(
            UsoDeFAQ(
                id=uuid4(),
                empresa_id=EMPRESA,
                faq_id=faq_id,
                mensaje_id=uuid4(),
                usado_en=cuando,
            )
        )


class TestListarFAQs:
    async def test_un_uso_del_ultimo_dia_cuenta_en_el_mes_argentino(self) -> None:
        """22:00 ART del 31/10: «Este mes» hasta medianoche, «Mes anterior» desde el día 1."""
        faq = una_faq()
        faqs, usos = RepositorioFAQEnMemoria(faq), UsosDeFAQEnMemoria()
        await usar(usos, faq.id, datetime(2026, 10, 31, 22, 0, tzinfo=ART))

        en_octubre = await ListarFAQs(faqs, usos).ejecutar(
            ahora=datetime(2026, 10, 31, 23, 0, tzinfo=ART)
        )
        en_noviembre = await ListarFAQs(faqs, usos).ejecutar(
            ahora=datetime(2026, 11, 1, 0, 30, tzinfo=ART)
        )

        assert (en_octubre[0].conteo.este_mes, en_octubre[0].conteo.mes_anterior) == (1, 0)
        assert (en_noviembre[0].conteo.este_mes, en_noviembre[0].conteo.mes_anterior) == (0, 1)

    async def test_mes_vacio_y_empresa_sin_usos_dan_ceros(self) -> None:
        con_usos_viejos = una_faq(usos_anteriores=47)
        sin_usos = una_faq()
        faqs, usos = RepositorioFAQEnMemoria(con_usos_viejos, sin_usos), UsosDeFAQEnMemoria()
        await usar(usos, con_usos_viejos.id, AHORA - timedelta(days=40), veces=2)

        vistas = {v.faq.id: v for v in await ListarFAQs(faqs, usos).ejecutar(ahora=AHORA)}

        antiguo = vistas[con_usos_viejos.id]
        assert (antiguo.conteo.este_mes, antiguo.conteo.mes_anterior) == (0, 2)
        assert antiguo.usos_total == 49
        assert vistas[sin_usos.id].usos_total == 0

    async def test_ordena_por_este_mes_y_despues_por_total(self) -> None:
        poco, mucho, viejo = una_faq(), una_faq(), una_faq(usos_anteriores=500)
        faqs, usos = RepositorioFAQEnMemoria(viejo, poco, mucho), UsosDeFAQEnMemoria()
        await usar(usos, mucho.id, AHORA, veces=3)
        await usar(usos, poco.id, AHORA, veces=1)

        orden = [v.faq.id for v in await ListarFAQs(faqs, usos).ejecutar(ahora=AHORA)]

        assert orden == [mucho.id, poco.id, viejo.id]


class TestVerUsoDeFAQ:
    async def test_participacion_antes_y_despues_de_la_ultima_edicion(self) -> None:
        editada = AHORA - timedelta(days=10)
        faq = una_faq(editada_en=editada)
        otra = uuid4()
        faqs, usos = RepositorioFAQEnMemoria(faq), UsosDeFAQEnMemoria()
        await usar(usos, faq.id, editada - timedelta(days=3), veces=2)
        await usar(usos, otra, editada - timedelta(days=3), veces=6)  # 2 de 8 antes
        await usar(usos, faq.id, editada + timedelta(days=2), veces=6)
        await usar(usos, otra, editada + timedelta(days=2), veces=6)  # 6 de 12 despues

        detalle = await VerUsoDeFAQ(faqs, usos).ejecutar(faq_id=faq.id, ahora=AHORA)

        assert detalle.motivo is None
        assert detalle.comparacion is not None
        assert detalle.comparacion.dias == 10
        assert detalle.comparacion.antes.porcentaje == Decimal("25.0")
        assert detalle.comparacion.despues.porcentaje == Decimal("50.0")
        assert detalle.faq.editada_en == editada

    async def test_un_lapso_sin_respuestas_con_faq_no_tiene_porcentaje(self) -> None:
        editada = AHORA - timedelta(days=10)
        faq = una_faq(editada_en=editada)
        faqs, usos = RepositorioFAQEnMemoria(faq), UsosDeFAQEnMemoria()
        await usar(usos, faq.id, editada - timedelta(days=1))

        detalle = await VerUsoDeFAQ(faqs, usos).ejecutar(faq_id=faq.id, ahora=AHORA)

        assert detalle.comparacion is not None
        assert detalle.comparacion.antes.porcentaje == Decimal("100.0")
        assert detalle.comparacion.despues.porcentaje is None

    async def test_una_faq_nunca_editada_dice_por_que_no_compara(self) -> None:
        faq = una_faq()
        faqs, usos = RepositorioFAQEnMemoria(faq), UsosDeFAQEnMemoria()

        detalle = await VerUsoDeFAQ(faqs, usos).ejecutar(faq_id=faq.id, ahora=AHORA)

        assert detalle.comparacion is None
        assert detalle.motivo is MotivoSinComparacion.SIN_EDICIONES

    async def test_faq_inexistente(self) -> None:
        with pytest.raises(FAQInexistente):
            await VerUsoDeFAQ(RepositorioFAQEnMemoria(), UsosDeFAQEnMemoria()).ejecutar(
                faq_id=uuid4(), ahora=AHORA
            )


class TestCrearFAQ:
    async def test_crea_con_los_tres_conteos_en_cero_y_la_deja_indexada(self) -> None:
        faqs, embeddings = RepositorioFAQEnMemoria(), EmbeddingsEnMemoria()
        publicador = PublicadorEnMemoria()

        faq = await CrearFAQ(faqs, embeddings, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=ADMIN,
            pregunta="  ¿Abren feriados?  ",
            respuesta=" No. ",
            ahora=AHORA,
        )

        assert (faq.pregunta, faq.respuesta) == ("¿Abren feriados?", "No.")
        assert faq.usos_anteriores == 0
        assert faq.editada_en is None
        vista = (await ListarFAQs(faqs, UsosDeFAQEnMemoria()).ejecutar(ahora=AHORA))[0]
        assert (vista.conteo.este_mes, vista.conteo.mes_anterior, vista.usos_total) == (0, 0, 0)
        assert embeddings.pedidos == ["¿Abren feriados?"]
        assert faq.id in faqs.vectores
        assert publicador.acciones == ["crear_faq"]

    @pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
    async def test_un_rol_que_no_es_administrador_no_crea_nada(self, rol: RolUsuario) -> None:
        faqs, publicador = RepositorioFAQEnMemoria(), PublicadorEnMemoria()

        with pytest.raises(EntradaInvalida, match=MOTIVO_SOLO_ADMIN):
            await CrearFAQ(faqs, EmbeddingsEnMemoria(), publicador).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=rol,
                pregunta="¿Hola?",
                respuesta="Hola.",
                ahora=AHORA,
            )

        assert faqs.faqs == {}
        assert publicador.eventos == []

    async def test_si_el_proveedor_de_embeddings_cae_la_guarda_sin_indexar(self) -> None:
        faqs = RepositorioFAQEnMemoria()

        faq = await CrearFAQ(faqs, EmbeddingsEnMemoria(cae=True), PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=ADMIN,
            pregunta="¿Hola?",
            respuesta="Hola.",
            ahora=AHORA,
        )

        assert faqs.faqs[faq.id].embedding_obsoleto is True
        assert faq.id not in faqs.vectores


async def editar(
    faq_id: UUID,
    *,
    pregunta: str,
    respuesta: str,
    faqs: RepositorioFAQEnMemoria,
    usos: UsosDeFAQEnMemoria | None = None,
    publicador: PublicadorEnMemoria | None = None,
    embeddings: EmbeddingsEnMemoria | None = None,
    rol: RolUsuario = ADMIN,
) -> FAQConUsos:
    caso = EditarFAQ(
        faqs,
        embeddings or EmbeddingsEnMemoria(),
        publicador or PublicadorEnMemoria(),
        usos or UsosDeFAQEnMemoria(),
    )
    return await caso.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        faq_id=faq_id,
        pregunta=pregunta,
        respuesta=respuesta,
        ahora=AHORA,
    )


class TestEditarFAQ:
    async def test_el_mismo_texto_con_espacios_no_mueve_editada_en_ni_reindexa(self) -> None:
        faq = una_faq()
        faq.marcar_indexada("doble-v1", AHORA)  # ya indexada: nada pendiente
        faqs, embeddings = RepositorioFAQEnMemoria(faq), EmbeddingsEnMemoria()

        vista = await editar(
            faq.id,
            pregunta=f"  {faq.pregunta} ",
            respuesta=f" {faq.respuesta}  ",
            faqs=faqs,
            embeddings=embeddings,
        )

        assert vista.faq.editada_en is None
        assert embeddings.pedidos == []

    async def test_cambiar_solo_la_respuesta_mueve_editada_en_y_trae_los_conteos(self) -> None:
        faq = una_faq()
        faq.marcar_indexada("doble-v1", AHORA)  # ya indexada: nada pendiente
        faqs, usos, embeddings = (
            RepositorioFAQEnMemoria(faq),
            UsosDeFAQEnMemoria(),
            EmbeddingsEnMemoria(),
        )
        await usar(usos, faq.id, AHORA - timedelta(days=1), veces=3)
        await usar(usos, faq.id, AHORA - timedelta(days=40), veces=2)

        vista = await editar(
            faq.id,
            pregunta=faq.pregunta,
            respuesta="Ahora sale $9000.",
            faqs=faqs,
            usos=usos,
            embeddings=embeddings,
        )

        assert vista.faq.editada_en == AHORA
        assert vista.faq.respuesta == "Ahora sale $9000."
        assert (vista.conteo.este_mes, vista.conteo.mes_anterior, vista.usos_total) == (3, 2, 5)
        assert embeddings.pedidos == []  # el vector se calcula sobre la pregunta

    async def test_cambiar_la_pregunta_reindexa_y_audita(self) -> None:
        faq = una_faq()
        faq.marcar_indexada("doble-v1", AHORA)  # ya indexada: nada pendiente
        faqs, publicador, embeddings = (
            RepositorioFAQEnMemoria(faq),
            PublicadorEnMemoria(),
            EmbeddingsEnMemoria(),
        )

        vista = await editar(
            faq.id,
            pregunta="¿Y un corte con barba?",
            respuesta=faq.respuesta,
            faqs=faqs,
            publicador=publicador,
            embeddings=embeddings,
        )

        assert embeddings.pedidos == ["¿Y un corte con barba?"]
        assert vista.faq.embedding_obsoleto is False
        assert faq.id in faqs.vectores
        assert publicador.acciones == ["editar_faq"]
        assert vista.conteo.este_mes == 0

    async def test_una_faq_inexistente_falla_sin_auditar(self) -> None:
        publicador = PublicadorEnMemoria()

        with pytest.raises(FAQInexistente):
            await editar(
                uuid4(),
                pregunta="¿Hola?",
                respuesta="Hola.",
                faqs=RepositorioFAQEnMemoria(),
                publicador=publicador,
            )

        assert publicador.eventos == []

    async def test_un_operador_no_edita_y_la_faq_queda_igual(self) -> None:
        faq = una_faq()
        faqs = RepositorioFAQEnMemoria(faq)

        with pytest.raises(EntradaInvalida, match=MOTIVO_SOLO_ADMIN):
            await editar(
                faq.id,
                pregunta="Otra",
                respuesta="Otra.",
                faqs=faqs,
                rol=RolUsuario.OPERADOR,
            )

        assert faqs.guardados == 0
        assert faq.respuesta == "Un corte sale $8000."

    async def test_un_texto_vacio_se_rechaza_sin_guardar(self) -> None:
        faq = una_faq()
        faqs = RepositorioFAQEnMemoria(faq)

        with pytest.raises(EntradaInvalida):
            await editar(faq.id, pregunta="   ", respuesta="x", faqs=faqs)

        assert faqs.guardados == 0


class TestEliminarFAQ:
    async def test_la_baja_es_real_e_inmediata_y_queda_auditada(self) -> None:
        faq = una_faq()
        faqs, publicador = RepositorioFAQEnMemoria(faq), PublicadorEnMemoria()
        faqs.vectores[faq.id] = [0.1]

        await EliminarFAQ(faqs, publicador).ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, rol=ADMIN, faq_id=faq.id, ahora=AHORA
        )

        assert await faqs.buscar_por_id(faq.id) is None
        assert faq.id not in faqs.vectores
        (evento,) = publicador.de_la_accion("eliminar_faq")
        assert evento.entidad_afectada == f"FAQ:{faq.id}"

    async def test_una_faq_inexistente_falla_sin_auditar(self) -> None:
        publicador = PublicadorEnMemoria()

        with pytest.raises(FAQInexistente):
            await EliminarFAQ(RepositorioFAQEnMemoria(), publicador).ejecutar(
                empresa_id=EMPRESA, usuario_id=USUARIO, rol=ADMIN, faq_id=uuid4(), ahora=AHORA
            )

        assert publicador.eventos == []

    @pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
    async def test_un_rol_que_no_es_administrador_no_borra(self, rol: RolUsuario) -> None:
        faq = una_faq()
        faqs = RepositorioFAQEnMemoria(faq)

        with pytest.raises(EntradaInvalida, match=MOTIVO_SOLO_ADMIN):
            await EliminarFAQ(faqs, PublicadorEnMemoria()).ejecutar(
                empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, faq_id=faq.id, ahora=AHORA
            )

        assert await faqs.buscar_por_id(faq.id) is faq
