/**
 * @vitest-environment jsdom
 *
 * El selector de clientes activos (PAN-COB-03 RN-05; lo reusan facturacion y agenda).
 *
 * Tres cosas se prueban: que pide **solo activos** y busca por el texto (nombre o CUIT los
 * decide el backend), que sin resultados no deja al usuario en un callejon sin salida (avisa y
 * ofrece Clientes), y que elegir uno navega con `router.replace` a `<destino>?cliente=<id>`: la
 * URL es la unica fuente de verdad del cliente, y `replace` y no `push` para que retroceder no
 * pase por cada cliente que se miro.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarClientes = vi.fn();
const replace = vi.fn();

vi.mock("@/features/master_data/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/cliente")>(
    "@/features/master_data/api/cliente",
  );
  return { ...real, listarClientes: (...args: unknown[]) => listarClientes(...args) };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

const { SelectorDeClientes } = await import("../SelectorDeClientes");

const ROSA = {
  id: "cl-1",
  nombre: "Panaderia Dona Rosa",
  cuit: "30-71234567-1",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  contacto_whatsapp: null,
  contacto_email: null,
  origen: "PANEL",
  activo: true,
} as const;

const BRUNO = { ...ROSA, id: "cl-2", nombre: "Ferreteria Bruno", cuit: null } as const;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SelectorDeClientes", () => {
  it("pide solo clientes activos y lista nombre y CUIT", async () => {
    listarClientes.mockResolvedValue({ clientes: [ROSA, BRUNO], total: 2 });

    render(<SelectorDeClientes destino="/cobros/nuevo" seleccionado={null} />);

    expect(await screen.findByText("Panaderia Dona Rosa")).toBeTruthy();
    expect(screen.getByText("30-71234567-1")).toBeTruthy();
    expect(screen.getByText("Ferreteria Bruno")).toBeTruthy();
    expect(listarClientes).toHaveBeenCalledWith({ texto: "", soloActivos: true });
  });

  it("busca por el texto escrito, con el CUIT tal como se ve en pantalla", async () => {
    listarClientes.mockResolvedValue({ clientes: [ROSA], total: 1 });
    render(<SelectorDeClientes destino="/cobros/nuevo" seleccionado={null} />);
    await screen.findByText("Panaderia Dona Rosa");

    fireEvent.change(screen.getByLabelText("Buscar cliente por nombre o CUIT"), {
      target: { value: "30-71234567-1" },
    });

    await waitFor(() => {
      expect(listarClientes).toHaveBeenLastCalledWith({
        texto: "30-71234567-1",
        soloActivos: true,
      });
    });
  });

  it("sin resultados avisa y ofrece ir a Clientes", async () => {
    listarClientes.mockResolvedValue({ clientes: [], total: 0 });

    render(<SelectorDeClientes destino="/cobros/nuevo" seleccionado={null} />);

    expect(await screen.findByText("No se encontraron clientes.")).toBeTruthy();
    const enlace = screen.getByRole("link", { name: "Ir a Clientes" });
    expect(enlace.getAttribute("href")).toBe("/datos-maestros/clientes");
  });

  it("elegir un cliente navega a `<destino>?cliente=<id>` con replace", async () => {
    listarClientes.mockResolvedValue({ clientes: [ROSA], total: 1 });
    render(<SelectorDeClientes destino="/cobros/nuevo" seleccionado={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /Panaderia Dona Rosa/ }));

    expect(replace).toHaveBeenCalledWith("/cobros/nuevo?cliente=cl-1");
  });

  it("muestra al cliente preseleccionado, que sigue siendo editable", async () => {
    listarClientes.mockResolvedValue({ clientes: [ROSA, BRUNO], total: 2 });

    render(
      <SelectorDeClientes
        destino="/cobros/nuevo"
        seleccionado={{ id: "cl-1", nombre: "Panaderia Dona Rosa", cuit: "30-71234567-1" }}
      />,
    );

    expect(screen.getByText("Cliente seleccionado")).toBeTruthy();
    // Cambiarlo es elegir otro de la misma lista.
    fireEvent.click(await screen.findByRole("button", { name: /Ferreteria Bruno/ }));
    expect(replace).toHaveBeenCalledWith("/cobros/nuevo?cliente=cl-2");
  });

  it("si el listado falla, lo dice en vez de quedarse vacio", async () => {
    listarClientes.mockRejectedValue(new Error("caido"));

    render(<SelectorDeClientes destino="/cobros/nuevo" seleccionado={null} />);

    expect(await screen.findByText("No se pudieron cargar los clientes.")).toBeTruthy();
  });
});
