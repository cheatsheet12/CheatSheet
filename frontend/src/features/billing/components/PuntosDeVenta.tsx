/**
 * PAN-FAC-05 — Facturación · Puntos de venta (HU-E5-05).
 *
 * The listing the story's first criterion names — número, descripción y estado — plus the
 * numbering, which the story does not ask for and which is the first thing anybody looks
 * for when ARCA rejects a document for a number out of sequence.
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

import { Alert, Badge, Button, Campo, Modal, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ErrorDePuntoDeVenta,
  cambiarEstadoDePuntoDeVenta,
  listarPuntosDeVenta,
  registrarPuntoDeVenta,
  resumenDeNumeracion,
} from "../api/puntoDeVenta";
import type { ListadoDePuntosDeVenta, PuntoDeVenta } from "../api/puntoDeVenta";

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

  const columnas: readonly Columna<PuntoDeVenta>[] = [
    { clave: "numero", titulo: "Numero", celda: (fila) => formateado(fila.numero) },
    { clave: "descripcion", titulo: "Descripcion", celda: (fila) => fila.descripcion ?? "—" },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.activo ? "ok" : "pendiente"}>
          {fila.activo ? "Activo" : "Inactivo"}
        </Badge>
      ),
    },
    {
      clave: "numeracion",
      titulo: "Ultimo emitido",
      celda: (fila) => resumenDeNumeracion(fila) || "Sin emisiones",
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) => (puedeEditar ? accion(fila) : null),
    },
  ];

  function accion(fila: PuntoDeVenta): JSX.Element {
    if (!fila.activo) {
      return (
        <Button variante="secundario" onClick={() => void cambiarEstado(fila, true)}>
          Activar
        </Button>
      );
    }
    return (
      <Button
        variante="destructivo"
        confirmacion={`Vas a desactivar el punto ${formateado(fila.numero)}. No vas a poder emitir comprobantes nuevos con el; los que ya emitiste se conservan y la numeracion queda donde esta.`}
        onClick={() => void cambiarEstado(fila, false)}
      >
        Desactivar
      </Button>
    );
  }

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {puedeEditar && (
        <div className="fac-acciones">
          <Button onClick={abrirAlta}>Agregar punto de venta</Button>
        </div>
      )}

      <Tabla
        titulo="Puntos de venta"
        columnas={columnas}
        filas={listado.puntos}
        claveDeFila={(fila) => fila.id}
        vacia="Todavia no hay puntos de venta. Agregá uno de los que ARCA te habilitó."
      />

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
            etiqueta="Numero"
            mono
            ayuda="Tiene que estar habilitado en ARCA para tu CUIT. Lo verificamos antes de guardarlo."
            value={numero}
            onChange={(evento) => setNumero(evento.target.value)}
          />
          <Campo
            id="punto-descripcion"
            etiqueta="Descripcion"
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
