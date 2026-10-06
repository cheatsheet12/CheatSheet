/**
 * The client form of PAN-DM-01, for both creating and editing.
 *
 * **The «Validar contra ARCA» button is the whole point of the screen's fiscal half.** It
 * is the same shape the onboarding uses (PAN-ONB-02): press it, and one of three things
 * happens — the registry fills in the name and the VAT condition, it says the tax id does
 * not exist, or it says it could not be asked. The third is not an error and is not
 * presented as one: ARCA is optional, and a company that never connected it still has to
 * be able to load its customers.
 *
 * **`origen` is not on this form.** HU-E4-01 RN-01 says the system assigns it and nobody
 * edits it, so there is no field, no hidden input and no default to argue about.
 *
 * Nothing here decides whether a CUIT is valid. The check digit is verified by the
 * backend, and this only shows what it answered — `CLAUDE.md` §5: the panel consumes the
 * API, it does not compute.
 */

"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { Alert, Button, Campo, Select } from "@/shared";

import { consultarPadron } from "../api/cliente";
import type { Cliente, CondicionIVA, DatosDeCliente, ResultadoDePadron } from "../api/cliente";

import { IconoDeCliente } from "./iconos";

const CONDICIONES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Sin especificar" },
  { valor: "RESPONSABLE_INSCRIPTO", etiqueta: "Responsable Inscripto" },
  { valor: "MONOTRIBUTO", etiqueta: "Monotributo" },
  { valor: "EXENTO", etiqueta: "Exento" },
  { valor: "CONSUMIDOR_FINAL", etiqueta: "Consumidor Final" },
];

export interface PropsDeFormulario {
  /** Absent when creating. */
  readonly cliente?: Cliente;
  readonly onGuardar: (datos: DatosDeCliente) => Promise<void>;
  readonly onCancelar: () => void;
  /** Set when the save failed, so the message sits next to the fields that caused it. */
  readonly error?: string | null;
  /** The duplicate's id, when the save failed for that reason (RN-03). */
  readonly duplicadoId?: string | null;
  readonly onVerDuplicado?: (id: string) => void;
  /**
   * El selector de categorías, que sólo existe al editar (una asignación necesita un cliente
   * con id). Entra como ranura y no como hijo del `Modal` para que quede **dentro** del
   * formulario, encima del pie de acciones: si no, «Guardar» quedaba en medio de la hoja y las
   * categorías debajo, como si fueran de otro formulario.
   */
  readonly categorias?: ReactNode | undefined;
}

interface Campos {
  nombre: string;
  cuit: string;
  condicion_iva: string;
  contacto_whatsapp: string;
  contacto_email: string;
}

function inicial(cliente: Cliente | undefined): Campos {
  return {
    nombre: cliente?.nombre ?? "",
    cuit: cliente?.cuit ?? "",
    condicion_iva: cliente?.condicion_iva ?? "",
    contacto_whatsapp: cliente?.contacto_whatsapp ?? "",
    contacto_email: cliente?.contacto_email ?? "",
  };
}

/** What the padrón answer means on screen, in one place so the three cases stay apart. */
function avisoDePadron(resultado: ResultadoDePadron): {
  tono: "exito" | "advertencia" | "error";
  texto: string;
} {
  if (resultado.estado === "ENCONTRADO") {
    return {
      tono: "exito",
      texto: `ARCA reconoce el CUIT: ${resultado.datos?.razon_social ?? ""}`,
    };
  }
  if (resultado.estado === "NO_ENCONTRADO") {
    return { tono: "error", texto: "ARCA no reconoce ese CUIT. Revisalo antes de guardar." };
  }
  return {
    tono: "advertencia",
    texto: `No se pudo validar contra ARCA: ${resultado.motivo ?? "el servicio no respondió"}. El cliente se guarda igual.`,
  };
}

export function FormularioDeCliente({
  cliente,
  onGuardar,
  onCancelar,
  error = null,
  duplicadoId = null,
  onVerDuplicado,
  categorias,
}: PropsDeFormulario): JSX.Element {
  const [campos, setCampos] = useState<Campos>(() => inicial(cliente));
  const [padron, setPadron] = useState<ResultadoDePadron | null>(null);
  const [errorDePadron, setErrorDePadron] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);
  const [guardando, setGuardando] = useState(false);

  function cambiar(clave: keyof Campos, valor: string): void {
    setCampos((previos) => ({ ...previos, [clave]: valor }));
  }

  async function validar(): Promise<void> {
    setValidando(true);
    setErrorDePadron(null);
    try {
      const resultado = await consultarPadron(campos.cuit);
      setPadron(resultado);
      // Only fills what is empty. Overwriting a name somebody typed is not a correction.
      if (resultado.estado === "ENCONTRADO" && resultado.datos !== null) {
        setCampos((previos) => ({
          ...previos,
          nombre: previos.nombre === "" ? (resultado.datos?.razon_social ?? "") : previos.nombre,
          condicion_iva:
            previos.condicion_iva === ""
              ? (resultado.datos?.condicion_iva ?? "")
              : previos.condicion_iva,
        }));
      }
    } catch (fallo) {
      setErrorDePadron(fallo instanceof Error ? fallo.message : "No se pudo consultar ARCA");
    } finally {
      setValidando(false);
    }
  }

  async function guardar(): Promise<void> {
    setGuardando(true);
    try {
      await onGuardar({
        nombre: campos.nombre,
        cuit: campos.cuit,
        condicion_iva: campos.condicion_iva === "" ? null : (campos.condicion_iva as CondicionIVA),
        contacto_whatsapp: campos.contacto_whatsapp,
        contacto_email: campos.contacto_email,
      });
    } finally {
      setGuardando(false);
    }
  }

  const aviso = padron === null ? null : avisoDePadron(padron);
  const editando = cliente !== undefined;

  return (
    <form
      className="dm-formulario mae-form"
      onSubmit={(evento) => {
        evento.preventDefault();
        void guardar();
      }}
    >
      {/* Qué decide este formulario, antes de los campos: quien lo abre no tendría que
          deducirlo de los nombres de las etiquetas. */}
      <div className="mae-form__intro">
        <span className="mae-form__tile" aria-hidden="true">
          <IconoDeCliente />
        </span>
        <p className="mae-form__nota">
          Sólo el nombre es obligatorio. El CUIT y la condición frente al IVA son lo que después
          necesita la facturación; el WhatsApp, el agente.
        </p>
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
          {duplicadoId !== null && onVerDuplicado !== undefined && (
            <>
              {" "}
              <Button variante="secundario" onClick={() => onVerDuplicado(duplicadoId)}>
                Ver el cliente existente
              </Button>
            </>
          )}
        </Alert>
      )}

      <section className="mae-seccion" aria-labelledby="cliente-sec-fiscal">
        <h3 className="mae-seccion__titulo" id="cliente-sec-fiscal">
          Datos fiscales
        </h3>
        <Campo
          id="cliente-nombre"
          etiqueta="Nombre o razón social"
          value={campos.nombre}
          onChange={(evento) => cambiar("nombre", evento.target.value)}
          ayuda="Si validás un CUIT contra ARCA y dejás esto vacío, se completa solo."
        />

        <div className="dm-formulario__cuit">
          <Campo
            id="cliente-cuit"
            etiqueta="CUIT"
            mono
            value={campos.cuit}
            onChange={(evento) => cambiar("cuit", evento.target.value)}
            ayuda="Opcional. Un cliente sin CUIT no puede recibir Factura A."
          />
          <Button
            variante="secundario"
            onClick={() => void validar()}
            cargando={validando}
            disabled={campos.cuit.trim() === ""}
          >
            Validar contra ARCA
          </Button>
        </div>

        {aviso !== null && <Alert tono={aviso.tono}>{aviso.texto}</Alert>}
        {errorDePadron !== null && <Alert tono="error">{errorDePadron}</Alert>}

        <Select
          id="cliente-condicion-iva"
          etiqueta="Condición frente al IVA"
          opciones={CONDICIONES}
          value={campos.condicion_iva}
          onChange={(evento) => cambiar("condicion_iva", evento.target.value)}
          ayuda="Define qué tipo de factura se le puede emitir."
        />
      </section>

      <section className="mae-seccion" aria-labelledby="cliente-sec-contacto">
        <h3 className="mae-seccion__titulo" id="cliente-sec-contacto">
          Contacto
        </h3>
        <div className="mae-form__columnas">
          <Campo
            id="cliente-whatsapp"
            etiqueta="WhatsApp"
            mono
            value={campos.contacto_whatsapp}
            onChange={(evento) => cambiar("contacto_whatsapp", evento.target.value)}
            ayuda="Con código de país, sin espacios."
          />
          <Campo
            id="cliente-email"
            etiqueta="Email"
            type="email"
            value={campos.contacto_email}
            onChange={(evento) => cambiar("contacto_email", evento.target.value)}
            ayuda="Donde se envían los comprobantes."
          />
        </div>
      </section>

      <section className="mae-seccion mae-seccion--categorias" aria-labelledby="cliente-sec-cat">
        <h3 className="mae-seccion__titulo" id="cliente-sec-cat">
          Categorías
        </h3>
        {editando ? (
          categorias
        ) : (
          <p className="mae-seccion__ayuda">
            Podés asignarle categorías una vez creado el cliente.
          </p>
        )}
      </section>

      <div className="dm-formulario__acciones mae-form__pie">
        <Button variante="secundario" onClick={onCancelar}>
          Cancelar
        </Button>
        <Button type="submit" cargando={guardando}>
          {guardando ? "Guardando…" : editando ? "Guardar cambios" : "Crear cliente"}
        </Button>
      </div>
    </form>
  );
}
