/**
 * @vitest-environment jsdom
 *
 * Las tres pantallas del épico 5 (HU-E5-01, HU-E5-02, HU-E5-03).
 *
 * Lo que se prueba acá es lo que los criterios de aceptación afirman sobre **lo que se
 * ve**, y una cosa más que no está en ninguna historia y sí en el código: que la pantalla
 * de detalle le diga a alguien que **no vuelva a emitir** un comprobante que quedó
 * esperando a ARCA. Es la única defensa de interfaz que tiene la decisión D17, y sin ella
 * el camino más natural del mundo —«no pasó nada, lo hago de nuevo»— produce dos
 * comprobantes legales por una sola venta.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarComprobantes = vi.fn();
const validarReceptor = vi.fn();
const emitirComprobante = vi.fn();
const push = vi.fn();

vi.mock("@/features/billing/api/comprobante", async () => {
  const real = await vi.importActual<typeof import("@/features/billing/api/comprobante")>(
    "@/features/billing/api/comprobante",
  );
  return {
    ...real,
    listarComprobantes: (...args: unknown[]) => listarComprobantes(...args),
    validarReceptor: (...args: unknown[]) => validarReceptor(...args),
    emitirComprobante: (...args: unknown[]) => emitirComprobante(...args),
  };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { ErrorDeComprobante, MENSAJE_SIN_RESULTADOS } from "@/features/billing";
import type { Comprobante, PuntoDeVenta, ReceptorValidado } from "@/features/billing";

const { ListadoDeComprobantes } = await import(
  "@/features/billing/components/ListadoDeComprobantes"
);
const { DetalleDeComprobante } = await import("@/features/billing/components/DetalleDeComprobante");
const { NuevaEmision } = await import("@/features/billing/components/NuevaEmision");

const AUTORIZADO: Comprobante = {
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

const RECEPTOR: ReceptorValidado = {
  nombre: "Acme SA",
  cuit: "30712345671",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  tipos_disponibles: ["FACTURA_A", "NOTA_CREDITO_A"],
};

const PUNTO: PuntoDeVenta = {
  id: "p1",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: {},
  created_at: "2026-09-07T12:00:00Z",
};

beforeAll(() => {
  vi.stubGlobal("confirm", () => true);
  vi.stubGlobal("open", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ------------------------------------------------------------------ PAN-FAC-01

describe("el listado", () => {
  it("muestra las seis columnas del criterio de aceptacion", () => {
    render(<ListadoDeComprobantes inicial={{ comprobantes: [AUTORIZADO] }} puedeEmitir />);

    // Acotado a la fila: «Factura A» y «Autorizado» tambien son opciones de los filtros,
    // y afirmar sobre el documento entero encontraria esas y no la celda.
    const fila = screen.getAllByRole("row")[1] as HTMLTableRowElement;
    const celdas = [...fila.cells].map((celda) => celda.textContent);

    expect(celdas[0]).toBe("00000123");
    expect(celdas[1]).toBe("Factura A");
    expect(celdas[2]).toBe("Acme SA");
    // El monto formateado, no recalculado: llega como texto y se muestra como texto.
    expect(celdas[3]).toMatch(/2\.420,00/);
    expect(celdas[5]).toBe("Autorizado");
  });

  it("sin resultados muestra la frase de la historia", () => {
    render(<ListadoDeComprobantes inicial={{ comprobantes: [] }} puedeEmitir />);

    expect(screen.getByText(MENSAJE_SIN_RESULTADOS)).toBeDefined();
  });

  it("filtrar por estado pregunta al servidor y no filtra el array en memoria", async () => {
    listarComprobantes.mockResolvedValue({ comprobantes: [] });
    render(<ListadoDeComprobantes inicial={{ comprobantes: [AUTORIZADO] }} puedeEmitir />);

    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "RECHAZADO" } });

    await waitFor(() => expect(listarComprobantes).toHaveBeenCalledWith({ estado: "RECHAZADO" }));
  });

  it("Solo Lectura ve y filtra sin acciones de emision", () => {
    render(<ListadoDeComprobantes inicial={{ comprobantes: [AUTORIZADO] }} puedeEmitir={false} />);

    expect(screen.getByText("Acme SA")).toBeDefined();
    expect(screen.getByLabelText("Estado")).toBeDefined();
    expect(screen.queryByText("Emitir comprobante")).toBeNull();
  });
});

// ------------------------------------------------------------------ PAN-FAC-02

describe("el detalle", () => {
  it("muestra el CAE, su vencimiento y el numero como lo imprime ARCA", () => {
    render(<DetalleDeComprobante comprobante={AUTORIZADO} puntoNumero={1} />);

    expect(screen.getByText("0001-00000123")).toBeDefined();
    expect(screen.getByText("75123456789012")).toBeDefined();
    expect(screen.getByText("Descargar PDF")).toBeDefined();
  });

  it("un comprobante en error muestra las palabras de ARCA y no ofrece el PDF", () => {
    const rechazado: Comprobante = {
      ...AUTORIZADO,
      estado: "RECHAZADO",
      cae: null,
      cae_vence_el: null,
      descargable: false,
      motivo_de_rechazo: "Error 10016: el comprobante no cumple la resolucion general vigente",
    };

    render(<DetalleDeComprobante comprobante={rechazado} puntoNumero={1} />);

    expect(screen.getByText(/Error 10016/)).toBeDefined();
    expect(screen.queryByText("Descargar PDF")).toBeNull();
  });

  it("un comprobante esperando a ARCA avisa que no se vuelva a emitir", () => {
    // **La unica defensa de interfaz que tiene D17.** Sin este aviso, el camino mas
    // natural del mundo produce dos comprobantes legales por una sola venta.
    const enVuelo: Comprobante = {
      ...AUTORIZADO,
      estado: "ENVIADO_A_ARCA",
      cae: null,
      cae_vence_el: null,
      descargable: false,
    };

    render(<DetalleDeComprobante comprobante={enVuelo} puntoNumero={1} />);

    expect(screen.getByText(/No lo emitas de nuevo/)).toBeDefined();
    expect(screen.getByText("Pendiente")).toBeDefined();
  });

  it("no ofrece editar nada: un comprobante autorizado es inmutable (RN-01)", () => {
    render(<DetalleDeComprobante comprobante={AUTORIZADO} puntoNumero={1} />);

    expect(screen.queryByRole("button", { name: /editar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /eliminar/i })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

// ------------------------------------------------------------------ PAN-FAC-03

describe("la nueva emision", () => {
  it("no ofrece nada hasta que el CUIT se valida", () => {
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    expect(screen.queryByLabelText("Tipo de comprobante")).toBeNull();
    expect(screen.queryByRole("button", { name: "Emitir" })).toBeNull();
  });

  it("un CUIT invalido muestra la frase de la historia y no habilita el resto", async () => {
    validarReceptor.mockRejectedValue(
      new ErrorDeComprobante("El CUIT ingresado no es válido. Debe contener 11 dígitos correctos."),
    );
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345670" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));

    expect(await screen.findByText(/El CUIT ingresado no es válido/)).toBeDefined();
    expect(screen.queryByLabelText("Tipo de comprobante")).toBeNull();
  });

  it("un CUIT valido completa razon social y ofrece solo los tipos legales", async () => {
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));

    await screen.findByText(/Acme SA/);
    const tipos = screen.getByLabelText("Tipo de comprobante") as HTMLSelectElement;
    const opciones = [...tipos.options].map((opcion) => opcion.value);
    // RN-01: la Factura B no esta, porque el receptor es Responsable Inscripto.
    expect(opciones).toContain("FACTURA_A");
    expect(opciones).not.toContain("FACTURA_B");
  });

  it("sin items el boton Emitir queda deshabilitado y se dice por que", async () => {
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText(/Acme SA/);

    expect(screen.getByText(/Debe agregar al menos un ítem/)).toBeDefined();
    expect((screen.getByRole("button", { name: "Emitir" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("cambiar el CUIT invalida el tipo elegido", async () => {
    // Los tipos legales dependen de la condicion de IVA del receptor. Dejar la respuesta
    // vieja en pantalla seria la pantalla mintiendo.
    validarReceptor.mockResolvedValue(RECEPTOR);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    const campo = screen.getByLabelText("CUIT del receptor");
    fireEvent.change(campo, { target: { value: "30712345671" } });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText(/Acme SA/);

    fireEvent.change(campo, { target: { value: "3071234567" } });

    expect(screen.queryByLabelText("Tipo de comprobante")).toBeNull();
  });

  it("emitir manda los montos como texto y lleva al detalle", async () => {
    validarReceptor.mockResolvedValue(RECEPTOR);
    emitirComprobante.mockResolvedValue(AUTORIZADO);
    render(<NuevaEmision puntos={[PUNTO]} clienteId="cl1" />);

    fireEvent.change(screen.getByLabelText("CUIT del receptor"), {
      target: { value: "30712345671" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Validar" }));
    await screen.findByText(/Acme SA/);

    fireEvent.change(screen.getByLabelText("Tipo de comprobante"), {
      target: { value: "FACTURA_A" },
    });
    fireEvent.change(screen.getByLabelText("Descripcion 1"), {
      target: { value: "Corte de pelo" },
    });
    fireEvent.change(screen.getByLabelText("Precio unitario"), {
      target: { value: "1000.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Emitir" }));

    await waitFor(() => expect(emitirComprobante).toHaveBeenCalled());
    const enviado = emitirComprobante.mock.calls[0]?.[0] as {
      items: { precio_unitario: unknown }[];
    };
    expect(typeof enviado.items[0]?.precio_unitario).toBe("string");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/facturacion/c1"));
  });
});
