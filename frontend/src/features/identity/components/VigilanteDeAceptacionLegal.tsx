/**
 * Turns "you owe a legal document" into the redirect to the screen that settles it
 * (HU-E1-03 RN-03, HU-E1-08 RN-05).
 *
 * While a document is pending the API answers **403 `AceptacionLegalPendiente`** to every call
 * but a short list. The layout of the panel already sends somebody there on a full page load,
 * but a person who is *already inside* when a version changes keeps calling the BFF from
 * screens that each translate errors in their own way, and none of them could say anything
 * useful about this one: they would print "No se pudo completar la operación" and leave the
 * person stuck (the pattern of issue #75). This component watches the one place all of those
 * calls go through, the browser's `fetch`, and navigates instead.
 *
 * - It only looks at **403s from this app's own `/api/` routes**, and only acts when the body
 *   names `AceptacionLegalPendiente`. Any other 403 (a role that may not do something) passes
 *   through untouched, with its body still readable: it inspects a clone.
 * - The call that was refused **never settles**: the page is on its way out, and resolving it
 *   would let its screen flash a generic error first.
 * - It does nothing on `/aceptacion-legal` itself, so the screen cannot redirect to itself.
 */

"use client";

import { useEffect } from "react";

const RUTA_DE_ACEPTACION = "/aceptacion-legal";
const CODIGO_DE_BLOQUEO = "AceptacionLegalPendiente";

function irA(destino: string): void {
  window.location.assign(destino);
}

function urlDe(entrada: RequestInfo | URL): string {
  if (typeof entrada === "string") {
    return entrada;
  }
  return entrada instanceof URL ? entrada.href : entrada.url;
}

function esDeLaApp(entrada: RequestInfo | URL): boolean {
  try {
    const url = new URL(urlDe(entrada), window.location.origin);
    return url.origin === window.location.origin && url.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

async function esBloqueoLegal(respuesta: Response): Promise<boolean> {
  try {
    const cuerpo: unknown = await respuesta.clone().json();
    return (
      typeof cuerpo === "object" &&
      cuerpo !== null &&
      "error" in cuerpo &&
      cuerpo.error === CODIGO_DE_BLOQUEO
    );
  } catch {
    return false;
  }
}

export interface PropsDeVigilante {
  /** How to leave. Defaults to a full navigation; a test replaces it. */
  readonly ir?: (destino: string) => void;
}

export function VigilanteDeAceptacionLegal({ ir = irA }: PropsDeVigilante): null {
  useEffect(() => {
    const original = window.fetch;
    const vigilado: typeof fetch = async (entrada, opciones) => {
      const respuesta = await original(entrada, opciones);
      if (
        respuesta.status !== 403 ||
        !esDeLaApp(entrada) ||
        window.location.pathname === RUTA_DE_ACEPTACION ||
        !(await esBloqueoLegal(respuesta))
      ) {
        return respuesta;
      }
      ir(RUTA_DE_ACEPTACION);
      return new Promise<Response>(() => undefined);
    };
    window.fetch = vigilado;
    return () => {
      if (window.fetch === vigilado) {
        window.fetch = original;
      }
    };
  }, [ir]);

  return null;
}
