/**
 * The consent a person gives when an account is born (HU-E1-03 RN-02, HU-E1-08 RN-03).
 *
 * The messages are the ones the stories dictate, as amended by ADR-0009, and the backend
 * answers with the very same words. **This only decides whether to bother the server:** the
 * rule itself — both versions in force, nothing else — is enforced by the API, so skipping
 * this check could never create an account without consent.
 */

export const MENSAJE_DE_TERMINOS = "Debe aceptar los términos y condiciones para continuar.";
export const MENSAJE_DE_PRIVACIDAD = "Debe aceptar la política de privacidad para continuar.";

export interface Aceptaciones {
  readonly terminos: boolean;
  readonly privacidad: boolean;
}

export interface ErroresDeConsentimiento {
  readonly terminos?: string;
  readonly privacidad?: string;
}

/**
 * Which boxes are still unticked. `requiereTerminos` is false for an invited person: the
 * terms were accepted by the company's Administrator (HU-E1-08 RN-04).
 */
export function validarConsentimiento(
  aceptaciones: Aceptaciones,
  requiereTerminos: boolean,
): ErroresDeConsentimiento {
  return {
    ...(requiereTerminos && !aceptaciones.terminos ? { terminos: MENSAJE_DE_TERMINOS } : {}),
    ...(!aceptaciones.privacidad ? { privacidad: MENSAJE_DE_PRIVACIDAD } : {}),
  };
}

export function hayErrores(errores: ErroresDeConsentimiento): boolean {
  return errores.terminos !== undefined || errores.privacidad !== undefined;
}
