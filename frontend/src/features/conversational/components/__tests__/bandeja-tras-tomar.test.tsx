/**
 * @vitest-environment jsdom
 *
 * La bandeja se actualiza sola cuando el operador actúa sobre el hilo abierto (HU-E9-01).
 *
 * El hilo y la bandeja son dos componentes hermanos que muestran el mismo dato —el estado del
 * escalamiento—, y la acción del hilo sólo refrescaba el suyo: la izquierda seguía diciendo
 * «Espera un asesor» y «2 esperan» hasta recargar la página. Cada caso monta **la misma
 * composición que la página** (la bandeja con el hilo como `children`) y comprueba lo que se ve
 * a la izquierda, no sólo que se haya llamado al backend.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarConversaciones = vi.fn();
const verConversacion = vi.fn();
const tomarEscalamiento = vi.fn();
const cerrarEscalamiento = vi.fn();
const responder = vi.fn();

vi.mock("@/features/conversational/api/conversacion", async () => {
  const real = await vi.importActual<typeof import("@/features/conversational/api/conversacion")>(
    "@/features/conversational/api/conversacion",
  );
  return {
    ...real,
    listarConversaciones: (...args: unknown[]) => listarConversaciones(...args),
    verConversacion: (...args: unknown[]) => verConversacion(...args),
    tomarEscalamiento: (...args: unknown[]) => tomarEscalamiento(...args),
    cerrarEscalamiento: (...args: unknown[]) => cerrarEscalamiento(...args),
    responder: (...args: unknown[]) => responder(...args),
  };
});

import { ErrorDeConversacion } from "@/features/conversational";
import type { Conversacion, DetalleDeConversacion } from "@/features/conversational";

const { BandejaDeConversaciones } = await import(
  "@/features/conversational/components/BandejaDeConversaciones"
);
const { HiloDeConversacion } = await import(
  "@/features/conversational/components/HiloDeConversacion"
);

const ABIERTA: Conversacion = {
  id: "c1",
  cliente_id: "cl1",
  estado: "ACTIVA",
  ultimo_mensaje_en: "2026-09-08T18:00:00+00:00",
  esta_escalada: true,
  escalamiento_id: "e1",
  motivo: "Pidió hablar con una persona",
  estado_escalamiento: "ABIERTO",
  usuario_asignado_id: null,
};

const OTRA_ABIERTA: Conversacion = {
  ...ABIERTA,
  id: "c2",
  cliente_id: "cl2",
  escalamiento_id: "e2",
  motivo: "Consulta por un cobro",
};

const TOMADA: Conversacion = { ...ABIERTA, estado_escalamiento: "ASIGNADO" };

const CERRADA: Conversacion = {
  ...ABIERTA,
  esta_escalada: false,
  escalamiento_id: null,
  motivo: null,
  estado_escalamiento: null,
};

function detalle(base: Conversacion): DetalleDeConversacion {
  return { ...base, mensajes: [] };
}

/** La composición de `conversaciones/[conversacionId]/page.tsx`: bandeja con el hilo adentro. */
function montarComoLaPagina(hilo: Conversacion): void {
  render(
    <BandejaDeConversaciones
      inicial={{ conversaciones: [ABIERTA, OTRA_ABIERTA] }}
      puedeAtender
      seleccionadaId="c1"
      soloEscaladasInicial={false}
    >
      <HiloDeConversacion key="c1" inicial={detalle(hilo)} puedeAtender />
    </BandejaDeConversaciones>,
  );
}

function lista(): ReturnType<typeof within> {
  return within(screen.getByRole("list", { name: "Conversaciones" }));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PAN-WA-01 — la bandeja tras actuar sobre el hilo", () => {
  it("al tomar la conversación, el renglón pasa a «En atención» y el contador baja", async () => {
    tomarEscalamiento.mockResolvedValue(undefined);
    verConversacion.mockResolvedValue(detalle(TOMADA));
    listarConversaciones.mockResolvedValue({ conversaciones: [TOMADA, OTRA_ABIERTA] });
    montarComoLaPagina(ABIERTA);
    expect(screen.getByText("2 esperan")).toBeTruthy();
    expect(lista().queryByText("En atención")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Tomar la conversación" }));

    await waitFor(() => {
      expect(lista().getByText("En atención")).toBeTruthy();
    });
    expect(screen.getByText("1 espera")).toBeTruthy();
    expect(screen.queryByText("2 esperan")).toBeNull();
    // Se vuelve a preguntar al backend con el filtro vigente: la bandeja no deriva el estado.
    expect(listarConversaciones).toHaveBeenCalledWith(false);
  });

  it("al dar por finalizada, también se recarga la bandeja", async () => {
    cerrarEscalamiento.mockResolvedValue(undefined);
    verConversacion.mockResolvedValue(detalle(CERRADA));
    listarConversaciones.mockResolvedValue({ conversaciones: [CERRADA, OTRA_ABIERTA] });
    montarComoLaPagina(TOMADA);

    fireEvent.click(screen.getByRole("button", { name: "Dar por finalizada" }));

    await waitFor(() => {
      expect(lista().getByText("La atiende el agente")).toBeTruthy();
    });
    expect(listarConversaciones).toHaveBeenCalledWith(false);
  });

  it("si la recarga falla, el hilo queda actualizado y la bandeja lo dice", async () => {
    tomarEscalamiento.mockResolvedValue(undefined);
    verConversacion.mockResolvedValue(detalle(TOMADA));
    listarConversaciones.mockRejectedValue(new Error("sin red"));
    montarComoLaPagina(ABIERTA);

    fireEvent.click(screen.getByRole("button", { name: "Tomar la conversación" }));

    await waitFor(() => {
      expect(screen.getByText("No se pudo actualizar la bandeja.")).toBeTruthy();
    });
    const hiloAbierto = within(screen.getByRole("region", { name: "Conversación" }));
    expect(hiloAbierto.getByText("En atención")).toBeTruthy();
    expect(hiloAbierto.queryByRole("button", { name: "Tomar la conversación" })).toBeNull();
  });

  it("si la toma falla, la bandeja no se recarga", async () => {
    tomarEscalamiento.mockRejectedValue(new ErrorDeConversacion("Otro operador ya la tomó."));
    montarComoLaPagina(ABIERTA);

    fireEvent.click(screen.getByRole("button", { name: "Tomar la conversación" }));

    await waitFor(() => {
      expect(screen.getByText("Otro operador ya la tomó.")).toBeTruthy();
    });
    expect(listarConversaciones).not.toHaveBeenCalled();
    expect(screen.getByText("2 esperan")).toBeTruthy();
  });
});
