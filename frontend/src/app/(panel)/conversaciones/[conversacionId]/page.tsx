/**
 * PAN-WA-01 — el hilo abierto (HU-E9-01, HU-E9-02).
 *
 * La pantalla no maneja el teléfono del cliente: la respuesta del operador sale siempre al
 * WhatsApp del cliente dueño del hilo, que el backend resuelve por su cuenta.
 */

import { notFound, redirect } from "next/navigation";

import { HiloDeConversacion } from "@/features/conversational";
import type { DetalleDeConversacion } from "@/features/conversational";
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

  return (
    <>
      <h1>Conversación</h1>
      <HiloDeConversacion
        inicial={hilo}
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
