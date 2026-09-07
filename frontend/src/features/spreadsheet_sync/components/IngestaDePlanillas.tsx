/**
 * PAN-ING-01 — Ingesta de Datos · Carga (HU-E2-04, HU-E3-03).
 *
 * The drop zone and the link button sit side by side because the prototype
 * (`docs/aidlc/inputs/prototipos/ingesta.html`) puts them there: they are two answers to
 * the same question, and a company picks one.
 *
 * **The two rejections happen before anything is uploaded.** `validarArchivo` runs on the
 * chosen file and shows the story's own sentence; the backend refuses the same two things
 * and that is the guarantee, but making somebody wait out a 30 MB upload to be told the
 * limit is 25 is a minute of their connection spent on a foregone answer.
 *
 * `Cargas recientes` is a listing and every role reads it (HU-E3-05 RN-04). `puedeEditar`
 * only decides whether the actions render — hiding a button is a courtesy, and the
 * backend refuses regardless.
 */

"use client";

import { useRef, useState } from "react";

import { Alert, Badge, Button, Card, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_PROVEEDOR,
  EXTENSIONES_ACEPTADAS,
  ErrorDePlanilla,
  LIMITE_TAMANO_MB,
  desvincularPlanilla,
  iniciarVinculacionConGoogle,
  listarPlanillas,
  subirPlanilla,
} from "../api/planilla";
import type { ListadoDeVinculos, Vinculo } from "../api/planilla";

export interface PropsDeIngesta {
  readonly inicial: ListadoDeVinculos;
  readonly puedeEditar: boolean;
}

/** What a link's state is called on screen, and how the badge is toned. */
function estadoDe(vinculo: Vinculo): { readonly texto: string; readonly tono: EstadoDeBadge } {
  if (vinculo.pausado) {
    return { texto: "Pausada", tono: "atencion" };
  }
  if (!vinculo.tiene_mapeo) {
    return { texto: "Falta mapear", tono: "atencion" };
  }
  return { texto: "Vinculada", tono: "ok" };
}

function tamanoLegible(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function IngestaDePlanillas({ inicial, puedeEditar }: PropsDeIngesta): JSX.Element {
  const [listado, setListado] = useState<ListadoDeVinculos>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [arrastrando, setArrastrando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  async function refrescar(): Promise<void> {
    setListado(await listarPlanillas());
  }

  function reportar(problema: unknown): void {
    setAviso(null);
    setError(
      problema instanceof ErrorDePlanilla ? problema.message : "No se pudo completar la operacion",
    );
  }

  async function cargar(archivo: File | undefined): Promise<void> {
    if (archivo === undefined) {
      return;
    }
    setError(null);
    setAviso(null);
    setSubiendo(true);
    try {
      const vinculo = await subirPlanilla(archivo);
      await refrescar();
      setAviso(`Se cargo ${vinculo.nombre_archivo ?? archivo.name}. Ya podes revisar el mapeo.`);
    } catch (problema) {
      reportar(problema);
    } finally {
      setSubiendo(false);
      // Clearing the input matters: without it, choosing the same file again after a
      // rejection fires no `change` event and the screen looks frozen.
      if (entrada.current !== null) {
        entrada.current.value = "";
      }
    }
  }

  async function vincularConGoogle(): Promise<void> {
    setError(null);
    try {
      window.location.href = await iniciarVinculacionConGoogle();
    } catch (problema) {
      reportar(problema);
    }
  }

  async function desvincular(vinculo: Vinculo): Promise<void> {
    setError(null);
    try {
      await desvincularPlanilla(vinculo.id);
      await refrescar();
      setAviso("Se desvinculo la planilla. Los datos que ya se importaron siguen en el sistema.");
    } catch (problema) {
      reportar(problema);
    }
  }

  const columnasBase: readonly Columna<Vinculo>[] = [
    {
      clave: "origen",
      titulo: "Origen",
      celda: (vinculo) => (
        <>
          <strong>{vinculo.nombre_archivo ?? vinculo.hoja_empresa}</strong>
          <br />
          <small>{ETIQUETAS_DE_PROVEEDOR[vinculo.proveedor]}</small>
        </>
      ),
    },
    { clave: "tamano", titulo: "Tamano", celda: (v) => tamanoLegible(v.tamano_bytes) },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (vinculo) => {
        const { texto, tono } = estadoDe(vinculo);
        return <Badge estado={tono}>{texto}</Badge>;
      },
    },
    {
      clave: "escritura",
      titulo: "Escritura",
      // HU-E3-07's fourth criterion: a link that cannot be written back to says so,
      // rather than offering an option that would silently do nothing.
      celda: (vinculo) => (vinculo.escribe_de_vuelta ? "Lectura y escritura" : "Solo lectura"),
    },
  ];

  const columnaDeAcciones: Columna<Vinculo> = {
    clave: "acciones",
    titulo: "Acciones",
    alDerecha: true,
    celda: (vinculo) => (
      <Button
        variante="destructivo"
        confirmacion="Vas a desvincular esta planilla. Los datos que ya se importaron se quedan; solo se corta la conexion."
        onClick={() => {
          void desvincular(vinculo);
        }}
      >
        Desvincular
      </Button>
    ),
  };

  const columnas = puedeEditar ? [...columnasBase, columnaDeAcciones] : columnasBase;

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      {puedeEditar && (
        <Card>
          <div
            className={`ingesta__zona${arrastrando ? " ingesta__zona--activa" : ""}`}
            onDragOver={(evento) => {
              evento.preventDefault();
              setArrastrando(true);
            }}
            onDragLeave={() => {
              setArrastrando(false);
            }}
            onDrop={(evento) => {
              evento.preventDefault();
              setArrastrando(false);
              void cargar(evento.dataTransfer.files[0]);
            }}
          >
            <p className="ingesta__titulo">Arrastrá tu planilla acá</p>
            <p className="ingesta__ayuda">
              {EXTENSIONES_ACEPTADAS.join(", ")} · hasta {LIMITE_TAMANO_MB} MB
            </p>
            <input
              ref={entrada}
              type="file"
              accept={EXTENSIONES_ACEPTADAS.join(",")}
              aria-label="Elegir una planilla"
              disabled={subiendo}
              onChange={(evento) => {
                void cargar(evento.target.files?.[0]);
              }}
            />
            <p className="ingesta__o">o</p>
            <Button
              variante="secundario"
              disabled={subiendo}
              onClick={() => {
                void vincularConGoogle();
              }}
            >
              Vincular Google Sheets
            </Button>
            <p className="ingesta__ayuda">
              Te vamos a pedir permiso de lectura <strong>sobre la planilla que elijas</strong>, no
              sobre todo tu Drive.
            </p>
          </div>
          {subiendo && <p role="status">Subiendo la planilla…</p>}
        </Card>
      )}

      <Tabla
        titulo="Cargas recientes"
        columnas={columnas}
        filas={listado.vinculos}
        claveDeFila={(vinculo) => vinculo.id}
        vacia="Todavia no vinculaste ninguna planilla."
      />
    </>
  );
}
