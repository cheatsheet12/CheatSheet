/**
 * El cliente de API de las tres pantallas de cobros.
 *
 * Dos cosas se afirman acá y en ningún otro lado del frontend:
 *
 * - **el monto viaja como texto.** Es el invariante que sostiene todo el archivo, y la
 *   manera de romperlo sin darse cuenta es un `Number()` puesto para «normalizar»: el
 *   cuerpo que sale se compara carácter por carácter para que eso se caiga;
 * - **`copiarLink` dice que no pudo.** Fuera de un contexto seguro `navigator.clipboard`
 *   no existe, y un `catch` que devolviera `true` haría que alguien pegue lo que tenía
 *   antes en el portapapeles en el WhatsApp de un cliente.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  MENSAJE_MP_CAIDO,
  actualizarReembolso,
  cancelarCobro,
  copiarLink,
  corregirReembolso,
  generarCobro,
  listarCobros,
  pendienteDeReembolso,
  reembolsarCobro,
  regenerarLink,
  registrarReembolso,
  tieneReembolsos,
  tonoDeEstado,
  verCobro,
} from "@/features/payments";
import type { Cobro } from "@/features/payments";

const COBRO: Cobro = {
  id: "co1",
  cliente_id: "cl1",
  comprobante_id: null,
  turno_id: null,
  monto: "12500.10",
  monto_reembolsado: "0.00",
  descripcion: "Consulta",
  estado: "PENDIENTE",
  url_de_pago: "https://mp.test/checkout/co1",
  tiene_link_activo: true,
  vence_el: "2026-09-20",
  fecha_pago: null,
  fecha_pago_aproximada: false,
  medio_de_pago: "LINK_MERCADOPAGO",
  numero_de_operacion: null,
  reembolso_en_proceso: false,
  reembolso_en_proceso_monto: null,
  tiene_pago_huerfano: false,
  motivo_de_cancelacion: null,
  created_at: "2026-09-07T12:00:00Z",
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
  vi.clearAllMocks();
});

describe("listarCobros", () => {
  it("no cachea: el estado de un cobro cambia por un webhook, no por una accion nuestra", async () => {
    const espia = espiarFetch(respuesta({ cobros: [COBRO], metricas: {} }));

    await listarCobros();

    expect(espia).toHaveBeenCalledWith("/api/cobros", { cache: "no-store" });
  });

  it("arma el query string con los filtros que tienen valor y con ninguno mas", async () => {
    const espia = espiarFetch(respuesta({ cobros: [], metricas: {} }));

    await listarCobros({ desde: "2026-09-01", hasta: "", estado: "VENCIDO" });

    // `hasta` vacio no viaja: `hasta=` seria un filtro por la cadena vacia, que no es lo
    // mismo que no filtrar por fecha de fin.
    expect(espia).toHaveBeenCalledWith("/api/cobros?desde=2026-09-01&estado=VENCIDO", {
      cache: "no-store",
    });
  });

  it("prefiere el detalle del backend al codigo de la excepcion", async () => {
    espiarFetch(
      respuesta({ error: "PasarelaNoDisponible", detalle: MENSAJE_MP_CAIDO }, false, 502),
    );

    await expect(listarCobros()).rejects.toThrow(MENSAJE_MP_CAIDO);
  });

  it("cae en el codigo cuando el backend no mando detalle", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(listarCobros()).rejects.toThrow("NoAutenticado");
  });

  it("no se rompe con un cuerpo que no es JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: () => Promise.reject(new Error("no es JSON")),
      } as unknown as Response),
    );

    await expect(listarCobros()).rejects.toBeInstanceOf(ErrorDeCobro);
  });
});

describe("verCobro", () => {
  it("pide el detalle del cobro sin cache", async () => {
    const espia = espiarFetch(respuesta({ ...COBRO, recordatorios: [] }));

    const detalle = await verCobro("co1");

    expect(detalle.id).toBe("co1");
    expect(espia).toHaveBeenCalledWith("/api/cobros/co1", { cache: "no-store" });
  });
});

describe("generarCobro", () => {
  it("manda el monto tal como se escribio, sin pasar por un numero", async () => {
    const espia = espiarFetch(respuesta(COBRO));

    await generarCobro({ cliente_id: "cl1", monto: "12500.10", descripcion: "Consulta" });

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    // Caracter por caracter: `12500.1` seria la prueba de que un `Number()` se metio en el
    // camino, y ese redondeo es el que se come un centavo.
    expect(opciones.body).toBe(
      JSON.stringify({ cliente_id: "cl1", monto: "12500.10", descripcion: "Consulta" }),
    );
  });

  it("propaga la caida de MercadoPago con la frase de la historia", async () => {
    espiarFetch(
      respuesta({ error: "PasarelaNoDisponible", detalle: MENSAJE_MP_CAIDO }, false, 502),
    );

    await expect(
      generarCobro({ cliente_id: "cl1", monto: "100", descripcion: "x" }),
    ).rejects.toThrow(MENSAJE_MP_CAIDO);
  });
});

describe("regenerarLink", () => {
  it("es un POST sin cuerpo: no hay nada que elegir, se rehace el link", async () => {
    const espia = espiarFetch(respuesta(COBRO));

    await regenerarLink("co1");

    expect(espia).toHaveBeenCalledWith("/api/cobros/co1/link", { method: "POST" });
  });

  it("falla cuando el cobro ya no admite un link", async () => {
    espiarFetch(respuesta({ error: "CobroNoEstaAbierto" }, false, 422));

    await expect(regenerarLink("co1")).rejects.toThrow("CobroNoEstaAbierto");
  });
});

describe("cancelarCobro", () => {
  it("manda el motivo en el cuerpo, que es donde la bitacora lo va a buscar", async () => {
    const espia = espiarFetch(respuesta({ ...COBRO, estado: "CANCELADO" }));

    await cancelarCobro("co1", "El cliente pago por transferencia");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/cobros/co1/cancelacion");
    expect(opciones.body).toBe(JSON.stringify({ motivo: "El cliente pago por transferencia" }));
  });
});

describe("reembolsarCobro", () => {
  it("manda el monto como texto, igual que al generar", async () => {
    const espia = espiarFetch(respuesta({ ...COBRO, estado: "REEMBOLSADO" }));

    await reembolsarCobro("co1", "12500.10");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/cobros/co1/reembolso");
    expect(opciones.body).toBe(JSON.stringify({ monto: "12500.10" }));
  });

  it("muestra el rechazo de MercadoPago con las palabras del backend", async () => {
    const frase = "MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.";
    espiarFetch(respuesta({ error: "ReembolsoRechazado", detalle: frase }, false, 422));

    await expect(reembolsarCobro("co1", "100")).rejects.toThrow(frase);
  });
});

describe("copiarLink", () => {
  it("copia cuando el navegador deja", async () => {
    const escribir = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText: escribir } });

    expect(await copiarLink("https://mp.test/x")).toBe(true);
    expect(escribir).toHaveBeenCalledWith("https://mp.test/x");
  });

  it("dice que no pudo cuando no hay portapapeles, en vez de mentir", async () => {
    // Exactamente lo que pasa fuera de un contexto seguro: la API no existe.
    vi.stubGlobal("navigator", {});

    expect(await copiarLink("https://mp.test/x")).toBe(false);
  });

  it("dice que no pudo cuando el navegador niega el permiso", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denegado")) },
    });

    expect(await copiarLink("https://mp.test/x")).toBe(false);
  });
});

describe("tonoDeEstado", () => {
  it("le da a cada estado el tono que su significado pide", () => {
    // `VENCIDO` es rojo y `PENDIENTE` no: la mora es un problema, la espera todavia no.
    expect(tonoDeEstado("APROBADO")).toBe("ok");
    expect(tonoDeEstado("VENCIDO")).toBe("error");
    expect(tonoDeEstado("PENDIENTE")).toBe("atencion");
    expect(tonoDeEstado("CANCELADO")).toBe("pendiente");
    expect(tonoDeEstado("REEMBOLSADO")).toBe("pendiente");
    // Un parcial todavía se puede seguir devolviendo: pide un vistazo.
    expect(tonoDeEstado("REEMBOLSADO_PARCIAL")).toBe("atencion");
  });
});

describe("los reembolsos parciales y manuales (HU-E6-05)", () => {
  it("«Actualizar estado» es un POST a la ruta de actualización, sin cuerpo", async () => {
    const espia = espiarFetch(respuesta({ ...COBRO, estado: "REEMBOLSADO_PARCIAL" }));

    await actualizarReembolso("co1");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/cobros/co1/reembolso/actualizacion");
    expect(opciones.method).toBe("POST");
    expect(opciones.body).toBeUndefined();
  });

  it("registrar un reembolso manda el monto y la fecha como texto", async () => {
    const espia = espiarFetch(respuesta(COBRO));

    await registrarReembolso("co1", {
      monto: "300.10",
      fecha: "2026-09-20",
      referencia: "OP-77",
      motivo: "Devolución por transferencia",
    });

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/cobros/co1/reembolsos");
    // Carácter por carácter: un `Number()` puesto para «normalizar» se cae acá.
    expect(opciones.body).toBe(
      JSON.stringify({
        monto: "300.10",
        fecha: "2026-09-20",
        referencia: "OP-77",
        motivo: "Devolución por transferencia",
      }),
    );
  });

  it("omite la referencia cuando quedó vacía", async () => {
    const espia = espiarFetch(respuesta(COBRO));

    await registrarReembolso("co1", {
      monto: "300.10",
      fecha: "2026-09-20",
      referencia: "   ",
      motivo: "Devolución",
    });

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(opciones.body))).toEqual({
      monto: "300.10",
      fecha: "2026-09-20",
      motivo: "Devolución",
    });
  });

  it("corregir manda solo el motivo, a la ruta de esa fila", async () => {
    const espia = espiarFetch(respuesta(COBRO));

    await corregirReembolso("co1", "rb1", "Se cargó por error");

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/cobros/co1/reembolsos/rb1/correccion");
    expect(opciones.body).toBe(JSON.stringify({ motivo: "Se cargó por error" }));
  });

  it("un conflicto llega con las palabras del backend", async () => {
    const frase = "Este cobro ya tiene un reembolso en proceso.";
    const conflicto = { error: "ReembolsoEnProceso", detalle: frase };
    espiarFetch(respuesta(conflicto, false, 409), respuesta(conflicto, false, 409));

    await expect(actualizarReembolso("co1")).rejects.toThrow(frase);
    await expect(actualizarReembolso("co1")).rejects.toBeInstanceOf(ErrorDeCobro);
  });
});

describe("pendienteDeReembolso", () => {
  it("resta en centavos y no en punto flotante", () => {
    // `1000.00 - 0.10` con floats no da 999.90 exacto; con centavos enteros sí.
    expect(pendienteDeReembolso({ monto: "1000.00", monto_reembolsado: "0.10" })).toBe("999.90");
    expect(pendienteDeReembolso({ monto: "12500.10", monto_reembolsado: "0.20" })).toBe("12499.90");
    expect(pendienteDeReembolso({ monto: "0.30", monto_reembolsado: "0.10" })).toBe("0.20");
  });

  it("sin reembolsos falta todo, y con todo reembolsado no falta nada", () => {
    expect(pendienteDeReembolso({ monto: "12500.10", monto_reembolsado: "0.00" })).toBe("12500.10");
    expect(pendienteDeReembolso({ monto: "1000.00", monto_reembolsado: "1000.00" })).toBe("0.00");
  });

  it("completa los decimales que faltan", () => {
    expect(pendienteDeReembolso({ monto: "100", monto_reembolsado: "0.5" })).toBe("99.50");
  });
});

describe("tieneReembolsos", () => {
  it("es verdadero solo con un acumulado mayor que cero", () => {
    expect(tieneReembolsos({ monto_reembolsado: "0.00" })).toBe(false);
    expect(tieneReembolsos({ monto_reembolsado: "0.01" })).toBe(true);
    expect(tieneReembolsos({ monto_reembolsado: "250.00" })).toBe(true);
  });
});

describe("las etiquetas de estado", () => {
  it("el parcial se lee «Reembolsado parcialmente»", () => {
    expect(ETIQUETAS_DE_ESTADO.REEMBOLSADO_PARCIAL).toBe("Reembolsado parcialmente");
    expect(ETIQUETAS_DE_ESTADO.REEMBOLSADO).toBe("Reembolsado");
  });
});
