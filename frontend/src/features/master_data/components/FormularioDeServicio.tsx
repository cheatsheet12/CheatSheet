/**
 * The service form of PAN-DM-02, for both creating and editing.
 *
 * **The duration field only exists while the service is bookable.** That is not a
 * cosmetic choice: HU-E4-02 RN-01 pairs the two, the aggregate drops the duration when a
 * service stops being bookable, and a field that stayed on screen holding a value the
 * backend has already discarded would be lying.
 *
 * **The price is a text input.** A `<input type="number">` hands back a JavaScript
 * `number`, which is the float this system refuses to let near money — and the backend
 * would answer 422, which is correct and a terrible way to find out.
 *
 * Nothing here validates the price or the duration beyond keeping the shape sane: the
 * rules live in the backend and this shows what it answered (`CLAUDE.md` §5).
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, Select } from "@/shared";

import { ETIQUETAS_DE_ALICUOTA } from "../api/servicio";
import type { AlicuotaIVA, DatosDeServicio, Servicio } from "../api/servicio";

const ALICUOTAS: readonly { valor: string; etiqueta: string }[] = (
  Object.keys(ETIQUETAS_DE_ALICUOTA) as AlicuotaIVA[]
).map((valor) => ({ valor, etiqueta: `IVA ${ETIQUETAS_DE_ALICUOTA[valor]}` }));

export interface PropsDeFormularioDeServicio {
  /** Absent when creating. */
  readonly servicio?: Servicio;
  readonly onGuardar: (datos: DatosDeServicio) => Promise<void>;
  readonly onCancelar: () => void;
  readonly error?: string | null;
}

interface Campos {
  nombre: string;
  precio: string;
  alicuota_iva: AlicuotaIVA;
  agendable: boolean;
  duracion: string;
}

function inicial(servicio: Servicio | undefined): Campos {
  return {
    nombre: servicio?.nombre ?? "",
    precio: servicio?.precio ?? "",
    alicuota_iva: servicio?.alicuota_iva ?? "0.21",
    agendable: servicio?.agendable ?? false,
    duracion:
      servicio?.duracion_estandar_min !== null && servicio?.duracion_estandar_min !== undefined
        ? String(servicio.duracion_estandar_min)
        : "",
  };
}

/** `""` and a non-numeric string both mean "nothing usable", and the backend decides. */
function duracionDe(campos: Campos): number | null {
  if (!campos.agendable) {
    return null;
  }
  const numero = Number.parseInt(campos.duracion, 10);
  return Number.isNaN(numero) ? null : numero;
}

export function FormularioDeServicio({
  servicio,
  onGuardar,
  onCancelar,
  error = null,
}: PropsDeFormularioDeServicio): JSX.Element {
  const [campos, setCampos] = useState<Campos>(() => inicial(servicio));
  const [guardando, setGuardando] = useState(false);

  function cambiar<C extends keyof Campos>(clave: C, valor: Campos[C]): void {
    setCampos((previos) => ({ ...previos, [clave]: valor }));
  }

  async function guardar(): Promise<void> {
    setGuardando(true);
    try {
      await onGuardar({
        nombre: campos.nombre,
        precio: campos.precio,
        alicuota_iva: campos.alicuota_iva,
        agendable: campos.agendable,
        duracion_estandar_min: duracionDe(campos),
      });
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form
      className="dm-formulario"
      onSubmit={(evento) => {
        evento.preventDefault();
        void guardar();
      }}
    >
      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
        </Alert>
      )}

      <Campo
        id="servicio-nombre"
        etiqueta="Nombre"
        value={campos.nombre}
        onChange={(evento) => cambiar("nombre", evento.target.value)}
      />

      <Campo
        id="servicio-precio"
        etiqueta="Precio sin IVA"
        mono
        inputMode="decimal"
        value={campos.precio}
        onChange={(evento) => cambiar("precio", evento.target.value)}
        ayuda="En pesos, con hasta dos decimales. Ej: 5000.00"
      />

      <Select
        id="servicio-alicuota"
        etiqueta="Alicuota de IVA"
        opciones={ALICUOTAS}
        value={campos.alicuota_iva}
        onChange={(evento) => cambiar("alicuota_iva", evento.target.value as AlicuotaIVA)}
      />

      <label className="dm-filtros__casilla" htmlFor="servicio-agendable">
        <input
          id="servicio-agendable"
          type="checkbox"
          checked={campos.agendable}
          onChange={(evento) => cambiar("agendable", evento.target.checked)}
        />
        Se puede reservar por agenda
      </label>

      {campos.agendable && (
        <Campo
          id="servicio-duracion"
          etiqueta="Duracion estandar (minutos)"
          inputMode="numeric"
          value={campos.duracion}
          onChange={(evento) => cambiar("duracion", evento.target.value)}
          ayuda="Obligatoria para los servicios agendables."
        />
      )}

      <div className="dm-formulario__acciones">
        <Button variante="secundario" onClick={onCancelar}>
          Cancelar
        </Button>
        <Button type="submit" cargando={guardando}>
          {servicio === undefined ? "Crear servicio" : "Guardar cambios"}
        </Button>
      </div>
    </form>
  );
}
