/**
 * @vitest-environment jsdom
 *
 * PAN-ONB-02 (HU-E1-02).
 *
 * The rule the specification is most explicit about — «"Continuar" permanece
 * deshabilitado mientras el CUIT no sea válido» — is the first thing checked, along with
 * the documented deviation of two extra mandatory fields the prototype does not show.
 *
 * The other half of this file is `padron-y-datos-fiscales`: three answers from ARCA that
 * must stay three. «No lo encuentro» blocks the form; «no pude preguntar» must not, and
 * is the ordinary answer until the company loads its fiscal certificate.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const empujar = vi.fn();
const refrescar = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: empujar, refresh: refrescar }),
}));

const guardar = vi.fn();
const consultar = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return {
    ...real,
    guardarEmpresa: (datos: unknown) => guardar(datos),
    consultarPadron: (cuit: string) => consultar(cuit),
  };
});

const { FormularioDeEmpresa } = await import("@/features/identity/components/FormularioDeEmpresa");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

const CUIT_VALIDO = "30-71234567-1";

afterEach(() => {
  cleanup();
  empujar.mockReset();
  refrescar.mockReset();
  guardar.mockReset();
  consultar.mockReset();
});

function botonValidar(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Validar contra ARCA/ }) as HTMLButtonElement;
}

function escribir(etiqueta: RegExp, valor: string): void {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

function completarTodo(cuit = CUIT_VALIDO): void {
  escribir(/CUIT/, cuit);
  escribir(/Razón social/, "Panadería Doña Rosa SRL");
  escribir(/Nombre del responsable/, "Rosa Giménez");
  escribir(/Email de contacto/, "rosa@panaderia.com");
}

function botonContinuar(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
}

describe("PAN-ONB-02", () => {
  it("Continuar arranca deshabilitado", () => {
    render(<FormularioDeEmpresa />);

    expect(botonContinuar().disabled).toBe(true);
  });

  it("sigue deshabilitado con un CUIT de dígito verificador inválido", () => {
    render(<FormularioDeEmpresa />);

    completarTodo("30712345670");

    expect(botonContinuar().disabled).toBe(true);
    expect(
      screen.getByText("El CUIT no supera la validación del dígito verificador."),
    ).toBeDefined();
  });

  it("pide los once dígitos cuando faltan", () => {
    render(<FormularioDeEmpresa />);

    escribir(/CUIT/, "3071234");

    expect(screen.getByText("Ingresá los 11 dígitos del CUIT.")).toBeDefined();
  });

  it("se habilita solo con todos los campos obligatorios de RN-03", () => {
    render(<FormularioDeEmpresa />);
    escribir(/CUIT/, CUIT_VALIDO);
    escribir(/Razón social/, "Panadería");
    expect(botonContinuar().disabled).toBe(true);

    escribir(/Nombre del responsable/, "Rosa");
    escribir(/Email de contacto/, "rosa@panaderia.com");

    expect(botonContinuar().disabled).toBe(false);
  });

  it("pide responsable y email de contacto, que el prototipo no muestra (H7)", () => {
    render(<FormularioDeEmpresa />);

    expect(screen.getByLabelText(/Nombre del responsable/)).toBeDefined();
    expect(screen.getByLabelText(/Email de contacto/)).toBeDefined();
  });

  it("no ofrece validar contra ARCA hasta que el CUIT sea estructuralmente válido", () => {
    render(<FormularioDeEmpresa />);

    escribir(/CUIT/, "30-71234567-0");
    expect(screen.queryByRole("button", { name: /Validar contra ARCA/ })).toBeNull();

    escribir(/CUIT/, CUIT_VALIDO);
    expect(botonValidar()).toBeDefined();
  });

  it("envía el CUIT normalizado, sin separadores", async () => {
    guardar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith(expect.objectContaining({ cuit: "30712345671" })),
    );
  });

  it("al guardar lleva al paso 3, las integraciones, y no salta al panel", async () => {
    guardar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/configuracion/integraciones"));
  });

  it("un CUIT ya registrado se muestra sin sacar al usuario del formulario", async () => {
    guardar.mockRejectedValue(
      new ErrorDeFormulario("Ese CUIT ya está registrado en otra empresa."),
    );
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() =>
      expect(screen.getByText("Ese CUIT ya está registrado en otra empresa.")).toBeDefined(),
    );
    expect(empujar).not.toHaveBeenCalled();
  });

  it("muestra el stepper en el paso 2", () => {
    render(<FormularioDeEmpresa />);

    expect(screen.getByLabelText("Progreso del onboarding")).toBeDefined();
    expect(screen.getByText("Empresa").closest("li")?.getAttribute("aria-current")).toBe("step");
  });
});

describe("FormularioDeEmpresa · padrón de ARCA", () => {
  function respuesta(
    estado: string,
    datos: { razon_social: string | null; condicion_iva: string | null; activo: boolean } | null,
    motivo: string | null = null,
  ): unknown {
    return { estado, datos, motivo };
  }

  it("un CUIT que ARCA no conoce bloquea el botón de continuar (caso 23)", async () => {
    consultar.mockResolvedValue(respuesta("NO_ENCONTRADO", null));
    render(<FormularioDeEmpresa />);
    completarTodo();
    expect(botonContinuar().disabled).toBe(false);

    fireEvent.click(botonValidar());

    await waitFor(() => expect(screen.getByText(/no encuentra este CUIT/)).toBeDefined());
    expect(botonContinuar().disabled).toBe(true);
  });

  it("«no disponible» avisa pero no bloquea nada (caso 26)", async () => {
    // Es la respuesta de todos los días hasta que la empresa carga su certificado. Si
    // bloqueara, una empresa recién registrada no podría guardar sus propios datos.
    consultar.mockResolvedValue(
      respuesta("NO_DISPONIBLE", null, "La empresa no tiene conectada la integracion con ARCA"),
    );
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonValidar());

    await waitFor(() => expect(screen.getByText(/No pudimos consultar el padrón/)).toBeDefined());
    expect(botonContinuar().disabled).toBe(false);
  });

  it("completa la razón social cuando está vacía", async () => {
    consultar.mockResolvedValue(
      respuesta("ENCONTRADO", {
        razon_social: "PANADERIA DONA ROSA SRL",
        condicion_iva: "RESPONSABLE_INSCRIPTO",
        activo: true,
      }),
    );
    render(<FormularioDeEmpresa />);
    escribir(/CUIT/, CUIT_VALIDO);

    fireEvent.click(botonValidar());

    await waitFor(() =>
      expect((screen.getByLabelText(/Razón social/) as HTMLInputElement).value).toBe(
        "PANADERIA DONA ROSA SRL",
      ),
    );
  });

  it("propone en vez de pisar lo que el usuario ya escribió (caso 25)", async () => {
    consultar.mockResolvedValue(
      respuesta("ENCONTRADO", {
        razon_social: "OTRO NOMBRE SA",
        condicion_iva: "RESPONSABLE_INSCRIPTO",
        activo: true,
      }),
    );
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonValidar());

    await waitFor(() => expect(screen.getByText(/En ARCA figura con/)).toBeDefined());
    // Lo tipeado sigue intacto: el nombre de una empresa no se reescribe a sus espaldas.
    expect((screen.getByLabelText(/Razón social/) as HTMLInputElement).value).toBe(
      "Panadería Doña Rosa SRL",
    );

    fireEvent.click(screen.getByRole("button", { name: /Usar los datos de ARCA/ }));

    expect((screen.getByLabelText(/Razón social/) as HTMLInputElement).value).toBe(
      "OTRO NOMBRE SA",
    );
  });

  it("cambiar el CUIT descarta lo que ARCA había dicho del anterior", async () => {
    consultar.mockResolvedValue(respuesta("NO_ENCONTRADO", null));
    render(<FormularioDeEmpresa />);
    completarTodo();
    fireEvent.click(botonValidar());
    await waitFor(() => expect(botonContinuar().disabled).toBe(true));

    escribir(/CUIT/, "27-12345678-0");

    expect(screen.queryByText(/no encuentra este CUIT/)).toBeNull();
    expect(botonContinuar().disabled).toBe(false);
  });

  it("un CUIT inactivo se informa sin bloquear", async () => {
    consultar.mockResolvedValue(
      respuesta("ENCONTRADO", {
        razon_social: "EX EMPRESA SRL",
        condicion_iva: null,
        activo: false,
      }),
    );
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonValidar());

    await waitFor(() => expect(screen.getByText(/figura como inactivo/)).toBeDefined());
    expect(botonContinuar().disabled).toBe(false);
  });

  it("en modo edición carga los valores actuales y no muestra el stepper (caso 27)", () => {
    render(
      <FormularioDeEmpresa
        modo="edicion"
        iniciales={{
          razon_social: "Panadería Doña Rosa SRL",
          onboarding_completo: true,
          cuit: "30712345671",
          condicion_iva: "MONOTRIBUTO",
          nombre_responsable: "Rosa Giménez",
          email_contacto: "rosa@panaderia.com",
        }}
      />,
    );

    expect((screen.getByLabelText(/CUIT/) as HTMLInputElement).value).toBe("30712345671");
    expect((screen.getByLabelText(/Condición IVA/) as HTMLSelectElement).value).toBe("MONOTRIBUTO");
    expect(screen.getByRole("button", { name: /Guardar/ })).toBeDefined();
    expect(screen.queryByText(/Integraciones/)).toBeNull();
  });

  it("en modo edición confirma en la pantalla en vez de navegar", async () => {
    guardar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeEmpresa modo="edicion" />);
    completarTodo();

    fireEvent.click(screen.getByRole("button", { name: /Guardar/ }));

    await waitFor(() => expect(screen.getByText(/Guardamos los datos/)).toBeDefined());
    expect(empujar).not.toHaveBeenCalled();
  });
});
