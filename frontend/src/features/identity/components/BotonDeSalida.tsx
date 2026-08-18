/**
 * Sign out (ADR-011).
 *
 * **This existed as a route handler and as nothing else.** `/api/auth/logout` was written
 * two units ago and no screen ever called it, so the only way out of the panel was to
 * clear the cookies by hand. A panel that issues tax documents and cannot be left is not
 * a panel anybody should be asked to use on a shared machine.
 *
 * `router.refresh()` before navigating throws away the cached server render: without it
 * Next can serve the panel shell it already had, and the person sees their own data for
 * a moment after signing out.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function BotonDeSalida(): JSX.Element {
  const router = useRouter();
  const [saliendo, setSaliendo] = useState(false);

  const salir = async (): Promise<void> => {
    setSaliendo(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Swallowed deliberately: leaving is what the person asked for, and a failed
      // request is no reason to trap them in the panel.
      //
      // `finally` on its own was not enough. It runs on the way out and then lets the
      // rejection keep going, straight into `void salir()`, where nothing is left to
      // catch it — an unhandled rejection in every browser console, and a failed CI
      // run, while both tests still reported green.
    } finally {
      // Whatever happened above, this browser is done with the session.
      router.refresh();
      router.push("/");
    }
  };

  return (
    <button type="button" className="panel__salir" disabled={saliendo} onClick={() => void salir()}>
      {saliendo ? "Saliendo…" : "Cerrar sesión"}
    </button>
  );
}
