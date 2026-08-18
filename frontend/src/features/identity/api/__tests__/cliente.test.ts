/**
 * What the screens call, and what they are told when it fails.
 *
 * Two properties are under test. First, each function hits **this app's** BFF and never
 * the backend directly — the whole point of the BFF is that the browser holds no token,
 * and a `fetch` pointed at the API would quietly undo that. Second, the backend's error
 * *code* becomes Spanish product copy here: the API speaks in exception names, and the
 * person reading the screen does not.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

// Relative, not `@/features/identity/api/cliente`: that alias means "somebody outside
// reaching in", which R5 forbids. A module's own test is not that.
import {
  ErrorDeFormulario,
  aceptarInvitacion,
  cambiarRol,
  desactivarUsuario,
  guardarPreferencias,
  invitarUsuario,
  listarUsuarios,
  reactivarUsuario,
  reenviarInvitacion,
  revocarInvitacion,
  verPreferencias,
} from "../cliente";

const fetchFalso = vi.fn();
vi.stubGlobal("fetch", fetchFalso);

function responde(cuerpo: unknown, status = 200): void {
  fetchFalso.mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => cuerpo,
  });
}

function llamada(): { readonly ruta: string; readonly opciones: Record<string, unknown> } {
  const [ruta, opciones] = fetchFalso.mock.calls[0] as [string, Record<string, unknown>];
  return { ruta, opciones: opciones ?? {} };
}

afterEach(() => {
  fetchFalso.mockReset();
});

describe("las rutas apuntan al BFF y no a la API", () => {
  it("listar usuarios", async () => {
    responde([]);

    await listarUsuarios();

    expect(llamada().ruta).toBe("/api/usuarios");
  });

  it("invitar", async () => {
    responde({});

    await invitarUsuario({ email: "beto@empresa.com", rol: "OPERADOR" });

    expect(llamada().ruta).toBe("/api/usuarios/invitaciones");
    expect(llamada().opciones.method).toBe("POST");
  });

  it("reenviar y revocar usan el id de la invitación, no el del usuario", async () => {
    responde({});
    await reenviarInvitacion("i-1");
    expect(llamada().ruta).toBe("/api/usuarios/invitaciones/i-1/reenvio");

    fetchFalso.mockReset();
    responde({});
    await revocarInvitacion("i-1");
    expect(llamada().ruta).toBe("/api/usuarios/invitaciones/i-1");
    expect(llamada().opciones.method).toBe("DELETE");
  });

  it("cambiar el rol va por PATCH", async () => {
    responde({});

    await cambiarRol("u-1", "SOLO_LECTURA");

    expect(llamada().ruta).toBe("/api/usuarios/u-1/rol");
    expect(llamada().opciones.method).toBe("PATCH");
    expect(llamada().opciones.body).toBe(JSON.stringify({ rol: "SOLO_LECTURA" }));
  });

  it("desactivar y reactivar son acciones, no borrados", async () => {
    responde({});
    await desactivarUsuario("u-1");
    expect(llamada().ruta).toBe("/api/usuarios/u-1/desactivacion");

    fetchFalso.mockReset();
    responde({});
    await reactivarUsuario("u-1");
    expect(llamada().ruta).toBe("/api/usuarios/u-1/reactivacion");
  });

  it("las preferencias no llevan id de usuario en la ruta", async () => {
    responde({ pref_idioma: "es-AR" });

    await verPreferencias();

    // A path that took an id would be a path for editing somebody else's settings.
    expect(llamada().ruta).toBe("/api/usuarios/preferencias");

    fetchFalso.mockReset();
    responde({});
    await guardarPreferencias({ pref_idioma: "es-AR" });
    expect(llamada().opciones.method).toBe("PUT");
  });

  it("aceptar una invitación es público y va por /api/auth", async () => {
    responde({ onboarding_completo: false });

    await aceptarInvitacion({ token: "t", nombre: "Beto", contrasena: "12345678" });

    expect(llamada().ruta).toBe("/api/auth/invitaciones/aceptar");
  });
});

describe("los códigos del backend se vuelven copy en español", () => {
  it.each([
    ["PermisoDenegado", "Tu rol no permite esta acción."],
    ["UltimoAdministradorActivo", "La empresa debe conservar al menos un Administrador activo."],
    ["InvitacionInvalida", "Esta invitación no es válida o ya fue utilizada."],
    ["EmailYaRegistrado", "Ese email ya tiene una cuenta. ¿Iniciar sesión?"],
  ])("%s", async (codigo, mensaje) => {
    responde({ error: codigo }, 409);

    await expect(listarUsuarios()).rejects.toThrow(ErrorDeFormulario);
    await expect(listarUsuarios()).rejects.toThrow(mensaje);
  });

  it("un error de validación muestra el detalle que manda el backend", async () => {
    responde({ error: "EntradaInvalida", detalle: "El usuario no existe en esta empresa" }, 422);

    await expect(listarUsuarios()).rejects.toThrow("El usuario no existe en esta empresa");
  });

  it("un 500 no muestra internals, muestra qué hacer", async () => {
    responde({ error: "ErrorInterno", incidente: "abc" }, 500);

    await expect(listarUsuarios()).rejects.toThrow(
      "No pudimos completar la operación. Probá de nuevo en unos minutos.",
    );
  });

  it("una respuesta sin JSON tampoco rompe la pantalla", async () => {
    fetchFalso.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error("no es JSON");
      },
    });

    await expect(listarUsuarios()).rejects.toThrow(ErrorDeFormulario);
  });
});
