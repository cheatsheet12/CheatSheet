/**
 * Los clientes de API del canal conversacional.
 *
 * Dos cosas se afirman acá y en ningún otro lado del frontend:
 *
 * - **`variablesDe` y `variablesInvalidas` son una cortesía, no la garantía.** Son lo que hace
 *   que la pantalla avise mientras alguien escribe; la validación que cuenta es la del backend,
 *   porque dos pestañas pasan cualquier comprobación del navegador. Se prueban igual: si
 *   avisaran mal, el aviso sería peor que no avisar.
 *
 * - **`eliminarFaq` es el único `DELETE` del producto** que borra de verdad. Que exista se
 *   prueba; que sea el único lo sostienen los tests de las otras features, donde cada una
 *   afirma que su recurso se desactiva.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeConversacion,
  ErrorDeFaq,
  cerrarEscalamiento,
  crearFaq,
  editarPlantilla,
  eliminarFaq,
  listarConversaciones,
  listarFaqs,
  listarPlantillas,
  responder,
  tomarEscalamiento,
  tonoDeEscalamiento,
  variablesDe,
  variablesInvalidas,
  verConversacion,
} from "@/features/conversational";

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

function espiarFetch(una: Response): ReturnType<typeof vi.fn> {
  const espia = vi.fn().mockResolvedValue(una);
  vi.stubGlobal("fetch", espia);
  return espia;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("las conversaciones", () => {
  it("no cachean: un hilo cambia por un webhook, no por una accion nuestra", async () => {
    const espia = espiarFetch(respuesta({ conversaciones: [] }));

    await listarConversaciones();

    expect(espia).toHaveBeenCalledWith("/api/conversaciones", { cache: "no-store" });
  });

  it("piden solo las escaladas cuando se lo piden", async () => {
    const espia = espiarFetch(respuesta({ conversaciones: [] }));

    await listarConversaciones(true);

    expect(espia).toHaveBeenCalledWith("/api/conversaciones?solo_escaladas=true", {
      cache: "no-store",
    });
  });

  it("el detalle usa el id de la ruta", async () => {
    const espia = espiarFetch(respuesta({ id: "c1", mensajes: [] }));

    await verConversacion("c1");

    expect(espia).toHaveBeenCalledWith("/api/conversaciones/c1", { cache: "no-store" });
  });

  it("prefiere el detalle del backend al codigo de la excepcion", async () => {
    const frase = "Un escalamiento cerrado no se reabre.";
    espiarFetch(respuesta({ error: "EscalamientoNoReabrible", detalle: frase }, false, 422));

    await expect(cerrarEscalamiento("e1", true)).rejects.toThrow(frase);
  });

  it("cae en el codigo cuando el backend no mando detalle", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(listarConversaciones()).rejects.toThrow("NoAutenticado");
  });

  it("no se rompe con un cuerpo que no es JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("no es JSON")),
      } as unknown as Response),
    );

    await expect(listarConversaciones()).rejects.toBeInstanceOf(ErrorDeConversacion);
  });

  it("tomar el escalamiento no manda nada que elegir", async () => {
    const espia = espiarFetch(respuesta({ id: "c1" }));

    await tomarEscalamiento("e1");

    expect(espia).toHaveBeenCalledWith("/api/escalamientos/e1/toma", { method: "POST" });
  });

  it("cerrar manda la clasificacion, o `null` para que reevalue el agente", async () => {
    const espia = espiarFetch(respuesta({ id: "c1" }));

    await cerrarEscalamiento("e1", true, "PAGO");
    await cerrarEscalamiento("e1", false);

    const cuerpos = espia.mock.calls.map(([, opciones]) => (opciones as RequestInit).body);
    expect(cuerpos[0]).toBe(JSON.stringify({ devolver_al_agente: true, clasificacion: "PAGO" }));
    expect(cuerpos[1]).toBe(JSON.stringify({ devolver_al_agente: false, clasificacion: null }));
  });

  it("responder manda el texto y el telefono", async () => {
    const espia = espiarFetch(respuesta({ id: "m1" }));

    await responder("c1", "Hola!", "5491112345678");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/conversaciones/c1/mensajes");
    expect(opciones.body).toBe(JSON.stringify({ texto: "Hola!", telefono: "5491112345678" }));
  });
});

describe("tonoDeEscalamiento", () => {
  it("le da a cada estado el tono que su significado pide", () => {
    // Un escalamiento sin tomar es rojo: hay alguien esperando. Uno asignado no, porque ya
    // hay una persona ocupándose.
    expect(tonoDeEscalamiento("ABIERTO")).toBe("error");
    expect(tonoDeEscalamiento("ASIGNADO")).toBe("atencion");
    expect(tonoDeEscalamiento("RESUELTO")).toBe("ok");
    expect(tonoDeEscalamiento(null)).toBe("ok");
  });
});

describe("las FAQ", () => {
  it("no cachean el listado", async () => {
    const espia = espiarFetch(respuesta({ faqs: [] }));

    await listarFaqs();

    expect(espia).toHaveBeenCalledWith("/api/faqs", { cache: "no-store" });
  });

  it("crear manda pregunta y respuesta", async () => {
    const espia = espiarFetch(respuesta({ id: "f1" }));

    await crearFaq("¿Abren los sábados?", "Sí, de 9 a 13.");

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(opciones.body).toBe(
      JSON.stringify({ pregunta: "¿Abren los sábados?", respuesta: "Sí, de 9 a 13." }),
    );
  });

  it("eliminar es un DELETE de verdad", async () => {
    const espia = espiarFetch(respuesta({}, true, 204));

    await eliminarFaq("f1");

    expect(espia).toHaveBeenCalledWith("/api/faqs/f1", { method: "DELETE" });
  });

  it("propaga la frase de los campos obligatorios", async () => {
    const frase = "La pregunta y la respuesta son obligatorias.";
    espiarFetch(respuesta({ error: "EntradaInvalida", detalle: frase }, false, 422));

    await expect(crearFaq("", "algo")).rejects.toThrow(frase);
  });

  it("no se rompe con un cuerpo que no es JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("no es JSON")),
      } as unknown as Response),
    );

    await expect(listarFaqs()).rejects.toBeInstanceOf(ErrorDeFaq);
  });
});

describe("las plantillas", () => {
  it("se leen sin cache y se editan con PUT", async () => {
    const espia = espiarFetch(respuesta({ plantillas: [] }));
    await listarPlantillas();
    expect(espia).toHaveBeenCalledWith("/api/plantillas", { cache: "no-store" });

    const otro = espiarFetch(respuesta({ id: "p1" }));
    await editarPlantilla("p1", "Hola {{nombre}}.");
    const [ruta, opciones] = otro.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/plantillas/p1");
    expect(opciones.method).toBe("PUT");
  });
});

describe("las variables de una plantilla", () => {
  it("reconoce las que el texto usa", () => {
    expect(variablesDe("Hola {{nombre}}, el {{fecha}} a las {{hora}}.")).toEqual([
      "nombre",
      "fecha",
      "hora",
    ]);
  });

  it("ignora lo que no tiene la forma exacta", () => {
    // Una sola llave, mayúsculas, espacios: nada de eso es una variable, y tratarlo como tal
    // haría que la pantalla avisara sobre texto legítimo.
    expect(variablesDe("{nombre} {{ nombre }} {{Nombre}} {{}}")).toEqual([]);
  });

  it("señala solo las que la plantilla no admite", () => {
    const admitidas = ["nombre", "fecha"];

    expect(variablesInvalidas("Hola {{nombre}} el {{fecha}}.", admitidas)).toEqual([]);
    expect(variablesInvalidas("Hola {{nombre}}, saldo {{saldo}}.", admitidas)).toEqual(["saldo"]);
  });
});
