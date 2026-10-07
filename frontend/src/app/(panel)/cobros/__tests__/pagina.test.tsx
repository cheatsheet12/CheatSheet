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
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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

const CLIENTE = {
  id: "cl1",
  nombre: "Panaderia Dona Rosa",
  cuit: "30-71234567-1",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  contacto_whatsapp: null,
  contacto_email: null,
  origen: "PANEL",
  activo: true,
};

const COBRO = {
  id: "co1",
  cliente_id: "cl1",
  comprobante_id: null,
  turno_id: null,
  monto: "12500.00",
  monto_reembolsado: "0.00",
  descripcion: "Consulta de septiembre",
  estado: "APROBADO",
  url_de_pago: null,
  tiene_link_activo: false,
  vence_el: "2026-09-20",
  fecha_pago: "2026-09-15T18:20:00Z",
  fecha_pago_aproximada: false,
  medio_de_pago: "LINK_MERCADOPAGO",
  numero_de_operacion: null,
  reembolso_en_proceso: false,
  reembolso_en_proceso_monto: null,
  motivo_de_cancelacion: null,
  created_at: "2026-09-07T12:00:00Z",
  recordatorios: [],
  reembolsos: [],
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
    expect(renderToString(await PaginaDeCobros())).toContain("Nuevo cobro");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    expect(renderToString(await PaginaDeCobros())).not.toContain("Nuevo cobro");
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

  it("sin cliente muestra el selector y el formulario, ya no «Falta elegir el cliente»", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: {} }));

    expect(html).toContain("Buscar cliente por nombre o CUIT");
    expect(html).toContain("Generar link de pago");
    expect(html).toContain("Debe seleccionar un cliente.");
    expect(html).not.toContain("Falta elegir el cliente");
    // Sin cliente no hay comprobantes que ofrecer, asi que no se le pregunta nada al backend.
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("con un cliente lo muestra preseleccionado, y editable, sin el aviso de falta", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation(async (ruta: string) =>
      ruta === "/clientes/cl1" ? CLIENTE : { comprobantes: [] },
    );

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/clientes/cl1");
    expect(html).toContain("Cliente seleccionado");
    expect(html).toContain("Panaderia Dona Rosa");
    expect(html).toContain("Buscar cliente por nombre o CUIT");
    expect(html).not.toContain("Debe seleccionar un cliente.");
  });

  it.each([
    ["no existe", new ErrorDeApi(422, "No existe el cliente", "ClienteNoEncontrado")],
    ["no es de esta empresa", new ErrorDeApi(404, "No existe", "ClienteNoEncontrado")],
  ])("un cliente que %s se trata como sin cliente y se avisa", async (_caso, fallo) => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(fallo);

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: { cliente: "viejo" } }));

    expect(html).toContain("El cliente indicado no existe o está inactivo.");
    expect(html).toContain("Debe seleccionar un cliente.");
    // Ni siquiera pide comprobantes de alguien que no existe.
    expect(llamarApi).toHaveBeenCalledTimes(1);
  });

  it("un cliente inactivo se trata como sin cliente y se avisa", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockResolvedValue({ ...CLIENTE, activo: false });

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } }));

    expect(html).toContain("El cliente indicado no existe o está inactivo.");
    expect(html).toContain("Debe seleccionar un cliente.");
  });

  it("un fallo del backend que no es «no existe» no se disfraza de cliente vacio", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(500, "Se cayo", "ErrorInterno"));

    await expect(PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } })).rejects.toThrow(
      ErrorDeApi,
    );
  });

  it("ofrece solo los comprobantes con saldo del cliente elegido (HU-E6-06)", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation(async (ruta: string) =>
      ruta === "/clientes/cl1"
        ? CLIENTE
        : {
            comprobantes: [
              {
                id: "c1",
                cliente_id: "cl1",
                tipo: "FACTURA_B",
                numero: 123,
                saldo_pendiente: "2420.00",
              },
              // Saldado: no tiene nada que cobrar, asi que no se ofrece.
              {
                id: "c2",
                cliente_id: "cl1",
                tipo: "FACTURA_B",
                numero: 124,
                saldo_pendiente: "0.00",
              },
              // Con saldo, pero de otro cliente: cobrarlo seria cobrar una deuda ajena.
              {
                id: "c3",
                cliente_id: "cl2",
                tipo: "FACTURA_B",
                numero: 125,
                saldo_pendiente: "900.00",
              },
            ],
          },
    );

    const html = renderToString(await PaginaDeNuevoCobro({ searchParams: { cliente: "cl1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/comprobantes?estado=AUTORIZADO");
    expect(html).toContain("Factura B 123");
    expect(html).not.toContain("Factura B 124");
    expect(html).not.toContain("Factura B 125");
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
