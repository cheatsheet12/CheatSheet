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
 * Y el renglón entero es el enlace, porque apuntar a 60 px de alto es más fácil que apuntar a
 * las tres palabras del título.
 *
 * **Un hilo escalado se ve antes de leerlo**: fondo, borde y badge. Es el único estado que
 * obliga a alguien a hacer algo, y encontrarlo renglón por renglón es tiempo con un cliente
 * esperando del otro lado.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge } from "@/shared";

import {
  ErrorDeConversacion,
  MENSAJE_SIN_CONVERSACIONES,
  MENSAJE_SIN_ESCALADAS,
  horaDeMensaje,
  listarConversaciones,
  tonoDeEscalamiento,
} from "../api/conversacion";
import type { Conversacion, ListadoDeConversaciones } from "../api/conversacion";
import { IconoDeChat } from "./iconos";

export interface PropsDeBandejaDeConversaciones {
  readonly inicial: ListadoDeConversaciones;
  /** Administrador y Operador atienden; Solo Lectura mira (HU-E9-01). */
  readonly puedeAtender: boolean;
}

/** «1 hilo» y no «1 hilos»: el contador se lee, y un plural mal puesto se nota. */
function contar(cantidad: number, singular: string, plural: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : plural}`;
}

function etiquetaDe(conversacion: Conversacion): string {
  if (!conversacion.esta_escalada) {
    return "La atiende el agente";
  }
  return conversacion.estado_escalamiento === "ABIERTO" ? "Espera un asesor" : "En atención";
}

/**
 * El renglón de abajo del título.
 *
 * El prototipo pone ahí el último mensaje; el backend no lo manda en el listado, y pedir
 * cada hilo entero para mostrar una línea sería una consulta por conversación. Lo que sí
 * hay —quién tiene la pelota— es justamente lo que decide si alguien tiene que abrirla.
 */
function situacionDe(conversacion: Conversacion): string {
  if (conversacion.esta_escalada) {
    return conversacion.estado_escalamiento === "ABIERTO"
      ? "Todavía no la tomó nadie"
      : "La está atendiendo un operador";
  }
  return conversacion.estado === "ARCHIVADA" ? "Conversación archivada" : "El agente la sigue solo";
}

export function BandejaDeConversaciones({
  inicial,
  puedeAtender,
}: PropsDeBandejaDeConversaciones): JSX.Element {
  const [listado, setListado] = useState<ListadoDeConversaciones>(inicial);
  const [soloEscaladas, setSoloEscaladas] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function cambiarFiltro(valor: boolean): Promise<void> {
    setSoloEscaladas(valor);
    setError(null);
    try {
      setListado(await listarConversaciones(valor));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeConversacion ? fallo.message : "No se pudo actualizar la bandeja.",
      );
    }
  }

  const hilos = listado.conversaciones;
  const esperando = hilos.filter((uno) => uno.estado_escalamiento === "ABIERTO").length;

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

      <div className="wa-grid">
        <section className="wa-panel" aria-labelledby="wa-lista-titulo">
          <header className="wa-panel__head">
            <h2 className="wa-panel__titulo" id="wa-lista-titulo">
              Conversaciones
            </h2>
            <span className="wa-panel__cuenta">
              {contar(hilos.length, "hilo", "hilos")} ·{" "}
              {contar(esperando, "espera un asesor", "esperan un asesor")}
            </span>
          </header>

          {/* Píldoras de filtro y no botones verdes: en el resto del panel el verde sólido es
              la acción principal de la pantalla, y acá esto es un estado. Con la bandeja vacía
              lo más llamativo terminaba siendo un filtro que no filtraba nada. Mismo
              tratamiento que en `/facturacion` y `/cobros`. */}
          <div className="wa-filtros" role="group" aria-label="Filtros de la bandeja">
            <button
              type="button"
              className="wa-chip"
              aria-pressed={soloEscaladas}
              onClick={() => void cambiarFiltro(true)}
            >
              <span className="wa-chip__punto" aria-hidden="true" />
              Esperan a un asesor
            </button>
            <button
              type="button"
              className="wa-chip"
              aria-pressed={!soloEscaladas}
              onClick={() => void cambiarFiltro(false)}
            >
              Todas
            </button>
          </div>

          {hilos.length === 0 ? (
            <p className="wa-panel__vacio">
              {soloEscaladas ? MENSAJE_SIN_ESCALADAS : MENSAJE_SIN_CONVERSACIONES}
            </p>
          ) : (
            <ul className="wa-lista" aria-labelledby="wa-lista-titulo">
              {hilos.map((hilo) => (
                <li key={hilo.id}>
                  <Link
                    href={`/conversaciones/${hilo.id}`}
                    className={`wa-fila${hilo.esta_escalada ? " wa-fila--escalada" : ""}`}
                  >
                    <span
                      className={`wa-avatar${hilo.esta_escalada ? " wa-avatar--alerta" : ""}`}
                      aria-hidden="true"
                    >
                      <IconoDeChat />
                    </span>
                    <span className="wa-fila__cuerpo">
                      <span className="wa-fila__top">
                        <span className="wa-fila__nombre">
                          {hilo.motivo ?? "Conversación con el agente"}
                        </span>
                        <span className="wa-fila__hora">
                          {horaDeMensaje(hilo.ultimo_mensaje_en)}
                        </span>
                      </span>
                      <span className="wa-fila__motivo">{situacionDe(hilo)}</span>
                      <Badge
                        estado={
                          hilo.esta_escalada ? tonoDeEscalamiento(hilo.estado_escalamiento) : "ok"
                        }
                      >
                        {etiquetaDe(hilo)}
                      </Badge>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* El panel derecho del prototipo, todavía sin hilo elegido. Un hueco vacío al lado
            de la lista se lee como una pantalla que falló al cargar. */}
        <section className="wa-panel wa-panel--sin-hilo">
          <div>
            <span className="wa-avatar wa-avatar--grande" aria-hidden="true">
              <IconoDeChat />
            </span>
            <b>Elegí una conversación</b>
            <p>
              El hilo completo se abre acá: lo que dijo el cliente, lo que contestó el agente y lo
              que escribió un operador.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
