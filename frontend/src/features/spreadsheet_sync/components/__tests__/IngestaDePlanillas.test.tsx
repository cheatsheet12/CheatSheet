/**
 * @vitest-environment jsdom
 *
 * PAN-ING-01 (HU-E2-04, HU-E3-03).
 *
 * Dos cosas se prueban acá y no en el cliente de API: que el rechazo **se vea**, y que un
 * rol que no puede escribir no reciba la zona de carga. La validación en sí ya tiene sus
 * propios tests; lo que falta comprobar es que su mensaje llega a la pantalla, que es
 * literalmente lo que dice el criterio de aceptación.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const listarPlanillas = vi.fn();
const subirPlanilla = vi.fn();
const desvincularPlanilla = vi.fn();
const iniciarVinculacionConGoogle = vi.fn();
const listarCargas = vi.fn();
const procesarPlanilla = vi.fn();

vi.mock("@/features/spreadsheet_sync/api/planilla", async () => {
  const real = await vi.importActual<typeof import("@/features/spreadsheet_sync/api/planilla")>(
    "@/features/spreadsheet_sync/api/planilla",
  );
  return {
    ...real,
    listarPlanillas: (...args: unknown[]) => listarPlanillas(...args),
    subirPlanilla: (...args: unknown[]) => subirPlanilla(...args),
    desvincularPlanilla: (...args: unknown[]) => desvincularPlanilla(...args),
    iniciarVinculacionConGoogle: (...args: unknown[]) => iniciarVinculacionConGoogle(...args),
    listarCargas: (...args: unknown[]) => listarCargas(...args),
    procesarPlanilla: (...args: unknown[]) => procesarPlanilla(...args),
  };
});

import type { Carga, ListadoDeVinculos, Vinculo } from "@/features/spreadsheet_sync";
import { ErrorDePlanilla, MENSAJE_ARCHIVO_DEMASIADO_GRANDE } from "@/features/spreadsheet_sync";

const { IngestaDePlanillas } = await import(
  "@/features/spreadsheet_sync/components/IngestaDePlanillas"
);

const VINCULO: Vinculo = {
  id: "v1",
  proveedor: "ARCHIVO",
  direccion: "SOLO_LECTURA",
  hoja_empresa: "clientes.xlsx",
  nombre_archivo: "clientes.xlsx",
  tamano_bytes: 2 * 1024 * 1024,
  pausado: false,
  motivo_de_pausa: null,
  escribe_de_vuelta: false,
  tiene_mapeo: false,
  ultima_lectura: null,
  created_at: "2026-09-07T12:00:00Z",
};

const INICIAL: ListadoDeVinculos = { vinculos: [VINCULO] };

const CARGA: Carga = {
  id: "c1",
  estado: "CON_ERRORES",
  filas_totales: 100,
  filas_ok: 98,
  filas_error: 2,
  es_reproceso: false,
  created_at: "2026-09-07T12:00:00Z",
};

beforeAll(() => {
  // `Button variante="destructivo"` confirma con `window.confirm`, que jsdom no implementa.
  vi.stubGlobal("confirm", () => true);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  // `refrescar()` relee las dos tablas de la pantalla. Sin este doble, cualquier accion
  // que refresque termina en el camino de error y el test afirma sobre el mensaje
  // equivocado.
  listarCargas.mockResolvedValue({ cargas: [] });
});

function archivo(nombre: string): File {
  return new File([new Uint8Array(10)], nombre);
}

describe("IngestaDePlanillas", () => {
  it("muestra las cargas recientes con su proveedor y su estado", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    expect(screen.getByText("clientes.xlsx")).toBeTruthy();
    expect(screen.getByText("Archivo subido")).toBeTruthy();
    // Sin mapeo confirmado todavía: eso es lo que el usuario tiene que hacer después.
    expect(screen.getByText("Falta mapear")).toBeTruthy();
    expect(screen.getByText("Solo lectura")).toBeTruthy();
  });

  it("no ofrece la zona de carga a un rol que no puede escribir", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar={false} />);

    expect(screen.queryByLabelText("Elegir una planilla")).toBeNull();
    expect(screen.queryByText("Desvincular")).toBeNull();
    // Pero sí ve el listado: HU-E3-05 RN-04 le da derecho a mirar.
    expect(screen.getByText("clientes.xlsx")).toBeTruthy();
  });

  it("muestra en pantalla el mensaje exacto con el que se rechaza un archivo", async () => {
    subirPlanilla.mockRejectedValue(new ErrorDePlanilla(MENSAJE_ARCHIVO_DEMASIADO_GRANDE));
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Elegir una planilla"), {
      target: { files: [archivo("grande.xlsx")] },
    });

    await waitFor(() => {
      expect(screen.getByText(MENSAJE_ARCHIVO_DEMASIADO_GRANDE)).toBeTruthy();
    });
  });

  it("refresca el listado despues de una carga exitosa", async () => {
    subirPlanilla.mockResolvedValue({ ...VINCULO, nombre_archivo: "nuevos.csv" });
    listarPlanillas.mockResolvedValue({
      vinculos: [{ ...VINCULO, id: "v2", nombre_archivo: "nuevos.csv" }],
    });
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Elegir una planilla"), {
      target: { files: [archivo("nuevos.csv")] },
    });

    await waitFor(() => {
      expect(listarPlanillas).toHaveBeenCalled();
      expect(screen.getByText("nuevos.csv")).toBeTruthy();
    });
  });

  it("desvincula y avisa que los datos importados se quedan", async () => {
    desvincularPlanilla.mockResolvedValue(undefined);
    listarPlanillas.mockResolvedValue({ vinculos: [] });
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.click(screen.getByText("Desvincular"));

    await waitFor(() => {
      expect(desvincularPlanilla).toHaveBeenCalledWith("v1");
      expect(screen.getByText(/siguen en el sistema/)).toBeTruthy();
    });
  });

  it("muestra las cargas recientes con sus tres contadores", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[CARGA]} puedeEditar />);

    // El criterio de HU-E3-03: «indicando la cantidad de filas validas y fallidas».
    expect(screen.getByText("Con errores")).toBeTruthy();
    expect(screen.getByText("98 de 100")).toBeTruthy();
    expect(screen.getByText("Ver detalle")).toBeTruthy();
  });

  it("encola el procesamiento y avisa que recien empieza", async () => {
    procesarPlanilla.mockResolvedValue(undefined);
    listarPlanillas.mockResolvedValue(INICIAL);
    render(
      <IngestaDePlanillas
        inicial={{ vinculos: [{ ...VINCULO, tiene_mapeo: true }] }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    fireEvent.click(screen.getByText("Procesar"));

    await waitFor(() => {
      expect(procesarPlanilla).toHaveBeenCalledWith("v1");
      // 202: aceptado, no hecho. Decir «procesada» seria mentir sobre una importacion que
      // recien arranca (HU-E3-03 RN-01).
      expect(screen.getByText(/Empezamos a procesar/)).toBeTruthy();
    });
  });

  it("no ofrece procesar una planilla sin mapeo confirmado", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    expect(screen.queryByText("Procesar")).toBeNull();
  });

  it("informa cuando una planilla esta pausada porque cambio su estructura", () => {
    render(
      <IngestaDePlanillas
        inicial={{
          vinculos: [{ ...VINCULO, pausado: true, motivo_de_pausa: "cambio la estructura" }],
        }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    expect(screen.getByText("Pausada")).toBeTruthy();
  });
});
