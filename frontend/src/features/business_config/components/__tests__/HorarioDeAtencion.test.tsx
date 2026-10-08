/**
 * @vitest-environment jsdom
 *
 * PAN-WA-02 — la tarjeta «Horarios de atención» (caso 38; lo cubre también `FranjasDelDia`).
 *
 * Lo que se ve: sin regla, el mensaje y los valores del prototipo; con regla, sus días, sus dos
 * franjas y su política; «Agregar franja» y «Quitar»; el error de franjas superpuestas antes de
 * mandar; el `PUT` con las franjas ordenadas y las fechas; el mensaje del backend; y que el
 * Operador la vea sin poder editar.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const configurarHorarioDeAtencion = vi.fn();

vi.mock("@/features/business_config/api/atencion", async () => {
  const real = await vi.importActual<typeof import("@/features/business_config/api/atencion")>(
    "@/features/business_config/api/atencion",
  );
  return {
    ...real,
    configurarHorarioDeAtencion: (...args: unknown[]) => configurarHorarioDeAtencion(...args),
  };
});

import { elegirFecha } from "@/shared/ui/__tests__/elegir-fecha";
import { ErrorDeAtencion } from "../../api/atencion";
import type { HorarioDeAtencionGuardado } from "../../api/atencion";
import { HorarioDeAtencion } from "../HorarioDeAtencion";

const HOY = "2026-10-05";

const GUARDADO: HorarioDeAtencionGuardado = {
  reglaId: "rg1",
  activa: true,
  prioridad: 2,
  politica: "MENSAJE_FIJO",
  dias: [
    {
      dia: 0,
      franjas: [
        { desde: "09:00", hasta: "13:00" },
        { desde: "16:00", hasta: "20:00" },
      ],
    },
    { dia: 5, franjas: [{ desde: "09:00", hasta: "14:00" }] },
  ],
  fechas_cerradas: ["2026-10-12"],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function fila(dia: string): HTMLElement {
  const casilla = screen.getByLabelText(dia);
  const renglon = casilla.closest("li");
  if (renglon === null) {
    throw new Error(`No hay renglón para ${dia}`);
  }
  return renglon;
}

function valor(etiqueta: string): string {
  return (screen.getByLabelText(etiqueta) as HTMLInputElement).value;
}

function cambiar(etiqueta: string, nuevo: string): void {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: nuevo } });
}

const botonGuardar = (): HTMLButtonElement =>
  screen.getByRole("button", { name: "Guardar" }) as HTMLButtonElement;

describe("sin regla configurada", () => {
  it("dice que el agente atiende a cualquier hora y precarga los valores del prototipo", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    expect(
      screen.getByText("Sin horario configurado: el agente atiende y deriva a cualquier hora."),
    ).toBeTruthy();
    expect(valor("Desde (Lunes, franja 1)")).toBe("09:00");
    expect(valor("Hasta (Lunes, franja 1)")).toBe("19:00");
    expect(valor("Hasta (Sábado, franja 1)")).toBe("14:00");
    expect((screen.getByLabelText("Domingo") as HTMLInputElement).checked).toBe(false);
    expect(within(fila("Domingo")).getByText("Cerrado")).toBeTruthy();
    expect(screen.getByText(/Zona horaria: ART \(GMT-3\)/)).toBeTruthy();
  });

  it("la política por defecto es que el agente responde igual", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((uno) => uno.checked)).toEqual([true, false]);
  });
});

describe("con regla", () => {
  it("pinta sus días, sus dos franjas y su política", () => {
    render(<HorarioDeAtencion inicial={GUARDADO} puedeEditar hoy={HOY} />);

    expect(screen.queryByText(/Sin horario configurado/)).toBeNull();
    expect(valor("Desde (Lunes, franja 1)")).toBe("09:00");
    expect(valor("Hasta (Lunes, franja 1)")).toBe("13:00");
    expect(valor("Desde (Lunes, franja 2)")).toBe("16:00");
    expect(valor("Hasta (Lunes, franja 2)")).toBe("20:00");
    expect((screen.getByLabelText("Martes") as HTMLInputElement).checked).toBe(false);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((uno) => uno.checked)).toEqual([false, true]);
  });

  it("una regla desactivada lo avisa y dice que guardar la reactiva", () => {
    render(<HorarioDeAtencion inicial={{ ...GUARDADO, activa: false }} puedeEditar hoy={HOY} />);

    expect(screen.getByText(/desactivado en las reglas de negocio/)).toBeTruthy();
  });

  it("una configuración vacía se muestra con todos los días apagados y no deja guardar", () => {
    render(<HorarioDeAtencion inicial={{ ...GUARDADO, dias: [] }} puedeEditar hoy={HOY} />);

    expect(screen.getByText("Indicá al menos un día con horario de atención.")).toBeTruthy();
    expect(botonGuardar().disabled).toBe(true);
  });
});

describe("franjas", () => {
  it("«Agregar franja» suma un renglón y «Quitar» lo saca", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);
    const lunes = within(fila("Lunes"));

    fireEvent.click(lunes.getByRole("button", { name: "Agregar franja" }));

    expect(valor("Desde (Lunes, franja 2)")).toBe("16:00");
    expect(lunes.getAllByRole("button", { name: "Quitar" })).toHaveLength(2);

    fireEvent.click(lunes.getAllByRole("button", { name: "Quitar" })[1] as HTMLElement);

    expect(screen.queryByLabelText("Desde (Lunes, franja 2)")).toBeNull();
  });

  it("quitar la última franja apaga el día, y encenderlo de nuevo trae una franja", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    fireEvent.click(within(fila("Sábado")).getByRole("button", { name: "Quitar" }));

    expect((screen.getByLabelText("Sábado") as HTMLInputElement).checked).toBe(false);
    expect(within(fila("Sábado")).getByText("Cerrado")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("Sábado"));

    expect(valor("Desde (Sábado, franja 1)")).toBe("09:00");
  });

  it("dos franjas superpuestas o que se tocan muestran el error y deshabilitan «Guardar»", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);
    fireEvent.click(within(fila("Lunes")).getByRole("button", { name: "Agregar franja" }));

    // 09:00–19:00 y 16:00–20:00 se superponen.
    expect(
      within(fila("Lunes")).getByText(
        "Las franjas de un mismo día no pueden superponerse ni tocarse.",
      ),
    ).toBeTruthy();
    expect(botonGuardar().disabled).toBe(true);

    // 09:00–19:00 y 19:00–20:00 se tocan.
    cambiar("Desde (Lunes, franja 2)", "19:00");
    expect(
      within(fila("Lunes")).getByText(
        "Las franjas de un mismo día no pueden superponerse ni tocarse.",
      ),
    ).toBeTruthy();

    cambiar("Desde (Lunes, franja 2)", "20:00");
    cambiar("Hasta (Lunes, franja 2)", "21:00");
    expect(botonGuardar().disabled).toBe(false);
  });

  it("una franja con el cierre antes de la apertura muestra el error y deshabilita «Guardar»", () => {
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    cambiar("Hasta (Martes, franja 1)", "08:00");

    expect(
      within(fila("Martes")).getByText("La hora de cierre debe ser posterior a la de apertura."),
    ).toBeTruthy();
    expect(botonGuardar().disabled).toBe(true);
  });

  it("«Hasta la medianoche» manda 24:00", async () => {
    configurarHorarioDeAtencion.mockResolvedValue(GUARDADO);
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    fireEvent.click(screen.getByLabelText("Hasta la medianoche (Viernes, franja 1)"));
    expect((screen.getByLabelText("Hasta (Viernes, franja 1)") as HTMLInputElement).disabled).toBe(
      true,
    );
    fireEvent.click(botonGuardar());

    await waitFor(() => expect(configurarHorarioDeAtencion).toHaveBeenCalledTimes(1));
    const [configuracion] = configurarHorarioDeAtencion.mock.calls[0] as [
      { dias: { dia: number; franjas: { hasta: string }[] }[] },
    ];
    expect(configuracion.dias.find((uno) => uno.dia === 4)?.franjas[0]?.hasta).toBe("24:00");
  });
});

describe("guardar", () => {
  it("manda el PUT con las franjas ordenadas por «desde», las fechas y la política", async () => {
    configurarHorarioDeAtencion.mockResolvedValue(GUARDADO);
    render(<HorarioDeAtencion inicial={GUARDADO} puedeEditar hoy={HOY} />);

    // La segunda franja pasa a ser la más temprana: viaja primero.
    cambiar("Desde (Lunes, franja 2)", "06:00");
    cambiar("Hasta (Lunes, franja 2)", "08:00");
    fireEvent.click(botonGuardar());

    await waitFor(() => expect(configurarHorarioDeAtencion).toHaveBeenCalledTimes(1));
    expect(configurarHorarioDeAtencion).toHaveBeenCalledWith(
      {
        dias: [
          {
            dia: 0,
            franjas: [
              { desde: "06:00", hasta: "08:00" },
              { desde: "09:00", hasta: "13:00" },
            ],
          },
          { dia: 5, franjas: [{ desde: "09:00", hasta: "14:00" }] },
        ],
        fechas_cerradas: ["2026-10-12"],
        politica: "MENSAJE_FIJO",
      },
      2,
    );
    expect(await screen.findByText("Horario guardado.")).toBeTruthy();
  });

  it("elegir la otra política viaja en el PUT", async () => {
    configurarHorarioDeAtencion.mockResolvedValue(GUARDADO);
    render(<HorarioDeAtencion inicial={null} puedeEditar hoy={HOY} />);

    fireEvent.click(screen.getAllByRole("radio")[1] as HTMLElement);
    fireEvent.click(botonGuardar());

    await waitFor(() => expect(configurarHorarioDeAtencion).toHaveBeenCalledTimes(1));
    expect(configurarHorarioDeAtencion.mock.calls[0]?.[0]).toMatchObject({
      politica: "MENSAJE_FIJO",
    });
    expect(configurarHorarioDeAtencion.mock.calls[0]?.[1]).toBe(0);
  });

  it("muestra el mensaje de validación del backend", async () => {
    configurarHorarioDeAtencion.mockRejectedValue(
      new ErrorDeAtencion("La hora de cierre debe ser posterior a la de apertura."),
    );
    render(<HorarioDeAtencion inicial={GUARDADO} puedeEditar hoy={HOY} />);

    fireEvent.click(botonGuardar());

    expect(
      await screen.findByText("La hora de cierre debe ser posterior a la de apertura."),
    ).toBeTruthy();
    expect(screen.queryByText("Horario guardado.")).toBeNull();
  });

  it("una fecha agregada viaja en el PUT junto con la pasada que la tarjeta no muestra", async () => {
    configurarHorarioDeAtencion.mockResolvedValue(GUARDADO);
    render(
      <HorarioDeAtencion
        inicial={{ ...GUARDADO, fechas_cerradas: ["2026-09-30", "2026-10-12"] }}
        puedeEditar
        hoy={HOY}
      />,
    );
    expect(screen.queryByText("2026-09-30")).toBeNull();

    elegirFecha("Día sin atención", "2026-10-14");
    fireEvent.click(screen.getByRole("button", { name: "Agregar fecha" }));
    fireEvent.click(botonGuardar());

    await waitFor(() => expect(configurarHorarioDeAtencion).toHaveBeenCalledTimes(1));
    expect(configurarHorarioDeAtencion.mock.calls[0]?.[0]).toMatchObject({
      fechas_cerradas: ["2026-09-30", "2026-10-12", "2026-10-14"],
    });
  });
});

describe("un Operador", () => {
  it("la ve sin poder editar: sin «Guardar», sin «Quitar» y con los campos deshabilitados", () => {
    render(<HorarioDeAtencion inicial={GUARDADO} puedeEditar={false} hoy={HOY} />);

    expect(screen.getByText("Horarios de atención")).toBeTruthy();
    expect(valor("Desde (Lunes, franja 1)")).toBe("09:00");
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Quitar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Agregar franja" })).toBeNull();
    expect((screen.getByLabelText("Desde (Lunes, franja 1)") as HTMLInputElement).disabled).toBe(
      true,
    );
    expect((screen.getByLabelText("Lunes") as HTMLInputElement).disabled).toBe(true);
    for (const radio of screen.getAllByRole("radio") as HTMLInputElement[]) {
      expect(radio.closest("fieldset")?.disabled).toBe(true);
    }
  });
});
