/**
 * PAN-WA-02 — Agente WhatsApp · Configuración (HU-E9-04).
 *
 * Todos los roles ven las respuestas y su contador de usos —es información del negocio— y
 * sólo el Administrador las administra.
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

  return (
    <>
      <h1>Respuestas frecuentes</h1>
      <p className="dm-intro">
        Lo que el agente contesta solo. Busca por significado, así que no hace falta que el cliente
        escriba la pregunta igual; cuando ninguna alcanza, deriva a una persona.
      </p>
      <RespuestasFrecuentes inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
