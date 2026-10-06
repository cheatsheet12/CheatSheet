/**
 * El panel derecho de la bandeja cuando todavía no se eligió ningún hilo.
 *
 * Un hueco vacío al lado de la lista se lee como una pantalla que falló al cargar: acá se
 * dibuja una escena con dos burbujas (cliente y agente) y se explica qué va a aparecer.
 */

import { IconoDeBurbuja, IconoDeDestello } from "./iconos";

export function SinHiloElegido(): JSX.Element {
  return (
    <section className="cv-panel cv-sin-hilo" aria-label="Hilo de la conversación">
      <div className="cv-sin-hilo__contenido">
        <div className="cv-escena" aria-hidden="true">
          <span className="cv-escena__burbuja cv-escena__burbuja--cliente">
            <IconoDeBurbuja />
            <i />
            <i />
          </span>
          <span className="cv-escena__burbuja cv-escena__burbuja--agente">
            <IconoDeDestello />
            <i />
          </span>
        </div>
        <b className="cv-sin-hilo__titulo">Elegí una conversación</b>
        <p className="cv-sin-hilo__texto">
          El hilo completo se abre acá: lo que dijo el cliente, lo que contestó el agente y lo que
          escribió un operador.
        </p>
      </div>
    </section>
  );
}
