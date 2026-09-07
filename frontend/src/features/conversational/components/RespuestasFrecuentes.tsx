/**
 * PAN-WA-02 — Agente WhatsApp · Configuración (HU-E9-04).
 *
 * Los cuatro criterios de la historia: el alta con contador en cero, el rechazo de los campos
 * vacíos con su frase, la baja con confirmación, y el contador de usos por FAQ.
 *
 * **`sin_indexar` se muestra**, y es lo único de esta pantalla que no pide la historia. Una FAQ
 * guardada mientras el proveedor de embeddings estaba caído existe, se lee y se edita — lo
 * único que no puede es encontrarse por significado. Decirlo es la diferencia entre «el agente
 * todavía no la usa» y «el agente la ignora y no sé por qué».
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Modal, Tabla } from "@/shared";
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
} from "../api/faq";
import type { Faq, ListadoDeFaqs } from "../api/faq";

export interface PropsDeRespuestasFrecuentes {
  readonly inicial: ListadoDeFaqs;
  /** Sólo el Administrador administra; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
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

  const incompleta = pregunta.trim() === "" || respuesta.trim() === "";

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

  const columnas: readonly Columna<Faq>[] = [
    { clave: "pregunta", titulo: "Pregunta", celda: (fila) => fila.pregunta },
    { clave: "respuesta", titulo: "Respuesta", celda: (fila) => fila.respuesta },
    {
      clave: "usos",
      titulo: "Usos en el período",
      alDerecha: true,
      celda: (fila) => String(fila.usos),
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
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <>
            <Button variante="secundario" onClick={() => abrirEdicion(fila)}>
              Editar
            </Button>
            <Button variante="destructivo" onClick={() => setAConfirmar(fila)}>
              Eliminar
            </Button>
          </>
        ) : null,
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {puedeEditar && (
        <div className="fac-acciones">
          <Button onClick={abrirAlta}>Agregar respuesta</Button>
        </div>
      )}

      <Tabla
        titulo="Respuestas frecuentes"
        columnas={columnas}
        filas={listado.faqs}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_FAQS}
      />

      {listado.faqs.some((una) => una.sin_indexar) && (
        <Card titulo="Respuestas todavía no buscables">
          <p className="dm-intro">
            Estas respuestas están guardadas y se pueden editar, pero el agente todavía no las
            encuentra por significado. Se resuelve solo en la próxima pasada del sistema.
          </p>
        </Card>
      )}

      <Modal
        abierto={creando}
        titulo={editando === null ? "Agregar respuesta" : "Editar respuesta"}
        onCerrar={() => setCreando(false)}
      >
        <form
          className="dm-formulario"
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
          <p className="dm-intro">
            La pregunta es lo que el agente compara con lo que escribe el cliente; la respuesta se
            manda <strong>tal cual</strong>, sin que ningún modelo la reescriba.
          </p>
          <Campo
            id="faq-pregunta"
            etiqueta="Pregunta disparadora"
            value={pregunta}
            onChange={(evento) => setPregunta(evento.target.value)}
          />
          <Campo
            id="faq-respuesta"
            etiqueta="Respuesta"
            value={respuesta}
            onChange={(evento) => setRespuesta(evento.target.value)}
          />
          {incompleta && <Alert tono="neutral">{MENSAJE_CAMPOS_OBLIGATORIOS}</Alert>}
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setCreando(false)}>
              Volver
            </Button>
            <Button type="submit" disabled={incompleta} cargando={trabajando}>
              Guardar
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        abierto={aConfirmar !== null}
        titulo="Eliminar respuesta"
        onCerrar={() => setAConfirmar(null)}
      >
        {/* HU-E9-04, cuarto criterio: el sistema pide confirmación. Y la frase dice lo que
            pasa —el agente deja de usarla de inmediato— en vez de un «¿seguro?» genérico. */}
        <p className="dm-intro">{MENSAJE_CONFIRMAR_BAJA}</p>
        <p className="fac-mono">{aConfirmar?.pregunta}</p>
        <div className="dm-formulario__acciones">
          <Button variante="secundario" onClick={() => setAConfirmar(null)}>
            Volver
          </Button>
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
