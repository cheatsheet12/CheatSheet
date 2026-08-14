/**
 * PAN-ONB-01 — sign in and sign up (HU-E1-01, HU-E1-03).
 *
 * The messages are the ones the behaviour annotations prescribe, word for word
 * (`docs/aidlc/inputs/prototipos/anotaciones-comportamiento.html`).
 *
 * **The terms checkbox appears only when registering.** The annotations list it among
 * the screen's mandatory fields, but HU-E1-03 RN-02 ties the acceptance to *completing
 * the registration* — asking someone to re-accept the contract every time they sign in
 * would be noise, and the re-acceptance that RN-03 does require is a different flow,
 * triggered by a version change.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Card, Casilla } from "@/shared";

import { ErrorDeFormulario, ingresar, registrar } from "../api/cliente";

const LARGO_MINIMO_CONTRASENA = 8;

type Modo = "ingresar" | "registrarse";

interface Errores {
  readonly contrasena?: string;
  readonly terminos?: string;
  readonly general?: string;
}

export function FormularioDeIngreso(): JSX.Element {
  const router = useRouter();
  const [modo, setModo] = useState<Modo>("ingresar");
  const [email, setEmail] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [nombre, setNombre] = useState("");
  const [acepta, setAcepta] = useState(false);
  const [errores, setErrores] = useState<Errores>({});
  const [enviando, setEnviando] = useState(false);

  const registrando = modo === "registrarse";

  const validar = (): Errores => {
    const encontrados: Errores = {};
    if (contrasena.length < LARGO_MINIMO_CONTRASENA) {
      return { ...encontrados, contrasena: "La contraseña debe tener al menos 8 caracteres." };
    }
    if (registrando && !acepta) {
      return { ...encontrados, terminos: "Debés aceptar los Términos y Condiciones." };
    }
    return encontrados;
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
      const resultado = registrando
        ? await registrar({ email, contrasena, nombre })
        : await ingresar({ email, contrasena });
      // RN-04: the dashboard stays closed until the onboarding is complete.
      router.push(resultado.onboarding_completo ? "/panel" : "/onboarding/empresa");
    } catch (error) {
      setErrores({
        general:
          error instanceof ErrorDeFormulario
            ? error.detalle
            : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Card titulo={registrando ? "Creá tu cuenta" : "Ingresá a CheatSheet"}>
      {errores.general !== undefined && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <Alert tono="error">{errores.general}</Alert>
        </div>
      )}

      <form onSubmit={(evento) => void enviar(evento)} noValidate>
        <Campo
          id="email"
          etiqueta="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
        />

        {registrando && (
          <Campo
            id="nombre"
            etiqueta="Tu nombre"
            autoComplete="name"
            required
            value={nombre}
            onChange={(evento) => setNombre(evento.target.value)}
          />
        )}

        <Campo
          id="contrasena"
          etiqueta="Contraseña"
          type="password"
          autoComplete={registrando ? "new-password" : "current-password"}
          required
          error={errores.contrasena}
          ayuda={registrando ? "Mínimo 8 caracteres." : undefined}
          value={contrasena}
          onChange={(evento) => setContrasena(evento.target.value)}
        />

        {registrando && (
          <Casilla
            id="terminos"
            checked={acepta}
            error={errores.terminos}
            onChange={(evento) => setAcepta(evento.target.checked)}
          >
            Acepto los{" "}
            <a href="/terminos" target="_blank" rel="noreferrer">
              Términos y Condiciones
            </a>
          </Casilla>
        )}

        <Button type="submit" cargando={enviando}>
          {registrando ? "Crear cuenta" : "Ingresar"}
        </Button>
      </form>

      <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-2)" }}>
        <a href="/api/auth/google">Continuar con Google</a>
        <button
          type="button"
          className="boton boton--secundario"
          onClick={() => {
            setModo(registrando ? "ingresar" : "registrarse");
            setErrores({});
          }}
        >
          {registrando ? "Ya tengo cuenta" : "Registrate"}
        </button>
        {!registrando && <a href="/recuperar">¿Olvidaste tu contraseña?</a>}
      </div>
    </Card>
  );
}
