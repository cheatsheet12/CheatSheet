/**
 * @vitest-environment jsdom
 *
 * Las cuatro pantallas del canal conversacional (HU-E9-01, HU-E9-02, HU-E9-04, HU-E11-02).
 *
 * Lo que se prueba acá es lo que los criterios afirman sobre **lo que se ve**, más cuatro cosas
 * que no están en ninguna historia y sí en el código:
 *
 * - **El campo de respuesta no existe hasta tomar el escalamiento.** El backend lo rechaza
 *   igual, pero un operador que escribe un mensaje y recibe un 422 después de redactarlo
 *   pierde el mensaje y el tiempo. Y el motivo por el que no está se dice.
 * - **Los mensajes del operador se distinguen de los del agente** con la marca que trae el
 *   backend, no adivinando por el momento del escalamiento.
 * - **Una FAQ sin indexar lo dice.** Es la diferencia entre «el agente todavía no la usa» y
 *   «el agente la ignora y no sé por qué».
 * - **Una variable inválida se avisa mientras se escribe**, con la frase de la historia — y el
 *   botón queda gris, que es lo que evita el 422.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

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

const listarFaqs = vi.fn();
const crearFaq = vi.fn();
const eliminarFaq = vi.fn();
const verUsoDeFaq = vi.fn();
const listarPlantillas = vi.fn();
const editarPlantilla = vi.fn();
const enviarARevision = vi.fn();

vi.mock("@/features/conversational/api/faq", async () => {
  const real = await vi.importActual<typeof import("@/features/conversational/api/faq")>(
    "@/features/conversational/api/faq",
  );
  return {
    ...real,
    listarFaqs: (...args: unknown[]) => listarFaqs(...args),
    crearFaq: (...args: unknown[]) => crearFaq(...args),
    eliminarFaq: (...args: unknown[]) => eliminarFaq(...args),
    verUsoDeFaq: (...args: unknown[]) => verUsoDeFaq(...args),
    listarPlantillas: (...args: unknown[]) => listarPlantillas(...args),
    editarPlantilla: (...args: unknown[]) => editarPlantilla(...args),
    enviarARevision: (...args: unknown[]) => enviarARevision(...args),
  };
});

import {
  ErrorDeConversacion,
  ErrorDeFaq,
  MENSAJE_BORDE_CON_VARIABLE,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  MENSAJE_SIN_CONSULTAS,
  MENSAJE_SIN_EDICIONES,
  MENSAJE_SIN_ESCALADAS,
  MENSAJE_VARIABLE_INVALIDA,
} from "@/features/conversational";
import { formatearFecha } from "@/shared";
import type {
  Conversacion,
  DetalleDeConversacion,
  DetalleDeUso,
  Faq,
  ListadoDeConversaciones,
  ListadoDeFaqs,
  ListadoDePlantillas,
  Mensaje,
  Plantilla,
} from "@/features/conversational";

const { BandejaDeConversaciones } = await import(
  "@/features/conversational/components/BandejaDeConversaciones"
);
const { HiloDeConversacion } = await import(
  "@/features/conversational/components/HiloDeConversacion"
);
const { RespuestasFrecuentes } = await import(
  "@/features/conversational/components/RespuestasFrecuentes"
);
const { PlantillasDeNotificacion } = await import(
  "@/features/conversational/components/PlantillasDeNotificacion"
);

const ESCALADA: Conversacion = {
  id: "c1",
  cliente_id: "cl1",
  estado: "ACTIVA",
  ultimo_mensaje_en: "2026-09-08T18:00:00+00:00",
  esta_escalada: true,
  escalamiento_id: "e1",
  motivo: "El agente no interpretó la intención con confianza suficiente",
  estado_escalamiento: "ABIERTO",
  usuario_asignado_id: null,
};

const ATENDIDA: Conversacion = { ...ESCALADA, estado_escalamiento: "ASIGNADO" };
const RESUELTA: Conversacion = {
  ...ESCALADA,
  esta_escalada: false,
  escalamiento_id: null,
  motivo: null,
  estado_escalamiento: null,
};

const DEL_CLIENTE: Mensaje = {
  id: "m1",
  direccion: "ENTRANTE",
  tipo_contenido: "TEXTO",
  contenido: "hola, quiero un turno",
  momento: "2026-09-08T18:00:00+00:00",
  intencion: "TURNO",
  estado_entrega: null,
  origen: null,
};

const DEL_AGENTE: Mensaje = {
  id: "m2",
  direccion: "SALIENTE",
  tipo_contenido: "TEXTO",
  contenido: "Lo derivo con un asesor.",
  momento: "2026-09-08T18:01:00+00:00",
  intencion: null,
  estado_entrega: "ENVIADO",
  origen: "AGENTE",
};

const DEL_OPERADOR: Mensaje = { ...DEL_AGENTE, id: "m3", origen: "OPERADOR", contenido: "Hola!" };

function hilo(base: Conversacion, ...mensajes: Mensaje[]): DetalleDeConversacion {
  return { ...base, mensajes };
}

const FAQ_LISTA: Faq = {
  id: "f1",
  pregunta: "¿Cuánto sale un corte?",
  respuesta: "Sale $8000.",
  usos_este_mes: 12,
  usos_mes_anterior: 30,
  usos_total: 142,
  editada_en: null,
  sin_indexar: false,
};

const EDITADA_EN = "2026-09-26T15:00:00+00:00";

const DETALLE_COMPARABLE: DetalleDeUso = {
  usos_este_mes: 47,
  usos_mes_anterior: 30,
  usos_total: 142,
  editada_en: EDITADA_EN,
  comparacion: {
    dias: 10,
    antes: { usos: 2, total: 8, participacion: "25.0" },
    despues: { usos: 6, total: 12, participacion: "50.0" },
  },
  motivo_sin_comparacion: null,
};

const FAQ_SIN_INDEXAR: Faq = {
  ...FAQ_LISTA,
  id: "f2",
  pregunta: "¿Abren los sábados?",
  sin_indexar: true,
};

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

const SIN_APROBAR: Plantilla = {
  ...PLANTILLA,
  id: "p2",
  codigo: "recordatorio_de_cobro",
  estado_aprobacion: "PENDIENTE",
  variables: ["nombre", "monto", "concepto", "link", "vencimiento"],
  cuerpo: "Hola {{nombre}}, te debemos recordar {{concepto}}.",
  puede_usarse: false,
};

beforeAll(() => {
  vi.stubGlobal("confirm", () => true);
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
});

describe("PAN-WA-01 — bandeja", () => {
  it("arranca filtrada por las que esperan a un asesor", () => {
    const listado: ListadoDeConversaciones = { conversaciones: [ESCALADA] };
    render(<BandejaDeConversaciones inicial={listado} puedeAtender />);

    // La bandeja es una lista de conversaciones y no una tabla: cada fila es un hilo que se
    // abre, no un registro que se compara con el de al lado.
    const lista = within(screen.getByRole("list", { name: "Conversaciones" }));
    expect(lista.getByText("Espera un asesor")).toBeTruthy();
  });

  it("cambiar el filtro pide todas al backend", async () => {
    listarConversaciones.mockResolvedValue({ conversaciones: [] });
    render(<BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA] }} puedeAtender />);

    fireEvent.click(screen.getByRole("button", { name: "Todas" }));

    await waitFor(() => {
      expect(listarConversaciones).toHaveBeenCalledWith(false);
    });
  });

  it("dice el mensaje correcto segun el filtro cuando no hay nada", () => {
    render(<BandejaDeConversaciones inicial={{ conversaciones: [] }} puedeAtender />);

    expect(screen.getByText(MENSAJE_SIN_ESCALADAS)).toBeTruthy();
  });

  it("le avisa a Solo Lectura que puede mirar pero no atender", () => {
    const { rerender } = render(
      <BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA] }} puedeAtender />,
    );
    expect(screen.queryByText(/no atenderlas/)).toBeNull();

    rerender(
      <BandejaDeConversaciones inicial={{ conversaciones: [ESCALADA] }} puedeAtender={false} />,
    );
    expect(screen.getByText(/no atenderlas/)).toBeTruthy();
  });
});

describe("PAN-WA-01 — hilo", () => {
  it("muestra el historial completo, que es el contexto previo de RN-03", () => {
    render(<HiloDeConversacion inicial={hilo(ESCALADA, DEL_CLIENTE, DEL_AGENTE)} puedeAtender />);

    expect(screen.getByText("hola, quiero un turno")).toBeTruthy();
    expect(screen.getByText("Lo derivo con un asesor.")).toBeTruthy();
  });

  it("distingue el mensaje del operador del del agente (RN-04)", () => {
    render(
      <HiloDeConversacion
        inicial={hilo(ATENDIDA, DEL_CLIENTE, DEL_AGENTE, DEL_OPERADOR)}
        puedeAtender
      />,
    );

    expect(screen.getByText(/^Agente ·/)).toBeTruthy();
    expect(screen.getByText(/^Operador ·/)).toBeTruthy();
    expect(screen.getByText(/^Cliente ·/)).toBeTruthy();
  });

  it("muestra la intención del mensaje del cliente y nada cuando no se clasificó (HS-T2 RN-02)", () => {
    const sinClasificar: Mensaje = { ...DEL_CLIENTE, id: "m4", contenido: "hola", intencion: null };
    render(
      <HiloDeConversacion inicial={hilo(ESCALADA, DEL_CLIENTE, sinClasificar)} puedeAtender />,
    );

    const autores = screen.getAllByText(/^Cliente ·/).map((nodo) => nodo.textContent ?? "");
    expect(autores).toHaveLength(2);
    expect(autores[0]).toContain("· Turno");
    expect(autores[1]).not.toContain("· Turno");
  });

  it("no ofrece el campo de respuesta hasta tomar el escalamiento", () => {
    render(<HiloDeConversacion inicial={hilo(ESCALADA, DEL_CLIENTE)} puedeAtender />);

    expect(screen.queryByLabelText("Mensaje")).toBeNull();
    expect(screen.getByRole("button", { name: "Tomar la conversación" })).toBeTruthy();
  });

  it("con el escalamiento tomado aparece el campo y dice que el agente esta callado", () => {
    render(<HiloDeConversacion inicial={hilo(ATENDIDA, DEL_CLIENTE)} puedeAtender />);

    expect(screen.getByLabelText("Mensaje")).toBeTruthy();
    expect(screen.getByText(/no está contestando/)).toBeTruthy();
  });

  it("enviar llama a responder con el hilo y el texto, sin teléfono", async () => {
    responder.mockResolvedValue(DEL_OPERADOR);
    // After sending, the thread reloads itself from the API.
    verConversacion.mockResolvedValue(hilo(ATENDIDA, DEL_CLIENTE, DEL_OPERADOR));
    render(<HiloDeConversacion inicial={hilo(ATENDIDA, DEL_CLIENTE)} puedeAtender />);

    fireEvent.change(screen.getByLabelText("Mensaje"), { target: { value: "Hola, soy Ana" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => {
      expect(responder).toHaveBeenCalledWith("c1", "Hola, soy Ana");
    });
    expect(await screen.findByText("Hola!")).toBeTruthy();
  });

  it("tomar el escalamiento recarga el hilo", async () => {
    tomarEscalamiento.mockResolvedValue(ATENDIDA);
    verConversacion.mockResolvedValue(hilo(ATENDIDA, DEL_CLIENTE));
    render(<HiloDeConversacion inicial={hilo(ESCALADA, DEL_CLIENTE)} puedeAtender />);

    fireEvent.click(screen.getByRole("button", { name: "Tomar la conversación" }));

    await waitFor(() => {
      expect(tomarEscalamiento).toHaveBeenCalledWith("e1");
    });
    expect(await screen.findByLabelText("Mensaje")).toBeTruthy();
  });

  it("devolver al agente manda la clasificacion elegida (RN-05)", async () => {
    cerrarEscalamiento.mockResolvedValue(RESUELTA);
    verConversacion.mockResolvedValue(hilo(RESUELTA, DEL_CLIENTE));
    render(<HiloDeConversacion inicial={hilo(ATENDIDA, DEL_CLIENTE)} puedeAtender />);

    fireEvent.change(screen.getByLabelText("Clasificación al devolver"), {
      target: { value: "PAGO" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Devolver al agente" }));

    await waitFor(() => {
      expect(cerrarEscalamiento).toHaveBeenCalledWith("e1", true, "PAGO");
    });
  });

  it("sin clasificacion elegida deja que reevalue el agente", async () => {
    cerrarEscalamiento.mockResolvedValue(RESUELTA);
    verConversacion.mockResolvedValue(hilo(RESUELTA, DEL_CLIENTE));
    render(<HiloDeConversacion inicial={hilo(ATENDIDA, DEL_CLIENTE)} puedeAtender />);

    fireEvent.click(screen.getByRole("button", { name: "Devolver al agente" }));

    await waitFor(() => {
      expect(cerrarEscalamiento).toHaveBeenCalledWith("e1", true, undefined);
    });
  });

  it("muestra el rechazo de reapertura con las palabras del backend", async () => {
    cerrarEscalamiento.mockRejectedValue(
      new ErrorDeConversacion(
        "Un escalamiento cerrado no se reabre. Un nuevo pedido del cliente genera uno nuevo.",
      ),
    );
    render(<HiloDeConversacion inicial={hilo(ATENDIDA, DEL_CLIENTE)} puedeAtender />);

    fireEvent.click(screen.getByRole("button", { name: "Dar por finalizada" }));

    expect(await screen.findByText(/no se reabre/)).toBeTruthy();
  });

  it("le esconde todas las acciones a Solo Lectura pero le muestra el hilo", () => {
    render(<HiloDeConversacion inicial={hilo(ESCALADA, DEL_CLIENTE)} puedeAtender={false} />);

    expect(screen.getByText("hola, quiero un turno")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Tomar la conversación" })).toBeNull();
  });

  it("marca las notas de voz como transcriptas", () => {
    const audio: Mensaje = { ...DEL_CLIENTE, tipo_contenido: "AUDIO" };
    render(<HiloDeConversacion inicial={hilo(ESCALADA, audio)} puedeAtender />);

    expect(screen.getByText(/nota de voz transcripta/)).toBeTruthy();
  });
});

describe("PAN-WA-02 — respuestas frecuentes", () => {
  it("lista pregunta, respuesta y los tres conteos de uso (RN-02)", () => {
    const listado: ListadoDeFaqs = { faqs: [FAQ_LISTA] };
    render(<RespuestasFrecuentes inicial={listado} puedeEditar />);

    const tabla = within(screen.getByRole("table"));
    expect(tabla.getByText("¿Cuánto sale un corte?")).toBeTruthy();
    for (const titulo of ["Este mes", "Mes anterior", "Total"]) {
      expect(tabla.getByRole("columnheader", { name: titulo })).toBeTruthy();
    }
    expect(tabla.getByText("12")).toBeTruthy();
    expect(tabla.getByText("30")).toBeTruthy();
    expect(tabla.getByText("142")).toBeTruthy();
  });

  it("la barra suma los usos de este mes y ya no habla del período", () => {
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar />);

    expect(screen.getByText(/12/, { selector: "b" })).toBeTruthy();
    expect(screen.getByText(/usos este mes/)).toBeTruthy();
    expect(screen.queryByText(/en el período/)).toBeNull();
    expect(screen.queryByText("Usos en el período")).toBeNull();
  });

  it("«Ver uso» abre el detalle con la frase del prototipo y las dos participaciones", async () => {
    verUsoDeFaq.mockResolvedValue(DETALLE_COMPARABLE);
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Ver uso" }));

    expect(await screen.findByText("Respondida 47 veces este mes")).toBeTruthy();
    expect(verUsoDeFaq).toHaveBeenCalledWith("f1");
    const fecha = formatearFecha(EDITADA_EN);
    expect(
      screen.getByText(
        `Participación: 25,0 % en los 10 días antes de la edición del ${fecha} · 50,0 % en los 10 días después`,
      ),
    ).toBeTruthy();
  });

  it("sin comparación posible muestra el motivo y ningún porcentaje", async () => {
    verUsoDeFaq.mockResolvedValue({
      ...DETALLE_COMPARABLE,
      editada_en: null,
      comparacion: null,
      motivo_sin_comparacion: "SIN_EDICIONES",
    } satisfies DetalleDeUso);
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Ver uso" }));

    expect(await screen.findByText(MENSAJE_SIN_EDICIONES)).toBeTruthy();
    expect(screen.queryByText(/Participación:/)).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("un lapso sin consultas respondidas por FAQ no es un 0 %", async () => {
    verUsoDeFaq.mockResolvedValue({
      ...DETALLE_COMPARABLE,
      comparacion: {
        dias: 1,
        antes: { usos: 0, total: 0, participacion: null },
        despues: { usos: 1, total: 4, participacion: "25.0" },
      },
    } satisfies DetalleDeUso);
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Ver uso" }));

    const fecha = formatearFecha(EDITADA_EN);
    expect(
      await screen.findByText(
        `Participación: ${MENSAJE_SIN_CONSULTAS} en el día antes de la edición del ${fecha} · 25,0 % en el día después`,
      ),
    ).toBeTruthy();
  });

  it("dice cuando una respuesta todavia no es buscable", () => {
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_SIN_INDEXAR] }} puedeEditar />);

    expect(screen.getByText("Todavía no buscable")).toBeTruthy();
    expect(screen.getByText(/todavía no las encuentra por significado/)).toBeTruthy();
  });

  it("no deja guardar sin pregunta o sin respuesta, y lo dice", () => {
    render(<RespuestasFrecuentes inicial={{ faqs: [] }} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Agregar respuesta" }));

    expect(screen.getByText(MENSAJE_CAMPOS_OBLIGATORIOS)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar" }).hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Pregunta disparadora"), {
      target: { value: "¿Abren los sábados?" },
    });
    fireEvent.change(screen.getByLabelText("Respuesta"), { target: { value: "Sí, de 9 a 13." } });
    expect(screen.getByRole("button", { name: "Guardar" }).hasAttribute("disabled")).toBe(false);
  });

  it("crea la respuesta y recarga el listado", async () => {
    crearFaq.mockResolvedValue(FAQ_LISTA);
    listarFaqs.mockResolvedValue({ faqs: [FAQ_LISTA] });
    render(<RespuestasFrecuentes inicial={{ faqs: [] }} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Agregar respuesta" }));

    fireEvent.change(screen.getByLabelText("Pregunta disparadora"), {
      target: { value: "¿Cuánto sale un corte?" },
    });
    fireEvent.change(screen.getByLabelText("Respuesta"), { target: { value: "Sale $8000." } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(crearFaq).toHaveBeenCalledWith("¿Cuánto sale un corte?", "Sale $8000.");
    });
  });

  it("pide confirmacion antes de eliminar y dice que el efecto es inmediato", async () => {
    eliminarFaq.mockResolvedValue(undefined);
    listarFaqs.mockResolvedValue({ faqs: [] });
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar />);

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(screen.getByText(/de inmediato/)).toBeTruthy();
    // Y no se borró nada todavía.
    expect(eliminarFaq).not.toHaveBeenCalled();

    const modal = screen.getAllByRole("button", { name: "Eliminar" });
    fireEvent.click(modal[modal.length - 1] as HTMLElement);

    await waitFor(() => {
      expect(eliminarFaq).toHaveBeenCalledWith("f1");
    });
  });

  it("le muestra el listado a Solo Lectura pero no las acciones", () => {
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar={false} />);

    expect(screen.getByText("¿Cuánto sale un corte?")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Agregar respuesta" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
  });

  it("Solo Lectura puede «Ver uso» pero no «Editar» ni «Eliminar»", () => {
    render(<RespuestasFrecuentes inicial={{ faqs: [FAQ_LISTA] }} puedeEditar={false} />);

    expect(screen.getByRole("button", { name: "Ver uso" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Eliminar" })).toBeNull();
  });
});

describe("PAN-CFG-NOT — plantillas", () => {
  it("muestra el nombre legible y no el codigo del sistema", () => {
    const listado: ListadoDePlantillas = { plantillas: [PLANTILLA] };
    render(<PlantillasDeNotificacion inicial={listado} puedeEditar />);

    expect(screen.getByText("Recordatorio de turno")).toBeTruthy();
    expect(screen.queryByText("recordatorio_de_turno")).toBeNull();
  });

  it("avisa cuando hay plantillas sin aprobar (RN-04)", () => {
    render(<PlantillasDeNotificacion inicial={{ plantillas: [SIN_APROBAR] }} puedeEditar />);

    expect(screen.getByText("Hay plantillas sin aprobar")).toBeTruthy();
    expect(screen.getByText("En revisión de Meta")).toBeTruthy();
  });

  it("ofrece las variables admitidas en vez de hacerlas adivinar", () => {
    render(<PlantillasDeNotificacion inicial={{ plantillas: [PLANTILLA] }} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));

    // Acotado a la lista de variables y no a la pantalla entera: el cuerpo se edita en un
    // `textarea`, cuyo texto también dice `{{nombre}}`. Lo que la historia pide es que la
    // variable se **ofrezca**, no que aparezca en el mensaje que alguien ya escribió.
    const disponibles = within(screen.getByRole("list", { name: "Variables disponibles" }));
    expect(disponibles.getByText("{{nombre}}")).toBeTruthy();
  });

  it("avisa la variable invalida con la frase de la historia y deja el boton gris", () => {
    render(<PlantillasDeNotificacion inicial={{ plantillas: [PLANTILLA] }} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));

    fireEvent.change(screen.getByLabelText("Texto del mensaje"), {
      target: { value: "Hola {{nombre}}, tu saldo es {{saldo}}." },
    });

    expect(screen.getByText(MENSAJE_VARIABLE_INVALIDA)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Guardar" }).hasAttribute("disabled")).toBe(true);
  });

  it("guarda cuando todas las variables son admitidas", async () => {
    editarPlantilla.mockResolvedValue(PLANTILLA);
    listarPlantillas.mockResolvedValue({ plantillas: [PLANTILLA] });
    render(<PlantillasDeNotificacion inicial={{ plantillas: [PLANTILLA] }} puedeEditar />);
    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));

    fireEvent.change(screen.getByLabelText("Texto del mensaje"), {
      target: { value: "Hola {{nombre}}: te esperamos el {{fecha}} a las {{hora}}." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(editarPlantilla).toHaveBeenCalledWith(
        "p1",
        "Hola {{nombre}}: te esperamos el {{fecha}} a las {{hora}}.",
      );
    });
  });

  it("le esconde la edicion a quien no es Administrador", () => {
    render(<PlantillasDeNotificacion inicial={{ plantillas: [PLANTILLA] }} puedeEditar={false} />);

    expect(screen.getByText("Recordatorio de turno")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Editar texto" })).toBeNull();
  });
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
