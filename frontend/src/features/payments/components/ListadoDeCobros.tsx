/**
 * PAN-COB-01 — Cobros · Listado (HU-E6-01).
 *
 * El encabezado con «Nuevo cobro», las cuatro métricas, la barra de filtros y el listado con su
 * estado, que es lo que pide el primer criterio de aceptación.
 *
 * **Las etiquetas no son los estados.** La historia es explícita: `APROBADO` se muestra
 * «Pagado» y `VENCIDO` se muestra «En mora». El dominio es la fuente de verdad y esto es
 * presentación — pero el filtro manda el nombre del dominio, porque es lo que el backend
 * entiende.
 *
 * **Nada acá suma nada.** Las métricas llegan calculadas sobre el período entero: sumarlas en
 * el navegador sobre las filas mostraría un total que cambia con el filtro. El monto de cada
 * fila es el texto que mandó la API.
 *
 * **La fila entera lleva al detalle**, y lo hace con un enlace de verdad: el concepto es un
 * `<a>` y su zona clicable se estira sobre toda la fila (`::after`). Así funciona con teclado y
 * lector de pantalla sin un `onClick` en el `<tr>`, y los botones de la fila (copiar, ⋯) quedan
 * por encima y no navegan.
 *
 * **Acciones.** Desde el listado se puede ver el detalle, copiar y abrir el link. Cancelar y
 * reembolsar siguen siendo del detalle: piden motivo, monto y confirmación, y un diálogo así
 * sobre una fila de tabla se aprieta por error.
 */

"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert, Badge, Card, Tabla, formatearFecha, formatearNumero } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  MENSAJE_LINK_COPIADO,
  MENSAJE_SIN_RESULTADOS,
  copiarLink,
  listarCobros,
  tonoDeEstado,
} from "../api/cobro";
import type { Cobro, FiltrosDeCobro, ListadoDeCobros as Listado } from "../api/cobro";
import { HerramientasDeCobros, hayFiltrosActivos } from "./HerramientasDeCobros";
import { LinkDePago, MenuDeCobro, VacioDeCobros, linkDe } from "./PiezasDeListadoDeCobros";
import type { ResultadoDeCopia } from "./PiezasDeListadoDeCobros";
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

/** Cuánto dura el «✓ Copiado» en el botón antes de volver a «Copiar link». */
const MS_DE_AVISO = 2200;

/** Los estados en los que un vencimiento todavía dice algo: pagado o cancelado, no. */
const ESTADOS_CON_VENCIMIENTO: readonly string[] = ["PENDIENTE", "VENCIDO"];

export function ListadoDeCobros({ inicial, puedeGestionar }: PropsDeListadoDeCobros): JSX.Element {
  const router = useRouter();
  const [listado, setListado] = useState<Listado>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeCobro>({});
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [copia, setCopia] = useState<{ id: string; resultado: "copiado" | "fallo" } | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);
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
    return () => {
      if (temporizador.current !== null) {
        clearTimeout(temporizador.current);
      }
    };
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

  function limpiar(): void {
    void aplicar({ estado: "", desde: "", hasta: "" });
  }

  /** Copia el link y lo dice en la fila; si no se pudo, también: callar parece que copió. */
  async function copiar(cobro: Cobro): Promise<void> {
    const url = linkDe(cobro);
    if (url === null) {
      return;
    }
    const copiado = await copiarLink(url);
    setCopia({ id: cobro.id, resultado: copiado ? "copiado" : "fallo" });
    if (temporizador.current !== null) {
      clearTimeout(temporizador.current);
    }
    temporizador.current = setTimeout(() => setCopia(null), MS_DE_AVISO);
  }

  function resultadoDe(cobro: Cobro): ResultadoDeCopia {
    return copia?.id === cobro.id ? copia.resultado : null;
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
            <Link href={`/cobros/${fila.id}`} className="cob-celda-cliente__nombre cob-lst-enlace">
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
      celda: (fila) => <Vencimiento cobro={fila} hoy={hoy} />,
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
      celda: (fila) => (
        <LinkDePago cobro={fila} resultado={resultadoDe(fila)} onCopiar={() => void copiar(fila)} />
      ),
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) => (
        <MenuDeCobro
          cobro={fila}
          onVer={() => router.push(`/cobros/${fila.id}`)}
          onCopiar={() => void copiar(fila)}
        />
      ),
    },
  ];

  const botonNuevo = (compacto: boolean): JSX.Element => (
    <Link href="/cobros/nuevo" className={`cob-lst-cta${compacto ? " cob-lst-cta--compacto" : ""}`}>
      <span className="cob-lst-cta__icono" aria-hidden="true">
        <Plus size={14} strokeWidth={2.6} />
      </span>
      Nuevo cobro
    </Link>
  );

  return (
    <>
      <header className="cob-lst-encabezado">
        <div>
          <p className="cob-lst-encabezado__eyebrow">Operaciones · Cobros</p>
          <h1>Cobros</h1>
          <p className="cob-lst-encabezado__intro">
            Lo cobrado, lo pendiente y lo que está en mora, con la cadena de recordatorios corriendo
            sola según la regla que configuraste.
          </p>
        </div>
        {puedeGestionar && <div className="cob-lst-encabezado__acciones">{botonNuevo(false)}</div>}
      </header>

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

      <HerramientasDeCobros
        filtros={filtros}
        total={listado.cobros.length}
        onCambiar={(cambios) => void aplicar(cambios)}
        onLimpiar={limpiar}
      />

      <section
        className={`cob-lst-panel${cargando ? " cob-cargando" : ""}`}
        aria-busy={cargando}
        aria-label="Cobros del período"
      >
        {listado.cobros.length === 0 ? (
          <VacioDeCobros
            hayFiltros={hayFiltrosActivos(filtros)}
            puedeGestionar={puedeGestionar}
            mensajeDeFiltro={MENSAJE_SIN_RESULTADOS}
            alNuevo={botonNuevo(true)}
            onLimpiar={limpiar}
          />
        ) : (
          <Tabla
            titulo="Cobros del período"
            columnas={columnas}
            filas={listado.cobros}
            claveDeFila={(fila) => fila.id}
            vacia={MENSAJE_SIN_RESULTADOS}
          />
        )}
      </section>

      {/* Lo que dice el botón, dicho también para quien no lo mira. */}
      <p className="solo-lectores" role="status">
        {copia === null
          ? ""
          : copia.resultado === "copiado"
            ? MENSAJE_LINK_COPIADO
            : "No se pudo copiar. Abrí el cobro y copialo a mano."}
      </p>
    </>
  );
}

/**
 * La fecha y, debajo, cuánto falta o cuánto hace — en el color de la urgencia.
 *
 * Sólo en los cobros que siguen abiertos: «hace 30 días» en rojo sobre un cobro ya pagado
 * diría que hay una deuda que no existe. Ni el color ni las palabras son lógica de negocio
 * nueva: salen de `restoHastaVencimiento`, que compara la fecha con hoy y nada más.
 */
function Vencimiento({
  cobro,
  hoy,
}: {
  readonly cobro: Cobro;
  readonly hoy: string | null;
}): JSX.Element {
  const resto =
    hoy === null || !ESTADOS_CON_VENCIMIENTO.includes(cobro.estado)
      ? null
      : restoHastaVencimiento(cobro.vence_el, hoy);
  return (
    <>
      <span className="cob-vence__fecha">{formatearFecha(cobro.vence_el)}</span>
      {resto !== null && (
        <span className={`cob-vence__resto cob-vence__resto--${resto.tono}`}>{resto.texto}</span>
      )}
    </>
  );
}
