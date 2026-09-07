/**
 * PAN-WA-01 — el hilo abierto (HU-E9-01, HU-E9-02).
 *
 * **El historial completo es la promesa de HU-E8-05 RN-03**: el cliente no tiene que repetir
 * nada. Por eso la pantalla muestra todo el hilo y no sólo lo que pasó después del
 * escalamiento.
 *
 * **Los mensajes del operador se distinguen de los del agente** (RN-04), y la marca viene del
 * backend: la pantalla no la deduce por el momento del escalamiento.
 *
 * **El campo de respuesta aparece recién con el escalamiento tomado.** Sin eso el agente sigue
 * contestando el mismo hilo, y el cliente tendría dos interlocutores — que es exactamente lo
 * que RN-02 evita. El backend lo rechaza igual; esconderlo es la cortesía.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Select, formatearFechaHora } from "@/shared";

import {
  ETIQUETAS_DE_INTENCION,
  ETIQUETAS_DE_ORIGEN,
  ErrorDeConversacion,
  cerrarEscalamiento,
  responder,
  tomarEscalamiento,
  verConversacion,
} from "../api/conversacion";
import type { DetalleDeConversacion, Intencion, Mensaje } from "../api/conversacion";

export interface PropsDeHiloDeConversacion {
  readonly inicial: DetalleDeConversacion;
  /** El número del cliente, resuelto del lado del servidor. */
  readonly telefono: string;
  readonly puedeAtender: boolean;
}

const CLASIFICACIONES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Que reevalúe el agente" },
  { valor: "TURNO", etiqueta: "Turno" },
  { valor: "CONSULTA", etiqueta: "Consulta" },
  { valor: "PAGO", etiqueta: "Pago" },
  { valor: "FAQ", etiqueta: "Pregunta frecuente" },
];

function autorDe(mensaje: Mensaje): string {
  if (mensaje.direccion === "ENTRANTE") {
    return "Cliente";
  }
  return mensaje.origen === null ? "Sistema" : ETIQUETAS_DE_ORIGEN[mensaje.origen];
}

export function HiloDeConversacion({
  inicial,
  telefono,
  puedeAtender,
}: PropsDeHiloDeConversacion): JSX.Element {
  const [hilo, setHilo] = useState<DetalleDeConversacion>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [clasificacion, setClasificacion] = useState("");
  const [trabajando, setTrabajando] = useState(false);

  const tomado = hilo.estado_escalamiento === "ASIGNADO";
  const esperando = hilo.estado_escalamiento === "ABIERTO";

  async function correr(accion: () => Promise<unknown>, porDefecto: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await accion();
      setHilo(await verConversacion(hilo.id));
    } catch (fallo) {
      setError(fallo instanceof ErrorDeConversacion ? fallo.message : porDefecto);
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {esperando && (
        <Alert tono="advertencia" titulo="Esperando a un asesor">
          {hilo.motivo}
        </Alert>
      )}

      <Card titulo="Historial">
        {/* El contexto previo de HU-E8-05 RN-03: todo el hilo, no sólo lo posterior al
            escalamiento. Es lo que evita que el cliente tenga que repetir. */}
        <ol className="wa-hilo">
          {hilo.mensajes.map((mensaje) => (
            <li
              key={mensaje.id}
              className={
                mensaje.direccion === "ENTRANTE" ? "wa-mensaje wa-mensaje--cliente" : "wa-mensaje"
              }
            >
              <p className="wa-mensaje__autor">
                {autorDe(mensaje)} · {formatearFechaHora(mensaje.momento)}
                {mensaje.intencion !== null && <> · {ETIQUETAS_DE_INTENCION[mensaje.intencion]}</>}
                {mensaje.tipo_contenido === "AUDIO" && <> · nota de voz transcripta</>}
              </p>
              <p>{mensaje.contenido}</p>
              {mensaje.estado_entrega !== null && (
                <p className="wa-mensaje__entrega">{mensaje.estado_entrega}</p>
              )}
            </li>
          ))}
        </ol>
        {hilo.mensajes.length === 0 && (
          <p className="dm-intro">Este hilo todavía no tiene mensajes.</p>
        )}
      </Card>

      {puedeAtender && esperando && (
        <div className="fac-acciones">
          <Button
            cargando={trabajando}
            onClick={() =>
              void correr(
                () => tomarEscalamiento(hilo.escalamiento_id ?? ""),
                "No se pudo tomar el escalamiento.",
              )
            }
          >
            Tomar la conversación
          </Button>
        </div>
      )}

      {puedeAtender && tomado && (
        <Card titulo="Responder">
          <p className="dm-intro">
            El agente <strong>no está contestando</strong> este hilo mientras vos lo tengas tomado.
            Tu mensaje sale por WhatsApp y se distingue del agente en el historial.
          </p>
          <form
            className="dm-formulario"
            onSubmit={(evento) => {
              evento.preventDefault();
              void correr(async () => {
                await responder(hilo.id, texto, telefono);
                setTexto("");
              }, "No se pudo enviar el mensaje.");
            }}
          >
            <Campo
              id="hilo-respuesta"
              etiqueta="Mensaje"
              value={texto}
              onChange={(evento) => setTexto(evento.target.value)}
            />
            <div className="dm-formulario__acciones">
              <Button type="submit" disabled={texto.trim() === ""} cargando={trabajando}>
                Enviar
              </Button>
            </div>
          </form>
        </Card>
      )}

      {puedeAtender && (esperando || tomado) && (
        <Card titulo="Cerrar el escalamiento">
          <p className="dm-intro">
            Devolverle la conversación al agente hace que <strong>reevalúe la intención</strong> del
            hilo. Podés corregir esa clasificación antes de devolverlo. Un escalamiento cerrado no
            se reabre: un pedido nuevo del cliente genera uno nuevo.
          </p>
          <Select
            id="hilo-clasificacion"
            etiqueta="Clasificación al devolver"
            opciones={CLASIFICACIONES}
            value={clasificacion}
            onChange={(evento) => setClasificacion(evento.target.value)}
          />
          <div className="dm-formulario__acciones">
            <Button
              cargando={trabajando}
              onClick={() =>
                void correr(
                  () =>
                    cerrarEscalamiento(
                      hilo.escalamiento_id ?? "",
                      true,
                      clasificacion === "" ? undefined : (clasificacion as Intencion),
                    ),
                  "No se pudo cerrar el escalamiento.",
                )
              }
            >
              Devolver al agente
            </Button>
            <Button
              variante="secundario"
              cargando={trabajando}
              onClick={() =>
                void correr(
                  () => cerrarEscalamiento(hilo.escalamiento_id ?? "", false),
                  "No se pudo cerrar el escalamiento.",
                )
              }
            >
              Dar por finalizada
            </Button>
          </div>
        </Card>
      )}

      {!hilo.esta_escalada && (
        <Alert tono="neutral">
          <Badge estado="ok">La atiende el agente</Badge> Este hilo no tiene ningún escalamiento
          abierto.
        </Alert>
      )}
    </>
  );
}
