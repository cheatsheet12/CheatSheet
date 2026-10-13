/**
 * @vitest-environment jsdom
 *
 * PAN-COB-02, la cadena de recordatorios con reintento (U7, D-U7-7).
 *
 * Un recordatorio puede estar en seis situaciones y la pantalla tiene que decir cuál: programado,
 * enviándose, esperando un reintento, enviado, fallido (con su motivo en castellano) o descartado
 * porque el cobro se cerró. Lo que se afirma es lo que se **ve**: nada de `SATURADA` ni `131047`
 * crudos delante del operador, salvo el código de lo que no sabemos traducir.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import type { DetalleDeCobroRespuesta, Recordatorio } from "@/features/payments";

const { DetalleDeCobro } = await import("@/features/payments/components/DetalleDeCobro");

const BASE: Recordatorio = {
  id: "r1",
  paso: 1,
  canal: "WHATSAPP",
  enviado_en: null,
  estado_entrega: null,
  intentos: 0,
  proximo_intento_en: null,
  ultimo_error: null,
};

function detalleCon(...recordatorios: Recordatorio[]): DetalleDeCobroRespuesta {
  return {
    id: "co1",
    cliente_id: "cl1",
    cliente_nombre: "Ana Prueba",
    cliente_cuit: "20-22222222-3",
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
    recordatorios,
    reembolsos: [],
  };
}

function mostrar(...recordatorios: Recordatorio[]): void {
  render(<DetalleDeCobro inicial={detalleCon(...recordatorios)} puedeGestionar puedeReembolsar />);
}

afterEach(cleanup);

describe("recordatorio esperando un reintento", () => {
  it("dice qué intento viene, de cuántos, y a qué hora", () => {
    // 19:00 UTC son las 16:00 en Buenos Aires.
    mostrar({
      ...BASE,
      intentos: 1,
      proximo_intento_en: "2026-10-07T19:00:00Z",
      ultimo_error: "SATURADA",
    });

    expect(screen.getByText("Reintentando · intento 2 de 3 · próximo 16:00")).toBeTruthy();
    expect(screen.getByText("Reintentando")).toBeTruthy();
    // No se confunde con uno que simplemente no salió todavía.
    expect(screen.queryByText("Programado")).toBeNull();
  });

  it("muestra el último error traducido, no la clase cruda", () => {
    mostrar({
      ...BASE,
      intentos: 2,
      proximo_intento_en: "2026-10-07T19:00:00Z",
      ultimo_error: "SATURADA",
    });

    expect(screen.getByText("Reintentando · intento 3 de 3 · próximo 16:00")).toBeTruthy();
    expect(screen.getByText("Meta estaba saturado y no aceptó el mensaje")).toBeTruthy();
    expect(screen.queryByText("SATURADA")).toBeNull();
  });
});

describe("recordatorio fallido", () => {
  it.each([
    ["131047", "Fuera de la ventana de 24 h y sin plantilla aprobada"],
    ["131026", "El número no usa WhatsApp"],
    ["131049", "Meta frenó el envío; se puede reintentar mañana"],
    ["132015", "La plantilla está pausada en Meta"],
    ["132016", "La plantilla está deshabilitada en Meta"],
    ["INCIERTO", "No sabemos si llegó: Meta no respondió"],
  ])("traduce el motivo %s", (codigo, texto) => {
    mostrar({
      ...BASE,
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "FALLIDO",
      intentos: 1,
      ultimo_error: codigo,
    });

    expect(screen.getByText("FALLIDO")).toBeTruthy();
    expect(screen.getByText(texto)).toBeTruthy();
  });

  it("muestra el código crudo de lo que no sabe traducir", () => {
    mostrar({
      ...BASE,
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "FALLIDO",
      intentos: 1,
      ultimo_error: "131050",
    });

    expect(screen.getByText("Código 131050")).toBeTruthy();
  });

  it("sin código dice que no hay detalle", () => {
    mostrar({
      ...BASE,
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "FALLIDO",
      intentos: 1,
    });

    expect(screen.getByText("Sin detalle")).toBeTruthy();
  });
});

describe("recordatorio que no salió", () => {
  it("descartado porque el cobro se cerró: dice por qué no se envió", () => {
    mostrar({ ...BASE, intentos: 1, ultimo_error: "COBRO_CERRADO" });

    expect(screen.getByText("No se envió: el cobro se cerró")).toBeTruthy();
    expect(screen.queryByText("Programado")).toBeNull();
  });

  it("con un envío en curso dice «Enviando» y no «Programado»", () => {
    mostrar({ ...BASE, intentos: 1 });

    expect(screen.getByText("Enviando")).toBeTruthy();
    expect(screen.queryByText("Programado")).toBeNull();
  });

  it("sin ningún intento sigue diciendo «Programado»", () => {
    mostrar(BASE);

    expect(screen.getByText("Programado")).toBeTruthy();
  });

  it("uno enviado no muestra motivo ni reintento", () => {
    mostrar({
      ...BASE,
      enviado_en: "2026-09-23T09:00:00Z",
      estado_entrega: "ENVIADO",
      intentos: 1,
    });

    expect(screen.getByText("ENVIADO")).toBeTruthy();
    expect(screen.queryByText(/Reintentando/)).toBeNull();
    expect(screen.queryByText("Sin detalle")).toBeNull();
  });
});
