/**
 * @vitest-environment jsdom
 *
 * Las tres pantallas de la agenda (HU-E7-01 … HU-E7-06).
 *
 * Lo que se prueba acá es lo que los criterios afirman sobre **lo que se ve**, más tres cosas
 * que no están en ninguna historia y sí en el código:
 *
 * - **«Reprogramado» no existe en pantalla.** La historia se tomó el trabajo de decirlo
 *   (RN-02), así que un test lo fija: un turno movido se ve en su franja nueva con el estado
 *   que tenía, y la palabra no aparece en el mapa de etiquetas.
 * - **El botón que no está, dice por qué.** Un turno futuro no ofrece marcar asistencia y
 *   muestra «El turno aún no transcurrió.» — sin eso, alguien recarga la página buscando el
 *   botón.
 * - **El alta vuelve a pedir los horarios cuando alguien se adelantó.** Es la única defensa de
 *   interfaz que tiene la decisión D28, y sin ella el segundo intento repite el primero.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarTurnos = vi.fn();
const verDisponibilidad = vi.fn();
const reservarTurno = vi.fn();
const cancelarTurno = vi.fn();
const reprogramarTurno = vi.fn();
const registrarAsistencia = vi.fn();

vi.mock("@/features/scheduling/api/turno", async () => {
  const real = await vi.importActual<typeof import("@/features/scheduling/api/turno")>(
    "@/features/scheduling/api/turno",
  );
  return {
    ...real,
    listarTurnos: (...args: unknown[]) => listarTurnos(...args),
    verDisponibilidad: (...args: unknown[]) => verDisponibilidad(...args),
    reservarTurno: (...args: unknown[]) => reservarTurno(...args),
    cancelarTurno: (...args: unknown[]) => cancelarTurno(...args),
    reprogramarTurno: (...args: unknown[]) => reprogramarTurno(...args),
    registrarAsistencia: (...args: unknown[]) => registrarAsistencia(...args),
  };
});

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeTurno,
  MENSAJE_NO_TRANSCURRIO,
  MENSAJE_REPROGRAMAR_AL_PASADO,
  MENSAJE_TURNO_EN_EL_PASADO,
} from "@/features/scheduling";
import type { ListadoDeTurnos, Recurso, ServicioAgendable, Turno } from "@/features/scheduling";
import { elegirFecha } from "@/shared/ui/__tests__/elegir-fecha";

const { AgendaDelDia } = await import("@/features/scheduling/components/AgendaDelDia");
const { DetalleDeTurno } = await import("@/features/scheduling/components/DetalleDeTurno");
const { NuevoTurno } = await import("@/features/scheduling/components/NuevoTurno");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const push = routerQueSuspende.push;

const CORTE: ServicioAgendable = { id: "s1", nombre: "Corte", duracion_estandar_min: 30 };

const RECURSO: Recurso = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [
    { dia_semana: 1, hora_inicio: "09:00:00", hora_fin: "18:00:00", duracion_slot_min: 60 },
  ],
  excepciones: [],
  servicios: [CORTE.id],
  intervalo_entre_turnos_min: 0,
};

const INACTIVO: Recurso = { ...RECURSO, id: "r2", nombre: "Consultorio 2", activo: false };

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

const PASADO: Turno = { ...RESERVADO, ya_transcurrio: true };
const CANCELADO: Turno = { ...RESERVADO, estado: "CANCELADO" };

const LISTADO: ListadoDeTurnos = { turnos: [RESERVADO] };

beforeAll(() => {
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
  reiniciarRouter();
});

describe("PAN-AGE-01 — agenda", () => {
  it("no ofrece «Reprogramado» como estado en ningun lado (RN-02)", () => {
    render(<AgendaDelDia inicial={LISTADO} recursos={[RECURSO]} puedeGestionar />);

    // Dentro del listado: el filtro de estados usa las mismas palabras, y lo que se afirma acá
    // es lo que dice la **fila**.
    const tabla = within(screen.getByRole("region", { name: "Turnos" }));
    expect(tabla.getByText("Reservado")).toBeTruthy();
    expect(screen.queryByText("Reprogramado")).toBeNull();
    expect(Object.values(ETIQUETAS_DE_ESTADO)).not.toContain("Reprogramado");
  });

  it("muestra el nombre del recurso y no su id", () => {
    render(<AgendaDelDia inicial={LISTADO} recursos={[RECURSO]} puedeGestionar />);

    // Dentro del listado: el selector de recursos también lo nombra.
    const tabla = within(screen.getByRole("region", { name: "Turnos" }));
    expect(tabla.getByText("Consultorio 1")).toBeTruthy();
    expect(tabla.queryByText("r1")).toBeNull();
  });

  it("filtra por el estado del dominio aunque muestre la etiqueta de interfaz", async () => {
    listarTurnos.mockResolvedValue({ turnos: [] });
    render(<AgendaDelDia inicial={LISTADO} recursos={[RECURSO]} puedeGestionar />);

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "NO_SHOW" } });

    await waitFor(() => {
      expect(listarTurnos).toHaveBeenCalledWith({ estado: "NO_SHOW" });
    });
  });

  it("le esconde «Nuevo turno» a Solo Lectura (RN-03)", () => {
    const { rerender } = render(
      <AgendaDelDia inicial={LISTADO} recursos={[RECURSO]} puedeGestionar />,
    );
    expect(screen.getByRole("link", { name: "Nuevo turno" })).toBeTruthy();

    rerender(<AgendaDelDia inicial={LISTADO} recursos={[RECURSO]} puedeGestionar={false} />);
    expect(screen.queryByRole("link", { name: "Nuevo turno" })).toBeNull();
  });
});

describe("PAN-AGE-02 — detalle del turno", () => {
  it("no ofrece marcar asistencia en un turno futuro, y dice por que", () => {
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    expect(screen.queryByRole("button", { name: "Marcar completado" })).toBeNull();
    // La frase de la historia, en lugar de un botón que no está y no se explica.
    expect(screen.getByText(MENSAJE_NO_TRANSCURRIO)).toBeTruthy();
  });

  it("ofrece las dos marcas cuando el turno ya transcurrio", () => {
    render(
      <DetalleDeTurno inicial={PASADO} puedeGestionar recurso="Consultorio 1" servicio="Corte" />,
    );

    expect(screen.getByRole("button", { name: "Marcar completado" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "No se presentó" })).toBeTruthy();
    expect(screen.queryByText(MENSAJE_NO_TRANSCURRIO)).toBeNull();
  });

  it("un turno cancelado no ofrece ninguna accion", () => {
    render(
      <DetalleDeTurno
        inicial={CANCELADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    expect(screen.queryByRole("button", { name: "Cancelar turno" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reprogramar" })).toBeNull();
  });

  it("le esconde las acciones a Solo Lectura pero le muestra el turno", () => {
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar={false}
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    expect(screen.getByText("Consultorio 1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancelar turno" })).toBeNull();
  });

  it("reprogramar conserva el estado que devuelve el backend", async () => {
    reprogramarTurno.mockResolvedValue({
      ...RESERVADO,
      estado: "CONFIRMADO",
      inicio: "2027-09-07T19:00:00+00:00",
    });
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reprogramar" }));
    fireEvent.change(screen.getByLabelText("Nuevo horario"), {
      target: { value: "2027-09-07T16:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => {
      expect(reprogramarTurno).toHaveBeenCalled();
    });
    expect(await screen.findByText("Confirmado")).toBeTruthy();
  });

  it("muestra el rechazo del backend con sus palabras", async () => {
    cancelarTurno.mockRejectedValue(new ErrorDeTurno("El turno ya fue cancelado"));
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancelar turno" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, cancelar el turno" }));

    expect(await screen.findByText("El turno ya fue cancelado")).toBeTruthy();
  });

  // #172: cancelar no se deshace y le avisa al cliente; ya no pasa al primer clic.
  it("pide confirmación antes de cancelar, y «Volver» no cancela nada", async () => {
    cancelarTurno.mockResolvedValue({ ...RESERVADO, estado: "CANCELADO" });
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancelar turno" }));
    expect(cancelarTurno).not.toHaveBeenCalled();
    expect(screen.getByText(/se le avisa al cliente/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Volver" }));
    expect(cancelarTurno).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar turno" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, cancelar el turno" }));
    await waitFor(() => expect(cancelarTurno).toHaveBeenCalledWith("t1"));
  });

  it("enlaza la sena cuando el turno tiene un cobro asociado (HU-E6-07)", () => {
    render(
      <DetalleDeTurno
        inicial={{ ...RESERVADO, cobro_id: "co1" }}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    const enlace = screen.getByRole("link", { name: "Ver el cobro asociado" });
    expect(enlace.getAttribute("href")).toBe("/cobros/co1");
  });
});

describe("PAN-AGE-02 — nuevo turno", () => {
  it("no ofrece recursos desactivados", () => {
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO, INACTIVO]} servicios={[CORTE]} />);

    const opciones = Array.from(
      (screen.getByLabelText("Recurso") as HTMLSelectElement).options,
    ).map((una) => una.textContent);
    expect(opciones).toContain("Consultorio 1");
    expect(opciones).not.toContain("Consultorio 2");
  });

  it("ofrece solo los horarios libres del recurso ese dia", async () => {
    verDisponibilidad.mockResolvedValue({
      fecha: "2027-09-07",
      horarios: [
        { inicio: "2027-09-07T18:00:00+00:00", ocupado: true },
        { inicio: "2027-09-07T19:00:00+00:00", ocupado: false },
      ],
    });
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });

    const horario = (await screen.findByLabelText("Horario")) as HTMLSelectElement;
    // El ocupado no se ofrece: es la única opción, además de la vacía.
    expect(horario.options).toHaveLength(2);
  });

  it("vuelve a pedir los horarios cuando alguien se adelanto (D28)", async () => {
    verDisponibilidad.mockResolvedValue({
      fecha: "2027-09-07",
      horarios: [{ inicio: "2027-09-07T19:00:00+00:00", ocupado: false }],
    });
    reservarTurno.mockRejectedValue(
      new ErrorDeTurno("El horario seleccionado no está disponible."),
    );
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });
    fireEvent.change(await screen.findByLabelText("Horario"), {
      target: { value: "2027-09-07T19:00:00+00:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reservar turno" }));

    expect(await screen.findByText("El horario seleccionado no está disponible.")).toBeTruthy();
    // La lista se vuelve a pedir: el segundo intento tiene que ver lo que hay ahora. Dos
    // llamadas: la de elegir el servicio y la del refresco despues del rechazo — sin servicio
    // todavia no se consulta nada (D96).
    await waitFor(() => {
      expect(verDisponibilidad).toHaveBeenCalledTimes(2);
    });
    expect(push).not.toHaveBeenCalled();
  });

  it("dice cuando el recurso no tiene horarios ese dia en vez de quedarse mudo", async () => {
    verDisponibilidad.mockResolvedValue({ fecha: "2027-09-05", horarios: [] });
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-05");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });

    expect(await screen.findByText(/El recurso no tiene horarios libres ese día/)).toBeTruthy();
  });

  it("no busca los horarios sin servicio y pide elegirlo (D96)", async () => {
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");

    expect(await screen.findByText("Elegí el servicio para ver los horarios")).toBeTruthy();
    expect(verDisponibilidad).not.toHaveBeenCalled();
  });

  it("busca con el servicio y vuelve a buscar cuando se cambia de servicio (D96)", async () => {
    const color: ServicioAgendable = { id: "s2", nombre: "Color", duracion_estandar_min: 90 };
    verDisponibilidad.mockResolvedValue({
      fecha: "2027-09-07",
      horarios: [{ inicio: "2027-09-07T19:00:00+00:00", ocupado: false }],
    });
    render(
      <NuevoTurno
        clienteId="cl1"
        recursos={[{ ...RECURSO, servicios: [CORTE.id, color.id] }]}
        servicios={[CORTE, color]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });
    fireEvent.change(await screen.findByLabelText("Horario"), {
      target: { value: "2027-09-07T19:00:00+00:00" },
    });
    expect(verDisponibilidad).toHaveBeenLastCalledWith(RECURSO.id, "2027-09-07", CORTE.id);

    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: color.id } });

    await waitFor(() => {
      expect(verDisponibilidad).toHaveBeenLastCalledWith(RECURSO.id, "2027-09-07", color.id);
    });
    // Un horario elegido para el servicio anterior no queda elegido: la grilla es otra.
    await waitFor(() => {
      expect((screen.getByLabelText("Horario") as HTMLSelectElement).value).toBe("");
    });
  });

  it("solo ofrece los servicios que el recurso presta (RN-03)", async () => {
    const color: ServicioAgendable = { id: "s2", nombre: "Color", duracion_estandar_min: 90 };
    verDisponibilidad.mockResolvedValue({ fecha: "2027-09-07", horarios: [] });
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE, color]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });

    const opciones = Array.from(
      (screen.getByLabelText("Servicio") as HTMLSelectElement).options,
    ).map((una) => una.textContent);
    expect(opciones.some((una) => una?.startsWith("Corte"))).toBe(true);
    expect(opciones.some((una) => una?.startsWith("Color"))).toBe(false);
  });
});

describe("D95 — los turnos no se agendan en el pasado", () => {
  it("nuevo turno: el Operador no ve la opcion a posteriori y el Administrador si", () => {
    const { rerender } = render(
      <NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />,
    );
    expect(screen.queryByLabelText("Registrar una atención ya realizada")).toBeNull();

    rerender(
      <NuevoTurno
        clienteId="cl1"
        recursos={[RECURSO]}
        servicios={[CORTE]}
        puedeRegistrarAPosteriori
      />,
    );
    expect(screen.getByLabelText("Registrar una atención ya realizada")).toBeTruthy();
  });

  it("nuevo turno: el campo de fecha no deja elegir un dia anterior a hoy", async () => {
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    // El límite llega con la carga de «hoy»: recién entonces el mes anterior queda deshabilitado.
    await waitFor(() => {
      fireEvent.click(screen.getByLabelText("Fecha"));
      fireEvent.click(screen.getByRole("button", { name: "Mes anterior" }));
      const dia = screen
        .getByRole("dialog")
        .querySelector<HTMLButtonElement>('[data-afuera="false"]:not([disabled])');
      expect(dia).toBeNull();
    });
  });

  it("nuevo turno: a posteriori reemplaza la grilla por fecha y hora, y manda el indicador", async () => {
    reservarTurno.mockResolvedValue({ ...PASADO, id: "t9" });
    render(
      <NuevoTurno
        clienteId="cl1"
        recursos={[RECURSO]}
        servicios={[CORTE]}
        puedeRegistrarAPosteriori
      />,
    );

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });
    fireEvent.click(screen.getByLabelText("Registrar una atención ya realizada"));

    expect(screen.queryByLabelText("Fecha")).toBeNull();
    fireEvent.change(screen.getByLabelText("Fecha y hora de la atención"), {
      target: { value: "2020-09-08T15:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Registrar atención" }));

    await waitFor(() => {
      expect(reservarTurno).toHaveBeenCalledWith(
        expect.objectContaining({ a_posteriori: true, recurso_id: RECURSO.id }),
      );
    });
    expect(push).toHaveBeenCalledWith("/agenda/t9");
  });

  it("nuevo turno: el mensaje del backend se muestra tal cual en el Alert", async () => {
    verDisponibilidad.mockResolvedValue({
      fecha: "2027-09-07",
      horarios: [{ inicio: "2027-09-07T19:00:00+00:00", ocupado: false }],
    });
    reservarTurno.mockRejectedValue(new ErrorDeTurno(MENSAJE_TURNO_EN_EL_PASADO));
    render(<NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />);

    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });
    fireEvent.change(await screen.findByLabelText("Horario"), {
      target: { value: "2027-09-07T19:00:00+00:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reservar turno" }));

    expect(await screen.findByText(MENSAJE_TURNO_EN_EL_PASADO)).toBeTruthy();
  });

  it("detalle: el Operador no ve la correccion a posteriori y el Administrador si", () => {
    const { rerender } = render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reprogramar" }));
    expect(screen.queryByLabelText(/Corrección a posteriori/)).toBeNull();

    rerender(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        puedeRegistrarAPosteriori
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );
    expect(screen.getByLabelText(/Corrección a posteriori/)).toBeTruthy();
  });

  it("detalle: la correccion a posteriori quita el minimo y manda el indicador", async () => {
    reprogramarTurno.mockResolvedValue({ ...RESERVADO, inicio: "2020-09-08T18:00:00+00:00" });
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        puedeRegistrarAPosteriori
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reprogramar" }));
    const campo = screen.getByLabelText("Nuevo horario") as HTMLInputElement;
    await waitFor(() => {
      expect(campo.min).not.toBe("");
    });
    fireEvent.click(screen.getByLabelText(/Corrección a posteriori/));
    expect(campo.min).toBe("");
    fireEvent.change(campo, { target: { value: "2020-09-08T15:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => {
      expect(reprogramarTurno).toHaveBeenCalledWith("t1", expect.any(String), true);
    });
  });

  it("detalle: el rechazo del backend se muestra tal cual y sin correccion manda false", async () => {
    reprogramarTurno.mockRejectedValue(new ErrorDeTurno(MENSAJE_REPROGRAMAR_AL_PASADO));
    render(
      <DetalleDeTurno
        inicial={RESERVADO}
        puedeGestionar
        recurso="Consultorio 1"
        servicio="Corte"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reprogramar" }));
    // Un horario futuro: el `min` del campo es una cortesía que el navegador hace cumplir al
    // enviar el formulario, y lo que se prueba acá es que el rechazo del backend se muestra.
    fireEvent.change(screen.getByLabelText("Nuevo horario"), {
      target: { value: "2099-09-08T15:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByText(MENSAJE_REPROGRAMAR_AL_PASADO)).toBeTruthy();
    expect(reprogramarTurno).toHaveBeenCalledWith("t1", expect.any(String), false);
  });
});

describe("PAN-AGE-02 — nuevo turno, mientras la navegación tarda", () => {
  it("un segundo clic después de la respuesta y antes del detalle no reserva otra vez", async () => {
    // El backend rechazaría el solape, y la pantalla diría «no disponible» sobre un turno que
    // sí se creó mientras la página de destino todavía carga.
    verDisponibilidad.mockResolvedValue({
      fecha: "2027-09-07",
      horarios: [{ inicio: "2027-09-07T19:00:00+00:00", ocupado: false }],
    });
    reservarTurno.mockResolvedValue(RESERVADO);
    render(
      <ArnesDeRouter>
        <NuevoTurno clienteId="cl1" recursos={[RECURSO]} servicios={[CORTE]} />
      </ArnesDeRouter>,
    );
    fireEvent.change(screen.getByLabelText("Recurso"), { target: { value: RECURSO.id } });
    elegirFecha("Fecha", "2027-09-07");
    fireEvent.change(screen.getByLabelText("Servicio"), { target: { value: CORTE.id } });
    fireEvent.change(await screen.findByLabelText("Horario"), {
      target: { value: "2027-09-07T19:00:00+00:00" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Reservar turno" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/agenda/t1"));

    const boton = screen.getByRole("button", { name: "Reservar turno" });
    expect((boton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(boton);
    fireEvent.submit(boton.closest("form") as HTMLFormElement);
    expect(reservarTurno).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
    expect(reservarTurno).toHaveBeenCalledTimes(1);
  });
});
