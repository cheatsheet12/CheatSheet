/**
 * The hydration defect QA found on `/configuracion/preferencias`.
 *
 * `Intl.DateTimeFormat` is backed by ICU, and Node's build and the browser's disagree on
 * details as small as which space separates the time from "p. m." (U+202F vs U+00A0).
 * React compared the two strings, found them different, and **threw away the server HTML
 * to re-render the whole root on the client** — an error in the console on every load.
 *
 * So the assertion is not "the date looks right": it is that the server renders no date
 * at all. Whatever ICU Node happens to ship cannot then disagree with anything.
 */

import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FormularioDePreferencias } from "@/features/identity";

const INICIALES = {
  pref_idioma: "es-AR",
  pref_zona_horaria: "America/Argentina/Buenos_Aires",
  pref_suscripciones: { FACTURACION: ["EMAIL"] },
};

describe("render en el servidor", () => {
  it("no escribe la fecha de ejemplo, que es lo que rompía la hidratación", () => {
    const html = renderToString(<FormularioDePreferencias iniciales={INICIALES} />);

    expect(html).toContain("Así vas a ver las fechas");
    expect(html).not.toMatch(/\d{1,2}\/\d{1,2}\/\d{2}/);
  });

  it("el resto del formulario sí se renderiza en el servidor", () => {
    const html = renderToString(<FormularioDePreferencias iniciales={INICIALES} />);

    // The fix must not turn the whole screen into a client-only render.
    expect(html).toContain("Zona horaria");
    expect(html).toContain("Facturación");
    expect(html).toContain("Guardar cambios");
  });
});
