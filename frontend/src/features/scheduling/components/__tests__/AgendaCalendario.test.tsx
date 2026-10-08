/**
 * @vitest-environment jsdom
 *
 * La agenda con sus tres vistas: Lista agrupada por día, y Semana y Día como grilla de tiempo.
 *
 * Hoy, en estos tests, es el martes 6 de octubre de 2026 a las 12:00 de la agenda
 * (15:00 UTC): los turnos se escriben en UTC y se leen en la zona fija de la agenda.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarTurnos = vi.fn();

vi.mock("@/features/scheduling/api/turno", async () => {
  const real = await vi.importActual<typeof import("@/features/scheduling/api/turno")>(
    "@/features/scheduling/api/turno",
  );
  return { ...real, listarTurnos: (...args: unknown[]) => listarTurnos(...args) };
});

import type { Recurso, Turno } from "@/features/scheduling";

import {
  agruparPorDia,
  diaDe,
  encabezadoDeDia,
  horaEnAgenda,
  horasVisibles,
  lunesDe,
  rangoDeVista,
  rangoLegible,
  repartirEnCarriles,
  semanaDe,
  semanasDelMes,
  sumarMeses,
} from "../calendario";

const { AgendaDelDia } = await import("@/features/scheduling/components/AgendaDelDia");

const HOY = "2026-10-06T15:00:00+00:00";

const RECURSO: Recurso = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [],
  excepciones: [],
  servicios: [],
  intervalo_entre_turnos_min: 0,
};
const OTRO: Recurso = { ...RECURSO, id: "r2", nombre: "Consultorio 2" };

function turno(id: string, inicio: string, fin: string, extra: Partial<Turno> = {}): Turno {
  const minutos = (Date.parse(fin) - Date.parse(inicio)) / 60_000;
  return {
    id,
    cliente_id: "c1",
    servicio_id: "s1",
    recurso_id: RECURSO.id,
    cobro_id: null,
    inicio,
    duracion_min: minutos,
    fin,
    estado: "RESERVADO",
    canal_reserva: "PANEL",
    ya_transcurrio: false,
    habilita_facturacion: false,
    ...extra,
  };
}

// 10:00–11:00 y 10:30–11:30 de la agenda (UTC−3): se pisan.
const A = turno("a", "2026-10-06T13:00:00+00:00", "2026-10-06T14:00:00+00:00");
const B = turno("b", "2026-10-06T13:30:00+00:00", "2026-10-06T14:30:00+00:00", {
  cliente_id: "c2",
  estado: "CONFIRMADO",
});
// Mañana 15:00–15:30 de la agenda.
const C = turno("c", "2026-10-07T18:00:00+00:00", "2026-10-07T18:30:00+00:00", {
  recurso_id: OTRO.id,
});

const props = {
  recursos: [RECURSO, OTRO],
  puedeGestionar: true,
  clientes: [
    { id: "c1", nombre: "Ana Pérez" },
    { id: "c2", nombre: "Beto Gómez" },
  ],
  servicios: [{ id: "s1", nombre: "Corte" }],
  hoy: HOY,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("calendario.ts", () => {
  it("lee el día y la hora en la zona de la agenda, no en la del navegador ni en UTC", () => {
    // 01:30 UTC del 7 es todavía el 6 a las 22:30 en Buenos Aires.
    expect(diaDe("2026-10-07T01:30:00+00:00")).toBe("2026-10-06");
    expect(horaEnAgenda("2026-10-07T01:30:00+00:00")).toBe("22:30");
    expect(horaEnAgenda("2026-10-06T03:00:00+00:00")).toBe("00:00");
  });

  it("arma la semana de lunes a domingo y su rango, con el domingo del otro mes incluido", () => {
    expect(lunesDe("2026-10-06")).toBe("2026-10-05");
    expect(semanaDe("2026-10-06")).toHaveLength(7);
    expect(rangoDeVista("semana", "2026-10-06")).toEqual({
      desde: "2026-10-05T00:00:00-03:00",
      hasta: "2026-10-12T00:00:00-03:00",
    });
    expect(rangoDeVista("dia", "2026-10-06")).toEqual({
      desde: "2026-10-06T00:00:00-03:00",
      hasta: "2026-10-07T00:00:00-03:00",
    });
    expect(rangoLegible("semana", "2026-10-06")).toBe("5 – 11 de octubre");
    expect(rangoLegible("semana", "2026-10-29")).toContain("26 oct");
  });

  it("arma las semanas del mes: octubre de 2026 empieza en jueves y ocupa cinco filas", () => {
    const semanas = semanasDelMes("2026-10-15");
    expect(semanas).toHaveLength(5);
    expect(semanas[0]).toEqual([
      "2026-09-28",
      "2026-09-29",
      "2026-09-30",
      "2026-10-01",
      "2026-10-02",
      "2026-10-03",
      "2026-10-04",
    ]);
    expect(semanas[4]?.[6]).toBe("2026-11-01");
    // Un mes de febrero que empieza en lunes y tiene 28 días cabe en cuatro filas.
    expect(semanasDelMes("2027-02-10")).toHaveLength(4);
    // Noviembre de 2026 empieza en domingo: la primera fila es casi toda de octubre y son seis.
    expect(semanasDelMes("2026-11-10")).toHaveLength(6);
  });

  it("suma meses sin pasarse del último día y cruza el año", () => {
    expect(sumarMeses("2026-10-31", 1)).toBe("2026-11-30");
    expect(sumarMeses("2026-01-31", 1)).toBe("2026-02-28");
    expect(sumarMeses("2026-12-15", 1)).toBe("2027-01-15");
    expect(sumarMeses("2026-01-15", -1)).toBe("2025-12-15");
  });

  it("el rango del mes cubre las semanas completas de la grilla y se lee «mes de año»", () => {
    expect(rangoDeVista("mes", "2026-10-06")).toEqual({
      desde: "2026-09-28T00:00:00-03:00",
      hasta: "2026-11-02T00:00:00-03:00",
    });
    expect(rangoLegible("mes", "2026-10-06")).toBe("octubre de 2026");
  });

  it("escribe Hoy y Mañana en el encabezado de cada día", () => {
    expect(encabezadoDeDia("2026-10-06", "2026-10-06")).toBe("Hoy · martes 6 de octubre");
    expect(encabezadoDeDia("2026-10-07", "2026-10-06")).toBe("Mañana · miércoles 7 de octubre");
    expect(encabezadoDeDia("2026-10-09", "2026-10-06")).toBe("viernes 9 de octubre");
  });

  it("agrupa por día y ordena por hora", () => {
    const grupos = agruparPorDia([C, B, A]);
    expect(grupos.map((g) => g.dia)).toEqual(["2026-10-06", "2026-10-07"]);
    expect(grupos[0]?.turnos.map((t) => t.id)).toEqual(["a", "b"]);
  });

  it("reparte el ancho entre los turnos que se pisan y deja entero al que no", () => {
    const solo = turno("z", "2026-10-06T17:00:00+00:00", "2026-10-06T18:00:00+00:00");
    const franjas = repartirEnCarriles([A, B, solo]);
    const de = (id: string) => franjas.find((f) => f.turno.id === id);
    expect(de("a")).toMatchObject({ carril: 0, carriles: 2 });
    expect(de("b")).toMatchObject({ carril: 1, carriles: 2 });
    expect(de("z")).toMatchObject({ carril: 0, carriles: 1 });
  });

  it("amplía las horas visibles para que ningún turno quede afuera", () => {
    expect(horasVisibles([A])).toEqual({ desde: 8, hasta: 20 });
    const tarde = turno("t", "2026-10-07T01:00:00+00:00", "2026-10-07T02:00:00+00:00");
    expect(horasVisibles([tarde])).toEqual({ desde: 8, hasta: 23 });
  });
});

describe("Agenda · vistas", () => {
  it("agrupa la lista por día con «Hoy» y «Mañana» y cada turno es un enlace al detalle", () => {
    render(<AgendaDelDia inicial={{ turnos: [A, B, C] }} {...props} />);

    expect(screen.getByRole("heading", { name: /Hoy · martes 6 de octubre/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Mañana · miércoles 7 de octubre/ })).toBeTruthy();
    const lista = within(screen.getByRole("region", { name: "Turnos" }));
    const enlaces = lista.getAllByRole("link");
    expect(enlaces.map((uno) => uno.getAttribute("href"))).toEqual([
      "/agenda/a",
      "/agenda/b",
      "/agenda/c",
    ]);
    expect(lista.getByText("10:00")).toBeTruthy();
    expect(screen.getByText("3 turnos")).toBeTruthy();
  });

  it("cambia a Semana, pide el rango de la semana y posiciona cada bloque por hora y duración", async () => {
    listarTurnos.mockResolvedValue({ turnos: [A, B, C] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Semana" }));

    await waitFor(() => {
      expect(listarTurnos).toHaveBeenCalledWith({
        desde: "2026-10-05T00:00:00-03:00",
        hasta: "2026-10-12T00:00:00-03:00",
      });
    });
    expect(screen.getByText("5 – 11 de octubre")).toBeTruthy();

    const bloque = await screen.findByRole("link", { name: /^10:00 a 11:00, Ana Pérez/ });
    // Grilla de 8 a 20 (720 min): 10:00 es el minuto 120 → 16,67 %; una hora → 8,33 %.
    expect(Number.parseFloat(bloque.style.top)).toBeCloseTo(16.667, 2);
    expect(Number.parseFloat(bloque.style.height)).toBeCloseTo(8.333, 2);
    // Se pisa con el de las 10:30: se reparten el ancho.
    expect(bloque.style.width).toBe("50%");
    expect(bloque.style.left).toBe("0%");
    const otro = screen.getByRole("link", { name: /^10:30 a 11:30, Beto Gómez/ });
    expect(otro.style.left).toBe("50%");
    expect(otro.getAttribute("href")).toBe("/agenda/b");
    expect(bloque.getAttribute("data-estado")).toBe("RESERVADO");
    expect(otro.getAttribute("data-estado")).toBe("CONFIRMADO");
    // El día de hoy tiene su línea de «ahora» (12:00).
    expect(screen.getByTestId("linea-de-ahora")).toBeTruthy();
  });

  it("navega el período con ‹ y › y vuelve con Hoy, siempre con los mismos parámetros", async () => {
    listarTurnos.mockResolvedValue({ turnos: [] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));
    await waitFor(() => expect(listarTurnos).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Período siguiente" }));
    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        desde: "2026-10-12T00:00:00-03:00",
        hasta: "2026-10-19T00:00:00-03:00",
      });
    });
    expect(screen.getByText("12 – 18 de octubre")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));
    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        desde: "2026-10-05T00:00:00-03:00",
        hasta: "2026-10-12T00:00:00-03:00",
      });
    });
  });

  it("en la vista Día hay una columna por recurso y conserva los filtros elegidos", async () => {
    listarTurnos.mockResolvedValue({ turnos: [A] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "RESERVADO" } });
    await waitFor(() => expect(listarTurnos).toHaveBeenCalledWith({ estado: "RESERVADO" }));

    fireEvent.click(screen.getByRole("button", { name: "Día" }));
    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        estado: "RESERVADO",
        desde: "2026-10-06T00:00:00-03:00",
        hasta: "2026-10-07T00:00:00-03:00",
      });
    });

    expect(await screen.findByRole("group", { name: "Consultorio 1" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Consultorio 2" })).toBeTruthy();
    expect(
      within(screen.getByRole("group", { name: "Consultorio 1" })).getAllByRole("link"),
    ).toHaveLength(1);
  });

  it("muestra el vacío con la frase de la historia y la salida «Nuevo turno»", () => {
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);

    expect(screen.getByText("No hay turnos para el período seleccionado.")).toBeTruthy();
    // Uno en la cabecera y otro en el vacío.
    expect(screen.getAllByRole("link", { name: "Nuevo turno" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).toBeNull();
  });

  it("con un filtro puesto, el vacío ofrece limpiarlo y vuelve a pedir sin filtros", async () => {
    listarTurnos.mockResolvedValue({ turnos: [] });
    render(<AgendaDelDia inicial={{ turnos: [A] }} {...props} />);

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "NO_SHOW" } });
    expect(await screen.findByText("Ningún turno coincide con los filtros")).toBeTruthy();

    const limpiar = screen.getAllByRole("button", { name: "Limpiar filtros" });
    fireEvent.click(limpiar[limpiar.length - 1] as HTMLElement);
    await waitFor(() => expect(listarTurnos).toHaveBeenLastCalledWith({}));
    await waitFor(() => {
      expect(screen.queryByText("Ningún turno coincide con los filtros")).toBeNull();
    });
  });

  it("la grilla vacía se dibuja igual, con el aviso arriba", async () => {
    listarTurnos.mockResolvedValue({ turnos: [] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Semana" }));

    expect(await screen.findAllByRole("group", { name: /de octubre$/ })).toHaveLength(7);
    expect(await screen.findByText("No hay turnos para el período seleccionado.")).toBeTruthy();
  });
});

describe("Agenda · vista Mes", () => {
  const delMes = (id: string, dia: string, hora: number): Turno =>
    turno(
      id,
      `${dia}T${String(hora).padStart(2, "0")}:00:00+00:00`,
      `${dia}T${String(hora + 1).padStart(2, "0")}:00:00+00:00`,
    );

  it("pide las semanas visibles y dibuja una celda por día, con hoy marcado", async () => {
    listarTurnos.mockResolvedValue({ turnos: [A, C] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Mes" }));

    await waitFor(() => {
      expect(listarTurnos).toHaveBeenCalledWith({
        desde: "2026-09-28T00:00:00-03:00",
        hasta: "2026-11-02T00:00:00-03:00",
      });
    });
    expect(screen.getByText("octubre de 2026")).toBeTruthy();
    expect(await screen.findAllByRole("gridcell")).toHaveLength(35);
    expect(screen.getByRole("gridcell", { name: "martes 6 de octubre" }).dataset.hoy).toBe("true");
    expect(screen.getByRole("gridcell", { name: "lunes 28 de septiembre" }).dataset.afuera).toBe(
      "true",
    );
    const dia = within(screen.getByRole("gridcell", { name: "martes 6 de octubre" }));
    expect(dia.getByRole("link", { name: /^10:00, Ana Pérez/ }).getAttribute("href")).toBe(
      "/agenda/a",
    );
  });

  it("navega por mes con ‹ y › y vuelve con Hoy", async () => {
    listarTurnos.mockResolvedValue({ turnos: [] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Mes" }));
    await waitFor(() => expect(listarTurnos).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Período siguiente" }));
    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        desde: "2026-10-26T00:00:00-03:00",
        hasta: "2026-12-07T00:00:00-03:00",
      });
    });
    expect(screen.getByText("noviembre de 2026")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));
    expect(await screen.findByText("octubre de 2026")).toBeTruthy();
  });

  it("un clic en un día lleva a la vista Día de esa fecha", async () => {
    listarTurnos.mockResolvedValue({ turnos: [C] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Mes" }));
    const celda = await screen.findByRole("gridcell", { name: "miércoles 7 de octubre" });

    fireEvent.click(celda);

    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        desde: "2026-10-07T00:00:00-03:00",
        hasta: "2026-10-08T00:00:00-03:00",
      });
    });
    expect(screen.getByText("miércoles 7 de octubre")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Día" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("muestra tres fichas por día y «+N más» para el resto, que también abre el día", async () => {
    const cinco = [10, 11, 12, 13, 14].map((hora) => delMes(`m${hora}`, "2026-10-14", hora));
    listarTurnos.mockResolvedValue({ turnos: cinco });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Mes" }));

    const celda = within(await screen.findByRole("gridcell", { name: "miércoles 14 de octubre" }));
    expect(celda.getAllByRole("link")).toHaveLength(3);
    fireEvent.click(celda.getByRole("button", { name: "+2 más" }));

    await waitFor(() => {
      expect(listarTurnos).toHaveBeenLastCalledWith({
        desde: "2026-10-14T00:00:00-03:00",
        hasta: "2026-10-15T00:00:00-03:00",
      });
    });
  });

  it("un clic en una ficha no cambia de vista: abre el turno", async () => {
    listarTurnos.mockResolvedValue({ turnos: [A] });
    render(<AgendaDelDia inicial={{ turnos: [] }} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Mes" }));
    const ficha = await screen.findByRole("link", { name: /^10:00, Ana Pérez/ });
    listarTurnos.mockClear();

    fireEvent.click(ficha);

    expect(listarTurnos).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mes" }).getAttribute("aria-pressed")).toBe("true");
  });
});
