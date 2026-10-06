"use client";

/**
 * El menú de la cuenta, en el encabezado: el avatar abre un panel con quién es la persona,
 * dos atajos y la salida.
 *
 * Es el patrón de «divulgación» y no un `role="menu"`: un botón con `aria-expanded` que
 * muestra enlaces y un botón normales, que se recorren con Tab como en cualquier página.
 * Se cierra con Escape (devolviendo el foco al botón), con un clic afuera y al navegar.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface PropiedadesDelMenu {
  readonly nombre: string;
  readonly rol: string;
  readonly iniciales: string;
  /** El botón de cerrar sesión, que vive en `features/identity` y llega ya armado. */
  readonly salida: ReactNode;
}

export function MenuDeUsuario({ nombre, rol, iniciales, salida }: PropiedadesDelMenu): JSX.Element {
  const [abierto, setAbierto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const disparador = useRef<HTMLButtonElement>(null);
  const ruta = usePathname();

  useEffect(() => {
    setAbierto(false);
  }, [ruta]);

  useEffect(() => {
    if (!abierto) return;
    const alPulsar = (evento: PointerEvent): void => {
      if (evento.target instanceof Node && !raiz.current?.contains(evento.target)) {
        setAbierto(false);
      }
    };
    const alTeclear = (evento: KeyboardEvent): void => {
      if (evento.key === "Escape") {
        setAbierto(false);
        disparador.current?.focus();
      }
    };
    document.addEventListener("pointerdown", alPulsar);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("pointerdown", alPulsar);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  return (
    <div ref={raiz} className="cuenta">
      <button
        ref={disparador}
        type="button"
        className="cuenta__disparador"
        aria-expanded={abierto}
        aria-controls="menu-de-cuenta"
        aria-label={`Cuenta de ${nombre}`}
        onClick={() => setAbierto((actual) => !actual)}
      >
        <span className="cuenta__avatar" aria-hidden="true">
          {iniciales}
        </span>
        <span className="cuenta__datos">
          <b>{nombre}</b>
          <small>{rol}</small>
        </span>
        <svg
          className="cuenta__chevron"
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <div id="menu-de-cuenta" className="cuenta__panel" data-abierto={abierto}>
        <div className="cuenta__cabecera">
          <b>{nombre}</b>
          <small>{rol === "" ? "Sesión iniciada" : rol}</small>
        </div>
        <Link className="cuenta__enlace" href="/configuracion/preferencias">
          Mis preferencias
        </Link>
        <Link className="cuenta__enlace" href="/soporte">
          Ayuda y soporte
        </Link>
        <div className="cuenta__salida">{salida}</div>
      </div>
    </div>
  );
}
