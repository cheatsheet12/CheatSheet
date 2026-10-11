/**
 * PAN-WA-01 — el hilo abierto (HU-E9-01, HU-E9-02).
 *
 * La pantalla no maneja el teléfono del cliente: la respuesta del operador sale siempre al
 * WhatsApp del cliente dueño del hilo, que el backend resuelve por su cuenta.
 */

import { notFound, redirect } from "next/navigation";

import { BandejaDeConversaciones, HiloDeConversacion } from "@/features/conversational";
import type { DetalleDeConversacion, ListadoDeConversaciones } from "@/features/conversational";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Conversación · CheatSheet" };

interface Props {
  readonly params: { readonly conversacionId: string };
}

export default async function PaginaDeConversacion({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const hilo = await leer(params.conversacionId);
  if (hilo === null) {
    // Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a propósito.
    notFound();
  }

  const puedeAtender = claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR";
  const listado = await llamarApi<ListadoDeConversaciones>("/conversaciones");

  // La bandeja queda a la izquierda con este hilo resaltado: elegir otro es un clic y no un
  // viaje de ida y vuelta. El listado viene completo porque el hilo abierto puede no estar
  // escalado, y un renglón resaltado que no está en la lista se lee como un error.
  return (
    <>
      {/* El mismo encabezado que la bandeja, para que abrir un hilo no mueva la pantalla. En el
          celular se oculta: ahí el hilo ocupa todo el alto y lleva su propio «Volver». */}
      <header className="wa-encabezado cv-encabezado cv-encabezado--hilo">
        <div>
          <p className="wa-encabezado__eyebrow">Agente WhatsApp · Conversaciones</p>
          <h1 className="wa-encabezado__titulo">Conversación</h1>
          <p className="wa-encabezado__intro">
            Los hilos que el agente derivó a una persona. Tomar una conversación hace que el agente
            deje de responderla hasta que la cierres.
          </p>
        </div>
      </header>
      <BandejaDeConversaciones
        inicial={listado}
        puedeAtender={puedeAtender}
        seleccionadaId={hilo.id}
        soloEscaladasInicial={false}
      >
        <HiloDeConversacion key={hilo.id} inicial={hilo} puedeAtender={puedeAtender} />
      </BandejaDeConversaciones>
    </>
  );
}

async function leer(conversacionId: string): Promise<DetalleDeConversacion | null> {
  try {
    return await llamarApi<DetalleDeConversacion>(`/conversaciones/${conversacionId}`);
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
