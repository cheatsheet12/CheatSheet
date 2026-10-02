/**
 * @vitest-environment jsdom
 *
 * Las pantallas de reportería (HU-E10-01 … HU-E10-06).
 *
 * Lo que se prueba es lo que los criterios afirman sobre **lo que se ve**, y tres cosas más
 * que no están en ninguna historia y sí en el código:
 *
 * - que una variación en `null` se dibuje como un guion y no como «0%». Es la diferencia
 *   entre «no creció» y «no hay con qué comparar», y sólo una de las dos es verdad;
 * - que cambiar el tipo de reporte **corrija el formato elegido** cuando el nuevo tipo no lo
 *   admite: sin eso, la pantalla ofrece una combinación que el backend rechaza con un 422;
 * - que el enlace del contador **no aparezca en ningún lado**. No está porque no existe de
 *   este lado: sale una sola vez, por mail.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const verTablero = vi.fn();
const previsualizar = vi.fn();
const generarReporte = vi.fn();
const listarReportes = vi.fn();

vi.mock("@/features/reporting/api/reporte", async () => {
  const real = await vi.importActual<typeof import("@/features/reporting/api/reporte")>(
    "@/features/reporting/api/reporte",
  );
  return {
    ...real,
    verTablero: (...args: unknown[]) => verTablero(...args),
    previsualizar: (...args: unknown[]) => previsualizar(...args),
    generarReporte: (...args: unknown[]) => generarReporte(...args),
    listarReportes: (...args: unknown[]) => listarReportes(...args),
  };
});

const guardarConfiguracion = vi.fn();
const generarPaquete = vi.fn();
const listarPaquetes = vi.fn();
const invitarContador = vi.fn();
const revocarContador = vi.fn();

vi.mock("@/features/reporting/api/paquete", async () => {
  const real = await vi.importActual<typeof import("@/features/reporting/api/paquete")>(
    "@/features/reporting/api/paquete",
  );
  return {
    ...real,
    guardarConfiguracion: (...args: unknown[]) => guardarConfiguracion(...args),
    generarPaquete: (...args: unknown[]) => generarPaquete(...args),
    listarPaquetes: (...args: unknown[]) => listarPaquetes(...args),
    invitarContador: (...args: unknown[]) => invitarContador(...args),
    revocarContador: (...args: unknown[]) => revocarContador(...args),
  };
});

import { ErrorDeReporte, MENSAJE_SIN_ACTIVIDAD, MENSAJE_SIN_DATOS } from "@/features/reporting";
import type {
  AccesoDelContador,
  ConfiguracionDelPaqueteRespuesta,
  Paquete,
  Reporte,
  TableroRespuesta,
} from "@/features/reporting";

const { Tablero } = await import("@/features/reporting/components/Tablero");
const { GeneradorDeReportes } = await import("@/features/reporting/components/GeneradorDeReportes");
const { ConfiguracionDelPaquete } = await import(
  "@/features/reporting/components/ConfiguracionDelPaquete"
);
const { AccesoContable } = await import("@/features/reporting/components/AccesoContable");

const TABLERO: TableroRespuesta = {
  desde: "2026-03-01",
  hasta: "2026-03-31",
  facturado: { valor: "12500.55", anterior: "10000.00", variacion: "25.0" },
  cobrado: { valor: "8000.00", anterior: "0.00", variacion: null },
  turnos: { valor: "12", anterior: "10", variacion: "20.0" },
  operaciones: { valor: "340", anterior: "300", variacion: "13.3" },
  por_tipo: { FACTURA_B: "12500.55" },
  por_semana: { "2026-W10": "12500.55" },
  pendiente: "1500.00",
  en_mora: "500.00",
  tasa_de_cobro: "72.50",
  cobrado_por_semana: { "2026-W10": "8000.00", "2026-W11": "-1500.00" },
  cobros_por_estado: {
    PENDIENTE: { cantidad: 3, monto: "1500.00" },
    APROBADO: { cantidad: 8, monto: "8000.00" },
    VENCIDO: { cantidad: 1, monto: "500.00" },
  },
  sin_actividad: false,
};

const VACIO: TableroRespuesta = {
  ...TABLERO,
  facturado: { valor: "0.00", anterior: "0.00", variacion: null },
  cobrado: { valor: "0.00", anterior: "0.00", variacion: null },
  turnos: { valor: "0", anterior: "0", variacion: null },
  operaciones: { valor: "0", anterior: "0", variacion: null },
  por_tipo: {},
  por_semana: {},
  sin_actividad: true,
};

const REPORTE: Reporte = {
  id: "r1",
  tipo: "FACTURACION",
  formato: "CSV",
  desde: "2026-03-01",
  hasta: "2026-03-31",
  estado: "LISTO",
  descargable: true,
};

const PAQUETE: Paquete = {
  id: "p1",
  periodo: "2026-03",
  anio: 2026,
  mes: 3,
  totales_por_tipo: { FACTURAS: { cantidad: "3", total: "12500.55" } },
  disponible: true,
};

const CONFIGURACION: ConfiguracionDelPaqueteRespuesta = {
  activo: false,
  dia_de_envio: 5,
  formatos: ["PDF"],
  contenido: ["FACTURAS", "REPORTE_DE_COBROS"],
  email_contador: null,
  proximo_envio: null,
  contador: { email: null, invitado: false, vence: null, accesos: 0 },
};

const ACCESO: AccesoDelContador = {
  vence: "2026-05-05T12:00:00Z",
  tablero: TABLERO,
  paquetes: { paquetes: [PAQUETE] },
};

/** La tarjeta que contiene un título, para no chocar con textos repetidos en la pantalla. */
function tarjeta(titulo: string): HTMLElement {
  const encabezado = screen.getByText(titulo);
  const seccion = encabezado.closest("section");
  if (seccion === null) {
    throw new Error(`No hay una tarjeta que contenga «${titulo}»`);
  }
  return seccion;
}

beforeAll(() => {
  // jsdom no implementa `confirm`, que el botón destructivo usa antes de revocar.
  vi.stubGlobal("confirm", () => true);
});

afterEach(() => {
  cleanup();
  verTablero.mockReset();
  previsualizar.mockReset();
  generarReporte.mockReset();
  listarReportes.mockReset();
  guardarConfiguracion.mockReset();
  generarPaquete.mockReset();
  listarPaquetes.mockReset();
  invitarContador.mockReset();
  revocarContador.mockReset();
});

describe("PAN-REP-01 · el tablero", () => {
  it("muestra las cuatro métricas con su variación", () => {
    render(<Tablero inicial={TABLERO} />);

    expect(within(tarjeta("Facturado")).getByText("$ 12.500,55")).toBeTruthy();
    expect(within(tarjeta("Facturado")).getByText(/25\.0%/)).toBeTruthy();
    expect(within(tarjeta("Turnos gestionados")).getByText("12")).toBeTruthy();
    expect(within(tarjeta("Operaciones")).getByText("340")).toBeTruthy();
  });

  it("dibuja un guion cuando no hay período anterior con el que comparar", () => {
    render(<Tablero inicial={TABLERO} />);

    // «Creció 0%» y «no hay con qué comparar» son cosas distintas.
    expect(within(tarjeta("Cobrado")).getByText("—")).toBeTruthy();
  });

  it("avisa con la frase de la historia cuando el período no tuvo actividad", () => {
    render(<Tablero inicial={VACIO} />);

    expect(screen.getByText(MENSAJE_SIN_ACTIVIDAD)).toBeTruthy();
  });

  it("cambiar el período vuelve a pedir el tablero", async () => {
    verTablero.mockResolvedValue({
      ...TABLERO,
      facturado: { ...TABLERO.facturado, valor: "1.00" },
    });
    render(<Tablero inicial={TABLERO} />);

    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-02-01" } });

    await waitFor(() => {
      expect(verTablero).toHaveBeenCalledWith({ desde: "2026-02-01", hasta: "2026-03-31" });
    });
  });

  it("un fallo al filtrar se dice, no se traga", async () => {
    verTablero.mockRejectedValue(new ErrorDeReporte("La API no respondió"));
    render(<Tablero inicial={TABLERO} />);

    fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "2026-03-15" } });

    await waitFor(() => {
      expect(screen.getByText("La API no respondió")).toBeTruthy();
    });
  });
});

describe("PAN-REP-01 · las visualizaciones de cobranza", () => {
  it("muestra «Cobrado por semana» y «Cobros por estado» con la tasa en el subtítulo", () => {
    render(<Tablero inicial={TABLERO} />);

    const semanal = tarjeta("Cobrado por semana");
    expect(within(semanal).getByText("$ 8.000,00")).toBeTruthy();

    const porEstado = tarjeta("Cobros por estado");
    expect(
      within(porEstado).getByText(
        "Cobros creados en el período, por su estado actual · tasa de cobro 72,50 %",
      ),
    ).toBeTruthy();
    // Las etiquetas son las de payments (APROBADO se ve «Pagado»), con la cantidad al lado.
    expect(within(porEstado).getByText("Pagado")).toBeTruthy();
    expect(within(porEstado).getByText("En mora")).toBeTruthy();
    expect(within(porEstado).getByText("8 cobros")).toBeTruthy();
    expect(within(porEstado).getByText("1 cobro")).toBeTruthy();
    expect(within(porEstado).getByText("$ 8.000,00")).toBeTruthy();
  });

  it("cambiar el período actualiza los dos gráficos de cobranza", async () => {
    verTablero.mockResolvedValue({
      ...TABLERO,
      tasa_de_cobro: "10.00",
      cobrado_por_semana: { "2026-W06": "111.00", "2026-W07": "222.00" },
      cobros_por_estado: {
        APROBADO: { cantidad: 2, monto: "333.00" },
        CANCELADO: { cantidad: 5, monto: "44.00" },
      },
    });
    render(<Tablero inicial={TABLERO} />);

    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-02-01" } });

    await waitFor(() => {
      expect(within(tarjeta("Cobrado por semana")).getByText("$ 222,00")).toBeTruthy();
    });
    const porEstado = tarjeta("Cobros por estado");
    expect(within(porEstado).getByText("Cancelado")).toBeTruthy();
    expect(within(porEstado).getByText(/tasa de cobro 10,00 %/)).toBeTruthy();
  });

  it("una semana negativa lleva la clase negativa y el monto con signo", () => {
    const { container } = render(<Tablero inicial={TABLERO} />);

    const semanal = tarjeta("Cobrado por semana");
    expect(within(semanal).getByText("$ -1.500,00")).toBeTruthy();
    const negativas = container.querySelectorAll(".rep-barras__barra--negativa");
    expect(negativas).toHaveLength(1);
    expect(negativas[0]?.closest("li")?.textContent).toContain("-1.500,00");
  });

  it("con una sola semana, la nota habla de cobros y no de facturación", () => {
    render(<Tablero inicial={{ ...TABLERO, cobrado_por_semana: { "2026-W10": "8000.00" } }} />);

    const semanal = tarjeta("Cobrado por semana");
    expect(within(semanal).getByText(/única semana con cobros/)).toBeTruthy();
    expect(within(semanal).queryByText(/facturación/)).toBeNull();
    // La facturación conserva su nota.
    expect(within(tarjeta("Facturación por semana")).getByText(/con facturación/)).toBeTruthy();
  });

  it("sin cobros dice que no los hubo", () => {
    render(<Tablero inicial={{ ...TABLERO, cobrado_por_semana: {}, cobros_por_estado: {} }} />);

    expect(within(tarjeta("Cobrado por semana")).getByText(/No hubo cobros/)).toBeTruthy();
    expect(within(tarjeta("Cobros por estado")).getByText(/No se crearon cobros/)).toBeTruthy();
  });
});

describe("PAN-REP-01 · generar reportes", () => {
  /** La previsualización se dispara sola al cambiar cualquier filtro, así que siempre hay
   * alguien esperando una respuesta: un doble sin valor de retorno haría fallar tests que no
   * tienen nada que ver con ella. */
  const ESTIMACION = {
    tipo: "FACTURACION" as const,
    desde: "2026-03-01",
    hasta: "2026-03-31",
    cantidad: 2,
    total: "100.00",
    hay_datos: true,
  };

  it("Solo Lectura ve el historial y no el generador", () => {
    render(<GeneradorDeReportes inicial={[REPORTE]} periodo={{}} puedeGenerar={false} />);

    expect(screen.queryByText("Generar un reporte")).toBeNull();
    expect(screen.getByText("Reportes generados")).toBeTruthy();
  });

  it("ofrece sólo los formatos que el tipo admite", () => {
    previsualizar.mockResolvedValue(ESTIMACION);
    render(<GeneradorDeReportes inicial={[]} periodo={{}} puedeGenerar />);

    const formato = screen.getByLabelText("Formato") as HTMLSelectElement;
    expect([...formato.options].map((una) => una.value)).toEqual(["CSV", "XML"]);

    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "RESUMEN_EJECUTIVO" } });

    // Y corrige el formato elegido: CSV no existe para un resumen ejecutivo.
    expect([...formato.options].map((una) => una.value)).toEqual(["PDF"]);
    expect(formato.value).toBe("PDF");
  });

  it("previsualiza al cambiar un filtro, sin generar nada", async () => {
    previsualizar.mockResolvedValue({
      tipo: "COBROS",
      desde: "2026-03-01",
      hasta: "2026-03-31",
      cantidad: 7,
      total: "42000.00",
      hay_datos: true,
    });
    render(<GeneradorDeReportes inicial={[]} periodo={{}} puedeGenerar />);

    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "COBROS" } });

    await waitFor(() => {
      expect(screen.getByText(/Se van a exportar 7 registros/)).toBeTruthy();
    });
    expect(generarReporte).not.toHaveBeenCalled();
  });

  it("generar refresca el historial", async () => {
    previsualizar.mockResolvedValue(ESTIMACION);
    generarReporte.mockResolvedValue(REPORTE);
    listarReportes.mockResolvedValue({ reportes: [REPORTE] });
    render(<GeneradorDeReportes inicial={[]} periodo={{}} puedeGenerar />);

    fireEvent.click(screen.getByRole("button", { name: "Generar" }));

    await waitFor(() => {
      expect(within(screen.getByRole("table")).getByText("Facturación")).toBeTruthy();
    });
  });

  it("un fallo al generar muestra el error y recarga el historial", async () => {
    const FALLIDO: Reporte = { ...REPORTE, id: "r2", estado: "FALLIDO", descargable: false };
    previsualizar.mockResolvedValue(ESTIMACION);
    generarReporte.mockRejectedValue(new ErrorDeReporte("No se pudo generar el reporte."));
    listarReportes.mockResolvedValue({ reportes: [FALLIDO] });
    render(<GeneradorDeReportes inicial={[]} periodo={{}} puedeGenerar />);

    fireEvent.click(screen.getByRole("button", { name: "Generar" }));

    await waitFor(() => {
      expect(listarReportes).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText("No se pudo generar el reporte.")).toBeTruthy();
    await waitFor(() => {
      expect(within(screen.getByRole("table")).getByText("Facturación")).toBeTruthy();
    });
  });

  it("un período sin datos muestra la frase de la historia", async () => {
    previsualizar.mockResolvedValue(ESTIMACION);
    generarReporte.mockRejectedValue(new ErrorDeReporte(MENSAJE_SIN_DATOS));
    render(<GeneradorDeReportes inicial={[]} periodo={{}} puedeGenerar />);

    fireEvent.click(screen.getByRole("button", { name: "Generar" }));

    await waitFor(() => {
      expect(screen.getByText(MENSAJE_SIN_DATOS)).toBeTruthy();
    });
  });
});

describe("PAN-REP-02 · el paquete contable", () => {
  it("el Operador ve el estado pero no puede tocarlo", () => {
    render(
      <ConfiguracionDelPaquete
        inicial={CONFIGURACION}
        paquetes={[PAQUETE]}
        puedeConfigurar={false}
      />,
    );

    expect((screen.getByLabelText("Día de envío") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
  });

  it("activar manda la configuración entera", async () => {
    guardarConfiguracion.mockResolvedValue({ ...CONFIGURACION, activo: true });
    render(<ConfiguracionDelPaquete inicial={CONFIGURACION} paquetes={[]} puedeConfigurar />);

    fireEvent.change(screen.getByLabelText("Día de envío"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Activar envío" }));

    await waitFor(() => {
      expect(guardarConfiguracion).toHaveBeenCalledWith({
        dia_de_envio: 10,
        formatos: ["PDF"],
        contenido: ["FACTURAS", "REPORTE_DE_COBROS"],
        email_contador: null,
        activo: true,
      });
    });
  });

  it("el paquete de prueba refresca el listado", async () => {
    generarPaquete.mockResolvedValue(PAQUETE);
    listarPaquetes.mockResolvedValue({ paquetes: [PAQUETE] });
    render(<ConfiguracionDelPaquete inicial={CONFIGURACION} paquetes={[]} puedeConfigurar />);

    fireEvent.click(screen.getByRole("button", { name: "Generar paquete de prueba" }));

    await waitFor(() => {
      expect(within(screen.getByRole("table")).getByText("2026-03")).toBeTruthy();
    });
  });

  it("invitar muestra al contador y **no** el enlace", async () => {
    invitarContador.mockResolvedValue({
      email: "contador@estudio.com.ar",
      invitado: true,
      vence: "2026-05-05T12:00:00Z",
      accesos: 0,
    });
    render(<ConfiguracionDelPaquete inicial={CONFIGURACION} paquetes={[]} puedeConfigurar />);

    fireEvent.change(screen.getByLabelText("Email del contador", { selector: "#paq-contador" }), {
      target: { value: "contador@estudio.com.ar" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Invitar" }));

    await waitFor(() => {
      expect(screen.getByText("Invitado con acceso limitado")).toBeTruthy();
    });
    expect(screen.queryByText(/https?:\/\//)).toBeNull();
  });

  it("revocar deja de mostrar al contador", async () => {
    revocarContador.mockResolvedValue(undefined);
    render(
      <ConfiguracionDelPaquete
        inicial={{
          ...CONFIGURACION,
          contador: {
            email: "contador@estudio.com.ar",
            invitado: true,
            vence: "2026-05-05T12:00:00Z",
            accesos: 2,
          },
        }}
        paquetes={[]}
        puedeConfigurar
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Revocar acceso" }));

    await waitFor(() => {
      expect(screen.getByText("Todavía no invitaste a ningún contador.")).toBeTruthy();
    });
  });
});

describe("HU-E10-06 · la pantalla del contador", () => {
  it("muestra los indicadores y los paquetes", () => {
    render(<AccesoContable valor="abc" acceso={ACCESO} />);

    expect(within(tarjeta("Facturado")).getByText("$ 12.500,55")).toBeTruthy();
    expect(within(screen.getByRole("table")).getByText("2026-03")).toBeTruthy();
  });

  it("la descarga lleva el enlace y el paquete", () => {
    render(<AccesoContable valor="abc" acceso={ACCESO} />);

    const enlace = within(screen.getByRole("table")).getByText("Descargar") as HTMLAnchorElement;
    expect(enlace.getAttribute("href")).toBe("/api/contador/abc/paquetes/p1");
  });

  it("un enlace que no sirve muestra la frase y nada más", () => {
    render(
      <AccesoContable
        valor="abc"
        acceso={null}
        motivo="El acceso a este paquete ya no está disponible."
      />,
    );

    expect(screen.getByText("El acceso a este paquete ya no está disponible.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
