/**
 * What PAN-CFG-NOT and the panel's badge call (HU-E11-03), and the support form (HU-E9-03).
 *
 * **No hay forma de pedir la bandeja de otra persona.** El destinatario sale de la sesión del
 * lado del backend, y ninguna de estas funciones recibe un id de usuario: la única bandeja que
 * se puede leer es la propia.
 *
 * **Marcar como leída no se deshace.** No hay `marcarComoNoLeida`, porque «lo vi» es un hecho:
 * un botón que lo revierte convierte el estado de lectura en una preferencia de interfaz, que
 * es justo lo que deja de servir para saber si alguien se enteró.
 */

export type Severidad = "ALTA" | "MEDIA" | "BAJA";

export interface Notificacion {
  readonly id: string;
  readonly categoria: string;
  readonly severidad: Severidad;
  readonly cuerpo: string;
  readonly leida: boolean;
  /** RN-04: la pantalla destaca lo que esto marca. Alta **y sin leer**. */
  readonly se_destaca: boolean;
  readonly created_at: string | null;
}

export interface ListadoDeNotificaciones {
  readonly notificaciones: readonly Notificacion[];
  readonly no_leidas: number;
}

export type PrioridadDeSoporte = "ALTA" | "MEDIA" | "BAJA";

export interface Solicitud {
  readonly id: string;
  readonly asunto: string;
  readonly descripcion: string;
  readonly prioridad: PrioridadDeSoporte;
  readonly estado: string;
  readonly esta_abierta: boolean;
  readonly created_at: string | null;
}

export interface ListadoDeSolicitudes {
  readonly solicitudes: readonly Solicitud[];
}

export interface SolicitudNueva {
  readonly asunto: string;
  readonly descripcion: string;
  readonly prioridad: PrioridadDeSoporte;
}

/** HU-E11-03 y HU-E9-03, palabra por palabra. */
export const MENSAJE_SIN_NOTIFICACIONES = "No tenés notificaciones.";
export const MENSAJE_CAMPOS_OBLIGATORIOS = "El asunto y la descripción son obligatorios.";

export const ETIQUETAS_DE_CATEGORIA: Readonly<Record<string, string>> = {
  FACTURACION: "Facturación",
  COBROS: "Cobros",
  SINCRONIZACION: "Sincronización",
  AGENDA: "Agenda",
  SISTEMA: "Sistema",
};

export const ETIQUETAS_DE_ESTADO: Readonly<Record<string, string>> = {
  ABIERTA: "Abierta",
  EN_REVISION: "En revisión",
  RESUELTA: "Resuelta",
  CERRADA: "Cerrada",
};

export class ErrorDeNotificacion extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeNotificacion";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeNotificacion(
    cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion",
  );
}

export async function listarNotificaciones(soloNoLeidas = false): Promise<ListadoDeNotificaciones> {
  const consulta = soloNoLeidas ? "?solo_no_leidas=true" : "";
  const respuesta = await fetch(`/api/notificaciones${consulta}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeNotificaciones;
}

/** HU-E11-03 RN-03. `POST` sobre el acuse de lectura, que es lo que se crea. */
export async function marcarComoLeida(notificacionId: string): Promise<Notificacion> {
  const respuesta = await fetch(`/api/notificaciones/${notificacionId}/lectura`, {
    method: "POST",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Notificacion;
}

export async function listarSolicitudes(soloAbiertas = false): Promise<ListadoDeSolicitudes> {
  const consulta = soloAbiertas ? "?solo_abiertas=true" : "";
  const respuesta = await fetch(`/api/soporte${consulta}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeSolicitudes;
}

export async function abrirSolicitud(datos: SolicitudNueva): Promise<Solicitud> {
  const respuesta = await fetch("/api/soporte", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Solicitud;
}
