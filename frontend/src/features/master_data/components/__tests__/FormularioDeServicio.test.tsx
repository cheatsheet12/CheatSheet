/**
 * @vitest-environment jsdom
 *
 * El formulario de PAN-DM-02, y las dos cosas que tiene que hacer bien.
 *
 * **El precio sale como texto.** Es la mitad de la defensa contra el `float` en el
 * dinero: la otra mitad la pone el backend rechazando un número JSON, pero si el panel lo
 * manda como `number` el usuario ve un 422 sin entender por qué.
 *
 * **La duración aparece y desaparece con el checkbox.** El agregado borra la duración
 * cuando el servicio deja de ser agendable, así que un campo que siguiera en pantalla
 * mostraría un valor que el backend ya descartó.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DatosDeServicio, Servicio } from "@/features/master_data";
import { FormularioDeServicio } from "@/features/master_data";

const CORTE: Servicio = {
  id: "3f1c2b8e-0000-4000-8000-000000000020",
  nombre: "Corte de pelo",
  precio: "5000.00",
  alicuota_iva: "0.21",
  agendable: true,
  duracion_estandar_min: 45,
  origen: "PANEL",
  activo: true,
};

afterEach(cleanup);

/**
 * Lo que el formulario le pasó a `onGuardar`, con el índice comprobado.
 *
 * `mock.calls[0]` es `T | undefined` bajo `noUncheckedIndexedAccess`, y en un test eso es
 * información útil: si el formulario no llamó, el error dice eso y no «undefined».
 */
function datosDe(onGuardar: ReturnType<typeof vi.fn>): DatosDeServicio {
  const [primera] = onGuardar.mock.calls;
  if (primera === undefined) {
    throw new Error("onGuardar no fue llamado");
  }
  return primera[0] as DatosDeServicio;
}

function montar(onGuardar = vi.fn().mockResolvedValue(undefined), servicio?: Servicio): void {
  render(
    <FormularioDeServicio
      {...(servicio !== undefined ? { servicio } : {})}
      onGuardar={onGuardar}
      onCancelar={() => undefined}
    />,
  );
}

describe("FormularioDeServicio", () => {
  it("el precio es un campo de texto, no uno numerico", () => {
    montar();

    const precio = screen.getByLabelText(/Precio sin IVA/);
    expect(precio.getAttribute("type")).not.toBe("number");
  });

  it("manda el precio como string", async () => {
    const onGuardar = vi.fn().mockResolvedValue(undefined);
    montar(onGuardar);

    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Shampoo" } });
    fireEvent.change(screen.getByLabelText(/Precio sin IVA/), { target: { value: "3000.50" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

    await waitFor(() => {
      expect(onGuardar).toHaveBeenCalled();
    });
    const datos = datosDe(onGuardar);
    expect(typeof datos.precio).toBe("string");
    expect(datos.precio).toBe("3000.50");
  });

  it("la duracion no esta en pantalla mientras el servicio no es agendable", () => {
    montar();

    expect(screen.queryByLabelText(/Duración estándar/)).toBeNull();
  });

  it("marcar agendable hace aparecer la duracion", () => {
    montar();

    fireEvent.click(screen.getByLabelText(/Se puede reservar por agenda/));

    expect(screen.getByLabelText(/Duración estándar/)).toBeDefined();
  });

  it("desmarcar agendable manda duracion nula, no la ultima que se escribio", async () => {
    const onGuardar = vi.fn().mockResolvedValue(undefined);
    montar(onGuardar, CORTE);

    fireEvent.click(screen.getByLabelText(/Se puede reservar por agenda/));
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(onGuardar).toHaveBeenCalled();
    });
    const datos = datosDe(onGuardar);
    expect(datos.agendable).toBe(false);
    expect(datos.duracion_estandar_min).toBeNull();
  });

  it("una duracion vacia viaja como null y la decide el backend", async () => {
    const onGuardar = vi.fn().mockResolvedValue(undefined);
    montar(onGuardar);

    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Corte" } });
    fireEvent.change(screen.getByLabelText(/Precio sin IVA/), { target: { value: "5000" } });
    fireEvent.click(screen.getByLabelText(/Se puede reservar por agenda/));
    fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

    await waitFor(() => {
      expect(onGuardar).toHaveBeenCalled();
    });
    const datos = datosDe(onGuardar);
    expect(datos.agendable).toBe(true);
    expect(datos.duracion_estandar_min).toBeNull();
  });

  it.each([
    ["12.7", "12.7"],
    ["99999abc", "99999abc"],
    ["12,5", "12,5"],
  ])(
    "no trunca en silencio la duracion %s: la manda tal cual para que el backend la rechace",
    async (escrito, enviado) => {
      const onGuardar = vi.fn().mockResolvedValue(undefined);
      montar(onGuardar);

      fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Corte" } });
      fireEvent.change(screen.getByLabelText(/Precio sin IVA/), { target: { value: "5000" } });
      fireEvent.click(screen.getByLabelText(/Se puede reservar por agenda/));
      fireEvent.change(screen.getByLabelText(/Duración estándar/), { target: { value: escrito } });
      fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

      await waitFor(() => {
        expect(onGuardar).toHaveBeenCalled();
      });
      expect(datosDe(onGuardar).duracion_estandar_min).toBe(enviado);
    },
  );

  it("una duracion escrita solo con digitos viaja como numero", async () => {
    const onGuardar = vi.fn().mockResolvedValue(undefined);
    montar(onGuardar);

    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: "Corte" } });
    fireEvent.change(screen.getByLabelText(/Precio sin IVA/), { target: { value: "5000" } });
    fireEvent.click(screen.getByLabelText(/Se puede reservar por agenda/));
    fireEvent.change(screen.getByLabelText(/Duración estándar/), { target: { value: " 45 " } });
    fireEvent.click(screen.getByRole("button", { name: "Crear servicio" }));

    await waitFor(() => {
      expect(onGuardar).toHaveBeenCalled();
    });
    expect(datosDe(onGuardar).duracion_estandar_min).toBe(45);
  });

  it("la ayuda de la duracion dice el rango de 5 a 480 minutos", () => {
    montar(vi.fn(), CORTE);

    expect(screen.getByText(/Entre 5 y 480 minutos\./)).toBeDefined();
  });

  it("muestra el mensaje de rango que devuelve el backend", () => {
    render(
      <FormularioDeServicio
        servicio={CORTE}
        onGuardar={async () => undefined}
        onCancelar={() => undefined}
        error="La duracion debe estar entre 5 y 480 minutos."
      />,
    );

    expect(screen.getByText("La duracion debe estar entre 5 y 480 minutos.")).toBeDefined();
  });

  it("ofrece las tres alicuotas de la regla y ninguna mas", () => {
    montar();

    const opciones = screen
      .getAllByRole("option")
      .map((opcion) => (opcion as HTMLOptionElement).value);

    expect(opciones).toEqual(["0.00", "0.105", "0.21"]);
  });

  it("editar precarga los datos del servicio", () => {
    montar(vi.fn(), CORTE);

    expect((screen.getByLabelText(/^Nombre/) as HTMLInputElement).value).toBe("Corte de pelo");
    expect((screen.getByLabelText(/Precio sin IVA/) as HTMLInputElement).value).toBe("5000.00");
    expect((screen.getByLabelText(/Duración estándar/) as HTMLInputElement).value).toBe("45");
  });

  it("muestra el error que le pasan", () => {
    render(
      <FormularioDeServicio
        onGuardar={async () => undefined}
        onCancelar={() => undefined}
        error="El precio debe ser mayor a cero."
      />,
    );

    expect(screen.getByText("El precio debe ser mayor a cero.")).toBeDefined();
  });
});
