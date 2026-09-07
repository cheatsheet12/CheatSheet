/**
 * PAN-FAC-03 — Facturación · Nueva emisión (HU-E5-03).
 *
 * **Solo Lectura never reaches this page.** The use case refuses it anyway, but a screen
 * that renders a whole form and then answers 403 on Submit wastes somebody's afternoon:
 * the redirect is what the navigation map asks for.
 *
 * The two preconditions of the story are checked here, before the form renders, because
 * each has a different answer: without an active point of sale there is no fiscal
 * numbering, and without a client there is nobody to invoice.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { NuevaEmision } from "@/features/billing";
import type { ListadoDePuntosDeVenta } from "@/features/billing";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Nueva emisión · CheatSheet" };

interface Props {
  readonly searchParams: { readonly cliente?: string };
}

export default async function PaginaDeNuevaEmision({ searchParams }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }
  if (claims.rol !== "ADMINISTRADOR" && claims.rol !== "OPERADOR") {
    redirect("/facturacion");
  }

  const listado = await llamarApi<ListadoDePuntosDeVenta>("/puntos-de-venta");
  const activos = listado.puntos.filter((punto) => punto.activo);

  if (activos.length === 0) {
    return (
      <>
        <h1>Nueva emisión</h1>
        <p className="dm-intro">
          Todavía no tenés un punto de venta activo, y sin punto de venta no hay numeración fiscal.{" "}
          <Link href="/facturacion/puntos-de-venta">Configurá uno</Link> antes de emitir.
        </p>
      </>
    );
  }

  const clienteId = searchParams.cliente;
  if (clienteId === undefined) {
    return (
      <>
        <h1>Nueva emisión</h1>
        <p className="dm-intro">
          Elegí primero a quién le vas a facturar.{" "}
          <Link href="/datos-maestros/clientes">Ir a Clientes</Link>.
        </p>
      </>
    );
  }

  return (
    <>
      <h1>Nueva emisión</h1>
      <p className="dm-intro">
        Validamos el CUIT contra el padrón de ARCA antes de habilitar el resto del formulario: de
        esa respuesta depende qué tipo de comprobante se puede emitir.
      </p>
      <NuevaEmision puntos={activos} clienteId={clienteId} />
    </>
  );
}
