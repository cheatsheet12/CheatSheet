/**
 * PAN-COB-01 — Cobros · Listado (HU-E6-01).
 *
 * Las cuatro métricas del encabezado y el listado con su estado, que es lo que pide el primer
 * criterio de aceptación.
 *
 * **Las etiquetas no son los estados.** La historia es explícita: `APROBADO` se muestra
 * «Pagado» y `VENCIDO` se muestra «En mora». El dominio es la fuente de verdad y esto es
 * presentación — pero el filtro manda el nombre del dominio, porque es lo que el backend
 * entiende.
 *
 * **Nada acá suma nada.** Las métricas llegan calculadas sobre el período entero: sumarlas en
 * el navegador sobre la página mostraría un total que cambia al pasar de hoja.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Alert,
  Badge,
  Campo,
  Card,
  Select,
  Tabla,
  formatearFecha,
  formatearNumero,
} from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  MENSAJE_SIN_RESULTADOS,
  listarCobros,
  tonoDeEstado,
} from "../api/cobro";
import type { Cobro, FiltrosDeCobro, ListadoDeCobros as Listado } from "../api/cobro";

export interface PropsDeListadoDeCobros {
  readonly inicial: Listado;
  /** Administrador y Operador generan; Solo Lectura sólo mira (HU-E6-01 RN-04). */
  readonly puedeGestionar: boolean;
}

/**
 * Los cinco estados del enum, con la etiqueta de interfaz de cada uno.
 *
 * El valor que viaja es el del dominio y la etiqueta es lo que se lee: mandar «En mora» al
 * backend obligaría a traducir del otro lado, que es el seam donde una traducción mal hecha
 * hace que un filtro devuelva la lista entera.
 */
const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "APROBADO", etiqueta: "Pagado" },
  { valor: "PENDIENTE", etiqueta: "Pendiente" },
  { valor: "VENCIDO", etiqueta: "En mora" },
  { valor: "CANCELADO", etiqueta: "Cancelado" },
  { valor: "REEMBOLSADO", etiqueta: "Reembolsado" },
];

export function ListadoDeCobros({ inicial, puedeGestionar }: PropsDeListadoDeCobros): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeCobro>({});
  const [error, setError] = useState<string | null>(null);

  async function aplicar(cambios: FiltrosDeCobro): Promise<void> {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    setError(null);
    try {
      setListado(await listarCobros(siguientes));
    } catch (fallo) {
      setError(fallo instanceof ErrorDeCobro ? fallo.message : "No se pudo actualizar el listado.");
    }
  }

  const columnas: readonly Columna<Cobro>[] = [
    {
      clave: "concepto",
      titulo: "Concepto",
      celda: (fila) => <Link href={`/cobros/${fila.id}`}>{fila.descripcion}</Link>,
    },
    {
      clave: "monto",
      titulo: "Monto",
      celda: (fila) => `$ ${formatearNumero(fila.monto)}`,
      alDerecha: true,
    },
    { clave: "vence", titulo: "Vence", celda: (fila) => formatearFecha(fila.vence_el) },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDeEstado(fila.estado)}>{ETIQUETAS_DE_ESTADO[fila.estado]}</Badge>
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

      <div className="fac-detalle">
        <Card titulo="Cobrado">
          <p className="fac-totales__final">$ {formatearNumero(listado.metricas.cobrado)}</p>
        </Card>
        <Card titulo="Pendiente">
          <p className="fac-totales__final">$ {formatearNumero(listado.metricas.pendiente)}</p>
        </Card>
        <Card titulo="En mora">
          <p className="fac-totales__final">$ {formatearNumero(listado.metricas.en_mora)}</p>
        </Card>
        <Card titulo="Tasa de cobro">
          <p className="fac-totales__final">{formatearNumero(listado.metricas.tasa_de_cobro)} %</p>
        </Card>
      </div>

      {puedeGestionar && (
        <div className="fac-acciones">
          <Link href="/cobros/nuevo" className="boton boton--primario">
            Generar cobro
          </Link>
        </div>
      )}

      <div className="dm-filtros">
        <Campo
          id="cobros-desde"
          etiqueta="Desde"
          type="date"
          value={filtros.desde ?? ""}
          onChange={(evento) => void aplicar({ desde: evento.target.value })}
        />
        <Campo
          id="cobros-hasta"
          etiqueta="Hasta"
          type="date"
          value={filtros.hasta ?? ""}
          onChange={(evento) => void aplicar({ hasta: evento.target.value })}
        />
        <Select
          id="cobros-estado"
          etiqueta="Estado"
          opciones={ESTADOS}
          value={filtros.estado ?? ""}
          onChange={(evento) => void aplicar({ estado: evento.target.value })}
        />
      </div>

      <Tabla
        titulo="Cobros del período"
        columnas={columnas}
        filas={listado.cobros}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_RESULTADOS}
      />
    </>
  );
}
