/**
 * El historial de un hilo: burbujas agrupadas por día (HU-E9-01).
 *
 * **El historial completo es la promesa de HU-E8-05 RN-03**: el cliente no tiene que repetir
 * nada. Por eso se muestra todo el hilo y no sólo lo posterior al escalamiento.
 *
 * **El operador se distingue del agente** (RN-04) por tres cosas a la vez —color, icono y
 * palabra—, porque un color solo no le dice nada a quien no sabe cuál es cuál. La marca viene
 * del backend (`origen`): la pantalla no la deduce por el momento del escalamiento.
 * El cliente va a la izquierda, gris suave; agente y operador a la derecha, como WhatsApp.
 */

import { ETIQUETAS_DE_INTENCION, ETIQUETAS_DE_ORIGEN, horaDeMensaje } from "../api/conversacion";
import type { Mensaje } from "../api/conversacion";
import { IconoDeDestello, IconoDeOperador } from "./iconos";
import { agruparPorDia } from "./vista";

function autorDe(mensaje: Mensaje): string {
  if (mensaje.direccion === "ENTRANTE") {
    return "Cliente";
  }
  return mensaje.origen === null ? "Sistema" : ETIQUETAS_DE_ORIGEN[mensaje.origen];
}

function variante(mensaje: Mensaje): "cliente" | "agente" | "operador" | "sistema" {
  if (mensaje.direccion === "ENTRANTE") {
    return "cliente";
  }
  if (mensaje.origen === "OPERADOR") {
    return "operador";
  }
  return mensaje.origen === null || mensaje.origen === "SISTEMA" ? "sistema" : "agente";
}

function MensajeBurbuja({ mensaje }: { readonly mensaje: Mensaje }): JSX.Element {
  const tipo = variante(mensaje);
  return (
    <li className={`cv-msg cv-msg--${tipo}`}>
      <div className="cv-msg__burbuja">
        <p className="cv-msg__texto">{mensaje.contenido}</p>
      </div>
      <p className="cv-msg__meta">
        {tipo === "agente" && <IconoDeDestello />}
        {tipo === "operador" && <IconoDeOperador />}
        {autorDe(mensaje)} · {horaDeMensaje(mensaje.momento)}
        {mensaje.intencion !== null && <> · {ETIQUETAS_DE_INTENCION[mensaje.intencion]}</>}
        {mensaje.tipo_contenido === "AUDIO" && <> · nota de voz transcripta</>}
        {mensaje.estado_entrega !== null && (
          <span className="cv-msg__entrega">{mensaje.estado_entrega}</span>
        )}
      </p>
    </li>
  );
}

export function LineaDeTiempo({
  mensajes,
}: {
  readonly mensajes: readonly Mensaje[];
}): JSX.Element {
  return (
    <ol className="cv-dias">
      {agruparPorDia(mensajes).map((grupo) => (
        <li key={grupo.clave} className="cv-dia">
          <p className="cv-dia__rotulo">
            <span>{grupo.rotulo}</span>
          </p>
          <ol className="cv-dia__mensajes">
            {grupo.mensajes.map((mensaje) => (
              <MensajeBurbuja key={mensaje.id} mensaje={mensaje} />
            ))}
          </ol>
        </li>
      ))}
    </ol>
  );
}
