/**
 * PAN-LOG-01 — Log de Operaciones · Listado (HU-E12-01).
 *
 * **Administrador y Operador** (RN-05). Solo Lectura no entra, y el backend lo refuerza: si
 * llega igual, la respuesta es un 422 con el motivo, y esta página lo muestra en vez de una
 * tabla vacía que parece un sistema roto.
 */

import { redirect } from "next/navigation";

import { Bitacora } from "@/features/observability";
import type { ListadoDeOperaciones } from "@/features/observability";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Log de operaciones · CheatSheet" };

export default async function PaginaDeAuditoria(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  let listado: ListadoDeOperaciones = { operaciones: [], total: 0 };
  let motivo: string | undefined;
  try {
    listado = await llamarApi<ListadoDeOperaciones>("/bitacora");
  } catch (error) {
    if (!(error instanceof ErrorDeApi) || error.status >= 500) {
      throw error;
    }
    motivo = error.detalle;
  }

  return (
    <>
      <h1>Log de operaciones</h1>
      <p className="dm-intro">
        Todo lo que el sistema ejecutó en nombre de tu empresa, con quién lo puso en marcha: una
        persona, un proceso automático o el agente de WhatsApp.
      </p>
      {motivo !== undefined ? (
        <p className="tabla__vacia">{motivo}</p>
      ) : (
        <Bitacora inicial={listado} />
      )}
    </>
  );
}
