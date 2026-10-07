/**
 * @vitest-environment jsdom
 *
 * Keeping the session alive (D-06): the refresh token lasted thirty days and nothing spent it.
 */

import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALO_DE_RENOVACION_MS, RenovadorDeSesion } from "../RenovadorDeSesion";

const pedir = vi.fn();
const irA = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  pedir.mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", pedir);
  Object.defineProperty(window, "location", { value: { assign: irA }, writable: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  pedir.mockReset();
  irA.mockReset();
});

function volverALaPestana(): void {
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("RenovadorDeSesion (D-06)", () => {
  it("renueva la sesión cada diez minutos mientras el panel está abierto", async () => {
    render(<RenovadorDeSesion />);
    expect(pedir).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(INTERVALO_DE_RENOVACION_MS);

    expect(pedir).toHaveBeenCalledWith("/api/auth/refresh", { method: "POST" });
  });

  it("al volver a la pestaña después de una pausa renueva en el acto", async () => {
    render(<RenovadorDeSesion />);
    vi.setSystemTime(Date.now() + INTERVALO_DE_RENOVACION_MS + 1);

    volverALaPestana();
    await vi.advanceTimersByTimeAsync(0);

    expect(pedir).toHaveBeenCalledTimes(1);
  });

  it("al volver enseguida no gasta una renovación", async () => {
    render(<RenovadorDeSesion />);

    volverALaPestana();
    await vi.advanceTimersByTimeAsync(0);

    expect(pedir).not.toHaveBeenCalled();
  });

  it("una renovación rechazada manda al login", async () => {
    pedir.mockResolvedValue(new Response("{}", { status: 401 }));
    render(<RenovadorDeSesion />);

    await vi.advanceTimersByTimeAsync(INTERVALO_DE_RENOVACION_MS);

    expect(irA).toHaveBeenCalledWith("/");
  });

  it("una falla de red no cierra la sesión", async () => {
    pedir.mockRejectedValue(new TypeError("sin red"));
    render(<RenovadorDeSesion />);

    await vi.advanceTimersByTimeAsync(INTERVALO_DE_RENOVACION_MS);

    expect(irA).not.toHaveBeenCalled();
  });
});
