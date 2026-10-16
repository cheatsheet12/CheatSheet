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
 *
 * **Es una columna de tres pisos**: cabecera con el estado y la acción principal, historial
 * con su propio scroll y, abajo, lo que el operador hace (responder, cerrar). Así la caja de
 * respuesta queda a la vista mientras se lee el último mensaje.
 */

"use client";

import Link from "next/link";
import { useContext, useEffect, useRef, useState } from "react";

import { Alert, Button, Select } from "@/shared";

import {
  ErrorDeConversacion,
  cerrarEscalamiento,
  responder,
  tomarEscalamiento,
  verConversacion,
} from "../api/conversacion";
import type { DetalleDeConversacion, Intencion } from "../api/conversacion";
import { ContextoDeAvisoDeBandeja } from "./AvisoDeBandeja";
import { CajaDeRespuesta } from "./CajaDeRespuesta";
import { etiquetaDe, tituloDe, tonoDeEstadoDe } from "./FilaDeConversacion";
import { IconoDeBurbuja, IconoDeBurbujas, IconoDeVolver } from "./iconos";
import { LineaDeTiempo } from "./LineaDeTiempo";
import { tonoDe } from "./vista";

export interface PropsDeHiloDeConversacion {
  readonly inicial: DetalleDeConversacion;
  readonly puedeAtender: boolean;
}

const CLASIFICACIONES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Que reevalúe el agente" },
  { valor: "TURNO", etiqueta: "Turno" },
  { valor: "CONSULTA", etiqueta: "Consulta" },
  { valor: "PAGO", etiqueta: "Pago" },
  { valor: "FAQ", etiqueta: "Pregunta frecuente" },
];

export function HiloDeConversacion({
  inicial,
  puedeAtender,
}: PropsDeHiloDeConversacion): JSX.Element {
  const [hilo, setHilo] = useState<DetalleDeConversacion>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [clasificacion, setClasificacion] = useState("");
  const [trabajando, setTrabajando] = useState(false);
  const cuerpo = useRef<HTMLDivElement>(null);
  const { avisarCambio } = useContext(ContextoDeAvisoDeBandeja);

  const tomado = hilo.estado_escalamiento === "ASIGNADO";
  const esperando = hilo.estado_escalamiento === "ABIERTO";
  const cantidad = hilo.mensajes.length;

  // El historial abre en lo último que se dijo, como cualquier chat.
  useEffect(() => {
    const zona = cuerpo.current;
    if (zona !== null) {
      zona.scrollTop = zona.scrollHeight;
    }
  }, [cantidad]);

  async function correr(accion: () => Promise<unknown>, porDefecto: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await accion();
      setHilo(await verConversacion(hilo.id));
      // La bandeja de al lado muestra el mismo estado: que lo vuelva a pedir al backend.
      avisarCambio();
    } catch (fallo) {
      setError(fallo instanceof ErrorDeConversacion ? fallo.message : porDefecto);
    } finally {
      setTrabajando(false);
    }
  }

  const estado = tonoDeEstadoDe(hilo);

  return (
    <section className="cv-panel cv-conv" aria-label="Conversación">
      <header className="cv-conv__head">
        <Link href="/conversaciones" className="cv-conv__volver">
          <IconoDeVolver />
          Volver
        </Link>
        <span className={`cv-avatar cv-tono-${tonoDe(hilo.cliente_id)}`} aria-hidden="true">
          <IconoDeBurbuja />
        </span>
        <div className="cv-conv__quien">
          <h2 className="cv-conv__titulo">{tituloDe(hilo)}</h2>
          <span className="cv-conv__estado">
            <span className={`cv-pastilla cv-pastilla--${estado}`}>
              <span className="cv-pastilla__punto" aria-hidden="true" />
              {etiquetaDe(hilo)}
            </span>
            <span className="cv-conv__canal">WhatsApp</span>
          </span>
        </div>
        {puedeAtender && esperando && (
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
        )}
      </header>

      {(error !== null || esperando) && (
        <div className="cv-conv__avisos">
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
        </div>
      )}

      <div className="cv-conv__cuerpo" ref={cuerpo}>
        {cantidad === 0 ? (
          <div className="cv-conv__vacio">
            <span className="cv-vacio__icono" aria-hidden="true">
              <IconoDeBurbujas />
            </span>
            <p>Este hilo todavía no tiene mensajes.</p>
          </div>
        ) : (
          <LineaDeTiempo mensajes={hilo.mensajes} />
        )}
      </div>

      {puedeAtender && tomado && (
        <CajaDeRespuesta
          texto={texto}
          trabajando={trabajando}
          onCambio={setTexto}
          onEnviar={() =>
            void correr(async () => {
              await responder(hilo.id, texto);
              setTexto("");
            }, "No se pudo enviar el mensaje.")
          }
        />
      )}

      {puedeAtender && (esperando || tomado) && (
        <div className="cv-cierre">
          <div className="cv-cierre__texto">
            <b>Cerrar el escalamiento</b>
            <p>
              Devolverle la conversación al agente hace que <strong>reevalúe la intención</strong>{" "}
              del hilo. Podés corregir esa clasificación antes de devolverlo. Un escalamiento
              cerrado no se reabre: un pedido nuevo del cliente genera uno nuevo.
            </p>
          </div>
          <div className="cv-cierre__acciones">
            <Select
              id="hilo-clasificacion"
              etiqueta="Clasificación al devolver"
              opciones={CLASIFICACIONES}
              value={clasificacion}
              onChange={(evento) => setClasificacion(evento.target.value)}
            />
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
        </div>
      )}

      {!hilo.esta_escalada && (
        <div className="cv-conv__aviso-agente">Este hilo no tiene ningún escalamiento abierto.</div>
      )}
    </section>
  );
}
