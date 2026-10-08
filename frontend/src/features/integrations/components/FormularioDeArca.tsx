/**
 * Connecting ARCA by delegation (HU-E2-01, ADR-0014) — no certificates, no files.
 *
 * The company delegates the web service «Facturación Electrónica» to CheatSheet's CUIT at
 * ARCA, once, and this screen asks ARCA whether that delegation exists. Nothing secret
 * travels from the browser any more: the request carries no credential, and the CUIT that
 * ARCA is asked about is the company's own, taken by the server from its fiscal data.
 */

"use client";

import { Button } from "@/shared";

export interface PropsDeFormularioDeArca {
  readonly enviando: boolean;
  /** The CUIT the company has to delegate to. `null` when the deployment does not set it. */
  readonly cuitDeCheatsheet: string | null;
  readonly onEnviar: () => void;
  readonly onCancelar: () => void;
}

export function FormularioDeArca({
  enviando,
  cuitDeCheatsheet,
  onEnviar,
  onCancelar,
}: PropsDeFormularioDeArca): JSX.Element {
  function enviar(evento: React.FormEvent<HTMLFormElement>): void {
    evento.preventDefault();
    onEnviar();
  }

  return (
    <form onSubmit={enviar} noValidate>
      <p className="int-form__ayuda">
        CheatSheet factura en nombre de tu empresa con su propio certificado. Para autorizarlo,
        delegá el servicio de facturación electrónica <strong>una sola vez</strong> en ARCA:
      </p>
      <ol className="int-form__pasos">
        <li>Ingresá a ARCA con tu clave fiscal nivel 3.</li>
        <li>Abrí «Administrador de Relaciones de Clave Fiscal» y elegí «Nueva relación».</li>
        <li>Buscá ARCA › WebServices › «Facturación Electrónica».</li>
        <li>
          En «Representante» ingresá la CUIT de CheatSheet
          {cuitDeCheatsheet !== null ? (
            <>
              : <strong>{cuitDeCheatsheet}</strong>
            </>
          ) : null}{" "}
          y confirmá.
        </li>
      </ol>
      <p className="int-form__ayuda">
        Cuando termines, verificamos la delegación con la CUIT cargada en «Datos de la empresa».
      </p>

      <div className="int-form__acciones">
        <Button variante="secundario" type="button" onClick={onCancelar} disabled={enviando}>
          Cancelar
        </Button>
        <Button type="submit" disabled={enviando}>
          {enviando ? "Verificando en ARCA…" : "Verificar delegación"}
        </Button>
      </div>
    </form>
  );
}
