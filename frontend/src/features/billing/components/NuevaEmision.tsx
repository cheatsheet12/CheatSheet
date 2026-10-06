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
 * **Los tres pasos son tres `<fieldset>` numerados y no un indicador de progreso decorativo.**
 * Son tres grupos de campos de verdad, y agruparlos es lo que hace que un lector de pantalla
 * anuncie «Receptor» antes de leer el CUIT. Los pasos 2 y 3 se dibujan desde el principio,
 * apagados y diciendo qué falta: una pantalla que sólo muestra un campo no deja ver cuánto
 * queda, y ese es el motivo por el que alguien la abandona a mitad de camino. Lo que **no**
 * se dibuja hasta que ARCA contesta son sus controles, que es RN-01.
 *
 * **Nothing on this screen multiplies anything.** No running total, no VAT preview. The
 * amounts are text, they travel as text, and what the customer owes is decided by the
 * backend and authorised by ARCA (`CLAUDE.md` §5: no business logic in the frontend).
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Campo, Select, useAccionConNavegacion } from "@/shared";

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
  /**
   * El CUIT que ese cliente ya tiene en el catálogo, si tiene.
   *
   * Se precarga y se valida solo: quien llegó acá eligió a quién facturarle, y volver a
   * pedirle el dato que el sistema ya guardó es pedirle que lo transcriba — con la chance
   * de equivocarse, sobre el campo del que depende qué comprobante se puede emitir.
   */
  readonly cuitDelCliente?: string | null;
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

/** Hecho, en curso o todavía no: es lo único que decide el color del número del paso. */
function estadoDePaso(hecho: boolean, actual: boolean): string {
  if (hecho) {
    return " fac-nuevo-paso--hecho";
  }
  return actual ? " fac-nuevo-paso--actual" : "";
}

export function NuevaEmision({
  puntos,
  clienteId,
  cuitDelCliente = null,
}: PropsDeNuevaEmision): JSX.Element {
  const [cuit, setCuit] = useState((cuitDelCliente ?? "").replace(/-/g, ""));
  const [receptor, setReceptor] = useState<ReceptorValidado | null>(null);
  const [errorDeCuit, setErrorDeCuit] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);

  const [tipo, setTipo] = useState("");
  const [puntoId, setPuntoId] = useState(puntos[0]?.id ?? "");
  const [domicilio, setDomicilio] = useState("");
  const [lineas, setLineas] = useState<readonly Linea[]>([lineaVacia()]);
  const [error, setError] = useState<string | null>(null);
  const { pendiente: emitiendo, ejecutar } = useAccionConNavegacion();

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

  /**
   * Validar de entrada el CUIT que vino del catálogo.
   *
   * Sin esto la pantalla abre con el campo lleno y el paso 2 cerrado, esperando un clic
   * que no decide nada. Se corre una sola vez: si la persona edita el CUIT, el efecto no
   * vuelve a dispararse y valida ella.
   */
  useEffect(() => {
    if (cuit !== "") {
      void validar();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- al montar y nada más
  }, []);

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
    try {
      await ejecutar(
        () =>
          emitirComprobante({
            cliente_id: clienteId,
            punto_de_venta_id: puntoId,
            tipo: tipo as TipoComprobante,
            receptor_cuit: receptor.cuit,
            receptor_domicilio: domicilio.trim() === "" ? null : domicilio.trim(),
            items: lineasCargadas.map(({ clave: _clave, ...resto }) => resto),
          }),
        // Straight to the detail: the document is Pendiente and this is the page that will
        // show the CAE or ARCA's rejection when the answer arrives. The button stays busy
        // until it does: a second click here would issue a second document with its own CAE.
        (emitido, router) => router.push(`/facturacion/${emitido.id}`),
      );
    } catch (fallo) {
      setError(mensajeDe(fallo, "No se pudo emitir el comprobante."));
    }
  }

  const validado = receptor !== null;

  return (
    <form
      className="fac-nuevo-formulario"
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

      <fieldset className={`fac-nuevo-paso${estadoDePaso(validado, !validado)}`}>
        <legend>
          <span className="fac-nuevo-paso__numero" aria-hidden>
            1
          </span>
          Receptor
        </legend>
        <p className="fac-nuevo-paso__ayuda">
          Lo verificamos contra el padrón de ARCA. De esa respuesta depende qué se puede emitir, así
          que es lo primero.
        </p>

        <div className="fac-nuevo-cuit">
          <Campo
            id="emision-cuit"
            etiqueta="CUIT del receptor"
            mono
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
          <Alert tono="exito" titulo="CUIT validado">
            {receptor.nombre} — {receptor.condicion_iva.replaceAll("_", " ").toLowerCase()}
          </Alert>
        )}
      </fieldset>

      <fieldset className={`fac-nuevo-paso${estadoDePaso(validado && tipo !== "", validado)}`}>
        <legend>
          <span className="fac-nuevo-paso__numero" aria-hidden>
            2
          </span>
          Comprobante
        </legend>
        <p className="fac-nuevo-paso__ayuda">
          Qué se puede emitir lo decide la condición de IVA del receptor, y con qué numeración lo
          decide el punto de venta.
        </p>

        {receptor === null ? (
          <p className="fac-nuevo-vacio">Validá el CUIT del paso 1 para continuar.</p>
        ) : (
          <>
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
          </>
        )}
      </fieldset>

      <fieldset
        className={`fac-nuevo-paso${estadoDePaso(lineasCargadas.length > 0, validado && tipo !== "")}`}
      >
        <legend>
          <span className="fac-nuevo-paso__numero" aria-hidden>
            3
          </span>
          Ítems
        </legend>
        <p className="fac-nuevo-paso__ayuda">
          Los importes viajan como texto y los calcula el backend: acá no se multiplica nada.
        </p>

        {receptor === null ? (
          <p className="fac-nuevo-vacio">
            Los ítems se cargan cuando ya sabemos a quién se le factura.
          </p>
        ) : (
          <>
            {lineas.map((linea, indice) => (
              <div className="fac-nuevo-item" key={linea.clave}>
                <Campo
                  id={`item-descripcion-${linea.clave}`}
                  etiqueta={`Descripción ${indice + 1}`}
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
            <div className="fac-nuevo-acciones">
              <Button
                variante="secundario"
                onClick={() => setLineas((previas) => [...previas, lineaVacia()])}
              >
                Agregar item
              </Button>
            </div>
            {lineasCargadas.length === 0 && <Alert tono="neutral">{MENSAJE_SIN_ITEMS}</Alert>}
          </>
        )}
      </fieldset>

      {receptor !== null && (
        <div className="fac-nuevo-acciones">
          <Button type="submit" disabled={!puedeEmitir} cargando={emitiendo}>
            Emitir
          </Button>
        </div>
      )}
    </form>
  );
}
