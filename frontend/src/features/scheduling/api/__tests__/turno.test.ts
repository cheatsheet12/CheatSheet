/**
 * El cliente de API de las tres pantallas de la agenda.
 *
 * Dos cosas se afirman acá y en ningún otro lado del frontend:
 *
 * - **el filtro vacío no viaja.** `hasta=` sería un filtro por la cadena vacía, que no es lo
 *   mismo que no filtrar por fecha de fin — y la diferencia es una agenda vacía donde debería
 *   haber turnos;
 * - **cancelar no manda cuerpo.** A diferencia de cancelar un cobro, que pide el motivo
 *   (HU-E6-04 RN-02). La diferencia es del negocio, y un cuerpo de más acá sería una pregunta
 *   que el backend no hizo.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeTurno,
  MENSAJE_HORARIO_OCUPADO,
  cancelarTurno,
  horaDe,
  listarTurnos,
  registrarAsistencia,
  reprogramarTurno,
  reservarTurno,
  tonoDeEstado,
  verDisponibilidad,
  verTurno,
} from "@/features/scheduling";
import type { Turno } from "@/features/scheduling";

const TURNO: Turno = {
  id: "t1",
  cliente_id: "cl1",
  servicio_id: "s1",
  recurso_id: "r1",
  cobro_id: null,
  inicio: "2027-09-07T18:00:00+00:00",
  duracion_min: 60,
  fin: "2027-09-07T19:00:00+00:00",
  estado: "RESERVADO",
  canal_reserva: "PANEL",
  ya_transcurrio: false,
  habilita_facturacion: false,
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

describe("listarTurnos", () => {
  it("no cachea: un turno puede cambiar por una cancelacion de otro operador", async () => {
    const espia = espiarFetch(respuesta({ turnos: [TURNO] }));

    await listarTurnos();

    expect(espia).toHaveBeenCalledWith("/api/turnos", { cache: "no-store" });
  });

  it("arma el query string con los filtros que tienen valor y con ninguno mas", async () => {
    const espia = espiarFetch(respuesta({ turnos: [] }));

    await listarTurnos({ recurso_id: "r1", desde: "2027-09-07", hasta: "", estado: "NO_SHOW" });

    expect(espia).toHaveBeenCalledWith(
      "/api/turnos?recurso_id=r1&desde=2027-09-07&estado=NO_SHOW",
      { cache: "no-store" },
    );
  });

  it("prefiere el detalle del backend al codigo de la excepcion", async () => {
    espiarFetch(
      respuesta({ error: "FranjaOcupada", detalle: MENSAJE_HORARIO_OCUPADO }, false, 422),
    );

    await expect(listarTurnos()).rejects.toThrow(MENSAJE_HORARIO_OCUPADO);
  });

  it("cae en el codigo cuando el backend no mando detalle", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(listarTurnos()).rejects.toThrow("NoAutenticado");
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

    await expect(listarTurnos()).rejects.toBeInstanceOf(ErrorDeTurno);
  });
});

describe("verTurno y verDisponibilidad", () => {
  it("piden el detalle sin cache", async () => {
    const espia = espiarFetch(respuesta(TURNO));

    await verTurno("t1");

    expect(espia).toHaveBeenCalledWith("/api/turnos/t1", { cache: "no-store" });
  });

  it("la disponibilidad manda el recurso y la fecha", async () => {
    const espia = espiarFetch(respuesta({ fecha: "2027-09-07", horarios: [] }));

    await verDisponibilidad("r1", "2027-09-07");

    expect(espia).toHaveBeenCalledWith(
      "/api/turnos/disponibilidad?recurso_id=r1&fecha=2027-09-07",
      { cache: "no-store" },
    );
  });
});

describe("reservarTurno", () => {
  it("manda los cuatro datos que el backend necesita y ninguno mas", async () => {
    const espia = espiarFetch(respuesta(TURNO));

    await reservarTurno({
      cliente_id: "cl1",
      servicio_id: "s1",
      recurso_id: "r1",
      inicio: "2027-09-07T18:00:00.000Z",
    });

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    // Sin `duracion_min`: la duración sale del servicio, y mandarla desde el navegador
    // dejaría que dos turnos del mismo servicio duraran distinto.
    expect(opciones.body).toBe(
      JSON.stringify({
        cliente_id: "cl1",
        servicio_id: "s1",
        recurso_id: "r1",
        inicio: "2027-09-07T18:00:00.000Z",
      }),
    );
  });

  it("propaga el rechazo por solapamiento con la frase de la historia", async () => {
    espiarFetch(
      respuesta({ error: "FranjaOcupada", detalle: MENSAJE_HORARIO_OCUPADO }, false, 422),
    );

    await expect(
      reservarTurno({
        cliente_id: "cl1",
        servicio_id: "s1",
        recurso_id: "r1",
        inicio: "2027-09-07T18:00:00.000Z",
      }),
    ).rejects.toThrow(MENSAJE_HORARIO_OCUPADO);
  });
});

describe("cancelarTurno", () => {
  it("es un POST sin cuerpo: cancelar un turno no pide motivo", async () => {
    const espia = espiarFetch(respuesta({ ...TURNO, estado: "CANCELADO" }));

    await cancelarTurno("t1");

    expect(espia).toHaveBeenCalledWith("/api/turnos/t1/cancelacion", { method: "POST" });
  });
});

describe("reprogramarTurno", () => {
  it("manda solo el horario nuevo: el estado se conserva y no se manda", async () => {
    const espia = espiarFetch(respuesta(TURNO));

    await reprogramarTurno("t1", "2027-09-07T19:00:00.000Z");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/turnos/t1/reprogramacion");
    expect(opciones.body).toBe(JSON.stringify({ inicio: "2027-09-07T19:00:00.000Z" }));
  });
});

describe("registrarAsistencia", () => {
  it("una sola ruta para las dos marcas", async () => {
    const espia = espiarFetch(respuesta({ ...TURNO, estado: "COMPLETADO" }));

    await registrarAsistencia("t1", true);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/turnos/t1/asistencia");
    expect(opciones.body).toBe(JSON.stringify({ asistio: true }));
  });

  it("propaga el rechazo de un turno futuro", async () => {
    espiarFetch(
      respuesta(
        { error: "TurnoNoModificable", detalle: "El turno aún no transcurrió." },
        false,
        409,
      ),
    );

    await expect(registrarAsistencia("t1", false)).rejects.toThrow("El turno aún no transcurrió.");
  });
});

describe("tonoDeEstado", () => {
  it("le da a cada estado el tono que su significado pide", () => {
    // Un no-show es rojo y un cancelado no: la inasistencia es un problema, la cancelación
    // es una decisión.
    expect(tonoDeEstado("COMPLETADO")).toBe("ok");
    expect(tonoDeEstado("NO_SHOW")).toBe("error");
    expect(tonoDeEstado("RESERVADO")).toBe("atencion");
    expect(tonoDeEstado("CONFIRMADO")).toBe("atencion");
    expect(tonoDeEstado("CANCELADO")).toBe("pendiente");
  });
});

describe("horaDe", () => {
  it("devuelve una hora legible", () => {
    // La zona la pone el navegador. Lo que se afirma es la forma, no el número: el test
    // corre en la zona de quien lo corra.
    expect(horaDe("2027-09-07T18:00:00+00:00")).toMatch(/^\d{2}:\d{2}$/);
  });
});
