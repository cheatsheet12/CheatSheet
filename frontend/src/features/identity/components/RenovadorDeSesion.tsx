/**
 * Keeps the session alive while the panel is open (D-06 of the Etapa 6 test script).
 *
 * The access cookie lasts fifteen minutes and every screen calls the BFF with it. Without
 * this, somebody working on a form for twenty minutes pressed "Guardar" into a 401. The
 * refresh token was there all along, lasting thirty days; nothing ever spent it.
 *
 * It renews every ten minutes, and again when the tab comes back after a pause longer than
 * that: timers in a background tab are throttled, so the interval alone is not enough.
 * A renewal the API refuses (expired, revoked, reused) ends the session and sends the
 * person to the login, which is the only honest thing left to do.
 *
 * The access token stays short on purpose: a role change or a deactivation still takes
 * effect within fifteen minutes.
 */

"use client";

import { useEffect } from "react";

export const INTERVALO_DE_RENOVACION_MS = 10 * 60 * 1000;

export function RenovadorDeSesion(): null {
  useEffect(() => {
    let ultima = Date.now();

    const renovar = async (): Promise<void> => {
      ultima = Date.now();
      try {
        const respuesta = await fetch("/api/auth/refresh", { method: "POST" });
        if (respuesta.status === 401) {
          window.location.assign("/");
        }
      } catch {
        // A network blip is not a dead session: the next tick tries again.
      }
    };

    const alVolver = (): void => {
      if (
        document.visibilityState === "visible" &&
        Date.now() - ultima >= INTERVALO_DE_RENOVACION_MS
      ) {
        void renovar();
      }
    };

    const intervalo = window.setInterval(() => void renovar(), INTERVALO_DE_RENOVACION_MS);
    document.addEventListener("visibilitychange", alVolver);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, []);

  return null;
}
