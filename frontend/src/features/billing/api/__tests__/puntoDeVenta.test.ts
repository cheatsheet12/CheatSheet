/**
 * El cliente de API de PAN-FAC-05.
 *
 * Lo único que este módulo decide por su cuenta es **cuál de los dos campos del error se
 * muestra**, y esa decisión es la que hace que el usuario lea «El punto de venta no está
 * habilitado en ARCA.» en vez de `PuntoDeVentaNoHabilitado`. Los dos mensajes de la
 * historia se afirman acá letra por letra: si alguien reescribe el texto de un lado, esto
 * se cae.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDePuntoDeVenta,
  MENSAJE_DUPLICADO,
  MENSAJE_NO_HABILITADO,
  cambiarEstadoDePuntoDeVenta,
  listarPuntosDeVenta,
  registrarPuntoDeVenta,
  resumenDeNumeracion,
} from "@/features/billing";
import type { PuntoDeVenta } from "@/features/billing";

const PUNTO: PuntoDeVenta = {
  id: "p1",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: { FACTURA_B: 12 },
  created_at: "2026-09-07T12:00:00Z",
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: () => Promise.resolve(cuerpo),
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("listarPuntosDeVenta", () => {
  it("no cachea: la numeracion cambia con cada comprobante emitido", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta({ puntos: [PUNTO] }));
    vi.stubGlobal("fetch", fetchFalso);

    const listado = await listarPuntosDeVenta();

    expect(listado.puntos).toHaveLength(1);
    expect(fetchFalso).toHaveBeenCalledWith("/api/puntos-de-venta", { cache: "no-store" });
  });

  it("falla con el codigo cuando la sesion se vencio con la pantalla abierta", async () => {
    // La pantalla recarga sola despues de cada accion, asi que este es el camino real de
    // un 401: no hay `detalle` que mostrar, y el codigo es mejor que una pantalla en blanco.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respuesta({ error: "NoAutenticado" }, false, 401)),
    );

    await expect(listarPuntosDeVenta()).rejects.toThrow("NoAutenticado");
  });
});

describe("registrarPuntoDeVenta", () => {
  it("muestra el detalle del backend cuando ARCA no tiene habilitado el punto", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          respuesta(
            { error: "PuntoDeVentaNoHabilitado", detalle: MENSAJE_NO_HABILITADO },
            false,
            422,
          ),
        ),
    );

    await expect(registrarPuntoDeVenta({ numero: 7, descripcion: null })).rejects.toThrow(
      MENSAJE_NO_HABILITADO,
    );
  });

  it("muestra el detalle del backend cuando el numero ya existe", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          respuesta({ error: "PuntoDeVentaDuplicado", detalle: MENSAJE_DUPLICADO }, false, 422),
        ),
    );

    await expect(registrarPuntoDeVenta({ numero: 1, descripcion: null })).rejects.toThrow(
      MENSAJE_DUPLICADO,
    );
  });

  it("devuelve el punto creado cuando ARCA lo confirma", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta(PUNTO, true, 201));
    vi.stubGlobal("fetch", fetchFalso);

    const creado = await registrarPuntoDeVenta({ numero: 1, descripcion: "Casa central" });

    expect(creado).toEqual(PUNTO);
    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(opciones.body))).toEqual({ numero: 1, descripcion: "Casa central" });
  });

  it("cae al codigo cuando el backend no manda detalle", async () => {
    // Un 500 no trae `detalle`. Mostrar «undefined» sería peor que mostrar el codigo.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respuesta({ error: "ErrorInterno" }, false, 500)),
    );

    await expect(registrarPuntoDeVenta({ numero: 1, descripcion: null })).rejects.toBeInstanceOf(
      ErrorDePuntoDeVenta,
    );
  });
});

describe("cambiarEstadoDePuntoDeVenta", () => {
  it("manda el estado pedido a la ruta del punto", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(respuesta({ ...PUNTO, activo: false }));
    vi.stubGlobal("fetch", fetchFalso);

    await cambiarEstadoDePuntoDeVenta("p1", false);

    const [ruta, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/puntos-de-venta/p1/estado");
    expect(opciones.method).toBe("PUT");
    expect(JSON.parse(String(opciones.body))).toEqual({ activo: false });
  });

  it("reactivar falla cuando ARCA ya no tiene habilitado el punto", async () => {
    // El backend vuelve a preguntarle a ARCA al reactivar, asi que este camino existe
    // incluso para un punto que se dio de alta sin problemas hace meses.
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          respuesta({ error: "EntradaInvalida", detalle: MENSAJE_NO_HABILITADO }, false, 422),
        ),
    );

    await expect(cambiarEstadoDePuntoDeVenta("p1", true)).rejects.toThrow(MENSAJE_NO_HABILITADO);
  });
});

describe("resumenDeNumeracion", () => {
  it("nombra los tipos con la etiqueta y no con el enum", () => {
    expect(resumenDeNumeracion(PUNTO)).toBe("Factura B: 12");
  });

  it("es vacio cuando el punto todavia no emitio nada", () => {
    // La pantalla usa ese vacio para escribir «Sin emisiones».
    expect(resumenDeNumeracion({ ...PUNTO, numerador_por_tipo: {} })).toBe("");
  });
});
