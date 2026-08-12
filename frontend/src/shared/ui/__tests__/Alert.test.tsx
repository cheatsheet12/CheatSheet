/**
 * The design system's one behavioural rule: an error announces itself.
 *
 * Rendered to a string rather than to a DOM, so the suite needs no browser
 * environment for a component this simple.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Alert, Button, Card } from "@/shared";

describe("sistema de diseño", () => {
  it("una alerta de error se anuncia como alert", () => {
    const html = renderToStaticMarkup(<Alert tono="error">CUIT invalido</Alert>);

    expect(html).toContain('role="alert"');
  });

  it("una alerta informativa no interrumpe al lector de pantalla", () => {
    const html = renderToStaticMarkup(<Alert>Todo en orden</Alert>);

    expect(html).toContain('role="status"');
  });

  it("el boton nunca envia un formulario por accidente", () => {
    const html = renderToStaticMarkup(<Button>Guardar</Button>);

    expect(html).toContain('type="button"');
  });

  it("la card titula con una jerarquia real, no con texto en negrita", () => {
    const html = renderToStaticMarkup(<Card titulo="Comprobantes">contenido</Card>);

    expect(html).toContain("<h2");
  });

  it("la card sin titulo no inventa un encabezado vacio", () => {
    const html = renderToStaticMarkup(<Card>contenido</Card>);

    expect(html).not.toContain("<h2");
  });

  it("la alerta con titulo lo destaca", () => {
    const html = renderToStaticMarkup(
      <Alert tono="atencion" titulo="Revisá el CUIT">
        detalle
      </Alert>,
    );

    expect(html).toContain("Revisá el CUIT");
    expect(html).toContain("<strong");
  });

  it("el boton de peligro se distingue del primario", () => {
    const peligro = renderToStaticMarkup(<Button variante="peligro">Anular</Button>);
    const secundario = renderToStaticMarkup(<Button variante="secundario">Volver</Button>);
    const primario = renderToStaticMarkup(<Button>Emitir</Button>);

    expect(peligro).toContain("--color-peligro");
    expect(secundario).toContain("transparent");
    expect(primario).toContain("--color-primario");
  });

  it("el boton acepta ser submit cuando el formulario lo necesita", () => {
    const html = renderToStaticMarkup(<Button type="submit">Guardar</Button>);

    expect(html).toContain('type="submit"');
  });
});
