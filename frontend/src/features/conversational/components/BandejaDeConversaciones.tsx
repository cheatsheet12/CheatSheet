/**
 * PAN-WA-01 — Agente WhatsApp · Conversaciones (HU-E9-01).
 *
 * La bandeja arranca **filtrada por escaladas**, que es lo que un operador viene a hacer: las
 * conversaciones que el agente resolvió solo no necesitan a nadie. El filtro se puede sacar
 * para ver todo el historial.
 *
 * **«Escalada» no es un estado del hilo** (RN-01): lo que se muestra es el estado del
 * escalamiento abierto, que el backend deriva. Acá no se calcula nada — derivarlo otra vez del
 * lado del cliente sería el mismo hecho en dos lugares.
 *
 * **Es una lista de mensajería y no una tabla**, como el prototipo. Un hilo no es una fila de
 * datos comparables columna contra columna: es un interlocutor, una última línea y un estado.
 * Y el renglón entero es el enlace, porque apuntar a 64 px de alto es más fácil que apuntar a
 * las tres palabras del título.
 *
 * **Un hilo escalado se ve antes de leerlo**: punto ámbar y pastilla. Es el único estado que
 * obliga a alguien a hacer algo, y encontrarlo renglón por renglón es tiempo con un cliente
 * esperando del otro lado.
 *
 * **Bandeja y hilo comparten pantalla.** Con un hilo abierto (`children`), el panel derecho
 * es el hilo y su renglón queda resaltado; en un celular se ve uno u otro, con un «Volver».
 */

"use client";

import { useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

import { Alert } from "@/shared";

import {
  ErrorDeConversacion,
  MENSAJE_SIN_CONVERSACIONES,
  MENSAJE_SIN_ESCALADAS,
  listarConversaciones,
} from "../api/conversacion";
import type { ListadoDeConversaciones } from "../api/conversacion";
import { ContextoDeAvisoDeBandeja } from "./AvisoDeBandeja";
import type { AvisoDeBandeja } from "./AvisoDeBandeja";
import { FilaDeConversacion, etiquetaDe, situacionDe, tituloDe } from "./FilaDeConversacion";
import { IconoDeBandeja, IconoDeLimpiar, IconoDeLupa } from "./iconos";
import { SinHiloElegido } from "./SinHiloElegido";

export interface PropsDeBandejaDeConversaciones {
  readonly inicial: ListadoDeConversaciones;
  /** Administrador y Operador atienden; Solo Lectura mira (HU-E9-01). */
  readonly puedeAtender: boolean;
  /** El hilo abierto, si lo hay: ocupa el panel derecho y resalta su renglón. */
  readonly seleccionadaId?: string;
  /** La bandeja arranca filtrada por escaladas, salvo que el listado ya venga completo. */
  readonly soloEscaladasInicial?: boolean;
  readonly children?: ReactNode;
}

/** «1 hilo» y no «1 hilos»: el contador se lee, y un plural mal puesto se nota. */
function contar(cantidad: number, singular: string, plural: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : plural}`;
}

/** Flechas arriba y abajo recorren los renglones sin salir de la lista. */
function moverConFlechas(evento: KeyboardEvent<HTMLUListElement>): void {
  if (evento.key !== "ArrowDown" && evento.key !== "ArrowUp") {
    return;
  }
  const enlaces = Array.from(evento.currentTarget.querySelectorAll<HTMLAnchorElement>("a"));
  const actual = enlaces.findIndex((enlace) => enlace === document.activeElement);
  const siguiente = evento.key === "ArrowDown" ? actual + 1 : actual - 1;
  const destino = enlaces[Math.max(0, Math.min(enlaces.length - 1, siguiente))];
  if (destino !== undefined) {
    evento.preventDefault();
    destino.focus();
  }
}

export function BandejaDeConversaciones({
  inicial,
  puedeAtender,
  seleccionadaId,
  soloEscaladasInicial = true,
  children,
}: PropsDeBandejaDeConversaciones): JSX.Element {
  const [listado, setListado] = useState<ListadoDeConversaciones>(inicial);
  const [soloEscaladas, setSoloEscaladas] = useState(soloEscaladasInicial);
  const [error, setError] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");

  async function recargar(filtro: boolean): Promise<void> {
    setError(null);
    try {
      setListado(await listarConversaciones(filtro));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeConversacion ? fallo.message : "No se pudo actualizar la bandeja.",
      );
    }
  }

  function cambiarFiltro(valor: boolean): Promise<void> {
    setSoloEscaladas(valor);
    return recargar(valor);
  }

  // El hilo abierto avisa cuando actúa: se vuelve a pedir el listado con el filtro vigente.
  const aviso: AvisoDeBandeja = { avisarCambio: () => void recargar(soloEscaladas) };

  const hilos = listado.conversaciones;
  const esperando = hilos.filter((uno) => uno.estado_escalamiento === "ABIERTO").length;
  const consulta = busqueda.trim().toLowerCase();
  const visibles =
    consulta === ""
      ? hilos
      : hilos.filter((uno) =>
          [tituloDe(uno), situacionDe(uno), etiquetaDe(uno)].some((texto) =>
            texto.toLowerCase().includes(consulta),
          ),
        );
  const conHilo = children !== undefined && children !== null;

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {!puedeAtender && (
        // No se esconde la bandeja: Solo Lectura puede necesitar ver qué está pasando. Lo
        // que no puede es tomar un escalamiento, y eso se dice acá en vez de que lo descubra
        // apretando un botón que no está.
        <Alert tono="neutral">Con tu rol podés leer las conversaciones, pero no atenderlas.</Alert>
      )}

      <ContextoDeAvisoDeBandeja.Provider value={aviso}>
        <div className={`cv-grid${conHilo ? " cv-grid--con-hilo" : ""}`}>
          <section className="cv-panel cv-bandeja" aria-labelledby="wa-lista-titulo">
            <header className="cv-bandeja__head">
              <h2 className="cv-bandeja__titulo" id="wa-lista-titulo">
                Conversaciones
              </h2>
              <span className="cv-etiquetas">
                <span className="cv-etiqueta">{contar(hilos.length, "hilo", "hilos")}</span>
                <span
                  className={`cv-etiqueta${esperando > 0 ? " cv-etiqueta--espera" : ""}`}
                  title="Hilos que esperan a un asesor"
                >
                  {contar(esperando, "espera", "esperan")}
                </span>
              </span>
            </header>

            <div className="cv-buscador">
              <span className="cv-buscador__icono">
                <IconoDeLupa />
              </span>
              <input
                type="search"
                className="cv-buscador__control"
                placeholder="Buscar por motivo o estado"
                aria-label="Buscar conversaciones"
                value={busqueda}
                onChange={(evento) => setBusqueda(evento.target.value)}
              />
              {busqueda !== "" && (
                <button
                  type="button"
                  className="cv-buscador__limpiar"
                  aria-label="Limpiar búsqueda"
                  onClick={() => setBusqueda("")}
                >
                  <IconoDeLimpiar />
                </button>
              )}
            </div>

            {/* Control segmentado y no botones verdes: en el resto del panel el verde sólido es
              la acción principal de la pantalla, y acá esto es un estado. */}
            <div className="cv-segmentos" role="group" aria-label="Filtros de la bandeja">
              <button
                type="button"
                className="cv-segmento"
                aria-pressed={soloEscaladas}
                onClick={() => void cambiarFiltro(true)}
              >
                <span className="cv-segmento__punto" aria-hidden="true" />
                Esperan a un asesor
                <span className="cv-segmento__cuenta">{esperando}</span>
              </button>
              <button
                type="button"
                className="cv-segmento"
                aria-pressed={!soloEscaladas}
                onClick={() => void cambiarFiltro(false)}
              >
                Todas
              </button>
            </div>

            {hilos.length === 0 ? (
              <div className="cv-vacio">
                <span className="cv-vacio__icono" aria-hidden="true">
                  <IconoDeBandeja />
                </span>
                <p className="cv-vacio__titulo">
                  {soloEscaladas ? MENSAJE_SIN_ESCALADAS : MENSAJE_SIN_CONVERSACIONES}
                </p>
                <p className="cv-vacio__texto">
                  {soloEscaladas
                    ? "Cuando el agente derive un hilo a una persona, aparece acá."
                    : "Los hilos nuevos aparecen acá apenas escribe un cliente."}
                </p>
              </div>
            ) : visibles.length === 0 ? (
              <div className="cv-vacio">
                <span className="cv-vacio__icono" aria-hidden="true">
                  <IconoDeLupa />
                </span>
                <p className="cv-vacio__titulo">Ninguna conversación coincide con tu búsqueda.</p>
                <button type="button" className="cv-vacio__accion" onClick={() => setBusqueda("")}>
                  Mostrar todas
                </button>
              </div>
            ) : (
              <ul
                className="cv-lista"
                aria-labelledby="wa-lista-titulo"
                onKeyDown={moverConFlechas}
              >
                {visibles.map((hilo, indice) => (
                  <FilaDeConversacion
                    key={hilo.id}
                    conversacion={hilo}
                    seleccionada={hilo.id === seleccionadaId}
                    indice={indice}
                  />
                ))}
              </ul>
            )}
          </section>

          {conHilo ? children : <SinHiloElegido />}
        </div>
      </ContextoDeAvisoDeBandeja.Provider>
    </>
  );
}
