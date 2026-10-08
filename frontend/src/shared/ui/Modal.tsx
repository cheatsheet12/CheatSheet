/**
 * Modal dialog — gap P9: no prototype defines one, so it is built from §1.3 and §1.4.
 *
 * Rendered as a native `<dialog>` rather than a floating `<div>`. The browser then owns
 * the focus trap, the backdrop, `Escape`, and the accessibility role — four things a
 * hand-rolled overlay gets wrong in exactly the way that leaves a keyboard user stuck
 * behind an invisible layer.
 *
 * It renders nothing at all when closed, so the form inside starts empty every time it
 * is opened instead of showing what the previous attempt left behind.
 */

"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export interface PropsDeModal {
  readonly abierto: boolean;
  readonly titulo: string;
  readonly onCerrar: () => void;
  readonly children: ReactNode;
}

export function Modal({ abierto, titulo, onCerrar, children }: PropsDeModal): JSX.Element | null {
  const referencia = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialogo = referencia.current;
    if (dialogo === null) {
      return;
    }
    // `showModal` is what installs the focus trap; `open` as an attribute does not.
    if (abierto && !dialogo.open) {
      dialogo.showModal();
    }
    if (!abierto && dialogo.open) {
      dialogo.close();
    }
  }, [abierto]);

  if (!abierto) {
    return null;
  }

  return (
    <dialog
      ref={referencia}
      className="modal"
      aria-label={titulo}
      // Escape closes it at the browser level; this keeps React's state in step.
      onCancel={(evento) => {
        evento.preventDefault();
        onCerrar();
      }}
    >
      <div className="modal__encabezado">
        <h2 className="modal__titulo">{titulo}</h2>
        <button type="button" className="modal__cerrar" aria-label="Cerrar" onClick={onCerrar}>
          <X size={16} strokeWidth={2.2} aria-hidden="true" />
        </button>
      </div>
      <div className="modal__cuerpo">{children}</div>
    </dialog>
  );
}
