/**
 * @vitest-environment jsdom
 *
 * Las pantallas del panel de auditoría, notificaciones y soporte (épico 10).
 *
 * Lo que se prueba es lo que los criterios afirman sobre **lo que se ve**, más tres cosas que
 * no están en ninguna historia y sí en el código:
 *
 * - que cambiar un filtro **vuelva a la primera página**: quedarse en la cuarta de un
 *   resultado que ahora tiene dos muestra una tabla vacía que parece un error;
 * - que una operación de un solo paso diga «No registrada» en vez de «0 ms»;
 * - que una notificación ya leída **deje de destacarse**, porque un rojo permanente enseña a
 *   ignorar el rojo.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarOperaciones = vi.fn();
vi.mock("@/features/observability/api/bitacora", async () => {
  const real = await vi.importActual<typeof import("@/features/observability/api/bitacora")>(
    "@/features/observability/api/bitacora",
  );
  return { ...real, listarOperaciones: (...args: unknown[]) => listarOperaciones(...args) };
});

const marcarComoLeida = vi.fn();
const abrirSolicitud = vi.fn();
const listarSolicitudes = vi.fn();
vi.mock("@/features/observability/api/notificaciones", async () => {
  const real = await vi.importActual<typeof import("@/features/observability/api/notificaciones")>(
    "@/features/observability/api/notificaciones",
  );
  return {
    ...real,
    marcarComoLeida: (...args: unknown[]) => marcarComoLeida(...args),
    abrirSolicitud: (...args: unknown[]) => abrirSolicitud(...args),
    listarSolicitudes: (...args: unknown[]) => listarSolicitudes(...args),
  };
});

import {
  ErrorDeNotificacion,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  MENSAJE_SIN_NOTIFICACIONES,
  MENSAJE_SIN_OPERACIONES,
} from "@/features/observability";
import type {
  DetalleDeOperacionRespuesta,
  ListadoDeNotificaciones,
  Operacion,
  Solicitud,
} from "@/features/observability";

const { Bitacora } = await import("@/features/observability/components/Bitacora");
const { DetalleDeOperacion } = await import(
  "@/features/observability/components/DetalleDeOperacion"
);
const { CentroDeNotificaciones } = await import(
  "@/features/observability/components/CentroDeNotificaciones"
);
const { Soporte } = await import("@/features/observability/components/Soporte");

const OPERACION: Operacion = {
  id: "op1",
  timestamp: "2026-09-07T12:00:00Z",
  modulo: "billing",
  accion: "autorizar_comprobante",
  entidad_afectada: "Comprobante:1",
  iniciador: "ia",
  resultado: "completado",
  usuario_id: null,
};

const FALLIDA: Operacion = {
  ...OPERACION,
  id: "op2",
  accion: "enviar_a_arca",
  resultado: "error",
};

const DETALLE: DetalleDeOperacionRespuesta = {
  operacion: OPERACION,
  detalle: { cae: "70123456789012", estado: "AUTORIZADO" },
  timeline: [FALLIDA, OPERACION],
  duracion_ms: 2400,
  paso_con_error: "op2",
};

const BANDEJA: ListadoDeNotificaciones = {
  no_leidas: 1,
  notificaciones: [
    {
      id: "n1",
      categoria: "COBROS",
      severidad: "ALTA",
      cuerpo: "«confirmar_pago» falló sobre Cobro:1.",
      leida: false,
      se_destaca: true,
      created_at: "2026-09-07T12:00:00Z",
    },
  ],
};

const SOLICITUD: Solicitud = {
  id: "s1",
  asunto: "No puedo emitir",
  descripcion: "ARCA rechaza todo",
  prioridad: "ALTA",
  estado: "ABIERTA",
  esta_abierta: true,
  created_at: "2026-09-07T12:00:00Z",
};

afterEach(() => {
  cleanup();
  listarOperaciones.mockReset();
  marcarComoLeida.mockReset();
  abrirSolicitud.mockReset();
  listarSolicitudes.mockReset();
});

describe("PAN-LOG-01 · el listado", () => {
  it("muestra los seis datos que RN-01 pide", () => {
    render(<Bitacora inicial={{ operaciones: [OPERACION], total: 1 }} />);

    const tabla = within(screen.getByRole("table"));
    expect(tabla.getByText("autorizar_comprobante")).toBeTruthy();
    expect(tabla.getByText("Facturación")).toBeTruthy();
    expect(tabla.getByText("Comprobante:1")).toBeTruthy();
    expect(tabla.getByText("Agente IA")).toBeTruthy();
    expect(tabla.getByText("Completado")).toBeTruthy();
  });

  it("muestra la frase de la historia cuando no hay nada", () => {
    render(<Bitacora inicial={{ operaciones: [], total: 0 }} />);

    expect(screen.getByText(MENSAJE_SIN_OPERACIONES)).toBeTruthy();
  });

  it("filtrar por iniciador manda el valor del dominio", async () => {
    listarOperaciones.mockResolvedValue({ operaciones: [], total: 0 });
    render(<Bitacora inicial={{ operaciones: [OPERACION], total: 1 }} />);

    fireEvent.change(screen.getByLabelText("Iniciador"), { target: { value: "ia" } });

    await waitFor(() => {
      expect(listarOperaciones).toHaveBeenCalledWith({ iniciador: "ia", pagina: 1 });
    });
  });

  it("cambiar un filtro vuelve a la primera página", async () => {
    listarOperaciones.mockResolvedValue({ operaciones: [OPERACION], total: 60 });
    render(<Bitacora inicial={{ operaciones: [OPERACION], total: 60 }} />);

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(listarOperaciones).toHaveBeenCalledWith({ pagina: 2 });
    });

    fireEvent.change(screen.getByLabelText("Módulo"), { target: { value: "payments" } });

    await waitFor(() => {
      expect(listarOperaciones).toHaveBeenLastCalledWith({ modulo: "payments", pagina: 1 });
    });
  });

  it("no pagina cuando entra todo en una página", () => {
    render(<Bitacora inicial={{ operaciones: [OPERACION], total: 1 }} />);

    expect(screen.queryByRole("button", { name: "Siguiente" })).toBeNull();
  });

  it("un fallo se dice, no se traga", async () => {
    const { ErrorDeBitacora } = await import("@/features/observability/api/bitacora");
    listarOperaciones.mockRejectedValue(new ErrorDeBitacora("La API no respondió"));
    render(<Bitacora inicial={{ operaciones: [], total: 0 }} />);

    fireEvent.change(screen.getByLabelText("Buscar"), { target: { value: "cobro" } });

    await waitFor(() => {
      expect(screen.getByText("La API no respondió")).toBeTruthy();
    });
  });
});

describe("PAN-LOG-02 · el detalle", () => {
  it("muestra el resumen, los datos registrados y el timeline", () => {
    render(<DetalleDeOperacion detalle={DETALLE} />);

    expect(screen.getByText("70123456789012")).toBeTruthy();
    expect(screen.getByText("2.4 s")).toBeTruthy();
    // El timeline es una lista ordenada y no una tabla: lo que afirma es una secuencia
    // —qué pasó, en qué orden y dónde se cortó— y no filas comparables entre sí.
    const timeline = screen.getByRole("list", { name: "Pasos de la operación" });
    expect(within(timeline).getByText("enviar_a_arca")).toBeTruthy();
  });

  it("avisa cuando la operación falló", () => {
    render(<DetalleDeOperacion detalle={DETALLE} />);

    expect(screen.getByText("La operación falló")).toBeTruthy();
  });

  it("una operación sin pasos no tiene duración medida", () => {
    render(
      <DetalleDeOperacion
        detalle={{ ...DETALLE, duracion_ms: null, paso_con_error: null, detalle: {} }}
      />,
    );

    expect(screen.getByText("No registrada")).toBeTruthy();
    expect(screen.getByText("Esta operación no registró datos adicionales.")).toBeTruthy();
  });
});

describe("PAN-CFG-NOT · el centro de notificaciones", () => {
  it("destaca lo que requiere atención", () => {
    render(<CentroDeNotificaciones inicial={BANDEJA} />);

    expect(screen.getByText("Requiere atención")).toBeTruthy();
    expect(screen.getByText(/1 notificación sin leer/)).toBeTruthy();
  });

  it("marcar como leída deja de destacarla", async () => {
    marcarComoLeida.mockResolvedValue({
      ...BANDEJA.notificaciones[0],
      leida: true,
      se_destaca: false,
    });
    render(<CentroDeNotificaciones inicial={BANDEJA} />);

    fireEvent.click(screen.getByRole("button", { name: "Marcar como leída" }));

    await waitFor(() => {
      expect(screen.getByText("Leída")).toBeTruthy();
    });
    expect(screen.queryByText("Requiere atención")).toBeNull();
    expect(screen.getByText("No tenés notificaciones sin leer.")).toBeTruthy();
  });

  it("una bandeja vacía lo dice con la frase de la historia", () => {
    render(<CentroDeNotificaciones inicial={{ notificaciones: [], no_leidas: 0 }} />);

    expect(screen.getByText(MENSAJE_SIN_NOTIFICACIONES)).toBeTruthy();
  });

  it("un fallo al marcar se muestra", async () => {
    marcarComoLeida.mockRejectedValue(new ErrorDeNotificacion("No existe"));
    render(<CentroDeNotificaciones inicial={BANDEJA} />);

    fireEvent.click(screen.getByRole("button", { name: "Marcar como leída" }));

    await waitFor(() => {
      expect(screen.getByText("No existe")).toBeTruthy();
    });
  });
});

describe("PAN-SOP-01 · soporte", () => {
  // #178: el listado es de la empresa (D82), y «Mis solicitudes» hacía creer que era personal.
  it("titula el listado como de la empresa, no como personal", () => {
    render(<Soporte inicial={[SOLICITUD]} puedeAbrir={false} />);

    expect(screen.getByRole("heading", { name: "Solicitudes de la empresa" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Mis solicitudes" })).toBeNull();
  });

  it("sin solicitudes, lo dice en nombre de la empresa", () => {
    render(<Soporte inicial={[]} puedeAbrir={false} />);

    expect(screen.getByText("La empresa todavía no abrió ninguna solicitud.")).toBeTruthy();
  });

  it("el Operador ve lo abierto y no el formulario", () => {
    render(<Soporte inicial={[SOLICITUD]} puedeAbrir={false} />);

    expect(screen.queryByText("Nueva solicitud")).toBeNull();
    expect(within(screen.getByRole("table")).getByText("No puedo emitir")).toBeTruthy();
  });

  it("el botón está deshabilitado hasta que haya asunto y descripción", () => {
    render(<Soporte inicial={[]} puedeAbrir />);

    const boton = screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement;
    expect(boton.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Asunto"), { target: { value: "No puedo emitir" } });
    expect(boton.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "ARCA falla" } });
    expect(boton.disabled).toBe(false);
  });

  it("enviar refresca el listado y limpia el formulario", async () => {
    abrirSolicitud.mockResolvedValue(SOLICITUD);
    listarSolicitudes.mockResolvedValue({ solicitudes: [SOLICITUD] });
    render(<Soporte inicial={[]} puedeAbrir />);

    fireEvent.change(screen.getByLabelText("Asunto"), { target: { value: "No puedo emitir" } });
    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "ARCA falla" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => {
      expect(within(screen.getByRole("table")).getByText("No puedo emitir")).toBeTruthy();
    });
    expect((screen.getByLabelText("Asunto") as HTMLInputElement).value).toBe("");
  });

  it("un rechazo del backend se muestra con su frase", async () => {
    abrirSolicitud.mockRejectedValue(new ErrorDeNotificacion(MENSAJE_CAMPOS_OBLIGATORIOS));
    render(<Soporte inicial={[]} puedeAbrir />);

    fireEvent.change(screen.getByLabelText("Asunto"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "y" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => {
      expect(screen.getByText(MENSAJE_CAMPOS_OBLIGATORIOS)).toBeTruthy();
    });
  });
});
