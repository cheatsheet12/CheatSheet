/**
 * @vitest-environment jsdom
 *
 * Las tres páginas de cobros como *páginas* (HU-E6-01 … HU-E6-06).
 *
 * Mismo patrón que las del épico 5: el redirect sin sesión y el mapeo de rol a permisos. Dos
 * cosas propias de este épico se prueban acá y no en los componentes, porque son del servidor:
 *
 * - **Solo Lectura no llega al formulario de alta.** El caso de uso lo rechaza igual, pero
 *   renderizarle el formulario entero para contestarle 403 en «Generar» le hace perder la
 *   tarde a alguien;
 * - **el filtro de comprobantes con saldo** (HU-E6-06). Es una regla de la historia, y por eso
 *   se aplica del lado del servidor y no como una preferencia de la pantalla.
 */

import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();
const redirect = vi.fn(() => {
  throw new Error("REDIRECT");
});
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
  // PAN-COB-03 lleva al detalle despues de generar. En SSR el router no existe, y sin este
  // doble el formulario ni siquiera se renderiza.
  useRouter: () => ({ push: vi.fn() }),
}));

const PaginaDeCobros = (await import("@/app/(panel)/cobros/page")).default;
const PaginaDeCobro = (await import("@/app/(panel)/cobros/[cobroId]/page")).default;
const PaginaDeNuevoCobro = (await import("@/app/(panel)/cobros/nuevo/page")).default;
const PaginaDeReglas = (await import("@/app/(panel)/configuracion/reglas/page")).default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };
const CLAIMS_OPERADOR = { ...CLAIMS_ADMIN, rol: "OPERADOR" };
const CLAIMS_LECTURA = { ...CLAIMS_ADMIN, rol: "SOLO_LECTURA" };

const METRICAS = {
  cobrado: "45000.00",
  pendiente: "12500.00",
  en_mora: "8000.00",
  tasa_de_cobro: "68.75",
};

const COBRO = {
  id: "co1",
  cliente_id: "cl1",
  comprobante_id: null,
  turno_id: null,
  monto: "12500.00",
  monto_reembolsado: null,
  descripcion: "Consulta de septiembre",
  estado: "APROBADO",
  url_de_pago: null,
  tiene_link_activo: false,
  vence_el: "2026-09-20",
  pagado_en: "2026-09-15T18:20:00Z",
  reembolso_en_proceso: false,
  motivo_de_cancelacion: null,
  created_at: "2026-09-07T12:00:00Z",
  recordatorios: [],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDeCobros", () => {
  it("redirige sin sesion y no le pregunta nada al backend", async () => {
    leerClaims.mockReturnValue(null);
    await expect(PaginaDeCobros()).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("le da gestion al Operador y se la niega a Solo Lectura", async () => {
    llamarApi.mockResolvedValue({ cobros: [], metricas: METRICAS });

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    expect(renderToString(await PaginaDeCobros())).toContain("Generar cobro");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    expect(renderToString(await PaginaDeCobros())).not.toContain("Generar cobro");
  });
});

describe("PaginaDeCobro", () => {
  it("contesta 404 cuando el cobro no es de esta empresa", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(404, "No existe", "CobroInexistente"));

    // Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a proposito.
    await expect(PaginaDeCobro({ params: { cobroId: "ajeno" } })).rejects.toThrow("NOT_FOUND");
  });

  it("deja pasar un fallo del backend en vez de disfrazarlo de 404", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(500, "Se cayo", "ErrorInterno"));

    await expect(PaginaDeCobro({ params: { cobroId: "co1" } })).rejects.toThrow(ErrorDeApi);
    expect(notFound).not.toHaveBeenCalled();
  });

  it("solo el Administrador ve «Reembolsar» (RN-05)", async () => {
    llamarApi.mockResolvedValue(COBRO);

    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    const conAdmin = renderToString(await PaginaDeCobro({ params: { cobroId: "co1" } }));
    expect(conAdmin).toContain("Reembolsar");

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const conOperador = renderToString(await PaginaDeCobro({ params: { cobroId: "co1" } }));
    expect(conOperador).not.toContain("Reembolsar");
  });
});

describe("PaginaDeNuevoCobro", () => {
  it("saca a Solo Lectura antes de renderizar el formulario", async () => {
    leerClaims.mockReturnValue(CLAIMS_LECTURA);

    await expect(PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } })).rejects.toThrow(
      "REDIRECT",
    );
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("pide elegir un cliente antes que nada", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: {} }));
    expect(html).toContain("Elegí primero a quién le vas a cobrar");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("ofrece solo los comprobantes con saldo pendiente (HU-E6-06)", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({
      comprobantes: [
        { id: "c1", tipo: "FACTURA_B", numero: 123, saldo_pendiente: "2420.00" },
        // Saldado: no tiene nada que cobrar, asi que no se ofrece.
        { id: "c2", tipo: "FACTURA_B", numero: 124, saldo_pendiente: "0.00" },
      ],
    });

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/comprobantes?estado=AUTORIZADO");
    expect(html).toContain("Factura B 123");
    expect(html).not.toContain("Factura B 124");
  });
});

describe("PaginaDeReglas", () => {
  it("le muestra las reglas a todos y el editor solo al Administrador", async () => {
    llamarApi.mockResolvedValue({ reglas: [] });

    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    expect(renderToString(await PaginaDeReglas())).toContain("Cadena de recordatorios");

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const conOperador = renderToString(await PaginaDeReglas());
    expect(conOperador).toContain("Reglas de negocio");
    expect(conOperador).not.toContain("Cadena de recordatorios");
  });
});
