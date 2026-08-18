/**
 * PAN-CFG-INT — the four cards, the live check and the consolidated timestamp.
 *
 * HU-E2-05 in one component. The initial state is rendered by the server page; this takes
 * over from there so the check can update the table in place.
 *
 * **Connecting sends a placeholder credential.** Every provider is simulated in this unit
 * (`ConectorSimulado`), so there is no certificate to upload and no OAuth window to open —
 * those arrive with `conexion-arca`, `conexion-mercadopago` and `conexion-whatsapp`, each
 * replacing this button with its provider's real flow. What is exercised today is the path
 * that matters underneath: encrypt, persist, verify, audit.
 */

"use client";

import { useState } from "react";

import { Alert, Button, formatearFechaHora } from "@/shared";

import { conectarIntegracion, listarIntegraciones, verificarIntegraciones } from "../api/cliente";
import type { Integracion, ListadoDeIntegraciones, SistemaExterno } from "../api/cliente";
import { TarjetaDeIntegracion } from "./TarjetaDeIntegracion";

/** Google Sheets and Excel Online are on the screen; their connection is epic 4. */
const CONECTABLES: readonly SistemaExterno[] = ["ARCA", "MERCADOPAGO", "WHATSAPP"];

/** Stands in for the certificate or token a real provider flow will collect. */
const CREDENCIAL_SIMULADA = btoa("credencial-simulada");

export interface PropsDeGrilla {
  readonly inicial: ListadoDeIntegraciones;
  readonly puedeConectar: boolean;
}

export function GrillaDeIntegraciones({ inicial, puedeConectar }: PropsDeGrilla): JSX.Element {
  const [listado, setListado] = useState<ListadoDeIntegraciones>(inicial);
  const [ocupada, setOcupada] = useState<SistemaExterno | "verificacion" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const conectadas = listado.integraciones.filter((i) => i.estado === "CONECTADO").length;

  async function verificar(): Promise<void> {
    setOcupada("verificacion");
    setError(null);
    try {
      setListado(await verificarIntegraciones());
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo verificar");
    } finally {
      setOcupada(null);
    }
  }

  async function conectar(sistema: SistemaExterno): Promise<void> {
    setOcupada(sistema);
    setError(null);
    try {
      await conectarIntegracion(sistema, CREDENCIAL_SIMULADA);
      setListado(await listarIntegraciones());
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo conectar");
    } finally {
      setOcupada(null);
    }
  }

  return (
    <section>
      <header className="int-encabezado">
        <div>
          <p className="int-encabezado__resumen">
            {conectadas} de {listado.integraciones.length} conectados
          </p>
          <p className="int-encabezado__marca">
            Última verificación: {formatearFechaHora(listado.verificado_en)}
          </p>
        </div>
        <Button
          onClick={() => {
            void verificar();
          }}
          disabled={ocupada !== null}
        >
          {ocupada === "verificacion" ? "Verificando…" : "Verificar estado"}
        </Button>
      </header>

      {error !== null ? <Alert tono="error">{error}</Alert> : null}

      <div className="int-grid">
        {listado.integraciones.map((integracion: Integracion) => (
          <TarjetaDeIntegracion
            key={integracion.sistema}
            sistema={integracion.sistema}
            estado={integracion.estado}
            detalle={integracion.detalle}
            ambiente={integracion.ambiente}
            configurada={integracion.configurada}
            conectable={CONECTABLES.includes(integracion.sistema)}
            puedeConectar={puedeConectar}
            ocupada={ocupada !== null}
            onConectar={(sistema) => {
              void conectar(sistema);
            }}
          />
        ))}
      </div>
    </section>
  );
}
