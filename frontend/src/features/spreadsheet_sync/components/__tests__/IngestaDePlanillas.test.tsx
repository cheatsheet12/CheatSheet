/**
 * @vitest-environment jsdom
 *
 * PAN-ING-01 (HU-E2-04, HU-E3-03).
 *
 * Dos cosas se prueban acá y no en el cliente de API: que el rechazo **se vea**, y que un
 * rol que no puede escribir no reciba la zona de carga. La validación en sí ya tiene sus
 * propios tests; lo que falta comprobar es que su mensaje llega a la pantalla, que es
 * literalmente lo que dice el criterio de aceptación.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const listarPlanillas = vi.fn();
const subirPlanilla = vi.fn();
const desvincularPlanilla = vi.fn();
const iniciarVinculacionConGoogle = vi.fn();
const listarCargas = vi.fn();
const procesarPlanilla = vi.fn();

vi.mock("@/features/spreadsheet_sync/api/planilla", async () => {
  const real = await vi.importActual<typeof import("@/features/spreadsheet_sync/api/planilla")>(
    "@/features/spreadsheet_sync/api/planilla",
  );
  return {
    ...real,
    listarPlanillas: (...args: unknown[]) => listarPlanillas(...args),
    subirPlanilla: (...args: unknown[]) => subirPlanilla(...args),
    desvincularPlanilla: (...args: unknown[]) => desvincularPlanilla(...args),
    iniciarVinculacionConGoogle: (...args: unknown[]) => iniciarVinculacionConGoogle(...args),
    listarCargas: (...args: unknown[]) => listarCargas(...args),
    procesarPlanilla: (...args: unknown[]) => procesarPlanilla(...args),
  };
});

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

import type { Carga, ListadoDeVinculos, Vinculo } from "@/features/spreadsheet_sync";
import { ErrorDePlanilla, MENSAJE_ARCHIVO_DEMASIADO_GRANDE } from "@/features/spreadsheet_sync";

const { IngestaDePlanillas } = await import(
  "@/features/spreadsheet_sync/components/IngestaDePlanillas"
);

const VINCULO: Vinculo = {
  id: "v1",
  proveedor: "ARCHIVO",
  direccion: "SOLO_LECTURA",
  hoja_empresa: "clientes.xlsx",
  nombre_archivo: "clientes.xlsx",
  tamano_bytes: 2 * 1024 * 1024,
  pausado: false,
  motivo_de_pausa: null,
  escribe_de_vuelta: false,
  tiene_mapeo: false,
  ultima_lectura: null,
  created_at: "2026-09-07T12:00:00Z",
};

const INICIAL: ListadoDeVinculos = { vinculos: [VINCULO] };

const CARGA: Carga = {
  id: "c1",
  estado: "CON_ERRORES",
  filas_totales: 100,
  filas_ok: 98,
  filas_error: 2,
  es_reproceso: false,
  created_at: "2026-09-07T12:00:00Z",
};

beforeAll(() => {
  // `Button variante="destructivo"` confirma con `window.confirm`, que jsdom no implementa.
  vi.stubGlobal("confirm", () => true);
  // `Modal` es un `<dialog>` nativo y jsdom no implementa `showModal`.
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

beforeEach(() => {
  // `refrescar()` relee las dos tablas de la pantalla. Sin este doble, cualquier accion
  // que refresque termina en el camino de error y el test afirma sobre el mensaje
  // equivocado.
  listarCargas.mockResolvedValue({ cargas: [] });
});

function archivo(nombre: string): File {
  return new File([new Uint8Array(10)], nombre);
}

describe("IngestaDePlanillas", () => {
  it("ofrece revisar el mapeo de un vínculo Google real", () => {
    render(
      <IngestaDePlanillas
        inicial={{
          vinculos: [
            {
              ...VINCULO,
              proveedor: "GOOGLE_SHEETS",
              nombre_archivo: null,
              hoja_empresa: "Clientes",
            },
          ],
        }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    expect(screen.getByText("Revisar mapeo").closest("a")?.getAttribute("href")).toBe(
      "/ingesta/mapeo/v1",
    );
  });

  it("muestra las cargas recientes con su proveedor y su estado", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    expect(screen.getByText("clientes.xlsx")).toBeTruthy();
    expect(screen.getByText("Archivo subido")).toBeTruthy();
    // Sin mapeo confirmado todavía: eso es lo que el usuario tiene que hacer después.
    expect(screen.getByText("Falta mapear")).toBeTruthy();
    expect(screen.getByText("Solo lectura")).toBeTruthy();
  });

  it("no ofrece la zona de carga a un rol que no puede escribir", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar={false} />);

    expect(screen.queryByLabelText("Elegir una planilla")).toBeNull();
    expect(screen.queryByText("Desvincular")).toBeNull();
    // Pero sí ve el listado: HU-E3-05 RN-04 le da derecho a mirar.
    expect(screen.getByText("clientes.xlsx")).toBeTruthy();
  });

  it("muestra en pantalla el mensaje exacto con el que se rechaza un archivo", async () => {
    subirPlanilla.mockRejectedValue(new ErrorDePlanilla(MENSAJE_ARCHIVO_DEMASIADO_GRANDE));
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Elegir una planilla"), {
      target: { files: [archivo("grande.xlsx")] },
    });

    await waitFor(() => {
      expect(screen.getByText(MENSAJE_ARCHIVO_DEMASIADO_GRANDE)).toBeTruthy();
    });
  });

  it("refresca el listado despues de una carga exitosa", async () => {
    subirPlanilla.mockResolvedValue({ ...VINCULO, nombre_archivo: "nuevos.csv" });
    listarPlanillas.mockResolvedValue({
      vinculos: [{ ...VINCULO, id: "v2", nombre_archivo: "nuevos.csv" }],
    });
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.change(screen.getByLabelText("Elegir una planilla"), {
      target: { files: [archivo("nuevos.csv")] },
    });

    await waitFor(() => {
      expect(listarPlanillas).toHaveBeenCalled();
      expect(screen.getByText("nuevos.csv")).toBeTruthy();
    });
  });

  it("desvincula y avisa que los datos importados se quedan", async () => {
    desvincularPlanilla.mockResolvedValue(undefined);
    listarPlanillas.mockResolvedValue({ vinculos: [] });
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    fireEvent.click(screen.getByText("Desvincular"));

    await waitFor(() => {
      expect(desvincularPlanilla).toHaveBeenCalledWith("v1");
      expect(screen.getByText(/siguen en el sistema/)).toBeTruthy();
    });
  });

  it("muestra las cargas recientes con sus tres contadores", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[CARGA]} puedeEditar />);

    // El criterio de HU-E3-03: «indicando la cantidad de filas validas y fallidas».
    expect(screen.getByText("Con errores")).toBeTruthy();
    expect(screen.getByText("98 de 100")).toBeTruthy();
    expect(screen.getByText("Ver detalle")).toBeTruthy();
  });

  it("encola el procesamiento y avisa que recien empieza", async () => {
    procesarPlanilla.mockResolvedValue(undefined);
    listarPlanillas.mockResolvedValue(INICIAL);
    render(
      <IngestaDePlanillas
        inicial={{ vinculos: [{ ...VINCULO, tiene_mapeo: true }] }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    fireEvent.click(screen.getByText("Procesar"));

    await waitFor(() => {
      expect(procesarPlanilla).toHaveBeenCalledWith("v1");
      // 202: aceptado, no hecho. Decir «procesada» seria mentir sobre una importacion que
      // recien arranca (HU-E3-03 RN-01).
      expect(screen.getByText(/Empezamos a procesar/)).toBeTruthy();
    });
  });

  it("no ofrece procesar una planilla sin mapeo confirmado", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    expect(screen.queryByText("Procesar")).toBeNull();
  });

  it("informa cuando una planilla esta pausada porque cambio su estructura", () => {
    render(
      <IngestaDePlanillas
        inicial={{
          vinculos: [{ ...VINCULO, pausado: true, motivo_de_pausa: "cambio la estructura" }],
        }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    expect(screen.getByText("Pausada")).toBeTruthy();
  });
});

describe("IngestaDePlanillas · vincular con Google", () => {
  function abrirElPedidoDeEnlace(): void {
    fireEvent.click(screen.getByRole("button", { name: "Vincular Google Sheets" }));
    fireEvent.change(screen.getByLabelText("Enlace o nombre de la planilla"), {
      target: { value: "Clientes 2026" },
    });
  }

  it("permite pedir lectura y escritura para la hoja propia", async () => {
    iniciarVinculacionConGoogle.mockReturnValue(new Promise<string>(() => undefined));
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);
    abrirElPedidoDeEnlace();

    fireEvent.click(screen.getByLabelText("Escribir registros del panel en la hoja de CheatSheet"));
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() =>
      expect(iniciarVinculacionConGoogle).toHaveBeenCalledWith(
        "Clientes 2026",
        "LECTURA_Y_ESCRITURA",
      ),
    );
  });

  it("«Continuar» queda ocupado mientras se pide la URL y un segundo clic no pide otra vinculación", async () => {
    // Dos pedidos son dos `state` de OAuth: la cookie puede quedar con el otro y el callback
    // falla.
    let responder: (url: string) => void = () => undefined;
    iniciarVinculacionConGoogle.mockReturnValue(
      new Promise<string>((resolver) => {
        responder = resolver;
      }),
    );
    const original = window.location;
    const destino = { href: "" };
    vi.stubGlobal("location", destino);
    try {
      render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);
      abrirElPedidoDeEnlace();

      fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
      const boton = screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
      expect(boton.disabled).toBe(true);
      expect(boton.getAttribute("aria-busy")).toBe("true");
      fireEvent.click(boton);
      expect(iniciarVinculacionConGoogle).toHaveBeenCalledTimes(1);

      responder("https://accounts.example/oauth?state=abc");
      await waitFor(() => expect(destino.href).toBe("https://accounts.example/oauth?state=abc"));

      // La página todavía no se fue: el botón sigue ocupado hasta que lo haga.
      const despues = screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
      expect(despues.disabled).toBe(true);
      fireEvent.click(despues);
      expect(iniciarVinculacionConGoogle).toHaveBeenCalledTimes(1);
    } finally {
      vi.stubGlobal("location", original);
    }
  });

  it("si el pedido falla, «Continuar» se libera y el error se ve", async () => {
    iniciarVinculacionConGoogle.mockRejectedValue(new ErrorDePlanilla("Google no responde."));
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);
    abrirElPedidoDeEnlace();

    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    expect(await screen.findByText("Google no responde.")).toBeTruthy();
    const boton = screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
    expect(boton.disabled).toBe(false);
  });
});

describe("IngestaDePlanillas · resumen y avance", () => {
  it("la franja de resumen suma lo que la pantalla ya tiene", () => {
    const cargas: readonly Carga[] = [
      CARGA,
      { ...CARGA, id: "c2", estado: "COMPLETADO", filas_totales: 10, filas_ok: 10, filas_error: 0 },
    ];
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={cargas} puedeEditar />);

    const resumen = screen.getByRole("list", { name: "Resumen de la ingesta" });
    const valor = (clave: string): string | null =>
      resumen.querySelector(`[data-clave="${clave}"]`)?.textContent ?? null;
    expect(valor("planillas")).toBe("1");
    expect(valor("cargas")).toBe("2");
    expect(valor("importadas")).toBe("108");
    expect(valor("errores")).toBe("2");
  });

  it("sin mapeo, el paso que sigue es el mapeo", () => {
    render(<IngestaDePlanillas inicial={INICIAL} cargasIniciales={[]} puedeEditar />);

    const pasos = within(screen.getByRole("list", { name: "Avance de la planilla" })).getAllByRole(
      "listitem",
    );
    expect(pasos.map((paso) => paso.getAttribute("data-situacion"))).toEqual([
      "hecho",
      "actual",
      "pendiente",
    ]);
  });

  it("con mapeo y una lectura, los tres pasos quedan hechos", () => {
    render(
      <IngestaDePlanillas
        inicial={{
          vinculos: [{ ...VINCULO, tiene_mapeo: true, ultima_lectura: "2026-09-08T10:00:00Z" }],
        }}
        cargasIniciales={[]}
        puedeEditar
      />,
    );

    const pasos = within(screen.getByRole("list", { name: "Avance de la planilla" })).getAllByRole(
      "listitem",
    );
    expect(pasos.map((paso) => paso.getAttribute("data-situacion"))).toEqual([
      "hecho",
      "hecho",
      "hecho",
    ]);
  });
});
