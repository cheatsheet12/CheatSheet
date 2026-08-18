/**
 * @vitest-environment jsdom
 *
 * PAN-USR-01 — casos 38 y 40.
 *
 * The role check here is **cosmetic** and the test says so: what actually refuses an
 * Operador is the backend, and `test_un_operador_recibe_403_al_administrar_usuarios`
 * proves that against a real database. What this file proves is the other half — that
 * the panel does not offer an action that is going to be rejected.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const cambiarRol = vi.fn();
const desactivarUsuario = vi.fn();
const reactivarUsuario = vi.fn();
const reenviarInvitacion = vi.fn();
const revocarInvitacion = vi.fn();

vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return {
    ...real,
    cambiarRol: (...args: unknown[]) => cambiarRol(...args),
    desactivarUsuario: (...args: unknown[]) => desactivarUsuario(...args),
    reactivarUsuario: (...args: unknown[]) => reactivarUsuario(...args),
    reenviarInvitacion: (...args: unknown[]) => reenviarInvitacion(...args),
    revocarInvitacion: (...args: unknown[]) => revocarInvitacion(...args),
  };
});

import type { RolUsuario, UsuarioDeLaEmpresa } from "@/features/identity";

const { TablaDeUsuarios } = await import("@/features/identity/components/TablaDeUsuarios");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

const ANA: UsuarioDeLaEmpresa = {
  id: "u-1",
  email: "ana@empresa.com",
  nombre: "Ana Perez",
  rol: "ADMINISTRADOR" as const,
  estado: "ACTIVO" as const,
  invitacion_id: null,
};

const BETO: UsuarioDeLaEmpresa = {
  id: "u-2",
  email: "beto@empresa.com",
  nombre: "Beto Gomez",
  rol: "OPERADOR" as const,
  estado: "ACTIVO" as const,
  invitacion_id: null,
};

const PENDIENTE: UsuarioDeLaEmpresa = {
  id: "u-3",
  email: "carla@empresa.com",
  nombre: "(invitación pendiente)",
  rol: "OPERADOR" as const,
  estado: "INVITADO" as const,
  invitacion_id: "i-1",
};

const INACTIVO: UsuarioDeLaEmpresa = {
  ...BETO,
  id: "u-4",
  email: "dario@empresa.com",
  estado: "INACTIVO",
};

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function montar(rol: RolUsuario, filas: readonly UsuarioDeLaEmpresa[] = [ANA, BETO]): void {
  render(<TablaDeUsuarios usuarios={filas} rolDelUsuarioActual={rol} usuarioActualId={ANA.id} />);
}

describe("caso 38 — el rol gobierna lo que se ve", () => {
  it("un Operador ve la lista completa y ninguna acción", () => {
    montar("OPERADOR");

    // HU-E1-05's third criterion: they are *in* the section, looking at the list.
    expect(screen.getByText("Ana Perez")).toBeDefined();
    expect(screen.getByText("Beto Gomez")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Invitar usuario" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desactivar" })).toBeNull();
    expect(screen.queryByLabelText(/^Rol de/)).toBeNull();
  });

  it("un Solo Lectura tampoco puede cambiar un rol", () => {
    montar("SOLO_LECTURA");

    expect(screen.queryByLabelText(/^Rol de/)).toBeNull();
  });

  it("un Administrador sí ve las acciones", () => {
    montar("ADMINISTRADOR");

    expect(screen.getByRole("button", { name: "Invitar usuario" })).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Desactivar" })).toHaveLength(2);
    expect(screen.getByLabelText("Rol de Beto Gomez")).toBeDefined();
  });

  it("una invitación pendiente ofrece reenviar y revocar, no desactivar", () => {
    montar("ADMINISTRADOR", [ANA, PENDIENTE]);

    expect(screen.getByRole("button", { name: "Reenviar" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Revocar" })).toBeDefined();
    expect(screen.getByText("Invitación pendiente")).toBeDefined();
    // A pending invitation is revoked, never deactivated — the aggregate refuses it too.
    expect(screen.getAllByRole("button", { name: "Desactivar" })).toHaveLength(1);
  });

  it("un usuario inactivo ofrece reactivar", () => {
    montar("ADMINISTRADOR", [ANA, INACTIVO]);

    expect(screen.getByRole("button", { name: "Reactivar" })).toBeDefined();
  });
});

describe("caso 40 — desactivar pide confirmación", () => {
  it("si se cancela, no llama a la API", () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    montar("ADMINISTRADOR");

    fireEvent.click(screen.getAllByRole("button", { name: "Desactivar" })[1]!);

    expect(desactivarUsuario).not.toHaveBeenCalled();
  });

  it("si se confirma, desactiva y lo dice", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    desactivarUsuario.mockResolvedValue({ ...BETO, estado: "INACTIVO" });
    montar("ADMINISTRADOR");

    fireEvent.click(screen.getAllByRole("button", { name: "Desactivar" })[1]!);

    await waitFor(() => {
      expect(screen.getByText("Beto Gomez ya no tiene acceso.")).toBeDefined();
    });
    expect(desactivarUsuario).toHaveBeenCalledWith(BETO.id);
  });

  it("revocar una invitación también pregunta antes", () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    montar("ADMINISTRADOR", [ANA, PENDIENTE]);

    fireEvent.click(screen.getByRole("button", { name: "Revocar" }));

    expect(revocarInvitacion).not.toHaveBeenCalled();
  });
});

describe("las respuestas del backend llegan al usuario", () => {
  it("el último administrador no se puede degradar, y se explica por qué", async () => {
    cambiarRol.mockRejectedValue(
      new ErrorDeFormulario("La empresa debe conservar al menos un Administrador activo."),
    );
    montar("ADMINISTRADOR");

    fireEvent.change(screen.getByLabelText("Rol de Ana Perez"), {
      target: { value: "OPERADOR" },
    });

    await waitFor(() => {
      expect(
        screen.getByText("La empresa debe conservar al menos un Administrador activo."),
      ).toBeDefined();
    });
  });

  it("cambiar un rol actualiza la fila sin recargar", async () => {
    cambiarRol.mockResolvedValue({ ...BETO, rol: "SOLO_LECTURA" });
    montar("ADMINISTRADOR");

    fireEvent.change(screen.getByLabelText("Rol de Beto Gomez"), {
      target: { value: "SOLO_LECTURA" },
    });

    await waitFor(() => {
      expect((screen.getByLabelText("Rol de Beto Gomez") as HTMLSelectElement).value).toBe(
        "SOLO_LECTURA",
      );
    });
  });

  it("revocar saca la fila, porque el email queda libre", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    revocarInvitacion.mockResolvedValue(undefined);
    montar("ADMINISTRADOR", [ANA, PENDIENTE]);

    fireEvent.click(screen.getByRole("button", { name: "Revocar" }));

    await waitFor(() => {
      expect(screen.queryByText("carla@empresa.com")).toBeNull();
    });
  });
});
