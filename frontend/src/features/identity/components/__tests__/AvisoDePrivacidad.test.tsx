/**
 * @vitest-environment jsdom
 *
 * The accountant sees a notice with a link to the policy and nothing to accept
 * (HU-E1-08 RN-08; plan case 10).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AvisoDePrivacidad } from "../AvisoDePrivacidad";

afterEach(cleanup);

describe("AvisoDePrivacidad", () => {
  it("avisa del tratamiento de los datos y enlaza la política", () => {
    render(<AvisoDePrivacidad />);

    expect(screen.getByRole("link", { name: "Política de Privacidad" }).getAttribute("href")).toBe(
      "/privacidad",
    );
  });

  it("no ofrece aceptar nada", () => {
    const { container } = render(<AvisoDePrivacidad />);

    expect(container.querySelector("input")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
