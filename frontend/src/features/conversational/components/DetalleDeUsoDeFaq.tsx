/**
 * El detalle de uso de una respuesta frecuente (HU-E9-04 RN-02, RN-06, RN-07; ADR-0012).
 *
 * **No calcula nada**: muestra lo que da la API. Los conteos y la participación los resuelve el
 * backend con los meses en hora de Argentina; acá solo se les da forma de texto.
 *
 * Es una tarjeta a la vista y no un modal, por la misma razón que el formulario: mirar cuánto se
 * usa una respuesta es compararla con las demás, y un modal tapa el listado.
 */

import { formatearFecha, formatearNumero } from "@/shared";

import {
  MENSAJE_EDICION_RECIENTE,
  MENSAJE_SIN_CONSULTAS,
  MENSAJE_SIN_EDICIONES,
  MENSAJE_SIN_HISTORIA_PREVIA,
} from "../api/faq";
import type { DetalleDeUso, Faq, MotivoSinComparacion, ParticipacionDeFaq } from "../api/faq";

export interface PropsDeDetalleDeUsoDeFaq {
  readonly faq: Faq;
  readonly detalle: DetalleDeUso;
  readonly onCerrar: () => void;
}

const MOTIVOS: Readonly<Record<MotivoSinComparacion, string>> = {
  SIN_EDICIONES: MENSAJE_SIN_EDICIONES,
  EDICION_RECIENTE: MENSAJE_EDICION_RECIENTE,
  SIN_HISTORIA_PREVIA: MENSAJE_SIN_HISTORIA_PREVIA,
};

/** «12,5 %» o, si no hubo consultas con FAQ en el lapso, la frase: nunca un 0 % inventado. */
function porcentaje(participacion: ParticipacionDeFaq): string {
  return participacion.participacion === null
    ? MENSAJE_SIN_CONSULTAS
    : `${formatearNumero(participacion.participacion, undefined, 1)} %`;
}

function dias(cantidad: number): string {
  return cantidad === 1 ? "el día" : `los ${cantidad} días`;
}

function veces(cantidad: number): string {
  return cantidad === 1 ? "1 vez" : `${cantidad} veces`;
}

export function DetalleDeUsoDeFaq({
  faq,
  detalle,
  onCerrar,
}: PropsDeDetalleDeUsoDeFaq): JSX.Element {
  const { comparacion, motivo_sin_comparacion: motivo } = detalle;
  return (
    <section className="faq-form" aria-labelledby="faq-uso-titulo">
      <header className="faq-form__head">
        <div>
          <p className="faq-form__eyebrow">Uso de la respuesta</p>
          <h2 className="faq-form__titulo" id="faq-uso-titulo">
            {faq.pregunta}
          </h2>
        </div>
      </header>

      <div className="faq-form__cuerpo">
        <p>Respondida {veces(detalle.usos_este_mes)} este mes</p>
        <p>
          Mes anterior: <b>{detalle.usos_mes_anterior}</b> · Total: <b>{detalle.usos_total}</b>
        </p>
        {comparacion !== null && (
          <p>
            {`Participación: ${porcentaje(comparacion.antes)} en ${dias(comparacion.dias)} antes de la edición del ${formatearFecha(detalle.editada_en)} · ${porcentaje(comparacion.despues)} en ${dias(comparacion.dias)} después`}
          </p>
        )}
        {motivo !== null && <p>{MOTIVOS[motivo]}</p>}
        <div className="faq-form__pie">
          <button type="button" className="faq-accion" onClick={onCerrar}>
            Cerrar
          </button>
        </div>
      </div>
    </section>
  );
}
