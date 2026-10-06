/**
 * Botón de icono que copia un dato técnico (CAE, CUIT) al portapapeles.
 *
 * La confirmación es visual —el icono pasa a una tilde— y también anunciada: un texto sólo para
 * lectores de pantalla dice «Copiado» en una región `status`. Si el navegador no deja escribir
 * en el portapapeles (contexto no seguro, permiso denegado) no pasa nada visible: el dato sigue
 * a la vista para seleccionarlo a mano.
 */

"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface PropsDeBotonDeCopiar {
  readonly valor: string;
  /** Nombre accesible: «Copiar CAE». */
  readonly etiqueta: string;
}

export function BotonDeCopiar({ valor, etiqueta }: PropsDeBotonDeCopiar): JSX.Element {
  const [copiado, setCopiado] = useState(false);
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (temporizador.current !== null) {
        clearTimeout(temporizador.current);
      }
    },
    [],
  );

  async function copiar(): Promise<void> {
    try {
      await navigator.clipboard.writeText(valor);
    } catch {
      // Sin portapapeles: el dato queda a la vista y se puede copiar a mano.
      return;
    }
    setCopiado(true);
    if (temporizador.current !== null) {
      clearTimeout(temporizador.current);
    }
    temporizador.current = setTimeout(() => setCopiado(false), 1800);
  }

  return (
    <>
      <button
        type="button"
        className={`fac-copiar${copiado ? " fac-copiar--listo" : ""}`}
        aria-label={etiqueta}
        title={copiado ? "Copiado" : etiqueta}
        onClick={() => void copiar()}
      >
        {copiado ? <Check aria-hidden="true" size={15} /> : <Copy aria-hidden="true" size={15} />}
      </button>
      <span className="solo-lectores" role="status">
        {copiado ? "Copiado" : ""}
      </span>
    </>
  );
}
