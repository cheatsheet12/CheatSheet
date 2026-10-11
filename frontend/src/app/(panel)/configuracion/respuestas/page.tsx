/**
 * PAN-WA-02 — Agente WhatsApp · Configuración (HU-E9-04).
 *
 * Todos los roles ven las respuestas y su contador de usos —es información del negocio— y
 * sólo el Administrador las administra. Lo mismo vale para la tarjeta de horarios de atención
 * (HS-T2 RN-04), que se compone arriba de las respuestas.
 *
 * El encabezado lo dibuja el componente y no esta página: el CTA depende del rol y abre el
 * formulario, así que necesita estado, y partir título y acción en dos archivos era lo que
 * dejaba al botón flotando solo arriba del listado.
 */

import { redirect } from "next/navigation";

import { HorarioDeAtencion, horarioDe } from "@/features/business_config";
import type { ListadoDeReglasCrudo } from "@/features/business_config";
import { RespuestasFrecuentes } from "@/features/conversational";
import type { ListadoDeFaqs } from "@/features/conversational";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Respuestas frecuentes · CheatSheet" };

export default async function PaginaDeFaqs(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const puedeEditar = claims.rol === "ADMINISTRADOR";
  const [listado, reglas] = await Promise.all([
    llamarApi<ListadoDeFaqs>("/faqs"),
    llamarApi<ListadoDeReglasCrudo>("/reglas"),
  ]);

  // La ruta compone dos features (R5): el horario de atención es de `business_config` y las
  // respuestas frecuentes de `conversational`. El horario va arriba: es lo que decide cuándo
  // contesta el agente.
  return (
    <>
      <HorarioDeAtencion inicial={horarioDe(reglas)} puedeEditar={puedeEditar} />
      <RespuestasFrecuentes inicial={listado} puedeEditar={puedeEditar} />
    </>
  );
}
