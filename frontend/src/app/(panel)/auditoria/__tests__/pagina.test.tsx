/**
 * @vitest-environment jsdom
 *
 * PAN-LOG-02 como *página* (HU-E12-02): el responsable se resuelve del lado del servidor (#169).
 *
 * La bitácora guarda sólo el id del usuario —nunca datos personales, D72—, así que el nombre y
 * el email salen de los usuarios de la empresa. Si no se pueden leer, la página sigue en pie y
 * muestra el id.
 */

import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

vi.mock("next/navigation", () => ({
  redirect: () => {
    throw new Error("REDIRECT");
  },
}));

const { ErrorDeApi } = await import("@/lib/api");
const PaginaDeDetalle = (await import("@/app/(panel)/auditoria/[operacionId]/page")).default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };

const DETALLE = {
  operacion: {
    id: "op1",
    timestamp: "2026-10-12T19:26:52Z",
    modulo: "scheduling",
    accion: "cargar_turno_a_posteriori",
    entidad_afectada: "Turno:t1",
    iniciador: "usuario",
    resultado: "completado",
    usuario_id: "u-1",
  },
  timeline: [],
  duracion_ms: null,
  detalle: {},
  paso_con_error: null,
};

const USUARIOS = [
  {
    id: "u-1",
    email: "admin.gomez@estudio-ejemplo.test",
    nombre: "Administración Ejemplo",
    rol: "ADMINISTRADOR",
    estado: "ACTIVO",
    invitacion_id: null,
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDeDetalle", () => {
  it("muestra el nombre y el email del responsable", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      Promise.resolve(ruta === "/usuarios" ? USUARIOS : DETALLE),
    );

    const html = renderToString(await PaginaDeDetalle({ params: { operacionId: "op1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/usuarios");
    expect(html).toContain("Administración Ejemplo · admin.gomez@estudio-ejemplo.test");
  });

  it("sigue en pie y muestra el id si los usuarios no se pudieron leer", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      ruta === "/usuarios"
        ? Promise.reject(new ErrorDeApi(500, "Se cayó", "ErrorInterno"))
        : Promise.resolve(DETALLE),
    );

    const html = renderToString(await PaginaDeDetalle({ params: { operacionId: "op1" } }));

    expect(html).toContain("cargar_turno_a_posteriori");
    expect(html).toContain("u-1");
    expect(html).not.toContain("admin.gomez@estudio-ejemplo.test");
  });
});
