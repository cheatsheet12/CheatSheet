/**
 * PAN-ING-01 — Ingesta de Datos · Carga (HU-E2-04, HU-E3-03).
 *
 * De arriba abajo: una franja con cuatro cifras, la zona principal en dos columnas (traer una
 * planilla, y «Cómo funciona»), las planillas vinculadas como tarjetas y las cargas recientes.
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

import {
  Alert,
  Badge,
  Button,
  Campo,
  Card,
  Modal,
  Tabla,
  formatearFechaHora,
  useAccionConNavegacion,
} from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import Link from "next/link";

import {
  ETIQUETAS_DE_ESTADO,
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
import { seleccionarPlanillaConGoogle, selectorGoogleConfigurado } from "../api/selectorGoogle";
import type { NombreDeIcono } from "./iconos";
import { ResumenDeIngesta, cifrasDeIngesta } from "./ResumenDeIngesta";
import { SeccionPlegable } from "./SeccionPlegable";
import { TarjetaDePlanilla } from "./TarjetaDePlanilla";

export interface PropsDeIngesta {
  readonly inicial: ListadoDeVinculos;
  /** `Cargas recientes` de PAN-ING-01. Lo lee todo rol (HU-E3-05 RN-04). */
  readonly cargasIniciales: readonly Carga[];
  readonly puedeEditar: boolean;
  /** Error de la vuelta OAuth, que llega como query param al recargar la página. */
  readonly errorInicial?: string | null;
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
            <span className="ing-carga__ref">
              {formatearFechaHora(carga.created_at).replace(", ", " · ")}
            </span>
          </span>
        </span>
      );
    },
  },
  {
    clave: "filas",
    titulo: "Filas",
    // El criterio de HU-E3-03: «indicando la cantidad de filas validas y fallidas».
    celda: (carga) => {
      // El porcentaje es sólo para la barra: el dato, para quien lee, es «98 de 100».
      const porcentaje =
        carga.filas_totales === 0 ? 0 : Math.round((carga.filas_ok / carga.filas_totales) * 100);
      return (
        <span className="ing-progreso">
          <span className="ing-filas">{`${carga.filas_ok} de ${carga.filas_totales}`}</span>
          <span
            className={carga.filas_error > 0 ? "ing-barra ing-barra--con-error" : "ing-barra"}
            aria-hidden="true"
          >
            <span className="ing-barra__relleno" style={{ width: `${porcentaje}%` }} />
          </span>
        </span>
      );
    },
  },
  {
    clave: "errores",
    titulo: "Con error",
    celda: (carga) => (
      <span className={carga.filas_error > 0 ? "ing-conteo ing-conteo--error" : "ing-conteo"}>
        {carga.filas_error}
      </span>
    ),
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
    celda: (carga) => (
      <Link className="ing-ver" href={`/ingesta/${carga.id}`}>
        Ver detalle
        <Icono nombre="flecha" />
      </Link>
    ),
  },
];

export function IngestaDePlanillas({
  inicial,
  cargasIniciales,
  puedeEditar,
  errorInicial = null,
}: PropsDeIngesta): JSX.Element {
  const [listado, setListado] = useState<ListadoDeVinculos>(inicial);
  const [cargas, setCargas] = useState<readonly Carga[]>(cargasIniciales);
  const [error, setError] = useState<string | null>(errorInicial);
  const [aviso, setAviso] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [arrastrando, setArrastrando] = useState(false);
  const [pidiendoEnlace, setPidiendoEnlace] = useState(false);
  const [enlace, setEnlace] = useState("");
  const [escribirDeVuelta, setEscribirDeVuelta] = useState(false);
  const [errorDelEnlace, setErrorDelEnlace] = useState<string | null>(null);
  const { pendiente: vinculando, ejecutar } = useAccionConNavegacion();
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
    let identificador: string | null = null;
    if (selectorGoogleConfigurado) {
      try {
        identificador = await seleccionarPlanillaConGoogle();
      } catch (problema) {
        reportar(problema);
        return;
      }
      if (identificador === null) return;
    } else {
      identificador = identificadorDePlanilla(enlace);
    }
    if (identificador === null) {
      setErrorDelEnlace("Escribí un enlace de Google Sheets o un nombre para la planilla.");
      return;
    }
    setErrorDelEnlace(null);
    setError(null);
    try {
      // A full-page navigation has no transition to wait on, so the button stays busy
      // until the page is gone (`saleDeLaPagina`) and is released only on failure. Two
      // requests would be two OAuth `state` values, and the cookie can keep the other one.
      await ejecutar(
        () =>
          iniciarVinculacionConGoogle(
            identificador,
            escribirDeVuelta ? "LECTURA_Y_ESCRITURA" : "SOLO_LECTURA",
          ),
        (direccion) => {
          window.location.href = direccion;
        },
        { saleDeLaPagina: true },
      );
    } catch (problema) {
      reportar(problema);
    }
  }

  async function desvincular(vinculo: Vinculo): Promise<void> {
    setError(null);
    try {
      await desvincularPlanilla(vinculo.id);
      await refrescar();
      setAviso("Se desvinculó la planilla. Los datos que ya se importaron siguen en el sistema.");
    } catch (problema) {
      reportar(problema);
    }
  }

  const cifras = cifrasDeIngesta(listado.vinculos, cargas);

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <ResumenDeIngesta cifras={cifras} />

      {puedeEditar && (
        <SeccionPlegable
          titulo="Subir una planilla"
          subtitulo="Arrastrá un archivo o vinculá una hoja de Google"
          icono="nube"
        >
          <div className="ing-principal">
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
              <p className="ing-dz-titulo">
                {arrastrando ? "Soltá la planilla para subirla" : "Arrastrá tu planilla acá"}
              </p>
              <p className="ing-dz-sub">
                {/* Los formatos y el tope, dichos una sola vez y como etiquetas: es lo que se
                  mira de un vistazo antes de elegir un archivo. */}
                <span className="ing-dz-formatos">
                  {EXTENSIONES_ACEPTADAS.map((extension) => (
                    <span key={extension} className="ing-dz-formato">
                      {extension}
                    </span>
                  ))}
                </span>
                <span className="ing-dz-limite">Hasta {LIMITE_TAMANO_MB} MB</span>
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
                  <Icono nombre="planilla" />
                  Vincular Google Sheets
                </Button>
              </div>
              <p className="ing-candado">
                <Icono nombre="candado" />
                <span>
                  Te vamos a pedir acceso <strong>sobre la planilla que elijas</strong>, no sobre
                  todo tu Drive.
                </span>
              </p>
              {subiendo && <p role="status">Subiendo la planilla…</p>}
            </div>
          </div>
        </SeccionPlegable>
      )}

      <Modal
        abierto={pidiendoEnlace}
        titulo="Vincular una planilla de Google"
        onCerrar={() => {
          setPidiendoEnlace(false);
        }}
      >
        <p className="ing-modal__texto">
          {selectorGoogleConfigurado
            ? "Elegí la planilla en Google Drive para conceder acceso a ese archivo."
            : "Pegá el enlace de la planilla que querés traer."}
        </p>
        {!selectorGoogleConfigurado && (
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
        )}
        <label>
          <input
            type="checkbox"
            checked={escribirDeVuelta}
            onChange={(evento) => setEscribirDeVuelta(evento.target.checked)}
          />
          Escribir registros del panel en la hoja de CheatSheet
        </label>
        {escribirDeVuelta && (
          <p className="ing-modal__texto">
            Crearemos una hoja separada para los registros del panel. La hoja original no se
            modifica.
          </p>
        )}
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
            cargando={vinculando}
            onClick={() => {
              void vincularConGoogle();
            }}
          >
            Continuar
          </Button>
        </div>
      </Modal>

      <SeccionPlegable
        titulo="Planillas vinculadas"
        subtitulo="Las fuentes desde las que entran tus datos"
        icono="planilla"
        cantidad={listado.vinculos.length}
      >
        {listado.vinculos.length === 0 ? (
          <EstadoVacio icono="planilla">Todavía no vinculaste ninguna planilla.</EstadoVacio>
        ) : (
          <ul className="ing-planes">
            {listado.vinculos.map((vinculo) => (
              <TarjetaDePlanilla
                key={vinculo.id}
                vinculo={vinculo}
                puedeEditar={puedeEditar}
                alProcesar={(elegido) => {
                  void procesar(elegido);
                }}
                alDesvincular={(elegido) => {
                  void desvincular(elegido);
                }}
              />
            ))}
          </ul>
        )}
      </SeccionPlegable>

      <SeccionPlegable
        titulo="Cargas recientes"
        subtitulo="Tus últimas ingestas de datos"
        icono="historial"
        cantidad={cargas.length}
      >
        {cargas.length === 0 ? (
          <EstadoVacio icono="historial">Todavía no procesaste ninguna planilla.</EstadoVacio>
        ) : (
          <div className="ing-tarjetas">
            <Card>
              <Tabla
                titulo="Cargas recientes"
                columnas={COLUMNAS_DE_CARGA}
                filas={cargas}
                claveDeFila={(carga) => carga.id}
                vacia="Todavía no procesaste ninguna planilla."
              />
            </Card>
          </div>
        )}
      </SeccionPlegable>
    </>
  );
}

/** El estado vacío de una sección: un icono y una frase, en una caja suave y no en una alarma. */
function EstadoVacio({
  icono,
  children,
}: {
  readonly icono: NombreDeIcono;
  readonly children: string;
}): JSX.Element {
  return (
    <div className="ing-vacio">
      <span className="ing-vacio__ico">
        <Icono nombre={icono} />
      </span>
      <p className="ing-vacio__texto">{children}</p>
    </div>
  );
}
