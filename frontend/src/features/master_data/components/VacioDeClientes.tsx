/**
 * El listado de clientes cuando no hay filas.
 *
 * Hay dos vacíos distintos y se dicen distinto: un catálogo que todavía no tiene clientes
 * —y entonces lo útil es crear el primero— y un filtro que no encontró nada —y entonces lo útil
 * es quitarlo—. Mostrar «Nuevo cliente» en el segundo caso le diría a alguien que no hay nadie
 * cuando el que no está es el nombre que buscó.
 */

import { IconoDeClientes, IconoDeMas } from "./iconos";

export interface PropsDeVacio {
  readonly hayFiltros: boolean;
  readonly puedeEditar: boolean;
  readonly onNuevo: () => void;
  readonly onLimpiar: () => void;
}

export function VacioDeClientes({
  hayFiltros,
  puedeEditar,
  onNuevo,
  onLimpiar,
}: PropsDeVacio): JSX.Element {
  return (
    <div className="mae-vacio">
      <span className="mae-vacio__icono" aria-hidden="true">
        <IconoDeClientes />
      </span>
      <p className="mae-vacio__titulo">
        {hayFiltros ? "Ningún cliente coincide" : "Todavía no hay clientes en el catálogo."}
      </p>
      <p className="mae-vacio__texto">
        {hayFiltros
          ? "Probá con otra búsqueda o quitá algún filtro."
          : "Creá el primero y quedará disponible para facturar, cobrar y agendar."}
      </p>
      {hayFiltros ? (
        <button type="button" className="mae-vacio__accion" onClick={onLimpiar}>
          Limpiar filtros
        </button>
      ) : (
        puedeEditar && (
          <button type="button" className="mae-cta mae-cta--compacto" onClick={onNuevo}>
            <span className="mae-cta__icono" aria-hidden="true">
              <IconoDeMas />
            </span>
            Nuevo cliente
          </button>
        )
      )}
    </div>
  );
}
