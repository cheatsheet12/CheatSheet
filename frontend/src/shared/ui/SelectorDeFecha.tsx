/**
 * Selector de fecha del panel: un calendario propio en lugar del `<input type="date">`.
 *
 * **Por qué no el nativo.** El calendario que abre Chrome es del navegador: no toma la
 * tipografía, los colores ni el radio del panel, y no se puede estilizar desde CSS. Cada
 * navegador dibuja el suyo, así que la misma pantalla se ve distinta según quién la mira. Esto
 * es lo único que lo resuelve: una pieza propia.
 *
 * **El contrato es el de un campo de fecha**: el valor es `YYYY-MM-DD` o `""`, y `alCambiar`
 * recibe lo mismo. Las fechas se manejan por componentes (año, mes, día) y nunca por
 * `toISOString`, que corre un día cuando el huso no es UTC.
 *
 * **Teclado completo**, porque un calendario que sólo se opera con el mouse no es un campo:
 * flechas mueven de a un día o una semana, Inicio y Fin van a los extremos de la semana,
 * RePág y AvPág cambian de mes (con Mayús, de año), Esc cierra y devuelve el foco al botón.
 */

"use client";

import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import "./selector-de-fecha.css";

export interface PropsDeSelectorDeFecha {
  readonly id: string;
  readonly etiqueta: string;
  /** `YYYY-MM-DD`, o `""` si no hay fecha. */
  readonly value: string;
  readonly alCambiar: (valor: string) => void;
  /** Primer y último día elegibles, `YYYY-MM-DD`. */
  readonly min?: string | undefined;
  readonly max?: string | undefined;
  readonly error?: string | undefined;
}

const PATRON = /^(\d{4})-(\d{2})-(\d{2})$/;
const DIAS_DE_LA_SEMANA = ["LU", "MA", "MI", "JU", "VI", "SA", "DO"] as const;
/** Seis semanas: el mes más desparejo ocupa seis filas, y una grilla fija no salta de alto. */
const CELDAS = 42;
const ANCHO_DEL_PANEL = 304;

const TITULO_DEL_MES = new Intl.DateTimeFormat("es-AR", { month: "long", year: "numeric" });
const NOMBRE_DEL_DIA = new Intl.DateTimeFormat("es-AR", { dateStyle: "long" });

function leer(iso: string): Date | null {
  const partes = PATRON.exec(iso);
  if (partes === null) return null;
  const [, anio, mes, dia] = partes;
  const fecha = new Date(Number(anio), Number(mes) - 1, Number(dia));
  // `new Date(2026, 1, 31)` no falla: se corre a marzo. Se descarta lo que no round-tripea.
  return aIso(fecha) === iso ? fecha : null;
}

function aIso(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const dia = String(fecha.getDate()).padStart(2, "0");
  return `${fecha.getFullYear()}-${mes}-${dia}`;
}

function enFormatoLocal(iso: string): string {
  const fecha = leer(iso);
  if (fecha === null) return "";
  const dia = String(fecha.getDate()).padStart(2, "0");
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  return `${dia}/${mes}/${fecha.getFullYear()}`;
}

function sumarDias(fecha: Date, dias: number): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate() + dias);
}

/** Corre `meses` conservando el día, o el último del mes si ese mes no lo tiene. */
function sumarMeses(fecha: Date, meses: number): Date {
  const destino = new Date(fecha.getFullYear(), fecha.getMonth() + meses, 1);
  const ultimo = new Date(destino.getFullYear(), destino.getMonth() + 1, 0).getDate();
  return new Date(destino.getFullYear(), destino.getMonth(), Math.min(fecha.getDate(), ultimo));
}

/** Las 42 fechas de la grilla del mes de `base`, empezando por el lunes. */
function grillaDelMes(base: Date): readonly Date[] {
  const primero = new Date(base.getFullYear(), base.getMonth(), 1);
  const desfase = (primero.getDay() + 6) % 7;
  return Array.from({ length: CELDAS }, (_, indice) => sumarDias(primero, indice - desfase));
}

function conMayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function SelectorDeFecha({
  id,
  etiqueta,
  value,
  alCambiar,
  min,
  max,
  error,
}: PropsDeSelectorDeFecha): JSX.Element {
  const [abierto, setAbierto] = useState(false);
  const [foco, setFoco] = useState<Date>(() => leer(value) ?? new Date());
  const [alinearALaDerecha, setAlinearALaDerecha] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  // El foco se mueve al día elegido sólo cuando la persona navegó con el teclado o acaba de
  // abrir: mover el foco en cada render le robaría el clic a quien usa el mouse.
  const moverFoco = useRef(false);

  const elegida = leer(value);
  // De la fecha ya validada, no de `value`: un texto que no es una fecha real no se muestra.
  const textoDelValor = enFormatoLocal(value);
  const hoy = new Date();
  const idDelPanel = `${id}-calendario`;
  const idDelError = `${id}-error`;

  function abrir(): void {
    setFoco(elegida ?? new Date());
    moverFoco.current = true;
    setAbierto(true);
  }

  function cerrar(devolverFoco: boolean): void {
    setAbierto(false);
    if (devolverFoco) boton.current?.focus();
  }

  function habilitado(fecha: Date): boolean {
    const iso = aIso(fecha);
    return (min === undefined || iso >= min) && (max === undefined || iso <= max);
  }

  function elegir(fecha: Date): void {
    if (!habilitado(fecha)) return;
    alCambiar(aIso(fecha));
    cerrar(true);
  }

  function moverA(fecha: Date): void {
    moverFoco.current = true;
    setFoco(fecha);
  }

  // Si el panel no entra a la derecha del botón, se abre hacia el otro lado.
  useLayoutEffect(() => {
    if (!abierto || boton.current === null) return;
    const caja = boton.current.getBoundingClientRect();
    setAlinearALaDerecha(caja.left + ANCHO_DEL_PANEL > window.innerWidth - 12);
  }, [abierto]);

  useEffect(() => {
    if (!abierto || !moverFoco.current) return;
    moverFoco.current = false;
    panel.current?.querySelector<HTMLElement>(`[data-iso="${aIso(foco)}"]`)?.focus();
  }, [abierto, foco]);

  // Un clic afuera cierra. `mousedown` y no `click`: así el panel ya está cerrado cuando el
  // clic llega al botón de otro campo, y no queda un calendario abierto detrás del nuevo.
  useEffect(() => {
    if (!abierto) return undefined;
    function alPresionar(evento: MouseEvent): void {
      if (raiz.current !== null && !raiz.current.contains(evento.target as Node)) {
        setAbierto(false);
      }
    }
    document.addEventListener("mousedown", alPresionar);
    return () => document.removeEventListener("mousedown", alPresionar);
  }, [abierto]);

  function alTeclear(evento: KeyboardEvent<HTMLDivElement>): void {
    const desvio = evento.shiftKey ? 12 : 1;
    const destinos: Readonly<Record<string, Date>> = {
      ArrowLeft: sumarDias(foco, -1),
      ArrowRight: sumarDias(foco, 1),
      ArrowUp: sumarDias(foco, -7),
      ArrowDown: sumarDias(foco, 7),
      Home: sumarDias(foco, -((foco.getDay() + 6) % 7)),
      End: sumarDias(foco, 6 - ((foco.getDay() + 6) % 7)),
      PageUp: sumarMeses(foco, -desvio),
      PageDown: sumarMeses(foco, desvio),
    };
    if (evento.key === "Escape") {
      evento.preventDefault();
      evento.stopPropagation();
      cerrar(true);
      return;
    }
    const destino = destinos[evento.key];
    if (destino !== undefined) {
      evento.preventDefault();
      moverA(destino);
    }
  }

  const celdas = grillaDelMes(foco);
  const mostrado = foco.getMonth();
  const hoyIso = aIso(hoy);

  return (
    <div className={`campo${error !== undefined ? " campo--con-error" : ""}`}>
      <label className="campo__etiqueta" htmlFor={id}>
        {etiqueta}
      </label>
      <div className="selector-fecha" ref={raiz}>
        <button
          ref={boton}
          id={id}
          type="button"
          className="campo__control selector-fecha__boton"
          aria-haspopup="dialog"
          aria-expanded={abierto}
          aria-controls={abierto ? idDelPanel : undefined}
          aria-describedby={error !== undefined ? idDelError : undefined}
          data-abierto={abierto}
          onClick={() => (abierto ? cerrar(false) : abrir())}
        >
          <span className={textoDelValor === "" ? "selector-fecha__vacio" : undefined}>
            {textoDelValor === "" ? "dd/mm/aaaa" : textoDelValor}
          </span>
          <CalendarDays size={16} strokeWidth={1.9} aria-hidden="true" />
        </button>

        {abierto ? (
          <div
            ref={panel}
            id={idDelPanel}
            className="selector-fecha__panel"
            data-alinear={alinearALaDerecha ? "derecha" : "izquierda"}
            role="dialog"
            aria-label={`Elegir ${etiqueta.toLowerCase()}`}
            onKeyDown={alTeclear}
          >
            <div className="selector-fecha__cabecera">
              <p className="selector-fecha__titulo" aria-live="polite">
                {conMayuscula(TITULO_DEL_MES.format(foco))}
              </p>
              <button
                type="button"
                className="selector-fecha__nav"
                aria-label="Mes anterior"
                onClick={() => setFoco(sumarMeses(foco, -1))}
              >
                <ChevronLeft size={16} strokeWidth={2} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="selector-fecha__nav"
                aria-label="Mes siguiente"
                onClick={() => setFoco(sumarMeses(foco, 1))}
              >
                <ChevronRight size={16} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>

            <div className="selector-fecha__semana" aria-hidden="true">
              {DIAS_DE_LA_SEMANA.map((dia) => (
                <span key={dia}>{dia}</span>
              ))}
            </div>

            {/* La `key` es el mes: al cambiarlo la grilla se vuelve a montar y entra con su
                fundido, en lugar de cambiar de golpe. */}
            <div
              key={`${foco.getFullYear()}-${mostrado}`}
              className="selector-fecha__grilla"
              role="group"
              aria-label={conMayuscula(TITULO_DEL_MES.format(foco))}
            >
              {celdas.map((fecha) => {
                const iso = aIso(fecha);
                const esElegida = elegida !== null && iso === aIso(elegida);
                const esDelFoco = iso === aIso(foco);
                return (
                  <button
                    key={iso}
                    type="button"
                    className="selector-fecha__dia"
                    data-iso={iso}
                    data-afuera={fecha.getMonth() !== mostrado}
                    data-hoy={iso === hoyIso}
                    data-elegida={esElegida}
                    tabIndex={esDelFoco ? 0 : -1}
                    disabled={!habilitado(fecha)}
                    aria-label={NOMBRE_DEL_DIA.format(fecha)}
                    aria-pressed={esElegida}
                    aria-current={iso === hoyIso ? "date" : undefined}
                    onClick={() => elegir(fecha)}
                  >
                    {fecha.getDate()}
                  </button>
                );
              })}
            </div>

            <div className="selector-fecha__pie">
              <button
                type="button"
                className="selector-fecha__accion"
                onClick={() => {
                  alCambiar("");
                  cerrar(true);
                }}
              >
                Borrar
              </button>
              <button
                type="button"
                className="selector-fecha__accion selector-fecha__accion--principal"
                disabled={!habilitado(hoy)}
                onClick={() => elegir(hoy)}
              >
                Hoy
              </button>
            </div>
          </div>
        ) : null}
      </div>
      {error !== undefined && (
        <span className="campo__error" id={idDelError} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
