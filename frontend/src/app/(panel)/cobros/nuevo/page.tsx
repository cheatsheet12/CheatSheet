/**
 * PAN-COB-03 — Cobros · Nuevo cobro (HU-E6-03, HU-E6-06).
 *
 * **Solo Lectura no llega acá.** El caso de uso lo rechaza igual, pero renderizar el
 * formulario entero para contestar 403 en Generar le hace perder la tarde a alguien.
 *
 * El cliente se elige antes, como en la emisión: es el dato que decide a quién se le cobra, y
 * un selector más en este formulario lo haría más largo sin hacerlo más claro.
 *
 * **El encabezado es el mismo en los dos caminos** —con cliente y sin cliente— y por eso vive
 * en una función: quien cae en el camino cortado tiene que ver dónde está parado y poder
 * volver, no sólo leer que le falta un dato.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { ETIQUETAS_DE_TIPO } from "@/features/billing";
import type { ListadoDeComprobantesRespuesta } from "@/features/billing";
import { NuevoCobro } from "@/features/payments";
import { formatearNumero } from "@/shared";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Nuevo cobro · CheatSheet" };

interface Props {
  readonly searchParams: { readonly cliente?: string };
}

/**
 * El encabezado de pantalla del panel: cintillo, título y bajada, con la vuelta al listado a
 * la derecha. Es el mismo bloque que usan la agenda y facturación, y está acá y no repetido
 * en cada rama para que las dos no se desalineen por separado.
 */
function Encabezado({ bajada }: { readonly bajada: string }): JSX.Element {
  return (
    <header className="cob-encabezado">
      <div>
        <span className="cob-cintillo">Cobros · Nuevo cobro</span>
        <h1 className="cob-titulo">Nuevo cobro</h1>
        <p className="cob-encabezado__sub">{bajada}</p>
      </div>
      <div className="cob-encabezado__acciones">
        <Link href="/cobros" className="boton boton--secundario cob-boton-enlace">
          Volver al listado
        </Link>
      </div>
    </header>
  );
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
    // Estado vacío, no dos renglones sobre el fondo: quien entra por el menú lateral llega
    // sin `?cliente=`, y lo que necesita es entender por qué no hay formulario y tener el
    // camino de salida a un clic, no un enlace suelto en medio de una oración.
    return (
      <>
        <Encabezado bajada="Un cobro se emite siempre contra un cliente del catálogo, así que ese es el primer dato." />
        <section className="cob-eleccion">
          <span className="cob-eleccion__icono" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <circle cx="12" cy="8" r="3.4" />
              <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" strokeLinecap="round" />
            </svg>
          </span>
          <h2 className="cob-eleccion__titulo">Falta elegir el cliente</h2>
          <p className="cob-eleccion__texto">
            Elegí primero a quién le vas a cobrar. Desde su ficha volvés a esta pantalla con el
            cliente ya cargado, y sólo quedan el concepto y el monto.
          </p>
          <Link href="/datos-maestros/clientes" className="boton boton--primario cob-boton-enlace">
            Ir a Clientes
          </Link>
        </section>
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
      // El tipo con el nombre que ya tiene facturación —«Factura B», no `FACTURA_B`— y el
      // saldo con el formato de acá —«18.500,00», no «18500.00»—. Ninguno de los dos se
      // reimplementa: el mapa de etiquetas es de `billing` y el formateador es de `@/shared`,
      // que recibe el importe como texto y devuelve texto. Nada lo convierte a número.
      etiqueta: `${ETIQUETAS_DE_TIPO[uno.tipo]} ${uno.numero ?? "s/n"} — saldo $ ${formatearNumero(uno.saldo_pendiente)}`,
    }));

  return (
    <>
      <Encabezado bajada="Se genera un link de MercadoPago y empieza la cadena de recordatorios. Si MercadoPago no responde, el cobro no se crea." />
      <NuevoCobro clienteId={clienteId} comprobantes={conSaldo} />
    </>
  );
}
