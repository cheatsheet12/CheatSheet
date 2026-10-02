/**
 * @vitest-environment jsdom
 *
 * PAN-AGE-03 (HU-E7-04, HU-E7-05).
 *
 * Los criterios que se ven: el listado con nombre, tipo, servicios y estado; el rechazo de una
 * franja invertida con la frase de la historia; y que la acción sea **desactivar** y no
 * eliminar, porque los turnos ya reservados se mantienen.
 *
 * Y uno que no está en ninguna historia: que un recurso **sin servicios asociados** lo diga.
 * Es el estado en el que nace, y un recurso que no acepta reservas sin explicar por qué manda
 * a alguien a buscar el error en otro lado.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarRecursos = vi.fn();
const registrarRecurso = vi.fn();
const configurarDisponibilidad = vi.fn();
const asociarServicios = vi.fn();
const cambiarEstadoDeRecurso = vi.fn();
const registrarExcepcion = vi.fn();
const quitarExcepcion = vi.fn();

vi.mock("@/features/scheduling/api/recurso", async () => {
  const real = await vi.importActual<typeof import("@/features/scheduling/api/recurso")>(
    "@/features/scheduling/api/recurso",
  );
  return {
    ...real,
    listarRecursos: (...args: unknown[]) => listarRecursos(...args),
    registrarRecurso: (...args: unknown[]) => registrarRecurso(...args),
    configurarDisponibilidad: (...args: unknown[]) => configurarDisponibilidad(...args),
    asociarServicios: (...args: unknown[]) => asociarServicios(...args),
    cambiarEstadoDeRecurso: (...args: unknown[]) => cambiarEstadoDeRecurso(...args),
    registrarExcepcion: (...args: unknown[]) => registrarExcepcion(...args),
    quitarExcepcion: (...args: unknown[]) => quitarExcepcion(...args),
  };
});

import { ErrorDeRecurso, MENSAJE_HORARIO_INVERTIDO } from "@/features/scheduling";
import type { ListadoDeRecursos, Recurso, ServicioAgendable } from "@/features/scheduling";

const { RecursosReservables } = await import(
  "@/features/scheduling/components/RecursosReservables"
);

const CORTE: ServicioAgendable = { id: "s1", nombre: "Corte", duracion_estandar_min: 30 };

const RECURSO: Recurso = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [
    { dia_semana: 1, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 30 },
  ],
  excepciones: [
    { fecha: "2027-09-05", tipo: "BLOQUEO", franja_inicio: null, franja_duracion_min: null },
  ],
  servicios: [CORTE.id],
  intervalo_entre_turnos_min: 0,
};

const SIN_CONFIGURAR: Recurso = {
  ...RECURSO,
  id: "r2",
  nombre: "Sala nueva",
  patrones: [],
  excepciones: [],
  servicios: [],
};

const LISTADO: ListadoDeRecursos = { recursos: [RECURSO] };

beforeAll(() => {
  let n = 0;
  if (globalThis.crypto === undefined) {
    vi.stubGlobal("crypto", {});
  }
  vi.spyOn(globalThis.crypto, "randomUUID").mockImplementation(
    () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}` as const,
  );
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** La tarjeta que lleva ese título. `Card` es un `<section>` con un `<h2>`. */
function tarjeta(titulo: string): HTMLElement {
  const encabezado = screen.getByRole("heading", { name: titulo });
  const seccion = encabezado.closest("section");
  if (seccion === null) {
    throw new Error(`La tarjeta «${titulo}» no esta dentro de un <section>.`);
  }
  return seccion;
}

describe("PAN-AGE-03", () => {
  it("lista nombre, tipo, servicios, horario y estado", () => {
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);

    const tabla = within(screen.getByRole("table"));
    expect(tabla.getByText("Consultorio 1")).toBeTruthy();
    expect(tabla.getByText("Espacio")).toBeTruthy();
    expect(tabla.getByText("Corte")).toBeTruthy();
    expect(tabla.getByText("Martes 09:00 a 18:00")).toBeTruthy();
    expect(tabla.getByText("Activo")).toBeTruthy();
  });

  it("dice cuando un recurso no tiene servicios ni horario", () => {
    render(
      <RecursosReservables
        inicial={{ recursos: [SIN_CONFIGURAR] }}
        servicios={[CORTE]}
        puedeEditar
      />,
    );

    // Un recurso a medio configurar no acepta reservas, y lo dice en vez de fallar después.
    expect(screen.getByText("Sin servicios asociados")).toBeTruthy();
    expect(screen.getByText("Sin horario configurado")).toBeTruthy();
  });

  it("desactiva en vez de eliminar (RN-03)", async () => {
    cambiarEstadoDeRecurso.mockResolvedValue({ ...RECURSO, activo: false });
    listarRecursos.mockResolvedValue({ recursos: [{ ...RECURSO, activo: false }] });
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);

    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Desactivar" }));

    await waitFor(() => {
      expect(cambiarEstadoDeRecurso).toHaveBeenCalledWith("r1", false);
    });
    expect(await screen.findByText("Inactivo")).toBeTruthy();
  });

  it("no deja guardar una franja invertida, y lo dice con la frase de la historia", () => {
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "08:00" } });

    expect(screen.getByText(MENSAJE_HORARIO_INVERTIDO)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar horario" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("guarda el horario entero, no la franja que cambio", async () => {
    configurarDisponibilidad.mockResolvedValue(RECURSO);
    listarRecursos.mockResolvedValue(LISTADO);
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.click(screen.getByRole("button", { name: "Agregar franja" }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar horario" }));

    await waitFor(() => {
      expect(configurarDisponibilidad).toHaveBeenCalledWith(
        "r1",
        [
          { dia_semana: 1, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 30 },
          { dia_semana: 0, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 30 },
        ],
        0,
      );
    });
  });

  it("rotula el paso de la grilla como duracion del slot y no como minutos por turno (D96)", () => {
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    expect(screen.getByLabelText("Duración del slot (min)")).toBeTruthy();
    expect(screen.queryByLabelText("Minutos por turno")).toBeNull();
    expect(screen.getByText(/La duración del turno es la del servicio/)).toBeTruthy();
  });

  it("manda el intervalo entre turnos junto con el horario (HU-E7-04 RN-06)", async () => {
    configurarDisponibilidad.mockResolvedValue({ ...RECURSO, intervalo_entre_turnos_min: 10 });
    listarRecursos.mockResolvedValue(LISTADO);
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    const intervalo = screen.getByLabelText("Intervalo entre turnos (min)") as HTMLInputElement;
    // Arranca en el valor del recurso: 0 por defecto.
    expect(intervalo.value).toBe("0");
    fireEvent.change(intervalo, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar horario" }));

    await waitFor(() => {
      expect(configurarDisponibilidad).toHaveBeenCalledWith("r1", expect.any(Array), 10);
    });
  });

  it("muestra el rechazo del backend con sus palabras al guardar un intervalo invalido", async () => {
    const mensaje = "El intervalo entre turnos debe estar entre 0 y 480 minutos.";
    configurarDisponibilidad.mockRejectedValue(new ErrorDeRecurso(mensaje));
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.change(screen.getByLabelText("Intervalo entre turnos (min)"), {
      target: { value: "-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar horario" }));

    expect(await screen.findByText(mensaje)).toBeTruthy();
  });

  it("no deja quitar la ultima franja: un recurso sin horario no atiende nunca", () => {
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    // Dentro de la tarjeta del horario: la tabla de excepciones tiene su propio «Quitar».
    const horario = within(tarjeta("Horario semanal"));
    expect(horario.getByRole("button", { name: "Quitar" }).hasAttribute("disabled")).toBe(true);
  });

  it("bloquea un dia y despues lo libera", async () => {
    const conBloqueo = {
      ...RECURSO,
      excepciones: [
        ...RECURSO.excepciones,
        {
          fecha: "2027-12-25",
          tipo: "BLOQUEO" as const,
          franja_inicio: null,
          franja_duracion_min: null,
        },
      ],
    };
    registrarExcepcion.mockResolvedValue(conBloqueo);
    quitarExcepcion.mockResolvedValue({ ...RECURSO, excepciones: [] });
    listarRecursos.mockResolvedValue(LISTADO);
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.change(screen.getByLabelText("Día sin atención"), {
      target: { value: "2027-12-25" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Bloquear el día" }));

    await waitFor(() => {
      expect(registrarExcepcion).toHaveBeenCalledWith("r1", {
        fecha: "2027-12-25",
        tipo: "BLOQUEO",
      });
    });
    expect(await screen.findByText("2027-12-25")).toBeTruthy();

    // El «Quitar» de la tabla de excepciones, no el de la franja del horario.
    const excepciones = within(tarjeta("Excepciones"));
    fireEvent.click(excepciones.getAllByRole("button", { name: "Quitar" })[0] as HTMLElement);
    await waitFor(() => {
      expect(quitarExcepcion).toHaveBeenCalledWith("r1", "2027-09-05");
    });
  });

  it("asocia y desasocia servicios reemplazando la lista", async () => {
    asociarServicios.mockResolvedValue({ ...RECURSO, servicios: [] });
    listarRecursos.mockResolvedValue(LISTADO);
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Guardar servicios" }));

    await waitFor(() => {
      expect(asociarServicios).toHaveBeenCalledWith("r1", []);
    });
  });

  it("le muestra el listado a Solo Lectura pero no las acciones", () => {
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar={false} />);

    expect(screen.getByText("Consultorio 1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Configurar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Agregar recurso" })).toBeNull();
  });

  it("crea un recurso sin horario ni servicios, y lo dice", async () => {
    registrarRecurso.mockResolvedValue(SIN_CONFIGURAR);
    listarRecursos.mockResolvedValue({ recursos: [RECURSO, SIN_CONFIGURAR] });
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Agregar recurso" }));
    expect(screen.getByText(/todavía no acepta reservas/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Sala nueva" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));

    await waitFor(() => {
      expect(registrarRecurso).toHaveBeenCalledWith({
        nombre: "Sala nueva",
        tipo: "PERSONA",
        patrones: [],
        servicios: [],
      });
    });
  });
});
