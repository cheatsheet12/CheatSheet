/**
 * @vitest-environment jsdom
 *
 * El error de una acción hecha dentro de un diálogo se lee **dentro del diálogo** (#74, en los
 * cuatro diálogos de la Agenda).
 *
 * Hasta acá el mensaje se pintaba arriba de la página, detrás del diálogo que seguía abierto:
 * quien apretaba «Guardar horario» con un slot inválido no veía nada y pensaba que se había
 * guardado. Lo que se prueba: que el mensaje esté dentro del `<dialog>`, que no se repita en la
 * página, y que al volver a abrir el diálogo no aparezca el error de la vez anterior.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarRecursos = vi.fn();
const registrarRecurso = vi.fn();
const configurarDisponibilidad = vi.fn();
const cancelarTurno = vi.fn();
const reprogramarTurno = vi.fn();

vi.mock("@/features/scheduling/api/recurso", async () => {
  const real = await vi.importActual<typeof import("@/features/scheduling/api/recurso")>(
    "@/features/scheduling/api/recurso",
  );
  return {
    ...real,
    listarRecursos: (...args: unknown[]) => listarRecursos(...args),
    registrarRecurso: (...args: unknown[]) => registrarRecurso(...args),
    configurarDisponibilidad: (...args: unknown[]) => configurarDisponibilidad(...args),
  };
});

vi.mock("@/features/scheduling/api/turno", async () => {
  const real = await vi.importActual<typeof import("@/features/scheduling/api/turno")>(
    "@/features/scheduling/api/turno",
  );
  return {
    ...real,
    cancelarTurno: (...args: unknown[]) => cancelarTurno(...args),
    reprogramarTurno: (...args: unknown[]) => reprogramarTurno(...args),
  };
});

import { ErrorDeRecurso, ErrorDeTurno } from "@/features/scheduling";
import type { ListadoDeRecursos, Recurso, ServicioAgendable, Turno } from "@/features/scheduling";

const { RecursosReservables } = await import(
  "@/features/scheduling/components/RecursosReservables"
);
const { DetalleDeTurno } = await import("@/features/scheduling/components/DetalleDeTurno");

const CORTE: ServicioAgendable = { id: "s1", nombre: "Corte", duracion_estandar_min: 30 };

const RECURSO: Recurso = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [
    { dia_semana: 1, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 30 },
  ],
  excepciones: [],
  servicios: [CORTE.id],
  intervalo_entre_turnos_min: 0,
};

const LISTADO: ListadoDeRecursos = { recursos: [RECURSO] };

const RESERVADO: Turno = {
  id: "t1",
  cliente_id: "cl1",
  servicio_id: CORTE.id,
  recurso_id: RECURSO.id,
  cobro_id: null,
  inicio: "2027-09-07T18:00:00+00:00",
  duracion_min: 60,
  fin: "2027-09-07T19:00:00+00:00",
  estado: "RESERVADO",
  canal_reserva: "PANEL",
  ya_transcurrio: false,
  habilita_facturacion: false,
};

const SLOT_INVALIDO = "La duración del slot debe estar entre 5 y 480 minutos.";

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

/** El diálogo abierto. Hay uno solo a la vez. */
function dialogo(): HTMLElement {
  const abierto = document.querySelector("dialog");
  if (abierto === null) {
    throw new Error("No hay ningún diálogo abierto.");
  }
  return abierto;
}

function renderDetalle(): void {
  render(
    <DetalleDeTurno
      inicial={RESERVADO}
      puedeGestionar
      recurso="Consultorio 1"
      servicio="Corte"
      cliente={null}
    />,
  );
}

describe("Configurar recurso", () => {
  it("el rechazo del backend al guardar el horario se lee dentro del diálogo", async () => {
    configurarDisponibilidad.mockRejectedValue(new ErrorDeRecurso(SLOT_INVALIDO));
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));

    fireEvent.click(screen.getByRole("button", { name: "Guardar horario" }));

    expect(await within(dialogo()).findByText(SLOT_INVALIDO)).toBeTruthy();
    // Una sola vez: no se repite detrás, en la página.
    expect(screen.getAllByText(SLOT_INVALIDO)).toHaveLength(1);
  });

  it("al cerrar y volver a abrir no queda el error anterior", async () => {
    configurarDisponibilidad.mockRejectedValue(new ErrorDeRecurso(SLOT_INVALIDO));
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar horario" }));
    await within(dialogo()).findByText(SLOT_INVALIDO);

    fireEvent.click(within(dialogo()).getByRole("button", { name: "Listo" }));
    expect(screen.queryByText(SLOT_INVALIDO)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Configurar" }));
    expect(screen.queryByText(SLOT_INVALIDO)).toBeNull();
  });
});

describe("Agregar recurso", () => {
  it("el rechazo del backend se lee dentro del diálogo", async () => {
    const mensaje = "Ya existe un recurso con ese nombre.";
    registrarRecurso.mockRejectedValue(new ErrorDeRecurso(mensaje));
    render(<RecursosReservables inicial={LISTADO} servicios={[CORTE]} puedeEditar />);
    // El del encabezado: el listado tiene otro, compacto, con el mismo nombre.
    const [agregar] = screen.getAllByRole("button", { name: "Agregar recurso" });
    if (agregar === undefined) {
      throw new Error("No está el botón «Agregar recurso».");
    }
    fireEvent.click(agregar);

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Consultorio 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));

    expect(await within(dialogo()).findByText(mensaje)).toBeTruthy();
    expect(screen.getAllByText(mensaje)).toHaveLength(1);
  });
});

describe("Reprogramar turno", () => {
  it("el rechazo del backend se lee dentro del diálogo, que sigue abierto", async () => {
    const mensaje = "El horario seleccionado no está disponible.";
    reprogramarTurno.mockRejectedValue(new ErrorDeTurno(mensaje));
    renderDetalle();
    fireEvent.click(screen.getByRole("button", { name: "Reprogramar" }));

    fireEvent.change(screen.getByLabelText("Nuevo horario"), {
      target: { value: "2027-09-07T16:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await within(dialogo()).findByText(mensaje)).toBeTruthy();
    expect(screen.getAllByText(mensaje)).toHaveLength(1);
  });
});

describe("Cancelar turno", () => {
  it("el rechazo del backend se lee dentro del diálogo, que sigue abierto", async () => {
    const mensaje = "El turno ya fue cancelado";
    cancelarTurno.mockRejectedValue(new ErrorDeTurno(mensaje));
    renderDetalle();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar turno" }));

    fireEvent.click(screen.getByRole("button", { name: "Sí, cancelar el turno" }));

    expect(await within(dialogo()).findByText(mensaje)).toBeTruthy();
    expect(screen.getAllByText(mensaje)).toHaveLength(1);
  });

  it("si cancela bien, el diálogo se cierra", async () => {
    cancelarTurno.mockResolvedValue({ ...RESERVADO, estado: "CANCELADO" });
    renderDetalle();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar turno" }));

    fireEvent.click(screen.getByRole("button", { name: "Sí, cancelar el turno" }));

    await waitFor(() => expect(document.querySelector("dialog")).toBeNull());
    expect(screen.getByText("Cancelado")).toBeTruthy();
  });
});
