/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-NOT (U8, caso 34): la advertencia del recordatorio de turno aparece si la plantilla no
 * está aprobada en Meta y no aparece si lo está.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AdvertenciaDeRecordatorio,
  MENSAJE_RECORDATORIO_SIN_APROBAR,
} from "@/features/conversational";
import type { Plantilla } from "@/features/conversational";

const RECORDATORIO: Plantilla = {
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

afterEach(cleanup);

describe("PAN-CFG-NOT — advertencia del recordatorio de turno", () => {
  it("no aparece si la plantilla está aprobada", () => {
    render(<AdvertenciaDeRecordatorio plantillas={[RECORDATORIO]} />);

    expect(screen.queryByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeNull();
  });

  it.each([["SIN_ENVIAR"], ["PENDIENTE"], ["RECHAZADA"], ["PAUSADA"], ["DESHABILITADA"]] as const)(
    "aparece si la plantilla está %s",
    (estado) => {
      render(
        <AdvertenciaDeRecordatorio
          plantillas={[{ ...RECORDATORIO, estado_aprobacion: estado, puede_usarse: false }]}
        />,
      );

      expect(screen.getByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeTruthy();
    },
  );

  it("aparece si la plantilla no está en el listado", () => {
    render(<AdvertenciaDeRecordatorio plantillas={[{ ...RECORDATORIO, codigo: "otra" }]} />);

    expect(screen.getByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeTruthy();
  });

  it("no aparece si los recordatorios están apagados en la agenda", () => {
    render(
      <AdvertenciaDeRecordatorio
        plantillas={[{ ...RECORDATORIO, estado_aprobacion: "PENDIENTE", puede_usarse: false }]}
        recordatoriosActivos={false}
      />,
    );

    expect(screen.queryByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeNull();
  });

  it("no aparece si WhatsApp no está conectado", () => {
    render(
      <AdvertenciaDeRecordatorio
        plantillas={[{ ...RECORDATORIO, estado_aprobacion: "PENDIENTE", puede_usarse: false }]}
        whatsappConectado={false}
      />,
    );

    expect(screen.queryByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeNull();
  });

  it("aparece si los recordatorios están activos y WhatsApp conectado", () => {
    render(
      <AdvertenciaDeRecordatorio
        plantillas={[{ ...RECORDATORIO, estado_aprobacion: "RECHAZADA", puede_usarse: false }]}
        recordatoriosActivos
        whatsappConectado
      />,
    );

    expect(screen.getByText(MENSAJE_RECORDATORIO_SIN_APROBAR)).toBeTruthy();
  });
});
