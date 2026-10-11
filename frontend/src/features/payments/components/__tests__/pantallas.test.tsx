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
const actualizarReembolso = vi.fn();
const registrarReembolso = vi.fn();
const corregirReembolso = vi.fn();

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
    actualizarReembolso: (...args: unknown[]) => actualizarReembolso(...args),
    registrarReembolso: (...args: unknown[]) => registrarReembolso(...args),
    corregirReembolso: (...args: unknown[]) => corregirReembolso(...args),
  };
});

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import {
  ErrorDeCobro,
  MENSAJE_LINK_COPIADO,
  MENSAJE_MONTO_NO_POSITIVO,
  MENSAJE_NOTA_DE_CREDITO,
  MENSAJE_PAGO_HUERFANO,
  MENSAJE_SIN_RESULTADOS,
} from "@/features/payments";
import type {
  Cobro,
  DetalleDeCobroRespuesta,
  ListadoDeCobrosRespuesta,
  Reembolso,
} from "@/features/payments";
import { elegirFecha } from "@/shared/ui/__tests__/elegir-fecha";

const { ListadoDeCobros } = await import("@/features/payments/components/ListadoDeCobros");
const { DetalleDeCobro } = await import("@/features/payments/components/DetalleDeCobro");
const { NuevoCobro } = await import("@/features/payments/components/NuevoCobro");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const push = routerQueSuspende.push;

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
  vence_el: "2026-09-20",
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
  cliente_nombre: "Ana Prueba",
  cliente_cuit: "20-22222222-3",
  recordatorios: [
    {
      id: "r1",
      paso: 1,
      canal: "WHATSAPP",
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "ENVIADO",
      intentos: 1,
      proximo_intento_en: null,
      ultimo_error: null,
    },
    {
      id: "r2",
      paso: 2,
      canal: "WHATSAPP",
      enviado_en: null,
      estado_entrega: null,
      intentos: 0,
      proximo_intento_en: null,
      ultimo_error: null,
    },
  ],
  reembolsos: [],
};

const PAGADO: DetalleDeCobroRespuesta = {
  ...DETALLE,
  estado: "APROBADO",
  tiene_link_activo: false,
  fecha_pago: "2026-09-15T18:20:00Z",
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
  reiniciarRouter();
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

  it("aclara que «Cobrado» se mide por fecha de pago", () => {
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    expect(within(metrica("Cobrado")).getByText(/por fecha de pago/)).toBeTruthy();
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

  it("le esconde «Nuevo cobro» a Solo Lectura", () => {
    const { rerender } = render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);
    expect(screen.getByRole("link", { name: "Nuevo cobro" })).toBeTruthy();

    rerender(<ListadoDeCobros inicial={LISTADO} puedeGestionar={false} />);
    expect(screen.queryByRole("link", { name: "Nuevo cobro" })).toBeNull();
  });
});

describe("PAN-COB-02 — detalle del cobro", () => {
  it("muestra el historial de recordatorios, y «Programado» el que todavia no salio", () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);

    expect(screen.getByText("ENVIADO")).toBeTruthy();
    // Un guion diria «salio y no sabemos que paso», que es otra cosa.
    expect(screen.getByText("Programado")).toBeTruthy();
  });

  it("muestra el nombre y el CUIT del cliente (HU-E6-02 criterio 1)", () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);

    expect(screen.getByText("Ana Prueba")).toBeTruthy();
    expect(screen.getByText("20-22222222-3")).toBeTruthy();
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

  it("avisa cuando MercadoPago no pudo invalidar el link al cancelar", async () => {
    // HU-E6-04 RN-03: si el link puede seguir cobrando, la cancelacion no ocurre, y la
    // pantalla lo dice con el texto del backend y no con uno inventado aca.
    cancelarCobro.mockRejectedValue(
      new ErrorDeCobro("MercadoPago no invalido el link de pago: no respondio"),
    );
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Cancelar cobro" }));
    fireEvent.change(screen.getByLabelText("Motivo"), {
      target: { value: "El cliente ya pago por transferencia" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cancelación" }));

    expect(
      await screen.findByText("MercadoPago no invalido el link de pago: no respondio"),
    ).toBeTruthy();
  });

  it("muestra el pago que entro por un link ya cancelado", () => {
    // El aviso de severidad alta manda al administrador a esta pantalla; sin esto, no veria
    // nada distinto de una cancelacion normal.
    render(
      <DetalleDeCobro
        inicial={{
          ...DETALLE,
          estado: "CANCELADO",
          tiene_link_activo: false,
          motivo_de_cancelacion: "El cliente ya pago por transferencia",
          tiene_pago_huerfano: true,
        }}
        puedeGestionar
        puedeReembolsar={false}
      />,
    );

    expect(screen.getByText(MENSAJE_PAGO_HUERFANO)).toBeTruthy();
  });

  it("no dice nada raro en una cancelacion normal", () => {
    render(
      <DetalleDeCobro
        inicial={{
          ...DETALLE,
          estado: "CANCELADO",
          tiene_link_activo: false,
          motivo_de_cancelacion: "Se cargo por duplicado",
        }}
        puedeGestionar
        puedeReembolsar={false}
      />,
    );

    expect(screen.queryByText(MENSAJE_PAGO_HUERFANO)).toBeNull();
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

/** El valor de una fila «clave/valor» del detalle: el `<dd>` que acompaña a ese `<dt>`. */
function valorDe(rotulo: string): HTMLElement {
  const par = screen.getByText(rotulo, { selector: "dt" }).closest("div");
  if (par === null) {
    throw new Error(`La fila «${rotulo}» no esta dentro de un <div>.`);
  }
  return par;
}

describe("PAN-COB-02 — cuándo y cómo se pagó (D91)", () => {
  it("muestra el medio y la fecha de un cobro pagado por link, sin numero de operacion", () => {
    render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);

    expect(within(valorDe("Medio de pago")).getByText("Link de MercadoPago")).toBeTruthy();
    expect(within(valorDe("Fecha de pago")).queryByText("—")).toBeNull();
    expect(within(valorDe("Fecha de pago")).queryByText(/aproximada/)).toBeNull();
    expect(screen.queryByText("N.º de operación", { selector: "dt" })).toBeNull();
  });

  it("avisa cuando la fecha de pago es aproximada", () => {
    render(
      <DetalleDeCobro
        inicial={{ ...PAGADO, fecha_pago_aproximada: true }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(within(valorDe("Fecha de pago")).getByText(/\(aproximada\)/)).toBeTruthy();
  });

  it("muestra un guion en la fecha de un cobro que no se pago", () => {
    render(<DetalleDeCobro inicial={DETALLE} puedeGestionar puedeReembolsar />);

    expect(within(valorDe("Fecha de pago")).getByText("—")).toBeTruthy();
    expect(within(valorDe("Medio de pago")).getByText("Link de MercadoPago")).toBeTruthy();
  });

  it("muestra el numero de operacion solo cuando el medio es una transferencia", () => {
    render(
      <DetalleDeCobro
        inicial={{
          ...PAGADO,
          medio_de_pago: "TRANSFERENCIA",
          numero_de_operacion: "0000123456",
        }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(within(valorDe("Medio de pago")).getByText("Transferencia")).toBeTruthy();
    expect(within(valorDe("N.º de operación")).getByText("0000123456")).toBeTruthy();
  });

  it("le llama «Referencia» al codigo del cobro y no «Operacion»", () => {
    render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);

    expect(screen.getByText("Referencia", { selector: "dt" })).toBeTruthy();
    expect(screen.queryByText("Operación", { selector: "dt" })).toBeNull();
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

  it("sin cliente no deja generar, lo dice y no llama a generarCobro", () => {
    render(<NuevoCobro clienteId={null} comprobantes={[]} />);

    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "1000" } });

    const generar = screen.getByRole("button", { name: "Generar link de pago" });
    expect(generar.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Debe seleccionar un cliente.")).toBeTruthy();
    fireEvent.click(generar);
    expect(generarCobro).not.toHaveBeenCalled();
  });

  it("al cambiar de cliente descarta el comprobante que ya no se ofrece", async () => {
    generarCobro.mockResolvedValue(PENDIENTE);
    const deAna = [{ id: "c1", etiqueta: "Factura B 123 — saldo $ 2.420,00" }];
    const { rerender } = render(<NuevoCobro clienteId="cl1" comprobantes={deAna} />);
    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Comprobante asociado"), { target: { value: "c1" } });

    // Lo escrito se conserva y el comprobante de Ana no viaja con el cobro de Bruno.
    rerender(<NuevoCobro clienteId="cl2" comprobantes={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    await waitFor(() => {
      expect(generarCobro).toHaveBeenCalledWith(
        {
          cliente_id: "cl2",
          monto: "1000",
          descripcion: "Consulta",
          comprobante_id: null,
        },
        expect.any(String),
      );
    });
  });

  it("manda el monto como texto, tal como se escribio", async () => {
    generarCobro.mockResolvedValue(PENDIENTE);
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);

    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "12500.10" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    await waitFor(() => {
      expect(generarCobro).toHaveBeenCalledWith(
        {
          cliente_id: "cl1",
          // Texto, no `12500.1`: el punto de todo el archivo `cobro.ts`.
          monto: "12500.10",
          descripcion: "Consulta",
          comprobante_id: null,
        },
        expect.any(String),
      );
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

  it("al cambiar de cliente deja de mostrar el error del cliente anterior", async () => {
    generarCobro.mockRejectedValue(
      new ErrorDeCobro("El comprobante no corresponde al cliente elegido."),
    );
    const { rerender } = render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    expect(
      await screen.findByText("El comprobante no corresponde al cliente elegido."),
    ).toBeTruthy();

    rerender(<NuevoCobro clienteId="cl2" comprobantes={[]} />);

    expect(screen.queryByText("El comprobante no corresponde al cliente elegido.")).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------------
// Reembolsos parciales y manuales (HU-E6-05)
// ---------------------------------------------------------------------------------------------

const FILA_API: Reembolso = {
  id: "rb1",
  monto: "2500.00",
  fecha_devolucion: "2026-09-20T15:00:00Z",
  origen: "API_MERCADOPAGO",
  referencia: null,
  motivo: null,
  corrige_a: null,
  corregido: false,
};

const FILA_MANUAL: Reembolso = {
  id: "rb2",
  monto: "1000.00",
  fecha_devolucion: "2026-09-21T15:00:00Z",
  origen: "MANUAL",
  referencia: "OP-9",
  motivo: "Devolución por transferencia",
  corrige_a: null,
  corregido: false,
};

const PARCIAL: DetalleDeCobroRespuesta = {
  ...PAGADO,
  estado: "REEMBOLSADO_PARCIAL",
  monto_reembolsado: "2500.00",
  reembolsos: [FILA_API],
};

const POR_TRANSFERENCIA: DetalleDeCobroRespuesta = {
  ...PAGADO,
  medio_de_pago: "TRANSFERENCIA",
  numero_de_operacion: "0000123456",
};

describe("PAN-COB-02 — reembolsos parciales y manuales (HU-E6-05)", () => {
  it("ofrece «Reembolsar» en un pagado y en un parcial, por link, con el pendiente precargado", () => {
    render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);
    fireEvent.click(screen.getByRole("button", { name: "Reembolsar" }));
    expect((screen.getByLabelText("Monto a reembolsar") as HTMLInputElement).value).toBe(
      "12500.00",
    );

    cleanup();
    render(<DetalleDeCobro inicial={PARCIAL} puedeGestionar puedeReembolsar />);
    fireEvent.click(screen.getByRole("button", { name: "Reembolsar" }));
    // 12500.00 - 2500.00: lo que falta devolver, no el monto entero.
    expect((screen.getByLabelText("Monto a reembolsar") as HTMLInputElement).value).toBe(
      "10000.00",
    );
  });

  it("no ofrece «Reembolsar» sobre un reembolsado entero", () => {
    render(
      <DetalleDeCobro
        inicial={{ ...PARCIAL, estado: "REEMBOLSADO", monto_reembolsado: "12500.00" }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();
  });

  it("ofrece «Registrar reembolso» solo en una transferencia, y no la API", () => {
    render(<DetalleDeCobro inicial={POR_TRANSFERENCIA} puedeGestionar puedeReembolsar />);
    expect(screen.getByRole("button", { name: "Registrar reembolso" })).toBeTruthy();
    // Una transferencia no tiene API a la que pedirle nada.
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();

    cleanup();
    render(<DetalleDeCobro inicial={PAGADO} puedeGestionar puedeReembolsar />);
    expect(screen.queryByRole("button", { name: "Registrar reembolso" })).toBeNull();
    expect(screen.getByRole("button", { name: "Reembolsar" })).toBeTruthy();
  });

  it("no le muestra ninguna acción de reembolso al Operador, pero sí el historial", () => {
    render(
      <DetalleDeCobro
        inicial={{
          ...POR_TRANSFERENCIA,
          estado: "REEMBOLSADO_PARCIAL",
          monto_reembolsado: "1000.00",
          reembolsos: [FILA_MANUAL],
        }}
        puedeGestionar
        puedeReembolsar={false}
      />,
    );

    expect(screen.getByText("Devolución por transferencia")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Registrar reembolso" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Corregir" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();
  });

  it("dice «Reembolso en proceso» con el monto y ofrece «Actualizar estado»", async () => {
    actualizarReembolso.mockResolvedValue(PARCIAL);
    verCobro.mockResolvedValue(PARCIAL);
    render(
      <DetalleDeCobro
        inicial={{ ...PAGADO, reembolso_en_proceso: true, reembolso_en_proceso_monto: "400.00" }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(screen.getByText("Reembolso en proceso")).toBeTruthy();
    expect(screen.getByText(/\$ 400,00/)).toBeTruthy();
    // No se ofrece pedir otro mientras el primero no volvió.
    expect(screen.queryByRole("button", { name: "Reembolsar" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Actualizar estado" }));

    await waitFor(() => {
      expect(actualizarReembolso).toHaveBeenCalledWith("co1");
    });
    expect(await screen.findByText("Reembolsado parcialmente")).toBeTruthy();
  });

  it("solo el Administrador ve «Actualizar estado»", () => {
    render(
      <DetalleDeCobro
        inicial={{ ...PAGADO, reembolso_en_proceso: true, reembolso_en_proceso_monto: "400.00" }}
        puedeGestionar
        puedeReembolsar={false}
      />,
    );

    expect(screen.getByText("Reembolso en proceso")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Actualizar estado" })).toBeNull();
  });

  it("muestra el historial con la corrección visible y «Corregir» solo donde corresponde", () => {
    const anulada: Reembolso = { ...FILA_MANUAL, corregido: true };
    const correccion: Reembolso = {
      id: "rb3",
      monto: "-1000.00",
      fecha_devolucion: "2026-09-22T15:00:00Z",
      origen: "MANUAL",
      referencia: null,
      motivo: "Se cargó por error",
      corrige_a: "rb2",
      corregido: false,
    };
    const otra: Reembolso = { ...FILA_MANUAL, id: "rb4", referencia: "OP-10", monto: "300.00" };
    render(
      <DetalleDeCobro
        inicial={{
          ...POR_TRANSFERENCIA,
          estado: "REEMBOLSADO_PARCIAL",
          monto_reembolsado: "300.00",
          reembolsos: [anulada, correccion, otra],
        }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(screen.getByText("Corregido")).toBeTruthy();
    expect(screen.getByText("Corrección")).toBeTruthy();
    // La anulada y la corrección no se corrigen de nuevo: solo la última fila manual.
    expect(screen.getAllByRole("button", { name: "Corregir" })).toHaveLength(1);
  });

  it("no ofrece «Corregir» sobre una fila de MercadoPago", () => {
    render(<DetalleDeCobro inicial={PARCIAL} puedeGestionar puedeReembolsar />);

    expect(screen.getByText("MercadoPago", { selector: ".cob-reembolso__origen" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Corregir" })).toBeNull();
  });

  it("corrige una fila manual pidiendo el motivo", async () => {
    corregirReembolso.mockResolvedValue(POR_TRANSFERENCIA);
    verCobro.mockResolvedValue(POR_TRANSFERENCIA);
    render(
      <DetalleDeCobro
        inicial={{
          ...POR_TRANSFERENCIA,
          estado: "REEMBOLSADO_PARCIAL",
          monto_reembolsado: "1000.00",
          reembolsos: [FILA_MANUAL],
        }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Corregir" }));
    const confirmar = screen.getByRole("button", { name: "Confirmar corrección" });
    // Sin motivo no se corrige: la corrección es una fila visible y tiene que decir por qué.
    expect(confirmar.hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Motivo de la corrección"), {
      target: { value: "Se cargó por error" },
    });
    fireEvent.click(confirmar);

    await waitFor(() => {
      expect(corregirReembolso).toHaveBeenCalledWith("co1", "rb2", "Se cargó por error");
    });
  });

  it("registra un reembolso manual con monto, fecha, referencia y motivo", async () => {
    registrarReembolso.mockResolvedValue(POR_TRANSFERENCIA);
    verCobro.mockResolvedValue(POR_TRANSFERENCIA);
    render(<DetalleDeCobro inicial={POR_TRANSFERENCIA} puedeGestionar puedeReembolsar />);

    fireEvent.click(screen.getByRole("button", { name: "Registrar reembolso" }));
    const confirmar = screen.getByRole("button", { name: "Confirmar registro" });
    expect(confirmar.hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Monto devuelto"), { target: { value: "300.10" } });
    elegirFecha("Fecha de devolución", "2026-09-20");
    fireEvent.change(screen.getByLabelText("Referencia (opcional)"), {
      target: { value: "OP-77" },
    });
    fireEvent.change(screen.getByLabelText("Motivo"), {
      target: { value: "Devolución por transferencia" },
    });
    fireEvent.click(confirmar);

    await waitFor(() => {
      expect(registrarReembolso).toHaveBeenCalledWith("co1", {
        monto: "300.10",
        fecha: "2026-09-20",
        referencia: "OP-77",
        motivo: "Devolución por transferencia",
      });
    });
  });

  it("muestra el rechazo del registro manual con las palabras del backend", async () => {
    registrarReembolso.mockRejectedValue(
      new ErrorDeCobro(
        "El monto a reembolsar no puede superar el monto pendiente de reembolso del cobro.",
      ),
    );
    render(<DetalleDeCobro inicial={POR_TRANSFERENCIA} puedeGestionar puedeReembolsar />);

    fireEvent.click(screen.getByRole("button", { name: "Registrar reembolso" }));
    fireEvent.change(screen.getByLabelText("Monto devuelto"), { target: { value: "99999.00" } });
    elegirFecha("Fecha de devolución", "2026-09-20");
    fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "Devolución" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar registro" }));

    expect(
      await screen.findByText(
        "El monto a reembolsar no puede superar el monto pendiente de reembolso del cobro.",
      ),
    ).toBeTruthy();
  });

  it("avisa que corresponde una nota de crédito, con el enlace, si hay comprobante y reembolso", () => {
    render(
      <DetalleDeCobro
        inicial={{ ...PARCIAL, comprobante_id: "cm1" }}
        puedeGestionar
        puedeReembolsar
      />,
    );

    expect(screen.getByText(MENSAJE_NOTA_DE_CREDITO)).toBeTruthy();
    const enlace = screen.getByRole("link", { name: "Emitir nota de crédito" });
    expect(enlace.getAttribute("href")).toBe("/facturacion/cm1/anular");
  });

  it("no avisa de la nota de crédito sin comprobante o sin nada reembolsado", () => {
    const { rerender } = render(
      <DetalleDeCobro inicial={PARCIAL} puedeGestionar puedeReembolsar />,
    );
    expect(screen.queryByText(MENSAJE_NOTA_DE_CREDITO)).toBeNull();

    rerender(
      <DetalleDeCobro
        inicial={{ ...PAGADO, comprobante_id: "cm1" }}
        puedeGestionar
        puedeReembolsar
      />,
    );
    expect(screen.queryByText(MENSAJE_NOTA_DE_CREDITO)).toBeNull();
  });

  it("le pone «Reembolsado parcialmente» al estado y lo ofrece en el filtro del listado", () => {
    render(<DetalleDeCobro inicial={PARCIAL} puedeGestionar puedeReembolsar />);
    expect(screen.getByText("Reembolsado parcialmente")).toBeTruthy();

    cleanup();
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);
    expect(screen.getByRole("option", { name: "Reembolsado parcialmente" })).toBeTruthy();
  });

  it("filtra por el estado del dominio REEMBOLSADO_PARCIAL", async () => {
    listarCobros.mockResolvedValue({ ...LISTADO, cobros: [] });
    render(<ListadoDeCobros inicial={LISTADO} puedeGestionar />);

    fireEvent.change(screen.getByLabelText("Estado"), {
      target: { value: "REEMBOLSADO_PARCIAL" },
    });

    await waitFor(() => {
      expect(listarCobros).toHaveBeenCalledWith({ estado: "REEMBOLSADO_PARCIAL" });
    });
  });
});

describe("PAN-COB-03 — nuevo cobro, la clave del pedido (ADR-0013)", () => {
  function completar(): void {
    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "1000" } });
  }

  function claveDeLaLlamada(numero: number): string {
    return (generarCobro.mock.calls[numero] as [unknown, string])[1];
  }

  it("manda la misma clave en dos envios tras un error (un 504 del BFF)", async () => {
    generarCobro.mockRejectedValue(new ErrorDeCobro("No se pudo completar la operacion"));
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    completar();

    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await screen.findByText("No se pudo completar la operacion");
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await waitFor(() => expect(generarCobro).toHaveBeenCalledTimes(2));

    expect(claveDeLaLlamada(0)).toMatch(/^[0-9a-f-]{36}$/);
    expect(claveDeLaLlamada(1)).toBe(claveDeLaLlamada(0));
  });

  it("no renueva la clave al editar el formulario despues de un error", async () => {
    generarCobro.mockRejectedValue(new ErrorDeCobro("No se pudo completar la operacion"));
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    completar();
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await screen.findByText("No se pudo completar la operacion");

    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "2000" } });
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await waitFor(() => expect(generarCobro).toHaveBeenCalledTimes(2));

    expect(claveDeLaLlamada(1)).toBe(claveDeLaLlamada(0));
  });

  it("renueva la clave despues de un exito: un nuevo envio es otro cobro", async () => {
    generarCobro.mockResolvedValue(PENDIENTE);
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    completar();

    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/cobros/co1"));
    // Como si el navegador restaurara la pantalla desde el bfcache: misma instancia, otro envio.
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Generar link de pago" }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await waitFor(() => expect(generarCobro).toHaveBeenCalledTimes(2));

    expect(claveDeLaLlamada(1)).not.toBe(claveDeLaLlamada(0));
  });

  it("ante una clave ya usada muestra el texto del backend y el enlace al listado", async () => {
    generarCobro.mockRejectedValue(
      new ErrorDeCobro(
        "Esta clave ya se uso para generar un cobro con otros datos. Revise el listado de cobros antes de reintentar.",
        "ClaveDeIdempotenciaReusada",
      ),
    );
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    completar();

    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    expect(await screen.findByText(/Esta clave ya se uso para generar un cobro/)).toBeTruthy();
    const enlace = screen.getByRole("link", { name: "Ver el listado de cobros" });
    expect(enlace.getAttribute("href")).toBe("/cobros");
  });

  it("un error comun no ofrece el enlace al listado", async () => {
    generarCobro.mockRejectedValue(new ErrorDeCobro("No se pudo completar la operacion"));
    render(<NuevoCobro clienteId="cl1" comprobantes={[]} />);
    completar();

    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));

    await screen.findByText("No se pudo completar la operacion");
    expect(screen.queryByRole("link", { name: "Ver el listado de cobros" })).toBeNull();
  });
});

describe("PAN-COB-03 — nuevo cobro, mientras la navegación tarda", () => {
  it("un segundo clic después de la respuesta y antes del detalle no genera otro cobro", async () => {
    // Un segundo cobro es un segundo link de pago, y la plata se cobra dos veces.
    generarCobro.mockResolvedValue(PENDIENTE);
    render(
      <ArnesDeRouter>
        <NuevoCobro clienteId="cl1" comprobantes={[]} />
      </ArnesDeRouter>,
    );
    fireEvent.change(screen.getByLabelText("Concepto"), { target: { value: "Consulta" } });
    fireEvent.change(screen.getByLabelText("Monto"), { target: { value: "12500.10" } });

    fireEvent.click(screen.getByRole("button", { name: "Generar link de pago" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/cobros/co1"));

    const boton = screen.getByRole("button", { name: "Generar link de pago" });
    expect((boton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(boton);
    fireEvent.submit(boton.closest("form") as HTMLFormElement);
    expect(generarCobro).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
    expect(generarCobro).toHaveBeenCalledTimes(1);
  });
});
