"""Contestar con una FAQ (HU-E8-03) y registrar el uso (HU-E8-03 RN-04, ADR-0012).

Salió de `agente.py`, que ya no tenía lugar para el registro del uso. Mismo patrón que
`fuera_de_horario.py` y los pasos de turnos: el agente delega y este módulo conoce lo suyo.

**La respuesta es la que escribió la empresa, palabra por palabra.** El modelo no la reescribe
ni la resume: una FAQ es lo que el negocio decidió contestar, y dejar que un modelo la
parafrasee es dejar que cambie lo que la empresa dice.

**Un uso es una respuesta que salió.** Se registra después del envío y solo si el saliente
quedó `ENVIADO`; un fallo del canal deja el saliente `FALLIDO` y ningún uso. Además, no se
escribe la fila de la FAQ: el uso es una fila nueva en su propia tabla.
"""

from __future__ import annotations

from uuid import uuid4

from cheatsheet.contexts.conversational.application.contexto import ContextoDelMensaje
from cheatsheet.contexts.conversational.application.ports import (
    PortEmbeddings,
    PortRepositorioFAQ,
    PortUsosDeFAQ,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_OFRECER_ASESOR,
    EstadoEntrega,
)
from cheatsheet.contexts.conversational.domain.uso_de_faq import UsoDeFAQ


class RespuestaPorFAQ:
    """Busca la FAQ por significado (RN-02), con umbral (RN-03), y contesta con ella."""

    def __init__(
        self,
        *,
        faqs: PortRepositorioFAQ,
        usos: PortUsosDeFAQ,
        embeddings: PortEmbeddings,
        salida: SalidaAlCliente,
    ) -> None:
        self._faqs = faqs
        self._usos = usos
        self._embeddings = embeddings
        self._salida = salida

    async def responder(self, contexto: ContextoDelMensaje, texto: str) -> str | None:
        vector = await self._embeddings.vectorizar(texto)
        candidatas = await self._faqs.buscar_por_significado(vector, limite=1)
        mejor = candidatas[0] if candidatas else None
        if mejor is None or not mejor.alcanza:
            # RN-03: ninguna FAQ alcanza, se ofrece derivar.
            return await self._decir(contexto, MENSAJE_OFRECER_ASESOR)
        saliente = await self._salida.enviar(
            contexto.empresa_id,
            contexto.conversacion,
            contexto.telefono,
            mejor.faq.respuesta,
            contexto.ahora,
        )
        if saliente.estado_entrega is not EstadoEntrega.ENVIADO:
            return None
        await self._usos.registrar(
            UsoDeFAQ(
                id=uuid4(),
                empresa_id=contexto.empresa_id,
                faq_id=mejor.faq.id,
                mensaje_id=saliente.id,
                usado_en=contexto.ahora,
            )
        )
        return saliente.contenido

    async def _decir(self, contexto: ContextoDelMensaje, texto: str) -> str | None:
        return await self._salida.responder(
            contexto.empresa_id,
            contexto.conversacion,
            contexto.telefono,
            texto,
            contexto.ahora,
        )


__all__ = ["RespuestaPorFAQ"]
