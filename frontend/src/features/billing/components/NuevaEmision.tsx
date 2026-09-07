/**
 * PAN-FAC-03 — Facturación · Nueva emisión (HU-E5-03).
 *
 * The form is **gated on the CUIT**, in the order the story writes: nothing else is enabled
 * until ARCA's registry has answered. That is not a UX flourish, it is RN-01 — the receptor's
 * VAT condition is what decides which document types are legal, and offering a type before
 * knowing it would be offering one the backend has to refuse.
 *
 * **The type selector only contains what the backend said is allowed.** The story's message
 * «El tipo de comprobante no es válido…» therefore belongs to a request that did not come
 * from this screen; the check on the way in is what makes it unreachable from here.
 *
 * **Nothing on this screen multiplies anything.** No running total, no VAT preview. The
 * amounts are text, they travel as text, and what the customer owes is decided by the
 * backend and authorised by ARCA (`CLAUDE.md` §5: no business logic in the frontend).
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Select } from "@/shared";

import {
  ALICUOTAS,
  ErrorDeComprobante,
  MENSAJE_SIN_ITEMS,
  emitirComprobante,
  validarReceptor,
} from "../api/comprobante";
import type { ItemNuevo, ReceptorValidado } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import type { PuntoDeVenta, TipoComprobante } from "../api/puntoDeVenta";

export interface PropsDeNuevaEmision {
  /** Only the active ones: an inactive point cannot issue (HU-E5-05 RN-04). */
  readonly puntos: readonly PuntoDeVenta[];
  /** The client the document is issued to, chosen before landing here. */
  readonly clienteId: string;
}

interface Linea extends ItemNuevo {
  readonly clave: string;
}

function lineaVacia(): Linea {
  return {
    clave: crypto.randomUUID(),
    descripcion: "",
    cantidad: "1",
    precio_unitario: "",
    alicuota_iva: "0.21",
  };
}

function mensajeDe(fallo: unknown, porDefecto: string): string {
  return fallo instanceof ErrorDeComprobante ? fallo.message : porDefecto;
}

export function NuevaEmision({ puntos, clienteId }: PropsDeNuevaEmision): JSX.Element {
  const router = useRouter();
  const [cuit, setCuit] = useState("");
  const [receptor, setReceptor] = useState<ReceptorValidado | null>(null);
  const [errorDeCuit, setErrorDeCuit] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);

  const [tipo, setTipo] = useState("");
  const [puntoId, setPuntoId] = useState(puntos[0]?.id ?? "");
  const [domicilio, setDomicilio] = useState("");
  const [lineas, setLineas] = useState<readonly Linea[]>([lineaVacia()]);
  const [error, setError] = useState<string | null>(null);
  const [emitiendo, setEmitiendo] = useState(false);

  async function validar(): Promise<void> {
    setErrorDeCuit(null);
    setReceptor(null);
    setValidando(true);
    try {
      const validado = await validarReceptor(cuit);
      setReceptor(validado);
      // Preselected only when there is exactly one legal option: choosing for somebody
      // among two is choosing which kind of document they issue.
      setTipo(validado.tipos_disponibles.length === 1 ? (validado.tipos_disponibles[0] ?? "") : "");
    } catch (fallo) {
      // «El CUIT ingresado no es válido…» y «No se encontró el CUIT en el padrón de ARCA.»
      // llegan por acá, tal cual las escribió la historia.
      setErrorDeCuit(mensajeDe(fallo, "No se pudo validar el CUIT."));
    } finally {
      setValidando(false);
    }
  }

  function cambiarLinea(clave: string, campo: keyof ItemNuevo, valor: string): void {
    setLineas((previas) =>
      previas.map((linea) => (linea.clave === clave ? { ...linea, [campo]: valor } : linea)),
    );
  }

  const lineasCargadas = lineas.filter(
    (linea) => linea.descripcion.trim() !== "" && linea.precio_unitario.trim() !== "",
  );
  // The criterion is explicit that the button stays disabled with no items loaded. The
  // message is shown too: a disabled button with no explanation is a dead end.
  const puedeEmitir =
    receptor !== null && tipo !== "" && puntoId !== "" && lineasCargadas.length > 0;

  async function emitir(): Promise<void> {
    if (receptor === null) {
      return;
    }
    setError(null);
    setEmitiendo(true);
    try {
      const emitido = await emitirComprobante({
        cliente_id: clienteId,
        punto_de_venta_id: puntoId,
        tipo: tipo as TipoComprobante,
        receptor_cuit: receptor.cuit,
        receptor_domicilio: domicilio.trim() === "" ? null : domicilio.trim(),
        items: lineasCargadas.map(({ clave: _clave, ...resto }) => resto),
      });
      // Straight to the detail: the document is Pendiente and this is the page that will
      // show the CAE or ARCA's rejection when the answer arrives.
      router.push(`/facturacion/${emitido.id}`);
    } catch (fallo) {
      setError(mensajeDe(fallo, "No se pudo emitir el comprobante."));
    } finally {
      setEmitiendo(false);
    }
  }

  return (
    <form
      className="dm-formulario"
      onSubmit={(evento) => {
        evento.preventDefault();
        void emitir();
      }}
    >
      {error !== null && (
        <Alert tono="error" titulo="No se pudo emitir">
          {error}
        </Alert>
      )}

      <div className="dm-formulario__cuit">
        <Campo
          id="emision-cuit"
          etiqueta="CUIT del receptor"
          mono
          ayuda="Lo verificamos contra el padrón de ARCA antes de habilitar el resto."
          error={errorDeCuit ?? undefined}
          value={cuit}
          onChange={(evento) => {
            setCuit(evento.target.value);
            // A changed CUIT invalidates everything that depended on it -- including which
            // types are legal. Keeping the old answer visible would be the screen lying.
            setReceptor(null);
            setTipo("");
          }}
        />
        <Button variante="secundario" cargando={validando} onClick={() => void validar()}>
          Validar
        </Button>
      </div>

      {receptor !== null && (
        <>
          <Alert tono="exito" titulo="CUIT validado">
            {receptor.nombre} — {receptor.condicion_iva.replaceAll("_", " ").toLowerCase()}
          </Alert>

          <Select
            id="emision-tipo"
            etiqueta="Tipo de comprobante"
            opciones={[
              { valor: "", etiqueta: "Elegí un tipo" },
              ...receptor.tipos_disponibles.map((valor) => ({
                valor,
                etiqueta: ETIQUETAS_DE_TIPO[valor],
              })),
            ]}
            value={tipo}
            onChange={(evento) => setTipo(evento.target.value)}
            ayuda="Solo se ofrecen los tipos válidos para tu condición de IVA y la del receptor."
          />

          <Select
            id="emision-punto"
            etiqueta="Punto de venta"
            opciones={puntos.map((punto) => ({
              valor: punto.id,
              etiqueta: `${String(punto.numero).padStart(4, "0")}${
                punto.descripcion === null ? "" : ` — ${punto.descripcion}`
              }`,
            }))}
            value={puntoId}
            onChange={(evento) => setPuntoId(evento.target.value)}
          />

          <Campo
            id="emision-domicilio"
            etiqueta="Domicilio del receptor"
            value={domicilio}
            onChange={(evento) => setDomicilio(evento.target.value)}
          />

          <fieldset className="dm-selector">
            <legend>Items</legend>
            {lineas.map((linea, indice) => (
              <div className="fac-item" key={linea.clave}>
                <Campo
                  id={`item-descripcion-${linea.clave}`}
                  etiqueta={`Descripcion ${indice + 1}`}
                  value={linea.descripcion}
                  onChange={(evento) =>
                    cambiarLinea(linea.clave, "descripcion", evento.target.value)
                  }
                />
                <Campo
                  id={`item-cantidad-${linea.clave}`}
                  etiqueta="Cantidad"
                  mono
                  value={linea.cantidad}
                  onChange={(evento) => cambiarLinea(linea.clave, "cantidad", evento.target.value)}
                />
                <Campo
                  id={`item-precio-${linea.clave}`}
                  etiqueta="Precio unitario"
                  mono
                  // Text and not `type="number"`: a number input hands back a JavaScript
                  // float, which is the type this system refuses to let near money.
                  value={linea.precio_unitario}
                  onChange={(evento) =>
                    cambiarLinea(linea.clave, "precio_unitario", evento.target.value)
                  }
                />
                <Select
                  id={`item-iva-${linea.clave}`}
                  etiqueta="IVA"
                  opciones={ALICUOTAS}
                  value={linea.alicuota_iva}
                  onChange={(evento) =>
                    cambiarLinea(linea.clave, "alicuota_iva", evento.target.value)
                  }
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
            <Button
              variante="secundario"
              onClick={() => setLineas((previas) => [...previas, lineaVacia()])}
            >
              Agregar item
            </Button>
          </fieldset>

          {lineasCargadas.length === 0 && <Alert tono="neutral">{MENSAJE_SIN_ITEMS}</Alert>}

          <div className="dm-formulario__acciones">
            <Button type="submit" disabled={!puedeEmitir} cargando={emitiendo}>
              Emitir
            </Button>
          </div>
        </>
      )}
    </form>
  );
}
