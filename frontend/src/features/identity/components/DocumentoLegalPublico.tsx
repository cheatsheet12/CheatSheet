/**
 * PAN-LEG-02 (terms) and PAN-LEG-01 (privacy): a public legal text with its version.
 *
 * Shows what HU-E1-03 RN-04 asks for — the version and the date it takes effect — and, while
 * the text is a draft, the mark that says so (HU-E1-08 RN-07). The draft mark is not
 * decoration: a text pending legal validation must never read as final.
 */

import { Alert } from "@/shared";

import type { DocumentoLegalPublicado } from "../api/cliente";
import { TITULOS_LEGALES, fechaLegible } from "./etiquetas-legales";
import { TextoLegal } from "./TextoLegal";

export function DocumentoLegalPublico({
  documento,
}: {
  readonly documento: DocumentoLegalPublicado;
}): JSX.Element {
  return (
    <article className="acc-tarjeta legal">
      <header className="legal__encabezado">
        <h1 className="acc-titulo">{TITULOS_LEGALES[documento.documento]}</h1>
        <p className="acc-sub">
          Versión {documento.version} · Vigente desde el {fechaLegible(documento.vigente_desde)}
        </p>
      </header>

      {documento.borrador && (
        <div className="legal__borrador">
          <Alert tono="advertencia">Versión preliminar, pendiente de validación legal.</Alert>
        </div>
      )}

      <TextoLegal texto={documento.texto} />
    </article>
  );
}
