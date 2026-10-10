/**
 * The cookies of the Google round trip (`state` and the consent) share one scope, and a
 * cookie is only removed by an expiry that names the *same* path.
 *
 * `cookies().delete(name)` in Next 14 emits `Path=/`, while these are set with
 * `path=/api/auth`: the browser treats them as two different cookies and keeps the real
 * one for the rest of its ten minutes. For `state` that means a used value stays replayable.
 * So both the set and the removal take their attributes from here.
 */

import { cookies } from "next/headers";

export const VIDA_DE_LAS_COOKIES_DE_OAUTH = 10 * 60;

function atributos(): {
  readonly httpOnly: true;
  readonly secure: boolean;
  readonly sameSite: "lax";
  readonly path: string;
} {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    // `lax`, not `strict`: the browser arrives back from Google's domain, and a strict
    // cookie would not be sent on that navigation.
    sameSite: "lax",
    path: "/api/auth",
  };
}

export function guardarCookieDeOAuth(nombre: string, valor: string): void {
  cookies().set({
    name: nombre,
    value: valor,
    ...atributos(),
    maxAge: VIDA_DE_LAS_COOKIES_DE_OAUTH,
  });
}

/** Remove one of them for real: same attributes it was set with, expired. */
export function borrarCookieDeOAuth(nombre: string): void {
  cookies().set({ name: nombre, value: "", ...atributos(), maxAge: 0 });
}
