/**
 * PAN-COB-02 — Cobros · Detalle (HU-E6-02, HU-E6-04, HU-E6-05).
 *
 * Todo lo que RN-01 pide —monto, cliente, link y el historial de recordatorios con su estado
 * de entrega— más las dos acciones que cambian el estado.
 *
 * **El prototipo lo dibuja como panel lateral y acá es una página.** La decisión es de la
 * ruta y no de este archivo: es la pantalla que alguien deja abierta mientras habla por
 * teléfono y la que manda por mensaje interno, y un cajón no tiene URL. La maqueta sí es la
 * del prototipo: encabezado, caja del monto, pares clave/valor y la cadena de recordatorios
 * como línea de tiempo.
 *
 * **El reembolso sólo aparece para el Administrador** (HU-E6-05 RN-05) y sólo sobre un cobro
 * pagado (RN-01), por link, que todavía tenga algo por devolver. Puede ser **parcial** y repetirse
 * hasta completar el monto. Esconder el botón es una cortesía: el caso de uso lo rechaza igual,
 * que es lo que enseñó PRU-09. El historial, «Registrar reembolso» (transferencias), «Corregir»
 * y «Actualizar estado» viven en `ReembolsosDeCobro.tsx`.
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
  Desplegable,
  Modal,
  formatearFecha,
  formatearFechaHora,
  formatearNumero,
} from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ETIQUETAS_DE_MEDIO,
  ErrorDeCobro,
  LARGO_MINIMO_DE_MOTIVO,
  MENSAJE_LINK_COPIADO,
  MENSAJE_MOTIVO_CORTO,
  MENSAJE_PAGO_HUERFANO,
  cancelarCobro,
  copiarLink,
  pendienteDeReembolso,
  reembolsarCobro,
  tieneReembolsos,
  tonoDeEstado,
  verCobro,
} from "../api/cobro";
import type { DetalleDeCobro as Detalle } from "../api/cobro";
import { HitoDeRecordatorio } from "./HitoDeRecordatorio";
import { inicialesDe, referenciaDeCobro, tonoDeCaja, varianteDeAvatar } from "./presentacion";
import { AvisosDeReembolso, ReembolsosDeCobro } from "./ReembolsosDeCobro";

export interface PropsDeDetalleDeCobro {
  readonly inicial: Detalle;
  /** Administrador y Operador cancelan (HU-E6-04). */
  readonly puedeGestionar: boolean;
  /** Sólo el Administrador reembolsa (HU-E6-05 RN-05). */
  readonly puedeReembolsar: boolean;
}

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
  const [montoAReembolsar, setMontoAReembolsar] = useState(pendienteDeReembolso(inicial));
  const [trabajando, setTrabajando] = useState(false);
  const [copiando, setCopiando] = useState(false);

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
    setCopiando(true);
    const copiado = await copiarLink(cobro.url_de_pago);
    setCopiando(false);
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

  /** El pendiente precargado: lo que falta devolver, no el monto entero (puede ser parcial). */
  function abrirReembolso(): void {
    setError(null);
    setMontoAReembolsar(pendienteDeReembolso(cobro));
    setReembolsando(true);
  }

  const motivoCorto = motivo.trim().length < LARGO_MINIMO_DE_MOTIVO;

  return (
    <>
      {/* Con un modal abierto el error va adentro del modal (más abajo): si se pintara acá,
          el overlay del modal lo taparía y el usuario no vería por qué falló la acción. */}
      {error !== null && !cancelando && !reembolsando && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <AvisosDeReembolso
        cobro={cobro}
        puedeReembolsar={puedeReembolsar}
        alActualizar={recargar}
        alFallar={setError}
      />

      <div className="cob-detalle">
        <div>
          <section className="cob-tarjeta">
            <header className="cob-cabecera">
              <span className={`cob-avatar cob-avatar--${varianteDeAvatar(cobro.id)}`} aria-hidden>
                {inicialesDe(cobro.descripcion)}
              </span>
              <div>
                <p className="cob-cabecera__rotulo">
                  Detalle de cobro · {referenciaDeCobro(cobro.id)}
                </p>
                <h2 className="cob-cabecera__titulo">{cobro.descripcion}</h2>
              </div>
            </header>

            {/* El monto y el estado en la misma caja: el número es lo que alguien busca y el
                estado es lo que decide qué hacer con él. */}
            <div className={`cob-monto cob-monto--${tonoDeCaja(cobro.estado)}`}>
              <div>
                <p className="cob-monto__rotulo">Monto</p>
                <p className="cob-monto__valor">$ {formatearNumero(cobro.monto)}</p>
              </div>
              <div className="cob-monto__estado">
                <Badge estado={tonoDeEstado(cobro.estado)}>
                  {ETIQUETAS_DE_ESTADO[cobro.estado]}
                </Badge>
                <p className="cob-monto__nota">Vence el {formatearFecha(cobro.vence_el)}</p>
              </div>
            </div>

            <p className="cob-rotulo">Detalle del cobro</p>
            <dl className="cob-kv">
              <div className="cob-kv__par">
                <dt>Concepto</dt>
                <dd>{cobro.descripcion}</dd>
              </div>
              {/* «Referencia» es el código derivado del id del cobro. «Operación» quedó para el
                  número de la transferencia: dos cosas distintas no se llaman igual. */}
              <div className="cob-kv__par">
                <dt>Referencia</dt>
                <dd className="cob-mono">{referenciaDeCobro(cobro.id)}</dd>
              </div>
              <div className="cob-kv__par">
                <dt>Medio de pago</dt>
                <dd>{ETIQUETAS_DE_MEDIO[cobro.medio_de_pago]}</dd>
              </div>
              <div className="cob-kv__par">
                <dt>Fecha de pago</dt>
                <dd>
                  {formatearFechaHora(cobro.fecha_pago)}
                  {cobro.fecha_pago !== null && cobro.fecha_pago_aproximada && " (aproximada)"}
                </dd>
              </div>
              {cobro.medio_de_pago === "TRANSFERENCIA" && cobro.numero_de_operacion !== null && (
                <div className="cob-kv__par">
                  <dt>N.º de operación</dt>
                  <dd className="cob-mono">{cobro.numero_de_operacion}</dd>
                </div>
              )}
              {tieneReembolsos(cobro) && (
                <div className="cob-kv__par">
                  <dt>Reembolsado</dt>
                  <dd>$ {formatearNumero(cobro.monto_reembolsado)}</dd>
                </div>
              )}
              {cobro.motivo_de_cancelacion !== null && (
                <div className="cob-kv__par">
                  <dt>Motivo de cancelación</dt>
                  <dd className="cob-kv__alerta">{cobro.motivo_de_cancelacion}</dd>
                </div>
              )}
              {cobro.tiene_pago_huerfano && (
                <div className="cob-kv__par">
                  <dt>Pago sobre cobro cancelado</dt>
                  <dd className="cob-kv__alerta">{MENSAJE_PAGO_HUERFANO}</dd>
                </div>
              )}
            </dl>

            <p className="cob-rotulo">
              Link de pago — MercadoPago
              {cobro.tiene_link_activo && <Badge estado="ok">Activo</Badge>}
            </p>
            {cobro.tiene_link_activo && cobro.url_de_pago !== null ? (
              <div className="cob-link">
                <span className="cob-link__marca" aria-hidden>
                  MP
                </span>
                <span className="cob-link__url">{cobro.url_de_pago}</span>
                <Button variante="secundario" cargando={copiando} onClick={() => void copiar()}>
                  Copiar link
                </Button>
              </div>
            ) : (
              <p className="cob-vacio">
                Este cobro no tiene un link activo. Un cobro pagado, cancelado o reembolsado ya no
                se puede pagar.
              </p>
            )}
          </section>

          <ReembolsosDeCobro cobro={cobro} puedeReembolsar={puedeReembolsar} alCambiar={recargar} />
        </div>

        <section className="cob-tarjeta">
          <h2 className="cob-cabecera__titulo">Recordatorios</h2>
          <Desplegable
            titulo="Cadena automática"
            variante="simple"
            abiertoAlInicio
            resumen={cobro.recordatorios.length === 0 ? undefined : cobro.recordatorios.length}
          >
            {cobro.recordatorios.length === 0 ? (
              <p className="cob-vacio">Todavía no se envió ningún recordatorio para este cobro.</p>
            ) : (
              <ol className="cob-timeline">
                {cobro.recordatorios.map((recordatorio) => (
                  <HitoDeRecordatorio key={recordatorio.id} recordatorio={recordatorio} />
                ))}
              </ol>
            )}
          </Desplegable>

          {(puedeGestionar || puedeReembolsar) && (
            <div className="cob-acciones">
              {puedeGestionar && cobro.tiene_link_activo && (
                <Button
                  variante="destructivo"
                  onClick={() => {
                    setError(null);
                    setCancelando(true);
                  }}
                >
                  Cancelar cobro
                </Button>
              )}
              {puedeReembolsar &&
                cobro.medio_de_pago === "LINK_MERCADOPAGO" &&
                (cobro.estado === "APROBADO" || cobro.estado === "REEMBOLSADO_PARCIAL") &&
                !cobro.reembolso_en_proceso && (
                  <Button variante="secundario" onClick={abrirReembolso}>
                    Reembolsar
                  </Button>
                )}
            </div>
          )}
        </section>
      </div>

      <Modal abierto={cancelando} titulo="Cancelar cobro" onCerrar={() => setCancelando(false)}>
        <form
          className="dm-formulario cob-modal"
          onSubmit={(evento) => {
            evento.preventDefault();
            void cancelar();
          }}
        >
          {error !== null && <Alert tono="error">{error}</Alert>}
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
          className="dm-formulario cob-modal"
          onSubmit={(evento) => {
            evento.preventDefault();
            void reembolsar();
          }}
        >
          {error !== null && <Alert tono="error">{error}</Alert>}
          <p className="dm-intro">
            Se le pide el reembolso a MercadoPago. Puede ser parcial y se puede repetir hasta
            completar el monto. Hasta que conteste, el estado del cobro no cambia.
          </p>
          <Campo
            id="cobro-reembolso"
            etiqueta="Monto a reembolsar"
            mono
            ayuda={`No puede superar $ ${formatearNumero(pendienteDeReembolso(cobro))}, lo que falta devolver.`}
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
