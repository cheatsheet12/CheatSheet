/**
 * PAN-COB-03 — Cobros · Nuevo cobro (HU-E6-03, HU-E6-06).
 *
 * **Solo Lectura no llega acá.** El caso de uso lo rechaza igual, pero renderizar el
 * formulario entero para contestar 403 en Generar le hace perder la tarde a alguien.
 *
 * El cliente se elige antes, como en la emisión: es el dato que decide a quién se le cobra, y
 * un selector más en este formulario lo haría más largo sin hacerlo más claro.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { NuevoCobro } from "@/features/payments";
import type { ListadoDeComprobantesRespuesta } from "@/features/billing";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Nuevo cobro · CheatSheet" };

interface Props {
  readonly searchParams: { readonly cliente?: string };
}

export default async function PaginaDeNuevoCobro({ searchParams }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }
  if (claims.rol !== "ADMINISTRADOR" && claims.rol !== "OPERADOR") {
    redirect("/cobros");
  }

  const clienteId = searchParams.cliente;
  if (clienteId === undefined) {
    return (
      <>
        <h1>Nuevo cobro</h1>
        <p className="dm-intro">
          Elegí primero a quién le vas a cobrar.{" "}
          <Link href="/datos-maestros/clientes">Ir a Clientes</Link>.
        </p>
      </>
    );
  }

  // HU-E6-06: sólo los autorizados con saldo pueden recibir un cobro asociado. Se filtran acá
  // y no en el componente porque es una regla de la historia, no una preferencia de la
  // pantalla.
  const listado = await llamarApi<ListadoDeComprobantesRespuesta>(
    "/comprobantes?estado=AUTORIZADO",
  );
  const conSaldo = listado.comprobantes
    .filter((uno) => Number(uno.saldo_pendiente) > 0)
    .map((uno) => ({
      id: uno.id,
      etiqueta: `${uno.tipo} ${uno.numero ?? "s/n"} — saldo $ ${uno.saldo_pendiente}`,
    }));

  return (
    <>
      <h1>Nuevo cobro</h1>
      <p className="dm-intro">
        Se genera un link de MercadoPago y empieza la cadena de recordatorios. Si MercadoPago no
        responde, el cobro no se crea.
      </p>
      <NuevoCobro clienteId={clienteId} comprobantes={conSaldo} />
    </>
  );
}
