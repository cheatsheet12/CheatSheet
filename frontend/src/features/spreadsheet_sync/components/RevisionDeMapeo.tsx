/**
 * PAN-ING-02 — Ingesta de Datos · Revisión del mapeo (HU-E3-01, HU-E3-02).
 *
 * La tabla muestra las cuatro cosas que pide el primer criterio de HU-E3-02: la columna
 * original, el campo interno asignado, un ejemplo de dato y el nivel de confianza.
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

import { useState } from "react";

import { Alert, Badge, Button, Select, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ATRIBUTOS_DE_CLIENTE,
  ETIQUETAS_DE_ATRIBUTO,
  ErrorDePlanilla,
  MENSAJE_FALTAN_OBLIGATORIAS,
  confirmarMapeo,
  corregirMapeo,
} from "../api/planilla";
import type { EntradaDeMapeo, Mapeo, NivelDeConfianza } from "../api/planilla";

export interface PropsDeRevision {
  readonly inicial: Mapeo;
  readonly puedeEditar: boolean;
  readonly onConfirmado?: (mapeo: Mapeo) => void;
}

const TONO_DE_CONFIANZA: Readonly<Record<NivelDeConfianza, EstadoDeBadge>> = {
  ALTA: "ok",
  MEDIA: "atencion",
  BAJA: "error",
};

const OPCIONES = [
  { valor: "", etiqueta: "Sin asignar" },
  ...ATRIBUTOS_DE_CLIENTE.map((valor) => ({
    valor,
    etiqueta: ETIQUETAS_DE_ATRIBUTO[valor] ?? valor,
  })),
];

export function RevisionDeMapeo({
  inicial,
  puedeEditar,
  onConfirmado,
}: PropsDeRevision): JSX.Element {
  const [mapeo, setMapeo] = useState<Mapeo>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  function reportar(problema: unknown): void {
    setError(
      problema instanceof ErrorDePlanilla ? problema.message : "No se pudo completar la operacion",
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

  const columnas: readonly Columna<EntradaDeMapeo>[] = [
    { clave: "origen", titulo: "Columna de tu planilla", celda: (e) => e.columna_origen },
    {
      clave: "ejemplo",
      titulo: "Ejemplo",
      // Leído de la planilla, mostrado acá, nunca enviado al modelo (D12).
      celda: (e) => <code>{e.ejemplo ?? "—"}</code>,
    },
    {
      clave: "destino",
      titulo: "Campo del sistema",
      celda: (entrada) =>
        puedeEditar ? (
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
          (ETIQUETAS_DE_ATRIBUTO[entrada.atributo_destino ?? ""] ?? "Sin asignar")
        ),
    },
    {
      clave: "confianza",
      titulo: "Confianza",
      celda: (entrada) => (
        <Badge estado={TONO_DE_CONFIANZA[entrada.confianza]}>
          {entrada.corregida_a_mano ? "Corregida" : entrada.confianza}
        </Badge>
      ),
    },
  ];

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}

      {!mapeo.propuesto_por_el_modelo && (
        // «No pudimos proponerlo» y «ya lo teníamos» son cosas distintas para alguien
        // mirando una tabla llena de «Sin asignar», y la diferencia se dice.
        <Alert tono="advertencia">
          No pudimos proponerte un mapeo automatico esta vez. Asigná las columnas a mano; el sistema
          lo va a recordar para las proximas sincronizaciones.
        </Alert>
      )}

      {mapeo.faltantes.length > 0 && (
        <Alert tono="advertencia">
          {MENSAJE_FALTAN_OBLIGATORIAS}{" "}
          {`Falta: ${mapeo.faltantes.map((f) => ETIQUETAS_DE_ATRIBUTO[f] ?? f).join(", ")}.`}
        </Alert>
      )}

      {mapeo.estado === "VALIDADO" && (
        <Alert tono="exito">El mapeo quedo confirmado. Ya podes procesar la planilla.</Alert>
      )}

      <Tabla
        titulo="Revision del mapeo"
        columnas={columnas}
        filas={mapeo.entradas}
        claveDeFila={(entrada) => entrada.columna_origen}
        vacia="La planilla no tiene columnas para mapear."
      />

      {puedeEditar && mapeo.estado !== "VALIDADO" && (
        <Button
          disabled={!mapeo.puede_confirmarse || trabajando}
          cargando={trabajando}
          onClick={() => {
            void confirmar();
          }}
        >
          Confirmar y procesar
        </Button>
      )}
    </>
  );
}
