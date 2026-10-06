/**
 * El cliente de API del paquete contable y del acceso del contador (HU-E10-04 … HU-E10-06).
 *
 * Lo que este archivo fija:
 *
 * - **la invitación no devuelve el enlace.** Lo que vuelve es el estado del contador, y el
 *   test lo afirma por ausencia: si alguien agregara el enlace a la respuesta, esto se cae;
 * - **revocar no espera cuerpo.** El backend contesta 204, y un `json()` sobre eso rompería
 *   justo en el camino que tiene que ser infalible;
 * - **la URL del contador escapa el valor del enlace.** Es un token opaco que viene de la
 *   barra de direcciones: meterlo crudo en una plantilla es cómo se arma una URL rota.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDePaquete,
  MENSAJE_ACCESO_NO_DISPONIBLE,
  MENSAJE_SIN_EMAIL,
  generarPaquete,
  guardarConfiguracion,
  invitarContador,
  listarPaquetes,
  revocarContador,
  urlDePaquete,
  urlDePaqueteDelContador,
  verAccesoDelContador,
  verConfiguracion,
} from "@/features/reporting";
import type { ConfiguracionDelPaqueteRespuesta } from "@/features/reporting";

const CONFIGURACION: ConfiguracionDelPaqueteRespuesta = {
  activo: true,
  dia_de_envio: 5,
  formatos: ["PDF"],
  contenido: ["FACTURAS"],
  email_contador: "contador@estudio.com.ar",
  proximo_envio: "2026-04-05T00:00:00Z",
  contador: {
    email: "contador@estudio.com.ar",
    invitado: true,
    vence: "2026-05-05T00:00:00Z",
    accesos: 3,
  },
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

describe("la configuración", () => {
  it("se lee entera", async () => {
    espiarFetch(respuesta(CONFIGURACION));

    const configuracion = await verConfiguracion();

    expect(configuracion.contador.accesos).toBe(3);
    expect(configuracion.proximo_envio).toBe("2026-04-05T00:00:00Z");
  });

  it("se guarda con un PUT y el cuerpo completo", async () => {
    const espia = espiarFetch(respuesta(CONFIGURACION));

    await guardarConfiguracion({
      dia_de_envio: 10,
      formatos: ["PDF", "XML"],
      contenido: ["FACTURAS"],
      email_contador: "contador@estudio.com.ar",
      activo: true,
    });

    const [url, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/reporteria/configuracion");
    expect(opciones.method).toBe("PUT");
    expect(opciones.body).toContain('"dia_de_envio":10');
  });

  it("propaga la frase de la historia cuando falta el email", async () => {
    espiarFetch(respuesta({ error: "InvarianteViolada", detalle: MENSAJE_SIN_EMAIL }, false, 409));

    await expect(
      guardarConfiguracion({
        dia_de_envio: 5,
        formatos: ["PDF"],
        contenido: ["FACTURAS"],
        email_contador: null,
        activo: true,
      }),
    ).rejects.toThrow(MENSAJE_SIN_EMAIL);
  });
});

describe("los paquetes", () => {
  it("se listan", async () => {
    espiarFetch(respuesta({ paquetes: [] }));

    expect(await listarPaquetes()).toEqual({ paquetes: [] });
  });

  it("el de prueba sale sin período", async () => {
    const espia = espiarFetch(
      respuesta({
        id: "p1",
        periodo: "2026-03",
        anio: 2026,
        mes: 3,
        totales_por_tipo: {},
        disponible: true,
      }),
    );

    await generarPaquete();

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(opciones.body).toBe("{}");
  });

  it("uno de un período elegido manda año y mes", async () => {
    const espia = espiarFetch(
      respuesta({
        id: "p1",
        periodo: "2026-02",
        anio: 2026,
        mes: 2,
        totales_por_tipo: {},
        disponible: true,
      }),
    );

    await generarPaquete({ anio: 2026, mes: 2 });

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(opciones.body).toBe(JSON.stringify({ anio: 2026, mes: 2 }));
  });
});

describe("el contador", () => {
  it("la invitación devuelve el estado y **no** el enlace", async () => {
    espiarFetch(respuesta(CONFIGURACION.contador));

    const contador = await invitarContador("contador@estudio.com.ar");

    expect(contador.invitado).toBe(true);
    expect(contador).not.toHaveProperty("enlace");
  });

  it("un email inválido levanta con la frase del backend", async () => {
    espiarFetch(
      respuesta({ error: "EntradaInvalida", detalle: "Ingrese un email válido." }, false, 422),
    );

    await expect(invitarContador("no-es-un-email")).rejects.toBeInstanceOf(ErrorDePaquete);
  });

  it("revocar no lee el cuerpo de la respuesta", async () => {
    const sinCuerpo = {
      ok: true,
      status: 204,
      json: () => Promise.reject(new Error("204 no trae cuerpo")),
    } as unknown as Response;
    espiarFetch(sinCuerpo);

    await expect(revocarContador()).resolves.toBeUndefined();
  });

  it("revocar propaga un fallo", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(revocarContador()).rejects.toBeInstanceOf(ErrorDePaquete);
  });
});

describe("el acceso sin sesión", () => {
  it("pide el acceso con el valor del enlace escapado", async () => {
    const espia = espiarFetch(
      respuesta({ vence: "2026-05-05T00:00:00Z", tablero: {}, paquetes: { paquetes: [] } }),
    );

    await verAccesoDelContador("un valor/raro");

    expect(espia).toHaveBeenCalledWith("/api/contador/un%20valor%2Fraro", expect.anything());
  });

  it("un enlace revocado da la frase de la historia", async () => {
    espiarFetch(
      respuesta({ error: "AccesoNoDisponible", detalle: MENSAJE_ACCESO_NO_DISPONIBLE }, false, 422),
    );

    await expect(verAccesoDelContador("abc")).rejects.toThrow(MENSAJE_ACCESO_NO_DISPONIBLE);
  });

  it("la descarga del contador lleva el enlace y el paquete", () => {
    expect(urlDePaqueteDelContador("abc", "p1")).toBe("/api/contador/abc/paquetes/p1");
  });
});

describe("urlDePaquete", () => {
  it("apunta al BFF", () => {
    expect(urlDePaquete("p1")).toBe("/api/reporteria/paquetes/p1/archivo");
  });
});
