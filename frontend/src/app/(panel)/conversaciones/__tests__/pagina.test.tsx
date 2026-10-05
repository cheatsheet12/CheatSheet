/**
 * @vitest-environment jsdom
 *
 * Las cuatro páginas del canal conversacional como *páginas*.
 *
 * Mismo patrón que las de los épicos anteriores: el redirect sin sesión y el mapeo de rol a
 * permisos. Dos cosas propias de este épico se prueban acá y no en los componentes:
 *
 * - **La bandeja arranca filtrada por escaladas.** Lo decide la página, así que sólo se ve
 *   desde el servidor.
 * - **El teléfono del cliente se resuelve del lado del servidor**, y **un fallo al resolverlo
 *   no deja sin pantalla a nadie**: el hilo se lee igual, con el campo de respuesta vacío. Un
 *   `throw` ahí sería perder el historial completo por un dato que sólo hace falta para
 *   responder.
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
  useRouter: () => ({ push: vi.fn() }),
}));

const PaginaDeConversaciones = (await import("@/app/(panel)/conversaciones/page")).default;
const PaginaDeConversacion = (await import("@/app/(panel)/conversaciones/[conversacionId]/page"))
  .default;
const PaginaDeFaqs = (await import("@/app/(panel)/configuracion/respuestas/page")).default;
const PaginaDePlantillas = (await import("@/app/(panel)/configuracion/plantillas/page")).default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };
const CLAIMS_OPERADOR = { ...CLAIMS_ADMIN, rol: "OPERADOR" };
const CLAIMS_LECTURA = { ...CLAIMS_ADMIN, rol: "SOLO_LECTURA" };

const HILO = {
  id: "c1",
  cliente_id: "cl1",
  estado: "ACTIVA",
  ultimo_mensaje_en: "2026-09-08T18:00:00+00:00",
  esta_escalada: true,
  escalamiento_id: "e1",
  motivo: "El agente no interpretó la intención con confianza suficiente",
  estado_escalamiento: "ABIERTO",
  usuario_asignado_id: null,
  mensajes: [
    {
      id: "m1",
      direccion: "ENTRANTE",
      tipo_contenido: "TEXTO",
      contenido: "hola, quiero un turno",
      momento: "2026-09-08T18:00:00+00:00",
      intencion: "TURNO",
      estado_entrega: null,
      origen: null,
    },
  ],
};

const FAQ = {
  id: "f1",
  pregunta: "¿Cuánto sale un corte?",
  respuesta: "Sale $8000.",
  usos: 3,
  sin_indexar: false,
};

const PLANTILLA = {
  id: "p1",
  codigo: "recordatorio_de_turno",
  canal: "WHATSAPP",
  idioma: "es_AR",
  cuerpo: "Hola {{nombre}}.",
  estado_aprobacion: "APROBADA",
  variables: ["nombre", "fecha"],
  puede_usarse: true,
};

/** Contesta según la ruta: estas páginas piden dos cosas distintas cada una. */
function porRuta(ruta: string): unknown {
  if (ruta.startsWith("/conversaciones/")) {
    return HILO;
  }
  if (ruta.startsWith("/conversaciones")) {
    return { conversaciones: [HILO] };
  }
  if (ruta.startsWith("/faqs")) {
    return { faqs: [FAQ] };
  }
  return { plantillas: [PLANTILLA] };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDeConversaciones", () => {
  it("redirige sin sesion y no le pregunta nada al backend", async () => {
    leerClaims.mockReturnValue(null);
    await expect(PaginaDeConversaciones()).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("arranca filtrada por las que esperan a un asesor", async () => {
    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    renderToString(await PaginaDeConversaciones());

    expect(llamarApi).toHaveBeenCalledWith("/conversaciones?solo_escaladas=true");
  });

  it("le avisa a Solo Lectura que no puede atender", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    expect(renderToString(await PaginaDeConversaciones())).not.toContain("no atenderlas");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    expect(renderToString(await PaginaDeConversaciones())).toContain("no atenderlas");
  });
});

describe("PaginaDeConversacion", () => {
  it("contesta 404 cuando el hilo no es de esta empresa", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(422, "No existe", "ConversacionInexistente"));

    await expect(PaginaDeConversacion({ params: { conversacionId: "ajeno" } })).rejects.toThrow(
      "NOT_FOUND",
    );
  });

  it("deja pasar un fallo del backend en vez de disfrazarlo de 404", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(500, "Se cayo", "ErrorInterno"));

    await expect(PaginaDeConversacion({ params: { conversacionId: "c1" } })).rejects.toThrow(
      ErrorDeApi,
    );
    expect(notFound).not.toHaveBeenCalled();
  });

  it("no le pide nada a /clientes: el teléfono ya no lo maneja la pantalla", async () => {
    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    const html = renderToString(await PaginaDeConversacion({ params: { conversacionId: "c1" } }));

    expect(html).toContain("hola, quiero un turno");
    const rutas = llamarApi.mock.calls.map(([ruta]) => ruta as string);
    expect(rutas.some((ruta) => ruta.startsWith("/clientes/"))).toBe(false);
  });

  it("le esconde las acciones a Solo Lectura", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const conOperador = renderToString(
      await PaginaDeConversacion({ params: { conversacionId: "c1" } }),
    );
    expect(conOperador).toContain("Tomar la conversación");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    const conLectura = renderToString(
      await PaginaDeConversacion({ params: { conversacionId: "c1" } }),
    );
    expect(conLectura).not.toContain("Tomar la conversación");
  });
});

describe("PaginaDeFaqs y PaginaDePlantillas", () => {
  it("le muestran el listado a todos y la edicion solo al Administrador", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    expect(renderToString(await PaginaDeFaqs())).toContain("Agregar respuesta");
    expect(renderToString(await PaginaDePlantillas())).toContain("Editar texto");

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const faqs = renderToString(await PaginaDeFaqs());
    expect(faqs).toContain("¿Cuánto sale un corte?");
    expect(faqs).not.toContain("Agregar respuesta");
    expect(renderToString(await PaginaDePlantillas())).not.toContain("Editar texto");
  });

  it("redirigen sin sesion", async () => {
    leerClaims.mockReturnValue(null);
    await expect(PaginaDeFaqs()).rejects.toThrow("REDIRECT");
    await expect(PaginaDePlantillas()).rejects.toThrow("REDIRECT");
  });
});
