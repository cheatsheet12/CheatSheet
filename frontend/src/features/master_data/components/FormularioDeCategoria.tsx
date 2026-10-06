/**
 * The category form of PAN-DM-03 (HU-E4-03).
 *
 * Two fields, and the second one is the whole story: the scope decides what the category
 * can classify, and `AMBOS` — decision D9 of the epic 3 map — is the value the DER's enum
 * did not have.
 *
 * Uniqueness is not checked here. The backend compares case-insensitively against a
 * functional unique index, and duplicating that rule in the browser would be a second
 * place for it to drift.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, Select } from "@/shared";

import { ETIQUETAS_DE_AMBITO } from "../api/categoria";
import type { AmbitoDeCategoria, Categoria } from "../api/categoria";
import { IconoDeCategoria } from "./iconos";

const AMBITOS: readonly { valor: string; etiqueta: string }[] = (
  Object.keys(ETIQUETAS_DE_AMBITO) as AmbitoDeCategoria[]
).map((valor) => ({ valor, etiqueta: ETIQUETAS_DE_AMBITO[valor] }));

export interface PropsDeFormularioDeCategoria {
  readonly categoria?: Categoria;
  readonly onGuardar: (nombre: string, aplica_a: AmbitoDeCategoria) => Promise<void>;
  readonly onCancelar: () => void;
  readonly error?: string | null;
}

export function FormularioDeCategoria({
  categoria,
  onGuardar,
  onCancelar,
  error = null,
}: PropsDeFormularioDeCategoria): JSX.Element {
  const [nombre, setNombre] = useState(categoria?.nombre ?? "");
  const [ambito, setAmbito] = useState<AmbitoDeCategoria>(categoria?.aplica_a ?? "CLIENTE");
  const [guardando, setGuardando] = useState(false);

  async function guardar(): Promise<void> {
    setGuardando(true);
    try {
      await onGuardar(nombre, ambito);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form
      className="dm-formulario mae-form"
      onSubmit={(evento) => {
        evento.preventDefault();
        void guardar();
      }}
    >
      {/* El ámbito es la mitad de la historia de esta pantalla, y no se deduce del nombre
          del campo: la nota lo dice antes de que alguien elija mal. */}
      <div className="mae-form__intro">
        <span className="mae-form__tile" aria-hidden="true">
          <IconoDeCategoria />
        </span>
        <p className="mae-form__nota">
          El ámbito decide dónde se puede usar la etiqueta. Cambiarlo más tarde no borra lo que ya
          está clasificado.
        </p>
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
        </Alert>
      )}

      <section className="mae-seccion" aria-labelledby="categoria-sec-datos">
        <h3 className="mae-seccion__titulo" id="categoria-sec-datos">
          Datos de la categoría
        </h3>
        <Campo
          id="categoria-nombre"
          etiqueta="Nombre"
          value={nombre}
          onChange={(evento) => setNombre(evento.target.value)}
          ayuda="Único dentro de cada ámbito: no puede repetirse entre clientes ni entre servicios."
        />

        <Select
          id="categoria-ambito"
          etiqueta="Se aplica a"
          opciones={AMBITOS}
          value={ambito}
          onChange={(evento) => setAmbito(evento.target.value as AmbitoDeCategoria)}
          ayuda="Decide qué se puede clasificar con esta categoría."
        />
      </section>

      <div className="dm-formulario__acciones mae-form__pie">
        <Button variante="secundario" onClick={onCancelar}>
          Cancelar
        </Button>
        <Button type="submit" cargando={guardando}>
          {guardando
            ? "Guardando…"
            : categoria === undefined
              ? "Crear categoría"
              : "Guardar cambios"}
        </Button>
      </div>
    </form>
  );
}
