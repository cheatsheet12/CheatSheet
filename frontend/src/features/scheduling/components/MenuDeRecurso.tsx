/**
 * El menú «más acciones» (⋯) de la tarjeta de un recurso.
 *
 * Equivalente local del de Clientes y Servicios: `master_data` no lo exporta y una feature no
 * importa los internos de otra (R5). Guarda lo que no se hace todos los días —dar de baja o
 * reactivar— para que la tarjeta muestre sólo lo principal. Es un menú de verdad:
 * `aria-haspopup`/`aria-expanded` en el disparador, `role="menu"` con `menuitem`, flechas para
 * moverse, `Esc` para cerrar devolviendo el foco y clic afuera.
 *
 * Se pinta en un portal con `position: fixed`, así que ni el borde de la tarjeta ni el
 * desbordamiento de la grilla lo recortan; si abajo no hay lugar, se abre hacia arriba.
 */

"use client";

import { Ellipsis } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

export interface ItemDeMenuDeRecurso {
  readonly clave: string;
  readonly etiqueta: string;
  readonly icono: ReactNode;
  /** Una acción que saca al recurso de circulación: el rojo va en el texto. */
  readonly peligrosa?: boolean;
  readonly alElegir: () => void;
}

export interface PropsDeMenuDeRecurso {
  /** Nombre accesible del disparador, p. ej. «Más acciones para Sillón 1». */
  readonly etiqueta: string;
  readonly items: readonly ItemDeMenuDeRecurso[];
}

interface Posicion {
  readonly derecha: number;
  readonly arriba: number | null;
  readonly abajo: number | null;
}

/** Alto aproximado de cada opción, para decidir si el menú cabe debajo del disparador. */
const ALTO_POR_ITEM = 44;

export function MenuDeRecurso({ etiqueta, items }: PropsDeMenuDeRecurso): JSX.Element {
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
    const cabeAbajo = caja.bottom + ALTO_POR_ITEM * items.length + 16 < window.innerHeight;
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
        className="age-mas"
        aria-label={etiqueta}
        title="Más acciones"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idDelMenu : undefined}
        onClick={() => (abierto ? cerrar(false) : abrir())}
      >
        <Ellipsis aria-hidden="true" />
      </button>
      {posicion !== null &&
        createPortal(
          <div
            ref={menu}
            id={idDelMenu}
            role="menu"
            aria-label={etiqueta}
            className={`age-menu${posicion.arriba === null ? " age-menu--arriba" : ""}`}
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
                className={`age-menu__item${item.peligrosa === true ? " age-menu__item--baja" : ""}`}
                onClick={() => {
                  cerrar(false);
                  item.alElegir();
                }}
              >
                <span className="age-menu__icono" aria-hidden="true">
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
