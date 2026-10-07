/**
 * La frontera del BFF para el canal conversacional.
 *
 * Las dos propiedades de siempre —ninguna ruta llega al backend sin sesión, y el query string
 * se reenvía entero— más las tres que son de esta unidad:
 *
 * - **No hay `DELETE` de conversaciones ni de escalamientos.** Una conversación es el registro
 *   de lo que se le dijo a un cliente, y un escalamiento cerrado es un caso atendido.
 * - **`/faqs/[faqId]` sí tiene `DELETE`, y es el único del producto que borra de verdad.**
 * - **Las plantillas no tienen alta ni baja**: los códigos los define el sistema.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

let cookieDeSesion: string | undefined;

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" && cookieDeSesion !== undefined
        ? { name: nombre, value: cookieDeSesion }
        : undefined,
    set: () => undefined,
    delete: () => undefined,
  }),
}));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");
const rutaConversaciones = await import("@/app/api/conversaciones/route");
const rutaHilo = await import("@/app/api/conversaciones/[conversacionId]/route");
const rutaMensajes = await import("@/app/api/conversaciones/[conversacionId]/mensajes/route");
const rutaToma = await import("@/app/api/escalamientos/[escalamientoId]/toma/route");
const rutaCierre = await import("@/app/api/escalamientos/[escalamientoId]/cierre/route");
const rutaFaqs = await import("@/app/api/faqs/route");
const rutaFaq = await import("@/app/api/faqs/[faqId]/route");
const rutaUsoDeFaq = await import("@/app/api/faqs/[faqId]/uso/route");
const rutaPlantillas = await import("@/app/api/plantillas/route");
const rutaPlantilla = await import("@/app/api/plantillas/[plantillaId]/route");
const rutaEnvioDePlantilla = await import("@/app/api/plantillas/[plantillaId]/envio/route");

function pedido(cuerpo: unknown = {}, metodo = "POST"): Request {
  return new Request("http://test/api/conversaciones", {
    method: metodo,
    body: JSON.stringify(cuerpo),
  });
}

function lectura(consulta = ""): Request {
  return new Request(`http://test/api/conversaciones${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaConversaciones.GET(lectura()),
      rutaHilo.GET(lectura(), { params: { conversacionId: "c1" } }),
      rutaMensajes.POST(pedido({ texto: "x", telefono: "549" }), {
        params: { conversacionId: "c1" },
      }),
      rutaToma.POST(lectura(), { params: { escalamientoId: "e1" } }),
      rutaCierre.POST(pedido({ devolver_al_agente: true }), {
        params: { escalamientoId: "e1" },
      }),
      rutaFaqs.GET(),
      rutaFaqs.POST(pedido({ pregunta: "x", respuesta: "y" })),
      rutaFaq.PUT(pedido({ pregunta: "x", respuesta: "y" }, "PUT"), { params: { faqId: "f1" } }),
      rutaFaq.DELETE(lectura(), { params: { faqId: "f1" } }),
      rutaUsoDeFaq.GET(lectura(), { params: { faqId: "f1" } }),
      rutaPlantillas.GET(),
      rutaPlantilla.PUT(pedido({ cuerpo: "x" }, "PUT"), { params: { plantillaId: "p1" } }),
      rutaEnvioDePlantilla.POST(pedido(), { params: { plantillaId: "p1" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(13).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("las conversaciones", () => {
  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ conversaciones: [] });

    await rutaConversaciones.GET(lectura("?solo_escaladas=true"));

    expect(llamarApi).toHaveBeenCalledWith("/conversaciones?solo_escaladas=true", {
      method: "GET",
    });
  });

  it("el hilo usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "c-1", mensajes: [] });

    await rutaHilo.GET(lectura(), { params: { conversacionId: "c-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/conversaciones/c-1", { method: "GET" });
  });

  it("el mensaje del operador lleva texto y telefono", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "m1" });

    await rutaMensajes.POST(pedido({ texto: "Hola!", telefono: "5491112345678" }), {
      params: { conversacionId: "c1" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/conversaciones/c1/mensajes", {
      method: "POST",
      body: { texto: "Hola!", telefono: "5491112345678" },
    });
  });

  it("el rechazo por no haber tomado el escalamiento llega con su texto", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "Para escribirle al cliente hay que tomar el escalamiento primero",
        "EntradaInvalida",
      ),
    );

    const respuesta = await rutaMensajes.POST(pedido({ texto: "x", telefono: "549" }), {
      params: { conversacionId: "c1" },
    });

    expect(respuesta.status).toBe(422);
    expect((await respuesta.json()).detalle).toContain("tomar el escalamiento");
  });

  it("no ofrece un DELETE: una conversación es un registro", () => {
    expect("DELETE" in rutaConversaciones).toBe(false);
    expect("DELETE" in rutaHilo).toBe(false);
  });
});

describe("los escalamientos", () => {
  it("tomar no manda nada que elegir: quién lo toma sale de la sesión", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "c1" });

    await rutaToma.POST(lectura(), { params: { escalamientoId: "e1" } });

    expect(llamarApi).toHaveBeenCalledWith("/escalamientos/e1/toma", {
      method: "POST",
      body: {},
    });
  });

  it("el rechazo de reapertura llega con la frase de la historia", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "Un escalamiento cerrado no se reabre. Un nuevo pedido del cliente genera uno nuevo.",
        "EscalamientoNoReabrible",
      ),
    );

    const respuesta = await rutaCierre.POST(pedido({ devolver_al_agente: false }), {
      params: { escalamientoId: "e1" },
    });

    // 422 y no 409 a propósito: este BFF reenvía el `detalle` sólo en un 422, y la historia
    // pide que el sistema **indique** por qué, no sólo que niegue.
    expect(respuesta.status).toBe(422);
    expect((await respuesta.json()).detalle).toContain("nuevo pedido del cliente");
  });

  it("no ofrece un DELETE: un escalamiento cerrado es un caso atendido", () => {
    expect("DELETE" in rutaToma).toBe(false);
    expect("DELETE" in rutaCierre).toBe(false);
  });
});

describe("las FAQ", () => {
  it("el DELETE existe, y es el único del producto que borra de verdad", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await rutaFaq.DELETE(lectura(), { params: { faqId: "f1" } });

    expect(llamarApi).toHaveBeenCalledWith("/faqs/f1", { method: "DELETE" });
  });

  it("el detalle de uso se pide al backend por FAQ", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ usos_este_mes: 1 });

    const respuesta = await rutaUsoDeFaq.GET(lectura(), { params: { faqId: "f1" } });

    expect(llamarApi).toHaveBeenCalledWith("/faqs/f1/uso", { method: "GET" });
    expect(await respuesta.json()).toEqual({ usos_este_mes: 1 });
  });

  it("el alta manda pregunta y respuesta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "f1" });

    await rutaFaqs.POST(pedido({ pregunta: "¿Abren?", respuesta: "Sí." }));

    expect(llamarApi).toHaveBeenCalledWith("/faqs", {
      method: "POST",
      body: { pregunta: "¿Abren?", respuesta: "Sí." },
    });
  });
});

describe("las plantillas", () => {
  it("no ofrecen alta ni baja: los códigos los define el sistema", () => {
    expect("POST" in rutaPlantillas).toBe(false);
    expect("DELETE" in rutaPlantillas).toBe(false);
    expect("DELETE" in rutaPlantilla).toBe(false);
  });

  it("editar el cuerpo es un PUT y su rechazo llega con la frase", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "La variable indicada no es válida para esta plantilla.",
        "EntradaInvalida",
      ),
    );

    const respuesta = await rutaPlantilla.PUT(pedido({ cuerpo: "{{saldo}}" }, "PUT"), {
      params: { plantillaId: "p1" },
    });

    expect(respuesta.status).toBe(422);
    expect((await respuesta.json()).detalle).toContain("no es válida");
  });
});

describe("enviar una plantilla a revisión de Meta", () => {
  it("es un POST sin cuerpo: qué plantilla sale de la ruta y quién la reenvía, de la sesión", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "p1", estado_aprobacion: "PENDIENTE" });

    const respuesta = await rutaEnvioDePlantilla.POST(pedido(), {
      params: { plantillaId: "p1" },
    });

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/plantillas/p1/envio", {
      method: "POST",
      body: {},
    });
  });

  it("no ofrece ningún otro método", () => {
    expect(Object.keys(rutaEnvioDePlantilla).filter((nombre) => /^[A-Z]+$/.test(nombre))).toEqual([
      "POST",
    ]);
  });

  it("el texto de Meta llega con un 422 y un 503 llega sin detalle", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValueOnce(new ErrorDeApi(422, "Texto de Meta", "MetaRechazoLaPlantilla"));
    const rechazada = await rutaEnvioDePlantilla.POST(pedido(), { params: { plantillaId: "p1" } });
    llamarApi.mockRejectedValueOnce(new ErrorDeApi(503, "interno", "MetaNoDisponible"));
    const caida = await rutaEnvioDePlantilla.POST(pedido(), { params: { plantillaId: "p1" } });

    expect(rechazada.status).toBe(422);
    expect((await rechazada.json()).detalle).toBe("Texto de Meta");
    expect(caida.status).toBe(503);
    expect((await caida.json()).detalle).toBeUndefined();
  });
});
