/**
 * The consent boxes (HU-E1-08 RN-03): the terms and the privacy policy are **two separate
 * boxes**, both unticked, each with its own link and its own message.
 *
 * Sign-up shows both; accepting an invitation shows only the policy, because the terms were
 * accepted by the company's Administrator (RN-04). The component is controlled: whoever
 * renders it owns the state and decides when to validate.
 */

import { Casilla } from "@/shared";

import type { Aceptaciones, ErroresDeConsentimiento } from "../validacion/consentimiento";

export interface PropsDeCasillasLegales {
  readonly aceptaciones: Aceptaciones;
  readonly onCambio: (aceptaciones: Aceptaciones) => void;
  readonly errores: ErroresDeConsentimiento;
  /** Accepting an invitation: no terms box. */
  readonly soloPrivacidad?: boolean;
}

export function CasillasLegales({
  aceptaciones,
  onCambio,
  errores,
  soloPrivacidad = false,
}: PropsDeCasillasLegales): JSX.Element {
  return (
    <div className="acc-terminos">
      {!soloPrivacidad && (
        <Casilla
          id="terminos"
          checked={aceptaciones.terminos}
          error={errores.terminos}
          onChange={(evento) => onCambio({ ...aceptaciones, terminos: evento.target.checked })}
        >
          Acepto los{" "}
          <a className="acc-enlace" href="/terminos" target="_blank" rel="noopener noreferrer">
            Términos y Condiciones
          </a>
        </Casilla>
      )}
      <Casilla
        id="privacidad"
        checked={aceptaciones.privacidad}
        error={errores.privacidad}
        onChange={(evento) => onCambio({ ...aceptaciones, privacidad: evento.target.checked })}
      >
        Acepto la{" "}
        <a className="acc-enlace" href="/privacidad" target="_blank" rel="noopener noreferrer">
          Política de Privacidad
        </a>
      </Casilla>
    </div>
  );
}
