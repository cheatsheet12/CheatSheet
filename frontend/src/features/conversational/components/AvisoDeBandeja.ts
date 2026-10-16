/**
 * El canal por el que el hilo abierto le avisa a la bandeja que algo cambió (HU-E9-01).
 *
 * La bandeja y el hilo son hermanos y muestran el mismo dato —el estado del escalamiento—. El
 * hilo, al actuar, sólo refrescaba el suyo, y la bandeja seguía diciendo «Espera un asesor».
 * El aviso no lleva datos a propósito: la bandeja vuelve a preguntarle al backend, que es quien
 * deriva ese estado (RN-01), en vez de recibir un renglón ya calculado del lado del cliente.
 *
 * Es **interno** de la feature: la página no lo conoce, porque el contexto de un componente
 * cliente llega a los `children` que le pasa el servidor. Fuera de una bandeja el aviso no hace
 * nada, y el hilo funciona suelto como siempre.
 */

import { createContext } from "react";

export interface AvisoDeBandeja {
  /** El hilo actuó con éxito: la bandeja tiene que volver a pedir su listado. */
  readonly avisarCambio: () => void;
}

export const ContextoDeAvisoDeBandeja = createContext<AvisoDeBandeja>({
  avisarCambio: () => undefined,
});
