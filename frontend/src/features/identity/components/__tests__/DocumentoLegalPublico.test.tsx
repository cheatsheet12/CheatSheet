/**
 * @vitest-environment jsdom
 *
 * `/terminos` and `/privacidad` show version, effective date and the draft mark
 * (HU-E1-03 RN-04, HU-E1-08 RN-07; plan case 7).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { DocumentoLegalPublicado } from "../../api/cliente";
import { DocumentoLegalPublico } from "../DocumentoLegalPublico";

afterEach(cleanup);

const PRIVACIDAD: DocumentoLegalPublicado = {
  documento: "PRIVACIDAD",
  version: "1.0",
  vigente_desde: "2026-10-10",
  borrador: true,
  texto: "## Finalidad del tratamiento\n\nPara prestar el servicio.",
};

describe("DocumentoLegalPublico", () => {
  it("muestra el título, la versión y la fecha de vigencia", () => {
    render(<DocumentoLegalPublico documento={PRIVACIDAD} />);

    expect(screen.getByRole("heading", { level: 1, name: "Política de Privacidad" })).toBeTruthy();
    expect(screen.getByText(/Versión 1\.0/)).toBeTruthy();
    expect(screen.getByText(/Vigente desde el 10\/10\/2026/)).toBeTruthy();
  });

  it("muestra la franja de borrador mientras la asesoría legal no valide el texto", () => {
    render(<DocumentoLegalPublico documento={PRIVACIDAD} />);

    expect(screen.getByText("Versión preliminar, pendiente de validación legal.")).toBeTruthy();
  });

  it("no muestra la franja cuando el texto ya fue validado", () => {
    render(<DocumentoLegalPublico documento={{ ...PRIVACIDAD, borrador: false }} />);

    expect(screen.queryByText(/pendiente de validación legal/)).toBeNull();
  });

  it("titula los términos con su nombre y dibuja el texto", () => {
    render(
      <DocumentoLegalPublico
        documento={{ ...PRIVACIDAD, documento: "TERMINOS", version: "1.1" }}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Términos y Condiciones" })).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 2, name: "Finalidad del tratamiento" }),
    ).toBeTruthy();
    expect(screen.getByText(/Versión 1\.1/)).toBeTruthy();
  });
});
