/**
 * El cliente de API del horario de atención (caso 40).
 *
 * Lo que se prueba acá es **`leerConfiguracion`**, que interpreta un JSONB: la configuración de
 * una regla es un objeto libre en la base (D24), así que la pantalla puede recibir cualquier cosa.
 * Devolver una configuración vacía en vez de romper hace que sea una regla editable y no una
 * página en blanco.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeAtencion,
  configurarHorarioDeAtencion,
  horarioDe,
  leerConfiguracion,
} from "../atencion";
import type { ConfiguracionDeAtencion, ReglaCruda } from "../atencion";

const REGLA: ReglaCruda = {
  id: "rg1",
  tipo: "HORARIO_DE_ATENCION",
  configuracion: {
    version: 1,
    politica: "MENSAJE_FIJO",
    dias: [
      {
        dia: 0,
        franjas: [
          { desde: "09:00", hasta: "13:00" },
          { desde: "16:00", hasta: "20:00" },
        ],
      },
    ],
    fechas_cerradas: ["2026-10-12"],
  },
  prioridad: 0,
  activa: true,
};

const CONFIGURACION: ConfiguracionDeAtencion = {
  dias: [{ dia: 0, franjas: [{ desde: "09:00", hasta: "19:00" }] }],
  fechas_cerradas: ["2026-10-12"],
  politica: "AGENTE_RESPONDE",
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("leerConfiguracion", () => {
  it("lee los días con sus franjas, las fechas sin atención y la política", () => {
    const leida = leerConfiguracion(REGLA.configuracion);

    expect(leida.politica).toBe("MENSAJE_FIJO");
    expect(leida.fechas_cerradas).toEqual(["2026-10-12"]);
    expect(leida.dias[0]?.franjas).toHaveLength(2);
  });

  it("sin fechas_cerradas lee una lista vacía", () => {
    const { fechas_cerradas: _omitida, ...sinFechas } = REGLA.configuracion;

    expect(leerConfiguracion(sinFechas).fechas_cerradas).toEqual([]);
  });

  it("una configuración mal formada se lee vacía en vez de romper", () => {
    const leida = leerConfiguracion({ dias: "lunes", politica: 7, fechas_cerradas: 3 });

    expect(leida).toEqual({ dias: [], fechas_cerradas: [], politica: "AGENTE_RESPONDE" });
  });

  it("descarta lo que no tiene la forma esperada y conserva el resto", () => {
    const leida = leerConfiguracion({
      dias: [
        null,
        { dia: "lunes", franjas: [] },
        { dia: 1, franjas: [{ desde: "09:00" }, { desde: "10:00", hasta: "11:00" }] },
        { dia: 2, franjas: [] },
      ],
      fechas_cerradas: ["2026-10-12", "12/10/2026", 5],
    });

    expect(leida.dias).toEqual([{ dia: 1, franjas: [{ desde: "10:00", hasta: "11:00" }] }]);
    expect(leida.fechas_cerradas).toEqual(["2026-10-12"]);
  });
});

describe("horarioDe", () => {
  it("sin regla de horario devuelve null", () => {
    expect(horarioDe({ reglas: [{ ...REGLA, tipo: "ESCALAMIENTO_DE_COBRO" }] })).toBeNull();
    expect(horarioDe({ reglas: [] })).toBeNull();
  });

  it("trae el id, el estado y la prioridad de la regla", () => {
    const guardado = horarioDe({ reglas: [{ ...REGLA, prioridad: 3, activa: false }] });

    expect(guardado).toMatchObject({ reglaId: "rg1", activa: false, prioridad: 3 });
  });

  it("prefiere la regla activa", () => {
    const guardado = horarioDe({
      reglas: [
        { ...REGLA, id: "vieja", activa: false },
        { ...REGLA, id: "vigente", activa: true },
      ],
    });

    expect(guardado?.reglaId).toBe("vigente");
  });
});

describe("configurarHorarioDeAtencion", () => {
  it("hace PUT con la configuración y la prioridad, y devuelve lo guardado", async () => {
    const espia = vi.fn().mockResolvedValue(respuesta(REGLA));
    vi.stubGlobal("fetch", espia);

    const guardado = await configurarHorarioDeAtencion(CONFIGURACION, 2);

    expect(espia).toHaveBeenCalledWith("/api/reglas/horario-de-atencion", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...CONFIGURACION, prioridad: 2 }),
    });
    expect(guardado.reglaId).toBe("rg1");
    expect(guardado.politica).toBe("MENSAJE_FIJO");
  });

  it("un error del PUT llega con el mensaje del backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respuesta(
          {
            error: "EntradaInvalida",
            detalle: "La hora de cierre debe ser posterior a la de apertura.",
          },
          false,
          422,
        ),
      ),
    );

    const intento = configurarHorarioDeAtencion(CONFIGURACION);

    await expect(intento).rejects.toBeInstanceOf(ErrorDeAtencion);
    await expect(intento).rejects.toThrow("La hora de cierre debe ser posterior a la de apertura.");
  });

  it("sin detalle usa el código y, sin cuerpo, un mensaje genérico", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(respuesta({ error: "NoAutenticado" }, false, 401)),
    );
    await expect(configurarHorarioDeAtencion(CONFIGURACION)).rejects.toThrow("NoAutenticado");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("no es json")),
      } as unknown as Response),
    );
    await expect(configurarHorarioDeAtencion(CONFIGURACION)).rejects.toThrow(
      "No se pudo guardar el horario.",
    );
  });
});
