/**
 * @vitest-environment jsdom
 *
 * El rediseño de «Conversaciones» (PAN-WA-01): lo que se agregó a la bandeja y al hilo sin
 * tocar su lógica — búsqueda, hilo seleccionado, estado vacío con contexto, separadores de día,
 * marcas de agente y operador, y los ayudantes de presentación.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BandejaDeConversaciones } from "../BandejaDeConversaciones";
import { HiloDeConversacion } from "../HiloDeConversacion";
import { CANTIDAD_DE_TONOS, agruparPorDia, horaRelativa, rotuloDeDia, tonoDe } from "../vista";
import type { Conversacion, Mensaje } from "@/features/conversational";

const ESCALADA: Conversacion = {
  id: "c1",
  cliente_id: "cl1",
  estado: "ACTIVA",
  ultimo_mensaje_en: "2026-09-08T18:00:00+00:00",
  esta_escalada: true,
  escalamiento_id: "e1",
  motivo: "El cliente pidió hablar con una persona",
  estado_escalamiento: "ABIERTO",
  usuario_asignado_id: null,
};

const DEL_AGENTE: Conversacion = {
  ...ESCALADA,
  id: "c2",
  cliente_id: "cl2",
  esta_escalada: false,
  escalamiento_id: null,
  motivo: null,
  estado_escalamiento: null,
};

const mensaje = (id: string, momento: string, extra: Partial<Mensaje> = {}): Mensaje => ({
  id,
  direccion: "ENTRANTE",
  tipo_contenido: "TEXTO",
  contenido: `mensaje ${id}`,
  momento,
  intencion: null,
  estado_entrega: null,
  origen: null,
  motivo_de_falla: null,
  ...extra,
});

afterEach(cleanup);

describe("bandeja rediseñada", () => {
  it("cuenta los hilos y los que esperan como etiquetas", () => {
    render(
      <BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA, DEL_AGENTE] }} puedeAtender />,
    );

    expect(screen.getByText("2 hilos")).toBeTruthy();
    expect(screen.getByText("1 espera")).toBeTruthy();
  });

  it("filtra la lista con la búsqueda y avisa cuando nada coincide", () => {
    render(
      <BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA, DEL_AGENTE] }} puedeAtender />,
    );
    const lista = (): HTMLElement => screen.getByRole("list", { name: "Conversaciones" });
    expect(within(lista()).getAllByRole("link")).toHaveLength(2);

    const buscador = screen.getByLabelText("Buscar conversaciones");
    fireEvent.change(buscador, { target: { value: "persona" } });
    expect(within(lista()).getAllByRole("link")).toHaveLength(1);

    fireEvent.change(buscador, { target: { value: "zzz" } });
    expect(screen.getByText("Ninguna conversación coincide con tu búsqueda.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar todas" }));
    expect(within(lista()).getAllByRole("link")).toHaveLength(2);
  });

  it("resalta la conversación abierta y muestra el hilo en el panel derecho", () => {
    render(
      <BandejaDeConversaciones
        inicial={{ conversaciones: [ESCALADA, DEL_AGENTE] }}
        puedeAtender
        seleccionadaId="c2"
        soloEscaladasInicial={false}
      >
        <p>el hilo abierto</p>
      </BandejaDeConversaciones>,
    );

    const activos = screen.getAllByRole("link").filter((a) => a.getAttribute("aria-current"));
    expect(activos).toHaveLength(1);
    expect(activos[0]?.getAttribute("href")).toBe("/conversaciones/c2");
    expect(screen.getByText("el hilo abierto")).toBeTruthy();
    expect(screen.queryByText("Elegí una conversación")).toBeNull();
  });

  it("sin hilo elegido invita a elegir uno, y el vacío trae una frase de contexto", () => {
    render(<BandejaDeConversaciones inicial={{ conversaciones: [] }} puedeAtender />);

    expect(screen.getByText("Elegí una conversación")).toBeTruthy();
    expect(screen.getByText(/aparece acá/)).toBeTruthy();
  });

  it("las flechas recorren los renglones", () => {
    render(
      <BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA, DEL_AGENTE] }} puedeAtender />,
    );
    const enlaces = screen.getAllByRole("link");
    enlaces[0]?.focus();

    fireEvent.keyDown(screen.getByRole("list", { name: "Conversaciones" }), { key: "ArrowDown" });

    expect(document.activeElement).toBe(enlaces[1]);
  });
});

describe("hilo rediseñado", () => {
  it("separa los mensajes por día y marca al agente y al operador", () => {
    render(
      <HiloDeConversacion
        inicial={{
          ...ESCALADA,
          estado_escalamiento: "ASIGNADO",
          mensajes: [
            mensaje("1", "2026-09-07T12:00:00+00:00"),
            mensaje("2", "2026-09-08T12:00:00+00:00", { direccion: "SALIENTE", origen: "AGENTE" }),
            mensaje("3", "2026-09-08T12:05:00+00:00", {
              direccion: "SALIENTE",
              origen: "OPERADOR",
            }),
          ],
        }}
        puedeAtender
      />,
    );

    expect(document.querySelectorAll(".cv-dia")).toHaveLength(2);
    expect(document.querySelector(".cv-msg--agente .cv-msg__meta svg")).not.toBeNull();
    expect(document.querySelector(".cv-msg--operador .cv-msg__meta svg")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Volver" }).getAttribute("href")).toBe(
      "/conversaciones",
    );
  });

  it("el botón de enviar queda apagado con el campo vacío", () => {
    render(
      <HiloDeConversacion
        inicial={{ ...ESCALADA, estado_escalamiento: "ASIGNADO", mensajes: [] }}
        puedeAtender
      />,
    );

    expect(screen.getByText("Este hilo todavía no tiene mensajes.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enviar" }).hasAttribute("disabled")).toBe(true);
  });
});

describe("ayudantes de presentación", () => {
  const AHORA = new Date(2026, 8, 10, 15, 0, 0);

  it("el tono de un cliente es estable y está dentro de la paleta", () => {
    expect(tonoDe("cliente-1")).toBe(tonoDe("cliente-1"));
    expect(tonoDe("cliente-1")).toBeLessThan(CANTIDAD_DE_TONOS);
    expect(tonoDe("")).toBe(0);
  });

  it("dice la hora relativa en español", () => {
    expect(horaRelativa(null)).toBe("—");
    expect(horaRelativa("no es una fecha")).toBe("—");
    expect(horaRelativa(new Date(2026, 8, 10, 14, 59, 40).toISOString(), AHORA)).toBe("ahora");
    expect(horaRelativa(new Date(2026, 8, 10, 14, 30).toISOString(), AHORA)).toBe("hace 30 min");
    expect(horaRelativa(new Date(2026, 8, 10, 11, 0).toISOString(), AHORA)).toBe("hace 4 h");
    expect(horaRelativa(new Date(2026, 8, 9, 20, 0).toISOString(), AHORA)).toBe("ayer");
    expect(horaRelativa(new Date(2026, 8, 1, 9, 0).toISOString(), AHORA)).toContain("sep");
  });

  it("rotula el día y agrupa lo consecutivo", () => {
    expect(rotuloDeDia(new Date(2026, 8, 10, 9).toISOString(), AHORA)).toBe("Hoy");
    expect(rotuloDeDia(new Date(2026, 8, 9, 9).toISOString(), AHORA)).toBe("Ayer");
    expect(rotuloDeDia(new Date(2026, 8, 1, 9).toISOString(), AHORA)).toBe("1 de septiembre");

    const grupos = agruparPorDia(
      [
        mensaje("a", new Date(2026, 8, 9, 9).toISOString()),
        mensaje("b", new Date(2026, 8, 9, 10).toISOString()),
        mensaje("c", new Date(2026, 8, 10, 9).toISOString()),
      ],
      AHORA,
    );
    expect(grupos.map((grupo) => grupo.mensajes.length)).toEqual([2, 1]);
  });
});
