/**
 * @vitest-environment jsdom
 *
 * El estado de entrega de cada mensaje saliente del hilo, en castellano (U7, D-U7-7).
 *
 * Antes la pantalla imprimía el enum (`ENVIADO`); ahora dice «Enviado», «Entregado», «Leído» y, si el
 * mensaje falló, **por qué** debajo (un aviso de turno `FALLIDO` es lo que le dice al operador que hay
 * que llamar al cliente). El motivo viene como código de Meta o clase corta y se traduce acá.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LineaDeTiempo } from "../LineaDeTiempo";
import type { Mensaje } from "@/features/conversational";

const SALIENTE: Mensaje = {
  id: "m1",
  direccion: "SALIENTE",
  tipo_contenido: "TEXTO",
  contenido: "Tu turno del 15/10 fue cancelado.",
  momento: "2026-10-07T18:00:00+00:00",
  intencion: null,
  estado_entrega: "ENVIADO",
  origen: "SISTEMA",
  motivo_de_falla: null,
};

afterEach(cleanup);

describe("estado de entrega en el hilo", () => {
  it.each([
    ["ENVIADO", "Enviado"],
    ["ENTREGADO", "Entregado"],
    ["LEIDO", "Leído"],
  ])("%s se lee «%s»", (estado, etiqueta) => {
    render(<LineaDeTiempo mensajes={[{ ...SALIENTE, estado_entrega: estado }]} />);

    expect(screen.getByText(etiqueta)).toBeTruthy();
    expect(screen.queryByText(estado)).toBeNull();
  });

  it("un aviso del sistema fallido dice que no se pudo enviar y por qué", () => {
    render(
      <LineaDeTiempo
        mensajes={[{ ...SALIENTE, estado_entrega: "FALLIDO", motivo_de_falla: "131047" }]}
      />,
    );

    expect(screen.getByText("No se pudo enviar")).toBeTruthy();
    expect(screen.getByText("Fuera de la ventana de 24 h y sin plantilla aprobada")).toBeTruthy();
    expect(screen.queryByText("131047")).toBeNull();
  });

  it("muestra el código crudo de un motivo que no conoce", () => {
    render(
      <LineaDeTiempo
        mensajes={[{ ...SALIENTE, estado_entrega: "FALLIDO", motivo_de_falla: "131050" }]}
      />,
    );

    expect(screen.getByText("Código 131050")).toBeTruthy();
  });

  it("un fallido sin motivo guardado dice «Sin detalle»", () => {
    render(<LineaDeTiempo mensajes={[{ ...SALIENTE, estado_entrega: "FALLIDO" }]} />);

    expect(screen.getByText("Sin detalle")).toBeTruthy();
  });

  it("un mensaje enviado no muestra ningún motivo", () => {
    render(<LineaDeTiempo mensajes={[SALIENTE]} />);

    expect(screen.queryByText("Sin detalle")).toBeNull();
  });

  it("un mensaje del cliente no lleva estado de entrega", () => {
    render(
      <LineaDeTiempo
        mensajes={[{ ...SALIENTE, direccion: "ENTRANTE", estado_entrega: null, origen: null }]}
      />,
    );

    expect(screen.queryByText("Enviado")).toBeNull();
  });

  it("el aviso del sistema se distingue como «Sistema»", () => {
    render(<LineaDeTiempo mensajes={[SALIENTE]} />);

    expect(screen.getByText(/Sistema ·/)).toBeTruthy();
  });
});
