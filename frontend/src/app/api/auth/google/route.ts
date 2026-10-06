/**
 * BFF — start the Google flow (HU-E1-01 RN-02).
 *
 * **The debt this pays.** PAN-ONB-01 has linked here since the previous unit and nothing
 * answered.
 *
 * `state` is minted here, stored in a short-lived HttpOnly cookie and checked on the way
 * back. It is the CSRF defence of the OAuth flow: without it, anybody can send a victim
 * a callback URL carrying *their* authorization code and quietly attach the victim's
 * browser to the attacker's account.
 */

import { randomUUID } from "node:crypto";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const COOKIE_STATE = "cheatsheet_oauth_state";
const VIDA_DEL_STATE = 10 * 60;

interface RespuestaDeUrl {
  readonly url: string;
}

export async function GET(): Promise<NextResponse> {
  const state = randomUUID();
  try {
    const { url } = await llamarApi<RespuestaDeUrl>(
      `/auth/google/url?state=${encodeURIComponent(state)}`,
    );
    cookies().set({
      name: COOKIE_STATE,
      value: state,
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      // `lax`, not `strict`: the browser arrives back here from Google's domain, and a
      // strict cookie would not be sent on that navigation.
      sameSite: "lax",
      path: "/api/auth",
      maxAge: VIDA_DEL_STATE,
    });
    return NextResponse.redirect(url);
  } catch (error) {
    const detalle = error instanceof ErrorDeApi ? error.codigo : "ErrorInterno";
    return NextResponse.redirect(new URL(`/?error=${detalle}`, urlDeLaApp()));
  }
}

export function urlDeLaApp(): string {
  return process.env.APP_BASE_URL ?? "http://localhost:3000";
}
