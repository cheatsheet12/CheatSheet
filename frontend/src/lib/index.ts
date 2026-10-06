/**
 * Technical plumbing for the BFF: fetch wrapper, auth/session helpers, cookie
 * handling. The JWT lives in an HttpOnly cookie and is never read from client
 * JavaScript (design ADR-011).
 */

export { ErrorDeApi, llamarApi } from "@/lib/api";
export type { OpcionesDeLlamada } from "@/lib/api";
export {
  SESSION_COOKIE_NAME,
  cerrarSesion,
  guardarSesion,
  haySesion,
  leerToken,
} from "@/lib/session";
export type { OpcionesDeSesion } from "@/lib/session";
