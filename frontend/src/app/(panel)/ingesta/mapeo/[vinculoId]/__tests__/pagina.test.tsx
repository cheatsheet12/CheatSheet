import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

const llamarApi = vi.fn();

vi.mock("@/lib/session", () => ({ leerClaims: () => ({ rol: "ADMINISTRADOR" }) }));
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const PaginaDeMapeo = (await import("../page")).default;
const { ErrorDeApi } = await import("@/lib/api");

afterEach(() => llamarApi.mockReset());

it("muestra el error de lectura de Google y permite volver a Ingesta", async () => {
  llamarApi.mockRejectedValue(
    new ErrorDeApi(503, "Google no pudo leer las filas", "ProveedorNoDisponible"),
  );

  const html = renderToString(await PaginaDeMapeo({ params: { vinculoId: "v1" } }));

  expect(html).toContain("Google no pudo leer las filas");
  expect(html).toContain('href="/ingesta"');
});
