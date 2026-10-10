/**
 * El cliente de API de las tres pantallas de facturación.
 *
 * Lo que este módulo decide por su cuenta es poco y todo importa: **que los montos crucen
 * como texto**, cuál de los dos campos del error se muestra, y cómo se arma el número que
 * ARCA imprime. Nada más — el resto lo decide el backend, que es lo correcto para un
 * módulo que toca plata.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeComprobante,
  emitirComprobante,
  listarComprobantes,
  numeroFormateado,
  tonoDeEstado,
  validarReceptor,
  verComprobante,
} from "@/features/billing";
import type { Comprobante } from "@/features/billing";

const COMPROBANTE: Comprobante = {
  id: "c1",
  tipo: "FACTURA_A",
  estado: "AUTORIZADO",
  numero: 123,
  punto_de_venta_id: "p1",
  cliente_id: "cl1",
  receptor_nombre: "Acme SA",
  receptor_cuit: "30712345671",
  receptor_condicion_iva: "RESPONSABLE_INSCRIPTO",
  cae: "75123456789012",
  cae_vence_el: "2026-09-17",
  motivo_de_rechazo: null,
  leyenda: null,
  subtotal: "2000.00",
  total_iva: "420.00",
  total: "2420.00",
  saldo_pendiente: "2420.00",
  fecha_emision: "2026-09-07T12:00:00Z",
  created_at: "2026-09-07T12:00:00Z",
  descargable: true,
  items: [],
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("listarComprobantes", () => {
  it("no manda filtros vacios en el query string", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta({ comprobantes: [] }));
    vi.stubGlobal("fetch", fetchFalso);

    await listarComprobantes({ desde: "", tipo: "FACTURA_A" });

    expect(fetchFalso).toHaveBeenCalledWith("/api/comprobantes?tipo=FACTURA_A", {
      cache: "no-store",
    });
  });

  it("sin filtros no agrega el signo de pregunta", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta({ comprobantes: [] }));
    vi.stubGlobal("fetch", fetchFalso);

    await listarComprobantes();

    expect(fetchFalso).toHaveBeenCalledWith("/api/comprobantes", { cache: "no-store" });
  });

  it("no cachea: el estado cambia cuando ARCA contesta", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta({ comprobantes: [COMPROBANTE] }));
    vi.stubGlobal("fetch", fetchFalso);

    const listado = await listarComprobantes();

    expect(listado.comprobantes).toHaveLength(1);
    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(opciones.cache).toBe("no-store");
  });
});

describe("verComprobante", () => {
  it("propaga el detalle del backend cuando el comprobante no existe", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          respuesta({ error: "EntradaInvalida", detalle: "El comprobante no existe" }, false, 422),
        ),
    );

    await expect(verComprobante("c1")).rejects.toThrow("El comprobante no existe");
  });
});

describe("validarReceptor", () => {
  it("escapa el CUIT en la ruta", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(
      respuesta({
        nombre: "Acme",
        cuit: "30712345671",
        condicion_iva: "RESPONSABLE_INSCRIPTO",
        tipos_disponibles: ["FACTURA_A"],
      }),
    );
    vi.stubGlobal("fetch", fetchFalso);

    await validarReceptor("30-71234567-1");

    expect(fetchFalso.mock.calls[0]?.[0]).toBe("/api/comprobantes/receptores/30-71234567-1");
  });

  it("muestra la frase de la historia cuando el CUIT no esta en el padron", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respuesta(
          {
            error: "EntradaInvalida",
            detalle: "No se encontró el CUIT en el padrón de ARCA.",
          },
          false,
          422,
        ),
      ),
    );

    await expect(validarReceptor("30712345671")).rejects.toThrow(
      "No se encontró el CUIT en el padrón de ARCA.",
    );
  });
});

describe("emitirComprobante", () => {
  it("los montos cruzan como texto y nunca como numero", async () => {
    // El test que impide la regresion mas cara de este modulo: un `number` en el cuerpo
    // llega al backend como float, que es lo que `CLAUDE.md` §3.5 prohibe.
    const fetchFalso = vi.fn().mockResolvedValue(respuesta(COMPROBANTE, true, 202));
    vi.stubGlobal("fetch", fetchFalso);

    await emitirComprobante({
      cliente_id: "cl1",
      punto_de_venta_id: "p1",
      tipo: "FACTURA_A",
      receptor_cuit: "30712345671",
      receptor_domicilio: null,
      items: [
        {
          descripcion: "Corte",
          cantidad: "2",
          precio_unitario: "1000.00",
          alicuota_iva: "0.21",
        },
      ],
    });

    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    const cuerpo = JSON.parse(String(opciones.body)) as {
      items: { precio_unitario: unknown; cantidad: unknown }[];
    };
    expect(typeof cuerpo.items[0]?.precio_unitario).toBe("string");
    expect(cuerpo.items[0]?.precio_unitario).toBe("1000.00");
    expect(typeof cuerpo.items[0]?.cantidad).toBe("string");
  });

  it("muestra las palabras de ARCA cuando rechaza", async () => {
    // «Error 10016: …» es texto de ARCA, no nuestro. Traducirlo seria decidir que
    // significan cuarenta codigos numericos.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        respuesta(
          {
            error: "EntradaInvalida",
            detalle: "Error 10016: el comprobante no cumple la resolucion general vigente",
          },
          false,
          422,
        ),
      ),
    );

    await expect(
      emitirComprobante({
        cliente_id: "cl1",
        punto_de_venta_id: "p1",
        tipo: "FACTURA_A",
        receptor_cuit: "30712345671",
        receptor_domicilio: null,
        items: [],
      }),
    ).rejects.toThrow(/10016/);
  });

  it("cae al codigo cuando el backend no manda detalle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respuesta({ error: "ArcaNoDisponible" }, false, 503)),
    );

    await expect(
      emitirComprobante({
        cliente_id: "cl1",
        punto_de_venta_id: "p1",
        tipo: "FACTURA_A",
        receptor_cuit: "30712345671",
        receptor_domicilio: null,
        items: [],
      }),
    ).rejects.toBeInstanceOf(ErrorDeComprobante);
  });
});

describe("numeroFormateado", () => {
  it("arma el numero como lo imprime ARCA", () => {
    expect(numeroFormateado(COMPROBANTE, 1)).toBe("0001-00000123");
  });

  it("un borrador dice que no tiene numero en vez de mostrar ceros", () => {
    // `0001-00000000` parece un numero real que da la casualidad de ser cero.
    expect(numeroFormateado({ ...COMPROBANTE, numero: null }, 1)).toBe("Sin numerar");
  });

  it("sin el punto de venta a mano, el numero igual se muestra", () => {
    // Cuatro guiones donde iria el punto, mas el separador. El numero del comprobante es
    // lo que no se puede omitir: es lo que alguien busca contra un papel.
    expect(numeroFormateado(COMPROBANTE, null)).toBe("-----00000123");
  });
});

describe("tonoDeEstado", () => {
  it("solo el rechazo es un error", () => {
    expect(tonoDeEstado("AUTORIZADO")).toBe("ok");
    expect(tonoDeEstado("RECHAZADO")).toBe("error");
    expect(tonoDeEstado("ENVIADO_A_ARCA")).toBe("atencion");
    expect(tonoDeEstado("BORRADOR")).toBe("pendiente");
  });
});
