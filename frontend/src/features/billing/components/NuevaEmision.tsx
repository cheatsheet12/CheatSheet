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
 * **Tres pasos con estado** (pendiente / activo / completo) y un indicador de progreso arriba.
 * Los pasos 2 y 3 se dibujan desde el principio, atenuados y diciendo qué los desbloquea: una
 * pantalla que sólo muestra un campo no deja ver cuánto queda. Lo que **no** se dibuja hasta
 * que ARCA contesta son sus controles, que es RN-01. El paso 1, una vez validado, se pliega en
 * la tarjeta del receptor con un «Cambiar».
 *
 * **Nothing on this screen multiplies anything.** No running total, no VAT preview. The
 * amounts are text, they travel as text, and what the customer owes is decided by the
 * backend and authorised by ARCA (`CLAUDE.md` §5: no business logic in the frontend).
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Campo, Select, useAccionConNavegacion } from "@/shared";

import { MENSAJE_SIN_ITEMS, emitirComprobante, validarReceptor } from "../api/comprobante";
import type { ReceptorValidado } from "../api/comprobante";
import { mensajeLegible } from "../api/mensajesDeError";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import type { PuntoDeVenta, TipoComprobante } from "../api/puntoDeVenta";
import { ItemsDeEmision, lineaVacia } from "./ItemsDeEmision";
import type { Linea } from "./ItemsDeEmision";
import { IconoDeEscudo, IconoDeLapiz, IconoDePersona } from "./iconosEmision";
import { Colapsable, IndicadorDePasos, PasoDeEmision } from "./PasoDeEmision";
import type { EstadoDePaso } from "./PasoDeEmision";
import { ResumenDeEmision } from "./ResumenDeEmision";
import { TarjetaDelReceptor } from "./TarjetaDelReceptor";

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
  /** El nombre de ese cliente, para decir de quién se trata. Sólo se muestra. */
  readonly nombreDelCliente?: string | null;
}

function punto4(punto: PuntoDeVenta): string {
  return String(punto.numero).padStart(4, "0");
}

/** Cómo se numera lo que se va a emitir, dicho sin inventar el número que asigna ARCA. */
function textoDeNumeracion(punto: PuntoDeVenta | undefined, tipo: string): string {
  if (punto === undefined || tipo === "") {
    return "Elegí el tipo de comprobante para ver con qué numeración se emite.";
  }
  const ultimo = punto.numerador_por_tipo[tipo as TipoComprobante];
  const etiqueta = ETIQUETAS_DE_TIPO[tipo as TipoComprobante];
  if (ultimo === undefined) {
    return `Todavía no se emitió ninguna ${etiqueta} en el punto de venta ${punto4(punto)}: ARCA asigna el primer número al emitir.`;
  }
  return `El último emitido en el punto de venta ${punto4(punto)} es el ${punto4(punto)}-${String(ultimo).padStart(8, "0")}. ARCA asigna el siguiente al emitir.`;
}

export function NuevaEmision({
  puntos,
  clienteId,
  cuitDelCliente = null,
  nombreDelCliente = null,
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
      // llegan por acá tal cual las escribió la historia; un código técnico se traduce.
      setErrorDeCuit(mensajeLegible(fallo, "validar"));
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

  function cambiarReceptor(): void {
    setReceptor(null);
    setTipo("");
    // El campo se despliega con una transición: se le da foco cuando ya es alcanzable.
    window.setTimeout(() => document.getElementById("emision-cuit")?.focus(), 60);
  }

  const lineasCargadas = lineas.filter(
    (linea) => linea.descripcion.trim() !== "" && linea.precio_unitario.trim() !== "",
  );
  // The criterion is explicit that the button stays disabled with no items loaded. The
  // message is shown too: a disabled button with no explanation is a dead end.
  const puedeEmitir =
    receptor !== null && tipo !== "" && puntoId !== "" && lineasCargadas.length > 0;

  const motivos: string[] = [];
  if (tipo === "") {
    motivos.push("Elegir el tipo de comprobante.");
  }
  if (puntoId === "") {
    motivos.push("Elegir el punto de venta.");
  }
  if (lineasCargadas.length === 0) {
    motivos.push(MENSAJE_SIN_ITEMS);
  }

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
      setError(mensajeLegible(fallo, "emitir"));
    }
  }

  const validado = receptor !== null;
  const estado1: EstadoDePaso = validado ? "completo" : "activo";
  const estado2: EstadoDePaso = !validado ? "pendiente" : tipo !== "" ? "completo" : "activo";
  const estado3: EstadoDePaso =
    !validado || tipo === "" ? "pendiente" : lineasCargadas.length > 0 ? "completo" : "activo";
  const puntoElegido = puntos.find((uno) => uno.id === puntoId);

  return (
    <form
      className="fac-em-formulario"
      onSubmit={(evento) => {
        evento.preventDefault();
        void emitir();
      }}
    >
      <div className="fac-em-flujo">
        <IndicadorDePasos
          pasos={[
            { titulo: "Receptor", estado: estado1 },
            { titulo: "Comprobante", estado: estado2 },
            { titulo: "Ítems", estado: estado3 },
          ]}
        />

        {error !== null && (
          <Alert tono="error" titulo="No se pudo emitir">
            {error}
          </Alert>
        )}

        <PasoDeEmision
          numero={1}
          titulo="Receptor"
          estado={estado1}
          ayuda="Lo verificamos contra el padrón de ARCA: de esa respuesta depende qué se puede emitir."
          motivoDeBloqueo=""
          extremo={
            validado ? (
              <Button variante="secundario" onClick={cambiarReceptor}>
                <IconoDeLapiz />
                Cambiar
              </Button>
            ) : undefined
          }
        >
          {nombreDelCliente !== null && (
            <p className="fac-em-cliente">
              <IconoDePersona />
              <span>
                Cliente del catálogo: <b>{nombreDelCliente}</b>
              </span>
            </p>
          )}
          <Colapsable abierto={!validado}>
            <div className="fac-em-cuit">
              <Campo
                id="emision-cuit"
                etiqueta="CUIT del receptor"
                mono
                inputMode="numeric"
                autoComplete="off"
                error={errorDeCuit ?? undefined}
                value={cuit}
                onKeyDown={(evento) => {
                  if (evento.key === "Enter") {
                    // Enter valida el CUIT; no envía el formulario.
                    evento.preventDefault();
                    void validar();
                  }
                }}
                onChange={(evento) => {
                  setCuit(evento.target.value);
                  // A changed CUIT invalidates everything that depended on it -- including which
                  // types are legal. Keeping the old answer visible would be the screen lying.
                  setReceptor(null);
                  setTipo("");
                }}
              />
              <Button variante="secundario" cargando={validando} onClick={() => void validar()}>
                <IconoDeEscudo />
                Validar
              </Button>
            </div>
          </Colapsable>
          {receptor !== null && <TarjetaDelReceptor receptor={receptor} />}
        </PasoDeEmision>

        <PasoDeEmision
          numero={2}
          titulo="Comprobante"
          estado={estado2}
          ayuda="Qué se puede emitir lo decide la condición de IVA del receptor, y con qué numeración, el punto de venta."
          motivoDeBloqueo="Se habilita cuando ARCA valida el CUIT del receptor."
          extremo={
            estado2 === "completo" && tipo !== "" ? (
              <span className="fac-em-paso__pastilla">
                {ETIQUETAS_DE_TIPO[tipo as TipoComprobante]}
              </span>
            ) : undefined
          }
        >
          {receptor !== null && (
            <>
              <div className="fac-em-par">
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
                    etiqueta: `${punto4(punto)}${
                      punto.descripcion === null ? "" : ` — ${punto.descripcion}`
                    }`,
                  }))}
                  value={puntoId}
                  onChange={(evento) => setPuntoId(evento.target.value)}
                />
              </div>
              <p className="fac-em-numeracion">{textoDeNumeracion(puntoElegido, tipo)}</p>
              <Campo
                id="emision-domicilio"
                etiqueta="Domicilio del receptor (opcional)"
                // Sin sugerencias de ningún tipo: no hay de dónde sacar un domicilio fiable, y el
                // navegador no debe ofrecer valores de otras emisiones.
                autoComplete="off"
                value={domicilio}
                onChange={(evento) => setDomicilio(evento.target.value)}
              />
            </>
          )}
        </PasoDeEmision>

        <PasoDeEmision
          numero={3}
          titulo="Ítems"
          estado={estado3}
          ayuda="Buscá un servicio del catálogo o escribí la descripción a mano. Los importes los calcula el backend."
          motivoDeBloqueo="Se habilita cuando elegís el tipo de comprobante."
          extremo={
            lineasCargadas.length > 0 ? (
              <span className="fac-em-paso__pastilla">
                {lineasCargadas.length} {lineasCargadas.length === 1 ? "ítem" : "ítems"}
              </span>
            ) : undefined
          }
        >
          <ItemsDeEmision lineas={lineas} alCambiarLineas={(cambio) => setLineas(cambio)} />
        </PasoDeEmision>
      </div>

      <ResumenDeEmision
        cuit={receptor?.cuit ?? null}
        tipo={tipo === "" ? null : ETIQUETAS_DE_TIPO[tipo as TipoComprobante]}
        punto={puntoElegido === undefined ? null : punto4(puntoElegido)}
        cantidadDeItems={lineasCargadas.length}
        motivos={motivos}
        ofreceEmitir={receptor !== null}
        puedeEmitir={puedeEmitir}
        emitiendo={emitiendo}
      />
    </form>
  );
}
