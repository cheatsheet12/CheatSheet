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

import { ElegirCliente, NuevaEmision } from "@/features/billing";
import type { ListadoDePuntosDeVenta } from "@/features/billing";
import type { ListadoDeClientesRespuesta } from "@/features/master_data";
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
        <Encabezado bajada="Sin punto de venta no hay numeración, y sin numeración no hay comprobante." />
        <section className="fac-nuevo-tarjeta">
          <p className="fac-nuevo-rotulo">Falta un paso previo</p>
          <p>
            Todavía no tenés un punto de venta activo, y sin punto de venta no hay numeración
            fiscal. <Link href="/facturacion/puntos-de-venta">Configurá uno</Link> antes de emitir.
          </p>
        </section>
      </>
    );
  }

  const clienteId = searchParams.cliente;
  if (clienteId === undefined) {
    // Se elige acá y no en otra pantalla: «Emitir comprobante» es la acción principal del
    // listado, y terminaba en una tarjeta cuya única salida era irse a Clientes.
    const { clientes } = await llamarApi<ListadoDeClientesRespuesta>("/clientes?activo=true");
    return (
      <>
        <Encabezado bajada="El comprobante se emite a nombre de un cliente del catálogo." />
        <ElegirCliente clientes={clientes} />
      </>
    );
  }

  return (
    <>
      <Encabezado bajada="Tres pasos: validamos el CUIT contra el padrón de ARCA, elegís con qué numeración se emite y cargás los ítems. De la respuesta de ARCA depende qué se puede emitir." />
      <NuevaEmision puntos={activos} clienteId={clienteId} />
    </>
  );
}

/**
 * El encabezado de la pantalla, con la vuelta al listado.
 *
 * Es el mismo bloque en los tres caminos —sin punto de venta, sin cliente y con todo listo—
 * y sólo cambia la bajada: quien cae en un camino cortado tiene que ver dónde está parado y
 * poder volver, no sólo leer por qué no puede seguir.
 */
function Encabezado({ bajada }: { readonly bajada: string }): JSX.Element {
  return (
    <header className="fac-nuevo-encabezado">
      <div>
        <span className="fac-nuevo-encabezado__cintillo">Facturación</span>
        <h1 className="fac-nuevo-encabezado__titulo">Nueva emisión</h1>
        <p className="fac-nuevo-encabezado__sub">{bajada}</p>
      </div>
      <div className="fac-nuevo-encabezado__acciones">
        <Link href="/facturacion" className="boton boton--secundario fac-nuevo-boton-enlace">
          Volver al listado
        </Link>
      </div>
    </header>
  );
}
