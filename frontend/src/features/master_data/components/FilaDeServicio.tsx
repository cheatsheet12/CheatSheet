/**
 * Lo que dibuja cada fila del listado de servicios: las celdas de precio, IVA y duración, y las
 * acciones.
 *
 * **El precio se muestra, no se calcula.** Llega como texto y sale como texto (formateado con el
 * helper de la pantalla); el IVA es una etiqueta al lado, no una suma. El total que paga el cliente
 * lo arma el comprobante.
 *
 * Editar y Desactivar van en el menú ⋯. Un servicio inactivo ofrece «Reactivar» a la vista, como
 * los clientes, porque no hay nada que confirmar.
 */

"use client";

import type { Servicio } from "../api/servicio";
import { IconoDeBaja, IconoDeEditar, IconoDeReactivar, IconoDeReloj } from "./iconos";
import { MenuDeAcciones } from "./MenuDeAcciones";
import type { ItemDeMenu } from "./MenuDeAcciones";

/** «90 min» como etiqueta con reloj, o un guion atenuado si el servicio no se agenda. */
export function DuracionDeServicio({ minutos }: { readonly minutos: number | null }): JSX.Element {
  if (minutos === null) {
    return <span className="mae-dato mae-dato--tenue">—</span>;
  }
  return (
    <span className="mae-etiqueta mae-etiqueta--mono">
      <IconoDeReloj />
      {`${minutos} min`}
    </span>
  );
}

export interface PropsDeAccionesDeServicio {
  readonly servicio: Servicio;
  readonly onEditar: (servicio: Servicio) => void;
  readonly onAlternarEstado: (servicio: Servicio) => void;
}

export function AccionesDeServicio({
  servicio,
  onEditar,
  onAlternarEstado,
}: PropsDeAccionesDeServicio): JSX.Element {
  const items: ItemDeMenu[] = [
    {
      clave: "editar",
      etiqueta: "Editar",
      icono: <IconoDeEditar />,
      alElegir: () => onEditar(servicio),
    },
  ];
  if (servicio.activo) {
    items.push({
      clave: "desactivar",
      etiqueta: "Desactivar",
      icono: <IconoDeBaja />,
      peligrosa: true,
      alElegir: () => onAlternarEstado(servicio),
    });
  }

  return (
    <span className="mae-acciones">
      {!servicio.activo && (
        <button
          type="button"
          className="mae-icono-accion mae-icono-accion--texto"
          onClick={() => onAlternarEstado(servicio)}
        >
          <IconoDeReactivar />
          Reactivar
        </button>
      )}
      <MenuDeAcciones etiqueta={`Más acciones para ${servicio.nombre}`} items={items} />
    </span>
  );
}
