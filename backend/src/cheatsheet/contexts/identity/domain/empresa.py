"""`Empresa` — the tenant itself (HU-E1-02, HU-E1-03).

**Why the fiscal columns are optional.** HU-E1-01 creates the account at step 1 and the
CUIT only arrives at step 2, so between the two there is a real, legitimate state: a
company that exists and is not yet usable. The DER marks `razon_social`, `cuit` and
`condicion_iva` NOT NULL, which does not admit that state — decision A of this unit's
plan resolves it by making the three nullable until onboarding completes.

`onboarding_completo` is **derived**, never stored. A boolean column would be a second
place where the truth lives, and the two would disagree the first time someone edited
one without the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cheatsheet.contexts.identity.domain.valores import (
    CUIT,
    CondicionIVA,
    Email,
    TerminosAceptados,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


@dataclass(slots=True)
class Empresa:
    """A company on the platform. Mutable: it has a lifecycle, unlike an audit record."""

    id: EmpresaId
    activa: bool = True
    razon_social: str | None = None
    cuit: CUIT | None = None
    condicion_iva: CondicionIVA | None = None
    #: HU-E1-02 RN-03 requires both, and the DER has neither (gap H7).
    nombre_responsable: str | None = None
    email_contacto: Email | None = None
    terminos: TerminosAceptados | None = None

    @property
    def datos_fiscales_completos(self) -> bool:
        return all(
            (
                self.razon_social,
                self.cuit,
                self.condicion_iva,
                self.nombre_responsable,
                self.email_contacto,
            )
        )

    @property
    def onboarding_completo(self) -> bool:
        """What HU-E1-02 RN-04 gates the dashboard on."""
        return self.datos_fiscales_completos and self.terminos is not None

    def completar_datos_fiscales(
        self,
        *,
        razon_social: str,
        cuit: CUIT,
        condicion_iva: CondicionIVA,
        nombre_responsable: str,
        email_contacto: Email,
    ) -> None:
        """Step 2 of the onboarding (HU-E1-02).

        Every field of RN-03 is mandatory here, together. Accepting a partial save would
        leave the company in a state the story does not describe and the panel cannot
        render.
        """
        if not razon_social.strip():
            raise EntradaInvalida("La razon social es obligatoria")
        if not nombre_responsable.strip():
            raise EntradaInvalida("El nombre del responsable es obligatorio")
        self.razon_social = razon_social.strip()
        self.cuit = cuit
        self.condicion_iva = condicion_iva
        self.nombre_responsable = nombre_responsable.strip()
        self.email_contacto = email_contacto

    def aceptar_terminos(self, version: str, momento: datetime) -> None:
        """HU-E1-03 RN-01: record which version, and when."""
        self.terminos = TerminosAceptados(version=version, fecha=momento)

    def debe_reaceptar_terminos(self, version_vigente: str) -> bool:
        """HU-E1-03 RN-03: a new version is asked for on the next sign-in."""
        return self.terminos is None or self.terminos.version != version_vigente

    def desactivar(self) -> None:
        self.activa = False

    def exigir_operativa(self) -> None:
        """Guard for anything that presupposes a usable company."""
        if not self.activa:
            raise InvarianteViolada("La empresa esta desactivada")
        if not self.onboarding_completo:
            raise InvarianteViolada(
                "La empresa no completo el onboarding: faltan datos fiscales o terminos"
            )
