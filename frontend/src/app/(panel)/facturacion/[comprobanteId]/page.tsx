/**
 * PAN-FAC-02 — Facturación · Detalle (HU-E5-02).
 *
 * Its own URL rather than a modal over the listing, and that is deliberate: this is the
 * page somebody sends to their accountant, opens in a second tab next to a paper invoice,
 * and bookmarks. A modal has none of those.
 *
 * Every role reads it. There are no actions here at all, so nothing depends on the role.
 */

import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { DetalleDeComprobante } from "@/features/billing";
import type { Anulacion, Comprobante, ListadoDePuntosDeVenta } from "@/features/billing";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Comprobante · CheatSheet" };

interface Props {
  readonly params: { readonly comprobanteId: string };
}

export default async function PaginaDeComprobante({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const comprobante = await leer(params.comprobanteId);
  if (comprobante === null) {
    // Under RLS "not yours" and "does not exist" are the same answer on purpose, and a 404
    // is how that reaches the browser without confirming somebody else's document id.
    notFound();
  }

  // The point of sale's own number, for the `0001-00000123` form ARCA prints. Read
  // separately because the document stores the id and ARCA prints the number.
  // Two independent reads the screen needs together for its first paint.
  const [puntos, anulacion] = await Promise.all([
    llamarApi<ListadoDePuntosDeVenta>("/puntos-de-venta"),
    llamarApi<Anulacion>(`/comprobantes/${comprobante.id}/anulacion`),
  ]);
  const punto = puntos.puntos.find((uno) => uno.id === comprobante.punto_de_venta_id);

  // Only an authorised invoice can be reversed (HU-E5-04 RN-01), and a credit note is not
  // reversed with another one: undoing an annulment is a new invoice, not a second note.
  const puedeAnular =
    (claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR") &&
    comprobante.estado === "AUTORIZADO" &&
    !comprobante.tipo.startsWith("NOTA_CREDITO");

  return (
    <>
      {/* El encabezado vive acá y no en el componente: la vuelta al listado es navegación de
          la ruta, y el componente se renderiza igual desde una pestaña abierta a mano. */}
      <header className="fac-nuevo-encabezado">
        <div>
          <span className="fac-nuevo-encabezado__cintillo">Facturación</span>
          <h1 className="fac-nuevo-encabezado__titulo">Comprobante</h1>
          <p className="fac-nuevo-encabezado__sub">
            Lo que ARCA autorizó, tal como quedó. Es la página que se manda al contador y la que se
            abre al lado de un papel.
          </p>
        </div>
        <div className="fac-nuevo-encabezado__acciones">
          <Link href="/facturacion" className="boton boton--secundario fac-nuevo-boton-enlace">
            Volver al listado
          </Link>
        </div>
      </header>
      <DetalleDeComprobante
        comprobante={comprobante}
        puntoNumero={punto?.numero ?? null}
        anulacion={anulacion}
        puedeAnular={puedeAnular}
      />
    </>
  );
}

async function leer(comprobanteId: string): Promise<Comprobante | null> {
  try {
    return await llamarApi<Comprobante>(`/comprobantes/${comprobanteId}`);
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
