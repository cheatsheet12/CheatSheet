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
 *
 * **It asks for the privacy policy and nothing else** (HU-E1-08 RN-04): the terms were
 * accepted by the company's Administrator, and the invited person is not a party to them.
 * The box starts unticked and the API refuses to activate the account without it.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, useAccionConNavegacion } from "@/shared";

import { ErrorDeFormulario, aceptarInvitacion } from "../api/cliente";
import { hayErrores, validarConsentimiento } from "../validacion/consentimiento";
import type { ErroresDeConsentimiento } from "../validacion/consentimiento";
import { CasillasLegales } from "./CasillasLegales";

const LARGO_MINIMO_CONTRASENA = 8;

interface Errores extends ErroresDeConsentimiento {
  readonly nombre?: string;
  readonly contrasena?: string;
  readonly confirmacion?: string;
  readonly general?: string;
}

const SIN_TEXTOS =
  "No pudimos cargar los textos legales vigentes. Recargá la página para activar tu cuenta.";

export interface PropsDeFormularioDeAceptacion {
  readonly token: string;
  /** The privacy policy version in force, or `null` when the page could not read it. */
  readonly versionDePrivacidad: string | null;
}

export function FormularioDeAceptacion({
  token,
  versionDePrivacidad,
}: PropsDeFormularioDeAceptacion): JSX.Element {
  const [nombre, setNombre] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [aceptaciones, setAceptaciones] = useState({ terminos: false, privacidad: false });
  const [errores, setErrores] = useState<Errores>({});
  const { pendiente: enviando, ejecutar } = useAccionConNavegacion();

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
    const faltantes = validarConsentimiento(aceptaciones, false);
    if (hayErrores(faltantes)) {
      return faltantes;
    }
    return versionDePrivacidad === null ? { general: SIN_TEXTOS } : {};
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
          aceptarInvitacion({
            token,
            nombre: nombre.trim(),
            contrasena,
            version_privacidad: versionDePrivacidad ?? "",
          }),
        // Whoever accepts is already signed in. Where they land depends on whether the
        // company finished its onboarding, exactly as it does after signing in.
        (resultado, router) =>
          router.push(resultado.onboarding_completo ? "/panel" : "/onboarding/empresa"),
      );
    } catch (fallo) {
      setErrores({
        general:
          fallo instanceof ErrorDeFormulario
            ? fallo.detalle
            : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      });
    }
  };

  return (
    <section className="acc-tarjeta acc-tarjeta--angosta">
      <header className="acc-encabezado">
        <h1 className="acc-titulo">Activá tu cuenta</h1>
        <p className="acc-sub">Te invitaron a CheatSheet. Elegí una contraseña y entrás.</p>
      </header>

      {errores.general !== undefined && (
        <div className="acc-aviso">
          <Alert tono="error">{errores.general}</Alert>
        </div>
      )}

      <form onSubmit={(evento) => void enviar(evento)} noValidate>
        <div className="acc-campos">
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
        </div>
        <CasillasLegales
          aceptaciones={aceptaciones}
          onCambio={setAceptaciones}
          errores={errores}
          soloPrivacidad
        />
        <div className="acc-accion">
          <Button type="submit" cargando={enviando}>
            Activar mi cuenta
          </Button>
        </div>
      </form>
    </section>
  );
}
