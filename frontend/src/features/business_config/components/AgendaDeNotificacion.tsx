/**
 * PAN-CFG-RN — la tarjeta «Recordatorios de turno» (HU-E11-01, HU-E8-04 RN-02).
 *
 * Hasta tres filas «N horas antes del turno» (1 a 168), sin repetidos. Se guardan ordenadas de
 * mayor a menor anticipación, y el backend es quien manda: acá sólo se evita el viaje inútil.
 *
 * **Sin regla configurada** rige un recordatorio 24 horas antes; la tarjeta precarga ese valor
 * pero no lo guarda hasta que el Administrador lo pide. **Con la regla desactivada** los
 * recordatorios están apagados —no vuelve el default—, y guardar la reactiva.
 */

"use client";

import { useRef, useState } from "react";

import { Alert, Button, Campo, Card } from "@/shared";

import {
  HORAS_POR_DEFECTO,
  MAXIMO_DE_HORAS,
  MAXIMO_DE_RECORDATORIOS,
  MENSAJE_AGENDA_DESACTIVADA,
  MENSAJE_HORAS_FUERA_DE_RANGO,
  MENSAJE_REPETIDOS,
  MENSAJE_SIN_AGENDA,
  MINIMO_DE_HORAS,
  configurarAgenda,
} from "../api/agenda";
import type { AgendaGuardada } from "../api/agenda";

export interface PropsDeAgendaDeNotificacion {
  /** `null` cuando la empresa nunca configuró una agenda. */
  readonly inicial: AgendaGuardada | null;
  /** Sólo el Administrador edita; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

interface FilaEditable {
  readonly clave: number;
  readonly horas: string;
}

const ENTERO = /^\d+$/;

function errorDeLaFila(fila: FilaEditable, todas: readonly FilaEditable[]): string | null {
  const texto = fila.horas.trim();
  if (!ENTERO.test(texto)) {
    return MENSAJE_HORAS_FUERA_DE_RANGO;
  }
  const horas = Number.parseInt(texto, 10);
  if (horas < MINIMO_DE_HORAS || horas > MAXIMO_DE_HORAS) {
    return MENSAJE_HORAS_FUERA_DE_RANGO;
  }
  const iguales = todas.filter((otra) => otra.horas.trim() === texto);
  return iguales.length > 1 ? MENSAJE_REPETIDOS : null;
}

export function AgendaDeNotificacion({
  inicial,
  puedeEditar,
}: PropsDeAgendaDeNotificacion): JSX.Element {
  const contador = useRef(0);
  const nuevaClave = (): number => {
    contador.current += 1;
    return contador.current;
  };

  const [guardada, setGuardada] = useState(inicial);
  const [filas, setFilas] = useState<FilaEditable[]>(() => {
    const horas =
      inicial === null || inicial.recordatorios.length === 0
        ? [HORAS_POR_DEFECTO]
        : inicial.recordatorios.map((uno) => uno.horas_antes);
    return horas.map((valor) => ({ clave: nuevaClave(), horas: String(valor) }));
  });
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);

  const errores = filas.map((fila) => errorDeLaFila(fila, filas));
  const invalida = filas.length === 0 || errores.some((uno) => uno !== null);

  function cambiar(clave: number, horas: string): void {
    setFilas((previas) =>
      previas.map((fila) => (fila.clave === clave ? { ...fila, horas } : fila)),
    );
    setExito(false);
  }

  function quitar(clave: number): void {
    setFilas((previas) => previas.filter((fila) => fila.clave !== clave));
    setExito(false);
  }

  function agregar(): void {
    setFilas((previas) => [...previas, { clave: nuevaClave(), horas: "" }]);
    setExito(false);
  }

  async function guardar(): Promise<void> {
    setTrabajando(true);
    setError(null);
    setExito(false);
    try {
      const nueva = await configurarAgenda(
        filas.map((fila) => ({ horas_antes: Number.parseInt(fila.horas.trim(), 10) })),
        guardada?.prioridad ?? 0,
      );
      setGuardada(nueva);
      setExito(true);
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo guardar la agenda.");
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <Card titulo="Recordatorios de turno">
      <p className="dm-intro">
        Cuántas horas antes del turno recibe el cliente un recordatorio por WhatsApp. Podés
        configurar hasta {MAXIMO_DE_RECORDATORIOS}.
      </p>

      {guardada === null && <Alert tono="neutral">{MENSAJE_SIN_AGENDA}</Alert>}
      {guardada !== null && !guardada.activa && (
        <Alert tono="advertencia">{MENSAJE_AGENDA_DESACTIVADA}</Alert>
      )}

      <ul className="ran-filas">
        {filas.map((fila, indice) => (
          <li className="ran-fila" key={fila.clave}>
            <Campo
              id={`ran-horas-${fila.clave}`}
              etiqueta={`Horas antes del turno (recordatorio ${indice + 1})`}
              type="number"
              inputMode="numeric"
              min={MINIMO_DE_HORAS}
              max={MAXIMO_DE_HORAS}
              value={fila.horas}
              disabled={!puedeEditar}
              error={fila.horas === "" ? undefined : (errores[indice] ?? undefined)}
              onChange={(evento) => cambiar(fila.clave, evento.target.value)}
            />
            {puedeEditar && filas.length > 1 && (
              <Button variante="secundario" onClick={() => quitar(fila.clave)}>
                Quitar
              </Button>
            )}
          </li>
        ))}
      </ul>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
        </Alert>
      )}
      {exito && <Alert tono="exito">Agenda guardada.</Alert>}

      {puedeEditar && (
        <div className="dm-formulario__acciones">
          <Button
            variante="secundario"
            disabled={filas.length >= MAXIMO_DE_RECORDATORIOS}
            onClick={agregar}
          >
            Agregar recordatorio
          </Button>
          <Button disabled={invalida} cargando={trabajando} onClick={() => void guardar()}>
            Guardar
          </Button>
        </div>
      )}
    </Card>
  );
}
