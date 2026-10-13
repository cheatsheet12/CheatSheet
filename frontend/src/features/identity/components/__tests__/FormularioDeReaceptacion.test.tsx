/**
 * @vitest-environment jsdom
 *
 * The re-acceptance screen (HU-E1-03 RN-03, HU-E1-08 RN-05; plan case 32): whoever owes a new
 * version sees what changed and has exactly two things to do, accept or sign out. Nothing
 * signs them out by itself.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

import type { PendienteLegal } from "../../api/cliente";
import { FormularioDeReaceptacion } from "../FormularioDeReaceptacion";

const PRIVACIDAD: PendienteLegal = {
  documento: "PRIVACIDAD",
  version: "1.2",
  vigente_desde: "2026-11-01",
  borrador: false,
};
const TERMINOS: PendienteLegal = {
  documento: "TERMINOS",
  version: "2.0",
  vigente_desde: "2026-11-01",
  borrador: true,
};

const fetchFalso = vi.fn();

beforeEach(() => {
  fetchFalso.mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchFalso);
});

afterEach(() => {
  cleanup();
  push.mockReset();
  refresh.mockReset();
  fetchFalso.mockReset();
  vi.unstubAllGlobals();
});

describe("FormularioDeReaceptacion", () => {
  it("ofrece solo «Aceptar» y «Cerrar sesión»", () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD, TERMINOS]} />);

    const botones = screen.getAllByRole("button").map((b) => b.textContent?.trim());
    expect(botones).toEqual(["Aceptar", "Cerrar sesión"]);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("dice qué cambió: documento, versión, vigencia y enlace al texto", () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD, TERMINOS]} />);

    const enlacePrivacidad = screen.getByRole("link", { name: /Política de Privacidad/ });
    const enlaceTerminos = screen.getByRole("link", { name: /Términos y Condiciones/ });
    expect(enlacePrivacidad.getAttribute("href")).toBe("/privacidad");
    expect(enlaceTerminos.getAttribute("href")).toBe("/terminos");
    expect(enlacePrivacidad.getAttribute("target")).toBe("_blank");
    expect(screen.getByText(/Versión 1\.2/)).toBeDefined();
    expect(screen.getByText(/Versión 2\.0/)).toBeDefined();
    expect(screen.getAllByText(/01\/11\/2026/)).toHaveLength(2);
  });

  it("marca como preliminar el texto que todavía es un borrador", () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD, TERMINOS]} />);

    expect(screen.getAllByText(/pendiente de validación legal/)).toHaveLength(1);
  });

  it("con solo la política pendiente no habla de los términos", () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD]} />);

    expect(screen.queryByRole("link", { name: /Términos y Condiciones/ })).toBeNull();
  });

  it("«Aceptar» manda cada documento con su versión y entra al panel", async () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD, TERMINOS]} />);

    fireEvent.click(screen.getByRole("button", { name: "Aceptar" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/panel"));
    const [ruta, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/legal/aceptaciones");
    expect(opciones.method).toBe("POST");
    expect(JSON.parse(String(opciones.body))).toEqual({
      documentos: [
        { documento: "PRIVACIDAD", version: "1.2" },
        { documento: "TERMINOS", version: "2.0" },
      ],
    });
  });

  it("si no puede aceptar lo dice y se queda, sin cerrar la sesión", async () => {
    fetchFalso.mockResolvedValue(
      new Response(JSON.stringify({ error: "VersionLegalDesactualizada" }), { status: 409 }),
    );
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD]} />);

    fireEvent.click(screen.getByRole("button", { name: "Aceptar" }));

    expect(await screen.findByRole("alert")).toBeDefined();
    expect(screen.getByText(/Actualizamos los textos legales/)).toBeDefined();
    expect(push).not.toHaveBeenCalled();
    expect(fetchFalso).toHaveBeenCalledTimes(1);
  });

  it("un rol sin permiso para los términos recibe el mensaje de permiso", async () => {
    fetchFalso.mockResolvedValue(
      new Response(JSON.stringify({ error: "PermisoDenegado" }), { status: 403 }),
    );
    render(<FormularioDeReaceptacion pendientes={[TERMINOS]} />);

    fireEvent.click(screen.getByRole("button", { name: "Aceptar" }));

    expect(await screen.findByText("Tu rol no permite esta acción.")).toBeDefined();
  });

  it("«Cerrar sesión» cierra la sesión y vuelve al ingreso", async () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD]} />);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
    expect(fetchFalso).toHaveBeenCalledWith("/api/auth/logout", { method: "POST" });
  });

  it("no cierra la sesión por su cuenta (decisión 7)", () => {
    render(<FormularioDeReaceptacion pendientes={[PRIVACIDAD]} />);

    expect(fetchFalso).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
