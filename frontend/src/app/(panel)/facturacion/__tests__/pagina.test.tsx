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
// Declarado junto a `redirect` y no mas abajo: `vi.mock` se iza por encima de todo el
// modulo, asi que una constante definida despues todavia no existe cuando el doble corre.
const notFound = vi.fn(() => {
  throw new Error("NOT_FOUND");
});

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");

vi.mock("next/navigation", () => ({
  redirect: () => redirect(),
  notFound: () => notFound(),
  // PAN-FAC-03 lleva al detalle despues de emitir. En SSR el router no existe, y sin este
  // doble el formulario ni siquiera se renderiza.
  useRouter: () => ({ push: vi.fn() }),
}));

const PaginaDePuntosDeVenta = (await import("@/app/(panel)/facturacion/puntos-de-venta/page"))
  .default;
const PaginaDeFacturacion = (await import("@/app/(panel)/facturacion/page")).default;
const PaginaDeComprobante = (await import("@/app/(panel)/facturacion/[comprobanteId]/page"))
  .default;
const PaginaDeNuevaEmision = (await import("@/app/(panel)/facturacion/nueva/page")).default;

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

const COMPROBANTE = {
  id: "c1",
  tipo: "FACTURA_A",
  estado: "AUTORIZADO",
  numero: 123,
  punto_de_venta_id: "p1",
  cliente_id: "cl1",
  receptor_nombre: "Acme SA",
  receptor_cuit: "30712345671",
  receptor_condicion_iva: "RESPONSABLE_INSCRIPTO",
  cae: "75123456789012",
  cae_vence_el: "2026-09-17",
  motivo_de_rechazo: null,
  subtotal: "2000.00",
  total_iva: "420.00",
  total: "2420.00",
  saldo_pendiente: "2420.00",
  fecha_emision: "2026-09-07T12:00:00Z",
  created_at: "2026-09-07T12:00:00Z",
  descargable: true,
  items: [],
};

describe("PaginaDeFacturacion (PAN-FAC-01)", () => {
  it("le da el boton de emitir al Administrador y al Operador", async () => {
    for (const rol of ["ADMINISTRADOR", "OPERADOR"]) {
      leerClaims.mockReturnValue({ ...CLAIMS_ADMIN, rol });
      llamarApi.mockResolvedValue({ comprobantes: [COMPROBANTE] });

      const html = renderToString(await PaginaDeFacturacion());

      expect(html).toContain("Emitir comprobante");
    }
  });

  it("a Solo Lectura le muestra el listado y ninguna accion (RN-04)", async () => {
    leerClaims.mockReturnValue({ ...CLAIMS_ADMIN, rol: "SOLO_LECTURA" });
    llamarApi.mockResolvedValue({ comprobantes: [COMPROBANTE] });

    const html = renderToString(await PaginaDeFacturacion());

    expect(html).not.toContain("Emitir comprobante");
    expect(html).toContain("Acme SA");
    // Los filtros siguen estando: la historia dice «ve y filtra».
    expect(html).toContain("Estado");
  });
});

describe("PaginaDeComprobante (PAN-FAC-02)", () => {
  it("muestra el CAE y su vencimiento", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      ruta.startsWith("/comprobantes") ? COMPROBANTE : { puntos: [PUNTO] },
    );

    const html = renderToString(await PaginaDeComprobante({ params: { comprobanteId: "c1" } }));

    expect(html).toContain("75123456789012");
    expect(html).toContain("0001-00000123");
  });

  it("un comprobante que no es de la empresa da 404 y no confirma que exista", async () => {
    // Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a proposito: distinguirlas
    // le diria a una empresa que el id de un comprobante ajeno es real.
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(422, "El comprobante no existe", "EntradaInvalida"));

    await expect(PaginaDeComprobante({ params: { comprobanteId: "c1" } })).rejects.toThrow(
      "NOT_FOUND",
    );
  });
});

describe("PaginaDeNuevaEmision (PAN-FAC-03)", () => {
  it("Solo Lectura ni siquiera ve el formulario", async () => {
    // El caso de uso lo rechaza igual; renderizar el formulario entero y contestar 403 en
    // Enviar le hace perder la tarde a alguien.
    leerClaims.mockReturnValue({ ...CLAIMS_ADMIN, rol: "SOLO_LECTURA" });

    await expect(PaginaDeNuevaEmision({ searchParams: {} })).rejects.toThrow("REDIRECT");
  });

  it("sin punto de venta activo explica por que y adonde ir", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ puntos: [{ ...PUNTO, activo: false }] });

    const html = renderToString(await PaginaDeNuevaEmision({ searchParams: {} }));

    expect(html).toContain("no hay numeraci");
    expect(html).toContain("/facturacion/puntos-de-venta");
  });

  it("sin cliente elegido manda a elegirlo", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const html = renderToString(await PaginaDeNuevaEmision({ searchParams: {} }));

    expect(html).toContain("/datos-maestros/clientes");
  });

  it("con todo listo renderiza el formulario, que arranca pidiendo el CUIT", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const html = renderToString(await PaginaDeNuevaEmision({ searchParams: { cliente: "cl1" } }));

    expect(html).toContain("CUIT del receptor");
    // Nada mas: el resto se habilita cuando ARCA contesta.
    expect(html).not.toContain("Tipo de comprobante");
  });
});
