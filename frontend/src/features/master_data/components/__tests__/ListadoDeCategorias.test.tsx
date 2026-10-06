/**
 * @vitest-environment jsdom
 *
 * PAN-DM-03 (HU-E4-03).
 *
 * El test que más importa es el del borrado: es **el único de la aplicación**, y el cuarto
 * criterio de aceptación pide confirmación. Se comprueban los dos caminos, porque un
 * «cancelar» que igual borra sería el peor defecto posible de esta pantalla.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarCategorias = vi.fn();
const crearCategoria = vi.fn();
const editarCategoria = vi.fn();
const eliminarCategoria = vi.fn();

vi.mock("@/features/master_data/api/categoria", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/categoria")>(
    "@/features/master_data/api/categoria",
  );
  return {
    ...real,
    listarCategorias: (...args: unknown[]) => listarCategorias(...args),
    crearCategoria: (...args: unknown[]) => crearCategoria(...args),
    editarCategoria: (...args: unknown[]) => editarCategoria(...args),
    eliminarCategoria: (...args: unknown[]) => eliminarCategoria(...args),
  };
});

import type { Categoria, ListadoDeCategoriasRespuesta as Listado } from "@/features/master_data";
import { ErrorDeCategoria } from "@/features/master_data";

const { ListadoDeCategorias } = await import(
  "@/features/master_data/components/ListadoDeCategorias"
);

const VIP: Categoria = {
  id: "3f1c2b8e-0000-4000-8000-000000000030",
  nombre: "VIP",
  aplica_a: "AMBOS",
};

const INICIAL: Listado = { categorias: [VIP] };

beforeAll(() => {
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
  vi.unstubAllGlobals();
});

/** Abre el menú ⋯ de la primera fila: Editar y Eliminar viven ahí. */
function abrirMenu(): void {
  fireEvent.click(screen.getByRole("button", { name: /Más acciones para/ }));
}

describe("ListadoDeCategorias", () => {
  it("muestra el nombre y el ambito en palabras", () => {
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    const tabla = within(screen.getByRole("table"));
    expect(tabla.getByText("VIP")).toBeDefined();
    expect(tabla.getByText("Clientes y servicios")).toBeDefined();
  });

  it("no ofrece acciones a quien no puede escribir", () => {
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar={false} />);

    expect(screen.queryByRole("button", { name: "Nueva categoría" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Más acciones/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Eliminar" })).toBeNull();
  });

  it("eliminar pide confirmacion, y cancelar no borra nada", () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Eliminar" }));

    expect(eliminarCategoria).not.toHaveBeenCalled();
  });

  it("la confirmacion dice que los elementos pierden la etiqueta", () => {
    const confirmar = vi.fn().mockReturnValue(false);
    vi.stubGlobal("confirm", confirmar);
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Eliminar" }));

    const texto = String(confirmar.mock.calls[0]?.[0] ?? "");
    expect(texto).toContain("pierden");
    expect(texto).toContain("VIP");
  });

  it("confirmar borra y recarga", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    eliminarCategoria.mockResolvedValue(undefined);
    listarCategorias.mockResolvedValue({ categorias: [] });
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Eliminar" }));

    await waitFor(() => {
      expect(eliminarCategoria).toHaveBeenCalledWith(VIP.id);
    });
    await waitFor(() => {
      expect(screen.getByText("Todavía no creaste ninguna categoría.")).toBeDefined();
    });
  });

  it("el mensaje de nombre duplicado se muestra tal cual llega", async () => {
    crearCategoria.mockRejectedValue(
      new ErrorDeCategoria("Ya existe una categoria con ese nombre en este ambito."),
    );
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Nueva categoría" }));
    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "VIP" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear categoría" }));

    await waitFor(() => {
      expect(
        screen.getByText("Ya existe una categoria con ese nombre en este ambito."),
      ).toBeDefined();
    });
  });

  it("el filtro por ambito recarga el listado", async () => {
    listarCategorias.mockResolvedValue({ categorias: [] });
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    fireEvent.change(screen.getByLabelText(/Filtrar por ámbito/), { target: { value: "CLIENTE" } });

    await waitFor(() => {
      expect(listarCategorias).toHaveBeenCalledWith("CLIENTE");
    });
  });

  it("todos los ambitos no filtra por nada", async () => {
    listarCategorias.mockResolvedValue({ categorias: [] });
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    fireEvent.change(screen.getByLabelText(/Filtrar por ámbito/), { target: { value: "CLIENTE" } });
    await waitFor(() => expect(listarCategorias).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/Filtrar por ámbito/), { target: { value: "" } });

    await waitFor(() => {
      expect(listarCategorias).toHaveBeenLastCalledWith(undefined);
    });
  });

  it("editar precarga los datos", () => {
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    abrirMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Editar" }));

    expect((screen.getByLabelText(/^Nombre/) as HTMLInputElement).value).toBe("VIP");
    expect((screen.getByLabelText(/Se aplica a/) as HTMLSelectElement).value).toBe("AMBOS");
  });

  it("Eliminar y Editar están dentro del menú ⋯", () => {
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    expect(screen.queryByRole("menuitem", { name: "Eliminar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Más acciones para VIP" }));

    expect(screen.getByRole("menuitem", { name: "Editar" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "Eliminar" })).toBeDefined();
  });

  it("la búsqueda filtra por nombre sin pedir nada a la red", () => {
    const otra: Categoria = { ...VIP, id: "2", nombre: "Mayorista", aplica_a: "CLIENTE" };
    render(<ListadoDeCategorias inicial={{ categorias: [VIP, otra] }} puedeEditar />);
    expect(screen.getByText("2 categorías")).toBeDefined();

    fireEvent.change(screen.getByLabelText(/Buscar/), { target: { value: "mayo" } });

    expect(screen.getByText("1 categoría")).toBeDefined();
    expect(within(screen.getByRole("table")).queryByText("VIP")).toBeNull();
    expect(listarCategorias).not.toHaveBeenCalled();
  });

  it("una búsqueda sin resultados ofrece limpiar los filtros", () => {
    render(<ListadoDeCategorias inicial={INICIAL} puedeEditar />);

    fireEvent.change(screen.getByLabelText(/Buscar/), { target: { value: "zzz" } });

    expect(screen.getByText("Ninguna categoría coincide")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    expect(within(screen.getByRole("table")).getByText("VIP")).toBeDefined();
  });
});
