/**
 * The active-client picker (PAN-COB-03 RN-05). Billing and the agenda reuse it.
 *
 * **The URL is the only source of truth for who is selected.** Choosing somebody does
 * `router.replace(`${destino}?cliente=<id>`)` and the server page renders again with that
 * client: the page, not this component, knows what else depends on it (the receipts of that
 * client, for one). `replace` and not `push`, so going back does not walk through every client
 * that was looked at. `destino` is a plain string because a server page cannot hand a function
 * to a client component.
 *
 * It only offers **active** clients and searches by name or CUIT; which of the two a text
 * matches is the backend's decision (the CUIT is compared by its digits, so the one on screen
 * can be pasted as it is). It never creates a client (D92): with no result it offers the way to
 * Clientes instead.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert, Campo, Card } from "@/shared";

import { listarClientes } from "../api/cliente";
import type { Cliente } from "../api/cliente";

/** What the page already knows about the chosen client. */
export interface ClienteSeleccionado {
  readonly id: string;
  readonly nombre: string;
  readonly cuit: string | null;
}

export interface PropsDeSelectorDeClientes {
  /** The route that owns the selection, e.g. `/cobros/nuevo`. */
  readonly destino: string;
  readonly seleccionado: ClienteSeleccionado | null;
}

const ESPERA_DE_TIPEO_MS = 250;

export function SelectorDeClientes({
  destino,
  seleccionado,
}: PropsDeSelectorDeClientes): JSX.Element {
  const router = useRouter();
  const [texto, setTexto] = useState("");
  const [encontrados, setEncontrados] = useState<readonly Cliente[]>([]);
  const [cargado, setCargado] = useState(false);
  const [error, setError] = useState(false);
  const primeraCarga = useRef(true);

  useEffect(() => {
    let vigente = true;
    // The first load is immediate; later ones wait for the typing to stop, so a CUIT typed
    // digit by digit is one query and not eleven.
    const espera = primeraCarga.current ? 0 : ESPERA_DE_TIPEO_MS;
    primeraCarga.current = false;
    const temporizador = setTimeout(() => {
      listarClientes({ texto, soloActivos: true })
        .then((listado) => {
          if (vigente) {
            setEncontrados(listado.clientes);
            setError(false);
            setCargado(true);
          }
        })
        .catch(() => {
          if (vigente) {
            setError(true);
            setCargado(true);
          }
        });
    }, espera);
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [texto]);

  function elegir(id: string): void {
    router.replace(`${destino}?cliente=${encodeURIComponent(id)}`);
  }

  return (
    <Card titulo="Cliente">
      <div className="dm-formulario">
        {seleccionado !== null && (
          <p className="dm-clientes__elegido">
            <span className="dm-clientes__rotulo">Cliente seleccionado</span>
            <strong>{seleccionado.nombre}</strong>
            {seleccionado.cuit !== null && <span>{seleccionado.cuit}</span>}
          </p>
        )}

        <Campo
          id="selector-de-clientes"
          etiqueta="Buscar cliente por nombre o CUIT"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
        />

        {error && <Alert tono="advertencia">No se pudieron cargar los clientes.</Alert>}

        {!error && cargado && encontrados.length === 0 && (
          <p className="dm-clientes__vacio">
            No se encontraron clientes.{" "}
            <Link href="/datos-maestros/clientes" className="dm-clientes__enlace">
              Ir a Clientes
            </Link>
          </p>
        )}

        {encontrados.length > 0 && (
          <ul className="dm-clientes__lista">
            {encontrados.map((cliente) => (
              <li key={cliente.id}>
                <button
                  type="button"
                  className="dm-clientes__opcion"
                  aria-current={cliente.id === seleccionado?.id ? "true" : undefined}
                  onClick={() => elegir(cliente.id)}
                >
                  <span>{cliente.nombre}</span>
                  <span className="dm-clientes__cuit">{cliente.cuit ?? "Sin CUIT"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
