/**
 * @vitest-environment jsdom
 *
 * PAN-FAC-05 (HU-E5-05).
 *
 * Tres de los cinco criterios de aceptación de la historia son sobre lo que **se ve**, y
 * eso es lo que se prueba acá: el listado con número, descripción y estado; y las dos
 * frases de rechazo llegando a la pantalla sin que este componente las invente.
 *
 * El cuarto criterio —desactivar no borra los comprobantes— es del backend y ya está
 * probado contra PostgreSQL. Acá alcanza con verificar que la acción que se ofrece es
 * desactivar y no eliminar: un botón «Eliminar» sería una promesa que el backend no puede
 * cumplir, porque no tiene el permiso.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarPuntosDeVenta = vi.fn();
const registrarPuntoDeVenta = vi.fn();
const cambiarEstadoDePuntoDeVenta = vi.fn();

vi.mock("@/features/billing/api/puntoDeVenta", async () => {
  const real = await vi.importActual<typeof import("@/features/billing/api/puntoDeVenta")>(
    "@/features/billing/api/puntoDeVenta",
  );
  return {
    ...real,
    listarPuntosDeVenta: (...args: unknown[]) => listarPuntosDeVenta(...args),
    registrarPuntoDeVenta: (...args: unknown[]) => registrarPuntoDeVenta(...args),
    cambiarEstadoDePuntoDeVenta: (...args: unknown[]) => cambiarEstadoDePuntoDeVenta(...args),
  };
});

import { ErrorDePuntoDeVenta, MENSAJE_DUPLICADO, MENSAJE_NO_HABILITADO } from "@/features/billing";
import type { ListadoDePuntosDeVenta, PuntoDeVenta } from "@/features/billing";

const { PuntosDeVenta } = await import("@/features/billing/components/PuntosDeVenta");

const ACTIVO: PuntoDeVenta = {
  id: "p1",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: { FACTURA_B: 12 },
  created_at: "2026-09-07T12:00:00Z",
};

const INACTIVO: PuntoDeVenta = {
  id: "p2",
  numero: 23,
  descripcion: null,
  activo: false,
  numerador_por_tipo: {},
  created_at: "2026-09-07T12:00:00Z",
};

const INICIAL: ListadoDePuntosDeVenta = { puntos: [ACTIVO, INACTIVO] };

beforeAll(() => {
  // `Button variante="destructivo"` confirma con `window.confirm`, que jsdom no implementa.
  vi.stubGlobal("confirm", () => true);
  // `Modal` es un `<dialog>` nativo, y jsdom tampoco implementa `showModal`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function abrirAlta(): void {
  fireEvent.click(screen.getByRole("button", { name: "Agregar punto de venta" }));
}

describe("el listado", () => {
  it("muestra numero, descripcion y estado de cada punto", () => {
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    // Cuatro dígitos, como los imprime ARCA en el comprobante.
    expect(screen.getByText("0001")).toBeDefined();
    expect(screen.getByText("0023")).toBeDefined();
    expect(screen.getByText("Casa central")).toBeDefined();
    expect(screen.getByText("Activo")).toBeDefined();
    expect(screen.getByText("Inactivo")).toBeDefined();
  });

  it("muestra donde va la numeracion, y dice cuando no empezo", () => {
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    expect(screen.getByText("Factura B: 12")).toBeDefined();
    expect(screen.getByText("Sin emisiones")).toBeDefined();
  });

  it("ofrece desactivar y nunca eliminar", () => {
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    expect(screen.getByRole("button", { name: "Desactivar" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Activar" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /eliminar/i })).toBeNull();
  });
});

describe("los roles", () => {
  it("Solo Lectura ve el listado y ninguna accion", () => {
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar={false} />);

    expect(screen.getByText("Casa central")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Agregar punto de venta" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desactivar" })).toBeNull();
  });
});

describe("el alta", () => {
  it("muestra la frase de la historia cuando ARCA no tiene habilitado el punto", async () => {
    registrarPuntoDeVenta.mockRejectedValue(new ErrorDePuntoDeVenta(MENSAJE_NO_HABILITADO));
    render(<PuntosDeVenta inicial={{ puntos: [] }} puedeEditar />);

    abrirAlta();
    fireEvent.change(screen.getByLabelText("Numero"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    expect(await screen.findByText(MENSAJE_NO_HABILITADO)).toBeDefined();
    expect(listarPuntosDeVenta).not.toHaveBeenCalled();
  });

  it("muestra la frase de la historia cuando el numero ya existe", async () => {
    registrarPuntoDeVenta.mockRejectedValue(new ErrorDePuntoDeVenta(MENSAJE_DUPLICADO));
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    abrirAlta();
    fireEvent.change(screen.getByLabelText("Numero"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    expect(await screen.findByText(MENSAJE_DUPLICADO)).toBeDefined();
  });

  it("manda el numero como entero y la descripcion vacia como nula", async () => {
    registrarPuntoDeVenta.mockResolvedValue(ACTIVO);
    listarPuntosDeVenta.mockResolvedValue(INICIAL);
    render(<PuntosDeVenta inicial={{ puntos: [] }} puedeEditar />);

    abrirAlta();
    fireEvent.change(screen.getByLabelText("Numero"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    await waitFor(() =>
      expect(registrarPuntoDeVenta).toHaveBeenCalledWith({ numero: 4, descripcion: null }),
    );
  });
});

describe("el cambio de estado", () => {
  it("reactivar puede fallar porque el backend vuelve a preguntarle a ARCA", async () => {
    cambiarEstadoDePuntoDeVenta.mockRejectedValue(new ErrorDePuntoDeVenta(MENSAJE_NO_HABILITADO));
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Activar" }));

    expect(await screen.findByText(MENSAJE_NO_HABILITADO)).toBeDefined();
  });

  it("desactivar recarga el listado", async () => {
    cambiarEstadoDePuntoDeVenta.mockResolvedValue({ ...ACTIVO, activo: false });
    listarPuntosDeVenta.mockResolvedValue({ puntos: [{ ...ACTIVO, activo: false }, INACTIVO] });
    render(<PuntosDeVenta inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));

    await waitFor(() => expect(cambiarEstadoDePuntoDeVenta).toHaveBeenCalledWith("p1", false));
    await waitFor(() => expect(listarPuntosDeVenta).toHaveBeenCalled());
  });
});
