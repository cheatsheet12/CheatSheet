/**
 * @vitest-environment jsdom
 *
 * Case 18 — the two consent boxes are separate, start unticked, and each blocks with its
 * own message (HU-E1-08 RN-03).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { CasillasLegales } from "../CasillasLegales";
import {
  MENSAJE_DE_PRIVACIDAD,
  MENSAJE_DE_TERMINOS,
  validarConsentimiento,
  type Aceptaciones,
  type ErroresDeConsentimiento,
} from "../../validacion/consentimiento";

afterEach(cleanup);

function Probador({
  errores = {},
  soloPrivacidad = false,
}: {
  readonly errores?: ErroresDeConsentimiento;
  readonly soloPrivacidad?: boolean;
}): JSX.Element {
  const [aceptaciones, setAceptaciones] = useState<Aceptaciones>({
    terminos: false,
    privacidad: false,
  });
  return (
    <CasillasLegales
      aceptaciones={aceptaciones}
      onCambio={setAceptaciones}
      errores={errores}
      soloPrivacidad={soloPrivacidad}
    />
  );
}

describe("CasillasLegales", () => {
  it("muestra dos casillas separadas y sin marcar, cada una con su enlace", () => {
    render(<Probador />);

    const terminos = screen.getByLabelText(/Términos y Condiciones/) as HTMLInputElement;
    const privacidad = screen.getByLabelText(/Política de Privacidad/) as HTMLInputElement;
    expect(terminos.type).toBe("checkbox");
    expect(privacidad.type).toBe("checkbox");
    expect(terminos.id).not.toBe(privacidad.id);
    expect(terminos.checked).toBe(false);
    expect(privacidad.checked).toBe(false);
    const hrefs = screen.getAllByRole("link").map((enlace) => enlace.getAttribute("href"));
    expect(hrefs).toEqual(["/terminos", "/privacidad"]);
  });

  it("marcar una no marca la otra", () => {
    render(<Probador />);

    fireEvent.click(screen.getByLabelText(/Política de Privacidad/));

    expect((screen.getByLabelText(/Política de Privacidad/) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByLabelText(/Términos y Condiciones/) as HTMLInputElement).checked).toBe(
      false,
    );
  });

  it("cada casilla muestra su propio mensaje de error", () => {
    render(<Probador errores={{ terminos: MENSAJE_DE_TERMINOS }} />);

    expect(screen.getByText(MENSAJE_DE_TERMINOS)).toBeDefined();
    expect(screen.queryByText(MENSAJE_DE_PRIVACIDAD)).toBeNull();
  });

  it("la invitación pide solo la política de privacidad", () => {
    render(<Probador soloPrivacidad />);

    expect(screen.getByLabelText(/Política de Privacidad/)).toBeDefined();
    expect(screen.queryByLabelText(/Términos y Condiciones/)).toBeNull();
  });
});

describe("validarConsentimiento", () => {
  it("sin marcar nada, cada casilla recibe su mensaje", () => {
    expect(validarConsentimiento({ terminos: false, privacidad: false }, true)).toEqual({
      terminos: "Debe aceptar los términos y condiciones para continuar.",
      privacidad: "Debe aceptar la política de privacidad para continuar.",
    });
  });

  it("solo falta la que no se marcó", () => {
    expect(validarConsentimiento({ terminos: true, privacidad: false }, true)).toEqual({
      privacidad: MENSAJE_DE_PRIVACIDAD,
    });
    expect(validarConsentimiento({ terminos: false, privacidad: true }, true)).toEqual({
      terminos: MENSAJE_DE_TERMINOS,
    });
  });

  it("quien acepta una invitación no debe los términos", () => {
    expect(validarConsentimiento({ terminos: false, privacidad: true }, false)).toEqual({});
    expect(validarConsentimiento({ terminos: false, privacidad: false }, false)).toEqual({
      privacidad: MENSAJE_DE_PRIVACIDAD,
    });
  });

  it("con las dos marcadas no hay errores", () => {
    expect(validarConsentimiento({ terminos: true, privacidad: true }, true)).toEqual({});
  });
});
