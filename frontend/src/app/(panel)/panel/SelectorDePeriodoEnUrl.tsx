/**
 * El selector de período de Inicio: escribe `desde` y `hasta` en la URL.
 *
 * Es el cliente mínimo que le falta a un componente de servidor. No pide nada por su cuenta:
 * al cambiar la URL, la página vuelve a leer el tablero y **toda** la pantalla sigue el mismo
 * período. Hasta que las dos fechas estén completas no toca la URL (un campo vaciado a la mitad
 * de escribir no es un período).
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SelectorDePeriodo } from "@/features/reporting";
import type { RangoDePeriodo } from "@/features/reporting";

export interface PropsDeSelectorDePeriodoEnUrl {
  readonly desde: string;
  readonly hasta: string;
  /** El período que contestó el backend, ya formateado. */
  readonly resumen: string;
}

export function SelectorDePeriodoEnUrl({
  desde,
  hasta,
  resumen,
}: PropsDeSelectorDePeriodoEnUrl): JSX.Element {
  const router = useRouter();
  const [rango, setRango] = useState<RangoDePeriodo>({ desde, hasta });

  function cambiar(cambios: RangoDePeriodo): void {
    const siguiente = { ...rango, ...cambios };
    setRango(siguiente);
    if (!siguiente.desde || !siguiente.hasta) {
      return;
    }
    const consulta = new URLSearchParams({ desde: siguiente.desde, hasta: siguiente.hasta });
    router.replace(`/panel?${consulta.toString()}`);
  }

  return <SelectorDePeriodo rango={rango} resumen={resumen} alCambiar={cambiar} />;
}
