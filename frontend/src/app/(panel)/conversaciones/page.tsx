/**
 * PAN-WA-01 — Agente WhatsApp · Conversaciones (HU-E9-01).
 *
 * Arranca filtrada por escaladas, que es lo que un operador viene a hacer: el agente resuelve
 * solo la mayoría de los hilos, y los que no, esperan a alguien.
 */

import { redirect } from "next/navigation";

import { BandejaDeConversaciones } from "@/features/conversational";
import type { ListadoDeConversaciones } from "@/features/conversational";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Conversaciones · CheatSheet" };

export default async function PaginaDeConversaciones(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeConversaciones>("/conversaciones?solo_escaladas=true");

  return (
    <>
      {/* El mismo encabezado que su pantalla hermana, `/configuracion/respuestas`: cintillo,
          título de 27 px y bajada. Dos criterios distintos dentro del mismo contexto es lo que
          hace que un panel se lea como dos productos pegados. */}
      <header className="wa-encabezado">
        <div>
          <p className="wa-encabezado__eyebrow">Agente WhatsApp · Conversaciones</p>
          <h1 className="wa-encabezado__titulo">Conversaciones</h1>
          <p className="wa-encabezado__intro">
            Los hilos que el agente derivó a una persona. Tomar una conversación hace que el agente
            deje de responderla hasta que la cierres.
          </p>
        </div>
      </header>
      <BandejaDeConversaciones
        inicial={listado}
        puedeAtender={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
      />
    </>
  );
}
