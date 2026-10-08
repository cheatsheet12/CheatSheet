/**
 * Run a mutation and then navigate, keeping the button busy until the destination shows.
 *
 * **The defect this exists for (H-P1).** A form that did `await mutate(); router.push(x);`
 * and then cleared its own `enviando` flag released the button the instant the mutation
 * answered. `router.push` returns `void` and the navigation takes as long as the server
 * needs to produce the next page — seconds, on a cold API — so the screen sat unchanged
 * with an active button, and a second click repeated the mutation: a second login, and on
 * the billing screens a second document with a CAE.
 *
 * Next 14's `push`, `replace` and `refresh` dispatch inside `startTransition`, and the
 * router tree suspends until the response arrives. A transition started by the component
 * that wraps the call is therefore pending for exactly that long, and `useTransition`
 * reports it. `pendiente` joins the two phases: the mutation (`enCurso`) and the
 * navigation (`isPending`). `enCurso` is released inside the transition, so there is no
 * committed render in between where the button is enabled.
 *
 * Depends on no feature (rule R5).
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

export type RouterDeNavegacion = ReturnType<typeof useRouter>;

export interface OpcionesDeEjecucion {
  /**
   * `navegar` leaves the page (`window.location`) instead of using the router. That has
   * no transition to wait on, so the pending state is kept until the page is gone and is
   * released only if the action fails.
   */
  readonly saleDeLaPagina?: boolean;
}

export interface AccionConNavegacion {
  /** `true` from the call until the destination is displayed (or the action fails). */
  readonly pendiente: boolean;
  /**
   * Runs `accion`; if it succeeds, calls `navegar` inside a transition. If `accion`
   * rejects, the error is rethrown — the caller keeps its own `catch` and its messages —
   * and nothing navigates. A call made while another is pending does nothing.
   */
  readonly ejecutar: <T>(
    accion: () => Promise<T>,
    navegar: (resultado: T, router: RouterDeNavegacion) => void,
    opciones?: OpcionesDeEjecucion,
  ) => Promise<void>;
}

export function useAccionConNavegacion(): AccionConNavegacion {
  const router = useRouter();
  const [enCurso, setEnCurso] = useState(false);
  const [navegando, iniciarTransicion] = useTransition();
  // Set synchronously, so a second call in the same tick (before any render shows the
  // disabled button) is turned away too. State alone would not be read yet.
  const ocupado = useRef(false);
  const montado = useRef(true);

  const pendiente = enCurso || navegando;

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  useEffect(() => {
    if (!pendiente) {
      ocupado.current = false;
    }
  }, [pendiente]);

  // A page left through `window.location` (`saleDeLaPagina`) never releases its pending
  // state. If the browser restores it from the back/forward cache, the person is back on
  // this screen with the same React state: without this the button would stay busy.
  useEffect(() => {
    const alVolver = (evento: PageTransitionEvent): void => {
      if (evento.persisted) {
        ocupado.current = false;
        setEnCurso(false);
      }
    };
    window.addEventListener("pageshow", alVolver);
    return () => {
      window.removeEventListener("pageshow", alVolver);
    };
  }, []);

  const ejecutar: AccionConNavegacion["ejecutar"] = async (accion, navegar, opciones) => {
    if (ocupado.current) {
      return;
    }
    ocupado.current = true;
    setEnCurso(true);

    let resultado: Awaited<ReturnType<typeof accion>>;
    try {
      resultado = await accion();
    } catch (error) {
      // Released here as well as in the effect: when the action fails in the same tick
      // there may be no render in which `pendiente` changed.
      ocupado.current = false;
      setEnCurso(false);
      throw error;
    }

    // The person left while the request was in flight: do not drag them to a destination
    // they no longer asked for.
    if (!montado.current) {
      return;
    }

    if (opciones?.saleDeLaPagina === true) {
      navegar(resultado, router);
      return;
    }
    iniciarTransicion(() => {
      try {
        navegar(resultado, router);
      } finally {
        // Released inside the transition, not next to it. `isPending` turns on at a higher
        // priority than a plain state update, so releasing `enCurso` outside could commit
        // a render where both are false before the transition's own pending render.
        // Inside, it commits together with the destination, which is when we are done.
        setEnCurso(false);
      }
    });
  };

  return { pendiente, ejecutar };
}
