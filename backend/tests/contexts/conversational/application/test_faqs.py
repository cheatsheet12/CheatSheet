"""Los conteos de uso de las FAQ y el detalle antes/después de la edición (ADR-0012)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import FAQInexistente
from cheatsheet.contexts.conversational.application.faqs import ListarFAQs, VerUsoDeFAQ
from cheatsheet.contexts.conversational.domain.faq import FAQ
from cheatsheet.contexts.conversational.domain.uso_de_faq import MotivoSinComparacion, UsoDeFAQ
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.conversational.application.dobles import (
    RepositorioFAQEnMemoria,
    UsosDeFAQEnMemoria,
)

pytestmark = pytest.mark.asyncio

ART = timezone(timedelta(hours=-3))
EMPRESA = EmpresaId(uuid4())
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
