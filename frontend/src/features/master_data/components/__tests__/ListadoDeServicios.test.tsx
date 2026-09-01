/**
 * @vitest-environment jsdom
 *
 * PAN-DM-02 — las cinco columnas y el par agendable/duración.
 *
 * Lo que más importa acá es lo que la pantalla **no** hace: no calcula el precio con IVA.
 * Muestra el neto y la alícuota por separado, que es lo que pide el criterio de
 * aceptación, y multiplicar sería lógica de negocio en el frontend.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarServicios = vi.fn();
const crearServicio = vi.fn();
const editarServicio = vi.fn();
const cambiarEstadoDeServicio = vi.fn();

vi.mock("@/features/master_data/api/servicio", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/servicio")>(
    "@/features/master_data/api/servicio",
  );
  return {
    ...real,
    listarServicios: (...args: unknown[]) => listarServicios(...args),
    crearServicio: (...args: unknown[]) => crearServicio(...args),
    editarServicio: (...args: unknown[]) => editarServicio(...args),
    cambiarEstadoDeServicio: (...args: unknown[]) => cambiarEstadoDeServicio(...args),
  };
});

// Esta pantalla ahora también habla con el módulo de categorías: el filtro las lista y
// «Editar» pide las que el elemento ya tiene. Sin este doble, el test saldría a la red.
const listarCategorias = vi.fn().mockResolvedValue({ categorias: [] });
const categoriasDeServicio = vi.fn().mockResolvedValue([]);
const clasificarServicio = vi.fn().mockResolvedValue({ categorias: [] });

vi.mock("@/features/master_data/api/categoria", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/categoria")>(
    "@/features/master_data/api/categoria",
  );
  return {
    ...real,
    listarCategorias: (...args: unknown[]) => listarCategorias(...args),
    categoriasDeServicio: (...args: unknown[]) => categoriasDeServicio(...args),
    clasificarServicio: (...args: unknown[]) => clasificarServicio(...args),
  };
});

import type { ListadoDeServiciosRespuesta as Listado, Servicio } from "@/features/master_data";
import { ErrorDeServicio } from "@/features/master_data";

const { ListadoDeServicios } = await import("@/features/master_data/components/ListadoDeServicios");

const CORTE: Servicio = {
  id: "3f1c2b8e-0000-4000-8000-000000000020",
  nombre: "Corte de pelo",
  precio: "5000.00",
  alicuota_iva: "0.21",
  agendable: true,
  duracion_estandar_min: 45,
  origen: "PANEL",
  activo: true,
};

const INICIAL: Listado = { servicios: [CORTE], total: 1 };

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

describe("ListadoDeServicios", () => {
  it("muestra las cinco columnas del criterio de aceptacion", () => {
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    for (const titulo of ["Nombre", "Precio", "IVA", "Duracion", "Estado"]) {
      expect(screen.getByRole("columnheader", { name: titulo })).toBeDefined();
    }
    expect(screen.getByText("$ 5000.00")).toBeDefined();
    expect(screen.getByText("21%")).toBeDefined();
    expect(screen.getByText("45 min")).toBeDefined();
  });

  it("no muestra el precio con IVA calculado en ninguna parte", () => {
    // 5000 * 1.21 = 6050. Si aparece, alguien puso la multiplicacion en el panel.
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    expect(screen.queryByText(/6050/)).toBeNull();
  });

  it("un servicio no agendable no muestra duracion", () => {
    const shampoo: Servicio = {
      ...CORTE,
      nombre: "Shampoo",
      agendable: false,
      duracion_estandar_min: null,
    };

    render(<ListadoDeServicios inicial={{ servicios: [shampoo], total: 1 }} puedeEditar />);

    expect(screen.getByText("—")).toBeDefined();
  });

  it("muestra la alicuota reducida como 10,5%", () => {
    const reducido: Servicio = { ...CORTE, alicuota_iva: "0.105" };

    render(<ListadoDeServicios inicial={{ servicios: [reducido], total: 1 }} puedeEditar />);

    expect(screen.getByText("10,5%")).toBeDefined();
  });

  it("no ofrece acciones de escritura a quien no puede escribir", () => {
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar={false} />);

    expect(screen.queryByRole("button", { name: "Nuevo servicio" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
  });

  it("un servicio inactivo se ofrece para reactivar, nunca para borrar", () => {
    render(
      <ListadoDeServicios
        inicial={{ servicios: [{ ...CORTE, activo: false }], total: 1 }}
        puedeEditar
      />,
    );

    expect(screen.getByRole("button", { name: "Reactivar" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /elimina|borra/i })).toBeNull();
  });

  it("cada filtro recarga el listado con lo que el usuario eligio", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.change(screen.getByLabelText(/Buscar/), { target: { value: "corte" } });
    await waitFor(() => {
      expect(listarServicios).toHaveBeenCalledWith(expect.objectContaining({ texto: "corte" }));
    });

    fireEvent.change(screen.getByLabelText(/Agendables/), { target: { value: "true" } });
    await waitFor(() => {
      expect(listarServicios).toHaveBeenCalledWith(expect.objectContaining({ agendable: true }));
    });

    fireEvent.click(screen.getByLabelText(/Solo activos/));
    await waitFor(() => {
      expect(listarServicios).toHaveBeenCalledWith(expect.objectContaining({ soloActivos: true }));
    });
  });

  it("«agendables y no agendables» no filtra por false, filtra por nada", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.change(screen.getByLabelText(/Agendables/), { target: { value: "" } });

    await waitFor(() => {
      expect(listarServicios).toHaveBeenCalledWith(expect.objectContaining({ agendable: null }));
    });
  });

  it("desactivar pide confirmacion, y si se cancela no llama a la API", () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));

    expect(cambiarEstadoDeServicio).not.toHaveBeenCalled();
  });

  it("desactivar confirmado llama a la API y refresca", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    cambiarEstadoDeServicio.mockResolvedValue({ ...CORTE, activo: false });
    listarServicios.mockResolvedValue({ servicios: [{ ...CORTE, activo: false }], total: 1 });
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));

    await waitFor(() => {
      expect(cambiarEstadoDeServicio).toHaveBeenCalledWith(CORTE.id, false);
    });
    await waitFor(() => {
      expect(screen.getByText("Inactivo")).toBeDefined();
    });
  });

  it("el mensaje del backend se muestra tal cual", async () => {
    crearServicio.mockRejectedValue(new ErrorDeServicio("El precio debe ser mayor a cero."));
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Nuevo servicio" }));
    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Shampoo" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

    await waitFor(() => {
      expect(screen.getByText("El precio debe ser mayor a cero.")).toBeDefined();
    });
  });

  it("un alta correcta cierra el formulario y recarga la tabla", async () => {
    crearServicio.mockResolvedValue(CORTE);
    listarServicios.mockResolvedValue({ servicios: [CORTE, { ...CORTE, id: "2" }], total: 2 });
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Nuevo servicio" }));
    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Shampoo" } });
    fireEvent.change(screen.getByLabelText(/Precio sin IVA/), { target: { value: "3000" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

    await waitFor(() => {
      expect(crearServicio).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText("2 servicios")).toBeDefined();
    });
  });

  it("editar abre el formulario con los datos del servicio", async () => {
    editarServicio.mockResolvedValue({ ...CORTE, nombre: "Corte y barba" });
    listarServicios.mockResolvedValue(INICIAL);
    render(<ListadoDeServicios inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));

    const precio = screen.getByLabelText(/Precio sin IVA/) as HTMLInputElement;
    expect(precio.value).toBe("5000.00");

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(editarServicio).toHaveBeenCalledWith(
        CORTE.id,
        expect.objectContaining({ precio: "5000.00" }),
      );
    });
  });
});
