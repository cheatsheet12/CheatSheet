/**
 * El menú «más acciones» (⋯) de una fila.
 *
 * Guarda lo que no se hace todos los días —editar, dar de baja— para que la fila muestre sólo
 * lo principal. Es un menú de verdad y no un `<details>`: `aria-haspopup`/`aria-expanded` en el
 * disparador, `role="menu"` con `menuitem`, flechas para moverse, `Esc` para cerrar devolviendo
 * el foco, y clic afuera.
 *
 * **Se pinta en un portal y con `position: fixed`.** La tabla compartida tiene su propio
 * contenedor con desbordamiento y recortaría el menú de las últimas filas. Si no hay lugar
 * abajo, se abre hacia arriba. Se cierra al desplazar o redimensionar: un menú flotando donde
 * ya no está su fila confunde más de lo que ayuda.
 */

"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconoDeMasAcciones } from "./iconos";

export interface ItemDeMenu {
  readonly clave: string;
  readonly etiqueta: string;
  readonly icono: ReactNode;
  /** Una acción que quita algo del catálogo: el rojo va en el texto, no en una caja. */
  readonly peligrosa?: boolean;
  readonly alElegir: () => void;
}

export interface PropsDeMenuDeAcciones {
  /** Nombre accesible del disparador, p. ej. «Más acciones para Panadería Doña Rosa». */
  readonly etiqueta: string;
  readonly items: readonly ItemDeMenu[];
}

interface Posicion {
  readonly derecha: number;
  readonly arriba: number | null;
  readonly abajo: number | null;
}

/** Alto aproximado del menú, para decidir si cabe debajo del disparador. */
const ALTO_ESTIMADO = 56;

export function MenuDeAcciones({ etiqueta, items }: PropsDeMenuDeAcciones): JSX.Element {
  const [posicion, setPosicion] = useState<Posicion | null>(null);
  const disparador = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const idDelMenu = useId();
  const abierto = posicion !== null;

  const cerrar = useCallback((devolverFoco: boolean): void => {
    setPosicion(null);
    if (devolverFoco) {
      disparador.current?.focus();
    }
  }, []);

  function abrir(): void {
    const caja = disparador.current?.getBoundingClientRect();
    if (caja === undefined) {
      return;
    }
    const cabeAbajo = caja.bottom + ALTO_ESTIMADO * items.length < window.innerHeight - 8;
    setPosicion({
      derecha: Math.max(8, window.innerWidth - caja.right),
      arriba: cabeAbajo ? caja.bottom + 6 : null,
      abajo: cabeAbajo ? null : window.innerHeight - caja.top + 6,
    });
  }

  useEffect(() => {
    if (!abierto) {
      return undefined;
    }
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();

    const alPulsar = (evento: MouseEvent): void => {
      const objetivo = evento.target as Node;
      if (menu.current?.contains(objetivo) !== true && !disparador.current?.contains(objetivo)) {
        cerrar(false);
      }
    };
    const alTeclear = (evento: globalThis.KeyboardEvent): void => {
      if (evento.key === "Escape") {
        // El Escape no tiene que llegar al diálogo que pueda haber detrás.
        evento.stopPropagation();
        cerrar(true);
      }
    };
    const alMoverse = (): void => cerrar(false);

    document.addEventListener("mousedown", alPulsar);
    document.addEventListener("keydown", alTeclear, true);
    window.addEventListener("resize", alMoverse);
    window.addEventListener("scroll", alMoverse, true);
    return () => {
      document.removeEventListener("mousedown", alPulsar);
      document.removeEventListener("keydown", alTeclear, true);
      window.removeEventListener("resize", alMoverse);
      window.removeEventListener("scroll", alMoverse, true);
    };
  }, [abierto, cerrar]);

  function moverFoco(evento: KeyboardEvent<HTMLDivElement>): void {
    const opciones = Array.from(
      menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    );
    const actual = opciones.indexOf(document.activeElement as HTMLElement);
    const pasos: Record<string, number> = { ArrowDown: 1, ArrowUp: -1 };
    const paso = pasos[evento.key];
    if (paso !== undefined) {
      evento.preventDefault();
      opciones[(actual + paso + opciones.length) % opciones.length]?.focus();
    } else if (evento.key === "Home" || evento.key === "End") {
      evento.preventDefault();
      opciones[evento.key === "Home" ? 0 : opciones.length - 1]?.focus();
    } else if (evento.key === "Tab") {
      cerrar(false);
    }
  }

  return (
    <>
      <button
        ref={disparador}
        type="button"
        className="mae-icono-accion mae-icono-accion--mas"
        aria-label={etiqueta}
        title="Más acciones"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idDelMenu : undefined}
        onClick={() => (abierto ? cerrar(false) : abrir())}
      >
        <IconoDeMasAcciones />
      </button>
      {posicion !== null &&
        createPortal(
          <div
            ref={menu}
            id={idDelMenu}
            role="menu"
            aria-label={etiqueta}
            className={`mae-menu${posicion.arriba === null ? " mae-menu--arriba" : ""}`}
            style={{
              right: posicion.derecha,
              ...(posicion.arriba !== null ? { top: posicion.arriba } : {}),
              ...(posicion.abajo !== null ? { bottom: posicion.abajo } : {}),
            }}
            onKeyDown={moverFoco}
          >
            {items.map((item) => (
              <button
                key={item.clave}
                type="button"
                role="menuitem"
                className={`mae-menu__item${item.peligrosa === true ? " mae-menu__item--baja" : ""}`}
                onClick={() => {
                  cerrar(false);
                  item.alElegir();
                }}
              >
                <span className="mae-menu__icono" aria-hidden="true">
                  {item.icono}
                </span>
                {item.etiqueta}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
