/**
 * PAN-ING-01 — Ingesta de Datos · Carga (HU-E2-04, HU-E3-03).
 *
 * La forma es la del prototipo (`docs/aidlc/inputs/prototipos/ingesta.html`): una zona de
 * carga grande con las dos maneras de traer datos —subir un archivo o vincular una hoja— y,
 * debajo, la banda que anuncia qué campos reconoce el modelo y las tablas de lo ya vinculado.
 *
 * **Las dos formas de traer datos van juntas y no en pestañas.** Son dos respuestas a la misma
 * pregunta y una empresa elige una sola vez; esconder una detrás de una pestaña obliga a
 * descubrirla.
 *
 * **Los dos rechazos ocurren antes de subir nada.** `validarArchivo` corre sobre el archivo
 * elegido y muestra la frase de la historia; el backend rechaza lo mismo y ésa es la garantía,
 * pero hacer esperar 30 MB de subida para enterarse de que el límite son 25 es un minuto de la
 * conexión de alguien gastado en una respuesta ya conocida.
 *
 * `Cargas recientes` es un listado y lo lee todo rol (HU-E3-05 RN-04). `puedeEditar` sólo
 * decide si se dibujan las acciones — esconder un botón es cortesía, y el backend rechaza igual.
 */

"use client";

import { useRef, useState } from "react";

import { Alert, Badge, Button, Campo, Card, Modal, Tabla, formatearFechaHora } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import Link from "next/link";

import {
  ATRIBUTOS_DE_CLIENTE,
  ETIQUETAS_DE_ATRIBUTO,
  ETIQUETAS_DE_ESTADO,
  ETIQUETAS_DE_PROVEEDOR,
  EXTENSIONES_ACEPTADAS,
  ErrorDePlanilla,
  LIMITE_TAMANO_MB,
  desvincularPlanilla,
  identificadorDePlanilla,
  iniciarVinculacionConGoogle,
  listarCargas,
  listarPlanillas,
  procesarPlanilla,
  subirPlanilla,
} from "../api/planilla";
import type { Carga, EstadoProcesamiento, ListadoDeVinculos, Vinculo } from "../api/planilla";
import { Icono } from "./iconos";
import type { NombreDeIcono } from "./iconos";

export interface PropsDeIngesta {
  readonly inicial: ListadoDeVinculos;
  /** `Cargas recientes` de PAN-ING-01. Lo lee todo rol (HU-E3-05 RN-04). */
  readonly cargasIniciales: readonly Carga[];
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

/**
 * Cómo se ve cada estado de un procesamiento.
 *
 * Los cuatro estados se distinguen dos veces: por el tono del badge y por el icono. «Con
 * errores» en verde —que es lo que hacía la versión anterior— le decía a alguien que su carga
 * salió bien cuando no salió bien.
 */
const ASPECTO_DE_ESTADO: Readonly<
  Record<EstadoProcesamiento, { readonly tono: EstadoDeBadge; readonly icono: NombreDeIcono }>
> = {
  EN_CURSO: { tono: "pendiente", icono: "refrescar" },
  COMPLETADO: { tono: "ok", icono: "planilla" },
  CON_ERRORES: { tono: "atencion", icono: "alerta" },
  FALLIDO: { tono: "error", icono: "alerta" },
};

/** El tono del icono de la carga, que sigue al del badge sin repetir su vocabulario. */
const TONO_DE_ICONO: Readonly<Record<EstadoDeBadge, string>> = {
  ok: "ok",
  atencion: "atencion",
  error: "error",
  pendiente: "",
};

/** `Cargas recientes`: el estado y los tres contadores que pide HU-E3-03. */
const COLUMNAS_DE_CARGA: readonly Columna<Carga>[] = [
  {
    clave: "carga",
    titulo: "Carga",
    celda: (carga) => {
      const aspecto = ASPECTO_DE_ESTADO[carga.estado];
      const tono = TONO_DE_ICONO[aspecto.tono];
      return (
        <span className="ing-carga">
          <span
            className={tono === "" ? "ing-carga__ico" : `ing-carga__ico ing-carga__ico--${tono}`}
          >
            <Icono nombre={aspecto.icono} />
          </span>
          <span>
            <b className="ing-carga__nombre">
              {carga.es_reproceso ? "Reproceso" : "Carga de planilla"}
            </b>
            <span className="ing-carga__ref">{formatearFechaHora(carga.created_at)}</span>
          </span>
        </span>
      );
    },
  },
  {
    clave: "filas",
    titulo: "Filas",
    // El criterio de HU-E3-03: «indicando la cantidad de filas validas y fallidas».
    celda: (carga) => (
      <span className="ing-filas">{`${carga.filas_ok} de ${carga.filas_totales}`}</span>
    ),
  },
  {
    clave: "errores",
    titulo: "Con error",
    celda: (carga) => <span className="ing-filas">{carga.filas_error}</span>,
  },
  {
    clave: "estado",
    titulo: "Estado",
    celda: (carga) => (
      <Badge estado={ASPECTO_DE_ESTADO[carga.estado].tono}>
        {ETIQUETAS_DE_ESTADO[carga.estado]}
      </Badge>
    ),
  },
  {
    clave: "detalle",
    titulo: "Detalle",
    alDerecha: true,
    celda: (carga) => <Link href={`/ingesta/${carga.id}`}>Ver detalle</Link>,
  },
];

export function IngestaDePlanillas({
  inicial,
  cargasIniciales,
  puedeEditar,
}: PropsDeIngesta): JSX.Element {
  const [listado, setListado] = useState<ListadoDeVinculos>(inicial);
  const [cargas, setCargas] = useState<readonly Carga[]>(cargasIniciales);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [arrastrando, setArrastrando] = useState(false);
  const [pidiendoEnlace, setPidiendoEnlace] = useState(false);
  const [enlace, setEnlace] = useState("");
  const [errorDelEnlace, setErrorDelEnlace] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  async function refrescar(): Promise<void> {
    setListado(await listarPlanillas());
    setCargas((await listarCargas()).cargas);
  }

  async function procesar(vinculo: Vinculo): Promise<void> {
    setError(null);
    setAviso(null);
    try {
      await procesarPlanilla(vinculo.id);
      // 202: el trabajo fue aceptado, no hecho. Decir «procesada» aca seria mentir sobre
      // una importacion que recien empieza (HU-E3-03 RN-01).
      setAviso("Empezamos a procesar la planilla. El resultado va a aparecer en Cargas recientes.");
      await refrescar();
    } catch (problema) {
      reportar(problema);
    }
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

  /**
   * Pedir la planilla antes de salir hacia Google.
   *
   * En el flujo real el archivo se elige en el selector de Google, y el identificador lo
   * conoce el panel. Pedir el enlace acá es la misma decisión tomada por el mismo actor —
   * y sin esto la pantalla vinculaba una planilla que nadie eligió.
   */
  async function vincularConGoogle(): Promise<void> {
    const identificador = identificadorDePlanilla(enlace);
    if (identificador === null) {
      setErrorDelEnlace("Escribí un enlace de Google Sheets o un nombre para la planilla.");
      return;
    }
    setErrorDelEnlace(null);
    setError(null);
    try {
      window.location.href = await iniciarVinculacionConGoogle(identificador);
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
        <span className="ing-carga">
          <span className="ing-carga__ico">
            <Icono nombre={vinculo.proveedor === "ARCHIVO" ? "documento" : "planilla"} />
          </span>
          <span>
            <b className="ing-carga__nombre">
              {vinculo.nombre_archivo ?? vinculo.identificador_externo ?? vinculo.hoja_empresa}
            </b>
            <span className="ing-carga__ref">{ETIQUETAS_DE_PROVEEDOR[vinculo.proveedor]}</span>
          </span>
        </span>
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
      <>
        {/* El estado «Falta mapear» tiene que llevar a algún lado: sin este enlace la fila
            sólo ofrecía desvincular, que es lo contrario de lo que quiere alguien que acaba
            de subir el archivo.

            Se ofrece **siempre**, y no sólo cuando falta el mapeo, porque `tiene_mapeo` dice
            que hay uno, no que esté confirmado. Un mapeo propuesto y sin confirmar no se
            puede procesar —el caso de uso lo rechaza— y esconder el enlace justo ahí dejaría
            la fila sin ninguna salida hacia adelante. */}
        {vinculo.nombre_archivo !== null && (
          <Link className="ing-accion" href={`/ingesta/mapeo/${vinculo.id}`}>
            Revisar mapeo
          </Link>
        )}
        {vinculo.tiene_mapeo && (
          <Button
            variante="secundario"
            onClick={() => {
              void procesar(vinculo);
            }}
          >
            Procesar
          </Button>
        )}
        <Button
          variante="destructivo"
          confirmacion="Vas a desvincular esta planilla. Los datos que ya se importaron se quedan; solo se corta la conexion."
          onClick={() => {
            void desvincular(vinculo);
          }}
        >
          Desvincular
        </Button>
      </>
    ),
  };

  const columnas = puedeEditar ? [...columnasBase, columnaDeAcciones] : columnasBase;

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      {puedeEditar && (
        <>
          <div
            className={arrastrando ? "ing-dropzone ing-dropzone--activa" : "ing-dropzone"}
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
            <span className="ing-dz-ico">
              <Icono nombre="nube" />
            </span>
            <p className="ing-dz-titulo">Arrastrá tu planilla acá</p>
            <p className="ing-dz-sub">
              Formatos aceptados: {EXTENSIONES_ACEPTADAS.join(", ")} · tamaño máximo{" "}
              {LIMITE_TAMANO_MB} MB
            </p>
            <div className="ing-dz-acciones">
              {/* El label es el botón y el input de verdad vive adentro: un solo control,
                  nativo, que el teclado alcanza y el lector de pantalla anuncia. */}
              <label className="ing-archivo">
                <Icono nombre="archivo" />
                Seleccionar archivo
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
              </label>
              <span className="ing-dz-o">o</span>
              <Button
                variante="secundario"
                disabled={subiendo}
                onClick={() => {
                  setErrorDelEnlace(null);
                  setPidiendoEnlace(true);
                }}
              >
                Vincular Google Sheets
              </Button>
            </div>
            <p className="ing-candado">
              <Icono nombre="candado" />
              Te vamos a pedir permiso de lectura <strong>sobre la planilla que elijas</strong>, no
              sobre todo tu Drive.
            </p>
            {subiendo && <p role="status">Subiendo la planilla…</p>}
          </div>

          {/* Qué campos reconoce el modelo, dicho antes de subir y no después de fallar
              (HU-E3-01 RN-01): saber que el orden y el nombre de las columnas no importan es
              justo lo que evita que alguien reordene su planilla a mano. */}
          <div className="ing-detect">
            <span className="ing-detect__ico">
              <Icono nombre="chispa" />
            </span>
            <span>
              <b className="ing-detect__titulo">La IA va a detectar automáticamente</b>
              <span className="ing-detect__sub">
                Sin importar el orden o el nombre exacto de tus columnas
              </span>
            </span>
            <ul className="ing-chips">
              {ATRIBUTOS_DE_CLIENTE.map((atributo) => (
                <li key={atributo} className="ing-chip">
                  {ETIQUETAS_DE_ATRIBUTO[atributo] ?? atributo}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      <Modal
        abierto={pidiendoEnlace}
        titulo="Vincular una planilla de Google"
        onCerrar={() => {
          setPidiendoEnlace(false);
        }}
      >
        <p className="ing-modal__texto">
          Pegá el enlace de la planilla que querés traer. Te vamos a pedir permiso de lectura{" "}
          <strong>sobre ésa</strong>, no sobre todo tu Drive.
        </p>
        <Campo
          id="enlace-de-planilla"
          etiqueta="Enlace o nombre de la planilla"
          placeholder="https://docs.google.com/spreadsheets/d/…"
          ayuda="Pegá el enlace de Google Sheets, o escribí un nombre para reconocerla en el listado."
          value={enlace}
          error={errorDelEnlace ?? undefined}
          onChange={(evento) => {
            setEnlace(evento.target.value);
            setErrorDelEnlace(null);
          }}
        />
        <div className="ing-modal__acciones">
          <Button
            variante="secundario"
            onClick={() => {
              setPidiendoEnlace(false);
            }}
          >
            Cancelar
          </Button>
          <Button
            onClick={() => {
              void vincularConGoogle();
            }}
          >
            Continuar
          </Button>
        </div>
      </Modal>

      {/* Las dos tablas van en tarjeta y con encabezado visible: `Tabla` pone su título en un
          `<caption>` oculto, así que sin esto quien mira la pantalla ve dos rejillas seguidas y
          tiene que deducir dónde termina una. */}
      <Card>
        <div className="ing-seccion">
          <div>
            <h2 className="ing-seccion__titulo">Planillas vinculadas</h2>
            <p className="ing-seccion__sub">Las fuentes desde las que entran tus datos</p>
          </div>
        </div>
        <Tabla
          titulo="Planillas vinculadas"
          columnas={columnas}
          filas={listado.vinculos}
          claveDeFila={(vinculo) => vinculo.id}
          vacia="Todavia no vinculaste ninguna planilla."
        />
      </Card>

      <Card>
        <div className="ing-seccion">
          <div>
            <h2 className="ing-seccion__titulo">Cargas recientes</h2>
            <p className="ing-seccion__sub">Tus últimas ingestas de datos</p>
          </div>
        </div>
        <Tabla
          titulo="Cargas recientes"
          columnas={COLUMNAS_DE_CARGA}
          filas={cargas}
          claveDeFila={(carga) => carga.id}
          vacia="Todavia no procesaste ninguna planilla."
        />
      </Card>
    </>
  );
}
