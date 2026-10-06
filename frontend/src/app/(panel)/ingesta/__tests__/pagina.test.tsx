/**
 * @vitest-environment jsdom
 *
 * PAN-ING-01 como *página* (HU-E2-04, HU-E3-03).
 *
 * Sigue el patrón que dejó `datos-maestros/__tests__/paginas.test.tsx`, y prueba lo mismo
 * que aquel: el redirect sin sesión, y el mapeo de rol a `puedeEditar`.
 *
 * Acá el mapeo es **más estricto** que en Datos Maestros y por eso vale la pena mirarlo:
 * el actor de HU-E2-04 es el Administrador y nadie más, así que un Operador —que en
 * clientes y servicios sí escribe— acá sólo mira.
 */

import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();
const redirect = vi.fn(() => {
  throw new Error("REDIRECT");
});

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

// The page renders `IngestaDePlanillas`, which reads the router through
// `useAccionConNavegacion`; it only needs to exist, nothing here navigates.
vi.mock("next/navigation", () => ({
  redirect: () => redirect(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

const PaginaDeIngesta = (await import("@/app/(panel)/ingesta/page")).default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDeIngesta", () => {
  it("redirige cuando no hay sesion, y no llama a la API", async () => {
    leerClaims.mockReturnValue(null);

    await expect(PaginaDeIngesta()).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("lee el listado con la cookie de sesion", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      ruta === "/planillas" ? { vinculos: [] } : { cargas: [] },
    );

    renderToString(await PaginaDeIngesta());

    // Las dos lecturas van en paralelo: la pantalla necesita las dos para su primer render.
    expect(llamarApi).toHaveBeenCalledWith("/planillas");
    expect(llamarApi).toHaveBeenCalledWith("/planillas/cargas");
  });

  it("le da la zona de carga al Administrador", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      ruta === "/planillas" ? { vinculos: [] } : { cargas: [] },
    );

    const html = renderToString(await PaginaDeIngesta());

    expect(html).toContain("Arrastr");
    expect(html).toContain("Vincular Google Sheets");
  });

  it.each(["OPERADOR", "SOLO_LECTURA"])(
    "no le ofrece vincular a un %s, aunque vea el listado",
    async (rol) => {
      leerClaims.mockReturnValue({ ...CLAIMS_ADMIN, rol });
      llamarApi.mockImplementation((ruta: string) =>
        ruta === "/planillas" ? { vinculos: [] } : { cargas: [] },
      );

      const html = renderToString(await PaginaDeIngesta());

      expect(html).not.toContain("Vincular Google Sheets");
      expect(html).not.toContain("Arrastr");
      // Pero la pantalla se renderiza y el listado esta: HU-E3-05 RN-04 le da derecho a
      // mirar. Se afirma sobre el vacio de la tabla y no sobre el titulo «Cargas
      // recientes» porque `Tabla` descarta su caption cuando no hay filas -- defecto del
      // sistema de diseno, anotado en `TODO.md`, no de esta pantalla.
      expect(html).toContain("Todavia no vinculaste ninguna planilla");
    },
  );
});
