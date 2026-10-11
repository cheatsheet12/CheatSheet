/**
 * Re-accepting the legal texts when a version in force changes — a variant of PAN-ONB-01
 * (HU-E1-03 RN-03, HU-E1-08 RN-05; decisions 7 and 8 of the unit plan).
 *
 * The person owes something, so the API answers 403 to everything else. This screen is the
 * way out and it has **two buttons and nothing more**: «Aceptar» and «Cerrar sesión». There
 * is no "No acepto": declining and signing out are the same act, so the second one is the
 * only one offered, and **nothing signs the person out by itself** (decision 7). No data is
 * deleted while they decide.
 *
 * There are no checkboxes: the request is a short sentence about what changed, with a link
 * to each text, and pressing «Aceptar» is the acceptance. What is sent back is the version of
 * each document exactly as `/legal/pendientes` listed it, and the backend checks it is still
 * the one in force before recording anything.
 */

"use client";

import { useState } from "react";

import { Alert, Button, useAccionConNavegacion } from "@/shared";

import { ErrorDeFormulario, aceptarDocumentos } from "../api/cliente";
import type { PendienteLegal } from "../api/cliente";
import { RUTAS_LEGALES, TITULOS_LEGALES, fechaLegible } from "./etiquetas-legales";

export interface PropsDeFormularioDeReaceptacion {
  readonly pendientes: readonly PendienteLegal[];
}

const SIN_CONEXION = "No pudimos completar la operación. Probá de nuevo en unos minutos.";

export function FormularioDeReaceptacion({
  pendientes,
}: PropsDeFormularioDeReaceptacion): JSX.Element {
  const [error, setError] = useState<string | undefined>(undefined);
  const { pendiente: aceptando, ejecutar: ejecutarAceptacion } = useAccionConNavegacion();
  const { pendiente: saliendo, ejecutar: ejecutarSalida } = useAccionConNavegacion();

  const aceptar = async (): Promise<void> => {
    setError(undefined);
    try {
      await ejecutarAceptacion(
        () =>
          aceptarDocumentos(pendientes.map(({ documento, version }) => ({ documento, version }))),
        // The panel decides where they go next (it may still owe the onboarding).
        (_resultado, router) => router.push("/panel"),
      );
    } catch (fallo) {
      setError(fallo instanceof ErrorDeFormulario ? fallo.detalle : SIN_CONEXION);
    }
  };

  const cerrarSesion = async (): Promise<void> => {
    await ejecutarSalida(
      async () => {
        try {
          await fetch("/api/auth/logout", { method: "POST" });
        } catch {
          // Leaving is what was asked for; a failed request is no reason to trap them here.
        }
      },
      (_resultado, router) => {
        router.push("/");
        router.refresh();
      },
    );
  };

  return (
    <section className="acc-tarjeta acc-tarjeta--angosta">
      <header className="acc-encabezado">
        <h1 className="acc-titulo">Actualizamos nuestros textos legales</h1>
        <p className="acc-sub">
          Para seguir usando CheatSheet tenés que aceptar la versión vigente. Hasta entonces solo
          podés leer los textos y cerrar sesión.
        </p>
      </header>

      {error !== undefined && (
        <div className="acc-aviso">
          <Alert tono="error">{error}</Alert>
        </div>
      )}

      <ul className="acc-documentos" aria-label="Documentos para aceptar">
        {pendientes.map((pendiente) => (
          <li key={pendiente.documento} className="acc-documento">
            <a
              className="acc-enlace"
              href={RUTAS_LEGALES[pendiente.documento]}
              target="_blank"
              rel="noopener noreferrer"
            >
              {TITULOS_LEGALES[pendiente.documento]}
            </a>
            <span className="acc-documento__detalle">
              Versión {pendiente.version} · vigente desde el {fechaLegible(pendiente.vigente_desde)}
            </span>
            {pendiente.borrador && (
              <span className="acc-documento__borrador">
                Versión preliminar, pendiente de validación legal.
              </span>
            )}
          </li>
        ))}
      </ul>

      <div className="acc-acciones">
        <Button
          type="button"
          cargando={aceptando}
          disabled={saliendo}
          onClick={() => void aceptar()}
        >
          Aceptar
        </Button>
        <Button
          type="button"
          variante="secundario"
          cargando={saliendo}
          disabled={aceptando}
          onClick={() => void cerrarSesion()}
        >
          Cerrar sesión
        </Button>
      </div>
    </section>
  );
}
