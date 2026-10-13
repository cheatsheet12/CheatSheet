/**
 * @vitest-environment jsdom
 *
 * Corregir una fila que falló, desde el detalle de la carga.
 *
 * Lo que importa: el editor muestra **los valores del archivo** y **el motivo**; lo que se edita es
 * lo que se manda; un rechazo del servidor se muestra **sin cerrar el editor** (para corregir de
 * nuevo); y sólo un éxito avisa a la pantalla, con el detalle actualizado.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const verFilaConError = vi.fn();
const corregirFila = vi.fn();

vi.mock("@/features/spreadsheet_sync/api/planilla", async () => {
  const real = await vi.importActual<typeof import("@/features/spreadsheet_sync/api/planilla")>(
    "@/features/spreadsheet_sync/api/planilla",
  );
  return {
    ...real,
    verFilaConError: (...args: unknown[]) => verFilaConError(...args),
    corregirFila: (...args: unknown[]) => corregirFila(...args),
  };
});

import { ErrorDePlanilla } from "@/features/spreadsheet_sync";
import type { DetalleDeCargaRespuesta } from "@/features/spreadsheet_sync";

const { CorreccionDeFila } = await import(
  "@/features/spreadsheet_sync/components/CorreccionDeFila"
);

const FILA = {
  numero_fila: 5,
  motivo: "El digito verificador del CUIT no es correcto",
  campos: [
    { atributo: "nombre", valor: "Heladería Polo Norte" },
    { atributo: "cuit", valor: "20-11111111-1" },
    { atributo: "contacto_email", valor: "" },
  ],
};

const DETALLE: DetalleDeCargaRespuesta = {
  carga: {
    id: "c1",
    estado: "CON_ERRORES",
    filas_totales: 6,
    filas_ok: 4,
    filas_error: 2,
    es_reproceso: false,
    created_at: "2026-10-06T11:07:00Z",
  },
  errores: [{ numero_fila: 5, motivo: "x", corregida: true }],
  puede_reprocesar: true,
};

beforeAll(() => {
  // `Modal` es un `<dialog>` nativo y jsdom no implementa `showModal`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function montar(numeroFila: number | null = 5) {
  const alCerrar = vi.fn();
  const alCorregir = vi.fn();
  render(
    <CorreccionDeFila
      cargaId="c1"
      numeroFila={numeroFila}
      alCerrar={alCerrar}
      alCorregir={alCorregir}
    />,
  );
  return { alCerrar, alCorregir };
}

describe("CorreccionDeFila", () => {
  it("no pide nada con el editor cerrado", () => {
    montar(null);

    expect(verFilaConError).not.toHaveBeenCalled();
  });

  it("muestra el motivo y los valores del archivo, editables", async () => {
    verFilaConError.mockResolvedValue(FILA);
    montar();

    expect(await screen.findByDisplayValue("20-11111111-1")).toBeTruthy();
    expect(verFilaConError).toHaveBeenCalledWith("c1", 5);
    expect(screen.getByText("El digito verificador del CUIT no es correcto")).toBeTruthy();
    expect((screen.getByLabelText("Nombre / Razón social") as HTMLInputElement).value).toBe(
      "Heladería Polo Norte",
    );
    // Un campo vacío del archivo también se puede completar.
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("");
  });

  it("manda lo que se editó y avisa con el detalle actualizado", async () => {
    verFilaConError.mockResolvedValue(FILA);
    corregirFila.mockResolvedValue(DETALLE);
    const { alCorregir } = montar();
    const cuit = await screen.findByLabelText("CUIT");

    fireEvent.change(cuit, { target: { value: "20123456786" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "polo@norte.ar" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar y reimportar" }));

    await waitFor(() => {
      expect(corregirFila).toHaveBeenCalledWith("c1", 5, {
        nombre: "Heladería Polo Norte",
        cuit: "20123456786",
        contacto_email: "polo@norte.ar",
      });
    });
    await waitFor(() => {
      expect(alCorregir).toHaveBeenCalledWith(DETALLE, 5);
    });
  });

  it("un rechazo se muestra en el mismo editor y no avisa a la pantalla", async () => {
    verFilaConError.mockResolvedValue(FILA);
    corregirFila.mockRejectedValue(
      new ErrorDePlanilla("El digito verificador del CUIT no es correcto"),
    );
    const { alCorregir, alCerrar } = montar();
    await screen.findByLabelText("CUIT");

    fireEvent.click(screen.getByRole("button", { name: "Guardar y reimportar" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("digito verificador");
    // Sigue abierto, con lo que se tipeó, para corregir otra vez.
    expect(screen.getByLabelText("CUIT")).toBeTruthy();
    expect(alCorregir).not.toHaveBeenCalled();
    expect(alCerrar).not.toHaveBeenCalled();
  });

  it("escribir de nuevo limpia el rechazo anterior", async () => {
    verFilaConError.mockResolvedValue(FILA);
    corregirFila.mockRejectedValue(new ErrorDePlanilla("CUIT mal"));
    montar();
    await screen.findByLabelText("CUIT");
    fireEvent.click(screen.getByRole("button", { name: "Guardar y reimportar" }));
    await screen.findByRole("alert");

    fireEvent.change(screen.getByLabelText("CUIT"), { target: { value: "2012" } });

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("si la fila no se puede leer, lo dice", async () => {
    verFilaConError.mockRejectedValue(new ErrorDePlanilla("La fila 5 ya no está en el archivo"));
    montar();

    const alerta = await screen.findByRole("alert");

    expect(alerta.textContent).toContain("ya no está en el archivo");
    expect(screen.queryByRole("button", { name: "Guardar y reimportar" })).toBeNull();
  });

  it("Cancelar cierra sin mandar nada", async () => {
    verFilaConError.mockResolvedValue(FILA);
    const { alCerrar } = montar();
    await screen.findByLabelText("CUIT");

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(alCerrar).toHaveBeenCalled();
    expect(corregirFila).not.toHaveBeenCalled();
  });
});
