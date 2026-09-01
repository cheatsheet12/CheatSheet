/**
 * @vitest-environment jsdom
 *
 * PAN-DM-01 — los casos 16 y 17 del plan.
 *
 * Dos cosas se prueban acá y ninguna es una regla de negocio: que las cinco columnas que
 * pide el primer criterio de aceptación estén, y que el 409 del CUIT duplicado se
 * convierta en un mensaje **con el enlace al que ya existe** — que es lo que quiere decir
 * «ofrece ver el duplicado».
 *
 * El control de rol de este archivo es **cosmético**, y conviene decirlo: quien rechaza a
 * un Solo Lectura que intenta escribir es el backend, y eso lo prueba el test de la capa
 * de aplicación. Lo que se prueba acá es la otra mitad: que el panel no ofrezca una
 * acción que va a ser rechazada.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarClientes = vi.fn();
const crearCliente = vi.fn();
const editarCliente = vi.fn();
const cambiarEstadoDeCliente = vi.fn();
const consultarPadron = vi.fn();

vi.mock("@/features/master_data/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/cliente")>(
    "@/features/master_data/api/cliente",
  );
  return {
    ...real,
    listarClientes: (...args: unknown[]) => listarClientes(...args),
    crearCliente: (...args: unknown[]) => crearCliente(...args),
    editarCliente: (...args: unknown[]) => editarCliente(...args),
    cambiarEstadoDeCliente: (...args: unknown[]) => cambiarEstadoDeCliente(...args),
    consultarPadron: (...args: unknown[]) => consultarPadron(...args),
  };
});

import type { Cliente, ListadoDeClientesRespuesta as Listado } from "@/features/master_data";
import { ErrorDeCatalogo } from "@/features/master_data";

const { ListadoDeClientes } = await import("@/features/master_data/components/ListadoDeClientes");

const ROSA: Cliente = {
  id: "11111111-1111-1111-1111-111111111111",
  nombre: "Panaderia Dona Rosa",
  cuit: "30-71234567-1",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  contacto_whatsapp: "5491112345678",
  contacto_email: "rosa@panaderia.com",
  origen: "PANEL",
  activo: true,
};

const INICIAL: Listado = { clientes: [ROSA], total: 1 };

beforeAll(() => {
  // jsdom has no `showModal`, and a `<dialog>` without `open` keeps its contents out of
  // the accessibility tree — so the stub has to set the flag, not just record the call.
  // Same shape as the tests of `ModalDeInvitacion` and `GrillaDeIntegraciones`.
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

describe("ListadoDeClientes", () => {
  it("muestra las cinco columnas del criterio de aceptacion", () => {
    render(<ListadoDeClientes inicial={INICIAL} puedeEditar />);

    for (const titulo of ["Nombre", "CUIT", "Origen", "WhatsApp", "Estado"]) {
      expect(screen.getByRole("columnheader", { name: titulo })).toBeDefined();
    }
    expect(screen.getByText("Panaderia Dona Rosa")).toBeDefined();
    expect(screen.getByText("30-71234567-1")).toBeDefined();
    expect(screen.getByText("PANEL")).toBeDefined();
  });

  it("un cliente sin CUIT ni WhatsApp no deja celdas en blanco", () => {
    const sinDatos: Cliente = {
      ...ROSA,
      cuit: null,
      contacto_whatsapp: null,
      nombre: "Cliente de WhatsApp",
    };

    render(<ListadoDeClientes inicial={{ clientes: [sinDatos], total: 1 }} puedeEditar />);

    expect(screen.getAllByText("—").length).toBe(2);
  });

  it("no ofrece acciones de escritura a quien no puede escribir", () => {
    render(<ListadoDeClientes inicial={INICIAL} puedeEditar={false} />);

    expect(screen.queryByRole("button", { name: "Nuevo cliente" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desactivar" })).toBeNull();
  });

  it("un cliente inactivo se ofrece para reactivar, nunca para borrar", () => {
    const inactivo: Cliente = { ...ROSA, activo: false };

    render(<ListadoDeClientes inicial={{ clientes: [inactivo], total: 1 }} puedeEditar />);

    expect(screen.getByRole("button", { name: "Reactivar" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /elimina|borra/i })).toBeNull();
  });

  it("el CUIT duplicado muestra el mensaje y ofrece ver el que ya existe", async () => {
    crearCliente.mockRejectedValue(
      new ErrorDeCatalogo("Ya existe un cliente con ese CUIT.", ROSA.id),
    );
    render(<ListadoDeClientes inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    fireEvent.change(screen.getByLabelText(/Nombre o razon social/), {
      target: { value: "Rosa otra vez" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cliente" }));

    await waitFor(() => {
      expect(screen.getByText("Ya existe un cliente con ese CUIT.")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: "Ver el cliente existente" })).toBeDefined();
  });

  it("un alta correcta cierra el formulario y recarga la tabla", async () => {
    crearCliente.mockResolvedValue(ROSA);
    listarClientes.mockResolvedValue({ clientes: [ROSA, { ...ROSA, id: "2" }], total: 2 });
    render(<ListadoDeClientes inicial={INICIAL} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    fireEvent.change(screen.getByLabelText(/Nombre o razon social/), {
      target: { value: "Otro cliente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cliente" }));

    await waitFor(() => {
      expect(crearCliente).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText("2 clientes")).toBeDefined();
    });
  });
});
