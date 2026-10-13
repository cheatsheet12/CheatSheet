/**
 * @vitest-environment jsdom
 *
 * The accountant's page carries the privacy notice and offers nothing to accept
 * (HU-E1-08 RN-08; plan case 10).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const llamarApi = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import { ErrorDeApi } from "@/lib/api";

import PaginaDelContador from "../contador/[valor]/page";

afterEach(() => {
  cleanup();
  llamarApi.mockReset();
});

describe("página del contador", () => {
  it("muestra el aviso con el enlace a la política, también con un enlace que no sirve", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(404, "Este acceso no está disponible."));

    render(await PaginaDelContador({ params: { valor: "abc" } }));

    expect(screen.getByRole("link", { name: "Política de Privacidad" }).getAttribute("href")).toBe(
      "/privacidad",
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
