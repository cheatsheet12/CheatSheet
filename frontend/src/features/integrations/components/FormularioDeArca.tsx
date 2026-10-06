/**
 * Connecting the fiscal credential of ARCA (HU-E2-01) — two files, not two text boxes.
 *
 * ARCA hands out a `.crt` and the company generated a `.key`; nobody is going to paste the
 * contents of a private key into a form. They are read in the browser and sent together as
 * one PEM bundle, because everything secret has to travel through the field the backend
 * encrypts — the free-form parameters are stored as plain JSON.
 *
 * **The private key does pass through the browser, and there is no way around it**: the
 * server has to sign with it. What can be controlled is that it stops there — it is read
 * from the file, sent once over HTTPS, and the component unmounts with the modal, which
 * renders nothing when closed.
 */

"use client";

import { useState } from "react";

import { Alert, Button } from "@/shared";

interface Archivos {
  readonly certificado: string;
  readonly clave: string;
}

const VACIO: Archivos = { certificado: "", clave: "" };

export interface PropsDeFormularioDeArca {
  readonly enviando: boolean;
  readonly onEnviar: (bundle: string) => void;
  readonly onCancelar: () => void;
}

export function FormularioDeArca({
  enviando,
  onEnviar,
  onCancelar,
}: PropsDeFormularioDeArca): JSX.Element {
  const [archivos, setArchivos] = useState<Archivos>(VACIO);
  const [error, setError] = useState<string | null>(null);

  const completo = archivos.certificado !== "" && archivos.clave !== "";

  async function leer(clave: keyof Archivos, lista: FileList | null): Promise<void> {
    const archivo = lista?.[0];
    if (archivo === undefined) {
      return;
    }
    try {
      const texto = await archivo.text();
      setArchivos((previos) => ({ ...previos, [clave]: texto }));
      setError(null);
    } catch {
      setError("No se pudo leer el archivo. Probá seleccionarlo de nuevo.");
    }
  }

  function enviar(evento: React.FormEvent<HTMLFormElement>): void {
    evento.preventDefault();
    if (!completo) {
      setError("Cargá el certificado y la clave privada para conectar ARCA.");
      return;
    }
    setError(null);
    // Concatenated, and the order does not matter: both are PEM blocks and the backend
    // reads each one by its own header.
    onEnviar(`${archivos.certificado.trim()}\n${archivos.clave.trim()}\n`);
  }

  return (
    <form onSubmit={enviar} noValidate>
      <p className="int-form__ayuda">
        Son los dos archivos del <strong>certificado fiscal</strong> de tu empresa: el que te
        entregó ARCA y la clave privada con la que lo generaste. Validamos las credenciales contra
        ARCA antes de guardarlas, y quedan cifradas.
      </p>

      <div className="campo">
        <label className="campo__etiqueta" htmlFor="arca-certificado">
          Certificado (.crt o .pem)
        </label>
        <input
          id="arca-certificado"
          className="campo__control"
          type="file"
          accept=".crt,.pem,.cer"
          onChange={(evento) => {
            void leer("certificado", evento.target.files);
          }}
        />
      </div>

      <div className="campo">
        <label className="campo__etiqueta" htmlFor="arca-clave">
          Clave privada (.key)
        </label>
        <input
          id="arca-clave"
          className="campo__control"
          type="file"
          accept=".key,.pem"
          onChange={(evento) => {
            void leer("clave", evento.target.files);
          }}
        />
        <span className="campo__ayuda" id="arca-clave-ayuda">
          Tiene que estar sin contraseña. No se guarda en tu navegador.
        </span>
      </div>

      {error !== null ? <Alert tono="error">{error}</Alert> : null}

      <div className="int-form__acciones">
        <Button variante="secundario" type="button" onClick={onCancelar} disabled={enviando}>
          Cancelar
        </Button>
        <Button type="submit" disabled={enviando || !completo}>
          {enviando ? "Validando contra ARCA…" : "Conectar ARCA"}
        </Button>
      </div>
    </form>
  );
}
