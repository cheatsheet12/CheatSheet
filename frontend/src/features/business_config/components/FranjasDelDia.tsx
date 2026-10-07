/**
 * Un renglón del horario de atención: un día de la semana con su interruptor y sus franjas.
 *
 * **Varias franjas por día**: un horario cortado (09:00–13:00 y 16:00–20:00) son dos. Es el
 * patrón de «Agregar franja» / «Quitar» de Recursos. Quitar la última franja apaga el día.
 */

"use client";

import { Button, Campo, Casilla } from "@/shared";

import { DIAS_DE_LA_SEMANA } from "../api/atencion";
import { MEDIANOCHE, nuevaFranja } from "./horario";
import type { DiaEditable, FilaDeFranja } from "./horario";

export interface PropsDeFranjasDelDia {
  readonly dia: DiaEditable;
  readonly error: string | null;
  /** El Operador ve la tarjeta pero no la edita (PAN-WA-02 es «Solo Admin»). */
  readonly deshabilitado: boolean;
  readonly onCambiar: (dia: DiaEditable) => void;
}

export function FranjasDelDia({
  dia,
  error,
  deshabilitado,
  onCambiar,
}: PropsDeFranjasDelDia): JSX.Element {
  const nombre = DIAS_DE_LA_SEMANA[dia.dia] ?? `Día ${dia.dia}`;

  function cambiarFranja(clave: string, cambios: Partial<FilaDeFranja>): void {
    onCambiar({
      ...dia,
      franjas: dia.franjas.map((uno) => (uno.clave === clave ? { ...uno, ...cambios } : uno)),
    });
  }

  function quitarFranja(clave: string): void {
    const franjas = dia.franjas.filter((uno) => uno.clave !== clave);
    // Quitar la última apaga el día: un día encendido sin franjas no significaría nada.
    onCambiar({ ...dia, franjas, activo: franjas.length > 0 });
  }

  function alternar(encendido: boolean): void {
    onCambiar({
      ...dia,
      activo: encendido,
      franjas: encendido && dia.franjas.length === 0 ? [nuevaFranja()] : dia.franjas,
    });
  }

  return (
    <li className="hda-dia">
      <Casilla
        id={`hda-dia-${dia.dia}`}
        checked={dia.activo}
        disabled={deshabilitado}
        onChange={(evento) => alternar(evento.target.checked)}
      >
        {nombre}
      </Casilla>

      {dia.activo ? (
        <div className="hda-franjas">
          {dia.franjas.map((franja, indice) => {
            const etiqueta = `${nombre}, franja ${indice + 1}`;
            const hastaMedianoche = franja.hasta === MEDIANOCHE;
            return (
              <div className="hda-franja" key={franja.clave}>
                <Campo
                  id={`hda-desde-${franja.clave}`}
                  etiqueta="Desde"
                  aria-label={`Desde (${etiqueta})`}
                  type="time"
                  value={franja.desde}
                  disabled={deshabilitado}
                  onChange={(evento) => cambiarFranja(franja.clave, { desde: evento.target.value })}
                />
                <Campo
                  id={`hda-hasta-${franja.clave}`}
                  etiqueta="Hasta"
                  aria-label={`Hasta (${etiqueta})`}
                  type="time"
                  value={hastaMedianoche ? "" : franja.hasta}
                  disabled={deshabilitado || hastaMedianoche}
                  onChange={(evento) => cambiarFranja(franja.clave, { hasta: evento.target.value })}
                />
                <Casilla
                  id={`hda-medianoche-${franja.clave}`}
                  aria-label={`Hasta la medianoche (${etiqueta})`}
                  checked={hastaMedianoche}
                  disabled={deshabilitado}
                  onChange={(evento) =>
                    cambiarFranja(franja.clave, { hasta: evento.target.checked ? MEDIANOCHE : "" })
                  }
                >
                  Hasta la medianoche
                </Casilla>
                {!deshabilitado && (
                  <Button variante="secundario" onClick={() => quitarFranja(franja.clave)}>
                    Quitar
                  </Button>
                )}
              </div>
            );
          })}
          {!deshabilitado && (
            <Button
              variante="secundario"
              onClick={() =>
                onCambiar({ ...dia, franjas: [...dia.franjas, nuevaFranja("16:00", "20:00")] })
              }
            >
              Agregar franja
            </Button>
          )}
        </div>
      ) : (
        <span className="hda-cerrado">Cerrado</span>
      )}

      {error !== null && (
        <span className="campo__error" role="alert">
          {error}
        </span>
      )}
    </li>
  );
}
