/**
 * Inviting somebody into the company (HU-E1-04).
 *
 * The email is validated here before the request goes out — not to replace the
 * backend's check, which is the one that decides, but so the obvious mistake is caught
 * without a round trip and without an error message written for a developer.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, Modal, Select } from "@/shared";

import type { RolUsuario, UsuarioDeLaEmpresa } from "../api/cliente";
import { ErrorDeFormulario, invitarUsuario } from "../api/cliente";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const ROLES = [
  { valor: "OPERADOR", etiqueta: "Operador" },
  { valor: "ADMINISTRADOR", etiqueta: "Administrador" },
  { valor: "SOLO_LECTURA", etiqueta: "Solo lectura" },
];

export interface PropsDeModalDeInvitacion {
  readonly abierto: boolean;
  readonly onCerrar: () => void;
  readonly onInvitado: (usuario: UsuarioDeLaEmpresa) => void;
}

export function ModalDeInvitacion({
  abierto,
  onCerrar,
  onInvitado,
}: PropsDeModalDeInvitacion): JSX.Element {
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<RolUsuario>("OPERADOR");
  const [error, setError] = useState<string | undefined>(undefined);
  const [general, setGeneral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (evento: React.FormEvent): Promise<void> => {
    evento.preventDefault();
    if (!EMAIL.test(email.trim())) {
      setError("Ingresá un email válido.");
      return;
    }
    setError(undefined);
    setGeneral(null);
    setEnviando(true);
    try {
      const usuario = await invitarUsuario({ email: email.trim(), rol });
      setEmail("");
      setRol("OPERADOR");
      onInvitado(usuario);
    } catch (fallo) {
      setGeneral(
        fallo instanceof ErrorDeFormulario
          ? fallo.detalle
          : "No pudimos enviar la invitación. Probá de nuevo en unos minutos.",
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal abierto={abierto} titulo="Invitar usuario" onCerrar={onCerrar}>
      {general !== null && <Alert tono="error">{general}</Alert>}
      <form onSubmit={(evento) => void enviar(evento)} noValidate>
        <Campo
          id="email-invitado"
          etiqueta="Email"
          type="email"
          required
          error={error}
          ayuda="Le llega un link para elegir su contraseña."
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
        />
        <Select
          id="rol-invitado"
          etiqueta="Rol"
          opciones={ROLES}
          value={rol}
          onChange={(evento) => setRol(evento.target.value as RolUsuario)}
        />
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <Button type="submit" cargando={enviando}>
            Enviar invitación
          </Button>
          <Button variante="secundario" onClick={onCerrar}>
            Cancelar
          </Button>
        </div>
      </form>
    </Modal>
  );
}
