/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-INT — cases 19 and 20 of the plan.
 *
 * The role check here is **cosmetic** and the test says so: what actually refuses an
 * Operador who tries to connect is the backend, and the application-layer test proves
 * that. What this file proves is the other half — that the panel does not offer an action
 * that is going to be rejected.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarIntegraciones = vi.fn();
const verificarIntegraciones = vi.fn();
const conectarIntegracion = vi.fn();

vi.mock("@/features/integrations/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/integrations/api/cliente")>(
    "@/features/integrations/api/cliente",
  );
  return {
    ...real,
    listarIntegraciones: (...args: unknown[]) => listarIntegraciones(...args),
    verificarIntegraciones: (...args: unknown[]) => verificarIntegraciones(...args),
    conectarIntegracion: (...args: unknown[]) => conectarIntegracion(...args),
  };
});

import type { Integracion, ListadoDeIntegraciones } from "@/features/integrations";

const { GrillaDeIntegraciones } = await import(
  "@/features/integrations/components/GrillaDeIntegraciones"
);

const ARCA: Integracion = {
  sistema: "ARCA",
  estado: "NO_CONECTADO",
  detalle: null,
  ambiente: null,
  verificado_en: null,
  configurada: false,
};

const RESTO: readonly Integracion[] = [
  {
    sistema: "MERCADOPAGO",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
  },
  {
    sistema: "WHATSAPP",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
  },
  {
    sistema: "GOOGLE_SHEETS",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
  },
];

const SIN_CONECTAR: ListadoDeIntegraciones = {
  integraciones: [ARCA, ...RESTO],
  verificado_en: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GrillaDeIntegraciones", () => {
  it("renderiza las cuatro tarjetas del prototipo", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("ARCA")).toBeTruthy();
    expect(screen.getByText("MercadoPago")).toBeTruthy();
    expect(screen.getByText("WhatsApp Business")).toBeTruthy();
    expect(screen.getByText("Google Sheets")).toBeTruthy();
    expect(screen.getAllByText("Sin conectar")).toHaveLength(4);
  });

  it("muestra el resumen de conectados y la marca de tiempo vacia", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("0 de 4 conectados")).toBeTruthy();
    expect(screen.getByText(/Última verificación: —/)).toBeTruthy();
  });

  it("verificar refresca los estados y la marca de tiempo", async () => {
    verificarIntegraciones.mockResolvedValue({
      integraciones: [
        {
          ...ARCA,
          estado: "CONECTADO",
          ambiente: "HOMOLOGACION",
          configurada: true,
          verificado_en: "2026-08-18T15:30:00Z",
        },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    });

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getByRole("button", { name: "Verificar estado" }));

    await waitFor(() => {
      expect(screen.getByText("Conectado")).toBeTruthy();
    });
    expect(screen.getByText("1 de 4 conectados")).toBeTruthy();
    // The exact rendering belongs to `formatearFechaHora`, which has its own test; what
    // matters here is that RN-03's timestamp stopped being empty.
    expect(screen.queryByText(/Última verificación: —/)).toBeNull();
  });

  it("muestra el detalle de una integracion degradada", () => {
    const degradada: ListadoDeIntegraciones = {
      integraciones: [
        { ...ARCA, estado: "ATENCION", detalle: "Servicio degradado", configurada: true },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    };

    render(<GrillaDeIntegraciones inicial={degradada} puedeConectar />);

    expect(screen.getByText("Atención")).toBeTruthy();
    expect(screen.getByText("Servicio degradado")).toBeTruthy();
  });

  it("una integracion ya configurada ofrece Reconectar y no Conectar", () => {
    const caida: ListadoDeIntegraciones = {
      integraciones: [{ ...ARCA, configurada: true }, ...RESTO],
      verificado_en: null,
    };

    render(<GrillaDeIntegraciones inicial={caida} puedeConectar />);

    expect(screen.getByRole("button", { name: "Reconectar" })).toBeTruthy();
  });

  it("el operador no ve ninguna accion de conectar", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar={false} />);

    expect(screen.queryByRole("button", { name: "Conectar" })).toBeNull();
    // The check is still there: HU-E2-05 names the Operador as an actor.
    expect(screen.getByRole("button", { name: "Verificar estado" })).toBeTruthy();
  });

  it("Google Sheets no es conectable en este epico", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("Disponible próximamente")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Conectar" })).toHaveLength(3);
  });

  it("conectar recarga el listado", async () => {
    conectarIntegracion.mockResolvedValue({});
    listarIntegraciones.mockResolvedValue({
      integraciones: [
        { ...ARCA, estado: "CONECTADO", ambiente: "HOMOLOGACION", configurada: true },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    });

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[0]!);

    await waitFor(() => {
      expect(screen.getByText("Conectado")).toBeTruthy();
    });
    expect(conectarIntegracion).toHaveBeenCalledWith("ARCA", expect.any(String));
    expect(screen.getByText("Homologación")).toBeTruthy();
  });

  it("un fallo de la verificacion se muestra y no rompe la pantalla", async () => {
    verificarIntegraciones.mockRejectedValue(new Error("El servicio no respondio"));

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getByRole("button", { name: "Verificar estado" }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("El servicio no respondio");
    });
    expect(screen.getAllByText("Sin conectar")).toHaveLength(4);
  });
});
