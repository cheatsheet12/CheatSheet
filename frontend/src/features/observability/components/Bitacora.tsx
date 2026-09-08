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

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Campo, Select, Tabla } from "@/shared";
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
        <Link className="log-op" href={`/auditoria/${fila.id}`}>
          {fila.accion}
        </Link>
      ),
    },
    {
      clave: "entidad",
      titulo: "Entidad afectada",
      celda: (fila) => <span className="log-ent">{fila.entidad_afectada}</span>,
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
        <Badge estado={tonoDe(fila.resultado)}>{ETIQUETAS_DE_RESULTADO[fila.resultado]}</Badge>
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

      <div className="log-filtros">
        <Campo
          id="log-desde"
          etiqueta="Desde"
          type="date"
          value={filtros.desde ?? ""}
          onChange={(evento) => void aplicar({ desde: evento.target.value })}
        />
        <Campo
          id="log-hasta"
          etiqueta="Hasta"
          type="date"
          value={filtros.hasta ?? ""}
          onChange={(evento) => void aplicar({ hasta: evento.target.value })}
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
