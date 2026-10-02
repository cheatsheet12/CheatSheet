/**
 * «Cobros del período» de PAN-DSH-01: cobrado (con variación), pendiente, en mora y tasa.
 *
 * Son las cuatro cifras de PAN-COB-01, leídas del mismo tablero que Reportes: por eso valen lo
 * mismo en las dos pantallas. **Nada se calcula acá**: la tasa llega redondeada y el cobrado
 * llega neto de reembolsos; esto sólo los formatea.
 */

import { formatearNumero } from "@/shared";

import type { Metrica } from "../api/reporte";
import { Cifra } from "./Cifras";
import { IconoAlerta, IconoBarras, IconoReloj, IconoTarjeta } from "./Iconos";

export interface PropsDeResumenDeCobros {
  readonly cobrado: Metrica;
  readonly pendiente: string;
  readonly enMora: string;
  readonly tasaDeCobro: string;
}

function pesos(valor: string): string {
  return `$ ${formatearNumero(valor)}`;
}

export function ResumenDeCobros({
  cobrado,
  pendiente,
  enMora,
  tasaDeCobro,
}: PropsDeResumenDeCobros): JSX.Element {
  return (
    <section aria-labelledby="resumen-de-cobros">
      <h2 id="resumen-de-cobros" className="dsh-seccion__titulo">
        Cobros del período
      </h2>
      <div className="rep-kpis rep-kpis--cuatro">
        <Cifra
          titulo="Cobrado"
          valor={pesos(cobrado.valor)}
          pie={`Período anterior · ${pesos(cobrado.anterior)}`}
          icono={<IconoTarjeta />}
          tono="menta"
          variacion={cobrado.variacion}
        />
        <Cifra
          titulo="Pendiente de cobro"
          valor={pesos(pendiente)}
          pie="Emitido y todavía sin cobrar"
          icono={<IconoReloj />}
          tono="ambar"
        />
        <Cifra
          titulo="En mora"
          valor={pesos(enMora)}
          pie="Vencido y sin cobrar"
          icono={<IconoAlerta />}
          tono="ambar"
        />
        <Cifra
          titulo="Tasa de cobro"
          valor={`${formatearNumero(tasaDeCobro)} %`}
          pie="Sobre los cobros creados en el período"
          icono={<IconoBarras />}
          tono="tinta"
        />
      </div>
    </section>
  );
}
