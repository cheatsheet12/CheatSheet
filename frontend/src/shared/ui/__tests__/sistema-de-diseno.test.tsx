/**
 * The design system, against §1.3 and §1.4 of the specification.
 *
 * These assert the properties the document states as requirements — the disabled state,
 * the visible label, the confirmation before a destructive action, the accessible role —
 * not the colours. Colours are tokens and a snapshot of them would only ever break when
 * somebody legitimately changed one.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Alert, Badge, Button, Campo, Card, Casilla, Stepper } from "@/shared";

describe("Button (§1.3, Elementos de Acción)", () => {
  it("no es submit por accidente", () => {
    expect(renderToStaticMarkup(<Button>Emitir</Button>)).toContain('type="button"');
  });

  it("acepta ser submit cuando el formulario lo necesita", () => {
    expect(renderToStaticMarkup(<Button type="submit">Guardar</Button>)).toContain('type="submit"');
  });

  it("las tres variantes se distinguen en el marcado", () => {
    expect(renderToStaticMarkup(<Button>A</Button>)).toContain("boton--primario");
    expect(renderToStaticMarkup(<Button variante="secundario">A</Button>)).toContain(
      "boton--secundario",
    );
    expect(renderToStaticMarkup(<Button variante="destructivo">A</Button>)).toContain(
      "boton--destructivo",
    );
  });

  it("cargando deshabilita el botón, para que no se envíe dos veces", () => {
    const html = renderToStaticMarkup(<Button cargando>Emitir</Button>);

    expect(html).toContain("disabled");
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("boton__spinner");
  });

  it("disabled se respeta aunque no esté cargando", () => {
    expect(renderToStaticMarkup(<Button disabled>Emitir</Button>)).toContain("disabled");
  });
});

describe("Campo (§1.4, etiquetas visibles)", () => {
  it("la etiqueta es un label real atado al input", () => {
    const html = renderToStaticMarkup(<Campo id="cuit" etiqueta="CUIT" />);

    expect(html).toContain('for="cuit"');
    expect(html).toContain('id="cuit"');
    expect(html).toContain("CUIT");
  });

  it("con error marca aria-invalid y lo describe", () => {
    const html = renderToStaticMarkup(
      <Campo id="cuit" etiqueta="CUIT" error="Ingresá los 11 dígitos del CUIT." />,
    );

    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('aria-describedby="cuit-error"');
    expect(html).toContain('role="alert"');
  });

  it("sin error no inventa aria-describedby", () => {
    const html = renderToStaticMarkup(<Campo id="cuit" etiqueta="CUIT" />);

    expect(html).not.toContain("aria-describedby");
    expect(html).toContain('aria-invalid="false"');
  });

  it("mono aplica la tipografía de CUIT y CAE (§1.2)", () => {
    expect(renderToStaticMarkup(<Campo id="cuit" etiqueta="CUIT" mono />)).toContain("campo--mono");
  });

  it("la casilla admite un enlace dentro de su etiqueta", () => {
    const html = renderToStaticMarkup(
      <Casilla id="terminos">
        Acepto los <a href="/terminos">Términos</a>
      </Casilla>,
    );

    expect(html).toContain('type="checkbox"');
    expect(html).toContain('for="terminos"');
    expect(html).toContain('<a href="/terminos"');
  });
});

describe("Alert / Caja de información (§1.3)", () => {
  it("un error se anuncia como alert", () => {
    expect(renderToStaticMarkup(<Alert tono="error">Falló</Alert>)).toContain('role="alert"');
  });

  it("lo demás se anuncia como status, que no interrumpe", () => {
    expect(renderToStaticMarkup(<Alert tono="exito">Listo</Alert>)).toContain('role="status"');
  });

  it("los cuatro tonos se distinguen", () => {
    expect(renderToStaticMarkup(<Alert>x</Alert>)).toContain("caja");
    expect(renderToStaticMarkup(<Alert tono="exito">x</Alert>)).toContain("caja--exito");
    expect(renderToStaticMarkup(<Alert tono="advertencia">x</Alert>)).toContain(
      "caja--advertencia",
    );
    expect(renderToStaticMarkup(<Alert tono="error">x</Alert>)).toContain("caja--error");
  });

  it("con título lo destaca; sin título no inventa uno", () => {
    expect(renderToStaticMarkup(<Alert titulo="Revisá el CUIT">d</Alert>)).toContain(
      "Revisá el CUIT",
    );
    expect(renderToStaticMarkup(<Alert>d</Alert>)).not.toContain("caja__titulo");
  });
});

describe("Card y Badge", () => {
  it("la card titula con jerarquía real, no con negrita", () => {
    expect(renderToStaticMarkup(<Card titulo="Comprobantes">c</Card>)).toContain("<h2");
  });

  it("la card sin título no deja un encabezado vacío", () => {
    expect(renderToStaticMarkup(<Card>c</Card>)).not.toContain("<h2");
  });

  it("los cuatro estados de badge se distinguen", () => {
    for (const estado of ["ok", "atencion", "pendiente", "error"] as const) {
      expect(renderToStaticMarkup(<Badge estado={estado}>x</Badge>)).toContain(`badge--${estado}`);
    }
  });
});

describe("Stepper (§1.3, Stepper de pasos)", () => {
  const PASOS = [
    { numero: 1, nombre: "Cuenta" },
    { numero: 2, nombre: "Empresa" },
    { numero: 3, nombre: "Integraciones" },
  ];

  it("marca completado, activo y pendiente", () => {
    const html = renderToStaticMarkup(<Stepper pasos={PASOS} actual={2} />);

    expect(html).toContain("stepper__paso--completado");
    expect(html).toContain("stepper__paso--activo");
    // El tercero queda sin modificador: es el estado pendiente.
    expect(html.match(/stepper__paso"/g)).toHaveLength(1);
  });

  it("el paso actual se anuncia con aria-current", () => {
    expect(renderToStaticMarkup(<Stepper pasos={PASOS} actual={2} />)).toContain(
      'aria-current="step"',
    );
  });

  it("el completado muestra el tilde y no su número", () => {
    const html = renderToStaticMarkup(<Stepper pasos={PASOS} actual={3} />);

    expect(html).toContain("✓");
  });

  it("es una lista ordenada, porque los pasos tienen orden", () => {
    expect(renderToStaticMarkup(<Stepper pasos={PASOS} actual={1} />)).toContain("<ol");
  });
});
