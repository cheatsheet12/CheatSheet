/**
 * @vitest-environment jsdom
 *
 * El rediseño de «Nueva emisión»: estado de cada paso, resumen del receptor, errores en
 * español, motivo del botón deshabilitado y autocompletado desde el catálogo de Servicios.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const validarReceptor = vi.fn();
const listarServicios = vi.fn();

vi.mock("@/features/billing/api/comprobante", async () => {
  const real = await vi.importActual<typeof import("@/features/billing/api/comprobante")>(
    "@/features/billing/api/comprobante",
  );
  return { ...real, validarReceptor: (...args: unknown[]) => validarReceptor(...args) };
});

vi.mock("@/features/master_data", () => ({
  listarServicios: (...args: unknown[]) => listarServicios(...args),
}));

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import { ErrorDeComprobante } from "@/features/billing";
import type { PuntoDeVenta, ReceptorValidado } from "@/features/billing";

const { NuevaEmision } = await import("@/features/billing/components/NuevaEmision");

const RECEPTOR: ReceptorValidado = {
  nombre: "Acme SA",
  cuit: "30712345671",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  tipos_disponibles: ["FACTURA_A", "NOTA_CREDITO_A"],
};

const PUNTO: PuntoDeVenta = {
  id: "p1",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: { FACTURA_A: 123 },
  created_at: "2026-09-07T12:00:00Z",
};

function servicio(id: string, nombre: string, precio: string, activo = true): unknown {
  return {
    id,
    nombre,
    precio,
    alicuota_iva: "0.105",
    agendable: false,
    duracion_estandar_min: null,
    origen: "MANUAL",
    activo,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function validarYElegirTipo(): Promise<void> {
  fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
    target: { value: "30712345671" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Validar" }));
  await screen.findByText("Acme SA");
  fireEvent.change(screen.getByLabelText("Tipo de comprobante"), {
    target: { value: "FACTURA_A" },
  });
}

function pasos(): HTMLElement {
  return screen.getByRole("list", { name: "Progreso de la emisión" });
}

describe("los pasos y su estado", () => {
  it("arranca con el paso 1 en curso y los otros dos pendientes y con su motivo", () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    const items = within(pasos()).getAllByRole("listitem");
    expect(items[0]?.className).toContain("--activo");
    expect(items[1]?.className).toContain("--pendiente");
    expect(items[2]?.className).toContain("--pendiente");
    expect(screen.getByText(/Se habilita cuando ARCA valida el CUIT/)).toBeDefined();
    expect(screen.getByText(/Se habilita cuando elegís el tipo/)).toBeDefined();
  });

  it("validar completa el paso 1 y activa el 2; elegir el tipo completa el 2", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText("Acme SA");

    let items = within(pasos()).getAllByRole("listitem");
    expect(items[0]?.className).toContain("--completo");
    expect(items[1]?.className).toContain("--activo");
    expect(screen.getByRole("button", { name: /Cambiar/ })).toBeDefined();

    fireEvent.change(screen.getByLabelText("Tipo de comprobante"), {
      target: { value: "FACTURA_A" },
    });
    items = within(pasos()).getAllByRole("listitem");
    expect(items[1]?.className).toContain("--completo");
    expect(items[2]?.className).toContain("--activo");
  });

  it("«Cambiar» vuelve al paso 1 y descarta lo que dependía del CUIT", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);
    await validarYElegirTipo();

    fireEvent.click(screen.getByRole("button", { name: /Cambiar/ }));

    expect(screen.queryByLabelText("Tipo de comprobante")).toBeNull();
    expect(screen.queryByText("Acme SA")).toBeNull();
  });
});

describe("el resumen del receptor", () => {
  it("muestra iniciales, razón social, CUIT, condición de IVA y qué se puede emitir", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" nombreDelCliente="Acme (catálogo)" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText("Acme SA");

    expect(screen.getByText("AS")).toBeDefined();
    expect(screen.getAllByText("30-71234567-1").length).toBeGreaterThan(0);
    expect(screen.getByText("Responsable inscripto")).toBeDefined();
    expect(screen.getByText("Se le puede emitir")).toBeDefined();
    expect(screen.getByText("Acme (catálogo)")).toBeDefined();
  });
});

describe("los errores de validación, en español", () => {
  it("un ErrorInterno no se muestra crudo", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockRejectedValue(new ErrorDeComprobante("ErrorInterno", "ErrorInterno"));
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), { target: { value: "2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));

    expect(await screen.findByText(/No pudimos validar el CUIT ahora/)).toBeDefined();
    expect(screen.queryByText("ErrorInterno")).toBeNull();
  });
});

describe("el botón de emitir y su motivo", () => {
  it("queda deshabilitado y dice qué falta, y se habilita con todo completo", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText("Acme SA");

    const boton = screen.getByRole("button", { name: /Emitir comprobante/ }) as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
    expect(screen.getByText("Elegir el tipo de comprobante.")).toBeDefined();
    expect(screen.getByText(/Debe agregar al menos un ítem/)).toBeDefined();

    fireEvent.change(screen.getByLabelText("Tipo de comprobante"), {
      target: { value: "FACTURA_A" },
    });
    fireEvent.change(screen.getByLabelText("Descripción 1"), { target: { value: "Corte" } });
    fireEvent.change(screen.getByLabelText("Precio unitario"), { target: { value: "1000.00" } });

    expect(boton.disabled).toBe(false);
    expect(screen.queryByText("Para emitir falta:")).toBeNull();
  });

  it("dice la numeración con el último número emitido, sin inventar el siguiente", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);
    await validarYElegirTipo();

    expect(screen.getByText(/0001-00000123/)).toBeDefined();
  });
});

describe("el domicilio del receptor", () => {
  it("no se autocompleta: el navegador no ofrece valores anteriores", async () => {
    listarServicios.mockResolvedValue({ servicios: [], total: 0 });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);
    await validarYElegirTipo();

    const campo = screen.getByLabelText(/Domicilio del receptor/);
    expect(campo.getAttribute("autocomplete")).toBe("off");
  });
});

describe("autocompletar un ítem desde el catálogo de Servicios", () => {
  async function preparar(): Promise<HTMLInputElement> {
    listarServicios.mockResolvedValue({
      servicios: [
        servicio("s1", "Corte de pelo", "1500.00"),
        servicio("s2", "Corte de barba", "800.00"),
        servicio("s3", "Tintura", "5000.00"),
        servicio("s4", "Corte antiguo", "100.00", false),
      ],
      total: 4,
    });
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);
    await validarYElegirTipo();
    await waitFor(() => expect(listarServicios).toHaveBeenCalled());
    // El pedido es una sola vez, al montar el paso 3.
    expect(listarServicios).toHaveBeenCalledTimes(1);
    return screen.getByLabelText("Descripción 1") as HTMLInputElement;
  }

  it("filtra por texto, muestra nombre y precio, y no ofrece los inactivos", async () => {
    const campo = await preparar();

    fireEvent.change(campo, { target: { value: "corte" } });

    const opciones = within(await screen.findByRole("listbox")).getAllByRole("option");
    expect(opciones.map((opcion) => opcion.textContent)).toEqual([
      "Corte de pelo$ 1500.00 · IVA 10,5%",
      "Corte de barba$ 800.00 · IVA 10,5%",
    ]);
    expect(screen.queryByText(/Corte antiguo/)).toBeNull();
  });

  it("elegir completa descripción, precio e IVA; con flechas y Enter también", async () => {
    const campo = await preparar();

    fireEvent.change(campo, { target: { value: "corte" } });
    fireEvent.keyDown(campo, { key: "ArrowDown" });
    fireEvent.keyDown(campo, { key: "ArrowDown" });
    fireEvent.keyDown(campo, { key: "Enter" });

    expect((screen.getByLabelText("Descripción 1") as HTMLInputElement).value).toBe(
      "Corte de barba",
    );
    expect((screen.getByLabelText("Precio unitario") as HTMLInputElement).value).toBe("800.00");
    expect((screen.getByLabelText("IVA") as HTMLSelectElement).value).toBe("0.105");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("el clic elige y Escape cierra sin elegir", async () => {
    const campo = await preparar();

    fireEvent.change(campo, { target: { value: "tint" } });
    fireEvent.keyDown(campo, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();

    fireEvent.change(campo, { target: { value: "tintu" } });
    fireEvent.mouseDown(within(await screen.findByRole("listbox")).getByRole("option"));
    expect((screen.getByLabelText("Precio unitario") as HTMLInputElement).value).toBe("5000.00");
  });

  it("una descripción libre que no está en el catálogo sigue funcionando", async () => {
    const campo = await preparar();

    fireEvent.change(campo, { target: { value: "Trabajo especial" } });
    fireEvent.change(screen.getByLabelText("Precio unitario"), { target: { value: "10.00" } });
    fireEvent.keyDown(campo, { key: "Enter" });

    expect(screen.queryByRole("listbox")).toBeNull();
    expect((screen.getByLabelText("Descripción 1") as HTMLInputElement).value).toBe(
      "Trabajo especial",
    );
    expect(
      (screen.getByRole("button", { name: /Emitir comprobante/ }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("si el catálogo falla, el campo sigue siendo texto libre", async () => {
    listarServicios.mockRejectedValue(new Error("caído"));
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);
    await validarYElegirTipo();
    await waitFor(() => expect(listarServicios).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Descripción 1"), { target: { value: "Algo" } });

    expect(screen.queryByRole("listbox")).toBeNull();
    expect((screen.getByLabelText("Descripción 1") as HTMLInputElement).value).toBe("Algo");
  });
});
