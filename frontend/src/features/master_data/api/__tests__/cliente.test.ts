/**
 * `verCliente`: un cliente por id, contra el BFF de esta app y nunca contra el backend.
 *
 * Mismas dos propiedades que `categoria.test.ts`: la ruta es la del BFF (el navegador no tiene
 * token) y un fallo se vuelve un `ErrorDeCatalogo` con el mensaje que mando el backend.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorDeCatalogo, verCliente } from "../cliente";

const fetchFalso = vi.fn();
vi.stubGlobal("fetch", fetchFalso);

afterEach(() => {
  fetchFalso.mockReset();
});

describe("verCliente", () => {
  it("pide el cliente por id al BFF con GET", async () => {
    fetchFalso.mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "c-1" }) });

    const cliente = await verCliente("c-1");

    expect(cliente).toEqual({ id: "c-1" });
    expect(fetchFalso).toHaveBeenCalledWith("/api/clientes/c-1", { method: "GET" });
  });

  it("un cliente que no existe llega como ErrorDeCatalogo con el mensaje del backend", async () => {
    fetchFalso.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detalle: "No existe el cliente c-9" }),
    });

    await expect(verCliente("c-9")).rejects.toThrow(ErrorDeCatalogo);
    await expect(verCliente("c-9")).rejects.toThrow("No existe el cliente c-9");
  });
});
