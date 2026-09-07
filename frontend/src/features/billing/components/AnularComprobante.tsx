/**
 * PAN-FAC-04 — Facturación · Nueva nota de crédito (HU-E5-04).
 *
 * **Everything is preloaded.** The first acceptance criterion asks for it and it is not
 * convenience: the type, the receptor and the ceiling all come from the original (RN-02,
 * RN-03), and a form that let somebody type them would be a form that can produce a
 * document ARCA rejects.
 *
 * The lines start as a copy of the original's, which is what a full reversal is. Editing
 * them down is what a partial one is, and that is the only thing this screen really lets
 * somebody do.
 *
 * **The ceiling is checked here and enforced by the backend**, and the duplication is
 * deliberate: showing it disabled is the difference between a form that explains itself and
 * one that answers 422 after somebody typed everything. The backend's check is the
 * guarantee, because two tabs can both pass this one.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Select, formatearNumero } from "@/shared";

import {
  ALICUOTAS,
  ErrorDeComprobante,
  MENSAJE_MONTO_EXCEDIDO,
  emitirNotaDeCredito,
} from "../api/comprobante";
import type { Anulacion, Comprobante, ItemNuevo } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO, notaDeCreditoDe } from "../api/puntoDeVenta";

export interface PropsDeAnularComprobante {
  readonly original: Comprobante;
  readonly anulacion: Anulacion;
}

interface Linea extends ItemNuevo {
  readonly clave: string;
}

/** The original's lines, which is what a full reversal is (RN-03's ceiling case). */
function lineasDe(original: Comprobante): Linea[] {
  return original.items.map((item) => ({
    clave: item.id,
    descripcion: item.descripcion,
    cantidad: item.cantidad,
    precio_unitario: item.precio_unitario,
    alicuota_iva: item.alicuota_iva,
  }));
}

/**
 * The note's total, **for the disabled state only**.
 *
 * This is the one place in the frontend that multiplies money, and it is allowed for
 * exactly one reason: it decides whether a button is grey. What the note actually reverses
 * is computed by the backend, rounded per item (D15) and validated against ARCA — this
 * number never travels and never appears as an amount owed.
 */
function totalAproximado(lineas: readonly Linea[]): number {
  return lineas.reduce((suma, linea) => {
    const cantidad = Number(linea.cantidad);
    const precio = Number(linea.precio_unitario);
    const tasa = Number(linea.alicuota_iva);
    if (Number.isNaN(cantidad) || Number.isNaN(precio) || Number.isNaN(tasa)) {
      return suma;
    }
    return suma + cantidad * precio * (1 + tasa);
  }, 0);
}

export function AnularComprobante({ original, anulacion }: PropsDeAnularComprobante): JSX.Element {
  const router = useRouter();
  const [lineas, setLineas] = useState<readonly Linea[]>(() => lineasDe(original));
  const [error, setError] = useState<string | null>(null);
  const [emitiendo, setEmitiendo] = useState(false);

  const disponible = Number(anulacion.disponible);
  const excede = totalAproximado(lineas) > disponible + 0.005;

  function cambiar(clave: string, campo: keyof ItemNuevo, valor: string): void {
    setLineas((previas) =>
      previas.map((linea) => (linea.clave === clave ? { ...linea, [campo]: valor } : linea)),
    );
  }

  async function anular(): Promise<void> {
    setError(null);
    setEmitiendo(true);
    try {
      await emitirNotaDeCredito(
        original.id,
        lineas.map(({ clave: _clave, ...resto }) => resto),
      );
      // Back to the original: this is the page that shows how much of it is now reversed.
      router.push(`/facturacion/${original.id}`);
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeComprobante
          ? fallo.message
          : "No se pudo emitir la nota de crédito.",
      );
    } finally {
      setEmitiendo(false);
    }
  }

  if (anulacion.es_total) {
    return (
      <Alert tono="neutral" titulo="Ya está anulado del todo">
        Este comprobante fue anulado por el total de ${formatearNumero(anulacion.total_anulado)}. No
        queda saldo para emitir otra nota de crédito.
      </Alert>
    );
  }

  return (
    <form
      className="dm-formulario"
      onSubmit={(evento) => {
        evento.preventDefault();
        void anular();
      }}
    >
      {error !== null && (
        <Alert tono="error" titulo="No se pudo anular">
          {error}
        </Alert>
      )}

      <Alert tono="neutral" titulo={`Anulando ${ETIQUETAS_DE_TIPO[original.tipo]}`}>
        Se emite una {ETIQUETAS_DE_TIPO[notaDeCreditoDe(original.tipo)]} a nombre de{" "}
        {original.receptor_nombre}. Podés anular hasta $ {formatearNumero(anulacion.disponible)}
        {anulacion.es_parcial
          ? ` — ya anulaste $ ${formatearNumero(anulacion.total_anulado)} de $ ${formatearNumero(anulacion.total_original)}.`
          : "."}
      </Alert>

      <fieldset className="dm-selector">
        <legend>Qué se anula</legend>
        {lineas.map((linea, indice) => (
          <div className="fac-item" key={linea.clave}>
            <Campo
              id={`anular-descripcion-${linea.clave}`}
              etiqueta={`Descripcion ${indice + 1}`}
              value={linea.descripcion}
              onChange={(evento) => cambiar(linea.clave, "descripcion", evento.target.value)}
            />
            <Campo
              id={`anular-cantidad-${linea.clave}`}
              etiqueta="Cantidad"
              mono
              value={linea.cantidad}
              onChange={(evento) => cambiar(linea.clave, "cantidad", evento.target.value)}
            />
            <Campo
              id={`anular-precio-${linea.clave}`}
              etiqueta="Precio unitario"
              mono
              value={linea.precio_unitario}
              onChange={(evento) => cambiar(linea.clave, "precio_unitario", evento.target.value)}
            />
            <Select
              id={`anular-iva-${linea.clave}`}
              etiqueta="IVA"
              opciones={ALICUOTAS}
              value={linea.alicuota_iva}
              onChange={(evento) => cambiar(linea.clave, "alicuota_iva", evento.target.value)}
            />
            <Button
              variante="secundario"
              disabled={lineas.length === 1}
              onClick={() =>
                setLineas((previas) => previas.filter((otra) => otra.clave !== linea.clave))
              }
            >
              Quitar
            </Button>
          </div>
        ))}
      </fieldset>

      {excede && <Alert tono="error">{MENSAJE_MONTO_EXCEDIDO}</Alert>}

      <div className="dm-formulario__acciones">
        <Button variante="secundario" onClick={() => router.push(`/facturacion/${original.id}`)}>
          Cancelar
        </Button>
        <Button type="submit" disabled={excede} cargando={emitiendo}>
          Emitir nota de crédito
        </Button>
      </div>
    </form>
  );
}
