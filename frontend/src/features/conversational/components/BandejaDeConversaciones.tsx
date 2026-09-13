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
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Tabla, formatearFechaHora } from "@/shared";
import type { Columna } from "@/shared";

import {
  ErrorDeConversacion,
  MENSAJE_SIN_CONVERSACIONES,
  MENSAJE_SIN_ESCALADAS,
  listarConversaciones,
  tonoDeEscalamiento,
} from "../api/conversacion";
import type { Conversacion, ListadoDeConversaciones } from "../api/conversacion";

export interface PropsDeBandejaDeConversaciones {
  readonly inicial: ListadoDeConversaciones;
  /** Administrador y Operador atienden; Solo Lectura mira (HU-E9-01). */
  readonly puedeAtender: boolean;
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

  const columnas: readonly Columna<Conversacion>[] = [
    {
      clave: "hilo",
      titulo: "Conversación",
      celda: (fila) => (
        <Link href={`/conversaciones/${fila.id}`}>
          {fila.motivo ?? "Conversación con el agente"}
        </Link>
      ),
    },
    {
      clave: "actividad",
      titulo: "Último mensaje",
      celda: (fila) => formatearFechaHora(fila.ultimo_mensaje_en),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) =>
        fila.esta_escalada ? (
          <Badge estado={tonoDeEscalamiento(fila.estado_escalamiento)}>
            {fila.estado_escalamiento === "ABIERTO" ? "Espera un asesor" : "En atención"}
          </Badge>
        ) : (
          <Badge estado="ok">La atiende el agente</Badge>
        ),
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <div className="fac-acciones">
        <Button
          variante={soloEscaladas ? "primario" : "secundario"}
          onClick={() => void cambiarFiltro(true)}
        >
          Esperan a un asesor
        </Button>
        <Button
          variante={soloEscaladas ? "secundario" : "primario"}
          onClick={() => void cambiarFiltro(false)}
        >
          Todas
        </Button>
      </div>

      {!puedeAtender && (
        // No se esconde la bandeja: Solo Lectura puede necesitar ver qué está pasando. Lo
        // que no puede es tomar un escalamiento, y eso se dice acá en vez de que lo descubra
        // apretando un botón que no está.
        <Alert tono="neutral">Con tu rol podés leer las conversaciones, pero no atenderlas.</Alert>
      )}

      <Tabla
        titulo="Conversaciones"
        columnas={columnas}
        filas={listado.conversaciones}
        claveDeFila={(fila) => fila.id}
        vacia={soloEscaladas ? MENSAJE_SIN_ESCALADAS : MENSAJE_SIN_CONVERSACIONES}
      />
    </>
  );
}
