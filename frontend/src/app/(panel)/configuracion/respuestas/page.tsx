/**
 * PAN-WA-02 — Agente WhatsApp · Configuración (HU-E9-04).
 *
 * Todos los roles ven las respuestas y su contador de usos —es información del negocio— y
 * sólo el Administrador las administra.
 *
 * El encabezado lo dibuja el componente y no esta página: el CTA depende del rol y abre el
 * formulario, así que necesita estado, y partir título y acción en dos archivos era lo que
 * dejaba al botón flotando solo arriba del listado.
 */

import { redirect } from "next/navigation";

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

  const listado = await llamarApi<ListadoDeFaqs>("/faqs");

  return <RespuestasFrecuentes inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />;
}
