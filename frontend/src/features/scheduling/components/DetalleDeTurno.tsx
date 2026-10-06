/**
 * PAN-AGE-02 — Agenda · Detalle de turno (HU-E7-02, HU-E7-03).
 *
 * «Veo su detalle y **las acciones disponibles según su estado**», dice el primer criterio de
 * HU-E7-02. Eso es lo que gobierna esta pantalla:
 *
 * - cancelar y reprogramar aparecen sólo sobre un turno Reservado o Confirmado;
 * - marcar asistencia aparece sólo cuando el turno **ya transcurrió** (HU-E7-03 RN-01), y
 *   cuando no, se dice por qué con la frase de la historia en lugar de esconder el botón sin
 *   explicación.
 *
 * Esconder es una cortesía: el caso de uso rechaza igual. Pero un botón que no está y no dice
 * por qué manda a alguien a recargar la página buscándolo.
 *
 * **Reprogramar no va al pasado** (D95): el campo lleva `min` = ahora, que es una cortesía — el
 * backend compara el instante y es quien rechaza. El Administrador tiene la excepción
 * «Corrección a posteriori», que quita el `min` y le pide al backend la franja ya terminada.
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Badge, Button, Campo, Card, Casilla, Modal, formatearFecha } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeTurno,
  MENSAJE_NO_TRANSCURRIO,
  cancelarTurno,
  horaDe,
  instanteDeAhora,
  registrarAsistencia,
  reprogramarTurno,
  tonoDeEstado,
} from "../api/turno";
import type { Turno } from "../api/turno";

export interface PropsDeDetalleDeTurno {
  readonly inicial: Turno;
  /** Administrador y Operador gestionan (HU-E7-02, HU-E7-03). */
  readonly puedeGestionar: boolean;
  /** El nombre del recurso, resuelto del lado del servidor. */
  readonly recurso: string;
  /** El nombre del servicio, ídem. */
  readonly servicio: string;
  /** Sólo el Administrador puede corregir a posteriori (HU-E7-02 RN-07). */
  readonly puedeRegistrarAPosteriori?: boolean;
}

export function DetalleDeTurno({
  inicial,
  puedeGestionar,
  recurso,
  servicio,
  puedeRegistrarAPosteriori = false,
}: PropsDeDetalleDeTurno): JSX.Element {
  const [turno, setTurno] = useState<Turno>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [reprogramando, setReprogramando] = useState(false);
  const [nuevoInicio, setNuevoInicio] = useState("");
  const [trabajando, setTrabajando] = useState(false);
  const [correccion, setCorreccion] = useState(false);
  // Después de montar y no en el render: el servidor puede estar en otra zona horaria.
  const [ahora, setAhora] = useState<string | undefined>(undefined);
  useEffect(() => {
    setAhora(instanteDeAhora());
  }, []);

  const abierto = turno.estado === "RESERVADO" || turno.estado === "CONFIRMADO";

  function mensajeDe(fallo: unknown, porDefecto: string): string {
    return fallo instanceof ErrorDeTurno ? fallo.message : porDefecto;
  }

  async function correr(accion: () => Promise<Turno>, porDefecto: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      setTurno(await accion());
      setReprogramando(false);
      setCorreccion(false);
    } catch (fallo) {
      setError(mensajeDe(fallo, porDefecto));
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

      {/*
       * La hora, la fecha y el estado suben a una tira propia y **salen de la lista de
       * abajo**: son las tres cosas que se miran mientras se habla por teléfono con alguien
       * que quiere cambiar el horario, y repetirlas en los dos lugares obligaría a mirar cuál
       * de las dos se actualizó después de reprogramar.
       */}
      <div className="age-turno">
        <p className="age-turno__hora">
          {horaDe(turno.inicio)}
          <span className="age-turno__fecha">
            {formatearFecha(turno.inicio)} · hasta {horaDe(turno.fin)}
          </span>
        </p>
        <span className="age-turno__estado">
          <Badge estado={tonoDeEstado(turno.estado)}>{ETIQUETAS_DE_ESTADO[turno.estado]}</Badge>
        </span>
      </div>

      <div className="fac-detalle">
        <Card titulo="Turno">
          <dl className="fac-datos">
            <dt>Servicio</dt>
            <dd>{servicio}</dd>
            <dt>Recurso</dt>
            <dd>{recurso}</dd>
            <dt>Origen</dt>
            {/* HU-E7-06 RN-02: distingue los turnos del panel de los del agente. */}
            <dd>{turno.canal_reserva === "PANEL" ? "Cargado desde el panel" : "Agente"}</dd>
            {turno.cobro_id !== null && (
              <>
                <dt>Seña</dt>
                <dd>
                  <a href={`/cobros/${turno.cobro_id}`}>Ver el cobro asociado</a>
                </dd>
              </>
            )}
          </dl>
        </Card>

        <Card titulo="Facturación">
          {turno.habilita_facturacion ? (
            <p className="dm-intro">
              El turno está completado, así que se puede emitir el comprobante del servicio.
            </p>
          ) : (
            <p className="dm-intro">
              Un turno habilita la emisión del comprobante cuando queda marcado como completado.
            </p>
          )}
        </Card>
      </div>

      {puedeGestionar && abierto && (
        <div className="fac-acciones">
          <Button variante="secundario" onClick={() => setReprogramando(true)}>
            Reprogramar
          </Button>
          <Button
            variante="destructivo"
            cargando={trabajando}
            onClick={() =>
              void correr(() => cancelarTurno(turno.id), "No se pudo cancelar el turno.")
            }
          >
            Cancelar turno
          </Button>
        </div>
      )}

      {puedeGestionar && abierto && !turno.ya_transcurrio && (
        // La frase de la historia, en lugar de un botón que no está y no se explica.
        <Alert tono="neutral">{MENSAJE_NO_TRANSCURRIO}</Alert>
      )}

      {puedeGestionar && abierto && turno.ya_transcurrio && (
        <div className="fac-acciones">
          <Button
            cargando={trabajando}
            onClick={() =>
              void correr(
                () => registrarAsistencia(turno.id, true),
                "No se pudo registrar la asistencia.",
              )
            }
          >
            Marcar completado
          </Button>
          <Button
            variante="secundario"
            cargando={trabajando}
            onClick={() =>
              void correr(
                () => registrarAsistencia(turno.id, false),
                "No se pudo registrar la inasistencia.",
              )
            }
          >
            No se presentó
          </Button>
        </div>
      )}

      <Modal
        abierto={reprogramando}
        titulo="Reprogramar turno"
        onCerrar={() => setReprogramando(false)}
      >
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void correr(
              () => reprogramarTurno(turno.id, new Date(nuevoInicio).toISOString(), correccion),
              "No se pudo reprogramar el turno.",
            );
          }}
        >
          <p className="dm-intro">
            El turno se mueve al horario nuevo y <strong>conserva su estado</strong>. Si la franja
            está ocupada, queda donde está.
          </p>
          <Campo
            id="turno-nuevo-inicio"
            etiqueta="Nuevo horario"
            type="datetime-local"
            min={correccion ? undefined : ahora}
            value={nuevoInicio}
            onChange={(evento) => setNuevoInicio(evento.target.value)}
          />
          {puedeRegistrarAPosteriori && (
            <Casilla
              id="turno-correccion-a-posteriori"
              checked={correccion}
              onChange={(evento) => setCorreccion(evento.target.checked)}
            >
              Corrección a posteriori: mover el turno a una franja que ya terminó, sin avisarle al
              cliente
            </Casilla>
          )}
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => setReprogramando(false)}>
              Volver
            </Button>
            <Button type="submit" disabled={nuevoInicio === ""} cargando={trabajando}>
              Confirmar
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
