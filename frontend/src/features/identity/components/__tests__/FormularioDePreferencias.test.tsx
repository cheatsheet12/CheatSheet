/**
 * @vitest-environment jsdom
 *
 * PAN-USR-02 — caso 41.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const guardarPreferencias = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, guardarPreferencias: (...args: unknown[]) => guardarPreferencias(...args) };
});

const { FormularioDePreferencias } = await import(
  "@/features/identity/components/FormularioDePreferencias"
);
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

const INICIALES = {
  pref_idioma: "es-AR",
  pref_zona_horaria: "America/Argentina/Buenos_Aires",
  pref_suscripciones: {
    FACTURACION: ["EMAIL", "PANEL"],
    COBROS: ["EMAIL"],
    SINCRONIZACION: [],
    AGENDA: [],
    SISTEMA: [],
  },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function casilla(categoria: string, canal: "EMAIL" | "PANEL"): HTMLInputElement {
  const etiqueta = canal === "EMAIL" ? "Email" : "Panel";
  return screen.getByLabelText(etiqueta, {
    selector: `#${categoria}-${canal}`,
  }) as HTMLInputElement;
}

describe("FormularioDePreferencias", () => {
  it("carga las preferencias actuales", () => {
    render(<FormularioDePreferencias iniciales={INICIALES} />);

    expect((screen.getByLabelText("Zona horaria") as HTMLSelectElement).value).toBe(
      "America/Argentina/Buenos_Aires",
    );
    // Five categories times two channels: the label alone is ambiguous, so each
    // checkbox is addressed by its own id — which is also how a user tells them apart,
    // by the row they are in.
    expect(casilla("FACTURACION", "EMAIL").checked).toBe(true);
    expect(casilla("FACTURACION", "PANEL").checked).toBe(true);
    expect(casilla("COBROS", "PANEL").checked).toBe(false);
  });

  it("guarda los cambios y lo confirma", async () => {
    guardarPreferencias.mockResolvedValue(INICIALES);
    render(<FormularioDePreferencias iniciales={INICIALES} />);

    fireEvent.change(screen.getByLabelText("Zona horaria"), {
      target: { value: "America/Argentina/Ushuaia" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(screen.getByText("Listo, tus preferencias quedaron guardadas.")).toBeDefined();
    });
    expect(guardarPreferencias).toHaveBeenCalledWith({
      pref_idioma: "es-AR",
      pref_zona_horaria: "America/Argentina/Ushuaia",
      pref_suscripciones: INICIALES.pref_suscripciones,
    });
  });

  it("destildar una suscripción la saca del envío", async () => {
    guardarPreferencias.mockResolvedValue(INICIALES);
    render(<FormularioDePreferencias iniciales={INICIALES} />);

    fireEvent.click(casilla("FACTURACION", "PANEL"));
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(guardarPreferencias).toHaveBeenCalled();
    });
    const enviado = guardarPreferencias.mock.calls[0]![0] as { pref_suscripciones: unknown };
    expect(enviado.pref_suscripciones).toMatchObject({ FACTURACION: ["EMAIL"] });
  });

  it("muestra el ejemplo de fecha, que es lo que la preferencia realmente gobierna", () => {
    render(<FormularioDePreferencias iniciales={INICIALES} />);

    // A dropdown with no visible consequence is a dropdown nobody knows what to do with.
    const ejemplo = screen.getByText(/Así vas a ver las fechas/).textContent ?? "";
    expect(ejemplo).toMatch(/\d{1,2}\/\d{1,2}\/\d{2}/);

    // Every option in the list is a zone `Intl` accepts: an invalid one throws on render.
    for (const zona of ["America/Argentina/Ushuaia", "America/Argentina/Salta"]) {
      fireEvent.change(screen.getByLabelText("Zona horaria"), { target: { value: zona } });
      expect(screen.getByText(/Así vas a ver las fechas/).textContent).toMatch(
        /\d{1,2}\/\d{1,2}\/\d{2}/,
      );
    }
  });

  it("un fallo al guardar se muestra y no se confirma nada", async () => {
    guardarPreferencias.mockRejectedValue(new ErrorDeFormulario("Revisá los datos ingresados."));
    render(<FormularioDePreferencias iniciales={INICIALES} />);

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(screen.getByText("Revisá los datos ingresados.")).toBeDefined();
    });
    expect(screen.queryByText("Listo, tus preferencias quedaron guardadas.")).toBeNull();
  });
});
