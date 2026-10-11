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
  return {
    ...real,
    registrar: (...args: unknown[]) => registrar(...args),
    ingresar: () => ingresar(),
  };
});

const { FormularioDeIngreso } = await import("@/features/identity/components/FormularioDeIngreso");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const empujar = routerQueSuspende.push;

const MENSAJE_TERMINOS = "Debe aceptar los términos y condiciones para continuar.";
const MENSAJE_PRIVACIDAD = "Debe aceptar la política de privacidad para continuar.";

const VERSIONES = {
  terminos: { version: "1.1", vigente_desde: "2026-10-10", borrador: true },
  privacidad: { version: "1.0", vigente_desde: "2026-10-10", borrador: true },
};

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

function aceptarTodo(): void {
  fireEvent.click(screen.getByLabelText(/Términos y Condiciones/));
  fireEvent.click(screen.getByLabelText(/Política de Privacidad/));
}

describe("PAN-ONB-01 — ingreso", () => {
  it("arranca en modo ingresar, sin pedir términos", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);

    expect(screen.getByRole("button", { name: "Ingresar" })).toBeDefined();
    expect(screen.queryByLabelText(/Términos/)).toBeNull();
  });

  it("la contraseña se oculta por defecto y el botón la muestra y la vuelve a ocultar", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
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
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Mostrar contraseña" }));

    expect(ingresar).not.toHaveBeenCalled();
  });

  it("una contraseña corta muestra el mensaje de RN-01 y no llama a la API", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "corta");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();
    expect(ingresar).not.toHaveBeenCalled();
  });

  it("credenciales correctas llevan al paso pendiente del onboarding", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("con el onboarding completo va al panel", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));
  });

  it("un error de credenciales se muestra sin decir cuál de los dos falló", async () => {
    ingresar.mockRejectedValue(new ErrorDeFormulario("Email o contraseña incorrectos."));
    render(<FormularioDeIngreso versiones={VERSIONES} />);
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
        <FormularioDeIngreso versiones={VERSIONES} />
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
        <FormularioDeIngreso versiones={VERSIONES} />
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
  it("al registrarse aparecen el nombre y las dos casillas, separadas y sin marcar", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);

    irARegistro();

    expect(screen.getByLabelText(/Tu nombre/)).toBeDefined();
    const terminos = screen.getByLabelText(/Términos y Condiciones/) as HTMLInputElement;
    const privacidad = screen.getByLabelText(/Política de Privacidad/) as HTMLInputElement;
    expect(terminos.checked).toBe(false);
    expect(privacidad.checked).toBe(false);
    expect(terminos.id).not.toBe(privacidad.id);
  });

  function completarSinAceptar(): void {
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
  }

  it("sin marcar ninguna casilla cada una muestra su mensaje y no se registra (RN-02, RN-03)", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    completarSinAceptar();

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(screen.getByText(MENSAJE_TERMINOS)).toBeDefined();
    expect(screen.getByText(MENSAJE_PRIVACIDAD)).toBeDefined();
    expect(registrar).not.toHaveBeenCalled();
  });

  it("con solo la política marcada falta únicamente el mensaje de los términos", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    completarSinAceptar();
    fireEvent.click(screen.getByLabelText(/Política de Privacidad/));

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(screen.getByText(MENSAJE_TERMINOS)).toBeDefined();
    expect(screen.queryByText(MENSAJE_PRIVACIDAD)).toBeNull();
    expect(registrar).not.toHaveBeenCalled();
  });

  it("registra mandando las dos versiones que se mostraron", async () => {
    registrar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    completarSinAceptar();
    aceptarTodo();

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() => expect(registrar).toHaveBeenCalledTimes(1));
    expect(registrar).toHaveBeenCalledWith({
      email: "ana@empresa.com",
      contrasena: "una-contrasena",
      nombre: "Ana",
      consentimiento: { version_terminos: "1.1", version_privacidad: "1.0" },
    });
  });

  it("sin los textos vigentes no deja registrar y lo dice", () => {
    render(<FormularioDeIngreso versiones={null} />);
    completarSinAceptar();
    aceptarTodo();

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(screen.getByText(/No pudimos cargar los textos legales/)).toBeDefined();
    expect(registrar).not.toHaveBeenCalled();
  });

  it("volver del flujo de Google sin consentimiento abre el registro con el mensaje (pregunta 6)", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} errorInicial="ConsentimientoRequerido" />);

    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeDefined();
    expect(screen.getByText(MENSAJE_PRIVACIDAD)).toBeDefined();
  });

  it("una versión desactualizada pide recargar y abre el registro", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} errorInicial="VersionLegalDesactualizada" />);

    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeDefined();
    expect(screen.getByText(/Actualizamos los textos legales/)).toBeDefined();
  });

  it("aceptando los términos sí se registra y avanza al paso 2", async () => {
    registrar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    aceptarTodo();

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("un email ya registrado ofrece iniciar sesión, como pide RN-03", async () => {
    registrar.mockRejectedValue(
      new ErrorDeFormulario("Ese email ya tiene una cuenta. ¿Iniciar sesión?"),
    );
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    aceptarTodo();

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() =>
      expect(screen.getByText("Ese email ya tiene una cuenta. ¿Iniciar sesión?")).toBeDefined(),
    );
  });

  it("volver a ingresar limpia los errores del otro modo", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();
    escribir(/Contraseña/, "corta");
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Ya tengo cuenta" }));

    expect(screen.queryByText("La contraseña debe tener al menos 8 caracteres.")).toBeNull();
  });

  it("enlaza los términos y la política en el pie, en los dos modos", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
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
    render(<FormularioDeIngreso versiones={VERSIONES} />);

    expect(screen.getByText("Continuar con Google")).toBeDefined();
    expect(screen.getByText("¿Olvidaste tu contraseña?")).toBeDefined();
  });
});

describe("PAN-ONB-01 — Continuar con Google (HU-E1-08 RN-03, criterio 3)", () => {
  const enlaceDeGoogle = (): HTMLAnchorElement =>
    screen.getByRole("link", { name: /Continuar con Google/ }) as HTMLAnchorElement;
  const botonDeGoogle = (): HTMLButtonElement =>
    screen.getByRole("button", { name: /Continuar con Google/ }) as HTMLButtonElement;
  const formularioDeGoogle = (): HTMLFormElement =>
    botonDeGoogle().closest("form") as HTMLFormElement;

  it("al ingresar es un enlace directo, sin casillas y sin versiones", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);

    expect(enlaceDeGoogle().getAttribute("href")).toBe("/api/auth/google");
    expect(fireEvent.click(enlaceDeGoogle())).toBe(true);
  });

  it("al registrarse, sin las casillas no envía y muestra los mensajes", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();

    const envio = vi.fn((evento: Event) => evento.preventDefault());
    formularioDeGoogle().addEventListener("submit", envio);
    const navego = fireEvent.click(botonDeGoogle());

    expect(navego).toBe(false);
    expect(envio).not.toHaveBeenCalled();
    expect(screen.getByText(MENSAJE_TERMINOS)).toBeDefined();
    expect(screen.getByText(MENSAJE_PRIVACIDAD)).toBeDefined();
  });

  it("con una sola casilla marcada tampoco envía", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();
    fireEvent.click(screen.getByLabelText(/Términos y Condiciones/));

    const navego = fireEvent.click(botonDeGoogle());

    expect(navego).toBe(false);
    expect(screen.getByText(MENSAJE_PRIVACIDAD)).toBeDefined();
  });

  it("con las dos marcadas envía por POST las versiones mostradas, nunca en la URL", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();
    aceptarTodo();

    const formulario = formularioDeGoogle();
    const envio = vi.fn((evento: Event) => evento.preventDefault());
    formulario.addEventListener("submit", envio);
    fireEvent.click(botonDeGoogle());

    expect(formulario.method).toBe("post");
    // No query string: a link must not be able to record an acceptance.
    expect(formulario.getAttribute("action")).toBe("/api/auth/google");
    expect(formulario.querySelector<HTMLInputElement>('input[name="terminos"]')?.value).toBe("1.1");
    expect(formulario.querySelector<HTMLInputElement>('input[name="privacidad"]')?.value).toBe(
      "1.0",
    );
    expect(envio).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("link", { name: /Continuar con Google/ })).toBeNull();
  });

  it("el botón de Google es un botón alcanzable por teclado con su nombre accesible", () => {
    render(<FormularioDeIngreso versiones={VERSIONES} />);
    irARegistro();

    expect(botonDeGoogle().type).toBe("submit");
    expect(botonDeGoogle().disabled).toBe(false);
  });
});
