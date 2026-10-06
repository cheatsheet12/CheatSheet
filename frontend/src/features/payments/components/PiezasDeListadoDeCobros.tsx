/**
 * Las piezas de cada fila del listado de cobros: el link de pago con su «Copiar», el menú ⋯ y
 * el vacío.
 *
 * **Presentacionales.** Ninguna llama a la red ni al portapapeles: reciben qué mostrar y avisan
 * qué se pidió. Quien copia es `ListadoDeCobros`, para que el botón de la fila y el ítem del menú
 * compartan el mismo «✓ Copiado» en lugar de decir cada uno lo suyo.
 *
 * **El menú se pinta en un portal con `position: fixed`.** La tabla compartida tiene su propio
 * contenedor con desbordamiento y recortaría el menú de las últimas filas. Se cierra al
 * desplazar o redimensionar: un menú flotando donde ya no está su fila confunde más de lo que
 * ayuda.
 */

"use client";

import {
  Check,
  ClipboardCopy,
  ExternalLink,
  Ellipsis,
  Eye,
  Link2Off,
  Wallet,
  X,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import type { Cobro } from "../api/cobro";

/** Lo que se le dice a una fila sobre su último intento de copiar: nada, bien o mal. */
export type ResultadoDeCopia = "copiado" | "fallo" | null;

/** El link sólo se ofrece si el cobro lo tiene activo y es una dirección web. */
export function linkDe(cobro: Cobro): string | null {
  const url = cobro.url_de_pago;
  if (!cobro.tiene_link_activo || url === null || !/^https?:\/\//i.test(url)) {
    return null;
  }
  return url;
}

export function LinkDePago({
  cobro,
  resultado,
  onCopiar,
}: {
  readonly cobro: Cobro;
  readonly resultado: ResultadoDeCopia;
  readonly onCopiar: () => void;
}): JSX.Element {
  const url = linkDe(cobro);
  if (url === null) {
    return <span className="cob-lst-sin-link">Sin link</span>;
  }
  const clase =
    resultado === "copiado"
      ? " cob-lst-copiar--listo"
      : resultado === "fallo"
        ? " cob-lst-copiar--fallo"
        : "";
  return (
    <span className="cob-lst-link">
      <button
        type="button"
        className={`cob-lst-copiar${clase}`}
        aria-label={`Copiar link de ${cobro.descripcion}`}
        onClick={onCopiar}
      >
        {resultado === "copiado" ? (
          <Check size={14} strokeWidth={2.4} aria-hidden="true" />
        ) : resultado === "fallo" ? (
          <X size={14} strokeWidth={2.4} aria-hidden="true" />
        ) : (
          <ClipboardCopy size={14} strokeWidth={2} aria-hidden="true" />
        )}
        <span>
          {resultado === "copiado"
            ? "Copiado"
            : resultado === "fallo"
              ? "No se pudo"
              : "Copiar link"}
        </span>
      </button>
      <a
        className="cob-lst-abrir"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Abrir el link de ${cobro.descripcion}`}
        title="Abrir el link de pago"
      >
        <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
        <span>Abrir</span>
      </a>
    </span>
  );
}

interface ItemDeMenu {
  readonly clave: string;
  readonly etiqueta: string;
  readonly icono: ReactNode;
  readonly alElegir: () => void;
}

interface Posicion {
  readonly derecha: number;
  readonly arriba: number | null;
  readonly abajo: number | null;
}

const ALTO_POR_ITEM = 40;

export function MenuDeCobro({
  cobro,
  onVer,
  onCopiar,
}: {
  readonly cobro: Cobro;
  readonly onVer: () => void;
  readonly onCopiar: () => void;
}): JSX.Element {
  const [posicion, setPosicion] = useState<Posicion | null>(null);
  const disparador = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const idDelMenu = useId();
  const abierto = posicion !== null;
  const url = linkDe(cobro);
  const etiqueta = `Más acciones para ${cobro.descripcion}`;

  const items: readonly ItemDeMenu[] = [
    {
      clave: "ver",
      etiqueta: "Ver detalle",
      icono: <Eye size={16} aria-hidden="true" />,
      alElegir: onVer,
    },
    ...(url === null
      ? []
      : [
          {
            clave: "copiar",
            etiqueta: "Copiar link",
            icono: <ClipboardCopy size={16} aria-hidden="true" />,
            alElegir: onCopiar,
          },
          {
            clave: "abrir",
            etiqueta: "Abrir link de pago",
            icono: <ExternalLink size={16} aria-hidden="true" />,
            alElegir: () => {
              window.open(url, "_blank", "noopener,noreferrer");
            },
          },
        ]),
  ];

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
    } else if (evento.key === "Tab") {
      cerrar(false);
    }
  }

  return (
    <>
      <button
        ref={disparador}
        type="button"
        className="cob-lst-mas"
        aria-label={etiqueta}
        title="Más acciones"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idDelMenu : undefined}
        onClick={() => (abierto ? cerrar(false) : abrir())}
      >
        <Ellipsis size={16} strokeWidth={2} aria-hidden="true" />
      </button>
      {posicion !== null &&
        createPortal(
          <div
            ref={menu}
            id={idDelMenu}
            role="menu"
            aria-label={etiqueta}
            className={`cob-lst-menu${posicion.arriba === null ? " cob-lst-menu--arriba" : ""}`}
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
                className="cob-lst-menu__item"
                onClick={() => {
                  cerrar(false);
                  item.alElegir();
                }}
              >
                {item.icono}
                {item.etiqueta}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

/**
 * El listado sin filas. Hay dos vacíos y se dicen distinto: todavía no hay cobros —y lo útil es
 * crear el primero— o un filtro no encontró ninguno —y lo útil es quitarlo—. Ofrecer «Nuevo
 * cobro» en el segundo diría que no hay nada cuando lo que no hay es eso que se filtró.
 */
export function VacioDeCobros({
  hayFiltros,
  puedeGestionar,
  mensajeDeFiltro,
  onLimpiar,
  alNuevo,
}: {
  readonly hayFiltros: boolean;
  readonly puedeGestionar: boolean;
  readonly mensajeDeFiltro: string;
  readonly onLimpiar: () => void;
  readonly alNuevo: ReactNode;
}): JSX.Element {
  return (
    <div className="cob-lst-vacio">
      <span className="cob-lst-vacio__icono" aria-hidden="true">
        {hayFiltros ? (
          <Link2Off size={26} strokeWidth={1.8} />
        ) : (
          <Wallet size={26} strokeWidth={1.8} />
        )}
      </span>
      <p className="cob-lst-vacio__titulo">
        {hayFiltros ? mensajeDeFiltro : "Todavía no hay cobros."}
      </p>
      {hayFiltros ? (
        <>
          <p className="cob-lst-vacio__texto">
            Probá con otro rango de fechas o quitá algún filtro.
          </p>
          <button type="button" className="cob-lst-vacio__accion" onClick={onLimpiar}>
            Limpiar filtros
          </button>
        </>
      ) : (
        <>
          <p className="cob-lst-vacio__texto">
            Generá el primero y vas a poder seguirlo, con sus recordatorios, desde acá.
          </p>
          {puedeGestionar && alNuevo}
        </>
      )}
    </div>
  );
}
