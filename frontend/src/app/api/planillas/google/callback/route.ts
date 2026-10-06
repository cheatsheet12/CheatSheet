/**
 * BFF — donde aterriza el usuario al volver de Google (HU-E2-04 RN-01).
 *
 * Es el otro extremo de `/planillas/google/autorizacion`: el proveedor manda el navegador
 * acá con `code` y `state`, y esta ruta los canjea contra el backend y devuelve a la
 * pantalla de ingesta. Faltaba, y sin ella «Vincular Google Sheets» terminaba en un 404 —
 * el adaptador simulado apunta a esta misma dirección justamente para que el recorrido
 * manual y el automático pasen por el mismo camino que tomará el callback real.
 *
 * **Es un `GET` que redirige, no una pantalla.** El usuario vuelve de un proveedor externo
 * y lo que corresponde es dejarlo donde estaba, con el vínculo hecho o con el motivo por el
 * que no se pudo. Una página intermedia acá sería una página que nadie eligió visitar.
 *
 * **El identificador del documento sale del `code`.** En el flujo real lo elige el usuario
 * en el selector de archivos de Google y viaja aparte; el simulado usa el código como
 * identificador, prefijado, y por eso alcanza con quitarle el prefijo. Cuando entre el
 * selector real, este es el único lugar que cambia.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { COOKIE_DOCUMENTO, COOKIE_ESTADO } from "@/app/api/planillas/google/autorizacion/route";

export const dynamic = "force-dynamic";

const PREFIJO_SIMULADO = "simulado:";

/** A dónde vuelve el usuario, con un motivo si algo salió mal. */
function aIngesta(origen: string, motivo?: string): NextResponse {
  const destino = new URL("/ingesta", origen);
  if (motivo !== undefined) {
    destino.searchParams.set("error", motivo);
  }
  return NextResponse.redirect(destino);
}

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  if (!haySesion()) {
    return NextResponse.redirect(new URL("/", url.origin));
  }

  const codigo = url.searchParams.get("code");
  const estado = url.searchParams.get("state");
  if (codigo === null || estado === null) {
    // Google manda `error=access_denied` cuando la persona rechaza el consentimiento, y
    // eso no es una falla: es una respuesta.
    return aIngesta(url.origin, "No se completó la vinculación con Google.");
  }

  // El guarda anti-CSRF: sin esto, cualquiera que logre que el navegador de la persona
  // llegue acá le engancha a su empresa la planilla que quiera. Se compara de este lado
  // porque es el único que ve la cookie, y se reenvía para que el backend compare la suya.
  const guardado = cookies().get(COOKIE_ESTADO)?.value;
  if (guardado === undefined || guardado !== estado) {
    return aIngesta(
      url.origin,
      "La autorización no coincide con la que iniciaste. Volvé a intentarlo.",
    );
  }

  try {
    await llamarApi("/planillas/google", {
      method: "POST",
      headers: { Cookie: `${COOKIE_ESTADO}=${guardado}` },
      body: {
        codigo,
        // La planilla que la persona eligió antes de irse. Si la cookie se perdió, el
        // código simulado trae uno usable; el real no, y el backend lo dirá.
        identificador_documento:
          cookies().get(COOKIE_DOCUMENTO)?.value ??
          (codigo.startsWith(PREFIJO_SIMULADO) ? codigo.slice(PREFIJO_SIMULADO.length) : codigo),
        estado,
      },
    });
    const hecho = aIngesta(url.origin);
    hecho.cookies.delete(COOKIE_ESTADO);
    hecho.cookies.delete(COOKIE_DOCUMENTO);
    return hecho;
  } catch (error) {
    return aIngesta(
      url.origin,
      error instanceof ErrorDeApi ? error.detalle : "No se pudo vincular la planilla.",
    );
  }
}
