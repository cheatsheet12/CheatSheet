/**
 * La tarjeta «Fechas sin atención»: feriados y vacaciones del negocio (HS-T2 RN-04).
 *
 * Réplica de la tarjeta «Excepciones» de Recursos, con tres diferencias que importan:
 *
 * - **No guarda al instante.** Edita el estado de la tarjeta y se guarda con «Guardar» del
 *   horario: el `PUT` reemplaza la regla entera.
 * - **No bloquea turnos.** El horario de atención no es la disponibilidad de los recursos: para
 *   que un recurso no se pueda reservar ese día, se carga su excepción en cada recurso.
 * - **Las fechas pasadas no se muestran, pero viajan.** El backend las usa para calcular «desde
 *   cuándo está cerrado» y las poda solo pasado un año; ocultarlas **y** descartarlas cambiaría
 *   el cálculo de la noche en curso.
 */

"use client";

import { useState } from "react";

import { Button, Card, SelectorDeFecha, Tabla } from "@/shared";

import { MAXIMO_DE_FECHAS } from "../api/atencion";

export interface PropsDeFechasSinAtencion {
  /** Todas las fechas de la regla, también las pasadas. */
  readonly fechas: readonly string[];
  /** Hoy en Argentina (`AAAA-MM-DD`). */
  readonly hoy: string;
  readonly deshabilitado: boolean;
  readonly onCambiar: (fechas: string[]) => void;
}

export function FechasSinAtencion({
  fechas,
  hoy,
  deshabilitado,
  onCambiar,
}: PropsDeFechasSinAtencion): JSX.Element {
  const [nueva, setNueva] = useState("");
  const visibles = fechas.filter((fecha) => fecha >= hoy).sort();
  const repetida = fechas.includes(nueva);
  const sinCupo = fechas.length >= MAXIMO_DE_FECHAS;

  function agregar(): void {
    if (nueva === "" || repetida || sinCupo || nueva < hoy) {
      return;
    }
    onCambiar([...fechas, nueva]);
    setNueva("");
  }

  return (
    <Card titulo="Fechas sin atención">
      <p className="dm-intro">
        Un feriado o unas vacaciones: ese día se atiende como fuera de horario. No bloquea los
        turnos: para eso, cargá la excepción en cada recurso.
      </p>
      <Tabla
        titulo=""
        columnas={[
          {
            clave: "fecha",
            titulo: "Fecha",
            celda: (fila) => <span className="age-fecha-iso">{fila}</span>,
          },
          {
            clave: "acciones",
            titulo: "Acciones",
            alDerecha: true,
            celda: (fila) =>
              deshabilitado ? null : (
                <Button
                  variante="secundario"
                  onClick={() => onCambiar(fechas.filter((otra) => otra !== fila))}
                >
                  Quitar
                </Button>
              ),
          },
        ]}
        filas={visibles}
        claveDeFila={(fila) => fila}
        vacia="No hay fechas sin atención cargadas."
      />
      {!deshabilitado && (
        <div className="age-excepcion">
          <SelectorDeFecha
            id="fecha-sin-atencion"
            etiqueta="Día sin atención"
            min={hoy}
            value={nueva}
            error={repetida ? "Esa fecha ya está cargada." : undefined}
            alCambiar={setNueva}
          />
          <Button
            variante="secundario"
            disabled={nueva === "" || repetida || sinCupo || nueva < hoy}
            onClick={agregar}
          >
            Agregar fecha
          </Button>
        </div>
      )}
    </Card>
  );
}
