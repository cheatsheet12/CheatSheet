/**
 * La descripción de un ítem, con sugerencias del catálogo de Servicios.
 *
 * Es un combobox (patrón ARIA «list autocomplete»): se escribe, se filtran los servicios activos
 * por nombre, y flechas / Enter / Esc / clic eligen o cierran. **Elegir es opcional**: lo que se
 * escribe sigue siendo la descripción, así que un ítem que no está en el catálogo se factura igual.
 *
 * El precio de la sugerencia se muestra como texto tal como viene de la API: no se convierte ni
 * se opera con él.
 */

"use client";

import { useId, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";

import { Campo } from "@/shared";
import type { Servicio } from "@/features/master_data";

import { ALICUOTAS } from "../api/comprobante";

const MAXIMO_DE_SUGERENCIAS = 6;

function normalizar(texto: string): string {
  return texto.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

/** La etiqueta de la alícuota del servicio, la misma que ofrece el select de IVA. */
export function etiquetaDeAlicuota(valor: string): string {
  return ALICUOTAS.find((alicuota) => alicuota.valor === valor)?.etiqueta ?? `IVA ${valor}`;
}

export interface PropsDeCampoDeServicio {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly servicios: readonly Servicio[];
  readonly alCambiar: (texto: string) => void;
  readonly alElegir: (servicio: Servicio) => void;
}

export function CampoDeServicio({
  id,
  etiqueta,
  valor,
  servicios,
  alCambiar,
  alElegir,
}: PropsDeCampoDeServicio): JSX.Element {
  const idLista = `${useId()}-sugerencias`;
  const [abierto, setAbierto] = useState(false);
  const [resaltado, setResaltado] = useState(-1);

  const sugerencias = useMemo(() => {
    const aguja = normalizar(valor.trim());
    return servicios
      .filter((servicio) => servicio.activo)
      .filter((servicio) => aguja === "" || normalizar(servicio.nombre).includes(aguja))
      .slice(0, MAXIMO_DE_SUGERENCIAS);
  }, [servicios, valor]);

  const visible = abierto && sugerencias.length > 0;

  function elegir(servicio: Servicio): void {
    alElegir(servicio);
    setAbierto(false);
    setResaltado(-1);
  }

  function alTeclear(evento: KeyboardEvent<HTMLInputElement>): void {
    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
      if (sugerencias.length === 0) {
        return;
      }
      evento.preventDefault();
      setAbierto(true);
      const paso = evento.key === "ArrowDown" ? 1 : -1;
      setResaltado((actual) => (actual + paso + sugerencias.length) % sugerencias.length);
    } else if (evento.key === "Enter" && visible && resaltado >= 0) {
      // Sólo si hay una sugerencia resaltada: sin ella Enter no hace nada especial.
      evento.preventDefault();
      const elegida = sugerencias[resaltado];
      if (elegida !== undefined) {
        elegir(elegida);
      }
    } else if (evento.key === "Escape" && visible) {
      evento.preventDefault();
      setAbierto(false);
      setResaltado(-1);
    }
  }

  return (
    <div className="fac-em-sugerencias">
      <Campo
        id={id}
        etiqueta={etiqueta}
        value={valor}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={visible}
        aria-controls={idLista}
        aria-activedescendant={visible && resaltado >= 0 ? `${idLista}-${resaltado}` : undefined}
        onChange={(evento) => {
          alCambiar(evento.target.value);
          setAbierto(true);
          setResaltado(-1);
        }}
        onFocus={() => setAbierto(true)}
        onBlur={() => setAbierto(false)}
        onKeyDown={alTeclear}
      />
      {visible && (
        <ul
          className="fac-em-sugerencias__lista"
          id={idLista}
          role="listbox"
          aria-label="Servicios"
        >
          {sugerencias.map((servicio, indice) => (
            <li
              key={servicio.id}
              id={`${idLista}-${indice}`}
              role="option"
              aria-selected={indice === resaltado}
              className={`fac-em-sugerencias__opcion${
                indice === resaltado ? " fac-em-sugerencias__opcion--resaltada" : ""
              }`}
              // `mousedown` y no `click`: el blur del campo cerraría la lista antes del clic.
              onMouseDown={(evento) => {
                evento.preventDefault();
                elegir(servicio);
              }}
              onMouseEnter={() => setResaltado(indice)}
            >
              <span className="fac-em-sugerencias__nombre">{servicio.nombre}</span>
              <span className="fac-em-sugerencias__precio">
                $ {servicio.precio} · {etiquetaDeAlicuota(servicio.alicuota_iva)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
