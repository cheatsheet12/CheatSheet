/**
 * PAN-COB-03 — Cobros · Nuevo cobro (HU-E6-03, HU-E6-06).
 *
 * **Solo Lectura no llega acá.** El caso de uso lo rechaza igual, pero renderizar el
 * formulario entero para contestar 403 en Generar le hace perder la tarde a alguien.
 *
 * **La página compone y la URL decide.** El selector de clientes es de `master_data` y el
 * formulario de `payments`; ninguno importa al otro (R5), así que quien los junta es esta ruta.
 * El cliente elegido vive en `?cliente=<id>`: elegir a otro navega acá mismo, la página se vuelve
 * a renderizar en el servidor y **vuelve a pedir los comprobantes de ese cliente**, sin estado
 * compartido que sincronizar. El formulario ocupa siempre el mismo lugar del árbol, y por eso
 * lo que se escribió en concepto y monto sobrevive al cambio de cliente.
 *
 * El cobro no crea clientes (D92): sin cliente el formulario se muestra y el botón queda
 * deshabilitado, y si el selector no encuentra a nadie ofrece ir a Clientes.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { ETIQUETAS_DE_TIPO } from "@/features/billing";
import type { ListadoDeComprobantesRespuesta } from "@/features/billing";
import { SelectorDeClientes } from "@/features/master_data";
import type { Cliente } from "@/features/master_data";
import { NuevoCobro } from "@/features/payments";
import { Alert, formatearNumero } from "@/shared";
import { ErrorDeApi, llamarApi } from "@/lib/api";
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

  const { cliente, indicadoPeroInvalido } = await cargarCliente(searchParams.cliente);

  // HU-E6-06: sólo los autorizados con saldo **del cliente elegido** pueden recibir un cobro
  // asociado. Se filtran acá y no en el componente porque es una regla de la historia, no una
  // preferencia de la pantalla, y sin cliente no hay nada que ofrecer ni que pedir.
  const conSaldo = cliente === null ? [] : await comprobantesConSaldoDe(cliente.id);

  return (
    <>
      <Encabezado bajada="Se genera un link de MercadoPago y empieza la cadena de recordatorios. Si MercadoPago no responde, el cobro no se crea." />
      {indicadoPeroInvalido && (
        <Alert tono="advertencia">El cliente indicado no existe o está inactivo.</Alert>
      )}
      <SelectorDeClientes
        destino="/cobros/nuevo"
        seleccionado={
          cliente === null ? null : { id: cliente.id, nombre: cliente.nombre, cuit: cliente.cuit }
        }
      />
      <NuevoCobro clienteId={cliente?.id ?? null} comprobantes={conSaldo} />
    </>
  );
}

/**
 * El cliente de `?cliente=`, si existe y está activo. Un id viejo, ajeno o de alguien dado de
 * baja se trata como «sin cliente» y se avisa: el backend igual lo rechazaría al generar, y es
 * mejor decirlo antes de que alguien escriba todo. Un fallo que no es «no existe» sí se deja
 * subir: disfrazar una caída del backend de «cliente vacío» esconde el problema.
 */
async function cargarCliente(
  id: string | undefined,
): Promise<{ cliente: Cliente | null; indicadoPeroInvalido: boolean }> {
  if (id === undefined) {
    return { cliente: null, indicadoPeroInvalido: false };
  }
  try {
    const cliente = await llamarApi<Cliente>(`/clientes/${encodeURIComponent(id)}`);
    return cliente.activo
      ? { cliente, indicadoPeroInvalido: false }
      : { cliente: null, indicadoPeroInvalido: true };
  } catch (fallo) {
    // 422 es «no existe» (o un id mal formado); 404 lo cubre si el backend algún día lo cambia.
    if (fallo instanceof ErrorDeApi && (fallo.status === 404 || fallo.status === 422)) {
      return { cliente: null, indicadoPeroInvalido: true };
    }
    throw fallo;
  }
}

async function comprobantesConSaldoDe(
  clienteId: string,
): Promise<readonly { readonly id: string; readonly etiqueta: string }[]> {
  const listado = await llamarApi<ListadoDeComprobantesRespuesta>(
    "/comprobantes?estado=AUTORIZADO",
  );
  return listado.comprobantes
    .filter((uno) => uno.cliente_id === clienteId && Number(uno.saldo_pendiente) > 0)
    .map((uno) => ({
      id: uno.id,
      // El tipo con el nombre que ya tiene facturación —«Factura B», no `FACTURA_B`— y el
      // saldo con el formato de acá —«18.500,00», no «18500.00»—. Ninguno de los dos se
      // reimplementa: el mapa de etiquetas es de `billing` y el formateador es de `@/shared`,
      // que recibe el importe como texto y devuelve texto. Nada lo convierte a número.
      etiqueta: `${ETIQUETAS_DE_TIPO[uno.tipo]} ${uno.numero ?? "s/n"} — saldo $ ${formatearNumero(uno.saldo_pendiente)}`,
    }));
}
