/**
 * @vitest-environment jsdom
 *
 * Caso 23 de la unidad `correccion-de-datos-existentes`: la sección «Formato de los datos
 * existentes» de PAN-DM-01.
 *
 * Lo que importa de esta pantalla es que **nada se escribe sin una confirmación**: aplicar
 * reescribe nombres y restaurar los devuelve. Se prueban los dos caminos de cada una, porque
 * un «cancelar» que igual escribe sería el peor defecto posible acá.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const informarCorreccion = vi.fn();
const aplicarCorreccion = vi.fn();
const listarCorridas = vi.fn();
const restaurarCorreccion = vi.fn();

vi.mock("@/features/master_data/api/correccion", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/correccion")>(
    "@/features/master_data/api/correccion",
  );
  return {
    ...real,
    informarCorreccion: (...args: unknown[]) => informarCorreccion(...args),
    aplicarCorreccion: (...args: unknown[]) => aplicarCorreccion(...args),
    listarCorridas: (...args: unknown[]) => listarCorridas(...args),
    restaurarCorreccion: (...args: unknown[]) => restaurarCorreccion(...args),
  };
});

import type { InformeDeCorreccion } from "@/features/master_data";
import { ErrorDeCorreccion } from "@/features/master_data";

const { CorreccionDeDatos } = await import("@/features/master_data/components/CorreccionDeDatos");

const CORRIDA_ID = "9d2f6c10-0000-4000-8000-000000000001";

const INFORME: InformeDeCorreccion = {
  a_corregir: { CLIENTE: 3, SERVICIO: 1, CATEGORIA: 0 },
  omitidos: { COLISION_DE_CATEGORIA: 2 },
  ejemplos: {
    CLIENTE: [{ antes: "JUAN PEREZ", despues: "Juan Perez" }],
    SERVICIO: [{ antes: "CORTE DE PELO", despues: "Corte de pelo" }],
  },
};

const INFORME_VACIO: InformeDeCorreccion = {
  a_corregir: { CLIENTE: 0, SERVICIO: 0, CATEGORIA: 0 },
  omitidos: {},
  ejemplos: {},
};

const CORRIDA = { corrida_id: CORRIDA_ID, creada_en: "2026-09-30T15:30:00+00:00", cantidad: 4 };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function revisar(): void {
  fireEvent.click(screen.getByRole("button", { name: "Revisar formato de los datos existentes" }));
}

describe("CorreccionDeDatos", () => {
  it("el informe muestra conteos, ejemplos y omitidos en palabras de usuario", async () => {
    listarCorridas.mockResolvedValue({ corridas: [] });
    informarCorreccion.mockResolvedValue(INFORME);
    render(<CorreccionDeDatos />);

    revisar();

    expect(await screen.findByText("JUAN PEREZ")).toBeDefined();
    expect(screen.getByText("Juan Perez")).toBeDefined();
    expect(screen.getByText("CORTE DE PELO")).toBeDefined();
    expect(screen.getByText(/3 clientes/)).toBeDefined();
    expect(screen.getByText(/2 omitidos/)).toBeDefined();
    expect(screen.getByText(/Ya existe otra categoría con ese nombre/)).toBeDefined();
    expect(screen.queryByText("COLISION_DE_CATEGORIA")).toBeNull();
  });

  it("aplicar pide confirmacion, y cancelar no escribe nada", async () => {
    listarCorridas.mockResolvedValue({ corridas: [] });
    informarCorreccion.mockResolvedValue(INFORME);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    render(<CorreccionDeDatos />);
    revisar();
    await screen.findByText("JUAN PEREZ");

    fireEvent.click(screen.getByRole("button", { name: "Aplicar corrección" }));

    expect(window.confirm).toHaveBeenCalledOnce();
    expect(aplicarCorreccion).not.toHaveBeenCalled();
  });

  it("al confirmar aplica, muestra el resultado y recarga las corridas", async () => {
    listarCorridas.mockResolvedValueOnce({ corridas: [] });
    listarCorridas.mockResolvedValueOnce({ corridas: [CORRIDA] });
    informarCorreccion.mockResolvedValue(INFORME);
    aplicarCorreccion.mockResolvedValue({
      corrida_id: CORRIDA_ID,
      conteos: { CLIENTE: 3, SERVICIO: 1, CATEGORIA: 0 },
    });
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    render(<CorreccionDeDatos />);
    revisar();
    await screen.findByText("JUAN PEREZ");

    fireEvent.click(screen.getByRole("button", { name: "Aplicar corrección" }));

    expect(await screen.findByText(/Se corrigieron 4 registros/)).toBeDefined();
    expect(aplicarCorreccion).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Restaurar" })).toBeDefined();
  });

  it("restaurar pide confirmacion y muestra restaurados y conservados", async () => {
    listarCorridas.mockResolvedValue({ corridas: [CORRIDA] });
    restaurarCorreccion.mockResolvedValue({ restaurados: 3, conservados: 1 });
    const confirmar = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.stubGlobal("confirm", confirmar);
    render(<CorreccionDeDatos />);
    const boton = await screen.findByRole("button", { name: "Restaurar" });

    fireEvent.click(boton);
    expect(restaurarCorreccion).not.toHaveBeenCalled();

    fireEvent.click(boton);
    expect(await screen.findByText(/Se restauraron 3 registros/)).toBeDefined();
    expect(screen.getByText(/1 se conservó porque se editó después/)).toBeDefined();
    expect(restaurarCorreccion).toHaveBeenCalledWith(CORRIDA_ID);
  });

  it("con cero para corregir dice que no hay datos y no ofrece aplicar", async () => {
    listarCorridas.mockResolvedValue({ corridas: [] });
    informarCorreccion.mockResolvedValue(INFORME_VACIO);
    render(<CorreccionDeDatos />);

    revisar();

    expect(await screen.findByText("No hay datos para corregir")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Aplicar corrección" })).toBeNull();
  });

  it.each([
    [403, /Solo un Administrador/],
    [409, /Ya hay una corrección en curso/],
    [422, /ya no existe/],
  ])("el error %i se muestra en palabras", async (estado, texto) => {
    listarCorridas.mockResolvedValue({ corridas: [CORRIDA] });
    restaurarCorreccion.mockRejectedValue(new ErrorDeCorreccion(estado, "detalle técnico"));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    render(<CorreccionDeDatos />);

    fireEvent.click(await screen.findByRole("button", { name: "Restaurar" }));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(texto));
  });
});
