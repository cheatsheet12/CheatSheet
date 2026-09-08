/**
 * PAN-USR-02 — personal preferences (HU-E1-07).
 *
 * Gap P9 again: no prototype, so this is built from the component catalogue.
 *
 * **The language selector shows one option, and that is deliberate and documented.** The
 * interface is not translated — see `shared/formato.ts`. What the preference governs is
 * how dates, times and numbers are written, which the preview below shows live so the
 * setting is not an unexplained dropdown.
 *
 * **La grilla de avisos escribe el nombre del canal una sola vez.** Antes lo decía dos: la
 * cabecera de columna y otra vez al lado de cada casilla, cinco veces. La etiqueta sigue
 * existiendo para quien escucha la pantalla —una casilla sin nombre accesible es una
 * casilla que no se puede tildar con un lector— pero no se dibuja, y cada renglón lleva su
 * categoría como nombre de grupo para que «Email» no se escuche suelto.
 */

"use client";

import { useEffect, useState } from "react";

import { Alert, Button, Select, formatearFechaHora } from "@/shared";

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
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo guardar">
          {error}
        </Alert>
      )}
      {guardado && <Alert tono="exito">Listo, tus preferencias quedaron guardadas.</Alert>}

      <div className="cfg-panel">
        <div className="cfg-panel__cab">
          {/* No repite el `<h1>`: aquel nombra la pantalla, este dice qué se está editando. */}
          <h2 className="cfg-panel__titulo">Ajustes de tu cuenta</h2>
          <p className="cfg-panel__nota">Valen sólo para vos</p>
        </div>

        <form onSubmit={(evento) => void enviar(evento)}>
          <section className="cfg-seccion">
            <h3 className="cfg-seccion__titulo">Formato regional</h3>
            <p className="cfg-seccion__nota">
              Define cómo se escriben las fechas, las horas y los números en todo el panel. La
              interfaz está en español y no se traduce.
            </p>

            <div className="cfg-campos">
              <Select
                id="idioma"
                etiqueta="Idioma"
                opciones={IDIOMAS}
                value={idioma}
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
            </div>

            {/* El texto suelto y el `<strong>` viven en el mismo párrafo a propósito: es una
                sola frase, y partirla en dos elementos la deja como una etiqueta con un dato
                al lado en vez de como el resultado que es. */}
            <p className="cfg-vista">
              Así vas a ver las fechas:{" "}
              <strong>
                {montado ? formatearFechaHora(EJEMPLO, { idioma, zonaHoraria: zona }) : "…"}
              </strong>
            </p>
          </section>

          <section className="cfg-seccion">
            {/* `fieldset` y `legend` de verdad, pero sin la caja: la agrupación es semántica
                —diez casillas que contestan una sola pregunta— y el borde dibujaba una
                tarjeta adentro de otra. */}
            <fieldset className="cfg-grupo">
              <legend className="cfg-seccion__titulo">Avisos que querés recibir</legend>
              <p className="cfg-seccion__nota">
                Elegí por qué canal te llega cada tipo de aviso. Sin ninguno tildado, ese tema no te
                interrumpe.
              </p>

              <div className="cfg-avisos">
                {/* La fila de canales nombra las columnas: sin ella son diez casillas
                    sueltas y hay que deducir cuál es cuál. Va oculta para un lector de
                    pantalla porque cada casilla ya lleva su propio nombre. */}
                <div className="cfg-avisos__fila cfg-avisos__cab" aria-hidden="true">
                  <span />
                  {CANALES.map((canal) => (
                    <span key={canal.clave}>{canal.etiqueta}</span>
                  ))}
                </div>

                {CATEGORIAS.map((categoria) => (
                  <div
                    className="cfg-avisos__fila"
                    key={categoria.clave}
                    role="group"
                    aria-label={categoria.etiqueta}
                  >
                    <span className="cfg-avisos__categoria">{categoria.etiqueta}</span>
                    {CANALES.map((canal) => (
                      <label
                        className="cfg-avisos__casilla"
                        key={canal.clave}
                        htmlFor={`${categoria.clave}-${canal.clave}`}
                      >
                        <input
                          id={`${categoria.clave}-${canal.clave}`}
                          type="checkbox"
                          checked={recibe(categoria.clave, canal.clave)}
                          onChange={() => alternar(categoria.clave, canal.clave)}
                        />
                        <span className="solo-lectores">{canal.etiqueta}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            </fieldset>
          </section>

          {/* A la derecha, como el «Guardar» de Empresa: la misma acción en dos pantallas de
              la misma sección no puede estar en dos lugares distintos. */}
          <div className="cfg-panel__pie">
            <Button type="submit" cargando={enviando}>
              Guardar cambios
            </Button>
          </div>
        </form>
      </div>
    </>
  );
}
