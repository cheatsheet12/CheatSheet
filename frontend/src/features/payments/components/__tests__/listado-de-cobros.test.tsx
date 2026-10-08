/**
 * @vitest-environment jsdom
 *
 * El listado de cobros rediseñado: la fila lleva al detalle, el link se copia con
 * confirmación, el menú ⋯ ofrece lo que existe, los filtros se limpian y los vacíos se dicen
 * distinto. Los estados y los montos son los de siempre: acá se prueba lo que se ve y se opera.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarCobros = vi.fn();
const push = vi.fn();

vi.mock("@/features/payments/api/cobro", async () => {
  const real = await vi.importActual<typeof import("@/features/payments/api/cobro")>(
    "@/features/payments/api/cobro",
  );
  return { ...real, listarCobros: (...args: unknown[]) => listarCobros(...args) };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import type { Cobro, ListadoDeCobrosRespuesta } from "@/features/payments";
import { elegirFecha } from "@/shared/ui/__tests__/elegir-fecha";

const { ListadoDeCobros } = await import("@/features/payments/components/ListadoDeCobros");

const PENDIENTE: Cobro = {
  id: "co1",
  cliente_id: "cl1",
  comprobante_id: null,
  turno_id: null,
  monto: "12500.00",
  monto_reembolsado: "0.00",
  descripcion: "Consulta de septiembre",
  estado: "PENDIENTE",
  url_de_pago: "https://mp.test/checkout/co1",
  tiene_link_activo: true,
  vence_el: "2999-09-20",
  fecha_pago: null,
  fecha_pago_aproximada: false,
  medio_de_pago: "LINK_MERCADOPAGO",
  numero_de_operacion: null,
  reembolso_en_proceso: false,
  reembolso_en_proceso_monto: null,
  tiene_pago_huerfano: false,
  motivo_de_cancelacion: null,
  created_at: "2026-09-07T12:00:00Z",
};

const PAGADO: Cobro = {
  ...PENDIENTE,
  id: "co2",
  descripcion: "Consulta de agosto",
  estado: "APROBADO",
  tiene_link_activo: false,
  url_de_pago: null,
  vence_el: "2020-01-10",
};

const METRICAS = { cobrado: "0.00", pendiente: "0.00", en_mora: "0.00", tasa_de_cobro: "0" };
const LISTADO: ListadoDeCobrosRespuesta = { cobros: [PENDIENTE, PAGADO], metricas: METRICAS };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("el listado de cobros — filas", () => {
  it("el concepto es un enlace real al detalle del cobro", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    const enlace = screen.getByRole("link", { name: "Consulta de septiembre" });
    expect(enlace.getAttribute("href")).toBe("/cobros/co1");
  });

  it("el monto es el texto de la API, en la fila", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    expect(screen.getAllByText("$ 12.500,00").length).toBeGreaterThan(0);
  });

  it("un cobro pagado no muestra «hace N días» aunque su vencimiento haya pasado", async () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    const fila = screen.getByText("Consulta de agosto").closest("tr");
    expect(fila).not.toBeNull();
    // Se espera a que el día de hoy esté: sin él ninguna fila dice «hace»/«en».
    await waitFor(() => {
      expect(screen.getByText(/^en \d+ días$/)).toBeTruthy();
    });
    expect(within(fila as HTMLElement).queryByText(/^hace /)).toBeNull();
  });
});

describe("el listado de cobros — link de pago", () => {
  it("copia el link y lo confirma en el botón", async () => {
    const escribir = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText: escribir } });
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.click(screen.getByRole("button", { name: "Copiar link de Consulta de septiembre" }));

    expect(await screen.findByText("Copiado")).toBeTruthy();
    expect(escribir).toHaveBeenCalledWith("https://mp.test/checkout/co1");
    expect(screen.getByRole("status").textContent).toBe("Link copiado al portapapeles.");
  });

  it("dice cuando no pudo copiar", async () => {
    vi.stubGlobal("navigator", {});
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.click(screen.getByRole("button", { name: "Copiar link de Consulta de septiembre" }));

    expect(await screen.findByText("No se pudo")).toBeTruthy();
  });

  it("«Abrir» lleva al link en otra pestaña", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    const abrir = screen.getByRole("link", { name: "Abrir el link de Consulta de septiembre" });
    expect(abrir.getAttribute("href")).toBe("https://mp.test/checkout/co1");
    expect(abrir.getAttribute("target")).toBe("_blank");
    expect(abrir.getAttribute("rel")).toContain("noopener");
  });

  it("un cobro sin link activo dice «Sin link» y no ofrece copiar", () => {
    render(<ListadoDeCobros inicial={{ ...LISTADO, cobros: [PAGADO] }} puedeGestionar />);

    expect(screen.getByText("Sin link")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Copiar link/ })).toBeNull();
  });
});

describe("el listado de cobros — menú ⋯", () => {
  it("ofrece ver el detalle, copiar y abrir el link, y «Ver detalle» navega", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.click(
      screen.getByRole("button", { name: "Más acciones para Consulta de septiembre" }),
    );
    const menu = screen.getByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Copiar link" })).toBeTruthy();
    expect(within(menu).getByRole("menuitem", { name: "Abrir link de pago" })).toBeTruthy();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Ver detalle" }));

    expect(push).toHaveBeenCalledWith("/cobros/co1");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("en un cobro sin link sólo ofrece ver el detalle", () => {
    render(<ListadoDeCobros inicial={{ ...LISTADO, cobros: [PAGADO] }} puedeGestionar />);

    fireEvent.click(screen.getByRole("button", { name: "Más acciones para Consulta de agosto" }));

    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Ver detalle",
    ]);
  });

  it("Escape lo cierra", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.click(
      screen.getByRole("button", { name: "Más acciones para Consulta de septiembre" }),
    );
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("el listado de cobros — filtros y vacíos", () => {
  it("«Limpiar filtros» sólo aparece con un filtro activo y lo quita", async () => {
    listarCobros.mockResolvedValue({ ...LISTADO, cobros: [PENDIENTE] });
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);
    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Pendientes" }));
    await waitFor(() => expect(listarCobros).toHaveBeenCalledWith({ estado: "PENDIENTE" }));

    listarCobros.mockResolvedValue(LISTADO);
    fireEvent.click(await screen.findByRole("button", { name: "Limpiar filtros" }));

    await waitFor(() => {
      expect(listarCobros).toHaveBeenLastCalledWith({ estado: "", desde: "", hasta: "" });
    });
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Limpiar filtros" })).toBeNull();
    });
  });

  it("el rango de fechas se elige en el calendario del panel", async () => {
    listarCobros.mockResolvedValue(LISTADO);
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    elegirFecha("Desde", "2027-03-15");

    await waitFor(() => expect(listarCobros).toHaveBeenCalledWith({ desde: "2027-03-15" }));
  });

  it("cuenta cuántos cobros se ven", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    expect(screen.getByText("2 cobros")).toBeTruthy();
  });

  it("sin cobros y sin filtros invita a crear el primero", () => {
    render(<ListadoDeCobros inicial={{ ...LISTADO, cobros: [] }} puedeGestionar />);

    expect(screen.getByText("Todavía no hay cobros.")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Nuevo cobro" }).length).toBe(2);
  });

  it("sin cobros y sin permiso no ofrece crear", () => {
    render(<ListadoDeCobros inicial={{ ...LISTADO, cobros: [] }} puedeGestionar={false} />);

    expect(screen.getByText("Todavía no hay cobros.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Nuevo cobro" })).toBeNull();
  });

  it("sin resultados por un filtro dice la frase de la historia y ofrece limpiarlo", async () => {
    listarCobros.mockResolvedValue({ ...LISTADO, cobros: [] });
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.click(screen.getByRole("button", { name: "En mora" }));

    expect(await screen.findByText("No hay cobros para los filtros seleccionados.")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Limpiar filtros" }).length).toBe(2);
    expect(screen.getAllByRole("link", { name: "Nuevo cobro" }).length).toBe(1);
  });
});
