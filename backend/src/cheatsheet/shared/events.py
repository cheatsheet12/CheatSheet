"""Shared Kernel — domain events and the ports that carry them.

The Context Map declares `all → observability` as an Open Host Service: every
context publishes what it did, and `observability` persists it. The word that does
not appear in that sentence is *import*. Rule R3 forbids `billing/domain` from
reaching into `observability/domain`, and it should: an aggregate that knows who is
listening is an aggregate coupled to its audience.

So the traffic goes through here. A context builds an event out of Shared Kernel
types and hands it to a `PublicadorDeEventos`. Who subscribes is decided in the
composition root (`api/main.py`) and is invisible to the emitter.

`ocurrido_en` is a required field with no default on purpose: the emitter reads it
from its injected `Reloj` (see `shared/clock.py`), so a test can place an event
anywhere in time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from cheatsheet.shared.tenant import TenantId


@dataclass(frozen=True, kw_only=True)
class EventoDeDominio:
    """Something that happened in the business, stated in the past tense.

    `evento_id` is the identity of the *occurrence*, not of the entity, and it is what
    makes delivery idempotent: the same event delivered twice leaves one audit row
    (ADR-009).
    """

    evento_id: UUID
    tenant_id: TenantId
    ocurrido_en: datetime

    def __post_init__(self) -> None:
        if self.ocurrido_en.tzinfo is None:
            raise ValueError("ocurrido_en debe tener zona horaria (UTC)")


@runtime_checkable
class SuscriptorDeEventos(Protocol):
    """Something that reacts to an event. Failure here is the publisher's problem."""

    async def manejar(self, evento: EventoDeDominio) -> None: ...


class PublicadorDeEventos(Protocol):
    """The port an application service depends on to announce what it did."""

    async def publicar(self, evento: EventoDeDominio) -> None: ...
