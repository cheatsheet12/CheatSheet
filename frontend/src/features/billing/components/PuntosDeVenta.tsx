/**
 * PAN-FAC-05 — Facturación · Puntos de venta (HU-E5-05).
 *
 * The listing the story's first criterion names — número, descripción y estado — plus the
 * numbering, which the story does not ask for and which is the first thing anybody looks
 * for when ARCA rejects a document for a number out of sequence.
 *
 * **Renglones a ancho completo y no una grilla.** Un punto de venta es una cosa con estado
 * propio y una numeración por tipo que, en una celda de tabla, se parte en tres líneas y
 * desalinea todo. Pero son pocos —los que ARCA habilitó para ese CUIT, y lo normal en una PyME
 * es uno—, y una grilla de un elemento deja una tarjeta de 500 px con 1150 px muertos a la
 * derecha: eso se lee como una pantalla que falló al cargar, no como una empresa con un solo
 * punto de venta. Cada renglón lleva su acción sin necesidad de una columna «Acciones».
 *
 * **The two error sentences are the backend's.** «El punto de venta no está habilitado en
 * ARCA.» and «Ya existe un punto de venta con ese número.» are shown exactly as they
 * arrive; this file never composes them and never pre-empts them with a check of its own.
 * A duplicate check in the browser would lose to a second tab, and an ARCA check here is
 * not possible at all.
 *
 * **Deactivating confirms; activating does not.** Deactivating stops the company
 * invoicing from that point, which is the kind of thing somebody finds out about on a
 * Monday morning. Activating is undone by deactivating, and it re-checks ARCA anyway.
 */

"use client";

import { useState } from "react";

import { Hash, ReceiptText, Store } from "lucide-react";

import { Alert, Badge, Button, Campo, Modal } from "@/shared";

import {
  ErrorDePuntoDeVenta,
  cambiarEstadoDePuntoDeVenta,
  listarPuntosDeVenta,
  registrarPuntoDeVenta,
} from "../api/puntoDeVenta";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import type { ListadoDePuntosDeVenta, PuntoDeVenta, TipoComprobante } from "../api/puntoDeVenta";

export interface PropsDePuntosDeVenta {
  readonly inicial: ListadoDePuntosDeVenta;
  /** Only the Administrador writes here (HU-E5-05's actor). Every role reads. */
  readonly puedeEditar: boolean;
}

function mensajeDe(fallo: unknown, porDefecto: string): string {
  return fallo instanceof ErrorDePuntoDeVenta ? fallo.message : porDefecto;
}

/** Four digits, the way ARCA prints it on the document: `0001-00000123`. */
function formateado(numero: number): string {
  return String(numero).padStart(4, "0");
}

/** Fecha de alta en hora argentina, fija: el servidor y el navegador tienen que dibujar lo mismo. */
function fechaDeAlta(iso: string): string | null {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("es-AR", {
    dateStyle: "long",
    timeZone: "America/Argentina/Buenos_Aires",
  }).format(fecha);
}

/** Los tipos que alguna vez emitieron, con su último número tal cual llega: texto, sin cuentas. */
function numeracionDe(punto: PuntoDeVenta): string[] {
  const entradas = Object.entries(punto.numerador_por_tipo) as [TipoComprobante, number][];
  return entradas.map(([tipo, ultimo]) => `${ETIQUETAS_DE_TIPO[tipo]}: ${ultimo}`);
}

export function PuntosDeVenta({ inicial, puedeEditar }: PropsDePuntosDeVenta): JSX.Element {
  const [listado, setListado] = useState<ListadoDePuntosDeVenta>(inicial);
  const [alta, setAlta] = useState(false);
  const [numero, setNumero] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [errorDeAlta, setErrorDeAlta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function recargar(): Promise<void> {
    setListado(await listarPuntosDeVenta());
  }

  function abrirAlta(): void {
    setNumero("");
    setDescripcion("");
    setErrorDeAlta(null);
    setAlta(true);
  }

  async function registrar(): Promise<void> {
    setErrorDeAlta(null);
    setGuardando(true);
    try {
      // `Number.parseInt` and not `<input type="number">`: what a valid point number is
      // (1 … 99 999) is the backend's rule, and an empty field has to reach it as
      // something it can refuse rather than be silently swallowed here.
      await registrarPuntoDeVenta({
        numero: Number.parseInt(numero, 10),
        descripcion: descripcion.trim() === "" ? null : descripcion.trim(),
      });
      setAlta(false);
      await recargar();
    } catch (fallo) {
      // «El punto de venta no está habilitado en ARCA.» y «Ya existe un punto de venta
      // con ese número.» llegan por acá, tal cual las escribió la historia.
      setErrorDeAlta(mensajeDe(fallo, "No se pudo agregar el punto de venta."));
    } finally {
      setGuardando(false);
    }
  }

  async function cambiarEstado(punto: PuntoDeVenta, activo: boolean): Promise<void> {
    setError(null);
    try {
      await cambiarEstadoDePuntoDeVenta(punto.id, activo);
      await recargar();
    } catch (fallo) {
      // Reactivating re-checks ARCA, so a point blocked at the AFIP after we recorded it
      // surfaces right here rather than on the first rejected invoice.
      setError(mensajeDe(fallo, "No se pudo cambiar el estado del punto de venta."));
    }
  }

  /**
   * La acción de la fila.
   *
   * Texto y no un botón con caja: es el estándar de acción por fila del panel, y un
   * rectángulo con borde rojo por renglón pesa más que el punto de venta que describe.
   *
   * **La confirmación no se relaja.** Sigue siendo el mismo diálogo modal que traía el botón
   * destructivo del catálogo —interrumpe y hay que contestarlo antes de que corra nada—; lo
   * único que cambió es el disparador. Desactivar frena la facturación de una empresa, y eso
   * es algo que alguien descubre un lunes a la mañana.
   */
  function accion(fila: PuntoDeVenta): JSX.Element {
    if (!fila.activo) {
      return (
        <button type="button" className="pdv-accion" onClick={() => void cambiarEstado(fila, true)}>
          Activar
        </button>
      );
    }
    return (
      <button
        type="button"
        className="pdv-accion pdv-accion--baja"
        onClick={() => {
          const aviso = `Vas a desactivar el punto ${formateado(fila.numero)}. No vas a poder emitir comprobantes nuevos con él; los que ya emitiste se conservan y la numeración queda donde está.`;
          if (window.confirm(aviso)) {
            void cambiarEstado(fila, false);
          }
        }}
      >
        Desactivar
      </button>
    );
  }

  return (
    <>
      <header className="fac-nuevo-encabezado">
        <div>
          <span className="fac-nuevo-encabezado__cintillo">Facturación</span>
          <h1 className="fac-nuevo-encabezado__titulo">Puntos de venta</h1>
          <p className="fac-nuevo-encabezado__sub">
            Cada punto lleva su propia numeración por tipo de comprobante, igual que en ARCA. Agregá
            acá los que la AFIP te tiene habilitados.
          </p>
        </div>
        {puedeEditar && (
          <div className="fac-nuevo-encabezado__acciones">
            <Button onClick={abrirAlta}>Agregar punto de venta</Button>
          </div>
        )}
      </header>

      <div className="fac-nuevo-avisos">
        {error !== null && (
          <Alert tono="error" titulo="No se pudo completar">
            {error}
          </Alert>
        )}
      </div>

      {listado.puntos.length > 0 && (
        <p className="ptv-resumen">
          <span>
            <strong>{listado.puntos.length}</strong>{" "}
            {listado.puntos.length === 1 ? "punto de venta" : "puntos de venta"}
          </span>
          <span className="ptv-resumen__item">
            <i className="ptv-resumen__punto ptv-resumen__punto--ok" aria-hidden="true" />
            <strong>{listado.puntos.filter((p) => p.activo).length}</strong> Activos
          </span>
          <span className="ptv-resumen__item">
            <i className="ptv-resumen__punto" aria-hidden="true" />
            <strong>{listado.puntos.filter((p) => !p.activo).length}</strong> Inactivos
          </span>
        </p>
      )}

      {listado.puntos.length === 0 ? (
        <div className="ptv-vacio">
          <span className="ptv-vacio__icono" aria-hidden="true">
            <Store size={26} strokeWidth={1.6} />
          </span>
          <p className="ptv-vacio__titulo">Todavía no hay puntos de venta.</p>
          <p className="ptv-vacio__texto">Agregá uno de los que ARCA te habilitó.</p>
        </div>
      ) : (
        <div className="ptv-grilla">
          {listado.puntos.map((punto, indice) => {
            const numeracion = numeracionDe(punto);
            const alta = fechaDeAlta(punto.created_at);
            return (
              <article
                key={punto.id}
                className={`ptv-tarjeta${punto.activo ? "" : " ptv-tarjeta--inactivo"}`}
                style={{ animationDelay: `${Math.min(indice, 8) * 60}ms` }}
              >
                <header className="ptv-tarjeta__cabeza">
                  <span className="ptv-ficha" aria-hidden="true">
                    <Hash size={14} strokeWidth={2} />
                  </span>
                  <span className="ptv-tarjeta__numero">{formateado(punto.numero)}</span>
                  <Badge estado={punto.activo ? "ok" : "pendiente"}>
                    {punto.activo ? "Activo" : "Inactivo"}
                  </Badge>
                </header>

                <h2 className="ptv-tarjeta__nombre">{punto.descripcion ?? "—"}</h2>

                <div className="ptv-numeracion">
                  <p className="ptv-numeracion__rotulo">
                    <ReceiptText size={13} strokeWidth={1.8} aria-hidden="true" />
                    Último emitido
                  </p>
                  {numeracion.length === 0 ? (
                    <p className="ptv-numeracion__vacio">Sin emisiones</p>
                  ) : (
                    <ul className="ptv-numeracion__lista">
                      {numeracion.map((texto) => (
                        <li key={texto} className="ptv-tipo">
                          {texto}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <details className="ptv-detalle">
                  <summary>Detalle</summary>
                  <dl className="ptv-detalle__datos">
                    <dt>Estado</dt>
                    <dd>
                      {punto.activo ? "Habilitado para emitir" : "No emite comprobantes nuevos"}
                    </dd>
                    {alta !== null && (
                      <>
                        <dt>Agregado el</dt>
                        <dd>{alta}</dd>
                      </>
                    )}
                    <dt>Tipos con emisiones</dt>
                    <dd>{numeracion.length}</dd>
                  </dl>
                </details>

                {puedeEditar && <div className="ptv-tarjeta__pie">{accion(punto)}</div>}
              </article>
            );
          })}
        </div>
      )}

      <Modal abierto={alta} titulo="Agregar punto de venta" onCerrar={() => setAlta(false)}>
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void registrar();
          }}
        >
          {errorDeAlta !== null && (
            <Alert tono="error" titulo="No se pudo agregar">
              {errorDeAlta}
            </Alert>
          )}

          <Campo
            id="punto-numero"
            etiqueta="Número"
            mono
            ayuda="Tiene que estar habilitado en ARCA para tu CUIT. Lo verificamos antes de guardarlo."
            value={numero}
            onChange={(evento) => setNumero(evento.target.value)}
          />
          <Campo
            id="punto-descripcion"
            etiqueta="Descripción"
            value={descripcion}
            onChange={(evento) => setDescripcion(evento.target.value)}
          />

          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setAlta(false)}>
              Cancelar
            </Button>
            <Button type="submit" cargando={guardando}>
              {guardando ? "Verificando en ARCA…" : "Agregar"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
