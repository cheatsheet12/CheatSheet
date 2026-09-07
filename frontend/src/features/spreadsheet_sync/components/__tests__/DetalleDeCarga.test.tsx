/**
 * @vitest-environment jsdom
 *
 * PAN-ING-03 (HU-E3-05, HU-E3-06).
 *
 * Lo que se prueba acá son los tres criterios de HU-E3-05: el resumen de filas, cada fila
 * fallida **con su número original** y su motivo, y la descarga del listado. Más el de
 * RN-04: Solo Lectura ve todo eso y no ve el botón de reprocesar.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const reprocesarCarga = vi.fn();
const verCarga = vi.fn();

vi.mock("@/features/spreadsheet_sync/api/planilla", async () => {
  const real =
    await vi.importActual<typeof import("@/features/spreadsheet_sync/api/planilla")>(
      "@/features/spreadsheet_sync/api/planilla",
    );
  return {
    ...real,
    reprocesarCarga: (...args: unknown[]) => reprocesarCarga(...args),
    verCarga: (...args: unknown[]) => verCarga(...args),
  };
});

import type { DetalleDeCargaRespuesta } from "@/features/spreadsheet_sync";
import { csvDeErrores } from "@/features/spreadsheet_sync";

const { DetalleDeCarga } = await import(
  "@/features/spreadsheet_sync/components/DetalleDeCarga"
);

const CON_ERRORES: DetalleDeCargaRespuesta = {
  carga: {
    id: "c1",
    estado: "CON_ERRORES",
    filas_totales: 100,
    filas_ok: 98,
    filas_error: 2,
    es_reproceso: false,
    created_at: "2026-09-07T12:00:00Z",
  },
  errores: [
    { numero_fila: 42, motivo: "CUIT invalido" },
    { numero_fila: 77, motivo: "La fila no tiene nombre" },
  ],
  puede_reprocesar: true,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DetalleDeCarga", () => {
  it("muestra el resumen de filas totales, procesadas y con error", () => {
    render(<DetalleDeCarga inicial={CON_ERRORES} />);

    expect(screen.getByText("100")).toBeTruthy();
    expect(screen.getByText("98")).toBeTruthy();
    expect(screen.getByText("Con errores")).toBeTruthy();
  });

  it("muestra cada fila fallida con su numero original y su motivo", () => {
    render(<DetalleDeCarga inicial={CON_ERRORES} />);

    // El numero que el usuario va a buscar en el margen de su propia planilla (RN-02).
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("CUIT invalido")).toBeTruthy();
    expect(screen.getByText("77")).toBeTruthy();
  });

  it("no ofrece reprocesar cuando el backend dice que no se puede", () => {
    // Cubre las dos razones a la vez: Solo Lectura (RN-04) y «no hay nada que corregir».
    render(<DetalleDeCarga inicial={{ ...CON_ERRORES, puede_reprocesar: false }} />);

    expect(screen.queryByText("Reprocesar las filas con error")).toBeNull();
    // Pero el detalle se ve igual: RN-04 le da derecho a mirar.
    expect(screen.getByText("CUIT invalido")).toBeTruthy();
  });

  it("reprocesa y avisa que el trabajo recien se encolo", async () => {
    reprocesarCarga.mockResolvedValue(undefined);
    verCarga.mockResolvedValue(CON_ERRORES);
    render(<DetalleDeCarga inicial={CON_ERRORES} />);

    fireEvent.click(screen.getByText("Reprocesar las filas con error"));

    await waitFor(() => {
      expect(reprocesarCarga).toHaveBeenCalledWith("c1");
      expect(screen.getByText(/Encolamos el reproceso/)).toBeTruthy();
    });
  });

  it("una carga sin errores no ofrece descargar nada", () => {
    render(
      <DetalleDeCarga
        inicial={{
          carga: { ...CON_ERRORES.carga, estado: "COMPLETADO", filas_error: 0, filas_ok: 100 },
          errores: [],
          puede_reprocesar: false,
        }}
      />,
    );

    expect(screen.queryByText("Descargar el listado de errores")).toBeNull();
    expect(screen.getByText("Procesado")).toBeTruthy();
  });

  it("dice cuando la carga es un reproceso de otra", () => {
    render(
      <DetalleDeCarga inicial={{ ...CON_ERRORES, carga: { ...CON_ERRORES.carga, es_reproceso: true } }} />,
    );

    expect(screen.getByText(/reproceso de una carga anterior/)).toBeTruthy();
  });
});

describe("csvDeErrores", () => {
  it("arma el listado que RN-03 deja descargar", () => {
    const csv = csvDeErrores(CON_ERRORES.errores);

    expect(csv.split("\n")[0]).toBe("fila,motivo");
    expect(csv).toContain('42,"CUIT invalido"');
  });

  it("escapa las comillas de un motivo", () => {
    const csv = csvDeErrores([{ numero_fila: 1, motivo: 'El campo "precio" no es un numero' }]);

    expect(csv).toContain('1,"El campo ""precio"" no es un numero"');
  });
});
