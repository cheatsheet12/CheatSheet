/**
 * PAN-LOG-02 — Log de Operaciones · Detalle (HU-E12-02).
 *
 * El responsable se resuelve del lado del servidor con los usuarios de la empresa (#169): la
 * bitácora guarda sólo el id —nunca datos personales, D72— y un id no le dice a quien audita
 * quién hizo la operación.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import type { UsuarioDeLaEmpresa } from "@/features/identity";
import { DetalleDeOperacion } from "@/features/observability";
import type { DetalleDeOperacionRespuesta, ResponsableDeOperacion } from "@/features/observability";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Detalle de la operación · CheatSheet" };

interface Props {
  readonly params: { readonly operacionId: string };
}

export default async function PaginaDeDetalle({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  let detalle: DetalleDeOperacionRespuesta | null = null;
  let motivo: string | undefined;
  try {
    detalle = await llamarApi<DetalleDeOperacionRespuesta>(`/bitacora/${params.operacionId}`);
  } catch (error) {
    if (!(error instanceof ErrorDeApi) || error.status >= 500) {
      throw error;
    }
    motivo = error.detalle;
  }

  return (
    <>
      <p className="dm-intro">
        <Link href="/auditoria">← Volver al log</Link>
      </p>
      <h1>Detalle de la operación</h1>
      {detalle === null ? (
        <p className="tabla__vacia">{motivo ?? "La operación no existe."}</p>
      ) : (
        <DetalleDeOperacion
          detalle={detalle}
          responsable={await responsableDe(detalle.operacion.usuario_id)}
        />
      )}
    </>
  );
}

/**
 * El nombre y el email de quien ejecutó la operación, o `null` si no se puede resolver: una
 * operación de la plataforma no tiene usuario, y un usuario que ya no figura —o una lista que
 * la API no devolvió— deja el id a la vista. Una respuesta de error no tumba la página.
 */
async function responsableDe(usuarioId: string | null): Promise<ResponsableDeOperacion | null> {
  if (usuarioId === null) {
    return null;
  }
  try {
    const usuarios = await llamarApi<readonly UsuarioDeLaEmpresa[]>("/usuarios");
    const usuario = usuarios.find((uno) => uno.id === usuarioId);
    return usuario === undefined ? null : { nombre: usuario.nombre, email: usuario.email };
  } catch (error) {
    if (error instanceof ErrorDeApi) {
      return null;
    }
    throw error;
  }
}
