/**
 * PAN-FAC-01 — Facturación · Listado (HU-E5-01).
 *
 * The six columns the acceptance criterion names — número, tipo, cliente, monto, fecha y
 * estado — and the three filters of RN-02.
 *
 * **Nothing here computes a total.** The amounts arrive as strings and are formatted for
 * display; what a customer owes was decided by the backend and authorised by ARCA, and a
 * screen that re-added the lines would eventually disagree with the document itself.
 *
 * **Filtering goes to the server, not to the array in memory.** A listing filtered in the
 * browser is a listing that lies as soon as it is paginated, and this one will be.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Campo, Select, Tabla, formatearFecha, formatearNumero } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeComprobante,
  MENSAJE_SIN_RESULTADOS,
  listarComprobantes,
  tonoDeEstado,
} from "../api/comprobante";
import type {
  Comprobante,
  EstadoComprobante,
  FiltrosDeComprobante,
  ListadoDeComprobantes as Listado,
} from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import type { TipoComprobante } from "../api/puntoDeVenta";

export interface PropsDeListadoDeComprobantes {
  readonly inicial: Listado;
  /** Administrador and Operador issue; Solo Lectura only looks (HU-E5-01 RN-04). */
  readonly puedeEmitir: boolean;
}

const TIPOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los tipos" },
  ...(Object.keys(ETIQUETAS_DE_TIPO) as TipoComprobante[]).map((valor) => ({
    valor,
    etiqueta: ETIQUETAS_DE_TIPO[valor],
  })),
];

// The three the story names, and only those. `BORRADOR` and `VALIDADO` are states of a
// document nobody has confirmed yet, and offering them as filters would suggest the
// listing is a work queue, which it is not.
const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "AUTORIZADO", etiqueta: "Autorizado" },
  { valor: "ENVIADO_A_ARCA", etiqueta: "Pendiente" },
  { valor: "RECHAZADO", etiqueta: "Error" },
];

export function ListadoDeComprobantes({
  inicial,
  puedeEmitir,
}: PropsDeListadoDeComprobantes): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeComprobante>({});
  const [error, setError] = useState<string | null>(null);

  async function aplicar(cambios: FiltrosDeComprobante): Promise<void> {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    setError(null);
    try {
      setListado(await listarComprobantes(siguientes));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeComprobante ? fallo.message : "No se pudo actualizar el listado.",
      );
    }
  }

  const columnas: readonly Columna<Comprobante>[] = [
    {
      clave: "numero",
      titulo: "Numero",
      celda: (fila) => (
        // The detail is a link and not a row handler: it is a page with its own URL, so it
        // can be opened in a new tab and sent to an accountant.
        <Link href={`/facturacion/${fila.id}`} className="fac-mono">
          {fila.numero === null ? "Sin numerar" : String(fila.numero).padStart(8, "0")}
        </Link>
      ),
    },
    { clave: "tipo", titulo: "Tipo", celda: (fila) => ETIQUETAS_DE_TIPO[fila.tipo] },
    { clave: "cliente", titulo: "Cliente", celda: (fila) => fila.receptor_nombre },
    {
      clave: "total",
      titulo: "Monto",
      celda: (fila) => `$ ${formatearNumero(fila.total)}`,
      alDerecha: true,
    },
    {
      clave: "fecha",
      titulo: "Fecha",
      celda: (fila) => formatearFecha(fila.fecha_emision ?? fila.created_at),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDeEstado(fila.estado)}>
          {ETIQUETAS_DE_ESTADO[fila.estado as EstadoComprobante]}
        </Badge>
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

      {puedeEmitir && (
        <div className="fac-acciones">
          <Link href="/facturacion/nueva" className="boton boton--primario">
            Emitir comprobante
          </Link>
        </div>
      )}

      <div className="dm-filtros">
        <Campo
          id="comprobantes-desde"
          etiqueta="Desde"
          type="date"
          value={filtros.desde ?? ""}
          onChange={(evento) => void aplicar({ desde: evento.target.value })}
        />
        <Campo
          id="comprobantes-hasta"
          etiqueta="Hasta"
          type="date"
          value={filtros.hasta ?? ""}
          onChange={(evento) => void aplicar({ hasta: evento.target.value })}
        />
        <Select
          id="comprobantes-tipo"
          etiqueta="Tipo"
          opciones={TIPOS}
          value={filtros.tipo ?? ""}
          onChange={(evento) => void aplicar({ tipo: evento.target.value })}
        />
        <Select
          id="comprobantes-estado"
          etiqueta="Estado"
          opciones={ESTADOS}
          value={filtros.estado ?? ""}
          onChange={(evento) => void aplicar({ estado: evento.target.value })}
        />
      </div>

      <Tabla
        titulo="Comprobantes emitidos"
        columnas={columnas}
        filas={listado.comprobantes}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_RESULTADOS}
      />
    </>
  );
}
