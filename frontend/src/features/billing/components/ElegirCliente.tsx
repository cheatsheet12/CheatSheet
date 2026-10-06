/**
 * Elegir a quién facturar, sin salir de la emisión.
 *
 * «Emitir comprobante» es la acción principal de PAN-FAC-01, y hasta acá terminaba en una
 * tarjeta que decía «elegí primero a quién le vas a facturar» y mandaba a otra pantalla. El
 * botón principal de una pantalla no puede dejar a alguien en un lugar donde lo único que
 * puede hacer es irse.
 *
 * **Sólo los clientes que se pueden facturar.** Un cliente sin CUIT no admite comprobante
 * —el receptor es lo primero que ARCA valida—, así que aparece deshabilitado y con el
 * motivo, en vez de desaparecer: alguien que lo busca tiene que encontrarlo y entender por
 * qué no está disponible, no concluir que se borró.
 */

"use client";

import { useMemo, useState } from "react";

import { Campo } from "@/shared";

import Link from "next/link";

import type { Cliente } from "@/features/master_data";

export interface PropsDeElegirCliente {
  readonly clientes: readonly Cliente[];
}

function normalizar(texto: string): string {
  return texto.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

export function ElegirCliente({ clientes }: PropsDeElegirCliente): JSX.Element {
  const [busqueda, setBusqueda] = useState("");

  const visibles = useMemo(() => {
    const aguja = normalizar(busqueda.trim());
    if (aguja === "") {
      return clientes;
    }
    return clientes.filter(
      (uno) =>
        normalizar(uno.nombre).includes(aguja) ||
        (uno.cuit ?? "").replace(/-/g, "").includes(aguja),
    );
  }, [clientes, busqueda]);

  if (clientes.length === 0) {
    return (
      <section className="fac-nuevo-tarjeta">
        <p className="fac-nuevo-rotulo">Todavía no hay clientes</p>
        <p>
          Un comprobante se emite a nombre de un cliente del catálogo.{" "}
          <Link href="/datos-maestros/clientes">Cargá el primero</Link> y volvé.
        </p>
      </section>
    );
  }

  return (
    <section className="fac-nuevo-tarjeta">
      <p className="fac-nuevo-rotulo">¿A quién le facturás?</p>
      <Campo
        id="buscar-cliente"
        etiqueta="Buscar"
        placeholder="Por nombre o por CUIT"
        value={busqueda}
        onChange={(evento) => {
          setBusqueda(evento.target.value);
        }}
      />

      {visibles.length === 0 ? (
        <p className="fac-elegir__vacio">Ningún cliente coincide con «{busqueda}».</p>
      ) : (
        <ul className="fac-elegir">
          {visibles.map((uno) => {
            const facturable = uno.cuit !== null && uno.cuit !== "";
            return (
              <li key={uno.id} className="fac-elegir__fila">
                <span>
                  <b className="fac-elegir__nombre">{uno.nombre}</b>
                  <span className="fac-elegir__cuit">
                    {facturable ? uno.cuit : "Sin CUIT: no se le puede emitir un comprobante"}
                  </span>
                </span>
                {facturable ? (
                  <Link
                    className="fac-elegir__accion"
                    href={`/facturacion/nueva?cliente=${uno.id}`}
                  >
                    Facturar
                  </Link>
                ) : (
                  <Link className="fac-elegir__completar" href="/datos-maestros/clientes">
                    Completar sus datos
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
