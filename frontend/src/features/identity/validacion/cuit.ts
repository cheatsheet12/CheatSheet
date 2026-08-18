/**
 * CUIT check digit, in the browser.
 *
 * **This is not business logic moving to the frontend.** CLAUDE.md §5 forbids the panel
 * computing taxes, and it does not: the authority on whether a CUIT is acceptable is
 * `contexts/identity/domain/valores.py`, which validates it again on every request. This
 * copy exists for one reason the specification names explicitly — «"Continuar"
 * permanece deshabilitado mientras el CUIT no sea válido» — and a round trip per
 * keystroke is not how you keep a button in sync with a field.
 *
 * The two implementations must agree. They are both the same published algorithm, and
 * the backend is the one that decides.
 */

const LARGO = 11;
/** ARCA's weights, in order. */
const MULTIPLICADORES = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2] as const;

/** Strips whatever separators the accountant's notation uses. */
export function normalizarCuit(entrada: string): string {
  return entrada.replace(/[^0-9]/g, "");
}

export function esCuitValido(entrada: string): boolean {
  const digitos = normalizarCuit(entrada);
  if (digitos.length !== LARGO) {
    return false;
  }
  const suma = MULTIPLICADORES.reduce(
    (acumulado, multiplicador, indice) => acumulado + Number(digitos[indice]) * multiplicador,
    0,
  );
  const resto = suma % 11;
  let esperado = 11 - resto;
  if (esperado === 11) {
    esperado = 0;
  } else if (esperado === 10) {
    // 10 is never assigned as a check digit, so no CUIT ends in it.
    return false;
  }
  return esperado === Number(digitos[LARGO - 1]);
}

/** The message the specification prescribes for each case, or null when it is fine. */
export function errorDeCuit(entrada: string): string | null {
  const digitos = normalizarCuit(entrada);
  if (digitos.length === 0) {
    return null; // Nothing typed yet is not an error to shout about.
  }
  if (digitos.length !== LARGO) {
    return "Ingresá los 11 dígitos del CUIT.";
  }
  if (!esCuitValido(digitos)) {
    return "El CUIT no supera la validación del dígito verificador.";
  }
  return null;
}

export function formatearCuit(entrada: string): string {
  const digitos = normalizarCuit(entrada);
  if (digitos.length !== LARGO) {
    return entrada;
  }
  return `${digitos.slice(0, 2)}-${digitos.slice(2, 10)}-${digitos.slice(10)}`;
}
