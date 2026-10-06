/**
 * PAN-FAC-01 — Facturación · Listado (HU-E5-01).
 *
 * Número (con su tipo), cliente, monto, fecha y estado —las columnas que nombra el criterio de
 * aceptación— y los tres filtros de RN-02.
 *
 * **Acá no se suma nada.** Los importes llegan como texto y se muestran como texto; lo que
 * un cliente debe lo decidió el backend y lo autorizó ARCA, y una pantalla que volviera a
 * sumar las líneas terminaría discrepando con el comprobante mismo. Por lo mismo no hay
 * contador por estado ni totalizador al pie: contar sobre `listado.comprobantes` contaría la
 * página y no el período.
 *
 * **El filtro va al servidor, no al arreglo en memoria.** Un listado filtrado en el
 * navegador es un listado que miente apenas se pagina, y éste se va a paginar.
 *
 * **El encabezado vive acá y no en `page.tsx`.** El CTA verde es la acción de esta pantalla
 * y depende del rol; separarlo del título obligaría a pasar `puedeEmitir` dos veces.
 *
 * **Los chips y el `select` de estado son el mismo filtro.** Los dos escriben
 * `filtros.estado` y los dos leen de ahí, así que no pueden mostrar cosas distintas.
 */

"use client";

import { FileText, Plus, SearchX, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alert, Select, SelectorDeFecha } from "@/shared";

import { ErrorDeComprobante, MENSAJE_SIN_RESULTADOS, listarComprobantes } from "../api/comprobante";
import type { FiltrosDeComprobante, ListadoDeComprobantes as Listado } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import type { TipoComprobante } from "../api/puntoDeVenta";
import { TablaDeComprobantes } from "./TablaDeComprobantes";

export interface PropsDeListadoDeComprobantes {
  readonly inicial: Listado;
  /** Administrador and Operador issue; Solo Lectura only looks (HU-E5-01 RN-04). */
  readonly puedeEmitir: boolean;
}

const TIPOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los tipos" },
  ...(Object.keys(ETIQUETAS_DE_TIPO) as TipoComprobante[]).map((valor) => ({
    valor,
    etiqueta: ETIQUETAS_DE_TIPO[valor],
  })),
];

// The three the story names, and only those. `BORRADOR` and `VALIDADO` are states of a
// document nobody has confirmed yet, and offering them as filters would suggest the
// listing is a work queue, which it is not.
const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "AUTORIZADO", etiqueta: "Autorizado" },
  { valor: "ENVIADO_A_ARCA", etiqueta: "Pendiente" },
  { valor: "RECHAZADO", etiqueta: "Error" },
];

/** Los atajos del prototipo: los tres cortes que se miran a diario. */
const CHIPS: readonly { valor: string; etiqueta: string; tono: string }[] = [
  { valor: "", etiqueta: "Todos", tono: "" },
  { valor: "AUTORIZADO", etiqueta: "Autorizados", tono: "autorizado" },
  { valor: "ENVIADO_A_ARCA", etiqueta: "Pendientes", tono: "pendiente" },
  { valor: "RECHAZADO", etiqueta: "Con error", tono: "error" },
];

function hayFiltros(filtros: FiltrosDeComprobante): boolean {
  return [filtros.desde, filtros.hasta, filtros.tipo, filtros.estado].some(
    (valor) => valor !== undefined && valor !== "",
  );
}

function BotonEmitir(): JSX.Element {
  return (
    <Link href="/facturacion/nueva" className="fac-cta">
      <Plus aria-hidden="true" />
      Emitir comprobante
    </Link>
  );
}

function SinComprobantes({ puedeEmitir }: { readonly puedeEmitir: boolean }): JSX.Element {
  return (
    <div className="fac-lst-vacio">
      <span className="fac-lst-vacio__icono" aria-hidden="true">
        <FileText size={26} />
      </span>
      <p className="fac-lst-vacio__titulo">Todavía no emitiste comprobantes.</p>
      <p className="fac-lst-vacio__texto">
        Cuando emitas el primero, vas a verlo acá con su número y su estado.
      </p>
      {puedeEmitir && <BotonEmitir />}
    </div>
  );
}

function SinResultados({ alLimpiar }: { readonly alLimpiar: () => void }): JSX.Element {
  return (
    <div className="fac-lst-vacio">
      <span className="fac-lst-vacio__icono" aria-hidden="true">
        <SearchX size={26} />
      </span>
      <p className="fac-lst-vacio__titulo">{MENSAJE_SIN_RESULTADOS}</p>
      <button type="button" className="fac-lst-limpiar fac-lst-limpiar--solo" onClick={alLimpiar}>
        <X aria-hidden="true" size={14} />
        Limpiar filtros
      </button>
    </div>
  );
}

export function ListadoDeComprobantes({
  inicial,
  puedeEmitir,
}: PropsDeListadoDeComprobantes): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeComprobante>({});
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function consultar(siguientes: FiltrosDeComprobante): Promise<void> {
    setFiltros(siguientes);
    setError(null);
    setCargando(true);
    try {
      setListado(await listarComprobantes(siguientes));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeComprobante ? fallo.message : "No se pudo actualizar el listado.",
      );
    } finally {
      setCargando(false);
    }
  }

  const aplicar = (cambios: FiltrosDeComprobante): Promise<void> =>
    consultar({ ...filtros, ...cambios });
  const limpiar = (): Promise<void> => consultar({});

  const activos = hayFiltros(filtros);
  const total = listado.comprobantes.length;

  return (
    <>
      <header className="fac-lst-encabezado">
        <div className="fac-lst-encabezado__texto">
          <span className="fac-nuevo-encabezado__cintillo">Facturación</span>
          <h1 className="fac-nuevo-encabezado__titulo">Comprobantes</h1>
          <p className="fac-nuevo-encabezado__sub">
            Los que emitiste, con su CAE cuando ARCA los autorizó. Un comprobante autorizado no se
            modifica ni se borra: se reversa con una nota de crédito.
          </p>
        </div>
        {puedeEmitir && <BotonEmitir />}
      </header>

      <div className="fac-nuevo-avisos">
        {error !== null && (
          <Alert tono="error" titulo="No se pudo completar">
            {error}
          </Alert>
        )}
      </div>

      <section className="fac-nuevo-panel fac-lst">
        <div className="fac-lst-barra">
          <div className="fac-lst-seg" role="group" aria-label="Filtros rápidos por estado">
            {CHIPS.map((chip) => (
              <button
                key={chip.etiqueta}
                type="button"
                className={`fac-lst-seg__opcion${chip.tono === "" ? "" : ` fac-lst-seg__opcion--${chip.tono}`}`}
                aria-pressed={(filtros.estado ?? "") === chip.valor}
                onClick={() => void aplicar({ estado: chip.valor })}
              >
                {chip.valor !== "" && <span className="fac-lst-seg__punto" aria-hidden="true" />}
                {chip.etiqueta}
              </button>
            ))}
          </div>
          <p className="fac-lst-cuenta" role="status" aria-live="polite">
            {total === 1 ? "1 comprobante" : `${total} comprobantes`}
          </p>
        </div>

        <div className="fac-lst-filtros">
          <SelectorDeFecha
            id="comprobantes-desde"
            etiqueta="Desde"
            value={filtros.desde ?? ""}
            max={filtros.hasta || undefined}
            alCambiar={(valor) => void aplicar({ desde: valor })}
          />
          <SelectorDeFecha
            id="comprobantes-hasta"
            etiqueta="Hasta"
            value={filtros.hasta ?? ""}
            min={filtros.desde || undefined}
            alCambiar={(valor) => void aplicar({ hasta: valor })}
          />
          <Select
            id="comprobantes-tipo"
            etiqueta="Tipo"
            opciones={TIPOS}
            value={filtros.tipo ?? ""}
            onChange={(evento) => void aplicar({ tipo: evento.target.value })}
          />
          <Select
            id="comprobantes-estado"
            etiqueta="Estado"
            opciones={ESTADOS}
            value={filtros.estado ?? ""}
            onChange={(evento) => void aplicar({ estado: evento.target.value })}
          />
          {activos && (
            <button type="button" className="fac-lst-limpiar" onClick={() => void limpiar()}>
              <X aria-hidden="true" size={14} />
              Limpiar filtros
            </button>
          )}
        </div>

        <div className={cargando ? "fac-nuevo-cargando" : undefined} aria-busy={cargando}>
          {total > 0 && (
            <TablaDeComprobantes filas={listado.comprobantes} puedeEmitir={puedeEmitir} />
          )}
          {total === 0 && activos && <SinResultados alLimpiar={() => void limpiar()} />}
          {total === 0 && !activos && <SinComprobantes puedeEmitir={puedeEmitir} />}
        </div>
      </section>
    </>
  );
}
