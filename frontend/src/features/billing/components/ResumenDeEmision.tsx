/**
 * El resumen de lo que se va a emitir y el botón principal.
 *
 * El botón queda deshabilitado hasta que todo está completo, y **dice por qué**: un botón apagado
 * sin explicación es un callejón sin salida. Acá no hay totales: el importe lo calcula el backend.
 */

import { cuitConGuiones } from "./TarjetaDelReceptor";
import { IconoDeNuevoDocumento } from "./iconosEmision";

export interface PropsDeResumenDeEmision {
  readonly cuit: string | null;
  readonly tipo: string | null;
  readonly punto: string | null;
  readonly cantidadDeItems: number;
  /** Lo que falta para poder emitir, en frases. Vacío cuando se puede. */
  readonly motivos: readonly string[];
  /** `false` hasta que ARCA contestó: antes de eso ni siquiera se ofrece el botón. */
  readonly ofreceEmitir: boolean;
  readonly puedeEmitir: boolean;
  readonly emitiendo: boolean;
}

function Fila({
  rotulo,
  valor,
  mono = false,
}: {
  rotulo: string;
  valor: string | null;
  mono?: boolean;
}): JSX.Element {
  return (
    <div className="fac-em-resumen__fila">
      <dt>{rotulo}</dt>
      <dd className={valor === null ? "fac-em-resumen__vacio" : mono ? "fac-em-resumen__mono" : ""}>
        {valor ?? "—"}
      </dd>
    </div>
  );
}

export function ResumenDeEmision({
  cuit,
  tipo,
  punto,
  cantidadDeItems,
  motivos,
  ofreceEmitir,
  puedeEmitir,
  emitiendo,
}: PropsDeResumenDeEmision): JSX.Element {
  return (
    <aside className="fac-em-resumen" aria-label="Resumen de la emisión">
      <h2 className="fac-em-resumen__titulo">Resumen</h2>
      <dl className="fac-em-resumen__lista">
        <Fila rotulo="CUIT" valor={cuit === null ? null : cuitConGuiones(cuit)} mono />
        <Fila rotulo="Comprobante" valor={tipo} />
        <Fila rotulo="Punto de venta" valor={punto} mono />
        <Fila
          rotulo="Ítems"
          valor={
            cantidadDeItems === 0
              ? null
              : `${cantidadDeItems} cargado${cantidadDeItems === 1 ? "" : "s"}`
          }
        />
      </dl>

      {!ofreceEmitir && (
        <p className="fac-em-resumen__nota">Validá el CUIT del receptor para poder emitir.</p>
      )}

      {ofreceEmitir && (
        <>
          {motivos.length > 0 && (
            <div className="fac-em-resumen__motivos" id="fac-em-motivos">
              <b>Para emitir falta:</b>
              <ul>
                {motivos.map((motivo) => (
                  <li key={motivo}>{motivo}</li>
                ))}
              </ul>
            </div>
          )}
          <button
            type="submit"
            className="fac-em-cta"
            disabled={!puedeEmitir || emitiendo}
            aria-busy={emitiendo}
            aria-describedby={motivos.length > 0 ? "fac-em-motivos" : undefined}
          >
            {emitiendo ? (
              <span className="boton__spinner" aria-hidden="true" />
            ) : (
              <IconoDeNuevoDocumento />
            )}
            Emitir comprobante
          </button>
          <p className="fac-em-resumen__nota">
            Al emitir, ARCA autoriza el comprobante y no se puede editar: se corrige con una nota de
            crédito.
          </p>
        </>
      )}
    </aside>
  );
}
