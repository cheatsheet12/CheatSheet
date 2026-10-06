/**
 * Sign out (ADR-011).
 *
 * **This existed as a route handler and as nothing else.** `/api/auth/logout` was written
 * two units ago and no screen ever called it, so the only way out of the panel was to
 * clear the cookies by hand. A panel that issues tax documents and cannot be left is not
 * a panel anybody should be asked to use on a shared machine.
 *
 * `router.refresh()` throws away the cached server render: without it Next can serve the
 * panel shell it already had, and the person sees their own data for a moment after
 * signing out.
 *
 * **The order is `push` and then `refresh`, and it is not cosmetic.** Next's action queue
 * marks a navigation that arrives while another action is pending as discarded, and its
 * state is never applied. `refresh` first and `push` second therefore dropped the
 * refresh — and the cache clean-up it exists for. A `refresh` issued after the `push`
 * queues behind the navigation and is applied.
 */

"use client";

import { LogOut } from "lucide-react";

import { useAccionConNavegacion } from "@/shared";

export function BotonDeSalida(): JSX.Element {
  const { pendiente: saliendo, ejecutar } = useAccionConNavegacion();

  const cerrarSesion = async (): Promise<void> => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Swallowed deliberately: leaving is what the person asked for, and a failed
      // request is no reason to trap them in the panel.
      //
      // Letting it propagate was not an option. It would keep going into `void salir()`,
      // where nothing is left to catch it — an unhandled rejection in every browser
      // console, and a failed CI run, while both tests still reported green.
    }
  };

  const salir = async (): Promise<void> => {
    // Whatever happened above, this browser is done with the session.
    await ejecutar(cerrarSesion, (_resultado, router) => {
      router.push("/");
      router.refresh();
    });
  };

  return (
    <button type="button" className="panel__salir" disabled={saliendo} onClick={() => void salir()}>
      <LogOut className="panel__salir-icono" size={16} strokeWidth={2} aria-hidden="true" />
      {saliendo ? "Saliendo…" : "Cerrar sesión"}
    </button>
  );
}
