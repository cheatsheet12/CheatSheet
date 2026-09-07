/**
 * @vitest-environment jsdom
 *
 * PAN-FAC-05 como *página* (HU-E5-05).
 *
 * Mismo patrón que las páginas del épico 4: el redirect sin sesión y el mapeo de rol a
 * `puedeEditar`. Acá el mapeo es tan estricto como el de Ingesta y por la misma razón —el
 * actor de la historia es el Administrador y nadie más—, con un agregado: un Operador que
 * no puede tocar los puntos de venta **sí** va a emitir comprobantes con ellos, así que
 * ver el listado no es una concesión, es lo que necesita para saber con qué numeración
 * está trabajando.
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

vi.mock("next/navigation", () => ({ redirect: () => redirect() }));

const PaginaDePuntosDeVenta = (await import("@/app/(panel)/facturacion/puntos-de-venta/page"))
  .default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };

const PUNTO = {
  id: "p1",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: { FACTURA_B: 12 },
  created_at: "2026-09-07T12:00:00Z",
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDePuntosDeVenta", () => {
  it("redirige cuando no hay sesion, y no llama a la API", async () => {
    leerClaims.mockReturnValue(null);

    await expect(PaginaDePuntosDeVenta()).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("lee el listado con la cookie de sesion", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const html = renderToString(await PaginaDePuntosDeVenta());

    expect(llamarApi).toHaveBeenCalledWith("/puntos-de-venta");
    expect(html).toContain("0001");
    expect(html).toContain("Casa central");
  });

  it("le da el alta al Administrador", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const html = renderToString(await PaginaDePuntosDeVenta());

    expect(html).toContain("Agregar punto de venta");
    expect(html).toContain("Desactivar");
  });

  it.each(["OPERADOR", "SOLO_LECTURA"])("a un %s le muestra el listado y nada mas", async (rol) => {
    leerClaims.mockReturnValue({ ...CLAIMS_ADMIN, rol });
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const html = renderToString(await PaginaDePuntosDeVenta());

    expect(html).not.toContain("Agregar punto de venta");
    expect(html).not.toContain("Desactivar");
    // Pero ve con qué numeración está trabajando, que es para lo que va a entrar.
    expect(html).toContain("Casa central");
    expect(html).toContain("Factura B: 12");
  });
});
