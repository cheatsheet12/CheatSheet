/**
 * El cliente de API de la bitácora, las notificaciones y el soporte (épico 10).
 *
 * Lo que este archivo fija:
 *
 * - **el filtro viaja con el mismo texto que el listado devuelve** (`identity`, `ia`,
 *   `error`), no con el nombre del miembro del enum. Traducir de un lado y no del otro es cómo
 *   un filtro termina devolviendo la lista entera;
 * - **la página 1 no viaja**: es el valor por defecto del backend, y mandarlo ensucia la URL
 *   que alguien copia para compartir una búsqueda;
 * - **no existe `marcarComoNoLeida`**, y el test lo afirma por ausencia sobre el módulo.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import * as observability from "@/features/observability";
import {
  ETIQUETAS_DE_INICIADOR,
  ErrorDeBitacora,
  ErrorDeNotificacion,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  abrirSolicitud,
  listarNotificaciones,
  listarOperaciones,
  listarSolicitudes,
  marcarComoLeida,
  verOperacion,
} from "@/features/observability";
import type { Operacion } from "@/features/observability";

const OPERACION: Operacion = {
  id: "op1",
  timestamp: "2026-09-07T12:00:00Z",
  modulo: "billing",
  accion: "autorizar_comprobante",
  entidad_afectada: "Comprobante:1",
  iniciador: "sistema",
  resultado: "completado",
  usuario_id: null,
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

function espiarFetch(...respuestas: readonly Response[]): ReturnType<typeof vi.fn> {
  const espia = vi.fn();
  for (const una of respuestas) {
    espia.mockResolvedValueOnce(una);
  }
  vi.stubGlobal("fetch", espia);
  return espia;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listarOperaciones", () => {
  it("manda los filtros con el texto que la tabla muestra", async () => {
    const espia = espiarFetch(respuesta({ operaciones: [OPERACION], total: 1 }));

    await listarOperaciones({ modulo: "billing", iniciador: "ia", resultado: "error" });

    expect(espia).toHaveBeenCalledWith(
      "/api/bitacora?modulo=billing&iniciador=ia&resultado=error",
      expect.anything(),
    );
  });

  it("no manda la página 1", async () => {
    const espia = espiarFetch(respuesta({ operaciones: [], total: 0 }));

    await listarOperaciones({ pagina: 1 });

    expect(espia).toHaveBeenCalledWith("/api/bitacora", expect.anything());
  });

  it("sí manda la página 3", async () => {
    const espia = espiarFetch(respuesta({ operaciones: [], total: 0 }));

    await listarOperaciones({ pagina: 3 });

    expect(espia).toHaveBeenCalledWith("/api/bitacora?pagina=3", expect.anything());
  });

  it("propaga el motivo cuando el rol no accede", async () => {
    espiarFetch(
      respuesta(
        {
          error: "AccesoALaBitacoraDenegado",
          detalle: "El rol Solo Lectura no accede a la bitácora de operaciones",
        },
        false,
        422,
      ),
    );

    await expect(listarOperaciones()).rejects.toThrow(/Solo Lectura/);
  });

  it("levanta un ErrorDeBitacora con un cuerpo que no es JSON", async () => {
    espiarFetch({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("no es json")),
    } as unknown as Response);

    await expect(listarOperaciones()).rejects.toBeInstanceOf(ErrorDeBitacora);
  });
});

describe("verOperacion", () => {
  it("trae el detalle con su timeline", async () => {
    espiarFetch(
      respuesta({
        operacion: OPERACION,
        detalle: { cae: "70123456789012" },
        timeline: [OPERACION],
        duracion_ms: 1200,
        paso_con_error: null,
      }),
    );

    const detalle = await verOperacion("op1");

    expect(detalle.detalle.cae).toBe("70123456789012");
    expect(detalle.duracion_ms).toBe(1200);
  });
});

describe("las etiquetas", () => {
  it("nombran al agente por lo que es", () => {
    // «Agente IA» y no «IA»: lo que la fila dice es que actuó sobre el mensaje de un cliente.
    expect(ETIQUETAS_DE_INICIADOR.ia).toBe("Agente IA");
  });
});

describe("las notificaciones", () => {
  it("no piden la bandeja de nadie en particular", async () => {
    const espia = espiarFetch(respuesta({ notificaciones: [], no_leidas: 0 }));

    await listarNotificaciones();

    // Sin id de usuario en la URL: la única bandeja que se puede pedir es la propia.
    expect(espia).toHaveBeenCalledWith("/api/notificaciones", expect.anything());
  });

  it("filtran las no leídas cuando se pide", async () => {
    const espia = espiarFetch(respuesta({ notificaciones: [], no_leidas: 0 }));

    await listarNotificaciones(true);

    expect(espia).toHaveBeenCalledWith(
      "/api/notificaciones?solo_no_leidas=true",
      expect.anything(),
    );
  });

  it("marcar como leída es un POST sobre el acuse", async () => {
    const espia = espiarFetch(
      respuesta({
        id: "n1",
        categoria: "COBROS",
        severidad: "ALTA",
        cuerpo: "algo falló",
        leida: true,
        se_destaca: false,
        created_at: null,
      }),
    );

    const marcada = await marcarComoLeida("n1");

    expect(espia).toHaveBeenCalledWith("/api/notificaciones/n1/lectura", { method: "POST" });
    expect(marcada.se_destaca).toBe(false);
  });

  it("no existe forma de desmarcarla", () => {
    expect(observability).not.toHaveProperty("marcarComoNoLeida");
  });

  it("un fallo levanta ErrorDeNotificacion", async () => {
    espiarFetch(respuesta({ error: "NotificacionInexistente" }, false, 422));

    await expect(marcarComoLeida("n1")).rejects.toBeInstanceOf(ErrorDeNotificacion);
  });
});

describe("el soporte", () => {
  it("lista lo abierto", async () => {
    const espia = espiarFetch(respuesta({ solicitudes: [] }));

    await listarSolicitudes(true);

    expect(espia).toHaveBeenCalledWith("/api/soporte?solo_abiertas=true", expect.anything());
  });

  it("manda asunto, descripción y prioridad", async () => {
    const espia = espiarFetch(
      respuesta({
        id: "s1",
        asunto: "No puedo emitir",
        descripcion: "ARCA rechaza",
        prioridad: "ALTA",
        estado: "ABIERTA",
        esta_abierta: true,
        created_at: null,
      }),
    );

    await abrirSolicitud({
      asunto: "No puedo emitir",
      descripcion: "ARCA rechaza",
      prioridad: "ALTA",
    });

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(opciones.method).toBe("POST");
    expect(opciones.body).toContain('"prioridad":"ALTA"');
  });

  it("propaga la frase de la historia cuando faltan campos", async () => {
    espiarFetch(
      respuesta({ error: "EntradaInvalida", detalle: MENSAJE_CAMPOS_OBLIGATORIOS }, false, 422),
    );

    await expect(
      abrirSolicitud({ asunto: "", descripcion: "", prioridad: "BAJA" }),
    ).rejects.toThrow(MENSAJE_CAMPOS_OBLIGATORIOS);
  });
});
