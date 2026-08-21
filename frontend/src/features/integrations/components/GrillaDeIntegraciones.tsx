/**
 * PAN-CFG-INT — the four cards, the live check and the consolidated timestamp.
 *
 * HU-E2-05 in one component. The initial state is rendered by the server page; this takes
 * over from there so the check can update the table in place.
 *
 * **Each of the three connectable systems has its own way in, and there is no placeholder
 * left.** WhatsApp asks for the three fields Meta needs (HU-E2-03); ARCA asks for the two
 * files of the fiscal certificate (HU-E2-01); MercadoPago leaves the app entirely and
 * comes back with an authorization code (HU-E2-02).
 *
 * **The return leg is why this component reads the query string.** MercadoPago redirects
 * the browser back to this very screen, so `?code&state` is how the second half of the
 * flow arrives. It is exchanged once — a ref guards against React running the effect
 * twice in development — and then wiped from the URL with `replaceState`, because a
 * reload that re-posted a spent code would show an error that means nothing to whoever
 * reads it.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { Alert, Button, Modal, formatearFechaHora } from "@/shared";

import {
  canjearAutorizacion,
  conectarIntegracion,
  iniciarAutorizacion,
  listarIntegraciones,
  verificarIntegraciones,
} from "../api/cliente";
import type {
  Integracion,
  ListadoDeIntegraciones,
  ParametrosDeConexion,
  SistemaExterno,
} from "../api/cliente";
import { FormularioDeArca } from "./FormularioDeArca";
import { FormularioDeWhatsApp } from "./FormularioDeWhatsApp";
import { TarjetaDeIntegracion } from "./TarjetaDeIntegracion";

/** Google Sheets and Excel Online are on the screen; their connection is epic 4. */
const CONECTABLES: readonly SistemaExterno[] = ["ARCA", "MERCADOPAGO", "WHATSAPP"];

/** Systems that collect their credential through a form of their own. */
const CON_FORMULARIO: readonly SistemaExterno[] = ["WHATSAPP", "ARCA"];

/** Systems that are connected by leaving the app and coming back (OAuth2). */
const CON_AUTORIZACION: readonly SistemaExterno[] = ["MERCADOPAGO"];

/**
 * What the provider says when the person pressed "Cancel" on its screen. It is not a
 * failure of ours and the message says so.
 */
const RECHAZO_DEL_USUARIO = "access_denied";

/** `btoa` is byte-oriented; a token with a non-ASCII character would corrupt without this. */
function aBase64(texto: string): string {
  const bytes = new TextEncoder().encode(texto);
  return btoa(String.fromCharCode(...bytes));
}

/** What the provider left in the query string when it sent the browser back. */
export interface RetornoDeAutorizacion {
  readonly sistema: SistemaExterno;
  readonly codigo: string | null;
  readonly estado: string | null;
  readonly error: string | null;
}

export interface PropsDeGrilla {
  readonly inicial: ListadoDeIntegraciones;
  readonly puedeConectar: boolean;
  /** Absent on an ordinary visit; present only on the way back from the provider. */
  readonly retorno?: RetornoDeAutorizacion | null;
}

/**
 * Wipes `?code&state` without reloading. A code is single-use, so leaving it in the
 * address bar leaves a URL that fails if anyone shares it or presses F5.
 */
function limpiarLaUrl(): void {
  window.history.replaceState(null, "", window.location.pathname);
}

export function GrillaDeIntegraciones({
  inicial,
  puedeConectar,
  retorno = null,
}: PropsDeGrilla): JSX.Element {
  const [listado, setListado] = useState<ListadoDeIntegraciones>(inicial);
  const [ocupada, setOcupada] = useState<SistemaExterno | "verificacion" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formulario, setFormulario] = useState<SistemaExterno | null>(null);
  //: Lo que el padrón de ARCA encontró al conectar. No se persiste: se recalcula cada
  //: vez que alguien mira los datos de la empresa, así que vive lo que dura la pantalla.
  const [avisoFiscal, setAvisoFiscal] = useState<string | null>(null);

  const conectadas = listado.integraciones.filter((i) => i.estado === "CONECTADO").length;
  //: One exchange per return, even if the effect runs twice — which it does in
  //: development. A spent `state` cannot be spent again, so the second attempt would
  //: report a failure for a connection that actually worked.
  const canjeado = useRef(false);

  useEffect(() => {
    if (retorno === null || canjeado.current) {
      return;
    }
    canjeado.current = true;
    limpiarLaUrl();
    if (retorno.error !== null) {
      setError(
        retorno.error === RECHAZO_DEL_USUARIO
          ? "No autorizaste el acceso, así que la cuenta no quedó conectada."
          : "El proveedor no completó la autorización. Probá de nuevo.",
      );
      return;
    }
    const { sistema, codigo, estado } = retorno;
    if (codigo === null || estado === null) {
      return;
    }
    void (async () => {
      setOcupada(sistema);
      try {
        await canjearAutorizacion(sistema, codigo, estado);
        setListado(await listarIntegraciones());
      } catch (fallo) {
        setError(fallo instanceof Error ? fallo.message : "No se pudo conectar");
      } finally {
        setOcupada(null);
      }
    })();
  }, [retorno]);

  async function autorizar(sistema: SistemaExterno): Promise<void> {
    setOcupada(sistema);
    setError(null);
    try {
      const { url } = await iniciarAutorizacion(sistema);
      // Leaves the app. Nothing after this line runs.
      window.location.assign(url);
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo iniciar la conexión");
      setOcupada(null);
    }
  }

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
    setAvisoFiscal(null);
    try {
      const conectada = await conectarIntegracion(sistema, contenido, parametros);
      setAvisoFiscal(conectada.aviso_fiscal ?? null);
      setListado(await listarIntegraciones());
      setFormulario(null);
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo conectar");
    } finally {
      setOcupada(null);
    }
  }

  function conectar(sistema: SistemaExterno): void {
    if (CON_FORMULARIO.includes(sistema)) {
      setError(null);
      setFormulario(sistema);
      return;
    }
    if (CON_AUTORIZACION.includes(sistema)) {
      void autorizar(sistema);
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
      {avisoFiscal !== null ? (
        <Alert tono="advertencia" titulo="Revisá los datos fiscales">
          {avisoFiscal}
        </Alert>
      ) : null}

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

      <Modal
        abierto={formulario === "ARCA"}
        titulo="Conectar ARCA"
        onCerrar={() => {
          setFormulario(null);
        }}
      >
        <FormularioDeArca
          enviando={ocupada === "ARCA"}
          onEnviar={(bundle) => {
            void enviarConexion("ARCA", aBase64(bundle), {});
          }}
          onCancelar={() => {
            setFormulario(null);
          }}
        />
      </Modal>
    </section>
  );
}
