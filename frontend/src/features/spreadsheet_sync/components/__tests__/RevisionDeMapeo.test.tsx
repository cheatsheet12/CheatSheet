/**
 * @vitest-environment jsdom
 *
 * PAN-ING-02 (HU-E3-01, HU-E3-02).
 *
 * Tres criterios de aceptación se comprueban acá y no en el cliente de API, porque son
 * sobre lo que el usuario **ve**:
 *
 * - las cuatro columnas de la revisión, incluido el ejemplo de dato;
 * - que «Confirmar y procesar» esté deshabilitado con obligatorias sin asignar, con el
 *   texto exacto de la historia;
 * - que corregir una asignación actualice la vista.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const corregirMapeo = vi.fn();
const confirmarMapeo = vi.fn();
const procesarPlanilla = vi.fn();
const push = vi.fn();

// La pantalla navega a `Cargas recientes` después de encolar el procesamiento, y jsdom no
// monta el router de la app. Mismo doble que usan las pruebas de página del panel.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

vi.mock("@/features/spreadsheet_sync/api/planilla", async () => {
  const real = await vi.importActual<typeof import("@/features/spreadsheet_sync/api/planilla")>(
    "@/features/spreadsheet_sync/api/planilla",
  );
  return {
    ...real,
    corregirMapeo: (...args: unknown[]) => corregirMapeo(...args),
    confirmarMapeo: (...args: unknown[]) => confirmarMapeo(...args),
    procesarPlanilla: (...args: unknown[]) => procesarPlanilla(...args),
  };
});

import type { Mapeo } from "@/features/spreadsheet_sync";
import { MENSAJE_FALTAN_OBLIGATORIAS } from "@/features/spreadsheet_sync";

const { RevisionDeMapeo } = await import("@/features/spreadsheet_sync/components/RevisionDeMapeo");

const INCOMPLETO: Mapeo = {
  id: "m1",
  estado: "BORRADOR",
  version: 1,
  entradas: [
    {
      columna_origen: "Razon Soc.",
      atributo_destino: null,
      confianza: "BAJA",
      ejemplo: "Panaderia Dona Rosa",
      corregida_a_mano: false,
    },
    {
      columna_origen: "CUIT",
      atributo_destino: "cuit",
      confianza: "ALTA",
      ejemplo: "30712345671",
      corregida_a_mano: false,
    },
  ],
  faltantes: ["nombre"],
  puede_confirmarse: false,
  propuesto_por_el_modelo: true,
};

const COMPLETO: Mapeo = {
  ...INCOMPLETO,
  entradas: [
    { ...INCOMPLETO.entradas[0]!, atributo_destino: "nombre", corregida_a_mano: true },
    INCOMPLETO.entradas[1]!,
  ],
  faltantes: [],
  puede_confirmarse: true,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RevisionDeMapeo", () => {
  it("muestra las cuatro cosas que pide el criterio de HU-E3-02", () => {
    render(<RevisionDeMapeo vinculoId="v-1" inicial={INCOMPLETO} puedeEditar />);

    expect(screen.getByText("Razon Soc.")).toBeTruthy();
    // El ejemplo: leido de la planilla, mostrado aca, nunca enviado al modelo (D12).
    expect(screen.getByText("Panaderia Dona Rosa")).toBeTruthy();
    expect(screen.getByText("30712345671")).toBeTruthy();
    // El nivel se muestra con su etiqueta legible —«Baja»— y no con el valor del enum: lo
    // que la pantalla dice es cuánta confianza tuvo la propuesta, no cómo se guarda.
    expect(screen.getByText("Baja")).toBeTruthy();
    expect(screen.getByLabelText("Campo del sistema para CUIT")).toBeTruthy();
  });

  it("bloquea confirmar con el texto exacto de la historia", () => {
    render(<RevisionDeMapeo vinculoId="v-1" inicial={INCOMPLETO} puedeEditar />);

    expect(screen.getByText(new RegExp(MENSAJE_FALTAN_OBLIGATORIAS))).toBeTruthy();
    const boton = screen.getByText("Confirmar y procesar").closest("button");
    expect(boton?.disabled).toBe(true);
  });

  it("habilita confirmar cuando ya no falta ninguna obligatoria", () => {
    render(<RevisionDeMapeo vinculoId="v-1" inicial={COMPLETO} puedeEditar />);

    const boton = screen.getByText("Confirmar y procesar").closest("button");
    expect(boton?.disabled).toBe(false);
  });

  it("corregir una asignacion actualiza la vista", async () => {
    corregirMapeo.mockResolvedValue(COMPLETO);
    render(<RevisionDeMapeo vinculoId="v-1" inicial={INCOMPLETO} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Campo del sistema para Razon Soc."), {
      target: { value: "nombre" },
    });

    await waitFor(() => {
      expect(corregirMapeo).toHaveBeenCalledWith("m1", "Razon Soc.", "nombre");
      expect(screen.getByText("Corregida")).toBeTruthy();
    });
  });

  it("avisa cuando el modelo no pudo proponer nada", () => {
    render(
      <RevisionDeMapeo
        vinculoId="v-1"
        inicial={{ ...INCOMPLETO, propuesto_por_el_modelo: false }}
        puedeEditar
      />,
    );

    // «No pudimos proponerlo» y «ya lo teniamos» son cosas distintas para alguien mirando
    // una tabla llena de «Sin asignar».
    expect(screen.getByText(/No pudimos proponerte un mapeo automatico/)).toBeTruthy();
  });

  it("un rol que no edita ve el mapeo sin controles ni boton", () => {
    render(<RevisionDeMapeo vinculoId="v-1" inicial={COMPLETO} puedeEditar={false} />);

    expect(screen.queryByLabelText("Campo del sistema para CUIT")).toBeNull();
    expect(screen.queryByText("Confirmar y procesar")).toBeNull();
    // Ve el mapeo entero, en texto. «CUIT» aparece dos veces —la columna de la planilla y
    // la etiqueta del campo asignado— y las dos son correctas.
    expect(screen.getAllByText("CUIT").length).toBe(2);
    expect(screen.getByText("Nombre / Razón social")).toBeTruthy();
  });

  it("confirmar avisa que ya se puede procesar", async () => {
    confirmarMapeo.mockResolvedValue({ ...COMPLETO, estado: "VALIDADO" });
    render(<RevisionDeMapeo vinculoId="v-1" inicial={COMPLETO} puedeEditar />);

    fireEvent.click(screen.getByText("Confirmar y procesar"));

    await waitFor(() => {
      expect(screen.getByText(/Ya podes procesar la planilla/)).toBeTruthy();
    });
  });

  it("y ofrece hacerlo, en vez de mandar a buscar el boton a otra pantalla", async () => {
    // El aviso decía «ya podés procesar la planilla» y la pantalla no ofrecía ninguna
    // forma de hacerlo: había que volver a Ingesta y encontrar la fila. Una pantalla que
    // dice qué sigue tiene que ofrecer qué sigue.
    procesarPlanilla.mockResolvedValue(undefined);
    render(
      <RevisionDeMapeo vinculoId="v-1" inicial={{ ...COMPLETO, estado: "VALIDADO" }} puedeEditar />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Procesar la planilla" }));

    await waitFor(() => {
      expect(procesarPlanilla).toHaveBeenCalledWith("v-1");
    });
    // Procesar contesta 202 y el trabajo lo hace un worker: el resultado se ve en
    // `Cargas recientes`, no acá.
    expect(push).toHaveBeenCalledWith("/ingesta");
  });

  it("un mapeo sin confirmar todavia no ofrece procesar", () => {
    render(<RevisionDeMapeo vinculoId="v-1" inicial={COMPLETO} puedeEditar />);

    expect(screen.queryByRole("button", { name: "Procesar la planilla" })).toBeNull();
  });
});
