/**
 * El editor de una fila que falló al importar.
 *
 * Antes la pantalla mandaba a corregir el dato en la planilla de origen y volver a procesar.
 * Acá se corrige en el lugar: se abre la fila con los valores que tiene **en el archivo**
 * —ya mapeados a campos del sistema—, se editan y se importa.
 *
 * **La validación no se repite en el navegador.** El backend ingiere la fila por las mismas
 * reglas del alta de un cliente y, si la rechaza, devuelve su motivo: ése es el mensaje que se
 * muestra, en el mismo editor y sin cerrarlo, para corregir otra vez. Un CUIT «válido» según
 * el navegador y rechazado por el servidor sería un editor que miente.
 *
 * `Modal` no dibuja nada cerrado, así que cada apertura arranca limpia: sin los valores ni el
 * rechazo del intento anterior.
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Campo, Modal } from "@/shared";

import {
  ETIQUETAS_DE_ATRIBUTO,
  ErrorDePlanilla,
  corregirFila,
  verFilaConError,
} from "../api/planilla";
import type { DetalleDeCarga, FilaConError } from "../api/planilla";

export interface PropsDeCorreccion {
  readonly cargaId: string;
  /** La fila que se está corrigiendo, o `null` con el editor cerrado. */
  readonly numeroFila: number | null;
  readonly alCerrar: () => void;
  /** Se llama con el detalle actualizado de la carga cuando la fila se importó. */
  readonly alCorregir: (detalle: DetalleDeCarga, numeroFila: number) => void;
}

const MENSAJE_GENERICO = "No se pudo completar la operación";

function mensajeDe(problema: unknown): string {
  return problema instanceof ErrorDePlanilla ? problema.message : MENSAJE_GENERICO;
}

export function CorreccionDeFila({
  cargaId,
  numeroFila,
  alCerrar,
  alCorregir,
}: PropsDeCorreccion): JSX.Element {
  const [fila, setFila] = useState<FilaConError | null>(null);
  const [valores, setValores] = useState<Readonly<Record<string, string>>>({});
  const [errorDeLectura, setErrorDeLectura] = useState<string | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    setFila(null);
    setRechazo(null);
    setErrorDeLectura(null);
    if (numeroFila === null) {
      return undefined;
    }
    let vigente = true;
    verFilaConError(cargaId, numeroFila)
      .then((leida) => {
        if (!vigente) return;
        setFila(leida);
        setValores(Object.fromEntries(leida.campos.map((c) => [c.atributo, c.valor])));
      })
      .catch((problema: unknown) => {
        if (vigente) setErrorDeLectura(mensajeDe(problema));
      });
    return () => {
      vigente = false;
    };
  }, [cargaId, numeroFila]);

  async function guardar(): Promise<void> {
    if (numeroFila === null) return;
    setRechazo(null);
    setEnviando(true);
    try {
      const detalle = await corregirFila(cargaId, numeroFila, valores);
      alCorregir(detalle, numeroFila);
    } catch (problema) {
      // El editor sigue abierto: el motivo es lo que hay que leer para corregir de nuevo.
      setRechazo(mensajeDe(problema));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal
      abierto={numeroFila !== null}
      titulo={`Corregir la fila ${numeroFila ?? ""}`}
      onCerrar={alCerrar}
    >
      {errorDeLectura !== null && <Alert tono="error">{errorDeLectura}</Alert>}
      {errorDeLectura === null && fila === null && <p role="status">Leyendo la fila…</p>}

      {fila !== null && (
        <form
          className="ing-correccion"
          onSubmit={(evento) => {
            evento.preventDefault();
            void guardar();
          }}
        >
          <p className="ing-correccion__motivo">
            <span>Por qué falló</span>
            {fila.motivo}
          </p>
          <p className="ing-correccion__ayuda">
            Estos son los valores de tu archivo. Corregilos y se importa esta fila: lo ya procesado
            no se toca.
          </p>

          <div className="ing-correccion__campos">
            {fila.campos.map((campo) => (
              <Campo
                key={campo.atributo}
                id={`correccion-${campo.atributo}`}
                etiqueta={ETIQUETAS_DE_ATRIBUTO[campo.atributo] ?? campo.atributo}
                mono={campo.atributo === "cuit"}
                value={valores[campo.atributo] ?? ""}
                onChange={(evento) => {
                  const nuevo = evento.target.value;
                  setValores((actuales) => ({ ...actuales, [campo.atributo]: nuevo }));
                  setRechazo(null);
                }}
              />
            ))}
          </div>

          {rechazo !== null && <Alert tono="error">{rechazo}</Alert>}

          <div className="ing-modal__acciones">
            <Button variante="secundario" onClick={alCerrar} disabled={enviando}>
              Cancelar
            </Button>
            <Button type="submit" cargando={enviando}>
              Guardar y reimportar
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
