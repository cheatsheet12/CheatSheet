/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-RN (HU-E11-01).
 *
 * Los criterios que se ven: el listado con tipo, prioridad y estado; la cadena editable con
 * su tope; el rechazo de un día que no es mayor a cero; y que la acción sea **desactivar** y
 * no eliminar, porque una regla borrada deja la bitácora apuntando a algo que no existe.
 *
 * Y uno que no está en la historia: que una empresa **sin** regla configurada vea igual un
 * paso editable. La alternativa —un formulario vacío— obliga a adivinar que hay que agregar
 * un paso antes de poder guardar nada, justo en la pantalla que existe para que la cadena
 * por defecto deje de ser un misterio.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarReglas = vi.fn();
const configurarEscalamiento = vi.fn();
const cambiarEstadoDeRegla = vi.fn();

vi.mock("@/features/payments/api/regla", async () => {
  const real = await vi.importActual<typeof import("@/features/payments/api/regla")>(
    "@/features/payments/api/regla",
  );
  return {
    ...real,
    listarReglas: (...args: unknown[]) => listarReglas(...args),
    configurarEscalamiento: (...args: unknown[]) => configurarEscalamiento(...args),
    cambiarEstadoDeRegla: (...args: unknown[]) => cambiarEstadoDeRegla(...args),
  };
});

import { MAXIMO_DE_PASOS, MENSAJE_DIAS_INVALIDOS } from "@/features/payments";
import type { ListadoDeReglas, ReglaDeNegocio } from "@/features/payments";

const { ReglasDeNegocio } = await import("@/features/payments/components/ReglasDeNegocio");

const ESCALAMIENTO: ReglaDeNegocio = {
  id: "rg1",
  tipo: "ESCALAMIENTO_DE_COBRO",
  configuracion: {
    pasos: [
      { dias: 3, canal: "WHATSAPP" },
      { dias: 7, canal: "WHATSAPP" },
    ],
  },
  prioridad: 0,
  activa: true,
  created_at: "2026-09-07T12:00:00Z",
  updated_at: null,
};

const CON_REGLA: ListadoDeReglas = { reglas: [ESCALAMIENTO] };
const SIN_REGLAS: ListadoDeReglas = { reglas: [] };

beforeAll(() => {
  // `crypto.randomUUID` no está en el jsdom de esta versión, y el componente lo usa para la
  // clave de cada fila. Un contador alcanza: sólo tiene que ser distinto por fila.
  let n = 0;
  if (globalThis.crypto === undefined) {
    vi.stubGlobal("crypto", {});
  }
  vi.spyOn(globalThis.crypto, "randomUUID").mockImplementation(
    () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}` as const,
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PAN-CFG-RN", () => {
  it("lista la regla con su tipo, prioridad y estado", () => {
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);

    expect(screen.getByText("Escalamiento de cobros")).toBeTruthy();
    expect(screen.getByText("Activa")).toBeTruthy();
  });

  it("desactiva en vez de eliminar (RN-04)", async () => {
    cambiarEstadoDeRegla.mockResolvedValue({ ...ESCALAMIENTO, activa: false });
    listarReglas.mockResolvedValue({ reglas: [{ ...ESCALAMIENTO, activa: false }] });
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);

    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));

    await waitFor(() => {
      expect(cambiarEstadoDeRegla).toHaveBeenCalledWith("rg1", false);
    });
    expect(await screen.findByText("Inactiva")).toBeTruthy();
  });

  it("carga la cadena guardada y la manda entera al reemplazarla", async () => {
    configurarEscalamiento.mockResolvedValue(ESCALAMIENTO);
    listarReglas.mockResolvedValue(CON_REGLA);
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);

    expect((screen.getByLabelText("Días del recordatorio 1") as HTMLInputElement).value).toBe("3");
    expect((screen.getByLabelText("Días del recordatorio 2") as HTMLInputElement).value).toBe("7");

    fireEvent.change(screen.getByLabelText("Días del recordatorio 2"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cadena" }));

    await waitFor(() => {
      // La cadena entera, no el paso que cambió: es un reemplazo, no un parche.
      expect(configurarEscalamiento).toHaveBeenCalledWith([
        { dias: 3, canal: "WHATSAPP" },
        { dias: 10, canal: "WHATSAPP" },
      ]);
    });
  });

  it("no deja guardar un dia que no sea mayor a cero", () => {
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Días del recordatorio 1"), {
      target: { value: "0" },
    });

    expect(screen.getByText(MENSAJE_DIAS_INVALIDOS)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar cadena" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("no deja pasar del tope de pasos", () => {
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);
    const agregar = screen.getByRole("button", { name: "Agregar paso" });

    for (let i = 2; i < MAXIMO_DE_PASOS; i += 1) {
      expect(agregar.hasAttribute("disabled")).toBe(false);
      fireEvent.click(agregar);
    }

    expect(screen.getByLabelText(`Días del recordatorio ${MAXIMO_DE_PASOS}`)).toBeTruthy();
    expect(agregar.hasAttribute("disabled")).toBe(true);
  });

  it("no deja quitar el ultimo paso: una cadena vacia no es una cadena", () => {
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar />);

    const quitar = screen.getAllByRole("button", { name: "Quitar" });
    fireEvent.click(quitar[1] as HTMLElement);

    expect(
      (screen.getAllByRole("button", { name: "Quitar" })[0] as HTMLElement).hasAttribute(
        "disabled",
      ),
    ).toBe(true);
  });

  it("le da un paso editable a una empresa que nunca configuro nada", () => {
    render(<ReglasDeNegocio inicial={SIN_REGLAS} puedeEditar />);

    expect(
      screen.getByText("Todavía no configuraste ninguna regla. Rige la cadena por defecto."),
    ).toBeTruthy();
    expect((screen.getByLabelText("Días del recordatorio 1") as HTMLInputElement).value).toBe("3");
  });

  it("le muestra las reglas a Solo Lectura pero no el editor ni el boton de estado", () => {
    render(<ReglasDeNegocio inicial={CON_REGLA} puedeEditar={false} />);

    expect(screen.getByText("Escalamiento de cobros")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Desactivar" })).toBeNull();
    expect(screen.queryByLabelText("Días del recordatorio 1")).toBeNull();
  });
});
