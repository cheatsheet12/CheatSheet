/**
 * PAN-ING-02 — Ingesta de Datos · Revisión del mapeo (HU-E3-01, HU-E3-02).
 *
 * La tabla muestra las cuatro cosas que pide el primer criterio de HU-E3-02: la columna
 * original, el campo interno asignado, un ejemplo de dato y el nivel de confianza. La forma es
 * la del prototipo: el stepper arriba para ubicar el paso, una fila por columna con su número
 * de orden, y un pie que cuenta cuántas quedan listas y cuántas necesitan una mirada.
 *
 * **El stepper no es adorno.** Esta pantalla aparece en medio de un flujo de cuatro pasos y sin
 * él no hay forma de saber si confirmar acá termina el trabajo o lo empieza. Cuando el mapeo
 * queda validado el paso avanza solo, que es la única confirmación visible de que el botón hizo
 * algo.
 *
 * **El ejemplo se lee de la planilla y nunca pasó por el modelo** (decisión D12): son
 * CUITs y teléfonos de clientes reales, y `CLAUDE.md` §3.6 no los deja salir. Que se vean
 * acá es justamente lo que hace que mandar sólo encabezados no le cueste nada al usuario.
 *
 * **El botón de confirmar está deshabilitado mientras falte una obligatoria** (RN-02), y
 * el mensaje es el de la historia, palabra por palabra. El backend lo rechaza igual: esto
 * es cortesía, no el control.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Card, Select, Stepper, Tabla } from "@/shared";
import type { Columna, Paso } from "@/shared";

import {
  ATRIBUTOS_DE_CLIENTE,
  ETIQUETAS_DE_ATRIBUTO,
  ErrorDePlanilla,
  MENSAJE_FALTAN_OBLIGATORIAS,
  confirmarMapeo,
  corregirMapeo,
  procesarPlanilla,
  reabrirMapeo,
} from "../api/planilla";
import type { EntradaDeMapeo, Mapeo, NivelDeConfianza } from "../api/planilla";
import { Icono } from "./iconos";

export interface PropsDeRevision {
  readonly inicial: Mapeo;
  /** El vínculo que se está revisando. Hace falta para poder procesarlo desde acá. */
  readonly vinculoId: string;
  readonly puedeEditar: boolean;
  readonly onConfirmado?: (mapeo: Mapeo) => void;
}

/**
 * Cómo se lee cada nivel de confianza.
 *
 * En capitales («ALTA») es como llega del backend y como se escribe un enum; en una píldora al
 * lado de un nombre propio se lee como un grito. Los tres niveles son los de HU-E3-01 RN-01 y
 * dicen exactamente lo mismo.
 */
const ETIQUETAS_DE_CONFIANZA: Readonly<Record<NivelDeConfianza, string>> = {
  ALTA: "Alta",
  MEDIA: "Media",
  BAJA: "Baja",
};

const CLASE_DE_CONFIANZA: Readonly<Record<NivelDeConfianza, string>> = {
  ALTA: "ing-conf ing-conf--alta",
  MEDIA: "ing-conf ing-conf--media",
  BAJA: "ing-conf ing-conf--baja",
};

const OPCIONES = [
  { valor: "", etiqueta: "Sin asignar" },
  ...ATRIBUTOS_DE_CLIENTE.map((valor) => ({
    valor,
    etiqueta: ETIQUETAS_DE_ATRIBUTO[valor] ?? valor,
  })),
];

/** Los cuatro pasos del prototipo. Esta pantalla es el segundo. */
const PASOS: readonly Paso[] = [
  { numero: 1, nombre: "Cargar archivo" },
  { numero: 2, nombre: "Revisar mapeo" },
  { numero: 3, nombre: "Procesar y validar" },
  { numero: 4, nombre: "Sincronizar" },
];

/** El número de orden de la columna, con cero adelante, como en el prototipo. */
function ordinal(indice: number): string {
  return String(indice + 1).padStart(2, "0");
}

export function RevisionDeMapeo({
  inicial,
  vinculoId,
  puedeEditar,
  onConfirmado,
}: PropsDeRevision): JSX.Element {
  const router = useRouter();
  const [mapeo, setMapeo] = useState<Mapeo>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  function reportar(problema: unknown): void {
    setError(
      problema instanceof ErrorDePlanilla ? problema.message : "No se pudo completar la operación",
    );
  }

  async function corregir(columna: string, valor: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      setMapeo(await corregirMapeo(mapeo.id, columna, valor === "" ? null : valor));
    } catch (problema) {
      reportar(problema);
    } finally {
      setTrabajando(false);
    }
  }

  /**
   * El paso 3 del propio stepper de esta pantalla.
   *
   * Sin esto, «El mapeo quedó confirmado. Ya podés procesar la planilla» era una
   * instrucción sin destino: había que volver a Ingesta y buscar la fila. Una pantalla que
   * dice qué sigue tiene que ofrecer qué sigue.
   *
   * Procesar contesta 202 y el trabajo lo hace un worker, así que lo honesto después de
   * encolarlo es llevar a donde se ve el resultado — `Cargas recientes` — y no quedarse acá
   * mirando un mapeo que ya no es la pregunta.
   */
  async function procesar(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await procesarPlanilla(vinculoId);
      router.push("/ingesta");
      router.refresh();
    } catch (problema) {
      reportar(problema);
      setTrabajando(false);
    }
  }

  /**
   * Volver a revisar lo ya confirmado.
   *
   * El dominio se niega a corregir un mapeo validado y dice qué hacer en su lugar; sin
   * este botón, esa salida existía en el código y no en la pantalla, así que una columna
   * que quedó «Sin asignar» era definitiva.
   */
  async function reabrir(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      setMapeo(await reabrirMapeo(mapeo.id));
    } catch (problema) {
      reportar(problema);
    } finally {
      setTrabajando(false);
    }
  }

  async function confirmar(): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      const confirmado = await confirmarMapeo(mapeo.id);
      setMapeo(confirmado);
      onConfirmado?.(confirmado);
    } catch (problema) {
      reportar(problema);
    } finally {
      setTrabajando(false);
    }
  }

  // Se calcula acá arriba y no junto a los contadores porque ahora decide también si la
  // celda de destino es un control o un texto.
  const validado = mapeo.estado === "VALIDADO";

  const columnas: readonly Columna<EntradaDeMapeo>[] = [
    {
      clave: "origen",
      titulo: "Columna de tu planilla",
      celda: (entrada) => (
        <span className="ing-map-origen">
          <span className="ing-map-n" aria-hidden="true">
            {ordinal(mapeo.entradas.indexOf(entrada))}
          </span>
          <span className="ing-map-columna">{entrada.columna_origen}</span>
        </span>
      ),
    },
    {
      clave: "destino",
      titulo: "Campo del sistema",
      celda: (entrada) => (
        <span className="ing-map-destino">
          <span className="ing-map-flecha" aria-hidden="true">
            <Icono nombre="flecha" />
          </span>
          {/* Confirmado, el destino deja de ser un control. El dominio ya rechaza corregir
              un mapeo validado —«para cambiarlo hay que revisarlo de nuevo»—, así que dejar
              el `select` habilitado es ofrecer una acción que sólo puede terminar en un
              error. Lo que se ve es lo que se puede hacer. */}
          {puedeEditar && !validado ? (
            <Select
              id={`mapeo-${entrada.columna_origen}`}
              // La cabecera de la columna ya dice «Campo del sistema», pero un control cuyo
              // unico nombre es su columna es inusable con lector de pantalla, que anuncia
              // las celdas de a una. Oculta, no ausente.
              etiqueta={`Campo del sistema para ${entrada.columna_origen}`}
              etiquetaOculta
              value={entrada.atributo_destino ?? ""}
              opciones={OPCIONES}
              disabled={trabajando}
              onChange={(evento) => {
                void corregir(entrada.columna_origen, evento.target.value);
              }}
            />
          ) : (
            <DestinoDeSoloLectura atributo={entrada.atributo_destino} />
          )}
        </span>
      ),
    },
    {
      clave: "ejemplo",
      titulo: "Ejemplo",
      // Leído de la planilla, mostrado acá, nunca enviado al modelo (D12).
      celda: (entrada) => <span className="ing-map-ejemplo">{entrada.ejemplo ?? "—"}</span>,
    },
    {
      clave: "confianza",
      titulo: "Confianza",
      alDerecha: true,
      celda: (entrada) =>
        // Una corrección a mano ya no tiene confianza que reportar: la asignación la puso una
        // persona, y decir «Baja» al lado de una decisión humana invita a desconfiar de ella.
        entrada.corregida_a_mano ? (
          <span className="ing-conf ing-conf--manual">Corregida</span>
        ) : (
          <span className={CLASE_DE_CONFIANZA[entrada.confianza]}>
            {ETIQUETAS_DE_CONFIANZA[entrada.confianza]}
          </span>
        ),
    },
  ];

  const asignadas = mapeo.entradas.filter((entrada) => entrada.atributo_destino !== null).length;
  const sinAsignar = mapeo.entradas.length - asignadas;

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}

      <Stepper pasos={PASOS} actual={validado ? 3 : 2} />

      {/* Qué archivo se está mapeando y quién lo interpretó. La marca «Analizado por IA» sólo
          aparece cuando el modelo efectivamente propuso: es una atribución, no un adorno. */}
      <div className="ing-resumen">
        <span className="ing-resumen__ico">
          <Icono nombre="planilla" />
        </span>
        <span className="ing-resumen__datos">
          <b className="ing-resumen__nombre">Mapeo de tu planilla</b>
          <span className="ing-resumen__detalle">
            {mapeo.entradas.length} columnas detectadas · versión {mapeo.version}
          </span>
        </span>
        {mapeo.propuesto_por_el_modelo && (
          <span className="ing-marca-ia">
            <Icono nombre="chispa" />
            Analizado por IA
          </span>
        )}
      </div>

      {/* «No pudimos proponerlo» y «ya lo teníamos» son cosas distintas para alguien
          mirando una tabla llena de «Sin asignar», y la diferencia se dice. Hasta que
          `reutilizado` existió, las dos mostraban el mismo cartel de error. */}
      {mapeo.reutilizado === true && (
        <Alert tono="neutral">
          Ya habías mapeado una planilla con estas mismas columnas, así que reusamos ese mapeo en
          vez de volver a analizarla. Podés cambiar lo que quieras antes de confirmar.
        </Alert>
      )}

      {!mapeo.propuesto_por_el_modelo && mapeo.reutilizado !== true && (
        <Alert tono="advertencia">
          No pudimos proponerte un mapeo automático esta vez. Asigná las columnas a mano; el sistema
          lo va a recordar para las próximas sincronizaciones.
        </Alert>
      )}

      {mapeo.faltantes.length > 0 && (
        <Alert tono="advertencia">
          {MENSAJE_FALTAN_OBLIGATORIAS}{" "}
          {`Falta: ${mapeo.faltantes.map((f) => ETIQUETAS_DE_ATRIBUTO[f] ?? f).join(", ")}.`}
        </Alert>
      )}

      {validado && (
        <Alert tono="exito">El mapeo quedó confirmado. Ya podés procesar la planilla.</Alert>
      )}

      {validado && puedeEditar && (
        <div className="ing-acciones ing-acciones--barra">
          <Button
            cargando={trabajando}
            disabled={trabajando}
            onClick={() => {
              void procesar();
            }}
          >
            Procesar la planilla
            <Icono nombre="flecha" />
          </Button>
          <Button
            variante="secundario"
            disabled={trabajando}
            onClick={() => {
              void reabrir();
            }}
          >
            Revisar de nuevo
          </Button>
        </div>
      )}

      <Card>
        <div className="ing-map-tabla">
          <Tabla
            titulo="Revisión del mapeo"
            columnas={columnas}
            filas={mapeo.entradas}
            claveDeFila={(entrada) => entrada.columna_origen}
            vacia="La planilla no tiene columnas para mapear."
          />
        </div>

        <div className="ing-pie">
          <span className="ing-pie__dato">
            <span className="ing-pie__ic ing-pie__ic--ok" aria-hidden="true">
              <Icono nombre="tilde" />
            </span>
            <b>{asignadas}</b> columnas asignadas
          </span>
          <span className="ing-pie__dato">
            <span className="ing-pie__ic ing-pie__ic--atencion" aria-hidden="true">
              <Icono nombre="alerta" />
            </span>
            <b>{sinAsignar}</b> sin asignar · revisión manual
          </span>
          {puedeEditar && !validado && (
            <span className="ing-pie__acciones">
              <Button
                disabled={!mapeo.puede_confirmarse || trabajando}
                cargando={trabajando}
                onClick={() => {
                  void confirmar();
                }}
              >
                Confirmar y procesar
              </Button>
            </span>
          )}
        </div>
      </Card>
    </>
  );
}

/**
 * El destino cuando no se puede editar.
 *
 * «Sin asignar» va en rojo y con borde porque es lo único de la tabla que frena el paso
 * siguiente (RN-02); un campo asignado es sólo información y se lee en negro.
 */
function DestinoDeSoloLectura({ atributo }: { readonly atributo: string | null }): JSX.Element {
  if (atributo === null) {
    return (
      <span className="ing-map-sin-asignar">
        <Icono nombre="alerta" />
        Sin asignar
      </span>
    );
  }
  return <span className="ing-map-campo">{ETIQUETAS_DE_ATRIBUTO[atributo] ?? atributo}</span>;
}
