"""Errors of `billing`.

Most derive from `EntradaInvalida` rather than `InvarianteViolada`, and that is not an
accident of inheritance: `api/main.py` maps the first to **422 and forwards its text**,
and the second to a generic 409 whose detail the BFF drops. Every message here is one a
story writes word for word — «Ya existe un punto de venta con ese numero.» — so it has to
reach the screen. Epic 4 recorded that seam in `TODO.md` after `ClienteDuplicado` lost its
message; this context is built knowing it.

`ComprobanteRechazadoPorArca` is the exception: it carries ARCA's own code and description,
which HU-E5-03 requires the screen to show verbatim.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class PuntoDeVentaDuplicado(EntradaInvalida):
    """HU-E5-05: «Ya existe un punto de venta con ese numero.»"""


class PuntoDeVentaNoHabilitado(EntradaInvalida):
    """HU-E5-05 RN-03: «El punto de venta no esta habilitado en ARCA.»"""


class PuntoDeVentaInexistente(EntradaInvalida):
    """Not this company's, or never existed. RLS makes those the same thing."""


class TipoDeComprobanteInvalido(EntradaInvalida):
    """HU-E5-03 RN-01: the pair of VAT conditions does not allow this type."""


class ComprobanteInexistente(EntradaInvalida):
    """The document is not this company's, or never existed."""


#: HU-E5-02: «El comprobante esta en Error» y por eso no se ofrece la descarga. Dicho como
#: instruccion y no como diagnostico, porque quien lo lee quiere saber que hacer.
MENSAJE_NO_DESCARGABLE = (
    "Este comprobante todavia no fue autorizado por ARCA, asi que no tiene "
    "representacion imprimible."
)


class ComprobanteNoDescargable(EntradaInvalida):
    """HU-E5-02 RN-03: solo un comprobante autorizado tiene PDF.

    Un PDF de algo que ARCA rechazo seria un papel identico a una factura que no lo es, y
    alguien se lo daria a un cliente.
    """


class ComprobanteNoAnulable(InvarianteViolada):
    """Only an authorised document can be reversed (HU-E5-04 RN-01)."""


class ArcaNoDisponible(EntradaInvalida):
    """ARCA could not be reached. Retryable, and the document stays where it was."""


class ComprobanteRechazadoPorArca(EntradaInvalida):
    """ARCA answered and said no. Carries its code and description (HU-E5-03).

    The story asks the screen to show «Error 10016: el comprobante no cumple la resolucion
    general vigente.» — ARCA's own words, not a translation of ours. Translating them would
    mean deciding what forty numeric codes mean, and being wrong about one of them in a
    message somebody takes to their accountant.
    """

    def __init__(self, codigo: str, descripcion: str) -> None:
        super().__init__(f"Error {codigo}: {descripcion}")
        self.codigo = codigo
        self.descripcion = descripcion
