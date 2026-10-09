/**
 * Los motivos con los que Meta rechaza una plantilla, en castellano (U6, PAN-CFG-NOT).
 *
 * Meta devuelve un **código** (`rejected_reason`): `PROMOTIONAL`, `INVALID_FORMAT`… El
 * administrador no tiene por qué saber qué dice. Es una cortesía de la pantalla: el texto
 * literal de Meta (`detalle_meta`) se muestra aparte, sin traducir, y un código que no está en
 * la tabla se muestra tal cual llegó en vez de inventarle una frase.
 */

const PROMOCIONAL = "Meta lo considera promocional: no corresponde a Utilidad";

const MOTIVOS: Readonly<Record<string, string>> = {
  ABUSIVE_CONTENT: "Meta lo consideró abusivo",
  INVALID_FORMAT: "Formato inválido: revisá variables y largo",
  PROMOTIONAL: PROMOCIONAL,
  INCORRECT_CATEGORY: PROMOCIONAL,
  TAG_CONTENT_MISMATCH: PROMOCIONAL,
  SCAM: "Meta lo consideró engañoso",
};

/** La frase para un código de motivo, o `null` si no hay motivo. */
export function traducirMotivoDeMeta(motivo: string | null): string | null {
  if (motivo === null) {
    return null;
  }
  return MOTIVOS[motivo] ?? `Motivo informado por Meta: ${motivo}`;
}
