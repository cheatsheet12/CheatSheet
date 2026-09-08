/**
 * PAN-DM-03 — Datos Maestros · Categorías (HU-E4-03).
 *
 * La tercera y última pantalla del épico 3, con el mismo hueco P10 que sus dos hermanas:
 * el mapa de navegación de Etapa 5 la codifica y no la maqueta, así que se arma con el
 * catálogo de componentes de la especificación §1.3.
 */

import { redirect } from "next/navigation";

import { ListadoDeCategorias } from "@/features/master_data";
import type { ListadoDeCategoriasRespuesta } from "@/features/master_data";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Categorias · CheatSheet" };

const ROLES_QUE_ESCRIBEN = ["ADMINISTRADOR", "OPERADOR"];

export default async function PaginaDeCategorias(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeCategoriasRespuesta>("/categorias");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Datos maestros</span>
          <h1>Categorias</h1>
          <p className="dm-intro">
            Las etiquetas con las que organizas tu catalogo. Cada una decide si sirve para clientes,
            para servicios o para las dos cosas.
          </p>
        </div>
      </header>
      <ListadoDeCategorias
        inicial={listado}
        puedeEditar={ROLES_QUE_ESCRIBEN.includes(claims.rol)}
      />
    </>
  );
}
