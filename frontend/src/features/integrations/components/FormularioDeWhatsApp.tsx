/**
 * Connecting a WhatsApp Business number (HU-E2-03) — the three fields Meta needs.
 *
 * **Manual entry, and the reason is worth knowing — decision D-f of the unit plan.** Meta
 * recommends Embedded Signup: a popup from the Facebook JS SDK where the Administrator
 * picks their account and number, and a code comes back. It is a far better experience.
 * It also requires an approved Meta app, which does not exist, so it can be neither built
 * nor demonstrated today. This form is what works now; when the app is approved it is
 * this component and one backend adapter that get replaced, and nothing else.
 *
 * The token is a credential: it is held in component state, sent once, and the component
 * unmounts with the modal — `Modal` renders nothing when closed, so nothing survives to
 * be shown to whoever opens the dialog next.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo } from "@/shared";

import type { ParametrosDeConexion } from "../api/cliente";

export interface PropsDeFormularioDeWhatsApp {
  readonly enviando: boolean;
  readonly onEnviar: (token: string, parametros: ParametrosDeConexion) => void;
  readonly onCancelar: () => void;
}

interface Campos {
  readonly token: string;
  readonly phoneNumberId: string;
  readonly wabaId: string;
}

const VACIO: Campos = { token: "", phoneNumberId: "", wabaId: "" };

export function FormularioDeWhatsApp({
  enviando,
  onEnviar,
  onCancelar,
}: PropsDeFormularioDeWhatsApp): JSX.Element {
  const [campos, setCampos] = useState<Campos>(VACIO);
  const [error, setError] = useState<string | null>(null);

  const completo =
    campos.token.trim() !== "" && campos.phoneNumberId.trim() !== "" && campos.wabaId.trim() !== "";

  function actualizar(clave: keyof Campos, valor: string): void {
    setCampos((previos) => ({ ...previos, [clave]: valor }));
  }

  function enviar(evento: React.FormEvent<HTMLFormElement>): void {
    evento.preventDefault();
    if (!completo) {
      setError("Completá los tres datos para conectar el número.");
      return;
    }
    setError(null);
    onEnviar(campos.token.trim(), {
      phone_number_id: campos.phoneNumberId.trim(),
      waba_id: campos.wabaId.trim(),
    });
  }

  return (
    <form onSubmit={enviar} noValidate>
      <p className="int-form__ayuda">
        Estos tres datos salen de <strong>Meta Business Manager</strong>, en la configuración de tu
        cuenta de WhatsApp Business. Meta puede tardar entre 24 y 72 horas en verificar el número:
        mientras tanto la integración queda en estado Pendiente y te avisamos por mail cuando
        responda.
      </p>

      <Campo
        id="whatsapp-token"
        etiqueta="Token de acceso"
        // `password` so it does not sit legible on a shared screen, and no autocomplete:
        // a browser storing this alongside passwords is a credential in a place nobody
        // is auditing.
        type="password"
        autoComplete="off"
        value={campos.token}
        onChange={(evento) => {
          actualizar("token", evento.target.value);
        }}
        ayuda="El token del usuario de sistema con permisos sobre la cuenta."
        required
      />
      <Campo
        id="whatsapp-phone-number-id"
        etiqueta="ID del número (Phone Number ID)"
        mono
        autoComplete="off"
        value={campos.phoneNumberId}
        onChange={(evento) => {
          actualizar("phoneNumberId", evento.target.value);
        }}
        required
      />
      <Campo
        id="whatsapp-waba-id"
        etiqueta="ID de la cuenta (WABA ID)"
        mono
        autoComplete="off"
        value={campos.wabaId}
        onChange={(evento) => {
          actualizar("wabaId", evento.target.value);
        }}
        ayuda="Verificamos que el número pertenezca a esta cuenta antes de guardarlo."
        required
      />

      {error !== null ? <Alert tono="error">{error}</Alert> : null}

      <div className="int-form__acciones">
        <Button variante="secundario" type="button" onClick={onCancelar} disabled={enviando}>
          Cancelar
        </Button>
        <Button type="submit" disabled={enviando || !completo}>
          {enviando ? "Conectando…" : "Conectar número"}
        </Button>
      </div>
    </form>
  );
}
