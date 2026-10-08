/**
 * Advertencia de PAN-CFG-NOT sobre el recordatorio de turno (U8, D-U8-18).
 *
 * Fuera de la ventana de 24 horas de Meta solo se aceptan plantillas aprobadas. Un recordatorio
 * de 24 h casi nunca cae dentro de esa ventana: si `recordatorio_de_turno` no está aprobada, el
 * recordatorio falla (error 131047 de Meta) para casi todos los clientes. La pantalla lo dice.
 *
 * Se apoya en el estado que el listado ya trae desde U6; no pide nada más.
 */

import type { Plantilla } from "../api/faq";
import { Alert } from "@/shared";

export const CODIGO_DEL_RECORDATORIO = "recordatorio_de_turno";

export const MENSAJE_RECORDATORIO_SIN_APROBAR =
  "La plantilla «recordatorio de turno» no está aprobada en Meta. Fuera de la ventana de 24 horas " +
  "Meta solo acepta plantillas aprobadas, así que los recordatorios de turno no van a llegar a " +
  "los clientes que no te escribieron en el último día.";

export interface PropsDeAdvertenciaDeRecordatorio {
  readonly plantillas: readonly Plantilla[];
}

export function AdvertenciaDeRecordatorio({
  plantillas,
}: PropsDeAdvertenciaDeRecordatorio): JSX.Element | null {
  const recordatorio = plantillas.find(
    (plantilla) => plantilla.codigo === CODIGO_DEL_RECORDATORIO && plantilla.canal === "WHATSAPP",
  );
  if (recordatorio !== undefined && recordatorio.estado_aprobacion === "APROBADA") {
    return null;
  }
  return (
    <Alert tono="advertencia" titulo="Los recordatorios de turno pueden no llegar">
      {MENSAJE_RECORDATORIO_SIN_APROBAR}
    </Alert>
  );
}
