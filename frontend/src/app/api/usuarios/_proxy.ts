/**
 * Shared plumbing for the user-administration route handlers.
 *
 * Every one of them does the same three things: refuse without a session, forward to the
 * backend with the bearer token from the HttpOnly cookie, and translate a failure into a
 * body carrying the error *code* and nothing else. Writing that seven times is writing
 * six chances to forget the first step.
 *
 * The underscore keeps the file out of Next's routing.
 */

import { NextResponse } from "next/server";

import { comoRutaDelBff, ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export type Metodo = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * `cabeceras` es opcional y aditivo: las demás rutas no lo pasan y se comportan igual. Existe para
 * que un pedido con efecto externo irreversible lleve su `X-Idempotency-Key` hasta el backend
 * (ADR-0013); el BFF reenvía el encabezado entrante y nunca inventa uno.
 */
export async function reenviarAlBackend(
  ruta: string,
  metodo: Metodo,
  cuerpo?: unknown,
  cabeceras?: Readonly<Record<string, string>>,
): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  try {
    const datos = await comoRutaDelBff(() =>
      llamarApi<unknown>(ruta, {
        method: metodo,
        ...(cuerpo !== undefined ? { body: cuerpo } : {}),
        ...(cabeceras !== undefined ? { headers: cabeceras } : {}),
      }),
    );
    return NextResponse.json(datos ?? {});
  } catch (error) {
    if (!(error instanceof ErrorDeApi)) {
      return respuestaDeError(null);
    }
    // **Un 409 de una operación de negocio sí lleva su mensaje al navegador**, y por eso
    // no se delega en `respuestaDeError`, que sólo reenvía el detalle de un 422.
    //
    // Esa regla es correcta para las rutas de `auth`, que la usan directo: el detalle de
    // un 409 de registro nombra el email, y reenviarlo convierte la pantalla de alta en un
    // oráculo que dice qué cuentas existen. Acá no hay nada que enumerar — la sesión ya
    // está verificada, y los 409 que llegan son estados del negocio escritos para quien
    // los va a leer: «Este mapeo ya fue confirmado: para cambiarlo hay que revisarlo de
    // nuevo», «Ese procesamiento todavia esta en curso».
    //
    // Sin esto la pantalla imprime el nombre de la clase de la excepción, que es la única
    // audiencia para la que ese texto seguro no fue escrito. Cierra `TODO.md` §10 para las
    // rutas de negocio; `ClienteDuplicado` recupera su mensaje sin dejar de ser un 409.
    if (error.status === 409) {
      return NextResponse.json({ error: error.codigo, detalle: error.detalle }, { status: 409 });
    }
    return respuestaDeError(error);
  }
}

/** The body of a request that may legitimately have none. */
export async function cuerpoDe(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return {};
  }
}
