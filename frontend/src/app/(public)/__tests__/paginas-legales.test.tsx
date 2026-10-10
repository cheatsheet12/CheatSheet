/**
 * @vitest-environment jsdom
 *
 * The public legal pages (HU-E1-03 RN-05: they never answer with an error; plan case 7).
 *
 * They are rendered on the server with hourly revalidation instead of `no-store`: if the
 * backend is down when Next revalidates, the last good copy keeps being served.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const llamarApi = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ llamarApi }));

import PaginaDePrivacidad from "../privacidad/page";
import PaginaDeTerminos from "../terminos/page";

afterEach(() => {
  cleanup();
  llamarApi.mockReset();
});

const publicado = (documento: string, version: string): object => ({
  documento,
  version,
  vigente_desde: "2026-10-10",
  borrador: true,
  texto: "## Apartado\n\nContenido.",
});

describe("páginas legales públicas", () => {
  it("/privacidad pide la política con revalidación y la muestra", async () => {
    llamarApi.mockResolvedValue(publicado("PRIVACIDAD", "1.0"));

    render(await PaginaDePrivacidad());

    expect(llamarApi).toHaveBeenCalledWith("/legal/privacidad", { revalidarCadaSegundos: 3600 });
    expect(screen.getByRole("heading", { level: 1, name: "Política de Privacidad" })).toBeTruthy();
    expect(screen.getByText(/Versión 1\.0/)).toBeTruthy();
  });

  it("/terminos pide los términos con revalidación y los muestra", async () => {
    llamarApi.mockResolvedValue(publicado("TERMINOS", "1.1"));

    render(await PaginaDeTerminos());

    expect(llamarApi).toHaveBeenCalledWith("/legal/terminos", { revalidarCadaSegundos: 3600 });
    expect(screen.getByRole("heading", { level: 1, name: "Términos y Condiciones" })).toBeTruthy();
    expect(screen.getByText("Versión preliminar, pendiente de validación legal.")).toBeTruthy();
  });

  it("si el backend falla propaga el error, para que Next conserve la última copia buena", async () => {
    llamarApi.mockRejectedValue(new Error("backend caído"));

    await expect(PaginaDePrivacidad()).rejects.toThrow("backend caído");
  });
});
