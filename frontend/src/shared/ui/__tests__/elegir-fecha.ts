/**
 * Auxiliar de tests: elige una fecha en el `SelectorDeFecha` como lo haría una persona, abriendo
 * el calendario y yendo mes a mes hasta que el día esté en la grilla. El calendario arranca en
 * el mes de la fecha elegida o, si no hay, en el de hoy.
 */

import { fireEvent, screen, within } from "@testing-library/react";

const TOPE_DE_MESES = 240;

export function elegirFecha(etiqueta: string, iso: string): void {
  fireEvent.click(screen.getByLabelText(etiqueta));
  for (let paso = 0; paso < TOPE_DE_MESES; paso += 1) {
    const panel = screen.getByRole("dialog", { name: `Elegir ${etiqueta.toLowerCase()}` });
    const dia = panel.querySelector<HTMLButtonElement>(`[data-iso="${iso}"][data-afuera="false"]`);
    if (dia !== null) {
      fireEvent.click(dia);
      return;
    }
    const primera = panel.querySelector<HTMLElement>("[data-iso]")?.dataset["iso"] ?? iso;
    const nombre = iso < primera ? "Mes anterior" : "Mes siguiente";
    fireEvent.click(within(panel).getByRole("button", { name: nombre }));
  }
  throw new Error(`No se llegó a ${iso} en el calendario.`);
}
