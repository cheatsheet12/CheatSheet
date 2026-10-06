/**
 * Lo que dibuja cada fila del listado de categorías: la pastilla «Se aplica a» y las acciones.
 *
 * Editar y Eliminar van en el menú ⋯. «Eliminar» es el único borrado de la aplicación; la
 * advertencia no la da el color de cada fila sino la confirmación, que dice qué se pierde.
 */

"use client";

import type { AmbitoDeCategoria, Categoria } from "../api/categoria";
import { ETIQUETAS_DE_AMBITO } from "../api/categoria";
import { IconoDeClientes, IconoDeEditar, IconoDeEliminar, IconoDeServicio } from "./iconos";
import { MenuDeAcciones } from "./MenuDeAcciones";

/** Clientes con `Users`, Servicios con `Briefcase`, y las dos para «Clientes y servicios». */
export function AmbitoDeCategoriaPastilla({
  ambito,
}: {
  readonly ambito: AmbitoDeCategoria;
}): JSX.Element {
  const conClientes = ambito === "CLIENTE" || ambito === "AMBOS";
  const conServicios = ambito === "SERVICIO" || ambito === "AMBOS";
  return (
    <span className="mae-etiqueta mae-ambito">
      {conClientes && <IconoDeClientes />}
      {conServicios && <IconoDeServicio />}
      {ETIQUETAS_DE_AMBITO[ambito]}
    </span>
  );
}

export interface PropsDeAccionesDeCategoria {
  readonly categoria: Categoria;
  readonly onEditar: (categoria: Categoria) => void;
  readonly onEliminar: (categoria: Categoria) => void;
}

export function AccionesDeCategoria({
  categoria,
  onEditar,
  onEliminar,
}: PropsDeAccionesDeCategoria): JSX.Element {
  return (
    <span className="mae-acciones">
      <MenuDeAcciones
        etiqueta={`Más acciones para ${categoria.nombre}`}
        items={[
          {
            clave: "editar",
            etiqueta: "Editar",
            icono: <IconoDeEditar />,
            alElegir: () => onEditar(categoria),
          },
          {
            clave: "eliminar",
            etiqueta: "Eliminar",
            icono: <IconoDeEliminar />,
            peligrosa: true,
            alElegir: () => onEliminar(categoria),
          },
        ]}
      />
    </span>
  );
}
