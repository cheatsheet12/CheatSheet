/**
 * Accepting an invitation — HU-E1-04 RN-02.
 *
 * **The third screen of this unit, which the catalogue does not number.** RN-02 requires
 * the invited person to choose their own password, and no `PAN-…` covers that moment. It
 * follows PAN-ONB-01's layout, because it is the same act from the other side: somebody
 * who has no session getting one.
 *
 * The password is asked twice. The rule is only "at least 8 characters" (HU-E1-01 RN-01)
 * and nothing more is imposed — but a typo in a password nobody can recover means the
 * invitation has to be revoked and reissued, so the confirmation earns its place.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Card } from "@/shared";

import { ErrorDeFormulario, aceptarInvitacion } from "../api/cliente";

const LARGO_MINIMO_CONTRASENA = 8;

interface Errores {
  readonly nombre?: string;
  readonly contrasena?: string;
  readonly confirmacion?: string;
  readonly general?: string;
}

export interface PropsDeFormularioDeAceptacion {
  readonly token: string;
}

export function FormularioDeAceptacion({ token }: PropsDeFormularioDeAceptacion): JSX.Element {
  const router = useRouter();
  const [nombre, setNombre] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [errores, setErrores] = useState<Errores>({});
  const [enviando, setEnviando] = useState(false);

  const validar = (): Errores => {
    if (nombre.trim() === "") {
      return { nombre: "Decinos cómo te llamás." };
    }
    if (contrasena.length < LARGO_MINIMO_CONTRASENA) {
      return { contrasena: "La contraseña debe tener al menos 8 caracteres." };
    }
    if (contrasena !== confirmacion) {
      return { confirmacion: "Las contraseñas no coinciden." };
    }
    return {};
  };

  const enviar = async (evento: React.FormEvent): Promise<void> => {
    evento.preventDefault();
    const encontrados = validar();
    setErrores(encontrados);
    if (Object.keys(encontrados).length > 0) {
      return;
    }

    setEnviando(true);
    try {
      const resultado = await aceptarInvitacion({ token, nombre: nombre.trim(), contrasena });
      // Whoever accepts is already signed in. Where they land depends on whether the
      // company finished its onboarding, exactly as it does after signing in.
      router.push(resultado.onboarding_completo ? "/panel" : "/onboarding/empresa");
    } catch (fallo) {
      setErrores({
        general:
          fallo instanceof ErrorDeFormulario
            ? fallo.detalle
            : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Card titulo="Activá tu cuenta">
      {errores.general !== undefined && <Alert tono="error">{errores.general}</Alert>}

      <p>Te invitaron a CheatSheet. Elegí una contraseña y entrás.</p>

      <form onSubmit={(evento) => void enviar(evento)} noValidate>
        <Campo
          id="nombre"
          etiqueta="Tu nombre"
          autoComplete="name"
          required
          error={errores.nombre}
          value={nombre}
          onChange={(evento) => setNombre(evento.target.value)}
        />
        <Campo
          id="contrasena"
          etiqueta="Contraseña"
          type="password"
          autoComplete="new-password"
          required
          ayuda="Mínimo 8 caracteres."
          error={errores.contrasena}
          value={contrasena}
          onChange={(evento) => setContrasena(evento.target.value)}
        />
        <Campo
          id="confirmacion"
          etiqueta="Repetí la contraseña"
          type="password"
          autoComplete="new-password"
          required
          error={errores.confirmacion}
          value={confirmacion}
          onChange={(evento) => setConfirmacion(evento.target.value)}
        />
        <Button type="submit" cargando={enviando}>
          Activar mi cuenta
        </Button>
      </form>
    </Card>
  );
}
