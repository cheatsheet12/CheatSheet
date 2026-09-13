/**
 * Inviting somebody into the company (HU-E1-04).
 *
 * The email is validated here before the request goes out — not to replace the
 * backend's check, which is the one that decides, but so the obvious mistake is caught
 * without a round trip and without an error message written for a developer.
 *
 * **El rol se explica mientras se elige.** Debajo del selector va lo que ese rol puede
 * hacer, y cambia al cambiarlo: quien invita está decidiendo a qué le da acceso a alguien,
 * y «Operador» a secas no dice a qué. Es el mismo texto que la leyenda del listado, así que
 * vive en `roles.ts` y no copiado acá.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, Modal, Select } from "@/shared";

import type { RolUsuario, UsuarioDeLaEmpresa } from "../api/cliente";
import { ErrorDeFormulario, invitarUsuario } from "../api/cliente";
import { QUE_PUEDE, ROLES } from "./roles";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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
      <div className="cfg-modal">
        {general !== null && <Alert tono="error">{general}</Alert>}

        {/* Lo que va a pasar cuando se apriete el botón, antes de apretarlo: la invitación
            no da acceso por sí sola, y quien la manda tiene que saber que falta un paso del
            otro lado. */}
        <p className="cfg-modal__texto">
          Le mandamos un correo con un enlace para que elija su contraseña. Hasta que lo haga,
          figura en el listado como invitación pendiente.
        </p>

        <form onSubmit={(evento) => void enviar(evento)} noValidate>
          <div className="cfg-modal__campos">
            <Campo
              id="email-invitado"
              etiqueta="Email"
              type="email"
              required
              error={error}
              placeholder="nombre@empresa.com"
              value={email}
              onChange={(evento) => setEmail(evento.target.value)}
            />
            <Select
              id="rol-invitado"
              etiqueta="Rol"
              opciones={ROLES}
              value={rol}
              ayuda={QUE_PUEDE[rol]}
              onChange={(evento) => setRol(evento.target.value as RolUsuario)}
            />
          </div>

          {/* Cancelar es texto y Enviar es el botón: dos botones sólidos lado a lado obligan
              a leer los dos para saber cuál es la salida. */}
          <div className="cfg-modal__acciones">
            <button type="button" className="cfg-accion" onClick={onCerrar}>
              Cancelar
            </button>
            <Button type="submit" cargando={enviando}>
              Enviar invitación
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
