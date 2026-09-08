/**
 * PAN-DM-03 — Datos Maestros · Categorías (HU-E4-03).
 *
 * La tercera y última pantalla del épico 3, con el mismo hueco P10 que sus dos hermanas:
 * el mapa de navegación de Etapa 5 la codifica y no la maqueta, así que se arma con el
 * catálogo de componentes de la especificación §1.3.
 *
 * **El encabezado lo dibuja el componente**, igual que en las otras dos: el CTA depende del
 * rol y abre el formulario, y antes quedaba dentro de la fila de filtros al lado de un
 * `<select>`, como si crear una categoría fuera una forma de filtrar.
 */

import { redirect } from "next/navigation";

import { ListadoDeCategorias } from "@/features/master_data";
import type { ListadoDeCategoriasRespuesta } from "@/features/master_data";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Categorías · CheatSheet" };

const ROLES_QUE_ESCRIBEN = ["ADMINISTRADOR", "OPERADOR"];

export default async function PaginaDeCategorias(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeCategoriasRespuesta>("/categorias");

  return (
    <ListadoDeCategorias inicial={listado} puedeEditar={ROLES_QUE_ESCRIBEN.includes(claims.rol)} />
  );
}
