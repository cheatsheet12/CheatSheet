/**
 * El cliente de API de la agenda de notificación (caso 8).
 *
 * Lo que se prueba acá es **`leerConfiguracionDeAgenda`**, que interpreta un JSONB: la
 * configuración de una regla es un objeto libre en la base (D24), así que la pantalla puede
 * recibir cualquier cosa. Devolver lo que se pudo leer en vez de romper hace que sea una regla
 * editable y no una página en blanco.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorDeAgenda, agendaDe, configurarAgenda, leerConfiguracionDeAgenda } from "../agenda";
import type { ReglaCruda } from "../atencion";

const REGLA: ReglaCruda = {
  id: "rg1",
  tipo: "AGENDA_DE_NOTIFICACION",
  configuracion: { recordatorios: [{ horas_antes: 48 }, { horas_antes: 2 }] },
  prioridad: 0,
  activa: true,
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("leerConfiguracionDeAgenda", () => {
  it("lee los recordatorios en el orden en que vienen", () => {
    expect(leerConfiguracionDeAgenda(REGLA.configuracion).recordatorios).toEqual([
      { horas_antes: 48 },
      { horas_antes: 2 },
    ]);
  });

  it("una configuración mal formada se lee vacía en vez de romper", () => {
    expect(leerConfiguracionDeAgenda({ recordatorios: "24" })).toEqual({ recordatorios: [] });
    expect(leerConfiguracionDeAgenda({})).toEqual({ recordatorios: [] });
  });

  it("descarta lo que no tiene la forma esperada y conserva el resto", () => {
    const leida = leerConfiguracionDeAgenda({
      recordatorios: [null, 24, { horas_antes: "24" }, { horas_antes: 2.5 }, { horas_antes: 12 }],
    });

    expect(leida.recordatorios).toEqual([{ horas_antes: 12 }]);
  });
});

describe("agendaDe", () => {
  it("sin regla de agenda devuelve null", () => {
    expect(agendaDe({ reglas: [{ ...REGLA, tipo: "HORARIO_DE_ATENCION" }] })).toBeNull();
    expect(agendaDe({ reglas: [] })).toBeNull();
  });

  it("trae el id, el estado y la prioridad de la regla", () => {
    const guardada = agendaDe({ reglas: [{ ...REGLA, prioridad: 3, activa: false }] });

    expect(guardada).toMatchObject({ reglaId: "rg1", activa: false, prioridad: 3 });
  });

  it("prefiere la regla activa", () => {
    const guardada = agendaDe({
      reglas: [
        { ...REGLA, id: "vieja", activa: false },
        { ...REGLA, id: "vigente", activa: true },
      ],
    });

    expect(guardada?.reglaId).toBe("vigente");
  });
});

describe("configurarAgenda", () => {
  it("hace PUT con los recordatorios y la prioridad, y devuelve lo guardado", async () => {
    const espia = vi.fn().mockResolvedValue(respuesta(REGLA));
    vi.stubGlobal("fetch", espia);

    const guardada = await configurarAgenda([{ horas_antes: 48 }, { horas_antes: 2 }], 2);

    expect(espia).toHaveBeenCalledWith("/api/reglas/agenda", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recordatorios: [{ horas_antes: 48 }, { horas_antes: 2 }],
        prioridad: 2,
      }),
    });
    expect(guardada.reglaId).toBe("rg1");
    expect(guardada.recordatorios).toHaveLength(2);
  });

  it("un error del PUT llega con el mensaje del backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respuesta(
          {
            error: "EntradaInvalida",
            detalle: "Las horas de anticipación deben estar entre 1 y 168.",
          },
          false,
          422,
        ),
      ),
    );

    const intento = configurarAgenda([{ horas_antes: 169 }]);

    await expect(intento).rejects.toBeInstanceOf(ErrorDeAgenda);
    await expect(intento).rejects.toThrow("Las horas de anticipación deben estar entre 1 y 168.");
  });

  it("sin detalle usa el código y, sin cuerpo, un mensaje genérico", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(respuesta({ error: "NoAutenticado" }, false, 401)),
    );
    await expect(configurarAgenda([{ horas_antes: 24 }])).rejects.toThrow("NoAutenticado");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("no es json")),
      } as unknown as Response),
    );
    await expect(configurarAgenda([{ horas_antes: 24 }])).rejects.toThrow(
      "No se pudo guardar la agenda.",
    );
  });
});
