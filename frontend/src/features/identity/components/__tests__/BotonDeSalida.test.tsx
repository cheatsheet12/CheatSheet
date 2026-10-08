/**
 * @vitest-environment jsdom
 *
 * Signing out — the defect QA found: the route handler existed and nothing called it.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

const { BotonDeSalida } = await import("@/features/identity/components/BotonDeSalida");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const empujar = routerQueSuspende.push;
const refrescar = routerQueSuspende.refresh;

const fetchFalso = vi.fn();
vi.stubGlobal("fetch", fetchFalso);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  reiniciarRouter();
});

/** The call order matters: a `refresh()` queued behind the navigation is applied, one issued
 * before it is discarded by the router's action queue (Next 14.2.15, `action-queue.js`). */
function empujoAntesDeRefrescar(): boolean {
  const [empuje] = empujar.mock.invocationCallOrder;
  const [refresco] = refrescar.mock.invocationCallOrder;
  return empuje !== undefined && refresco !== undefined && empuje < refresco;
}

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
    expect(empujoAntesDeRefrescar()).toBe(true);
  });

  it("si la llamada falla, igual se sale: el handler ya borró las cookies", async () => {
    fetchFalso.mockRejectedValue(new Error("sin red"));
    render(<BotonDeSalida />);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/");
    });
    expect(refrescar).toHaveBeenCalled();
    expect(empujoAntesDeRefrescar()).toBe(true);
  });

  it("el botón queda ocupado hasta que se muestra la página de inicio", async () => {
    fetchFalso.mockResolvedValue({ ok: true, json: async () => ({ cerrada: true }) });
    render(
      <ArnesDeRouter>
        <BotonDeSalida />
      </ArnesDeRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/"));

    const boton = screen.getByRole("button", { name: "Saliendo…" }) as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
    fireEvent.click(boton);
    expect(fetchFalso).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
  });
});
