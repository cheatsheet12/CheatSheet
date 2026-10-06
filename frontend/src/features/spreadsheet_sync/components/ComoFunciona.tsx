/**
 * «Cómo funciona»: los cuatro pasos de una ingesta, de arriba abajo y unidos por una línea.
 *
 * Reemplaza a la banda «La IA va a detectar»: las etiquetas de los campos que reconoce el modelo
 * ahora viven en el segundo paso, que es donde importa saberlas (HU-E3-01 RN-01). Decir antes de
 * subir que el orden y el nombre de las columnas no importan evita que alguien reordene su
 * planilla a mano.
 */

import { ATRIBUTOS_DE_CLIENTE, ETIQUETAS_DE_ATRIBUTO } from "../api/planilla";
import { Icono } from "./iconos";

export function ComoFunciona(): JSX.Element {
  return (
    <section className="ing-como" aria-labelledby="ing-como-titulo">
      <h2 id="ing-como-titulo" className="ing-seccion__titulo">
        Cómo funciona
      </h2>
      <p className="ing-seccion__sub">Cuatro pasos, y casi todos los hace la IA</p>

      <ol className="ing-pasos">
        <li className="ing-paso">
          <span className="ing-paso__n">1</span>
          <div className="ing-paso__cuerpo">
            <b className="ing-paso__titulo">Subí o vinculá tu planilla</b>
            <p className="ing-paso__texto">Un archivo de tu computadora o una hoja de Google.</p>
          </div>
        </li>
        <li className="ing-paso">
          <span className="ing-paso__n ing-paso__n--ia">
            <Icono nombre="chispa" />
          </span>
          <div className="ing-paso__cuerpo">
            <b className="ing-paso__titulo">La IA propone el mapeo</b>
            <p className="ing-paso__texto">
              Reconoce estos campos sin importar el orden ni el nombre exacto de tus columnas.
            </p>
            <ul className="ing-chips">
              {ATRIBUTOS_DE_CLIENTE.map((atributo) => (
                <li key={atributo} className="ing-chip">
                  <Icono nombre="tilde" />
                  {ETIQUETAS_DE_ATRIBUTO[atributo] ?? atributo}
                </li>
              ))}
            </ul>
          </div>
        </li>
        <li className="ing-paso">
          <span className="ing-paso__n">3</span>
          <div className="ing-paso__cuerpo">
            <b className="ing-paso__titulo">Revisás y confirmás</b>
            <p className="ing-paso__texto">Corregís lo que haga falta antes de que se importe.</p>
          </div>
        </li>
        <li className="ing-paso">
          <span className="ing-paso__n">4</span>
          <div className="ing-paso__cuerpo">
            <b className="ing-paso__titulo">Se importan tus clientes y servicios</b>
            <p className="ing-paso__texto">
              Las filas con error quedan listadas para que las corrijas.
            </p>
          </div>
        </li>
      </ol>
    </section>
  );
}
