/**
 * PAN-LOG-01 — Log de Operaciones · Listado (HU-E12-01).
 *
 * La tabla de todo lo que el sistema ejecutó en nombre de la empresa, con los cinco filtros
 * que RN-03 pide: rango de fechas, módulo, estado, iniciador y búsqueda por texto.
 *
 * **El iniciador es la columna que hace que esta pantalla valga la pena.** Distingue si una
 * operación la ejecutó una persona, un barrido del sistema o el agente de WhatsApp sobre el
 * mensaje de un cliente (RN-02) — y esa última es la que alguien viene a buscar después de una
 * conversación rara.
 *
 * **Los filtros mandan lo mismo que la tabla muestra.** El valor que viaja es `identity`,
 * `ia`, `error`: el mismo texto que llegó. Traducir de un lado y no del otro es cómo un filtro
 * termina devolviendo la lista entera sin que nadie lo note.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, Campo, Select, Tabla, formatearFechaHora } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_INICIADOR,
  ETIQUETAS_DE_MODULO,
  ETIQUETAS_DE_RESULTADO,
  ErrorDeBitacora,
  MENSAJE_SIN_OPERACIONES,
  TAMANO_DE_PAGINA,
  listarOperaciones,
} from "../api/bitacora";
import type { FiltrosDeBitacora, ListadoDeOperaciones, Operacion } from "../api/bitacora";

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

export function Bitacora({ inicial }: PropsDeBitacora): JSX.Element {
  const [listado, setListado] = useState<ListadoDeOperaciones>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeBitacora>({});
  const [error, setError] = useState<string | null>(null);

  const pagina = filtros.pagina ?? 1;
  const ultimaPagina = Math.max(1, Math.ceil(listado.total / TAMANO_DE_PAGINA));

  async function aplicar(cambios: FiltrosDeBitacora): Promise<void> {
    // Cualquier cambio de filtro vuelve a la primera página: quedarse en la cuarta de un
    // resultado que ahora tiene dos muestra una tabla vacía que parece un error.
    const siguientes = { ...filtros, ...cambios, pagina: cambios.pagina ?? 1 };
    setFiltros(siguientes);
    setError(null);
    try {
      setListado(await listarOperaciones(siguientes));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeBitacora ? fallo.message : "No se pudo consultar la bitácora.",
      );
    }
  }

  const columnas: readonly Columna<Operacion>[] = [
    {
      clave: "timestamp",
      titulo: "Momento",
      celda: (fila) => formatearFechaHora(fila.timestamp),
    },
    {
      clave: "modulo",
      titulo: "Módulo",
      celda: (fila) => ETIQUETAS_DE_MODULO[fila.modulo] ?? fila.modulo,
    },
    {
      clave: "accion",
      titulo: "Operación",
      celda: (fila) => <Link href={`/auditoria/${fila.id}`}>{fila.accion}</Link>,
    },
    { clave: "entidad", titulo: "Entidad", celda: (fila) => fila.entidad_afectada },
    {
      clave: "iniciador",
      titulo: "Iniciador",
      celda: (fila) => ETIQUETAS_DE_INICIADOR[fila.iniciador],
    },
    {
      clave: "resultado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDe(fila.resultado)}>{ETIQUETAS_DE_RESULTADO[fila.resultado]}</Badge>
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

      <div className="rep-filtros">
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
        <Campo
          id="log-texto"
          etiqueta="Buscar"
          type="search"
          value={filtros.texto ?? ""}
          ayuda="Por operación o entidad afectada."
          onChange={(evento) => void aplicar({ texto: evento.target.value })}
        />
      </div>

      <Tabla
        titulo="Operaciones registradas"
        columnas={columnas}
        filas={listado.operaciones}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_OPERACIONES}
      />

      {listado.total > TAMANO_DE_PAGINA && (
        <div className="rep-acciones">
          <Button
            variante="secundario"
            disabled={pagina <= 1}
            onClick={() => void aplicar({ pagina: pagina - 1 })}
          >
            Anterior
          </Button>
          <p className="rep-comparacion">
            Página {pagina} de {ultimaPagina} · {listado.total} operaciones
          </p>
          <Button
            variante="secundario"
            disabled={pagina >= ultimaPagina}
            onClick={() => void aplicar({ pagina: pagina + 1 })}
          >
            Siguiente
          </Button>
        </div>
      )}
    </>
  );
}
