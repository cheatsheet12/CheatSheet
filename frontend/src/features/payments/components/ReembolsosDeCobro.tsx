/**
 * Los reembolsos de un cobro en PAN-COB-02 (HU-E6-05): el historial, «Registrar reembolso»,
 * «Corregir», «Actualizar estado» y el aviso de nota de crédito.
 *
 * Vive fuera de `DetalleDeCobro.tsx` para que ese archivo no pase de las 400 líneas y porque es
 * un bloque con una sola razón de cambiar: cómo se ve y se opera la plata devuelta.
 *
 * **Cada reembolso es una fila que no se edita ni se borra.** Un error de carga se corrige con
 * «Corregir», que agrega una fila **negativa** visible (RN-08) y puede bajar el estado del cobro.
 * Solo se corrigen las filas manuales: las de MercadoPago las informa MercadoPago, que es la
 * fuente de verdad.
 *
 * **«Registrar reembolso» es de las transferencias** (RN-07): una transferencia no tiene una API
 * a la que pedirle nada, así que el administrador declara la devolución a mano. Un cobro pagado
 * por link se reembolsa por MercadoPago (el botón «Reembolsar» de la pantalla).
 *
 * Todo es del Administrador (RN-05); Operador y Solo Lectura ven el historial y ninguna acción.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Campo,
  Modal,
  SelectorDeFecha,
  formatearFecha,
  formatearNumero,
} from "@/shared";

import {
  ETIQUETAS_DE_ORIGEN,
  ErrorDeCobro,
  MENSAJE_NOTA_DE_CREDITO,
  actualizarReembolso,
  corregirReembolso,
  registrarReembolso,
  tieneReembolsos,
} from "../api/cobro";
import type { DetalleDeCobro as Detalle, Reembolso } from "../api/cobro";

function mensajeDe(fallo: unknown, porDefecto: string): string {
  return fallo instanceof ErrorDeCobro ? fallo.message : porDefecto;
}

export interface PropsDeAvisosDeReembolso {
  readonly cobro: Detalle;
  /** Sólo el Administrador actualiza el estado (HU-E6-05 RN-05). */
  readonly puedeReembolsar: boolean;
  /** Vuelve a pedir el detalle al backend. */
  readonly alActualizar: () => Promise<void>;
  readonly alFallar: (mensaje: string) => void;
}

/**
 * Lo que hay que ver arriba de todo: un reembolso en proceso y la nota de crédito que corresponde.
 *
 * «Reembolso en proceso» (decisión D27) **no es un estado**: el cobro sigue como estaba y esto
 * sale de la solicitud en vuelo. Si MercadoPago no contestó, «Actualizar estado» lo destraba.
 */
export function AvisosDeReembolso({
  cobro,
  puedeReembolsar,
  alActualizar,
  alFallar,
}: PropsDeAvisosDeReembolso): JSX.Element {
  const [actualizando, setActualizando] = useState(false);

  async function actualizar(): Promise<void> {
    setActualizando(true);
    try {
      await actualizarReembolso(cobro.id);
      await alActualizar();
    } catch (fallo) {
      alFallar(mensajeDe(fallo, "No se pudo actualizar el estado del reembolso."));
    } finally {
      setActualizando(false);
    }
  }

  return (
    <>
      {cobro.reembolso_en_proceso && (
        <Alert tono="advertencia" titulo="Reembolso en proceso">
          <p>
            Le pedimos a MercadoPago que devuelva
            {cobro.reembolso_en_proceso_monto !== null &&
              ` $ ${formatearNumero(cobro.reembolso_en_proceso_monto)}`}
            . Todavía no confirmó: mientras tanto el cobro sigue como estaba y no admite otro
            reembolso.
          </p>
          {puedeReembolsar && (
            <Button variante="secundario" cargando={actualizando} onClick={() => void actualizar()}>
              Actualizar estado
            </Button>
          )}
        </Alert>
      )}
      {cobro.comprobante_id !== null && tieneReembolsos(cobro) && (
        // RN-09 y D89: se avisa y se ofrece el camino; la nota de crédito no se emite sola.
        <Alert tono="advertencia" titulo="Nota de crédito">
          <p>{MENSAJE_NOTA_DE_CREDITO}</p>
          <p>
            <Link href={`/facturacion/${cobro.comprobante_id}/anular`}>Emitir nota de crédito</Link>
          </p>
        </Alert>
      )}
    </>
  );
}

export interface PropsDeReembolsosDeCobro {
  readonly cobro: Detalle;
  readonly puedeReembolsar: boolean;
  /** Vuelve a pedir el detalle después de registrar o corregir. */
  readonly alCambiar: () => Promise<void>;
}

const ADMITEN_REEMBOLSO: readonly Detalle["estado"][] = ["APROBADO", "REEMBOLSADO_PARCIAL"];

export function ReembolsosDeCobro({
  cobro,
  puedeReembolsar,
  alCambiar,
}: PropsDeReembolsosDeCobro): JSX.Element | null {
  const [registrando, setRegistrando] = useState(false);
  const [corrigiendo, setCorrigiendo] = useState<Reembolso | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [monto, setMonto] = useState("");
  const [fecha, setFecha] = useState("");
  const [referencia, setReferencia] = useState("");
  const [motivo, setMotivo] = useState("");

  const puedeRegistrar =
    puedeReembolsar &&
    cobro.medio_de_pago === "TRANSFERENCIA" &&
    ADMITEN_REEMBOLSO.includes(cobro.estado);

  if (cobro.reembolsos.length === 0 && !puedeRegistrar) {
    return null;
  }

  function abrirRegistro(): void {
    setError(null);
    setMonto("");
    setFecha("");
    setReferencia("");
    setMotivo("");
    setRegistrando(true);
  }

  function abrirCorreccion(fila: Reembolso): void {
    setError(null);
    setMotivo("");
    setCorrigiendo(fila);
  }

  async function registrar(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await registrarReembolso(cobro.id, { monto, fecha, referencia, motivo });
      setRegistrando(false);
      await alCambiar();
    } catch (fallo) {
      setError(mensajeDe(fallo, "No se pudo registrar el reembolso."));
    } finally {
      setTrabajando(false);
    }
  }

  async function corregir(): Promise<void> {
    if (corrigiendo === null) {
      return;
    }
    setError(null);
    setTrabajando(true);
    try {
      await corregirReembolso(cobro.id, corrigiendo.id, motivo);
      setCorrigiendo(null);
      await alCambiar();
    } catch (fallo) {
      setError(mensajeDe(fallo, "No se pudo corregir el reembolso."));
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <section className="cob-tarjeta">
      <p className="cob-rotulo">Reembolsos</p>
      {cobro.reembolsos.length === 0 ? (
        <p className="cob-vacio">Todavía no se registró ningún reembolso de este cobro.</p>
      ) : (
        <ul className="cob-reembolsos">
          {cobro.reembolsos.map((fila) => (
            <li key={fila.id} className="cob-reembolso">
              <span className="cob-reembolso__monto">$ {formatearNumero(fila.monto)}</span>
              <span className="cob-reembolso__detalle">
                {formatearFecha(fila.fecha_devolucion)} ·{" "}
                <span className="cob-reembolso__origen">{ETIQUETAS_DE_ORIGEN[fila.origen]}</span>
                {fila.referencia !== null && ` · ${fila.referencia}`}
              </span>
              {fila.motivo !== null && <span className="cob-reembolso__motivo">{fila.motivo}</span>}
              {fila.corrige_a !== null && <Badge estado="atencion">Corrección</Badge>}
              {fila.corregido && <Badge estado="pendiente">Corregido</Badge>}
              {puedeReembolsar &&
                fila.origen === "MANUAL" &&
                fila.corrige_a === null &&
                !fila.corregido && (
                  <Button variante="secundario" onClick={() => abrirCorreccion(fila)}>
                    Corregir
                  </Button>
                )}
            </li>
          ))}
        </ul>
      )}

      {puedeRegistrar && (
        <div className="cob-acciones">
          <Button variante="secundario" onClick={abrirRegistro}>
            Registrar reembolso
          </Button>
        </div>
      )}

      <Modal
        abierto={registrando}
        titulo="Registrar reembolso"
        onCerrar={() => setRegistrando(false)}
      >
        <form
          className="dm-formulario cob-modal"
          onSubmit={(evento) => {
            evento.preventDefault();
            void registrar();
          }}
        >
          <p className="dm-intro">
            Declará una devolución hecha por transferencia. No se le pide nada a MercadoPago: queda
            registrada con su fecha, su referencia y quién la cargó.
          </p>
          {error !== null && (
            <Alert tono="error" titulo="No se pudo completar">
              {error}
            </Alert>
          )}
          <Campo
            id="reembolso-monto"
            etiqueta="Monto devuelto"
            mono
            value={monto}
            onChange={(evento) => setMonto(evento.target.value)}
          />
          <SelectorDeFecha
            id="reembolso-fecha"
            etiqueta="Fecha de devolución"
            value={fecha}
            alCambiar={setFecha}
          />
          <Campo
            id="reembolso-referencia"
            etiqueta="Referencia (opcional)"
            ayuda="Número de operación o comprobante bancario."
            value={referencia}
            onChange={(evento) => setReferencia(evento.target.value)}
          />
          <Campo
            id="reembolso-motivo"
            etiqueta="Motivo"
            value={motivo}
            onChange={(evento) => setMotivo(evento.target.value)}
          />
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setRegistrando(false)}>
              Volver
            </Button>
            <Button
              type="submit"
              disabled={monto.trim() === "" || fecha === "" || motivo.trim() === ""}
              cargando={trabajando}
            >
              Confirmar registro
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        abierto={corrigiendo !== null}
        titulo="Corregir reembolso"
        onCerrar={() => setCorrigiendo(null)}
      >
        <form
          className="dm-formulario cob-modal"
          onSubmit={(evento) => {
            evento.preventDefault();
            void corregir();
          }}
        >
          <p className="dm-intro">
            Se agrega una fila negativa que anula la entera
            {corrigiendo !== null && ` ($ ${formatearNumero(corrigiendo.monto)})`}. La original no
            se edita ni se borra, y el estado del cobro se recalcula. Si el monto era otro, registrá
            después uno nuevo.
          </p>
          {error !== null && (
            <Alert tono="error" titulo="No se pudo completar">
              {error}
            </Alert>
          )}
          <Campo
            id="reembolso-correccion"
            etiqueta="Motivo de la corrección"
            value={motivo}
            onChange={(evento) => setMotivo(evento.target.value)}
          />
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setCorrigiendo(null)}>
              Volver
            </Button>
            <Button type="submit" disabled={motivo.trim() === ""} cargando={trabajando}>
              Confirmar corrección
            </Button>
          </div>
        </form>
      </Modal>
    </section>
  );
}
