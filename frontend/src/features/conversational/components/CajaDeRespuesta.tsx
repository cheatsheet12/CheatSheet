/**
 * La caja de respuesta del operador. Sólo existe con el escalamiento tomado: sin eso el
 * agente sigue contestando el mismo hilo y el cliente tendría dos interlocutores (RN-02).
 * El envío lo resuelve quien la usa; esta pieza únicamente dibuja el campo y el botón.
 */

import { IconoDeEnviar } from "./iconos";

export interface PropsDeCajaDeRespuesta {
  readonly texto: string;
  readonly trabajando: boolean;
  readonly onCambio: (texto: string) => void;
  readonly onEnviar: () => void;
}

export function CajaDeRespuesta({
  texto,
  trabajando,
  onCambio,
  onEnviar,
}: PropsDeCajaDeRespuesta): JSX.Element {
  return (
    <div className="cv-respuesta">
      <p className="cv-respuesta__nota">
        El agente <strong>no está contestando</strong> este hilo mientras vos lo tengas tomado. Tu
        mensaje sale por WhatsApp y se distingue del agente en el historial.
      </p>
      <form
        className="cv-respuesta__form"
        onSubmit={(evento) => {
          evento.preventDefault();
          onEnviar();
        }}
      >
        <label className="solo-lectores" htmlFor="hilo-respuesta">
          Mensaje
        </label>
        <textarea
          id="hilo-respuesta"
          className="cv-respuesta__campo"
          rows={2}
          placeholder="Escribí tu respuesta…"
          value={texto}
          onChange={(evento) => onCambio(evento.target.value)}
        />
        <button
          type="submit"
          className="cv-enviar"
          disabled={texto.trim() === "" || trabajando}
          aria-busy={trabajando}
        >
          <IconoDeEnviar />
          Enviar
        </button>
      </form>
    </div>
  );
}
