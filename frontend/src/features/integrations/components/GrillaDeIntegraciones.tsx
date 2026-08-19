/**
 * PAN-CFG-INT — the four cards, the live check and the consolidated timestamp.
 *
 * HU-E2-05 in one component. The initial state is rendered by the server page; this takes
 * over from there so the check can update the table in place.
 *
 * **Two connection paths, and the split is temporary.** WhatsApp opens a real form
 * (HU-E2-03): its provider exists, so it collects what Meta needs. ARCA and MercadoPago
 * still send a placeholder credential to their stand-ins, because their units have not
 * landed — `conexion-arca` and `conexion-mercadopago` each replace one branch of
 * `conectar` below with their own flow, and this comment shrinks by a paragraph.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Modal, formatearFechaHora } from "@/shared";

import { conectarIntegracion, listarIntegraciones, verificarIntegraciones } from "../api/cliente";
import type {
  Integracion,
  ListadoDeIntegraciones,
  ParametrosDeConexion,
  SistemaExterno,
} from "../api/cliente";
import { FormularioDeWhatsApp } from "./FormularioDeWhatsApp";
import { TarjetaDeIntegracion } from "./TarjetaDeIntegracion";

/** Google Sheets and Excel Online are on the screen; their connection is epic 4. */
const CONECTABLES: readonly SistemaExterno[] = ["ARCA", "MERCADOPAGO", "WHATSAPP"];

/** Stands in for the certificate a real ARCA or MercadoPago flow will collect. */
const CREDENCIAL_SIMULADA = btoa("credencial-simulada");

/** `btoa` is byte-oriented; a token with a non-ASCII character would corrupt without this. */
function aBase64(texto: string): string {
  const bytes = new TextEncoder().encode(texto);
  return btoa(String.fromCharCode(...bytes));
}

export interface PropsDeGrilla {
  readonly inicial: ListadoDeIntegraciones;
  readonly puedeConectar: boolean;
}

export function GrillaDeIntegraciones({ inicial, puedeConectar }: PropsDeGrilla): JSX.Element {
  const [listado, setListado] = useState<ListadoDeIntegraciones>(inicial);
  const [ocupada, setOcupada] = useState<SistemaExterno | "verificacion" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formulario, setFormulario] = useState<SistemaExterno | null>(null);

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

  async function enviarConexion(
    sistema: SistemaExterno,
    contenido: string,
    parametros: ParametrosDeConexion,
  ): Promise<void> {
    setOcupada(sistema);
    setError(null);
    try {
      await conectarIntegracion(sistema, contenido, parametros);
      setListado(await listarIntegraciones());
      setFormulario(null);
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo conectar");
    } finally {
      setOcupada(null);
    }
  }

  function conectar(sistema: SistemaExterno): void {
    if (sistema === "WHATSAPP") {
      // Meta needs three specific fields; everything else is still a stand-in.
      setError(null);
      setFormulario(sistema);
      return;
    }
    void enviarConexion(sistema, CREDENCIAL_SIMULADA, {});
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
            etiqueta={integracion.etiqueta}
            configurada={integracion.configurada}
            conectable={CONECTABLES.includes(integracion.sistema)}
            puedeConectar={puedeConectar}
            ocupada={ocupada !== null}
            onConectar={conectar}
          />
        ))}
      </div>

      <Modal
        abierto={formulario === "WHATSAPP"}
        titulo="Conectar WhatsApp Business"
        onCerrar={() => {
          setFormulario(null);
        }}
      >
        <FormularioDeWhatsApp
          enviando={ocupada === "WHATSAPP"}
          onEnviar={(token, parametros) => {
            void enviarConexion("WHATSAPP", aBase64(token), parametros);
          }}
          onCancelar={() => {
            setFormulario(null);
          }}
        />
      </Modal>
    </section>
  );
}
