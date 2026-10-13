/**
 * El estado de una plantilla ante Meta, como lo lee el administrador (U6, PAN-CFG-NOT).
 *
 * Un badge por estado y, debajo, lo que Meta dijo: el motivo traducido, su texto **literal** y la
 * advertencia si la recategorizó como marketing. Se extrajo de `PlantillasDeNotificacion`, que con
 * tres estados nuevos, los motivos y el bloqueo de edición pasaba de las 400 líneas.
 */

import { Badge } from "@/shared";
import type { EstadoDeBadge } from "@/shared";
import { formatearFechaHora } from "@/shared";

import { ETIQUETAS_DE_APROBACION } from "../api/faq";
import type { EstadoDeAprobacion, Plantilla } from "../api/faq";
import { traducirMotivoDeMeta } from "../api/motivosDeMeta";

/** El tono de cada estado: lo que se puede usar es `ok`; lo que frena un envío, no. */
const TONO: Readonly<Record<EstadoDeAprobacion, EstadoDeBadge>> = {
  NO_APLICA: "ok",
  APROBADA: "ok",
  PENDIENTE: "pendiente",
  SIN_ENVIAR: "atencion",
  PAUSADA: "atencion",
  RECHAZADA: "error",
  DESHABILITADA: "error",
};

export const MENSAJE_EN_REVISION =
  "Meta está revisando esta plantilla. Vas a poder editarla cuando responda.";

/**
 * Por qué el texto no se puede editar ahora, o `null` si se puede.
 *
 * Una `PENDIENTE` está en revisión y Meta no deja tocarla; una aprobada se edita una vez cada
 * 24 horas. La pantalla lo explica en vez de dejar un botón gris sin motivo; el backend lo
 * refuerza igual.
 */
export function motivoDeBloqueo(plantilla: Plantilla, ahora: Date): string | null {
  if (plantilla.canal !== "WHATSAPP") {
    return null;
  }
  if (plantilla.estado_aprobacion === "PENDIENTE") {
    return MENSAJE_EN_REVISION;
  }
  if (
    plantilla.estado_aprobacion === "APROBADA" &&
    plantilla.editable_desde !== null &&
    new Date(plantilla.editable_desde) > ahora
  ) {
    return `Meta permite editar una plantilla aprobada una vez cada 24 horas. Vas a poder editarla desde el ${formatearFechaHora(plantilla.editable_desde)}.`;
  }
  return null;
}

export interface PropsDeEstadoDePlantilla {
  readonly plantilla: Plantilla;
}

export function EstadoDePlantilla({ plantilla }: PropsDeEstadoDePlantilla): JSX.Element {
  const motivo = traducirMotivoDeMeta(plantilla.motivo_meta);
  return (
    <div className="plt-estado">
      <Badge estado={TONO[plantilla.estado_aprobacion]}>
        {ETIQUETAS_DE_APROBACION[plantilla.estado_aprobacion]}
      </Badge>
      {motivo !== null && <span className="plt-estado__motivo">{motivo}</span>}
      {plantilla.detalle_meta !== null && (
        // El texto literal de Meta, sin traducir ni resumir: es lo que dice qué corregir.
        <span className="plt-estado__detalle">{plantilla.detalle_meta}</span>
      )}
      {plantilla.categoria_en_meta === "MARKETING" && (
        <span className="plt-estado__aviso">
          Meta la clasificó como Marketing: los clientes que se dieron de baja de marketing no la
          reciben.
        </span>
      )}
    </div>
  );
}
