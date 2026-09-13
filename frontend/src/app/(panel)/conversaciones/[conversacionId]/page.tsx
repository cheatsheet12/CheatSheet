/**
 * PAN-WA-01 — el hilo abierto (HU-E9-01, HU-E9-02).
 *
 * El teléfono del cliente se resuelve del lado del servidor: la pantalla lo necesita para
 * poder responder, y pedirlo desde el componente sería una consulta más por cada hilo que
 * alguien abre.
 */

import { notFound, redirect } from "next/navigation";

import { HiloDeConversacion } from "@/features/conversational";
import type { DetalleDeConversacion } from "@/features/conversational";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Conversación · CheatSheet" };

interface ClienteDelHilo {
  readonly contacto_whatsapp: string | null;
}

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

  return (
    <>
      <h1>Conversación</h1>
      <HiloDeConversacion
        inicial={hilo}
        telefono={await telefonoDe(hilo.cliente_id)}
        puedeAtender={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
      />
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

/**
 * El número al que responder.
 *
 * Devuelve la cadena vacía si el cliente no tiene WhatsApp registrado — que no debería pasar,
 * porque el hilo nació de un mensaje suyo, pero un `throw` acá dejaría sin pantalla a alguien
 * por un dato que la pantalla usa sólo para el campo de respuesta.
 */
async function telefonoDe(clienteId: string): Promise<string> {
  try {
    const cliente = await llamarApi<ClienteDelHilo>(`/clientes/${clienteId}`);
    return cliente.contacto_whatsapp ?? "";
  } catch {
    return "";
  }
}
