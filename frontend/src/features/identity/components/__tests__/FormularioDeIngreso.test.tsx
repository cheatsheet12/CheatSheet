/**
 * @vitest-environment jsdom
 *
 * PAN-ONB-01 — the behaviour the annotations prescribe, checked as a user meets it.
 *
 * The assertions use the exact copy from
 * `docs/aidlc/inputs/prototipos/anotaciones-comportamiento.html`. If somebody reworks a
 * message, this fails and the change becomes a decision instead of a drift.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

const registrar = vi.fn();
const ingresar = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, registrar: () => registrar(), ingresar: () => ingresar() };
});

const { FormularioDeIngreso } = await import("@/features/identity/components/FormularioDeIngreso");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const empujar = routerQueSuspende.push;

afterEach(() => {
  cleanup();
  reiniciarRouter();
  registrar.mockReset();
  ingresar.mockReset();
});

function escribir(etiqueta: RegExp, valor: string): void {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

function irARegistro(): void {
  fireEvent.click(screen.getByRole("button", { name: "Registrate" }));
}

describe("PAN-ONB-01 — ingreso", () => {
  it("arranca en modo ingresar, sin pedir términos", () => {
    render(<FormularioDeIngreso />);

    expect(screen.getByRole("button", { name: "Ingresar" })).toBeDefined();
    expect(screen.queryByLabelText(/Términos/)).toBeNull();
  });

  it("la contraseña se oculta por defecto y el botón la muestra y la vuelve a ocultar", () => {
    render(<FormularioDeIngreso />);
    escribir(/Contraseña/, "una-contrasena");
    const campo = screen.getByLabelText(/Contraseña/);

    expect(campo.getAttribute("type")).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseña" }));
    expect(campo.getAttribute("type")).toBe("text");
    expect((campo as HTMLInputElement).value).toBe("una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ocultar contraseña" }));
    expect(campo.getAttribute("type")).toBe("password");
  });

  it("mostrar la contraseña no envía el formulario", () => {
    render(<FormularioDeIngreso />);
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseña" }));

    expect(ingresar).not.toHaveBeenCalled();
  });

  it("una contraseña corta muestra el mensaje de RN-01 y no llama a la API", () => {
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "corta");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();
    expect(ingresar).not.toHaveBeenCalled();
  });

  it("credenciales correctas llevan al paso pendiente del onboarding", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("con el onboarding completo va al panel", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));
  });

  it("un error de credenciales se muestra sin decir cuál de los dos falló", async () => {
    ingresar.mockRejectedValue(new ErrorDeFormulario("Email o contraseña incorrectos."));
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(screen.getByText("Email o contraseña incorrectos.")).toBeDefined());
  });
});

describe("PAN-ONB-01 — ingreso, mientras la navegación tarda", () => {
  function entrar(): void {
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));
  }

  it("el botón sigue ocupado hasta que se muestra la página de destino y un segundo envío no repite el login", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: true });
    render(
      <ArnesDeRouter>
        <FormularioDeIngreso />
      </ArnesDeRouter>,
    );

    entrar();
    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));

    // The login already answered; the destination has not arrived yet.
    const boton = screen.getByRole("button", { name: "Ingresar" });
    expect(boton.hasAttribute("disabled")).toBe(true);
    expect(boton.getAttribute("aria-busy")).toBe("true");
    fireEvent.submit(boton.closest("form") as HTMLFormElement);
    expect(ingresar).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
    expect(ingresar).toHaveBeenCalledTimes(1);
  });

  it("si el login falla el botón se libera y se muestra el error", async () => {
    ingresar.mockRejectedValue(new ErrorDeFormulario("Email o contraseña incorrectos."));
    render(
      <ArnesDeRouter>
        <FormularioDeIngreso />
      </ArnesDeRouter>,
    );

    entrar();

    await waitFor(() => expect(screen.getByText("Email o contraseña incorrectos.")).toBeDefined());
    const boton = screen.getByRole("button", { name: "Ingresar" });
    expect(boton.hasAttribute("disabled")).toBe(false);
    expect(empujar).not.toHaveBeenCalled();
  });
});

describe("PAN-ONB-01 — registro", () => {
  it("al registrarse aparecen el nombre y los términos", () => {
    render(<FormularioDeIngreso />);

    irARegistro();

    expect(screen.getByLabelText(/Tu nombre/)).toBeDefined();
    expect(screen.getByLabelText(/Acepto los/)).toBeDefined();
  });

  it("sin aceptar los términos no se registra (HU-E1-03 RN-02)", () => {
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(screen.getByText("Debés aceptar los Términos y Condiciones.")).toBeDefined();
    expect(registrar).not.toHaveBeenCalled();
  });

  it("aceptando los términos sí se registra y avanza al paso 2", async () => {
    registrar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    fireEvent.click(screen.getByLabelText(/Acepto los/));

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("un email ya registrado ofrece iniciar sesión, como pide RN-03", async () => {
    registrar.mockRejectedValue(
      new ErrorDeFormulario("Ese email ya tiene una cuenta. ¿Iniciar sesión?"),
    );
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    fireEvent.click(screen.getByLabelText(/Acepto los/));

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() =>
      expect(screen.getByText("Ese email ya tiene una cuenta. ¿Iniciar sesión?")).toBeDefined(),
    );
  });

  it("volver a ingresar limpia los errores del otro modo", () => {
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Contraseña/, "corta");
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Ya tengo cuenta" }));

    expect(screen.queryByText("La contraseña debe tener al menos 8 caracteres.")).toBeNull();
  });

  it("enlaza los términos y la política en el pie, en los dos modos", () => {
    render(<FormularioDeIngreso />);
    const enlazados = (): string[] =>
      screen
        .getAllByRole("link")
        .map((enlace) => enlace.getAttribute("href") ?? "")
        .filter((href) => href === "/terminos" || href === "/privacidad");

    expect(enlazados()).toEqual(["/terminos", "/privacidad"]);

    irARegistro();

    // The registration checkbox still links the terms; the footer adds both.
    expect(enlazados()).toEqual(expect.arrayContaining(["/terminos", "/privacidad"]));
    expect(
      screen.getByRole("navigation", { name: "Información legal" }).querySelectorAll("a[href]"),
    ).toHaveLength(2);
  });

  it("ofrece Google y recuperación de contraseña", () => {
    render(<FormularioDeIngreso />);

    expect(screen.getByText("Continuar con Google")).toBeDefined();
    expect(screen.getByText("¿Olvidaste tu contraseña?")).toBeDefined();
  });
});
