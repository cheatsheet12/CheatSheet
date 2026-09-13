/**
 * @vitest-environment jsdom
 *
 * Las tres pantallas de cobros (HU-E6-01, HU-E6-02, HU-E6-03, HU-E6-04, HU-E6-05).
 *
 * Lo que se prueba acá es lo que los criterios afirman sobre **lo que se ve**, y dos cosas
 * más que no están en ninguna historia y sí en el código:
 *
 * - que el listado mande al backend el nombre del **dominio** —`APROBADO`— aunque muestre
 *   «Pagado». Traducir de un lado y no del otro haría que un filtro devolviera la lista
 *   entera, que es la clase de error que nadie reporta porque parece que funciona;
 * - que copiar el link **avise cuando falla**. Sin `navigator.clipboard` —que es lo que pasa
 *   fuera de un contexto seguro— alguien que apretó «Copiar» y no ve nada asume que copió, y
 *   pega cualquier cosa en el WhatsApp de un cliente.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarCobros = vi.fn();
const verCobro = vi.fn();
const generarCobro = vi.fn();
const cancelarCobro = vi.fn();
const reembolsarCobro = vi.fn();
const push = vi.fn();

vi.mock("@/features/payments/api/cobro", async () => {
  const real = await vi.importActual<typeof import("@/features/payments/api/cobro")>(
    "@/features/payments/api/cobro",
  );
  return {
    ...real,
    listarCobros: (...args: unknown[]) => listarCobros(...args),
    verCobro: (...args: unknown[]) => verCobro(...args),
    generarCobro: (...args: unknown[]) => generarCobro(...args),
    cancelarCobro: (...args: unknown[]) => cancelarCobro(...args),
    reembolsarCobro: (...args: unknown[]) => reembolsarCobro(...args),
  };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import {
  ErrorDeCobro,
  MENSAJE_LINK_COPIADO,
  MENSAJE_MONTO_NO_POSITIVO,
  MENSAJE_SIN_RESULTADOS,
} from "@/features/payments";
import type { Cobro, DetalleDeCobroRespuesta, ListadoDeCobrosRespuesta } from "@/features/payments";

const { ListadoDeCobros } = await import("@/features/payments/components/ListadoDeCobros");
const { DetalleDeCobro } = await import("@/features/payments/components/DetalleDeCobro");
const { NuevoCobro } = await import("@/features/payments/components/NuevoCobro");

const PENDIENTE: Cobro = {
  id: "co1",
  cliente_id: "cl1",
  comprobante_id: null,
  turno_id: null,
  monto: "12500.00",
  monto_reembolsado: null,
  descripcion: "Consulta de septiembre",
  estado: "PENDIENTE",
  url_de_pago: "https://mp.test/checkout/co1",
  tiene_link_activo: true,
  vence_el: "2026-09-20",
  pagado_en: null,
  reembolso_en_proceso: false,
  motivo_de_cancelacion: null,
  created_at: "2026-09-07T12:00:00Z",
};

const VENCIDO: Cobro = {
  ...PENDIENTE,
  id: "co2",
  descripcion: "Consulta de agosto",
  estado: "VENCIDO",
  monto: "8000.00",
};

const LISTADO: ListadoDeCobrosRespuesta = {
  cobros: [PENDIENTE, VENCIDO],
  metricas: {
    cobrado: "45000.00",
    pendiente: "12500.00",
    en_mora: "8000.00",
    tasa_de_cobro: "68.75",
  },
};

const DETALLE: DetalleDeCobroRespuesta = {
  ...PENDIENTE,
  recordatorios: [
    {
      id: "r1",
      paso: 1,
      canal: "WHATSAPP",
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "ENVIADO",
    },
    { id: "r2", paso: 2, canal: "WHATSAPP", enviado_en: null, estado_entrega: null },
  ],
};

const PAGADO: DetalleDeCobroRespuesta = {
  ...DETALLE,
  estado: "APROBADO",
  tiene_link_activo: false,
  pagado_en: "2026-09-15T18:20:00Z",
};

beforeAll(() => {
  // `Modal` es un `<dialog>` nativo y jsdom no implementa `showModal`.
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

/** La tarjeta de metrica que lleva ese titulo. `Card` es un `<section>` con un `<h2>`. */
function metrica(titulo: string): HTMLElement {
  const encabezado = screen.getByRole("heading", { name: titulo });
  const tarjeta = encabezado.closest("section");
  if (tarjeta === null) {
    throw new Error(`La tarjeta «${titulo}» no esta dentro de un <section>.`);
  }
  return tarjeta;
}

describe("PAN-COB-01 — listado de cobros", () => {
  it("muestra las cuatro metricas y los estados con la etiqueta de la historia", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    // Las cuatro tarjetas del encabezado, con el valor que calculo el backend. Se buscan
    // **dentro de cada tarjeta**: el monto de una metrica y el de una fila pueden coincidir
    // —y coinciden acá a proposito— y una busqueda global no distinguiria el total del
    // periodo de la suma que se ve en la tabla, que es justo lo que esta prueba afirma que
    // son cosas distintas.
    expect(within(metrica("Cobrado")).getByText("$ 45.000,00")).toBeTruthy();
    expect(within(metrica("Pendiente")).getByText("$ 12.500,00")).toBeTruthy();
    expect(within(metrica("En mora")).getByText("$ 8.000,00")).toBeTruthy();
    expect(within(metrica("Tasa de cobro")).getByText("68,75 %")).toBeTruthy();

    // `VENCIDO` se lee «En mora», no «Vencido» — en la fila, que es donde esta el estado.
    // La tarjeta de metrica se llama igual, y por eso la busqueda es dentro de la tabla.
    const tabla = within(screen.getByRole("table"));
    expect(tabla.getByText("En mora")).toBeTruthy();
    expect(tabla.queryByText("Vencido")).toBeNull();
  });

  it("filtra por el estado del dominio aunque muestre la etiqueta de interfaz", async () => {
    listarCobros.mockResolvedValue({ ...LISTADO, cobros: [] });
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "APROBADO" } });

    await waitFor(() => {
      expect(listarCobros).toHaveBeenCalledWith({ estado: "APROBADO" });
    });
    expect(await screen.findByText(MENSAJE_SIN_RESULTADOS)).toBeTruthy();
  });

  it("le esconde «Generar cobro» a Solo Lectura", () => {
    const { rerender } = render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);
    expect(screen.getByRole("link", { name: "Generar cobro" })).toBeTruthy();

    rerender(<ListadoDeCobros inicial={LISTADO} puedeGestionar={false} />);
    expect(screen.queryByRole("link", { name: "Generar cobro" })).toBeNull();
  });
});

describe("PAN-COB-02 — detalle del cobro", () => {
  it("muestra el historial de recordatorios, y «Programado» el que todavia no salio", () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);

    expect(screen.getByText("ENVIADO")).toBeTruthy();
    // Un guion diria «salio y no sabemos que paso», que es otra cosa.
    expect(screen.getByText("Programado")).toBeTruthy();
  });

  it("avisa cuando no pudo copiar el link en vez de callarse", async () => {
    // Sin `navigator.clipboard`: exactamente lo que pasa fuera de un contexto seguro.
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);

    fireEvent.click(screen.getByRole("button", { name: "Copiar link" }));

    expect(
      await screen.findByText("No se pudo copiar. Copialo a mano desde el link."),
    ).toBeTruthy();
    expect(screen.queryByText(MENSAJE_LINK_COPIADO)).toBeNull();
  });

  it("no ofrece reembolsar sobre un cobro que no esta pagado", () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();
  });

  it("le esconde el reembolso al Operador aunque el cobro este pagado (RN-05)", () => {
    const { rerender } = render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);
    expect(screen.getByRole("button", { name: "Reembolsar" })).toBeTruthy();

    rerender(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar={false} />);
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();
  });

  it("no deja confirmar una cancelacion con un motivo de menos de diez caracteres", async () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar cobro" }));

    const confirmar = screen.getByRole("button", { name: "Confirmar cancelación" });
    expect(confirmar.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "corto" } });
    expect(confirmar.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Motivo"), {
      target: { value: "El cliente pago por transferencia" },
    });
    expect(confirmar.hasAttribute("disabled")).toBe(false);

    cancelarCobro.mockResolvedValue(PENDIENTE);
    verCobro.mockResolvedValue({ ...DETALLE, estado: "CANCELADO", tiene_link_activo: false });
    fireEvent.click(confirmar);

    await waitFor(() => {
      expect(cancelarCobro).toHaveBeenCalledWith("co1", "El cliente pago por transferencia");
    });
  });

  it("muestra el rechazo de MercadoPago con las palabras del backend", async () => {
    reembolsarCobro.mockRejectedValue(
      new ErrorDeCobro("MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado."),
    );
    render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);

    fireEvent.click(screen.getByRole("button", { name: "Reembolsar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar reembolso" }));

    expect(
      await screen.findByText(
        "MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.",
      ),
    ).toBeTruthy();
  });

  it("dice que el reembolso esta en curso sin mentir sobre el estado (D27)", () => {
    render(
      <DetalleDeCobro
        inicial={{ ...PAGADO, reembolso_en_proceso: true }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(screen.getByText("Reembolso en proceso")).toBeTruthy();
    // Y no se ofrece pedir un segundo reembolso mientras el primero no volvio.
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();
  });
});

describe("PAN-COB-03 — nuevo cobro", () => {
  it("no deja generar sin concepto ni con monto cero, y lo dice", () => {
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);

    const generar = screen.getByRole("button", { name: "Generar link de pago" });
    expect(generar.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Seña" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "0" } });
    expect(screen.getByText(MENSAJE_MONTO_NO_POSITIVO)).toBeTruthy();
    expect(generar.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "12500.50" } });
    expect(generar.hasAttribute("disabled")).toBe(false);
  });

  it("manda el monto como texto, tal como se escribio", async () => {
    generarCobro.mockResolvedValue(PENDIENTE);
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);

    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "12500.10" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    await waitFor(() => {
      expect(generarCobro).toHaveBeenCalledWith({
        cliente_id: "cl1",
        // Texto, no `12500.1`: el punto de todo el archivo `cobro.ts`.
        monto: "12500.10",
        descripcion: "Consulta",
        comprobante_id: null,
      });
    });
    expect(push).toHaveBeenCalledWith("/cobros/co1");
  });

  it("ofrece asociar un comprobante solo cuando hay alguno con saldo (HU-E6-06)", () => {
    const { rerender } = render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    expect(screen.queryByLabelText("Comprobante asociado")).toBeNull();

    rerender(
      <NuevoCobro
        clienteId="cl1"
        comprobantes={[{ id: "c1", etiqueta: "FACTURA_B 123 — saldo $ 2420.00" }]}
      />,
    );
    expect(screen.getByLabelText("Comprobante asociado")).toBeTruthy();
  });

  it("muestra la caida de MercadoPago con la frase de la historia", async () => {
    generarCobro.mockRejectedValue(
      new ErrorDeCobro("No se pudo generar el link de pago. Intente nuevamente."),
    );
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);

    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    expect(
      await screen.findByText("No se pudo generar el link de pago. Intente nuevamente."),
    ).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });
});
