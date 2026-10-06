/**
 * @vitest-environment jsdom
 *
 * El control de clasificación (HU-E4-04).
 *
 * Lo que se prueba es el criterio de aceptación literal: «el sistema no ofrece esa
 * categoría para ese elemento». Y **la forma en que se cumple importa**: el componente no
 * filtra nada. Le pide al backend las del ámbito correcto, que ya incluye las de `AMBOS`.
 * Si algún día alguien agrega un `.filter()` acá, la regla pasaría a estar en dos lugares
 * y este comentario es lo que debería frenarlo.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarCategorias = vi.fn();

vi.mock("@/features/master_data/api/categoria", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/categoria")>(
    "@/features/master_data/api/categoria",
  );
  return { ...real, listarCategorias: (...args: unknown[]) => listarCategorias(...args) };
});

import type { Categoria } from "@/features/master_data";

const { SelectorDeCategorias } = await import(
  "@/features/master_data/components/SelectorDeCategorias"
);

const VIP: Categoria = { id: "c-1", nombre: "VIP", aplica_a: "CLIENTE" };
const PREMIUM: Categoria = { id: "c-2", nombre: "Premium", aplica_a: "AMBOS" };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SelectorDeCategorias", () => {
  it("le pide al backend las del ambito, y no filtra por su cuenta", async () => {
    listarCategorias.mockResolvedValue({ categorias: [VIP, PREMIUM] });

    render(
      <SelectorDeCategorias ambito="CLIENTE" asignadas={[]} onAlternar={async () => undefined} />,
    );

    await waitFor(() => {
      expect(listarCategorias).toHaveBeenCalledWith("CLIENTE");
    });
    // Las dos se muestran: AMBOS es asignable a un cliente y el backend ya la incluyo.
    expect(screen.getByLabelText("VIP")).toBeDefined();
    expect(screen.getByLabelText("Premium")).toBeDefined();
  });

  it("las ya asignadas aparecen tildadas", async () => {
    listarCategorias.mockResolvedValue({ categorias: [VIP, PREMIUM] });

    render(
      <SelectorDeCategorias
        ambito="CLIENTE"
        asignadas={[PREMIUM]}
        onAlternar={async () => undefined}
      />,
    );

    await waitFor(() => {
      expect((screen.getByLabelText("Premium") as HTMLInputElement).checked).toBe(true);
    });
    expect((screen.getByLabelText("VIP") as HTMLInputElement).checked).toBe(false);
  });

  it("tildar asigna y destildar quita", async () => {
    listarCategorias.mockResolvedValue({ categorias: [VIP] });
    const onAlternar = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <SelectorDeCategorias ambito="CLIENTE" asignadas={[]} onAlternar={onAlternar} />,
    );
    await waitFor(() => expect(screen.getByLabelText("VIP")).toBeDefined());

    fireEvent.click(screen.getByLabelText("VIP"));
    expect(onAlternar).toHaveBeenLastCalledWith("c-1", true);

    rerender(<SelectorDeCategorias ambito="CLIENTE" asignadas={[VIP]} onAlternar={onAlternar} />);
    fireEvent.click(screen.getByLabelText("VIP"));
    expect(onAlternar).toHaveBeenLastCalledWith("c-1", false);
  });

  it("sin categorias del ambito lo dice, en vez de mostrar una caja vacia", async () => {
    listarCategorias.mockResolvedValue({ categorias: [] });

    render(
      <SelectorDeCategorias ambito="SERVICIO" asignadas={[]} onAlternar={async () => undefined} />,
    );

    await waitFor(() => {
      expect(screen.getByText(/No hay categorias para este tipo de elemento/)).toBeDefined();
    });
  });

  it("si la carga falla lo dice y no rompe el formulario", async () => {
    listarCategorias.mockRejectedValue(new Error("sin red"));

    render(
      <SelectorDeCategorias ambito="CLIENTE" asignadas={[]} onAlternar={async () => undefined} />,
    );

    await waitFor(() => {
      expect(screen.getByText("No se pudieron cargar las categorias.")).toBeDefined();
    });
  });
});
