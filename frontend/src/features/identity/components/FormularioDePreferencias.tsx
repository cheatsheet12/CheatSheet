/**
 * PAN-USR-02 — personal preferences (HU-E1-07).
 *
 * Gap P9 again: no prototype, so this is built from the component catalogue.
 *
 * **The language selector shows one option, and that is deliberate and documented.** The
 * interface is not translated — see `shared/formato.ts`. What the preference governs is
 * how dates, times and numbers are written, which the preview below shows live so the
 * setting is not an unexplained dropdown.
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Card, Select, formatearFechaHora } from "@/shared";

import type { Preferencias, Suscripciones } from "../api/cliente";
import { ErrorDeFormulario, guardarPreferencias } from "../api/cliente";

const IDIOMAS = [{ valor: "es-AR", etiqueta: "Español (Argentina)" }];

/** The IANA zones of Argentina. The country has more than one, and the difference is real. */
const ZONAS = [
  { valor: "America/Argentina/Buenos_Aires", etiqueta: "Buenos Aires" },
  { valor: "America/Argentina/Cordoba", etiqueta: "Córdoba" },
  { valor: "America/Argentina/Mendoza", etiqueta: "Mendoza" },
  { valor: "America/Argentina/Salta", etiqueta: "Salta" },
  { valor: "America/Argentina/Ushuaia", etiqueta: "Ushuaia" },
];

const CATEGORIAS = [
  { clave: "FACTURACION", etiqueta: "Facturación" },
  { clave: "COBROS", etiqueta: "Cobros" },
  { clave: "SINCRONIZACION", etiqueta: "Sincronización" },
  { clave: "AGENDA", etiqueta: "Agenda" },
  { clave: "SISTEMA", etiqueta: "Sistema" },
];

const CANALES = [
  { clave: "EMAIL", etiqueta: "Email" },
  { clave: "PANEL", etiqueta: "Panel" },
];

const EJEMPLO = "2026-08-18T17:45:00Z";

export interface PropsDeFormularioDePreferencias {
  readonly iniciales: Preferencias;
}

export function FormularioDePreferencias({
  iniciales,
}: PropsDeFormularioDePreferencias): JSX.Element {
  const [idioma, setIdioma] = useState(iniciales.pref_idioma);
  const [zona, setZona] = useState(iniciales.pref_zona_horaria);
  const [suscripciones, setSuscripciones] = useState<Suscripciones>(iniciales.pref_suscripciones);
  const [error, setError] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [montado, setMontado] = useState(false);

  // The preview renders **after hydration only**, and that is not a stylistic choice.
  // `Intl.DateTimeFormat` is backed by ICU, and Node's copy and the browser's disagree
  // on details as small as which space character separates the time from "p. m."
  // (U+202F vs U+00A0). React compares the two strings, finds them different, discards
  // the server HTML and re-renders the entire root on the client — a hydration error on
  // every single load. Rendering it here, where only the browser ever does, is the fix
  // that does not depend on two ICU builds agreeing.
  useEffect(() => setMontado(true), []);

  const recibe = (categoria: string, canal: string): boolean =>
    (suscripciones[categoria] ?? []).includes(canal);

  const alternar = (categoria: string, canal: string): void => {
    setGuardado(false);
    setSuscripciones((previas) => {
      const actuales = previas[categoria] ?? [];
      const nuevas = actuales.includes(canal)
        ? actuales.filter((otro) => otro !== canal)
        : [...actuales, canal];
      return { ...previas, [categoria]: nuevas };
    });
  };

  const enviar = async (evento: React.FormEvent): Promise<void> => {
    evento.preventDefault();
    setError(null);
    setGuardado(false);
    setEnviando(true);
    try {
      await guardarPreferencias({
        pref_idioma: idioma,
        pref_zona_horaria: zona,
        pref_suscripciones: suscripciones,
      });
      setGuardado(true);
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeFormulario
          ? fallo.detalle
          : "No pudimos guardar los cambios. Probá de nuevo en unos minutos.",
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Card titulo="Mis preferencias">
      {error !== null && <Alert tono="error">{error}</Alert>}
      {guardado && <Alert tono="exito">Listo, tus preferencias quedaron guardadas.</Alert>}

      <form onSubmit={(evento) => void enviar(evento)}>
        <Select
          id="idioma"
          etiqueta="Idioma"
          opciones={IDIOMAS}
          value={idioma}
          ayuda="Define el formato de fechas, horas y números. La interfaz está en español."
          onChange={(evento) => {
            setIdioma(evento.target.value);
            setGuardado(false);
          }}
        />
        <Select
          id="zona-horaria"
          etiqueta="Zona horaria"
          opciones={ZONAS}
          value={zona}
          onChange={(evento) => {
            setZona(evento.target.value);
            setGuardado(false);
          }}
        />

        <p className="campo__ayuda">
          Así vas a ver las fechas:{" "}
          <strong>
            {montado ? formatearFechaHora(EJEMPLO, { idioma, zonaHoraria: zona }) : "…"}
          </strong>
        </p>

        <fieldset className="suscripciones__grupo">
          <legend className="campo__etiqueta">Avisos que querés recibir</legend>
          <div className="suscripciones">
            {CATEGORIAS.map((categoria) => (
              <div className="suscripciones__fila" key={categoria.clave}>
                <span className="suscripciones__categoria">{categoria.etiqueta}</span>
                {CANALES.map((canal) => (
                  <label key={canal.clave} htmlFor={`${categoria.clave}-${canal.clave}`}>
                    <input
                      id={`${categoria.clave}-${canal.clave}`}
                      type="checkbox"
                      checked={recibe(categoria.clave, canal.clave)}
                      onChange={() => alternar(categoria.clave, canal.clave)}
                    />{" "}
                    {canal.etiqueta}
                  </label>
                ))}
              </div>
            ))}
          </div>
        </fieldset>

        <Button type="submit" cargando={enviando}>
          Guardar cambios
        </Button>
      </form>
    </Card>
  );
}
