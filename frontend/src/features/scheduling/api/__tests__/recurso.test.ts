/**
 * El cliente de API de PAN-AGE-03.
 *
 * Lo que se afirma acá es que las tres configuraciones **reemplazan**: `PUT` con la lista
 * entera, no `POST` con el elemento que cambió. Un recurso tiene un horario de atención y una
 * lista de servicios, no un catálogo de versiones de cada uno.
 *
 * Y una cosa que no está en ninguna historia: que `DIAS` esté indexado por el mismo número que
 * el backend guarda. Un corrimiento de uno acá mueve la agenda de una empresa un día entero,
 * y es exactamente la clase de error que nadie ve leyendo el código.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DIAS,
  ErrorDeRecurso,
  MENSAJE_EXCEPCION_DUPLICADA,
  asociarServicios,
  cambiarEstadoDeRecurso,
  configurarDisponibilidad,
  horarioDe,
  listarRecursos,
  listarServiciosAgendables,
  quitarExcepcion,
  registrarExcepcion,
  registrarRecurso,
} from "@/features/scheduling";
import type { Recurso } from "@/features/scheduling";

const RECURSO: Recurso = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [
    { dia_semana: 1, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 30 },
  ],
  excepciones: [],
  servicios: ["s1"],
};

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

describe("listarRecursos", () => {
  it("no cachea la configuracion vigente", async () => {
    const espia = espiarFetch(respuesta({ recursos: [RECURSO] }));

    await listarRecursos();

    expect(espia).toHaveBeenCalledWith("/api/recursos", { cache: "no-store" });
  });

  it("pide solo los activos cuando se lo piden", async () => {
    const espia = espiarFetch(respuesta({ recursos: [] }));

    await listarRecursos(true);

    expect(espia).toHaveBeenCalledWith("/api/recursos?solo_activos=true", { cache: "no-store" });
  });

  it("falla con el codigo cuando no hay detalle", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(listarRecursos()).rejects.toThrow("NoAutenticado");
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

    await expect(listarRecursos()).rejects.toBeInstanceOf(ErrorDeRecurso);
  });
});

describe("listarServiciosAgendables", () => {
  it("pide la vista de la agenda y no el catalogo completo", async () => {
    const espia = espiarFetch(respuesta([]));

    await listarServiciosAgendables();

    expect(espia).toHaveBeenCalledWith("/api/recursos/servicios", { cache: "no-store" });
  });
});

describe("registrarRecurso", () => {
  it("manda nombre, tipo, horario y servicios", async () => {
    const espia = espiarFetch(respuesta(RECURSO));

    await registrarRecurso({
      nombre: "Sala 2",
      tipo: "ESPACIO",
      patrones: [],
      servicios: [],
    });

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/recursos");
    expect(opciones.method).toBe("POST");
  });
});

describe("las tres configuraciones", () => {
  it("el horario se reemplaza con un PUT", async () => {
    const espia = espiarFetch(respuesta(RECURSO));

    await configurarDisponibilidad("r1", RECURSO.patrones);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/recursos/r1/disponibilidad");
    expect(opciones.method).toBe("PUT");
    expect(opciones.body).toBe(JSON.stringify({ patrones: RECURSO.patrones }));
  });

  it("los servicios se reemplazan con un PUT", async () => {
    const espia = espiarFetch(respuesta(RECURSO));

    await asociarServicios("r1", ["s1", "s2"]);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/recursos/r1/servicios");
    expect(opciones.body).toBe(JSON.stringify({ servicios: ["s1", "s2"] }));
  });

  it("el estado se manda entero y no como un toggle", async () => {
    const espia = espiarFetch(respuesta({ ...RECURSO, activo: false }));

    await cambiarEstadoDeRecurso("r1", false);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    // El estado deseado y no «alterná»: dos pestañas sobre el mismo recurso no pueden
    // dejarlo en el estado contrario al que cada una vio.
    expect(ruta).toBe("/api/recursos/r1/estado");
    expect(opciones.body).toBe(JSON.stringify({ activo: false }));
  });
});

describe("las excepciones", () => {
  it("un bloqueo viaja sin horario", async () => {
    const espia = espiarFetch(respuesta(RECURSO));

    await registrarExcepcion("r1", { fecha: "2027-12-25", tipo: "BLOQUEO" });

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/recursos/r1/excepciones");
    expect(opciones.body).toBe(JSON.stringify({ fecha: "2027-12-25", tipo: "BLOQUEO" }));
  });

  it("propaga el rechazo de la segunda excepcion para la misma fecha", async () => {
    espiarFetch(
      respuesta({ error: "ExcepcionDuplicada", detalle: MENSAJE_EXCEPCION_DUPLICADA }, false, 422),
    );

    await expect(
      registrarExcepcion("r1", { fecha: "2027-12-25", tipo: "BLOQUEO" }),
    ).rejects.toThrow(MENSAJE_EXCEPCION_DUPLICADA);
  });

  it("quitar una excepcion es el unico DELETE de la feature", async () => {
    const espia = espiarFetch(respuesta(RECURSO));

    await quitarExcepcion("r1", "2027-12-25");

    expect(espia).toHaveBeenCalledWith("/api/recursos/r1/excepciones/2027-12-25", {
      method: "DELETE",
    });
  });
});

describe("DIAS", () => {
  it("esta indexado por el mismo numero que el backend guarda", () => {
    // Lunes 0, domingo 6 — el orden de Python. Un corrimiento de uno acá mueve la agenda de
    // una empresa un día entero.
    expect(DIAS[0]).toBe("Lunes");
    expect(DIAS[6]).toBe("Domingo");
    expect(DIAS).toHaveLength(7);
  });
});

describe("horarioDe", () => {
  it("recorta los segundos que el backend manda", () => {
    expect(horarioDe(RECURSO.patrones[0]!)).toBe("09:00 a 18:00");
  });
});
