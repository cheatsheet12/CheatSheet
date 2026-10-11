/**
 * @vitest-environment jsdom
 *
 * The browser-side watcher (HU-E1-03 RN-03, HU-E1-08 RN-05): a `403 AceptacionLegalPendiente`
 * from **any** call of the panel becomes the redirect to `/aceptacion-legal`, instead of the
 * generic error each screen would otherwise print.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VigilanteDeAceptacionLegal } from "../VigilanteDeAceptacionLegal";

const BLOQUEO = { error: "AceptacionLegalPendiente", pendientes: ["PRIVACIDAD"] };

let original: typeof fetch;
const respuestaDelServidor = vi.fn();
const ir = vi.fn();

function respuesta(estado: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status: estado });
}

/** Resolves with what the promise settled to, or `"colgada"` if it did not within a moment. */
async function resultadoDe(promesa: Promise<Response>): Promise<Response | "colgada"> {
  return Promise.race([
    promesa,
    new Promise<"colgada">((resolver) => setTimeout(() => resolver("colgada"), 30)),
  ]);
}

beforeEach(() => {
  original = window.fetch;
  window.fetch = respuestaDelServidor as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  window.fetch = original;
  respuestaDelServidor.mockReset();
  ir.mockReset();
  window.history.pushState({}, "", "/");
});

describe("VigilanteDeAceptacionLegal", () => {
  it("un 403 AceptacionLegalPendiente de la app lleva a /aceptacion-legal", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(403, BLOQUEO));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await resultadoDe(window.fetch("/api/clientes"));

    expect(ir).toHaveBeenCalledTimes(1);
    expect(ir).toHaveBeenCalledWith("/aceptacion-legal");
    expect(resultado).toBe("colgada");
  });

  it("no deja que la pantalla muestre su error genérico mientras se va", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(403, BLOQUEO));
    render(<VigilanteDeAceptacionLegal ir={ir} />);
    const alFallar = vi.fn();

    void window.fetch("/api/usuarios", { method: "POST" }).then(alFallar, alFallar);
    await new Promise((resolver) => setTimeout(resolver, 30));

    expect(alFallar).not.toHaveBeenCalled();
  });

  it("también lo reconoce cuando la llamada lleva una URL absoluta de la misma app", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(403, BLOQUEO));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    await resultadoDe(window.fetch(`${window.location.origin}/api/cobros`));

    expect(ir).toHaveBeenCalledWith("/aceptacion-legal");
  });

  it("un 403 por otro motivo pasa intacto", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(403, { error: "PermisoDenegado" }));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await window.fetch("/api/usuarios");

    expect(ir).not.toHaveBeenCalled();
    expect(resultado.status).toBe(403);
    expect(await resultado.json()).toEqual({ error: "PermisoDenegado" });
  });

  it("una respuesta correcta pasa intacta", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(200, { ok: true }));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await window.fetch("/api/clientes");

    expect(ir).not.toHaveBeenCalled();
    expect(await resultado.json()).toEqual({ ok: true });
  });

  it("un 403 con cuerpo que no es JSON pasa intacto", async () => {
    respuestaDelServidor.mockResolvedValue(new Response("<html>", { status: 403 }));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await window.fetch("/api/clientes");

    expect(ir).not.toHaveBeenCalled();
    expect(resultado.status).toBe(403);
  });

  it("ignora lo que no es de la app aunque diga lo mismo", async () => {
    respuestaDelServidor.mockResolvedValue(respuesta(403, BLOQUEO));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await window.fetch("https://otro.example/api/clientes");

    expect(ir).not.toHaveBeenCalled();
    expect(resultado.status).toBe(403);
  });

  it("en la propia pantalla de aceptación no redirige a sí misma", async () => {
    window.history.pushState({}, "", "/aceptacion-legal");
    respuestaDelServidor.mockResolvedValue(respuesta(403, BLOQUEO));
    render(<VigilanteDeAceptacionLegal ir={ir} />);

    const resultado = await window.fetch("/api/legal/aceptaciones", { method: "POST" });

    expect(ir).not.toHaveBeenCalled();
    expect(resultado.status).toBe(403);
  });

  it("al desmontarse deja el fetch como estaba", () => {
    const { unmount } = render(<VigilanteDeAceptacionLegal ir={ir} />);
    expect(window.fetch).not.toBe(respuestaDelServidor);

    unmount();

    expect(window.fetch).toBe(respuestaDelServidor);
  });
});
