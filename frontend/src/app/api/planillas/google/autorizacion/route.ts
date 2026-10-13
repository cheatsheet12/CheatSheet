/**
 * BFF — where the user goes to grant read access to one spreadsheet (HU-E2-04 RN-01).
 *
 * **El `state` lo guarda este handler, no el backend.** El backend lo pone en una cookie de
 * su propia respuesta, y esa respuesta muere acá: `llamarApi` lee el JSON y descarta las
 * cabeceras, así que la cookie nunca llegaba al navegador y el guarda anti-CSRF del
 * callback no se podía satisfacer nunca. Poner la cookie en esta respuesta es lo que la
 * deja en el origen del panel, que es el único que el navegador va a visitar.
 *
 * El backend sigue verificando lo suyo: el callback le reenvía esta misma cookie. Son dos
 * chequeos del mismo valor en los dos lados de la frontera, y está bien que sean dos —
 * quien recibe el redirect de Google es el panel, y quien crea el vínculo es la API.
 */

import { NextResponse } from "next/server";

import { comoRutaDelBff, ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";
import { cuerpoDe } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export const COOKIE_ESTADO = "planilla_oauth_state";
/**
 * La planilla que la persona eligió, guardada para que sobreviva el redirect.
 *
 * En el flujo real la elige en el selector de archivos de Google y el identificador lo
 * conoce el panel, no el proveedor: no vuelve en el callback, así que hay que acordarse.
 * Una cookie corta es exactamente eso, y muere con el `state`.
 */
export const COOKIE_DOCUMENTO = "planilla_oauth_documento";
export const COOKIE_DIRECCION = "planilla_oauth_direccion";
/** Lo suficiente para elegir un archivo, y poco para que una pestaña olvidada no sea una invitación. */
const TTL_SEGUNDOS = 600;

export async function POST(request: Request): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  const { documento, direccion } = (await cuerpoDe(request)) as {
    documento?: string;
    direccion?: string;
  };
  if (typeof documento !== "string" || documento.trim() === "") {
    return NextResponse.json(
      { error: "EntradaInvalida", detalle: "Falta el enlace de la planilla." },
      { status: 422 },
    );
  }
  if (
    direccion !== undefined &&
    direccion !== "SOLO_LECTURA" &&
    direccion !== "LECTURA_Y_ESCRITURA"
  ) {
    return NextResponse.json(
      { error: "EntradaInvalida", detalle: "Dirección inválida." },
      { status: 422 },
    );
  }
  try {
    const datos = await comoRutaDelBff(() =>
      llamarApi<{ url: string }>("/planillas/google/autorizacion", {
        method: "POST",
      }),
    );
    const respuesta = NextResponse.json(datos);

    // El `state` viaja dentro de la URL que el backend arma. Leerlo de ahí evita que el
    // panel invente uno propio: el que se compara al volver tiene que ser el que el
    // proveedor recibió.
    const estado = new URL(datos.url, "http://interno").searchParams.get("state");
    if (estado !== null) {
      respuesta.cookies.set(COOKIE_ESTADO, estado, {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: TTL_SEGUNDOS,
      });
      respuesta.cookies.set(COOKIE_DOCUMENTO, documento.trim(), {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: TTL_SEGUNDOS,
      });
      respuesta.cookies.set(COOKIE_DIRECCION, direccion ?? "SOLO_LECTURA", {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: TTL_SEGUNDOS,
      });
    }
    return respuesta;
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
