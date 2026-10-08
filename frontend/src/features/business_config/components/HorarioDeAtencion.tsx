/**
 * PAN-WA-02 — la tarjeta «Horarios de atención» (HS-T2 RN-04, HU-E11-01).
 *
 * El prototipo muestra un renglón por día con su interruptor y «Zona horaria: ART (GMT-3)». Esta
 * tarjeta agrega lo mínimo que el prototipo no tiene: **varias franjas por día** (horario
 * cortado), **fechas sin atención** y **la política fuera de horario**, la opción (c) de I-09:
 *
 * - *El agente responde igual*: sigue atendiendo, y al derivar avisa desde cuándo atiende un
 *   asesor. Es la política por defecto.
 * - *El agente no responde y envía un mensaje fijo*: un mensaje por período de cierre.
 *
 * **Sin regla configurada nada cambia**: el agente atiende y deriva a cualquier hora. La tarjeta
 * precarga los valores del prototipo, pero no los guarda hasta que el Administrador lo pide.
 *
 * El horario es una regla de negocio más: desactivarla en PAN-CFG-RN deja de aplicarla de
 * inmediato, y guardar la reactiva.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Card } from "@/shared";

import { MENSAJE_SIN_HORARIO, configurarHorarioDeAtencion } from "../api/atencion";
import type { HorarioDeAtencionGuardado, PoliticaFueraDeHorario } from "../api/atencion";
import { FechasSinAtencion } from "./FechasSinAtencion";
import { FranjasDelDia } from "./FranjasDelDia";
import {
  MENSAJE_SIN_DIAS,
  aDias,
  diasDelPrototipo,
  diasEditables,
  errorDelDia,
  hayAlgunDia,
  hoyEnArgentina,
} from "./horario";
import type { DiaEditable } from "./horario";

export interface PropsDeHorarioDeAtencion {
  /** `null` cuando la empresa nunca configuró un horario. */
  readonly inicial: HorarioDeAtencionGuardado | null;
  /** Sólo el Administrador edita; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
  /** Hoy en Argentina. Sólo se inyecta en los tests. */
  readonly hoy?: string;
}

const POLITICAS: readonly {
  readonly valor: PoliticaFueraDeHorario;
  readonly etiqueta: string;
}[] = [
  {
    valor: "AGENTE_RESPONDE",
    etiqueta: "El agente responde igual (avisa desde cuándo atiende un asesor)",
  },
  {
    valor: "MENSAJE_FIJO",
    etiqueta: "El agente no responde y envía un mensaje fijo",
  },
];

export function HorarioDeAtencion({
  inicial,
  puedeEditar,
  hoy,
}: PropsDeHorarioDeAtencion): JSX.Element {
  const [guardado, setGuardado] = useState(inicial);
  const [dias, setDias] = useState<DiaEditable[]>(() =>
    inicial === null ? diasDelPrototipo() : diasEditables(inicial.dias),
  );
  const [politica, setPolitica] = useState<PoliticaFueraDeHorario>(
    inicial?.politica ?? "AGENTE_RESPONDE",
  );
  const [fechas, setFechas] = useState<readonly string[]>(inicial?.fechas_cerradas ?? []);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);

  const errores = dias.map(errorDelDia);
  const sinDias = !hayAlgunDia(dias);
  const invalido = sinDias || errores.some((uno) => uno !== null);

  function cambiarDia(cambiado: DiaEditable): void {
    setDias((previos) => previos.map((uno) => (uno.dia === cambiado.dia ? cambiado : uno)));
    setExito(false);
  }

  async function guardar(): Promise<void> {
    setTrabajando(true);
    setError(null);
    setExito(false);
    try {
      const nuevo = await configurarHorarioDeAtencion(
        { dias: aDias(dias), fechas_cerradas: [...fechas].sort(), politica },
        guardado?.prioridad ?? 0,
      );
      setGuardado(nuevo);
      setExito(true);
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo guardar el horario.");
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <div className="hda-pantalla">
      <Card titulo="Horarios de atención">
        <p className="dm-intro">Cuándo atiende el negocio. Zona horaria: ART (GMT-3).</p>

        {guardado === null && <Alert tono="neutral">{MENSAJE_SIN_HORARIO}</Alert>}
        {guardado !== null && !guardado.activa && (
          <Alert tono="advertencia">
            Este horario está desactivado en las reglas de negocio: el agente atiende y deriva a
            cualquier hora. Guardar lo vuelve a activar.
          </Alert>
        )}

        <ul className="hda-dias">
          {dias.map((dia, indice) => (
            <FranjasDelDia
              key={dia.dia}
              dia={dia}
              error={errores[indice] ?? null}
              deshabilitado={!puedeEditar}
              onCambiar={cambiarDia}
            />
          ))}
        </ul>
        {sinDias && (
          <span className="campo__error" role="alert">
            {MENSAJE_SIN_DIAS}
          </span>
        )}

        <fieldset className="hda-politica" disabled={!puedeEditar}>
          <legend className="campo__etiqueta">Fuera de horario</legend>
          {POLITICAS.map((opcion) => (
            <label className="hda-politica__opcion" key={opcion.valor}>
              <input
                type="radio"
                name="politica-fuera-de-horario"
                value={opcion.valor}
                checked={politica === opcion.valor}
                onChange={() => {
                  setPolitica(opcion.valor);
                  setExito(false);
                }}
              />
              {opcion.etiqueta}
            </label>
          ))}
        </fieldset>
      </Card>

      <FechasSinAtencion
        fechas={fechas}
        hoy={hoy ?? hoyEnArgentina()}
        deshabilitado={!puedeEditar}
        onCambiar={(nuevas) => {
          setFechas(nuevas);
          setExito(false);
        }}
      />

      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
        </Alert>
      )}
      {exito && <Alert tono="exito">Horario guardado.</Alert>}

      {puedeEditar && (
        <div className="dm-formulario__acciones">
          <Button disabled={invalido} cargando={trabajando} onClick={() => void guardar()}>
            Guardar
          </Button>
        </div>
      )}
    </div>
  );
}
