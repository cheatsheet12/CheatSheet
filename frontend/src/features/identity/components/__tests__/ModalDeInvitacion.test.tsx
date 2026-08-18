/**
 * @vitest-environment jsdom
 *
 * Caso 39 — the invitation modal validates before sending.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const invitarUsuario = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, invitarUsuario: (...args: unknown[]) => invitarUsuario(...args) };
});

const { ModalDeInvitacion } = await import("@/features/identity/components/ModalDeInvitacion");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

beforeAll(() => {
  // jsdom has no `showModal`, and a `<dialog>` without `open` keeps its contents out of
  // the accessibility tree — so the stub has to set the flag, not just record the call.
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

function montar(): {
  readonly cerrar: ReturnType<typeof vi.fn>;
  readonly invitado: ReturnType<typeof vi.fn>;
} {
  const cerrar = vi.fn();
  const invitado = vi.fn();
  render(<ModalDeInvitacion abierto onCerrar={cerrar} onInvitado={invitado} />);
  return { cerrar, invitado };
}

describe("ModalDeInvitacion", () => {
  it("no envía con el email vacío", () => {
    montar();

    fireEvent.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(screen.getByText("Ingresá un email válido.")).toBeDefined();
    expect(invitarUsuario).not.toHaveBeenCalled();
  });

  it("no envía con un email mal formado", () => {
    montar();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "beto@" } });

    fireEvent.click(screen.getByRole("button", { name: "Enviar invitación" }));

    expect(screen.getByText("Ingresá un email válido.")).toBeDefined();
    expect(invitarUsuario).not.toHaveBeenCalled();
  });

  it("invita con el rol elegido y avisa a quien lo abrió", async () => {
    const { invitado } = montar();
    const nuevo = {
      id: "u-9",
      email: "beto@empresa.com",
      nombre: "(invitación pendiente)",
      rol: "ADMINISTRADOR",
      estado: "INVITADO",
      invitacion_id: "i-9",
    };
    invitarUsuario.mockResolvedValue(nuevo);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " beto@empresa.com " } });
    fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "ADMINISTRADOR" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar invitación" }));

    await waitFor(() => {
      expect(invitado).toHaveBeenCalledWith(nuevo);
    });
    // Trimmed: a trailing space in an address is a typo, not a different person.
    expect(invitarUsuario).toHaveBeenCalledWith({
      email: "beto@empresa.com",
      rol: "ADMINISTRADOR",
    });
  });

  it("un email ya registrado se muestra tal como lo explica el backend", async () => {
    const { invitado } = montar();
    invitarUsuario.mockRejectedValue(
      new ErrorDeFormulario("Ese email ya tiene una cuenta. ¿Iniciar sesión?"),
    );

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ana@empresa.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar invitación" }));

    await waitFor(() => {
      expect(screen.getByText("Ese email ya tiene una cuenta. ¿Iniciar sesión?")).toBeDefined();
    });
    expect(invitado).not.toHaveBeenCalled();
  });

  it("cancelar cierra sin enviar nada", () => {
    const { cerrar } = montar();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(cerrar).toHaveBeenCalledOnce();
    expect(invitarUsuario).not.toHaveBeenCalled();
  });
});
