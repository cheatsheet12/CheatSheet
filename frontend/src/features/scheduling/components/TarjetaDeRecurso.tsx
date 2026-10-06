/**
 * La tarjeta de un recurso reservable: quién es, qué atiende, cuándo y con qué excepciones.
 *
 * Cada recurso es una tarjeta y no una fila: lo que se compara entre recursos —¿qué días
 * atiende?, ¿qué servicios presta?— se lee mejor con la semana dibujada (`MiniSemana`) que con
 * una pastilla de texto. Todo sale de los datos que la pantalla ya recibe; no se pide nada más.
 *
 * «Configurar» está a la vista; dar de baja o reactivar vive en el menú ⋯. La acción es
 * desactivar, no eliminar (RN-03). El resto de la tarjeta también abre «Configurar» con el mouse,
 * como atajo: el botón sigue siendo el camino para el teclado.
 */

"use client";

import {
  CalendarX,
  Clock,
  DoorOpen,
  Power,
  RotateCcw,
  SlidersHorizontal,
  UserRound,
  Wrench,
} from "lucide-react";
import type { CSSProperties, MouseEvent, ReactNode } from "react";

import { Badge, formatearFecha } from "@/shared";

import { DIAS, ETIQUETAS_DE_EXCEPCION, ETIQUETAS_DE_TIPO } from "../api/recurso";
import type { Recurso, TipoRecurso } from "../api/recurso";
import { MenuDeRecurso } from "./MenuDeRecurso";
import {
  INICIALES_DE_DIA,
  diasConHorario,
  excepcionesProximas,
  hoyIso,
  tramosDeHorario,
} from "./recursosDatos";

/** Cuántos servicios y cuántas excepciones caben en la tarjeta antes de resumir con «+N». */
const SERVICIOS_VISIBLES = 3;
const EXCEPCIONES_VISIBLES = 2;

const ICONOS_DE_TIPO: Readonly<Record<TipoRecurso, ReactNode>> = {
  PERSONA: <UserRound aria-hidden="true" />,
  ESPACIO: <DoorOpen aria-hidden="true" />,
  EQUIPO: <Wrench aria-hidden="true" />,
};

/** La tira L M X J V S D con los días que el recurso atiende encendidos. */
export function MiniSemana({ recurso }: { readonly recurso: Recurso }): JSX.Element {
  const atiende = diasConHorario(recurso.patrones);
  return (
    <ul className="age-mini" aria-label="Días de atención">
      {INICIALES_DE_DIA.map((inicial, indice) => {
        const activo = atiende.has(indice);
        return (
          <li
            key={DIAS[indice] ?? inicial}
            className={`age-mini__dia${activo ? " age-mini__dia--atiende" : ""}`}
          >
            <span aria-hidden="true">{inicial}</span>
            <span className="solo-lectores">
              {`${DIAS[indice] ?? inicial}: ${activo ? "atiende" : "cerrado"}`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Servicios({
  recurso,
  nombres,
}: {
  readonly recurso: Recurso;
  readonly nombres: ReadonlyMap<string, string>;
}): JSX.Element {
  if (recurso.servicios.length === 0) {
    // Un recurso sin servicios no admite ninguno, y decirlo evita que alguien se pregunte por
    // qué no puede reservar en él.
    return <span className="age-nada">Sin servicios asociados</span>;
  }
  const visibles = recurso.servicios.slice(0, SERVICIOS_VISIBLES);
  const resto = recurso.servicios.length - visibles.length;
  return (
    <span className="age-chips">
      {visibles.map((uno) => (
        <span className="age-chip" key={uno}>
          {nombres.get(uno) ?? uno}
        </span>
      ))}
      {resto > 0 && (
        <span
          className="age-chip age-chip--mas"
          title={recurso.servicios
            .slice(SERVICIOS_VISIBLES)
            .map((uno) => nombres.get(uno) ?? uno)
            .join(", ")}
        >
          {`+${resto}`}
        </span>
      )}
    </span>
  );
}

function Horario({ recurso }: { readonly recurso: Recurso }): JSX.Element {
  if (recurso.patrones.length === 0) {
    return <span className="age-nada">Sin horario configurado</span>;
  }
  const tramos = tramosDeHorario(recurso.patrones);
  return (
    <>
      <MiniSemana recurso={recurso} />
      <ul className="age-rec__franjas">
        {tramos.map((tramo) => (
          <li key={`${tramo.dias}-${tramo.franja}`}>
            <Clock aria-hidden="true" />
            <span className="age-rec__franja">{tramo.franja}</span>
            {tramos.length > 1 && <span className="age-rec__dias">{tramo.dias}</span>}
          </li>
        ))}
      </ul>
    </>
  );
}

function Excepciones({ recurso }: { readonly recurso: Recurso }): JSX.Element {
  if (recurso.excepciones.length === 0) {
    return <span className="age-nada">Sin excepciones</span>;
  }
  const proximas = excepcionesProximas(recurso.excepciones, hoyIso());
  const visibles = proximas.slice(0, EXCEPCIONES_VISIBLES);
  const resto = proximas.length - visibles.length;
  return (
    <span className="age-chips">
      {visibles.map((una) => (
        <span className="age-chip age-chip--excepcion" key={una.fecha}>
          <CalendarX aria-hidden="true" />
          {formatearFecha(una.fecha)} · {ETIQUETAS_DE_EXCEPCION[una.tipo]}
        </span>
      ))}
      {resto > 0 && <span className="age-chip age-chip--mas">{`+${resto}`}</span>}
      {visibles.length === 0 && <span className="age-nada">Ninguna próxima</span>}
    </span>
  );
}

export interface PropsDeTarjetaDeRecurso {
  readonly recurso: Recurso;
  readonly nombresDeServicio: ReadonlyMap<string, string>;
  readonly puedeEditar: boolean;
  /** Posición en la grilla: escalona la entrada de las tarjetas. */
  readonly indice: number;
  readonly onConfigurar: (recurso: Recurso) => void;
  readonly onAlternarEstado: (recurso: Recurso) => void;
}

export function TarjetaDeRecurso({
  recurso,
  nombresDeServicio,
  puedeEditar,
  indice,
  onConfigurar,
  onAlternarEstado,
}: PropsDeTarjetaDeRecurso): JSX.Element {
  function alPulsar(evento: MouseEvent<HTMLElement>): void {
    // Los botones, el menú (que se pinta en un portal pero burbujea por el árbol de React) y
    // los textos que se están seleccionando no abren nada.
    const objetivo = evento.target as HTMLElement;
    if (objetivo.closest("button, a, [role='menu']") !== null) {
      return;
    }
    if ((window.getSelection()?.toString() ?? "") !== "") {
      return;
    }
    onConfigurar(recurso);
  }

  return (
    <article
      className={`age-rec${recurso.activo ? "" : " age-rec--inactivo"}${
        puedeEditar ? " age-rec--abre" : ""
      }`}
      data-tipo={recurso.tipo}
      style={{ "--age-i": Math.min(indice, 8) } as CSSProperties}
      onClick={puedeEditar ? alPulsar : undefined}
    >
      <header className="age-rec__cabeza">
        <span className="age-rec__azulejo" aria-hidden="true">
          {ICONOS_DE_TIPO[recurso.tipo]}
        </span>
        <div className="age-rec__quien">
          <h3 className="age-rec__nombre">{recurso.nombre}</h3>
          <span className="age-rec__tipo">{ETIQUETAS_DE_TIPO[recurso.tipo]}</span>
        </div>
        <Badge estado={recurso.activo ? "ok" : "pendiente"}>
          {recurso.activo ? "Activo" : "Inactivo"}
        </Badge>
      </header>

      <div className="age-rec__bloque">
        <p className="age-rec__rotulo">Atiende</p>
        <Servicios recurso={recurso} nombres={nombresDeServicio} />
      </div>

      <div className="age-rec__bloque">
        <p className="age-rec__rotulo">Horario semanal</p>
        <Horario recurso={recurso} />
      </div>

      <div className="age-rec__bloque">
        <p className="age-rec__rotulo">
          Excepciones
          {recurso.excepciones.length > 0 && (
            <span className="age-rec__cuenta">{recurso.excepciones.length}</span>
          )}
        </p>
        <Excepciones recurso={recurso} />
      </div>

      {puedeEditar && (
        <footer className="age-rec__pie">
          <button type="button" className="age-configurar" onClick={() => onConfigurar(recurso)}>
            <SlidersHorizontal aria-hidden="true" />
            Configurar
          </button>
          <MenuDeRecurso
            etiqueta={`Más acciones para ${recurso.nombre}`}
            items={[
              {
                clave: "estado",
                etiqueta: recurso.activo ? "Desactivar" : "Reactivar",
                icono: recurso.activo ? <Power /> : <RotateCcw />,
                peligrosa: recurso.activo,
                alElegir: () => onAlternarEstado(recurso),
              },
            ]}
          />
        </footer>
      )}
    </article>
  );
}
