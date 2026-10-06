/**
 * PAN-WA-02 — Agente WhatsApp · Configuración (HU-E9-04).
 *
 * Los cuatro criterios de la historia: el alta con contadores en cero, el rechazo de los campos
 * vacíos con su frase, la baja con confirmación, y los usos por FAQ («Este mes», «Mes anterior»
 * y «Total»; ADR-0012) con un detalle de su participación antes y después de editarla.
 *
 * **El encabezado lo dibuja este componente y no la página.** El CTA depende del rol y abre el
 * formulario, así que necesita estado; dejar el título en el server component y el botón acá
 * los separaba en dos bloques, y el botón terminaba flotando solo arriba del listado sin
 * pertenecer a nada. Título, bajada y acción son una sola pieza.
 *
 * **El alta y la edición son una tarjeta a la vista, no un modal.** Escribir una respuesta es
 * mirar las que ya existen —para no repetir una y para copiar el tono—, y un modal tapa
 * justamente eso. La baja sí interrumpe: ahí la interrupción es el punto.
 *
 * **`sin_indexar` se muestra**, y es lo único de esta pantalla que no pide la historia. Una FAQ
 * guardada mientras el proveedor de embeddings estaba caído existe, se lee y se edita — lo
 * único que no puede es encontrarse por significado. Decirlo es la diferencia entre «el agente
 * todavía no la usa» y «el agente la ignora y no sé por qué».
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Modal, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ErrorDeFaq,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  MENSAJE_CONFIRMAR_BAJA,
  MENSAJE_SIN_FAQS,
  crearFaq,
  editarFaq,
  eliminarFaq,
  listarFaqs,
  verUsoDeFaq,
} from "../api/faq";
import type { DetalleDeUso, Faq, ListadoDeFaqs } from "../api/faq";
import { DetalleDeUsoDeFaq } from "./DetalleDeUsoDeFaq";

export interface PropsDeRespuestasFrecuentes {
  readonly inicial: ListadoDeFaqs;
  /** Sólo el Administrador administra; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

/** «1 respuesta» y no «1 respuestas»: el contador se lee, y un plural mal puesto se nota. */
function palabra(cantidad: number, singular: string, plural: string): string {
  return cantidad === 1 ? singular : plural;
}

export function RespuestasFrecuentes({
  inicial,
  puedeEditar,
}: PropsDeRespuestasFrecuentes): JSX.Element {
  const [listado, setListado] = useState<ListadoDeFaqs>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  const [editando, setEditando] = useState<Faq | null>(null);
  const [creando, setCreando] = useState(false);
  const [pregunta, setPregunta] = useState("");
  const [respuesta, setRespuesta] = useState("");
  const [aConfirmar, setAConfirmar] = useState<Faq | null>(null);
  const [viendoUso, setViendoUso] = useState<{ faq: Faq; detalle: DetalleDeUso } | null>(null);

  const incompleta = pregunta.trim() === "" || respuesta.trim() === "";
  const faqs = listado.faqs;
  const usos = faqs.reduce((total, una) => total + una.usos_este_mes, 0);
  const sinIndexar = faqs.filter((una) => una.sin_indexar).length;

  async function correr(accion: () => Promise<unknown>, porDefecto: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await accion();
      setListado(await listarFaqs());
    } catch (fallo) {
      setError(fallo instanceof ErrorDeFaq ? fallo.message : porDefecto);
    } finally {
      setTrabajando(false);
    }
  }

  async function abrirUso(faq: Faq): Promise<void> {
    setError(null);
    try {
      setViendoUso({ faq, detalle: await verUsoDeFaq(faq.id) });
    } catch (fallo) {
      setError(fallo instanceof ErrorDeFaq ? fallo.message : "No se pudo cargar el uso.");
    }
  }

  function abrirAlta(): void {
    setEditando(null);
    setPregunta("");
    setRespuesta("");
    setCreando(true);
  }

  function abrirEdicion(faq: Faq): void {
    setEditando(faq);
    setPregunta(faq.pregunta);
    setRespuesta(faq.respuesta);
    setCreando(true);
  }

  // «Ver uso» es de todos los roles (la historia deja leer el uso a quien lee el listado);
  // «Editar» y «Eliminar» solo se dibujan para quien puede editar, así que nadie ve una celda
  // con botones que no puede usar.
  const acciones: Columna<Faq> = {
    clave: "acciones",
    titulo: "Acciones",
    alDerecha: true,
    celda: (fila) => (
      <span className="tabla__acciones">
        <button type="button" className="faq-accion" onClick={() => void abrirUso(fila)}>
          Ver uso
        </button>
        {puedeEditar && (
          <>
            <button type="button" className="faq-accion" onClick={() => abrirEdicion(fila)}>
              Editar
            </button>
            <button
              type="button"
              className="faq-accion faq-accion--baja"
              onClick={() => setAConfirmar(fila)}
            >
              Eliminar
            </button>
          </>
        )}
      </span>
    ),
  };

  const columnas: readonly Columna<Faq>[] = [
    {
      clave: "pregunta",
      titulo: "Pregunta",
      celda: (fila) => (
        <span className="faq-q">
          {/* El signo del prototipo. Va oculto para un lector de pantalla: la columna ya
              dice «Pregunta», y anunciar «?» antes de cada fila sólo alarga la escucha. */}
          <span className="faq-q__marca" aria-hidden="true">
            ?
          </span>
          <span className="faq-q__texto">{fila.pregunta}</span>
        </span>
      ),
    },
    {
      clave: "respuesta",
      titulo: "Respuesta",
      // El texto entero viaja al DOM y lo recorta la hoja de estilos; cortarlo acá con
      // `slice` lo perdería también para quien escucha la pantalla.
      celda: (fila) => <span className="faq-frag">{fila.respuesta}</span>,
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) =>
        fila.sin_indexar ? (
          <Badge estado="atencion">Todavía no buscable</Badge>
        ) : (
          <Badge estado="ok">Disponible</Badge>
        ),
    },
    {
      clave: "usos_este_mes",
      titulo: "Este mes",
      alDerecha: true,
      celda: (fila) => <span className="faq-usos">{fila.usos_este_mes}</span>,
    },
    {
      clave: "usos_mes_anterior",
      titulo: "Mes anterior",
      alDerecha: true,
      celda: (fila) => <span className="faq-usos">{fila.usos_mes_anterior}</span>,
    },
    {
      clave: "usos_total",
      titulo: "Total",
      alDerecha: true,
      celda: (fila) => <span className="faq-usos">{fila.usos_total}</span>,
    },
    acciones,
  ];

  return (
    <>
      <header className="faq-encabezado">
        <div>
          <p className="faq-encabezado__eyebrow">Agente WhatsApp · Configuración</p>
          <h1>Respuestas frecuentes</h1>
          <p className="faq-encabezado__intro">
            Lo que el agente contesta solo. Busca por significado, así que no hace falta que el
            cliente escriba la pregunta igual; cuando ninguna alcanza, deriva a una persona.
          </p>
        </div>
        {puedeEditar && (
          <div className="faq-encabezado__acciones">
            <Button onClick={abrirAlta}>Agregar respuesta</Button>
          </div>
        )}
      </header>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {!puedeEditar && (
        // No se esconde el listado: las respuestas y su uso son información del negocio, y
        // todos los roles la ven. Lo que no se puede es editarlas, y se dice acá en vez de
        // que alguien lo descubra buscando un botón que no está.
        <Alert tono="neutral">
          Con tu rol podés leer las respuestas y cuánto se usan, pero no editarlas.
        </Alert>
      )}

      {creando && (
        <section className="faq-form" aria-labelledby="faq-form-titulo">
          <header className="faq-form__head">
            <div>
              <p className="faq-form__eyebrow">Respuestas frecuentes</p>
              <h2 className="faq-form__titulo" id="faq-form-titulo">
                {editando === null ? "Agregar respuesta" : "Editar respuesta"}
              </h2>
            </div>
          </header>

          <form
            className="faq-form__cuerpo"
            onSubmit={(evento) => {
              evento.preventDefault();
              void correr(async () => {
                if (editando === null) {
                  await crearFaq(pregunta, respuesta);
                } else {
                  await editarFaq(editando.id, pregunta, respuesta);
                }
                setCreando(false);
              }, "No se pudo guardar la respuesta.");
            }}
          >
            <p className="faq-form__ayuda">
              La pregunta es lo que el agente compara con lo que escribe el cliente; la respuesta se
              manda <strong>tal cual</strong>, sin que ningún modelo la reescriba.
            </p>

            <Campo
              id="faq-pregunta"
              etiqueta="Pregunta disparadora"
              value={pregunta}
              onChange={(evento) => setPregunta(evento.target.value)}
            />

            {/* Un `textarea` y no el `Campo` del catálogo: una respuesta es un párrafo, y un
                input de una línea esconde todo menos las últimas palabras justo cuando hay
                que releerlas. Lleva las clases del catálogo para heredar borde y foco. */}
            <div className="campo">
              <label className="campo__etiqueta" htmlFor="faq-respuesta">
                Respuesta
              </label>
              <textarea
                id="faq-respuesta"
                className="campo__control faq-area"
                rows={4}
                value={respuesta}
                onChange={(evento) => setRespuesta(evento.target.value)}
              />
            </div>

            <div className="faq-form__pie">
              {incompleta && <p className="faq-form__aviso">{MENSAJE_CAMPOS_OBLIGATORIOS}</p>}
              <button type="button" className="faq-accion" onClick={() => setCreando(false)}>
                Cancelar
              </button>
              <Button type="submit" disabled={incompleta} cargando={trabajando}>
                Guardar
              </Button>
            </div>
          </form>
        </section>
      )}

      {viendoUso !== null && (
        <DetalleDeUsoDeFaq
          faq={viendoUso.faq}
          detalle={viendoUso.detalle}
          onCerrar={() => setViendoUso(null)}
        />
      )}

      <div className="faq-barra">
        <p className="faq-barra__cuenta">
          <b>{faqs.length}</b> {palabra(faqs.length, "respuesta", "respuestas")} · <b>{usos}</b>{" "}
          {palabra(usos, "uso", "usos")} este mes
        </p>
      </div>

      <div className="faq-panel">
        <Tabla
          titulo="Respuestas frecuentes"
          columnas={columnas}
          filas={faqs}
          claveDeFila={(fila) => fila.id}
          vacia={MENSAJE_SIN_FAQS}
        />

        {sinIndexar > 0 && (
          // Al pie de la tabla y no en una tarjeta aparte: es una nota sobre las filas de
          // arriba, y en su propia caja quedaba lejos de lo que está explicando.
          <p className="faq-nota">
            <span className="faq-nota__marca" aria-hidden="true">
              ●
            </span>
            Estas respuestas están guardadas y se pueden editar, pero el agente todavía no las
            encuentra por significado. Se resuelve solo en la próxima pasada del sistema.
          </p>
        )}
      </div>

      <Modal
        abierto={aConfirmar !== null}
        titulo="Eliminar respuesta"
        onCerrar={() => setAConfirmar(null)}
      >
        {/* HU-E9-04, cuarto criterio: el sistema pide confirmación. Y la frase dice lo que
            pasa —el agente deja de usarla de inmediato— en vez de un «¿seguro?» genérico. */}
        <p className="faq-modal__texto">{MENSAJE_CONFIRMAR_BAJA}</p>
        <p className="faq-modal__pregunta">{aConfirmar?.pregunta}</p>
        <div className="faq-modal__acciones">
          <button type="button" className="faq-accion" onClick={() => setAConfirmar(null)}>
            Cancelar
          </button>
          <Button
            variante="destructivo"
            cargando={trabajando}
            onClick={() =>
              void correr(async () => {
                await eliminarFaq(aConfirmar?.id ?? "");
                setAConfirmar(null);
              }, "No se pudo eliminar la respuesta.")
            }
          >
            Eliminar
          </Button>
        </div>
      </Modal>
    </>
  );
}
