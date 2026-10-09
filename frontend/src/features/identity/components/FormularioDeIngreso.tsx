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
 *
 * **El stepper aparece sólo al registrarse, y esa es una decisión, no un olvido.** El
 * prototipo dibuja los tres pasos sobre las tres pantallas del flujo, pero quien vuelve a
 * entrar todos los días no está haciendo un onboarding: mostrarle «paso 1 de 3» le diría
 * que le faltan dos cosas que ya hizo. Al crear la cuenta sí es el paso 1, y ahí está.
 */

"use client";

import { useState } from "react";

import {
  Alert,
  Button,
  Campo,
  CampoDeContrasena,
  Casilla,
  Stepper,
  useAccionConNavegacion,
} from "@/shared";

import { ErrorDeFormulario, ingresar, registrar } from "../api/cliente";
import { PASOS_DEL_ONBOARDING } from "./pasos";

const LARGO_MINIMO_CONTRASENA = 8;

type Modo = "ingresar" | "registrarse";

interface Errores {
  readonly contrasena?: string;
  readonly terminos?: string;
  readonly general?: string;
}

export function FormularioDeIngreso(): JSX.Element {
  const [modo, setModo] = useState<Modo>("ingresar");
  const [email, setEmail] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [nombre, setNombre] = useState("");
  const [acepta, setAcepta] = useState(false);
  const [errores, setErrores] = useState<Errores>({});
  const { pendiente: enviando, ejecutar } = useAccionConNavegacion();

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

    try {
      await ejecutar(
        () =>
          registrando ? registrar({ email, contrasena, nombre }) : ingresar({ email, contrasena }),
        // RN-04: the dashboard stays closed until the onboarding is complete.
        (resultado, router) =>
          router.push(resultado.onboarding_completo ? "/panel" : "/onboarding/empresa"),
      );
    } catch (error) {
      setErrores({
        general:
          error instanceof ErrorDeFormulario
            ? error.detalle
            : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      });
    }
  };

  return (
    <>
      {registrando && (
        <div className="onb-stepper">
          <div className="onb-stepper__caja">
            <Stepper pasos={PASOS_DEL_ONBOARDING} actual={1} />
          </div>
        </div>
      )}

      <section className="acc-tarjeta acc-tarjeta--angosta">
        <header className="acc-encabezado">
          <h1 className="acc-titulo">
            {registrando ? "Creá tu cuenta" : "Bienvenido a CheatSheet"}
          </h1>
          <p className="acc-sub">
            {registrando
              ? "Tres pasos y tu empresa queda conectada."
              : "Automatizá tu negocio sin cambiar tus herramientas."}
          </p>
        </header>

        {errores.general !== undefined && (
          <div className="acc-aviso">
            <Alert tono="error">{errores.general}</Alert>
          </div>
        )}

        <form onSubmit={(evento) => void enviar(evento)} noValidate>
          <div className="acc-campos">
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

            <CampoDeContrasena
              id="contrasena"
              etiqueta="Contraseña"
              autoComplete={registrando ? "new-password" : "current-password"}
              required
              error={errores.contrasena}
              ayuda={registrando ? "Mínimo 8 caracteres." : undefined}
              value={contrasena}
              onChange={(evento) => setContrasena(evento.target.value)}
            />
          </div>

          {!registrando && (
            <p className="acc-secundario">
              <a className="acc-enlace" href="/recuperar">
                ¿Olvidaste tu contraseña?
              </a>
            </p>
          )}

          {registrando && (
            <div className="acc-terminos">
              <Casilla
                id="terminos"
                checked={acepta}
                error={errores.terminos}
                onChange={(evento) => setAcepta(evento.target.checked)}
              >
                Acepto los{" "}
                <a className="acc-enlace" href="/terminos" target="_blank" rel="noreferrer">
                  Términos y Condiciones
                </a>{" "}
                y la Política de Privacidad del servicio.
              </Casilla>
            </div>
          )}

          <div className="acc-accion">
            <Button type="submit" cargando={enviando}>
              {registrando ? "Crear cuenta" : "Ingresar"}
            </Button>
          </div>
        </form>

        <p className="acc-o">o</p>

        {/* El único proveedor externo de identidad que la plataforma acepta hoy. El enlace
            va a nuestra propia ruta: el `client_id` y el `state` los arma el servidor, así
            que acá no viaja ningún secreto. */}
        <a className="acc-google" href="/api/auth/google">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="#4285F4"
              d="M22.5 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.9a5 5 0 0 1-2.2 3.3v2.7h3.6c2.1-2 3.2-4.8 3.2-7.8Z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.9 0 5.4-1 7.2-2.6l-3.6-2.7c-1 .7-2.3 1.1-3.6 1.1-2.8 0-5.1-1.9-6-4.4H2.3v2.8A11 11 0 0 0 12 23Z"
            />
            <path
              fill="#FBBC05"
              d="M6 14.4a6.6 6.6 0 0 1 0-4.2V7.4H2.3a11 11 0 0 0 0 9.8L6 14.4Z"
            />
            <path
              fill="#EA4335"
              d="M12 5.4c1.6 0 3 .5 4.1 1.6l3.1-3.1A11 11 0 0 0 2.3 7.4L6 10.2c.9-2.5 3.2-4.4 6-4.4Z"
            />
          </svg>
          <span>Continuar con Google</span>
        </a>

        <p className="acc-pie">
          {registrando ? "¿Ya tenés una cuenta? " : "¿No tenés cuenta? "}
          <button
            type="button"
            className="acc-enlace"
            onClick={() => {
              setModo(registrando ? "ingresar" : "registrarse");
              setErrores({});
            }}
          >
            {registrando ? "Ya tengo cuenta" : "Registrate"}
          </button>
        </p>
      </section>
    </>
  );
}
