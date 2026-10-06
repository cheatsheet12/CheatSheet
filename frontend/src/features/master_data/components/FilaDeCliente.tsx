/**
 * Lo que dibuja cada fila del listado de clientes: el avatar con iniciales y las acciones.
 *
 * Vive aparte de `ListadoDeClientes` para que ese archivo siga siendo lo que su nombre dice —el
 * estado y las llamadas— y estos dos pedazos, que son sólo presentación, se puedan leer sin él.
 *
 * **Las acciones conservan exactamente lo que había.** Facturar, Cobrar y Agendar siguen siendo
 * enlaces con `?cliente=`; Editar y Desactivar/Reactivar siguen llamando a los mismos manejadores;
 * lo que cambió es cómo se ofrecen: las tres que se usan todos los días como botones de icono, y
 * Editar y la baja dentro del menú ⋯, para que la baja —la única que quita algo del catálogo—
 * quede a dos clics y no a uno.
 */

"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import type { Cliente } from "../api/cliente";
import {
  IconoDeBaja,
  IconoDeCobro,
  IconoDeEditar,
  IconoDeFactura,
  IconoDeReactivar,
  IconoDeTurno,
} from "./iconos";
import { MenuDeAcciones } from "./MenuDeAcciones";
import type { ItemDeMenu } from "./MenuDeAcciones";

/**
 * Las tres pantallas que sólo se pueden abrir con un cliente ya elegido.
 *
 * `/facturacion/nueva`, `/cobros/nuevo` y `/agenda/nuevo` leen `?cliente=` y, si no está,
 * responden «Elegí primero a quién…». Van sólo en las filas activas: un cliente dado de baja
 * salió del catálogo, y ofrecerle «Facturar» sería ofrecer algo que el catálogo ya decidió que
 * no está disponible. El rol se controla con el mismo `puedeEditar` que gobierna el resto de
 * las acciones, porque las tres pantallas destino redirigen a quien no es Administrador u
 * Operador.
 */
const DESTINOS = [
  { etiqueta: "Facturar", ruta: "/facturacion/nueva", icono: <IconoDeFactura /> },
  { etiqueta: "Cobrar", ruta: "/cobros/nuevo", icono: <IconoDeCobro /> },
  { etiqueta: "Agendar", ruta: "/agenda/nuevo", icono: <IconoDeTurno /> },
] as const;

/** Las iniciales: la primera letra de las dos primeras palabras, o las dos primeras de una. */
export function inicialesDe(nombre: string): string {
  const palabras = nombre.trim().split(/\s+/).filter(Boolean);
  if (palabras.length === 0) {
    return "?";
  }
  const [primera = "", segunda] = palabras;
  const letras =
    segunda === undefined ? primera.slice(0, 2) : `${primera[0] ?? ""}${segunda[0] ?? ""}`;
  return letras.toUpperCase();
}

/**
 * Un tono estable por nombre: el mismo cliente tiene siempre el mismo color, en cualquier
 * pantalla y en cualquier recarga. Va sólo por el rango azul–violeta: el verde queda reservado
 * a lo activo y el rojo a lo que advierte, y un avatar no es ninguna de las dos cosas.
 */
export function tonoDe(nombre: string): number {
  let suma = 0;
  for (const caracter of nombre) {
    suma = (suma * 31 + caracter.charCodeAt(0)) % 997;
  }
  return 205 + (suma % 6) * 20;
}

export function AvatarDeCliente({ nombre }: { readonly nombre: string }): JSX.Element {
  return (
    <span
      className="mae-avatar"
      aria-hidden="true"
      style={{ "--mae-tono": tonoDe(nombre) } as CSSProperties}
    >
      {inicialesDe(nombre)}
    </span>
  );
}

export interface PropsDeAcciones {
  readonly cliente: Cliente;
  readonly onEditar: (cliente: Cliente) => void;
  readonly onAlternarEstado: (cliente: Cliente) => void;
}

export function AccionesDeCliente({
  cliente,
  onEditar,
  onAlternarEstado,
}: PropsDeAcciones): JSX.Element {
  const items: ItemDeMenu[] = [
    {
      clave: "editar",
      etiqueta: "Editar",
      icono: <IconoDeEditar />,
      alElegir: () => onEditar(cliente),
    },
  ];
  if (cliente.activo) {
    items.push({
      clave: "desactivar",
      etiqueta: "Desactivar",
      icono: <IconoDeBaja />,
      peligrosa: true,
      alElegir: () => onAlternarEstado(cliente),
    });
  }

  return (
    <span className="mae-acciones">
      {cliente.activo ? (
        DESTINOS.map(({ etiqueta, ruta, icono }) => (
          <Link
            key={ruta}
            className="mae-icono-accion"
            href={`${ruta}?cliente=${encodeURIComponent(cliente.id)}`}
            aria-label={etiqueta}
            data-tip={etiqueta}
          >
            {icono}
          </Link>
        ))
      ) : (
        <button
          type="button"
          className="mae-icono-accion mae-icono-accion--texto"
          onClick={() => onAlternarEstado(cliente)}
        >
          <IconoDeReactivar />
          Reactivar
        </button>
      )}
      <MenuDeAcciones etiqueta={`Más acciones para ${cliente.nombre}`} items={items} />
    </span>
  );
}
