/**
 * Step indicator — specification §1.3, "Stepper de pasos".
 *
 * Completed is a green circle with a tick, active is a circle with its number, pending
 * is grey. Used by the onboarding flow and by the ingest flow.
 *
 * It is an `<ol>` because it is an ordered list of steps, and the current one is marked
 * with `aria-current`: a person who cannot see the colours still learns where they are.
 */

export interface Paso {
  readonly numero: number;
  readonly nombre: string;
}

export interface PropsDeStepper {
  readonly pasos: readonly Paso[];
  /** 1-based. Everything before it is completed; everything after is pending. */
  readonly actual: number;
}

export function Stepper({ pasos, actual }: PropsDeStepper): JSX.Element {
  return (
    <ol className="stepper" aria-label="Progreso del onboarding">
      {pasos.map((paso) => {
        const completado = paso.numero < actual;
        const activo = paso.numero === actual;
        const estado = completado
          ? " stepper__paso--completado"
          : activo
            ? " stepper__paso--activo"
            : "";
        return (
          <li
            key={paso.numero}
            className={`stepper__paso${estado}`}
            aria-current={activo ? "step" : undefined}
          >
            <span className="stepper__marca" aria-hidden="true">
              {completado ? "✓" : paso.numero}
            </span>
            {paso.nombre}
          </li>
        );
      })}
    </ol>
  );
}
