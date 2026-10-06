/**
 * Un renglón de la bandeja (PAN-WA-01).
 *
 * El backend no manda el nombre del cliente ni el último mensaje en el listado: pedir cada hilo
 * entero para mostrar una línea sería una consulta por conversación. Por eso el título es el
 * motivo del escalamiento y la vista previa dice quién tiene la pelota. El avatar toma un tono
 * estable del cliente dueño del hilo: el mismo cliente se ve siempre con el mismo color.
 *
 * El renglón entero es el enlace: apuntar a 64 px de alto es más fácil que apuntar a tres
 * palabras. Lo que obliga a alguien a actuar —«espera un asesor»— se ve antes de leerlo.
 */

import Link from "next/link";

import type { Conversacion } from "../api/conversacion";
import { IconoDeBurbuja } from "./iconos";
import { horaRelativa, tonoDe } from "./vista";

export function tituloDe(conversacion: Conversacion): string {
  return conversacion.motivo ?? "Conversación con el agente";
}

export function etiquetaDe(conversacion: Conversacion): string {
  if (!conversacion.esta_escalada) {
    return "La atiende el agente";
  }
  return conversacion.estado_escalamiento === "ABIERTO" ? "Espera un asesor" : "En atención";
}

/** Quién tiene la pelota: lo que decide si alguien tiene que abrir el hilo. */
export function situacionDe(conversacion: Conversacion): string {
  if (conversacion.esta_escalada) {
    return conversacion.estado_escalamiento === "ABIERTO"
      ? "Todavía no la tomó nadie"
      : "La está atendiendo un operador";
  }
  return conversacion.estado === "ARCHIVADA" ? "Conversación archivada" : "El agente la sigue solo";
}

export type TonoDeEstado = "espera" | "atencion" | "agente";

export function tonoDeEstadoDe(conversacion: Conversacion): TonoDeEstado {
  if (!conversacion.esta_escalada) {
    return "agente";
  }
  return conversacion.estado_escalamiento === "ABIERTO" ? "espera" : "atencion";
}

export interface PropsDeFila {
  readonly conversacion: Conversacion;
  readonly seleccionada: boolean;
  /** Para la entrada escalonada: cuánto se demora este renglón. */
  readonly indice: number;
}

export function FilaDeConversacion({
  conversacion,
  seleccionada,
  indice,
}: PropsDeFila): JSX.Element {
  const estado = tonoDeEstadoDe(conversacion);
  return (
    <li className="cv-item" style={{ animationDelay: `${Math.min(indice, 12) * 28}ms` }}>
      <Link
        href={`/conversaciones/${conversacion.id}`}
        className={`cv-fila${seleccionada ? " cv-fila--activa" : ""}`}
        aria-current={seleccionada ? "page" : undefined}
      >
        <span className={`cv-avatar cv-tono-${tonoDe(conversacion.cliente_id)}`} aria-hidden="true">
          <IconoDeBurbuja />
          {estado === "espera" && <span className="cv-avatar__alerta" />}
        </span>
        <span className="cv-fila__cuerpo">
          <span className="cv-fila__top">
            <span className="cv-fila__titulo">{tituloDe(conversacion)}</span>
            <span className="cv-fila__hora">{horaRelativa(conversacion.ultimo_mensaje_en)}</span>
          </span>
          <span className="cv-fila__vista">{situacionDe(conversacion)}</span>
          <span className={`cv-pastilla cv-pastilla--${estado}`}>
            <span className="cv-pastilla__punto" aria-hidden="true" />
            {etiquetaDe(conversacion)}
          </span>
        </span>
      </Link>
    </li>
  );
}
