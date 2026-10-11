/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-RN — la tarjeta «Recordatorios de turno» (caso 8).
 *
 * Lo que se ve: sin regla, el mensaje y el default de 24 h; con regla, sus filas; agregar hasta
 * tres y no más; quitar; las frases de validación antes de mandar; el `PUT`; el mensaje del
 * backend; la advertencia de la regla desactivada; y que el Operador la vea sin poder editar.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const configurarAgenda = vi.fn();

vi.mock("@/features/business_config/api/agenda", async () => {
  const real = await vi.importActual<typeof import("@/features/business_config/api/agenda")>(
    "@/features/business_config/api/agenda",
  );
  return {
    ...real,
    configurarAgenda: (...args: unknown[]) => configurarAgenda(...args),
  };
});

import {
  ErrorDeAgenda,
  MENSAJE_AGENDA_DESACTIVADA,
  MENSAJE_HORAS_FUERA_DE_RANGO,
  MENSAJE_REPETIDOS,
  MENSAJE_SIN_AGENDA,
} from "../../api/agenda";
import type { AgendaGuardada } from "../../api/agenda";
import { AgendaDeNotificacion } from "../AgendaDeNotificacion";

const GUARDADA: AgendaGuardada = {
  reglaId: "rg1",
  activa: true,
  prioridad: 2,
  recordatorios: [{ horas_antes: 48 }, { horas_antes: 2 }],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const campo = (numero: number): HTMLInputElement =>
  screen.getByLabelText(`Horas antes del turno (recordatorio ${numero})`) as HTMLInputElement;

const botonGuardar = (): HTMLButtonElement =>
  screen.getByRole("button", { name: "Guardar" }) as HTMLButtonElement;

function escribir(numero: number, valor: string): void {
  fireEvent.change(campo(numero), { target: { value: valor } });
}

describe("sin regla configurada", () => {
  it("dice que rige el default y precarga un recordatorio a 24 horas", () => {
    render(<AgendaDeNotificacion inicial={null} puedeEditar />);

    expect(screen.getByText(MENSAJE_SIN_AGENDA)).toBeTruthy();
    expect(campo(1).value).toBe("24");
    expect(screen.queryByLabelText(/recordatorio 2/)).toBeNull();
  });

  it("guarda el default con prioridad 0 sólo cuando se lo piden", async () => {
    configurarAgenda.mockResolvedValue({ ...GUARDADA, recordatorios: [{ horas_antes: 24 }] });
    render(<AgendaDeNotificacion inicial={null} puedeEditar />);
    expect(configurarAgenda).not.toHaveBeenCalled();

    fireEvent.click(botonGuardar());

    await waitFor(() => expect(screen.getByText("Agenda guardada.")).toBeTruthy());
    expect(configurarAgenda).toHaveBeenCalledWith([{ horas_antes: 24 }], 0);
  });
});

describe("con regla configurada", () => {
  it("muestra una fila por recordatorio", () => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);

    expect(campo(1).value).toBe("48");
    expect(campo(2).value).toBe("2");
    expect(screen.queryByText(MENSAJE_SIN_AGENDA)).toBeNull();
  });

  it("agrega hasta tres recordatorios y después deshabilita «Agregar»", () => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);
    const agregar = screen.getByRole("button", { name: "Agregar recordatorio" });

    fireEvent.click(agregar);

    expect(campo(3).value).toBe("");
    expect((agregar as HTMLButtonElement).disabled).toBe(true);
    expect(botonGuardar().disabled).toBe(true);
  });

  it("quita una fila pero nunca la última", () => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);

    expect(screen.getByRole("button", { name: "Quitar recordatorio 2" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Quitar recordatorio 1" }));

    expect(campo(1).value).toBe("2");
    expect(screen.queryByRole("button", { name: /^Quitar/ })).toBeNull();
  });

  it("manda el PUT con las horas como números y conserva la prioridad", async () => {
    configurarAgenda.mockResolvedValue(GUARDADA);
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);
    escribir(2, "6");

    fireEvent.click(botonGuardar());

    await waitFor(() => expect(screen.getByText("Agenda guardada.")).toBeTruthy());
    expect(configurarAgenda).toHaveBeenCalledWith([{ horas_antes: 48 }, { horas_antes: 6 }], 2);
  });
});

describe("validación", () => {
  it.each(["0", "169", "-3", "2.5"])("«%s» muestra la frase del dominio", (valor) => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);

    escribir(2, valor);

    expect(screen.getByText(MENSAJE_HORAS_FUERA_DE_RANGO)).toBeTruthy();
    expect(botonGuardar().disabled).toBe(true);
  });

  it("dos recordatorios iguales muestran la frase de repetidos", () => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);

    escribir(2, "48");

    expect(screen.getAllByText(MENSAJE_REPETIDOS).length).toBeGreaterThan(0);
    expect(botonGuardar().disabled).toBe(true);
  });
});

describe("errores del backend", () => {
  it("muestra el mensaje del backend y no marca éxito", async () => {
    configurarAgenda.mockRejectedValue(new ErrorDeAgenda("Sólo el Administrador puede hacerlo."));
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar />);

    fireEvent.click(botonGuardar());

    await waitFor(() =>
      expect(screen.getByText("Sólo el Administrador puede hacerlo.")).toBeTruthy(),
    );
    expect(screen.queryByText("Agenda guardada.")).toBeNull();
  });
});

describe("regla desactivada", () => {
  it("avisa que los recordatorios están apagados y que guardar la reactiva", () => {
    render(<AgendaDeNotificacion inicial={{ ...GUARDADA, activa: false }} puedeEditar />);

    expect(screen.getByText(MENSAJE_AGENDA_DESACTIVADA)).toBeTruthy();
  });
});

describe("sin permiso de edición", () => {
  it("el Operador ve las filas deshabilitadas y ningún botón", () => {
    render(<AgendaDeNotificacion inicial={GUARDADA} puedeEditar={false} />);

    expect(campo(1).disabled).toBe(true);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
