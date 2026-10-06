/**
 * Los tres roles, con su etiqueta y con lo que cada uno puede hacer.
 *
 * Viven en un módulo propio porque los usan dos componentes que ya se importan en una sola
 * dirección —`TablaDeUsuarios` trae a `ModalDeInvitacion`, nunca al revés— y dejar el mapa
 * en cualquiera de los dos obligaba a que el otro lo copiara. Dos copias de la frase que
 * explica qué puede un Operador es una copia que algún día va a decir otra cosa.
 *
 * **Las descripciones son texto de pantalla, no la regla.** Quién puede qué lo decide el
 * backend en cada endpoint; esto es lo que se le dice a quien está por elegir un rol para
 * alguien, para que no lo elija a ciegas.
 */

import type { RolUsuario } from "../api/cliente";

export const ETIQUETA_DE_ROL: Record<RolUsuario, string> = {
  ADMINISTRADOR: "Administrador",
  OPERADOR: "Operador",
  SOLO_LECTURA: "Solo lectura",
};

export const QUE_PUEDE: Record<RolUsuario, string> = {
  ADMINISTRADOR: "Configura la empresa, factura, cobra e invita a quien falte.",
  OPERADOR: "El día a día: factura, cobra y agenda. No toca la configuración.",
  SOLO_LECTURA: "Mira y descarga. No modifica nada.",
};

/** El orden en el que se ofrecen y se listan: de más permisos a menos. */
export const ROLES: readonly { readonly valor: RolUsuario; readonly etiqueta: string }[] = [
  { valor: "ADMINISTRADOR", etiqueta: ETIQUETA_DE_ROL.ADMINISTRADOR },
  { valor: "OPERADOR", etiqueta: ETIQUETA_DE_ROL.OPERADOR },
  { valor: "SOLO_LECTURA", etiqueta: ETIQUETA_DE_ROL.SOLO_LECTURA },
];
