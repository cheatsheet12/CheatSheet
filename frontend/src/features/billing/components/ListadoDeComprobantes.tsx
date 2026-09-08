/**
 * PAN-FAC-01 — Facturación · Listado (HU-E5-01).
 *
 * Las seis columnas que nombra el criterio de aceptación —número, tipo, cliente, monto,
 * fecha y estado— y los tres filtros de RN-02.
 *
 * **Acá no se suma nada.** Los importes llegan como texto y se muestran como texto; lo que
 * un cliente debe lo decidió el backend y lo autorizó ARCA, y una pantalla que volviera a
 * sumar las líneas terminaría discrepando con el comprobante mismo.
 *
 * **El filtro va al servidor, no al arreglo en memoria.** Un listado filtrado en el
 * navegador es un listado que miente apenas se pagina, y éste se va a paginar.
 *
 * **El encabezado vive acá y no en `page.tsx`.** El CTA verde es la acción de esta pantalla
 * y depende del rol; separarlo del título obligaría a pasar `puedeEmitir` dos veces y
 * abriría la puerta a que un día el botón aparezca sin que el listado lo sepa.
 *
 * **Los chips y el `select` de estado son el mismo filtro.** Los chips son el atajo a los
 * tres cortes que se miran a diario; el `select` es el control que un lector de pantalla
 * anuncia con su etiqueta. Los dos escriben `filtros.estado` y los dos leen de ahí, así que
 * no pueden mostrar cosas distintas.
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

/**
 * Los atajos del prototipo: los tres cortes que se miran a diario.
 *
 * **Sin contador.** Contar sobre `listado.comprobantes` contaría la página y no el período,
 * y un número que cambia al pasar de hoja es peor que no tener número.
 */
const CHIPS: readonly { valor: string; etiqueta: string; modificador: string }[] = [
  { valor: "", etiqueta: "Todos", modificador: "" },
  { valor: "AUTORIZADO", etiqueta: "Autorizados", modificador: " fac-nuevo-chip--autorizado" },
  { valor: "ENVIADO_A_ARCA", etiqueta: "Pendientes", modificador: " fac-nuevo-chip--pendiente" },
  { valor: "RECHAZADO", etiqueta: "Con error", modificador: " fac-nuevo-chip--error" },
];

export function ListadoDeComprobantes({
  inicial,
  puedeEmitir,
}: PropsDeListadoDeComprobantes): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeComprobante>({});
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function aplicar(cambios: FiltrosDeComprobante): Promise<void> {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    setError(null);
    setCargando(true);
    try {
      setListado(await listarComprobantes(siguientes));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeComprobante ? fallo.message : "No se pudo actualizar el listado.",
      );
    } finally {
      setCargando(false);
    }
  }

  const columnas: readonly Columna<Comprobante>[] = [
    {
      clave: "numero",
      titulo: "Número",
      celda: (fila) => (
        // The detail is a link and not a row handler: it is a page with its own URL, so it
        // can be opened in a new tab and sent to an accountant.
        <Link href={`/facturacion/${fila.id}`} className="fac-nuevo-numero">
          {fila.numero === null ? "Sin numerar" : String(fila.numero).padStart(8, "0")}
        </Link>
      ),
    },
    { clave: "tipo", titulo: "Tipo", celda: (fila) => ETIQUETAS_DE_TIPO[fila.tipo] },
    {
      clave: "cliente",
      titulo: "Cliente",
      celda: (fila) => <span className="fac-nuevo-cliente">{fila.receptor_nombre}</span>,
    },
    {
      clave: "total",
      titulo: "Total",
      // Interpolado entero: partido en dos hijos, un salto de línea del formateador se
      // lleva puesto el espacio entre el signo y el número.
      celda: (fila) => (
        <span className="fac-nuevo-importe">{`$ ${formatearNumero(fila.total)}`}</span>
      ),
      alDerecha: true,
    },
    {
      clave: "fecha",
      titulo: "Fecha",
      celda: (fila) => (
        <span className="fac-nuevo-fecha">
          {formatearFecha(fila.fecha_emision ?? fila.created_at)}
        </span>
      ),
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
      <header className="fac-nuevo-encabezado">
        <div>
          <span className="fac-nuevo-encabezado__cintillo">Facturación</span>
          <h1 className="fac-nuevo-encabezado__titulo">Comprobantes</h1>
          <p className="fac-nuevo-encabezado__sub">
            Los que emitiste, con su CAE cuando ARCA los autorizó. Un comprobante autorizado no se
            modifica ni se borra: se reversa con una nota de crédito.
          </p>
        </div>
        {puedeEmitir && (
          <div className="fac-nuevo-encabezado__acciones">
            <Link
              href="/facturacion/nueva"
              className="boton boton--primario fac-nuevo-boton-enlace"
            >
              Emitir comprobante
            </Link>
          </div>
        )}
      </header>

      <div className="fac-nuevo-avisos">
        {error !== null && (
          <Alert tono="error" titulo="No se pudo completar">
            {error}
          </Alert>
        )}
      </div>

      <section className="fac-nuevo-panel">
        <div className="fac-nuevo-barra">
          <div className="fac-nuevo-chips" role="group" aria-label="Filtros rápidos por estado">
            {CHIPS.map((chip) => (
              <button
                key={chip.etiqueta}
                type="button"
                className={`fac-nuevo-chip${chip.modificador}`}
                aria-pressed={(filtros.estado ?? "") === chip.valor}
                onClick={() => void aplicar({ estado: chip.valor })}
              >
                {chip.valor !== "" && <span className="fac-nuevo-chip__punto" aria-hidden />}
                {chip.etiqueta}
              </button>
            ))}
          </div>
        </div>

        <div className="fac-nuevo-filtros">
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

        <div className={cargando ? "fac-nuevo-cargando" : undefined} aria-busy={cargando}>
          <Tabla
            titulo="Comprobantes emitidos"
            columnas={columnas}
            filas={listado.comprobantes}
            claveDeFila={(fila) => fila.id}
            vacia={MENSAJE_SIN_RESULTADOS}
          />
        </div>
      </section>
    </>
  );
}
