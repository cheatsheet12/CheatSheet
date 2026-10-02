/**
 * @vitest-environment jsdom
 *
 * PAN-DSH-01 — Inicio como *página* (HU-E10-01 RN-06).
 *
 * Dos cosas son del servidor y se prueban acá: que el período viaja en la URL y de ahí a la
 * misma ruta que usa Reportes (así «las mismas cifras» vale por construcción), y que el
 * resumen de cobros reemplazó a la tarjeta «Cobros pendientes». El selector es un cliente
 * mínimo que sólo escribe la URL.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();
const replace = vi.fn();
const redirect = vi.fn(() => {
  throw new Error("REDIRECT");
});

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

vi.mock("next/navigation", () => ({
  redirect: () => redirect(),
  useRouter: () => ({ push: vi.fn(), replace }),
}));

const PanelHome = (await import("@/app/(panel)/panel/page")).default;
const { SelectorDePeriodoEnUrl } = await import("@/app/(panel)/panel/SelectorDePeriodoEnUrl");

const TABLERO = {
  desde: "2026-03-01",
  hasta: "2026-03-31",
  facturado: { valor: "12500.55", anterior: "10000.00", variacion: "25.0" },
  cobrado: { valor: "8000.00", anterior: "7111.00", variacion: "12.5" },
  turnos: { valor: "12", anterior: "10", variacion: "20.0" },
  operaciones: { valor: "340", anterior: "300", variacion: "13.3" },
  por_tipo: { FACTURA_B: "12500.55" },
  por_semana: { "2026-W10": "12500.55" },
  pendiente: "1500.00",
  en_mora: "500.00",
  tasa_de_cobro: "72.50",
  cobrado_por_semana: { "2026-W10": "8000.00" },
  cobros_por_estado: { APROBADO: { cantidad: 8, monto: "8000.00" } },
  sin_actividad: false,
};

function responderTablero(): void {
  llamarApi.mockImplementation(async (ruta: string) =>
    ruta.startsWith("/reporteria/tablero") ? TABLERO : { operaciones: [], total: 0 },
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PAN-DSH-01 · Inicio", () => {
  it("redirige sin sesión y no le pregunta nada al backend", async () => {
    leerClaims.mockReturnValue(null);

    await expect(PanelHome({ searchParams: {} })).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("muestra el resumen de cobros del mes en curso y el selector, sin «Cobros pendientes»", async () => {
    leerClaims.mockReturnValue({ rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" });
    responderTablero();

    const html = renderToString(await PanelHome({ searchParams: {} }));

    // Sin período en la URL pide la ruta pelada: el default «mes en curso» es del backend.
    expect(llamarApi).toHaveBeenCalledWith("/reporteria/tablero");
    expect(html).toContain("Cobros del período");
    expect(html).toContain("$ 8.000,00");
    expect(html).toContain("rep-variacion--sube");
    expect(html).toContain("$ 1.500,00");
    expect(html).toContain("$ 500,00");
    expect(html).toContain("72,50 %");
    expect(html).toContain("Desde");
    expect(html).toContain("Hasta");
    expect(html).not.toContain("Cobros pendientes");
  });

  it("con ?desde&hasta pide el tablero de ese período", async () => {
    leerClaims.mockReturnValue({ rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" });
    responderTablero();

    await PanelHome({ searchParams: { desde: "2026-02-01", hasta: "2026-02-28" } });

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/tablero?desde=2026-02-01&hasta=2026-02-28");
  });
});

describe("PAN-DSH-01 · el selector de período en la URL", () => {
  it("cambiar una fecha escribe desde y hasta en la URL", () => {
    render(
      <SelectorDePeriodoEnUrl desde="2026-03-01" hasta="2026-03-31" resumen="1/3/26 – 31/3/26" />,
    );

    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-02-01" } });

    expect(replace).toHaveBeenCalledWith("/panel?desde=2026-02-01&hasta=2026-03-31");
  });

  it("no toca la URL mientras falte una de las dos fechas", () => {
    render(
      <SelectorDePeriodoEnUrl desde="2026-03-01" hasta="2026-03-31" resumen="1/3/26 – 31/3/26" />,
    );

    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "" } });

    expect(replace).not.toHaveBeenCalled();
  });
});
