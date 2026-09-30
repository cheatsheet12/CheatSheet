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

const MENSAJE_DURACION_NO_ENTERA = "La duracion debe ser un numero entero de minutos.";

/**
 * Only the FORMAT is checked here: a non-empty duration must be digits. `parseInt` would turn
 * "12.7" into 12 and "99999abc" into 99999 without telling anyone, and sending the text on
 * would earn Pydantic's generic 422. The 5-to-480 rule stays in one place (the domain).
 * An empty field is `null`: «obligatoria» is the backend's message to give.
 */
function formatoDeDuracionInvalido(campos: Campos): boolean {
  if (!campos.agendable) {
    return false;
  }
  const escrito = campos.duracion.trim();
  return escrito !== "" && !/^\d+$/.test(escrito);
}

function duracionDe(campos: Campos): number | null {
  const escrito = campos.duracion.trim();
  return campos.agendable && escrito !== "" ? Number.parseInt(escrito, 10) : null;
}

export function FormularioDeServicio({
  servicio,
  onGuardar,
  onCancelar,
  error = null,
}: PropsDeFormularioDeServicio): JSX.Element {
  const [campos, setCampos] = useState<Campos>(() => inicial(servicio));
  const [guardando, setGuardando] = useState(false);
  const [errorDeDuracion, setErrorDeDuracion] = useState<string | undefined>(undefined);

  function cambiar<C extends keyof Campos>(clave: C, valor: Campos[C]): void {
    setCampos((previos) => ({ ...previos, [clave]: valor }));
  }

  async function guardar(): Promise<void> {
    if (formatoDeDuracionInvalido(campos)) {
      setErrorDeDuracion(MENSAJE_DURACION_NO_ENTERA);
      return;
    }
    setErrorDeDuracion(undefined);
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
      className="dm-formulario mae-form"
      onSubmit={(evento) => {
        evento.preventDefault();
        void guardar();
      }}
    >
      {/* Qué decide este formulario, antes de los campos. La frase también dice lo que el
          panel **no** hace: el total con IVA lo arma el comprobante, no esta pantalla. */}
      <p className="mae-form__nota">
        El precio se carga sin IVA y la alícuota va aparte. Marcá «se puede reservar por agenda»
        sólo si el servicio ocupa un turno.
      </p>

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
        etiqueta="Alícuota de IVA"
        opciones={ALICUOTAS}
        value={campos.alicuota_iva}
        onChange={(evento) => cambiar("alicuota_iva", evento.target.value as AlicuotaIVA)}
      />

      <label className="mae-casilla" htmlFor="servicio-agendable">
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
          etiqueta="Duración estándar (minutos)"
          inputMode="numeric"
          value={campos.duracion}
          onChange={(evento) => {
            setErrorDeDuracion(undefined);
            cambiar("duracion", evento.target.value);
          }}
          {...(errorDeDuracion !== undefined ? { error: errorDeDuracion } : {})}
          ayuda="Entre 5 y 480 minutos."
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
