/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-NOT ante Meta (U6, caso 30): el badge por estado, el motivo traducido, «Enviar a
 * revisión», el bloqueo de la edición y lo que se dice cuando Meta refuta o no responde.
 *
 * Aparte de `pantallas.test.tsx`, que ya pasaba de 400 líneas antes de esta unidad.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listarPlantillas = vi.fn();
const editarPlantilla = vi.fn();
const enviarARevision = vi.fn();

vi.mock("@/features/conversational/api/faq", async () => {
  const real = await vi.importActual<typeof import("@/features/conversational/api/faq")>(
    "@/features/conversational/api/faq",
  );
  return {
    ...real,
    listarPlantillas: (...args: unknown[]) => listarPlantillas(...args),
    editarPlantilla: (...args: unknown[]) => editarPlantilla(...args),
    enviarARevision: (...args: unknown[]) => enviarARevision(...args),
  };
});

import { ErrorDeFaq, MENSAJE_BORDE_CON_VARIABLE } from "@/features/conversational";
import type { Plantilla } from "@/features/conversational";

const { PlantillasDeNotificacion } = await import(
  "@/features/conversational/components/PlantillasDeNotificacion"
);

const PLANTILLA: Plantilla = {
  id: "p1",
  codigo: "recordatorio_de_turno",
  canal: "WHATSAPP",
  idioma: "es_AR",
  cuerpo: "Hola {{nombre}}, te esperamos el {{fecha}}.",
  estado_aprobacion: "APROBADA",
  variables: ["nombre", "servicio", "fecha", "hora"],
  puede_usarse: true,
  motivo_meta: null,
  detalle_meta: null,
  categoria_en_meta: null,
  editable_desde: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PAN-CFG-NOT — el estado ante Meta (U6)", () => {
  const SIN_ENVIAR: Plantilla = {
    ...PLANTILLA,
    id: "p3",
    estado_aprobacion: "SIN_ENVIAR",
    puede_usarse: false,
  };
  const RECHAZADA: Plantilla = {
    ...PLANTILLA,
    id: "p4",
    estado_aprobacion: "RECHAZADA",
    puede_usarse: false,
    motivo_meta: "PROMOTIONAL",
    detalle_meta: "Quitá el tono comercial del texto.",
  };

  function pantalla(plantilla: Plantilla, puedeEditar = true): void {
    render(
      <PlantillasDeNotificacion inicial={{ plantillas: [plantilla] }} puedeEditar={puedeEditar} />,
    );
  }

  it.each([
    ["SIN_ENVIAR", "Sin enviar a Meta"],
    ["PENDIENTE", "En revisión de Meta"],
    ["APROBADA", "Aprobada"],
    ["RECHAZADA", "Rechazada"],
    ["PAUSADA", "Pausada por Meta"],
    ["DESHABILITADA", "Deshabilitada por Meta"],
  ] as const)("%s se muestra como «%s»", (estado, etiqueta) => {
    pantalla({ ...PLANTILLA, estado_aprobacion: estado, puede_usarse: estado === "APROBADA" });

    expect(screen.getByText(etiqueta)).toBeTruthy();
  });

  it("traduce el motivo del rechazo y muestra el texto literal de Meta", () => {
    pantalla(RECHAZADA);

    expect(
      screen.getByText("Meta lo considera promocional: no corresponde a Utilidad"),
    ).toBeTruthy();
    expect(screen.getByText("Quitá el tono comercial del texto.")).toBeTruthy();
  });

  it("avisa cuando Meta la recategorizó como marketing", () => {
    pantalla({ ...PLANTILLA, categoria_en_meta: "MARKETING" });

    expect(screen.getByText(/Meta la clasificó como Marketing/)).toBeTruthy();
  });

  it.each([["SIN_ENVIAR"], ["RECHAZADA"]] as const)(
    "«Enviar a revisión» aparece en %s y reenvía sin tocar el texto",
    async (estado) => {
      enviarARevision.mockResolvedValue(SIN_ENVIAR);
      listarPlantillas.mockResolvedValue({ plantillas: [PLANTILLA] });
      pantalla(estado === "SIN_ENVIAR" ? SIN_ENVIAR : RECHAZADA);

      fireEvent.click(screen.getByRole("button", { name: "Enviar a revisión" }));

      await waitFor(() => {
        expect(enviarARevision).toHaveBeenCalledWith(estado === "SIN_ENVIAR" ? "p3" : "p4");
      });
      expect(editarPlantilla).not.toHaveBeenCalled();
    },
  );

  it.each([["APROBADA"], ["PENDIENTE"], ["PAUSADA"], ["DESHABILITADA"]] as const)(
    "«Enviar a revisión» no aparece en %s",
    (estado) => {
      pantalla({ ...PLANTILLA, estado_aprobacion: estado });

      expect(screen.queryByRole("button", { name: "Enviar a revisión" })).toBeNull();
    },
  );

  it("«Enviar a revisión» es solo del Administrador", () => {
    pantalla(SIN_ENVIAR, false);

    expect(screen.queryByRole("button", { name: "Enviar a revisión" })).toBeNull();
  });

  it("muestra el texto de Meta cuando reenviar falla", async () => {
    enviarARevision.mockRejectedValue(new ErrorDeFaq("Texto de Meta sobre el cuerpo"));
    pantalla(SIN_ENVIAR);

    fireEvent.click(screen.getByRole("button", { name: "Enviar a revisión" }));

    expect(await screen.findByText("Texto de Meta sobre el cuerpo")).toBeTruthy();
  });

  it("bloquea la edición de una plantilla en revisión y explica por qué", () => {
    pantalla({ ...PLANTILLA, estado_aprobacion: "PENDIENTE", puede_usarse: false });

    const boton = screen.getByRole("button", { name: "Editar texto" });
    expect(boton.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Meta está revisando esta plantilla/)).toBeTruthy();
  });

  it("bloquea la edición de una aprobada dentro de las 24 horas y dice desde cuándo", () => {
    const enUnaHora = new Date(Date.now() + 3_600_000).toISOString();
    pantalla({ ...PLANTILLA, editable_desde: enUnaHora });

    expect(screen.getByRole("button", { name: "Editar texto" }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(screen.getByText(/una vez cada 24 horas/)).toBeTruthy();
  });

  it("deja editar una aprobada cuando ya pasaron las 24 horas", () => {
    const haceUnaHora = new Date(Date.now() - 3_600_000).toISOString();
    pantalla({ ...PLANTILLA, editable_desde: haceUnaHora });

    expect(screen.getByRole("button", { name: "Editar texto" }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("avisa y no deja guardar un texto de WhatsApp que empieza con una variable", () => {
    pantalla(PLANTILLA);
    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));

    fireEvent.change(screen.getByLabelText("Texto del mensaje"), {
      target: { value: "{{nombre}}, te esperamos." },
    });

    expect(screen.getByText(MENSAJE_BORDE_CON_VARIABLE)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar" }).hasAttribute("disabled")).toBe(true);
  });

  it("muestra el texto de Meta cuando guardar es refutado", async () => {
    editarPlantilla.mockRejectedValue(new ErrorDeFaq("Meta: el texto es promocional"));
    pantalla(PLANTILLA);
    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));

    fireEvent.change(screen.getByLabelText("Texto del mensaje"), {
      target: { value: "Hola {{nombre}}, comprá ya." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Meta: el texto es promocional")).toBeTruthy();
  });
});
