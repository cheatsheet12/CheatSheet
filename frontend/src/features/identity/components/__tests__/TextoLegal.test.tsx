/**
 * @vitest-environment jsdom
 *
 * The legal text is drawn from a small Markdown subset as React elements, never as HTML
 * (plan case 8).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TextoLegal } from "../TextoLegal";

afterEach(cleanup);

describe("TextoLegal", () => {
  it("dibuja títulos, párrafos y listas del subconjunto", () => {
    const { container } = render(
      <TextoLegal texto={"## Finalidad\n\nPrimer párrafo.\n\n- Uno\n- Dos\n\n## Otro\n\nFin."} />,
    );

    expect(screen.getByRole("heading", { level: 2, name: "Finalidad" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Otro" })).toBeTruthy();
    expect(screen.getByText("Primer párrafo.")).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Uno", "Dos"]);
    expect(container.querySelectorAll("ul")).toHaveLength(1);
  });

  it("no interpreta HTML incrustado en el texto", () => {
    const hostil = [
      '## <img src=x onerror="alert(1)">',
      "",
      "<script>alert(1)</script> y <b>negrita</b>",
      "",
      '- <a href="javascript:alert(1)">enlace</a>',
    ].join("\n");

    const { container } = render(<TextoLegal texto={hostil} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("une las líneas contiguas en un solo párrafo y separa por línea en blanco", () => {
    const { container } = render(<TextoLegal texto={"Una línea\nsigue acá\n\nOtro párrafo"} />);

    const parrafos = [...container.querySelectorAll("p")].map((p) => p.textContent);
    expect(parrafos).toEqual(["Una línea sigue acá", "Otro párrafo"]);
  });

  it("tolera el texto vacío", () => {
    const { container } = render(<TextoLegal texto="" />);

    expect(container.textContent).toBe("");
  });
});
