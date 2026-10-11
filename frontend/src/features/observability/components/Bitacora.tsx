/**
 * PAN-LOG-01 — Log de Operaciones · Listado (HU-E12-01).
 *
 * La tabla de todo lo que el sistema ejecutó en nombre de la empresa, con los cinco filtros
 * que RN-03 pide: rango de fechas, módulo, estado, iniciador y búsqueda por texto.
 *
 * **El iniciador es la columna que hace que esta pantalla valga la pena.** Distingue si una
 * operación la ejecutó una persona, un barrido del sistema o el agente de WhatsApp sobre el
 * mensaje de un cliente (RN-02) — y esa última es la que alguien viene a buscar después de una
 * conversación rara. Por eso el agente de IA lleva marca propia (ver `MarcasDeOperacion`).
 *
 * **Los filtros mandan lo mismo que la tabla muestra.** El valor que viaja es `identity`,
 * `ia`, `error`: el mismo texto que llegó. Traducir de un lado y no del otro es cómo un filtro
 * termina devolviendo la lista entera sin que nadie lo note.
 *
 * **Las etiquetas de los filtros se ven.** El prototipo las mete adentro del control
 * («Módulo: Todos»); §1.4 de la especificación pide etiqueta visible en todo campo de
 * formulario, y un `<label>` real es además lo que un lector de pantalla anuncia.
 */

"use client";

import { Bot, CircleAlert, CircleCheck, ListFilter, RefreshCw, ScrollText, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Campo, Select, SelectorDeFecha, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_MODULO,
  ETIQUETAS_DE_RESULTADO,
  ErrorDeBitacora,
  MENSAJE_SIN_OPERACIONES,
  TAMANO_DE_PAGINA,
  listarOperaciones,
} from "../api/bitacora";
import type { FiltrosDeBitacora, ListadoDeOperaciones, Operacion } from "../api/bitacora";
import { entidadLegible, nombreDeAccion } from "./formato";
import { MarcaDeIniciador, MarcaDeModulo, MomentoDeOperacion } from "./MarcasDeOperacion";

export interface PropsDeBitacora {
  readonly inicial: ListadoDeOperaciones;
}

const MODULOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los módulos" },
  ...Object.entries(ETIQUETAS_DE_MODULO).map(([valor, etiqueta]) => ({ valor, etiqueta })),
];

const RESULTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "completado", etiqueta: "Completado" },
  { valor: "error", etiqueta: "Error" },
];

const INICIADORES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Cualquier iniciador" },
  { valor: "usuario", etiqueta: "Usuario" },
  { valor: "sistema", etiqueta: "Sistema" },
  { valor: "ia", etiqueta: "Agente IA" },
];

function tonoDe(resultado: Operacion["resultado"]): EstadoDeBadge {
  return resultado === "error" ? "error" : "ok";
}

/**
 * Qué números muestra el paginador.
 *
 * Primera, última y la vecindad de la actual. Listar 238 páginas es una fila de botones que
 * nadie puede apuntar; estas cinco cubren los dos saltos que alguien realmente hace —al
 * principio y al final— sin ocupar la pantalla.
 */
export function paginasVisibles(actual: number, ultima: number): readonly number[] {
  const candidatas = [1, actual - 1, actual, actual + 1, ultima];
  const dentro = candidatas.filter((numero) => numero >= 1 && numero <= ultima);
  return [...new Set(dentro)].sort((una, otra) => una - otra);
}

export function Bitacora({ inicial }: PropsDeBitacora): JSX.Element {
  const [listado, setListado] = useState<ListadoDeOperaciones>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeBitacora>({});
  const [error, setError] = useState<string | null>(null);
  const [consultando, setConsultando] = useState(false);

  const pagina = filtros.pagina ?? 1;
  const ultimaPagina = Math.max(1, Math.ceil(listado.total / TAMANO_DE_PAGINA));
  const primeraFila = listado.operaciones.length === 0 ? 0 : (pagina - 1) * TAMANO_DE_PAGINA + 1;
  const ultimaFila = (pagina - 1) * TAMANO_DE_PAGINA + listado.operaciones.length;

  async function aplicar(cambios: FiltrosDeBitacora): Promise<void> {
    // Cualquier cambio de filtro vuelve a la primera página: quedarse en la cuarta de un
    // resultado que ahora tiene dos muestra una tabla vacía que parece un error.
    const siguientes = { ...filtros, ...cambios, pagina: cambios.pagina ?? 1 };
    setFiltros(siguientes);
    setError(null);
    setConsultando(true);
    try {
      setListado(await listarOperaciones(siguientes));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeBitacora ? fallo.message : "No se pudo consultar la bitácora.",
      );
    } finally {
      setConsultando(false);
    }
  }

  async function limpiar(): Promise<void> {
    await aplicar({
      desde: "",
      hasta: "",
      modulo: "",
      resultado: "",
      iniciador: "",
      texto: "",
    });
  }

  const filtrosActivos = [
    filtros.desde,
    filtros.hasta,
    filtros.modulo,
    filtros.resultado,
    filtros.iniciador,
    filtros.texto,
  ].filter((valor) => valor !== undefined && valor !== "").length;

  // Los tres contadores de abajo cuentan lo que hay en esta página, no en todo el log: el
  // backend devuelve una página por vez y sumar el resto exigiría otra consulta. Por eso las
  // tarjetas lo dicen en su etiqueta.
  const enPagina = listado.operaciones;
  const conError = enPagina.filter((fila) => fila.resultado === "error").length;
  const completadas = enPagina.length - conError;
  const delAgente = enPagina.filter((fila) => fila.iniciador === "ia").length;

  const columnas: readonly Columna<Operacion>[] = [
    {
      clave: "timestamp",
      titulo: "Momento",
      celda: (fila) => <MomentoDeOperacion iso={fila.timestamp} />,
    },
    {
      clave: "modulo",
      titulo: "Módulo",
      celda: (fila) => <MarcaDeModulo modulo={fila.modulo} />,
    },
    {
      clave: "accion",
      titulo: "Operación",
      celda: (fila) => (
        <span className="log-op-celda">
          <Link className="log-op" href={`/auditoria/${fila.id}`}>
            {nombreDeAccion(fila.accion)}
          </Link>
          <code className="log-op-codigo">{fila.accion}</code>
        </span>
      ),
    },
    {
      clave: "entidad",
      titulo: "Entidad afectada",
      celda: (fila) => {
        const legible = entidadLegible(fila.entidad_afectada);
        if (legible === null) {
          return <span className="log-ent">{fila.entidad_afectada}</span>;
        }
        return (
          <span className="log-ent-celda" title={fila.entidad_afectada}>
            <span className="log-ent-celda__tipo">{legible.tipo}</span>
            <span className="log-ent">{legible.corto}</span>
          </span>
        );
      },
    },
    {
      clave: "iniciador",
      titulo: "Iniciado por",
      celda: (fila) => <MarcaDeIniciador iniciador={fila.iniciador} />,
    },
    {
      clave: "resultado",
      titulo: "Estado",
      celda: (fila) => (
        <span className={`log-estado log-estado--${fila.resultado}`}>
          <Badge estado={tonoDe(fila.resultado)}>{ETIQUETAS_DE_RESULTADO[fila.resultado]}</Badge>
        </span>
      ),
    },
    {
      clave: "ver",
      titulo: "",
      alDerecha: true,
      celda: (fila) => (
        // El chevron del prototipo, con nombre accesible: un enlace cuyo único contenido es
        // «›» se anuncia como «enlace, ›», que no dice a dónde va.
        <Link className="log-ver" href={`/auditoria/${fila.id}`}>
          <span className="solo-lectores">Ver el detalle de {fila.accion}</span>
          <span aria-hidden="true">›</span>
        </Link>
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

      <div className="log-resumen">
        <div className="log-dato" style={{ "--i": 0 } as React.CSSProperties}>
          <span className="log-dato__icono">
            <ScrollText size={18} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="log-dato__texto">
            <b>{listado.total}</b>
            <small>
              {filtrosActivos > 0 ? "Registros con estos filtros" : "Registros en total"}
            </small>
          </span>
        </div>
        <div className="log-dato" style={{ "--i": 1 } as React.CSSProperties}>
          <span className="log-dato__icono log-dato__icono--ok">
            <CircleCheck size={18} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="log-dato__texto">
            <b>{completadas}</b>
            <small>Completadas en esta página</small>
          </span>
        </div>
        <div className="log-dato" style={{ "--i": 2 } as React.CSSProperties}>
          <span className={`log-dato__icono${conError > 0 ? " log-dato__icono--error" : ""}`}>
            <CircleAlert size={18} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="log-dato__texto">
            <b>{conError}</b>
            <small>Con error en esta página</small>
          </span>
        </div>
        <div className="log-dato" style={{ "--i": 3 } as React.CSSProperties}>
          <span className="log-dato__icono log-dato__icono--ia">
            <Bot size={18} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="log-dato__texto">
            <b>{delAgente}</b>
            <small>Del agente de IA en esta página</small>
          </span>
        </div>
      </div>

      <div className="log-filtros-caja">
        <div className="log-filtros-caja__cab">
          <span className="log-filtros-caja__titulo">
            <ListFilter size={16} strokeWidth={2} aria-hidden="true" />
            Filtros
            {filtrosActivos > 0 && <em>{filtrosActivos}</em>}
          </span>
          {filtrosActivos > 0 && (
            <button
              type="button"
              className="log-limpiar"
              disabled={consultando}
              onClick={() => void limpiar()}
            >
              <X size={14} strokeWidth={2.4} aria-hidden="true" />
              Limpiar filtros
            </button>
          )}
        </div>
        <div className="log-filtros">
          <SelectorDeFecha
            id="log-desde"
            etiqueta="Desde"
            value={filtros.desde ?? ""}
            max={filtros.hasta || undefined}
            alCambiar={(valor) => void aplicar({ desde: valor })}
          />
          <SelectorDeFecha
            id="log-hasta"
            etiqueta="Hasta"
            value={filtros.hasta ?? ""}
            min={filtros.desde || undefined}
            alCambiar={(valor) => void aplicar({ hasta: valor })}
          />
          <Select
            id="log-modulo"
            etiqueta="Módulo"
            opciones={MODULOS}
            value={filtros.modulo ?? ""}
            onChange={(evento) => void aplicar({ modulo: evento.target.value })}
          />
          <Select
            id="log-resultado"
            etiqueta="Estado"
            opciones={RESULTADOS}
            value={filtros.resultado ?? ""}
            onChange={(evento) => void aplicar({ resultado: evento.target.value })}
          />
          <Select
            id="log-iniciador"
            etiqueta="Iniciador"
            opciones={INICIADORES}
            value={filtros.iniciador ?? ""}
            onChange={(evento) => void aplicar({ iniciador: evento.target.value })}
          />
          <div className="log-filtros__ancho">
            <Campo
              id="log-texto"
              etiqueta="Buscar"
              type="search"
              placeholder="Operación, entidad afectada, CAE…"
              value={filtros.texto ?? ""}
              onChange={(evento) => void aplicar({ texto: evento.target.value })}
            />
          </div>
        </div>
      </div>

      <div className="log-barra">
        <p className="log-barra__cuenta">
          {listado.total} {listado.total === 1 ? "registro" : "registros"}
        </p>
        <button
          type="button"
          className="log-accion"
          disabled={consultando}
          onClick={() => void aplicar({ pagina })}
        >
          <RefreshCw
            size={14}
            strokeWidth={2.2}
            aria-hidden="true"
            className={consultando ? "log-girar" : undefined}
          />
          Actualizar
        </button>
      </div>

      <div className="log-panel">
        <Tabla
          titulo="Operaciones registradas"
          columnas={columnas}
          filas={listado.operaciones}
          claveDeFila={(fila) => fila.id}
          vacia={MENSAJE_SIN_OPERACIONES}
        />

        {listado.operaciones.length > 0 && (
          <div className="log-pager">
            <p className="log-pager__resumen">
              Mostrando{" "}
              <b>
                {primeraFila}–{ultimaFila}
              </b>{" "}
              de <b>{listado.total}</b>
            </p>
            {ultimaPagina > 1 && (
              <div className="log-pager__paginas">
                <button
                  type="button"
                  className="log-pg"
                  disabled={pagina <= 1}
                  onClick={() => void aplicar({ pagina: pagina - 1 })}
                >
                  Anterior
                </button>
                {paginasVisibles(pagina, ultimaPagina).map((numero, indice, todas) => (
                  <span key={numero} className="log-pager__paginas">
                    {indice > 0 && numero - (todas[indice - 1] ?? 0) > 1 && (
                      <span className="log-pager__elipsis" aria-hidden="true">
                        …
                      </span>
                    )}
                    <button
                      type="button"
                      className="log-pg"
                      aria-label={`Página ${numero}`}
                      aria-current={numero === pagina ? "page" : undefined}
                      onClick={() => void aplicar({ pagina: numero })}
                    >
                      {numero}
                    </button>
                  </span>
                ))}
                <button
                  type="button"
                  className="log-pg"
                  disabled={pagina >= ultimaPagina}
                  onClick={() => void aplicar({ pagina: pagina + 1 })}
                >
                  Siguiente
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
