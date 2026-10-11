/**
 * @vitest-environment jsdom
 *
 * PAN-FAC-04 (HU-E5-04).
 *
 * Los tres criterios de aceptación que son sobre lo que **se ve**: que todo venga
 * precargado del original, que el tope se explique en vez de sólo bloquear, y que un
 * comprobante ya anulado del todo lo diga en lugar de ofrecer un formulario que sólo puede
 * fallar.
 *
 * Y una cuarta que no está en la historia: que la pantalla **no deje elegir el tipo**. Es
 * RN-02 —lo determina el sistema— y la forma de garantizarlo en la interfaz es no tener el
 * control.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const emitirNotaDeCredito = vi.fn();

vi.mock("@/features/billing/api/comprobante", async () => {
  const real = await vi.importActual<typeof import("@/features/billing/api/comprobante")>(
    "@/features/billing/api/comprobante",
  );
  return {
    ...real,
    emitirNotaDeCredito: (...args: unknown[]) => emitirNotaDeCredito(...args),
  };
});

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import { ErrorDeComprobante, MENSAJE_MONTO_EXCEDIDO } from "@/features/billing";
import type { Anulacion, Comprobante } from "@/features/billing";

const { AnularComprobante } = await import("@/features/billing/components/AnularComprobante");
const { DetalleDeComprobante } = await import("@/features/billing/components/DetalleDeComprobante");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const push = routerQueSuspende.push;

const ORIGINAL: Comprobante = {
  id: "c1",
  tipo: "FACTURA_A",
  estado: "AUTORIZADO",
  numero: 123,
  punto_de_venta_id: "p1",
  cliente_id: "cl1",
  receptor_nombre: "Acme SA",
  receptor_cuit: "30712345671",
  receptor_condicion_iva: "RESPONSABLE_INSCRIPTO",
  cae: "75123456789012",
  cae_vence_el: "2026-09-17",
  motivo_de_rechazo: null,
  leyenda: null,
  subtotal: "2000.00",
  total_iva: "420.00",
  total: "2420.00",
  saldo_pendiente: "2420.00",
  fecha_emision: "2026-09-07T12:00:00Z",
  created_at: "2026-09-07T12:00:00Z",
  descargable: true,
  items: [
    {
      id: "i1",
      descripcion: "Corte de pelo",
      cantidad: "2.00",
      precio_unitario: "1000.00",
      alicuota_iva: "0.2100",
      subtotal: "2000.00",
      iva: "420.00",
    },
  ],
};

const SIN_ANULAR: Anulacion = {
  total_original: "2420.00",
  total_anulado: "0.00",
  disponible: "2420.00",
  es_total: false,
  es_parcial: false,
  notas: [],
};

const PARCIAL: Anulacion = {
  total_original: "2420.00",
  total_anulado: "1210.00",
  disponible: "1210.00",
  es_total: false,
  es_parcial: true,
  notas: [],
};

const TOTAL: Anulacion = {
  total_original: "2420.00",
  total_anulado: "2420.00",
  disponible: "0.00",
  es_total: true,
  es_parcial: false,
  notas: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  reiniciarRouter();
});

describe("lo que viene precargado", () => {
  it("los items del original, que es lo que una anulacion total anula", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />);

    expect((screen.getByLabelText("Descripción 1") as HTMLInputElement).value).toBe(
      "Corte de pelo",
    );
    expect((screen.getByLabelText("Precio unitario") as HTMLInputElement).value).toBe("1000.00");
  });

  it("dice a nombre de quien y hasta cuanto se puede anular", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />);

    expect(screen.getByText(/Acme SA/)).toBeDefined();
    expect(screen.getByText(/2\.420,00/)).toBeDefined();
    expect(screen.getByText(/Nota de crédito A/)).toBeDefined();
  });

  it("**no deja elegir el tipo**: lo determina el original (RN-02)", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />);

    expect(screen.queryByLabelText("Tipo de comprobante")).toBeNull();
  });

  it("con una anulacion parcial previa, muestra lo que queda", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={PARCIAL} />);

    expect(screen.getByText(/ya anulaste/)).toBeDefined();
    expect(screen.getByText(/1\.210,00/)).toBeDefined();
  });
});

describe("el tope · RN-03", () => {
  it("un monto mayor al disponible muestra la frase y bloquea el boton", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={PARCIAL} />);

    // El original entero contra un disponible de la mitad.
    expect(screen.getByText(MENSAJE_MONTO_EXCEDIDO)).toBeDefined();
    expect(
      (screen.getByRole("button", { name: "Emitir nota de crédito" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("bajando la cantidad el boton se habilita", () => {
    render(<AnularComprobante original={ORIGINAL} anulacion={PARCIAL} />);

    fireEvent.change(screen.getByLabelText("Cantidad"), { target: { value: "1" } });

    expect(screen.queryByText(MENSAJE_MONTO_EXCEDIDO)).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Emitir nota de crédito" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it("uno ya anulado del todo no ofrece formulario", () => {
    // Un formulario que sólo puede fallar es peor que decir por qué no hay nada que hacer.
    render(<AnularComprobante original={ORIGINAL} anulacion={TOTAL} />);

    expect(screen.getByText(/Ya está anulado del todo/)).toBeDefined();
    expect(screen.queryByRole("button", { name: "Emitir nota de crédito" })).toBeNull();
  });
});

describe("la emision", () => {
  it("manda solo los items, y los montos como texto", async () => {
    emitirNotaDeCredito.mockResolvedValue({ ...ORIGINAL, id: "nc1" });
    render(<AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />);

    fireEvent.click(screen.getByRole("button", { name: "Emitir nota de crédito" }));

    await waitFor(() => expect(emitirNotaDeCredito).toHaveBeenCalled());
    const [id, items] = emitirNotaDeCredito.mock.calls[0] as [
      string,
      { precio_unitario: unknown; descripcion: string }[],
    ];
    expect(id).toBe("c1");
    expect(typeof items[0]?.precio_unitario).toBe("string");
    // Ni tipo ni receptor viajan: los pone el backend desde el original.
    expect(Object.keys(items[0] ?? {})).toEqual([
      "descripcion",
      "cantidad",
      "precio_unitario",
      "alicuota_iva",
    ]);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/facturacion/c1"));
  });

  it("un rechazo del backend se muestra tal cual llego", async () => {
    emitirNotaDeCredito.mockRejectedValue(new ErrorDeComprobante(MENSAJE_MONTO_EXCEDIDO));
    render(<AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />);

    fireEvent.click(screen.getByRole("button", { name: "Emitir nota de crédito" }));

    expect(await screen.findByText("No se pudo anular")).toBeDefined();
  });
});

describe("la emision, mientras la navegacion tarda", () => {
  it("un segundo clic despues de la respuesta y antes del detalle no emite otra nota de credito", async () => {
    // Con saldo disponible, una segunda nota de credito se emitiria de verdad.
    emitirNotaDeCredito.mockResolvedValue({ ...ORIGINAL, id: "nc1" });
    render(
      <ArnesDeRouter>
        <AnularComprobante original={ORIGINAL} anulacion={SIN_ANULAR} />
      </ArnesDeRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Emitir nota de crédito" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/facturacion/c1"));

    const boton = screen.getByRole("button", { name: "Emitir nota de crédito" });
    expect((boton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(boton);
    fireEvent.submit(boton.closest("form") as HTMLFormElement);
    expect(emitirNotaDeCredito).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
    expect(emitirNotaDeCredito).toHaveBeenCalledTimes(1);
  });
});

describe("el detalle refleja la anulacion · RN-05", () => {
  it("una anulacion parcial se dice, y el comprobante sigue autorizado", () => {
    // La anulación parcial no es un estado: es un monto. Sin este aviso, el badge
    // «Autorizado» se lee como «no le pasó nada a esto».
    render(<DetalleDeComprobante comprobante={ORIGINAL} puntoNumero={1} anulacion={PARCIAL} />);

    expect(screen.getByText(/Anulado parcialmente/)).toBeDefined();
    expect(screen.getByText(/vigentes/)).toBeDefined();
    expect(screen.getByText("Autorizado")).toBeDefined();
  });

  it("sin anulaciones no dice nada al respecto", () => {
    render(<DetalleDeComprobante comprobante={ORIGINAL} puntoNumero={1} anulacion={SIN_ANULAR} />);

    expect(screen.queryByText(/Anulado/)).toBeNull();
  });

  it("el boton de anular aparece solo para quien puede", () => {
    const { rerender } = render(
      <DetalleDeComprobante comprobante={ORIGINAL} puntoNumero={1} puedeAnular={false} />,
    );
    expect(screen.queryByText("Anular con nota de crédito")).toBeNull();

    rerender(<DetalleDeComprobante comprobante={ORIGINAL} puntoNumero={1} puedeAnular />);
    expect(screen.getByText("Anular con nota de crédito")).toBeDefined();
  });
});
