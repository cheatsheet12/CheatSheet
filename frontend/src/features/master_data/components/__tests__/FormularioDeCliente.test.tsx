/**
 * @vitest-environment jsdom
 *
 * El formulario de PAN-DM-01 y las tres respuestas de ARCA.
 *
 * La que importa es la tercera. Que «no se pudo preguntar» aparezca como una advertencia
 * que dice «el cliente se guarda igual» —y no como un error— es la decisión del Gate 1 de
 * esta unidad hecha pantalla. Si algún día alguien la convierte en un error, este test es
 * lo que se lo dice.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const consultarPadron = vi.fn();

vi.mock("@/features/master_data/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/master_data/api/cliente")>(
    "@/features/master_data/api/cliente",
  );
  return { ...real, consultarPadron: (...args: unknown[]) => consultarPadron(...args) };
});

const { FormularioDeCliente } = await import(
  "@/features/master_data/components/FormularioDeCliente"
);

const CUIT = "30712345671";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function montar(): void {
  render(<FormularioDeCliente onGuardar={async () => undefined} onCancelar={() => undefined} />);
}

async function validarCon(respuesta: unknown): Promise<void> {
  consultarPadron.mockResolvedValue(respuesta);
  montar();
  fireEvent.change(screen.getByLabelText(/CUIT/), { target: { value: CUIT } });
  fireEvent.click(screen.getByRole("button", { name: "Validar contra ARCA" }));
  await waitFor(() => {
    expect(consultarPadron).toHaveBeenCalledWith(CUIT);
  });
}

describe("FormularioDeCliente", () => {
  it("no ofrece campo de origen", () => {
    montar();

    expect(screen.queryByLabelText(/origen/i)).toBeNull();
  });

  it("no deja validar sin CUIT", () => {
    montar();

    const boton = screen.getByRole("button", { name: "Validar contra ARCA" });
    expect(boton.hasAttribute("disabled")).toBe(true);
  });

  it("encontrado completa nombre y condicion IVA", async () => {
    await validarCon({
      estado: "ENCONTRADO",
      datos: {
        razon_social: "PANADERIA DONA ROSA SRL",
        condicion_iva: "RESPONSABLE_INSCRIPTO",
        activo: true,
      },
      motivo: null,
    });

    await waitFor(() => {
      const nombre = screen.getByLabelText(/Nombre o razón social/) as HTMLInputElement;
      expect(nombre.value).toBe("PANADERIA DONA ROSA SRL");
    });
  });

  it("no pisa el nombre que el usuario ya escribio", async () => {
    consultarPadron.mockResolvedValue({
      estado: "ENCONTRADO",
      datos: { razon_social: "OTRO NOMBRE SRL", condicion_iva: "MONOTRIBUTO", activo: true },
      motivo: null,
    });
    montar();
    fireEvent.change(screen.getByLabelText(/Nombre o razón social/), {
      target: { value: "Panaderia de la esquina" },
    });
    fireEvent.change(screen.getByLabelText(/CUIT/), { target: { value: CUIT } });

    fireEvent.click(screen.getByRole("button", { name: "Validar contra ARCA" }));

    await waitFor(() => {
      expect(consultarPadron).toHaveBeenCalled();
    });
    const nombre = screen.getByLabelText(/Nombre o razón social/) as HTMLInputElement;
    expect(nombre.value).toBe("Panaderia de la esquina");
  });

  it("no encontrado avisa que hay que revisarlo", async () => {
    await validarCon({ estado: "NO_ENCONTRADO", datos: null, motivo: null });

    await waitFor(() => {
      expect(screen.getByText(/ARCA no reconoce ese CUIT/)).toBeDefined();
    });
  });

  it("no disponible avisa que el cliente se guarda igual", async () => {
    await validarCon({
      estado: "NO_DISPONIBLE",
      datos: null,
      motivo: "La empresa no tiene ARCA conectada",
    });

    await waitFor(() => {
      expect(screen.getByText(/El cliente se guarda igual/)).toBeDefined();
    });
    expect(screen.getByText(/La empresa no tiene ARCA conectada/)).toBeDefined();
  });
});
