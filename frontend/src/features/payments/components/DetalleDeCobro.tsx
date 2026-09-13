/**
 * PAN-COB-02 — Cobros · Detalle (HU-E6-02, HU-E6-04, HU-E6-05).
 *
 * Todo lo que RN-01 pide —monto, cliente, link y el historial de recordatorios con su estado
 * de entrega— más las dos acciones que cambian el estado.
 *
 * **El reembolso sólo aparece para el Administrador** (HU-E6-05 RN-05) y sólo sobre un cobro
 * pagado (RN-01). Esconder el botón es una cortesía: el caso de uso lo rechaza igual, que es
 * lo que enseñó PRU-09.
 *
 * **La cancelación pide el motivo antes de confirmar**, con el largo mínimo puesto en el
 * botón. La validación de verdad es del backend, porque dos pestañas pasan esta.
 */

"use client";

import { useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Campo,
  Card,
  Modal,
  Tabla,
  formatearFecha,
  formatearFechaHora,
  formatearNumero,
} from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  LARGO_MINIMO_DE_MOTIVO,
  MENSAJE_LINK_COPIADO,
  MENSAJE_MOTIVO_CORTO,
  cancelarCobro,
  copiarLink,
  reembolsarCobro,
  tonoDeEstado,
  verCobro,
} from "../api/cobro";
import type { DetalleDeCobro as Detalle, Recordatorio } from "../api/cobro";

export interface PropsDeDetalleDeCobro {
  readonly inicial: Detalle;
  /** Administrador y Operador cancelan (HU-E6-04). */
  readonly puedeGestionar: boolean;
  /** Sólo el Administrador reembolsa (HU-E6-05 RN-05). */
  readonly puedeReembolsar: boolean;
}

const COLUMNAS: readonly Columna<Recordatorio>[] = [
  { clave: "paso", titulo: "Paso", celda: (fila) => String(fila.paso) },
  { clave: "canal", titulo: "Canal", celda: (fila) => fila.canal },
  {
    clave: "enviado",
    titulo: "Enviado",
    celda: (fila) => formatearFechaHora(fila.enviado_en),
  },
  {
    clave: "entrega",
    titulo: "Entrega",
    // «Programado» y no un guión: la ausencia de fecha significa que todavía no salió, y eso
    // es distinto de que haya salido y no sepamos qué pasó.
    celda: (fila) => fila.estado_entrega ?? "Programado",
  },
];

export function DetalleDeCobro({
  inicial,
  puedeGestionar,
  puedeReembolsar,
}: PropsDeDetalleDeCobro): JSX.Element {
  const [cobro, setCobro] = useState<Detalle>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cancelando, setCancelando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [reembolsando, setReembolsando] = useState(false);
  const [montoAReembolsar, setMontoAReembolsar] = useState(inicial.monto);
  const [trabajando, setTrabajando] = useState(false);

  async function recargar(): Promise<void> {
    setCobro(await verCobro(cobro.id));
  }

  function mensajeDe(fallo: unknown, porDefecto: string): string {
    return fallo instanceof ErrorDeCobro ? fallo.message : porDefecto;
  }

  async function copiar(): Promise<void> {
    if (cobro.url_de_pago === null) {
      return;
    }
    const copiado = await copiarLink(cobro.url_de_pago);
    // Se dice cuando **no** se pudo: alguien que apretó «copiar» y no ve nada asume que copió.
    setAviso(copiado ? MENSAJE_LINK_COPIADO : "No se pudo copiar. Copialo a mano desde el link.");
  }

  async function cancelar(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await cancelarCobro(cobro.id, motivo);
      setCancelando(false);
      await recargar();
    } catch (fallo) {
      setError(mensajeDe(fallo, "No se pudo cancelar el cobro."));
    } finally {
      setTrabajando(false);
    }
  }

  async function reembolsar(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await reembolsarCobro(cobro.id, montoAReembolsar);
      setReembolsando(false);
      await recargar();
    } catch (fallo) {
      // «MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.» llega por
      // acá, con las palabras del backend.
      setError(mensajeDe(fallo, "No se pudo reembolsar el cobro."));
    } finally {
      setTrabajando(false);
    }
  }

  const motivoCorto = motivo.trim().length < LARGO_MINIMO_DE_MOTIVO;

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      {cobro.reembolso_en_proceso && (
        // Decisión D27: el cobro sigue `APROBADO` y esto sale de `reembolso_solicitado_en`.
        <Alert tono="advertencia" titulo="Reembolso en proceso">
          Le pedimos el reembolso a MercadoPago. Cuando conteste, el cobro va a quedar como
          reembolsado o va a volver a figurar como pagado.
        </Alert>
      )}

      <div className="fac-detalle">
        <Card titulo="Cobro">
          <dl className="fac-datos">
            <dt>Concepto</dt>
            <dd>{cobro.descripcion}</dd>
            <dt>Monto</dt>
            <dd>$ {formatearNumero(cobro.monto)}</dd>
            <dt>Estado</dt>
            <dd>
              <Badge estado={tonoDeEstado(cobro.estado)}>{ETIQUETAS_DE_ESTADO[cobro.estado]}</Badge>
            </dd>
            <dt>Vence</dt>
            <dd>{formatearFecha(cobro.vence_el)}</dd>
            <dt>Pagado</dt>
            <dd>{formatearFechaHora(cobro.pagado_en)}</dd>
            {cobro.monto_reembolsado !== null && (
              <>
                <dt>Reembolsado</dt>
                <dd>$ {formatearNumero(cobro.monto_reembolsado)}</dd>
              </>
            )}
            {cobro.motivo_de_cancelacion !== null && (
              <>
                <dt>Motivo de cancelación</dt>
                <dd>{cobro.motivo_de_cancelacion}</dd>
              </>
            )}
          </dl>
        </Card>

        <Card titulo="Link de pago">
          {cobro.tiene_link_activo && cobro.url_de_pago !== null ? (
            <>
              <p className="fac-mono">{cobro.url_de_pago}</p>
              <div className="fac-acciones">
                <Button variante="secundario" onClick={() => void copiar()}>
                  Copiar link
                </Button>
              </div>
            </>
          ) : (
            <p className="dm-intro">
              Este cobro no tiene un link activo. Un cobro pagado, cancelado o reembolsado ya no se
              puede pagar.
            </p>
          )}
        </Card>
      </div>

      <Tabla
        titulo="Recordatorios"
        columnas={COLUMNAS}
        filas={cobro.recordatorios}
        claveDeFila={(fila) => fila.id}
        vacia="Todavía no se envió ningún recordatorio para este cobro."
      />

      <div className="fac-acciones">
        {puedeGestionar && cobro.tiene_link_activo && (
          <Button variante="destructivo" onClick={() => setCancelando(true)}>
            Cancelar cobro
          </Button>
        )}
        {puedeReembolsar && cobro.estado === "APROBADO" && !cobro.reembolso_en_proceso && (
          <Button variante="secundario" onClick={() => setReembolsando(true)}>
            Reembolsar
          </Button>
        )}
      </div>

      <Modal abierto={cancelando} titulo="Cancelar cobro" onCerrar={() => setCancelando(false)}>
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void cancelar();
          }}
        >
          <p className="dm-intro">
            Se da de baja la deuda, se invalida el link y se detienen los recordatorios. Queda
            registrado con el motivo.
          </p>
          <Campo
            id="cobro-motivo"
            etiqueta="Motivo"
            error={motivo !== "" && motivoCorto ? MENSAJE_MOTIVO_CORTO : undefined}
            value={motivo}
            onChange={(evento) => setMotivo(evento.target.value)}
          />
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setCancelando(false)}>
              Volver
            </Button>
            <Button type="submit" disabled={motivoCorto} cargando={trabajando}>
              Confirmar cancelación
            </Button>
          </div>
        </form>
      </Modal>

      <Modal abierto={reembolsando} titulo="Reembolsar" onCerrar={() => setReembolsando(false)}>
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void reembolsar();
          }}
        >
          <p className="dm-intro">
            Se le pide el reembolso a MercadoPago. Hasta que conteste, el cobro sigue figurando como
            pagado.
          </p>
          <Campo
            id="cobro-reembolso"
            etiqueta="Monto a reembolsar"
            mono
            ayuda={`No puede superar $ ${formatearNumero(cobro.monto)}.`}
            value={montoAReembolsar}
            onChange={(evento) => setMontoAReembolsar(evento.target.value)}
          />
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setReembolsando(false)}>
              Volver
            </Button>
            <Button type="submit" cargando={trabajando}>
              Confirmar reembolso
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
