/**
 * @vitest-environment jsdom
 *
 * Signing out — the defect QA found: the route handler existed and nothing called it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const empujar = vi.fn();
const refrescar = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: empujar, refresh: refrescar }),
}));

const { BotonDeSalida } = await import("@/features/identity/components/BotonDeSalida");

const fetchFalso = vi.fn();
vi.stubGlobal("fetch", fetchFalso);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BotonDeSalida", () => {
  it("llama al handler que borra las cookies y vuelve al inicio", async () => {
    fetchFalso.mockResolvedValue({ ok: true, json: async () => ({ cerrada: true }) });
    render(<BotonDeSalida />);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/");
    });
    expect(fetchFalso).toHaveBeenCalledWith("/api/auth/logout", { method: "POST" });
    // Without the refresh, Next can serve the panel shell it already had — the person
    // sees their own data for a moment after signing out.
    expect(refrescar).toHaveBeenCalled();
  });

  it("si la llamada falla, igual se sale: el handler ya borró las cookies", async () => {
    fetchFalso.mockRejectedValue(new Error("sin red"));
    render(<BotonDeSalida />);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/");
    });
  });
});
