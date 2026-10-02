/**
 * PAN-COB-01 — Cobros · Listado (HU-E6-01).
 *
 * Las cuatro métricas del encabezado y el listado con su estado, que es lo que pide el primer
 * criterio de aceptación.
 *
 * **Las etiquetas no son los estados.** La historia es explícita: `APROBADO` se muestra
 * «Pagado» y `VENCIDO` se muestra «En mora». El dominio es la fuente de verdad y esto es
 * presentación — pero el filtro manda el nombre del dominio, porque es lo que el backend
 * entiende.
 *
 * **Nada acá suma nada.** Las métricas llegan calculadas sobre el período entero: sumarlas en
 * el navegador sobre la página mostraría un total que cambia al pasar de hoja.
 *
 * **Los chips y el `select` de estado son el mismo filtro.** Los chips son el atajo a los
 * cuatro estados que alguien mira todo el día; el `select` tiene los cinco del enum y es el
 * control que un lector de pantalla anuncia con su etiqueta. Los dos escriben `filtros.estado`
 * y los dos leen de ahí, así que no pueden mostrar cosas distintas.
 */

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  Alert,
  Badge,
  Campo,
  Card,
  Select,
  Tabla,
  formatearFecha,
  formatearNumero,
} from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  MENSAJE_SIN_RESULTADOS,
  listarCobros,
  tonoDeEstado,
} from "../api/cobro";
import type { Cobro, FiltrosDeCobro, ListadoDeCobros as Listado } from "../api/cobro";
import {
  ICONO_ALERTA,
  ICONO_BARRAS,
  ICONO_RELOJ,
  ICONO_TILDE,
  inicialesDe,
  referenciaDeCobro,
  restoHastaVencimiento,
  varianteDeAvatar,
} from "./presentacion";

export interface PropsDeListadoDeCobros {
  readonly inicial: Listado;
  /** Administrador y Operador generan; Solo Lectura sólo mira (HU-E6-01 RN-04). */
  readonly puedeGestionar: boolean;
}

/**
 * Los cinco estados del enum, con la etiqueta de interfaz de cada uno.
 *
 * El valor que viaja es el del dominio y la etiqueta es lo que se lee: mandar «En mora» al
 * backend obligaría a traducir del otro lado, que es el seam donde una traducción mal hecha
 * hace que un filtro devuelva la lista entera.
 */
const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "APROBADO", etiqueta: "Pagado" },
  { valor: "PENDIENTE", etiqueta: "Pendiente" },
  { valor: "VENCIDO", etiqueta: "En mora" },
  { valor: "CANCELADO", etiqueta: "Cancelado" },
  { valor: "REEMBOLSADO", etiqueta: "Reembolsado" },
];

/**
 * Los chips del prototipo: los cuatro cortes que se miran a diario.
 *
 * **Sin contador.** El prototipo dibuja un número al lado de cada chip; contar sobre
 * `listado.cobros` contaría la página y no el período, y un «3» que cambia al pasar de hoja
 * es peor que no tener número.
 */
const CHIPS: readonly { valor: string; etiqueta: string; modificador: string }[] = [
  { valor: "", etiqueta: "Todos", modificador: "" },
  { valor: "APROBADO", etiqueta: "Pagados", modificador: " cob-chip--pagado" },
  { valor: "PENDIENTE", etiqueta: "Pendientes", modificador: " cob-chip--pendiente" },
  { valor: "VENCIDO", etiqueta: "En mora", modificador: " cob-chip--mora" },
];

export function ListadoDeCobros({ inicial, puedeGestionar }: PropsDeListadoDeCobros): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeCobro>({});
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  /**
   * El día de hoy, y sólo después de montar.
   *
   * «hace 8 días» se calcula contra el reloj, y el servidor y el navegador pueden no estar en
   * el mismo día si el render cae sobre la medianoche. Dejarlo en `null` durante el render del
   * servidor hace imposible ese desacuerdo, al precio de que el resto aparezca un instante
   * después de la fecha — que ya está ahí desde el primer pintado.
   */
  const [hoy, setHoy] = useState<string | null>(null);

  useEffect(() => {
    setHoy(new Date().toISOString().slice(0, 10));
  }, []);

  async function aplicar(cambios: FiltrosDeCobro): Promise<void> {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    setError(null);
    setCargando(true);
    try {
      setListado(await listarCobros(siguientes));
    } catch (fallo) {
      setError(fallo instanceof ErrorDeCobro ? fallo.message : "No se pudo actualizar el listado.");
    } finally {
      setCargando(false);
    }
  }

  const columnas: readonly Columna<Cobro>[] = [
    {
      clave: "concepto",
      titulo: "Concepto",
      celda: (fila) => (
        <span className="cob-celda-cliente">
          {/* El avatar lleva las iniciales del concepto y no las del cliente: el listado no
              trae el nombre del cliente, y una inicial inventada es peor que ninguna. */}
          <span className={`cob-avatar cob-avatar--${varianteDeAvatar(fila.id)}`} aria-hidden>
            {inicialesDe(fila.descripcion)}
          </span>
          <span>
            <Link href={`/cobros/${fila.id}`} className="cob-celda-cliente__nombre">
              {fila.descripcion}
            </Link>
            <span className="cob-celda-cliente__ref">{referenciaDeCobro(fila.id)}</span>
          </span>
        </span>
      ),
    },
    {
      clave: "monto",
      titulo: "Monto",
      celda: (fila) => <span className="cob-importe">$ {formatearNumero(fila.monto)}</span>,
      alDerecha: true,
    },
    {
      clave: "vence",
      titulo: "Vencimiento",
      celda: (fila) => <Vencimiento venceEl={fila.vence_el} hoy={hoy} />,
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDeEstado(fila.estado)}>{ETIQUETAS_DE_ESTADO[fila.estado]}</Badge>
      ),
    },
    {
      clave: "link",
      titulo: "Link de pago",
      celda: (fila) =>
        fila.tiene_link_activo ? (
          <span className="cob-pastilla cob-pastilla--activo">Activo</span>
        ) : (
          <span className="cob-nada">—</span>
        ),
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <div className="cob-metricas">
        <div className="cob-metrica cob-metrica--cobrado">
          <Card titulo="Cobrado">
            <span className="cob-metrica__icono">{ICONO_TILDE}</span>
            <p className="cob-metrica__valor">$ {formatearNumero(listado.metricas.cobrado)}</p>
            <p className="cob-metrica__pie">Cobros aprobados, por fecha de pago.</p>
          </Card>
        </div>
        <div className="cob-metrica cob-metrica--pendiente">
          <Card titulo="Pendiente">
            <span className="cob-metrica__icono">{ICONO_RELOJ}</span>
            <p className="cob-metrica__valor">$ {formatearNumero(listado.metricas.pendiente)}</p>
            <p className="cob-metrica__pie">Todavía dentro del vencimiento.</p>
          </Card>
        </div>
        <div className="cob-metrica cob-metrica--mora">
          <Card titulo="En mora">
            <span className="cob-metrica__icono">{ICONO_ALERTA}</span>
            <p className="cob-metrica__valor">$ {formatearNumero(listado.metricas.en_mora)}</p>
            <p className="cob-metrica__pie">Pasado el vencimiento, sin pago confirmado.</p>
          </Card>
        </div>
        <div className="cob-metrica cob-metrica--tasa">
          <Card titulo="Tasa de cobro">
            <span className="cob-metrica__icono">{ICONO_BARRAS}</span>
            {/* Interpolado entero y no `{numero} %`: partido en dos hijos, un salto de línea
                del formateador se lleva puesto el espacio antes del signo. */}
            <p className="cob-metrica__valor">{`${formatearNumero(listado.metricas.tasa_de_cobro)} %`}</p>
            <p className="cob-metrica__pie">Cobrado sobre emitido, calculado por el backend.</p>
          </Card>
        </div>
      </div>

      <section className="cob-panel">
        <div className="cob-barra">
          <div className="cob-chips" role="group" aria-label="Filtros rápidos por estado">
            {CHIPS.map((chip) => (
              <button
                key={chip.etiqueta}
                type="button"
                className={`cob-chip${chip.modificador}`}
                aria-pressed={(filtros.estado ?? "") === chip.valor}
                onClick={() => void aplicar({ estado: chip.valor })}
              >
                {chip.valor !== "" && <span className="cob-chip__punto" aria-hidden />}
                {chip.etiqueta}
              </button>
            ))}
          </div>
          <div className="cob-barra__espacio" />
          {puedeGestionar && (
            <Link href="/cobros/nuevo" className="boton boton--primario cob-boton-enlace">
              Generar cobro
            </Link>
          )}
        </div>

        <div className="cob-filtros">
          <Campo
            id="cobros-desde"
            etiqueta="Desde"
            type="date"
            value={filtros.desde ?? ""}
            onChange={(evento) => void aplicar({ desde: evento.target.value })}
          />
          <Campo
            id="cobros-hasta"
            etiqueta="Hasta"
            type="date"
            value={filtros.hasta ?? ""}
            onChange={(evento) => void aplicar({ hasta: evento.target.value })}
          />
          <Select
            id="cobros-estado"
            etiqueta="Estado"
            opciones={ESTADOS}
            value={filtros.estado ?? ""}
            onChange={(evento) => void aplicar({ estado: evento.target.value })}
          />
        </div>

        <div className={cargando ? "cob-cargando" : undefined} aria-busy={cargando}>
          <Tabla
            titulo="Cobros del período"
            columnas={columnas}
            filas={listado.cobros}
            claveDeFila={(fila) => fila.id}
            vacia={MENSAJE_SIN_RESULTADOS}
          />
        </div>
      </section>
    </>
  );
}

/** La fecha, y debajo cuánto falta o cuánto hace — en el color de la urgencia. */
function Vencimiento({
  venceEl,
  hoy,
}: {
  readonly venceEl: string;
  readonly hoy: string | null;
}): JSX.Element {
  const resto = hoy === null ? null : restoHastaVencimiento(venceEl, hoy);
  return (
    <>
      <span className="cob-vence__fecha">{formatearFecha(venceEl)}</span>
      {resto !== null && (
        <span className={`cob-vence__resto cob-vence__resto--${resto.tono}`}>{resto.texto}</span>
      )}
    </>
  );
}
