/**
 * @vitest-environment jsdom
 *
 * PAN-CFG-INT — cases 19 and 20 of the plan.
 *
 * The role check here is **cosmetic** and the test says so: what actually refuses an
 * Operador who tries to connect is the backend, and the application-layer test proves
 * that. What this file proves is the other half — that the panel does not offer an action
 * that is going to be rejected.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const listarIntegraciones = vi.fn();
const verificarIntegraciones = vi.fn();
const conectarIntegracion = vi.fn();

vi.mock("@/features/integrations/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/integrations/api/cliente")>(
    "@/features/integrations/api/cliente",
  );
  return {
    ...real,
    listarIntegraciones: (...args: unknown[]) => listarIntegraciones(...args),
    verificarIntegraciones: (...args: unknown[]) => verificarIntegraciones(...args),
    conectarIntegracion: (...args: unknown[]) => conectarIntegracion(...args),
  };
});

import type { Integracion, ListadoDeIntegraciones } from "@/features/integrations";

const { GrillaDeIntegraciones } = await import(
  "@/features/integrations/components/GrillaDeIntegraciones"
);

const ARCA: Integracion = {
  sistema: "ARCA",
  estado: "NO_CONECTADO",
  detalle: null,
  ambiente: null,
  verificado_en: null,
  configurada: false,
  etiqueta: null,
};

const RESTO: readonly Integracion[] = [
  {
    sistema: "MERCADOPAGO",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
    etiqueta: null,
  },
  {
    sistema: "WHATSAPP",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
    etiqueta: null,
  },
  {
    sistema: "GOOGLE_SHEETS",
    estado: "NO_CONECTADO",
    detalle: null,
    ambiente: null,
    verificado_en: null,
    configurada: false,
    etiqueta: null,
  },
];

const SIN_CONECTAR: ListadoDeIntegraciones = {
  integraciones: [ARCA, ...RESTO],
  verificado_en: null,
};

beforeAll(() => {
  // jsdom has no `showModal`, and a `<dialog>` without `open` keeps its contents out of
  // the accessibility tree — so the stub has to set the flag, not just record the call.
  // Same shape as `ModalDeInvitacion`'s test in identity.
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

describe("GrillaDeIntegraciones", () => {
  it("renderiza las cuatro tarjetas del prototipo", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("ARCA")).toBeTruthy();
    expect(screen.getByText("MercadoPago")).toBeTruthy();
    expect(screen.getByText("WhatsApp Business")).toBeTruthy();
    expect(screen.getByText("Google Sheets")).toBeTruthy();
    expect(screen.getAllByText("Sin conectar")).toHaveLength(4);
  });

  it("muestra el resumen de conectados y la marca de tiempo vacia", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("0 de 4 conectados")).toBeTruthy();
    expect(screen.getByText(/Última verificación: —/)).toBeTruthy();
  });

  it("verificar refresca los estados y la marca de tiempo", async () => {
    verificarIntegraciones.mockResolvedValue({
      integraciones: [
        {
          ...ARCA,
          estado: "CONECTADO",
          ambiente: "HOMOLOGACION",
          configurada: true,
          verificado_en: "2026-08-18T15:30:00Z",
        },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    });

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getByRole("button", { name: "Verificar estado" }));

    await waitFor(() => {
      expect(screen.getByText("Conectado")).toBeTruthy();
    });
    expect(screen.getByText("1 de 4 conectados")).toBeTruthy();
    // The exact rendering belongs to `formatearFechaHora`, which has its own test; what
    // matters here is that RN-03's timestamp stopped being empty.
    expect(screen.queryByText(/Última verificación: —/)).toBeNull();
  });

  it("muestra el detalle de una integracion degradada", () => {
    const degradada: ListadoDeIntegraciones = {
      integraciones: [
        { ...ARCA, estado: "ATENCION", detalle: "Servicio degradado", configurada: true },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    };

    render(<GrillaDeIntegraciones inicial={degradada} puedeConectar />);

    expect(screen.getByText("Atención")).toBeTruthy();
    expect(screen.getByText("Servicio degradado")).toBeTruthy();
  });

  it("una integracion ya configurada ofrece Reconectar y no Conectar", () => {
    const caida: ListadoDeIntegraciones = {
      integraciones: [{ ...ARCA, configurada: true }, ...RESTO],
      verificado_en: null,
    };

    render(<GrillaDeIntegraciones inicial={caida} puedeConectar />);

    expect(screen.getByRole("button", { name: "Reconectar" })).toBeTruthy();
  });

  it("el operador no ve ninguna accion de conectar", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar={false} />);

    expect(screen.queryByRole("button", { name: "Conectar" })).toBeNull();
    // The check is still there: HU-E2-05 names the Operador as an actor.
    expect(screen.getByRole("button", { name: "Verificar estado" })).toBeTruthy();
  });

  it("Google Sheets no es conectable en este epico", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    expect(screen.getByText("Disponible próximamente")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Conectar" })).toHaveLength(3);
  });

  it("conectar recarga el listado", async () => {
    // MercadoPago es el único sistema que todavía manda una credencial de relleno: ARCA y
    // WhatsApp abren su propio formulario. Cuando llegue `conexion-mercadopago`, este test
    // se muda igual que se mudó acá.
    conectarIntegracion.mockResolvedValue({});
    listarIntegraciones.mockResolvedValue({
      integraciones: [
        ARCA,
        ...RESTO.map((integracion) =>
          integracion.sistema === "MERCADOPAGO"
            ? {
                ...integracion,
                estado: "CONECTADO" as const,
                ambiente: "HOMOLOGACION" as const,
                configurada: true,
              }
            : integracion,
        ),
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    });

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[1]!);

    await waitFor(() => {
      expect(screen.getByText("Conectado")).toBeTruthy();
    });
    expect(conectarIntegracion).toHaveBeenCalledWith("MERCADOPAGO", expect.any(String), {});
    expect(screen.getByText("Homologación")).toBeTruthy();
  });

  it("un fallo de la verificacion se muestra y no rompe la pantalla", async () => {
    verificarIntegraciones.mockRejectedValue(new Error("El servicio no respondio"));

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getByRole("button", { name: "Verificar estado" }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("El servicio no respondio");
    });
    expect(screen.getAllByText("Sin conectar")).toHaveLength(4);
  });

  // ------------------------------------------------- conexion-whatsapp: casos 27 y 28

  const WHATSAPP_PENDIENTE: ListadoDeIntegraciones = {
    integraciones: [
      ARCA,
      ...RESTO.map((integracion) =>
        integracion.sistema === "WHATSAPP"
          ? {
              ...integracion,
              estado: "PENDIENTE" as const,
              detalle: "Meta esta revisando el nombre para mostrar",
              configurada: true,
            }
          : integracion,
      ),
    ],
    verificado_en: "2026-08-18T15:30:00Z",
  };

  it("una integracion pendiente muestra el badge y no ofrece ninguna accion", () => {
    // Caso 27. La solicitud ya está en curso del lado de Meta: un botón acá invitaría a
    // arrancar una segunda revisión que reinicia el reloj de la primera.
    render(<GrillaDeIntegraciones inicial={WHATSAPP_PENDIENTE} puedeConectar />);

    expect(screen.getByText("Pendiente")).toBeTruthy();
    expect(screen.getByText("Meta esta revisando el nombre para mostrar")).toBeTruthy();
    // Quedan ARCA y MercadoPago; WhatsApp no aporta ninguno.
    expect(screen.getAllByRole("button", { name: "Conectar" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Reconectar" })).toBeNull();
  });

  it("una integracion conectada muestra el nombre verificado que informo el proveedor", () => {
    // RN-03: el display name verificado es lo que identifica *cuál* cuenta quedó conectada.
    const conectada: ListadoDeIntegraciones = {
      integraciones: [
        ARCA,
        ...RESTO.map((integracion) =>
          integracion.sistema === "WHATSAPP"
            ? {
                ...integracion,
                estado: "CONECTADO" as const,
                configurada: true,
                etiqueta: "Panaderia Dona Rosa · +54 9 11 5555-0000",
              }
            : integracion,
        ),
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    };

    render(<GrillaDeIntegraciones inicial={conectada} puedeConectar />);

    expect(screen.getByText("Panaderia Dona Rosa · +54 9 11 5555-0000")).toBeTruthy();
  });

  it("conectar WhatsApp abre el formulario en vez de mandar una credencial de relleno", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[2]!);

    expect(screen.getByLabelText("Token de acceso")).toBeTruthy();
    expect(conectarIntegracion).not.toHaveBeenCalled();
  });

  it("el formulario de WhatsApp exige los tres datos antes de llamar al backend", async () => {
    // Caso 28. Meta rechazaría la llamada igual; pedirlo acá le ahorra al Administrador
    // un viaje de ida y vuelta para enterarse.
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[2]!);

    fireEvent.change(screen.getByLabelText("Token de acceso"), {
      target: { value: "fake-token-for-tests" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Conectar número" }));

    expect(conectarIntegracion).not.toHaveBeenCalled();
  });

  it("el formulario completo manda el token y los dos identificadores", async () => {
    conectarIntegracion.mockResolvedValue({});
    listarIntegraciones.mockResolvedValue(WHATSAPP_PENDIENTE);

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[2]!);

    fireEvent.change(screen.getByLabelText("Token de acceso"), {
      target: { value: "fake-token-for-tests" },
    });
    fireEvent.change(screen.getByLabelText("ID del número (Phone Number ID)"), {
      target: { value: "109876543210987" },
    });
    fireEvent.change(screen.getByLabelText("ID de la cuenta (WABA ID)"), {
      target: { value: "102030405060708" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Conectar número" }));

    await waitFor(() => {
      expect(screen.getByText("Pendiente")).toBeTruthy();
    });
    expect(conectarIntegracion).toHaveBeenCalledWith("WHATSAPP", expect.any(String), {
      phone_number_id: "109876543210987",
      waba_id: "102030405060708",
    });
    // Caso 28, segunda mitad: el modal se cierra, así que la credencial no queda en el DOM
    // esperando a quien abra el diálogo la próxima vez.
    expect(screen.queryByLabelText("Token de acceso")).toBeNull();
  });

  // ------------------------------------------------------ conexion-arca: casos 28 y 29

  it("conectar ARCA abre el formulario de los dos archivos", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);

    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[0]!);

    expect(screen.getByLabelText("Certificado (.crt o .pem)")).toBeTruthy();
    expect(screen.getByLabelText("Clave privada (.key)")).toBeTruthy();
    expect(conectarIntegracion).not.toHaveBeenCalled();
  });

  it("el formulario de ARCA exige los dos archivos antes de llamar al backend", () => {
    // Caso 28. Sin uno de los dos no hay nada que validar contra ARCA.
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[0]!);

    expect(screen.getByRole("button", { name: "Conectar ARCA" }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(conectarIntegracion).not.toHaveBeenCalled();
  });

  it("la tarjeta de ARCA muestra el CUIT, el vencimiento y el ambiente", () => {
    // Caso 29, cuarto criterio de aceptación: «veo el ambiente configurado y el estado
    // actual de la conexión». El CUIT y la fecha viajan en `etiqueta`, que escribe la ACL.
    const conectada: ListadoDeIntegraciones = {
      integraciones: [
        {
          ...ARCA,
          estado: "CONECTADO",
          ambiente: "HOMOLOGACION",
          configurada: true,
          etiqueta: "CUIT 20123456789 · vence 2027-09-23",
        },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    };

    render(<GrillaDeIntegraciones inicial={conectada} puedeConectar />);

    expect(screen.getByText("CUIT 20123456789 · vence 2027-09-23")).toBeTruthy();
    expect(screen.getByText("Homologación")).toBeTruthy();
    expect(screen.getByText("Conectado")).toBeTruthy();
  });

  it("un certificado por vencer se muestra en Atención con el motivo", () => {
    const porVencer: ListadoDeIntegraciones = {
      integraciones: [
        {
          ...ARCA,
          estado: "ATENCION",
          detalle: "El certificado vence en 20 dias (2026-09-08). Renovalo en ARCA antes",
          configurada: true,
        },
        ...RESTO,
      ],
      verificado_en: "2026-08-18T15:30:00Z",
    };

    render(<GrillaDeIntegraciones inicial={porVencer} puedeConectar />);

    expect(screen.getByText("Atención")).toBeTruthy();
    expect(screen.getByText(/El certificado vence en 20 dias/)).toBeTruthy();
    // Sigue configurada, así que ofrece «Reconectar» para cargar el certificado nuevo.
    expect(screen.getByRole("button", { name: "Reconectar" })).toBeTruthy();
  });

  it("el aviso fiscal de la conexión con ARCA se muestra al Administrador", async () => {
    // Conectar ARCA es el primer instante en que el padrón se puede consultar, así que el
    // hallazgo vuelve en esa misma respuesta. Si no se mostrara acá, un certificado de
    // otro CUIT recién se notaría cuando saliera el primer comprobante mal emitido.
    conectarIntegracion.mockResolvedValue({
      aviso_fiscal: "El certificado cargado en ARCA pertenece a otro CUIT que el de la empresa.",
    });
    listarIntegraciones.mockResolvedValue(SIN_CONECTAR);

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[1]!);

    await waitFor(() => {
      expect(screen.getByText(/pertenece a otro CUIT/)).toBeTruthy();
    });
  });

  it("sin aviso fiscal la pantalla no inventa una advertencia", async () => {
    conectarIntegracion.mockResolvedValue({ aviso_fiscal: null });
    listarIntegraciones.mockResolvedValue(SIN_CONECTAR);

    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[1]!);

    await waitFor(() => expect(conectarIntegracion).toHaveBeenCalled());
    expect(screen.queryByText("Revisá los datos fiscales")).toBeNull();
  });

  it("el campo del token no queda legible en pantalla", () => {
    render(<GrillaDeIntegraciones inicial={SIN_CONECTAR} puedeConectar />);
    fireEvent.click(screen.getAllByRole("button", { name: "Conectar" })[2]!);

    const campo = screen.getByLabelText("Token de acceso");
    expect(campo.getAttribute("type")).toBe("password");
    expect(campo.getAttribute("autocomplete")).toBe("off");
  });
});
