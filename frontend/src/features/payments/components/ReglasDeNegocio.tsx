/**
 * PAN-CFG-RN — Configuración · Reglas de negocio (HU-E11-01).
 *
 * La cadena de escalamiento, que es la única de los tres tipos que el épico 6 usa. Los otros
 * dos aparecen en el listado con su estado —la historia pide verlos— y su edición llega con
 * el épico que los consuma.
 *
 * **Los días se cuentan desde el vencimiento**, no desde el paso anterior, y la pantalla lo
 * dice: es lo que hace legible una cadena de «a los 3, a los 7, a los 15» y lo que evita que
 * alguien configure algo distinto de lo que cree.
 */

"use client";

import { useId, useState } from "react";

import { Alert, Badge, Button, Campo, Card, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  CANALES,
  ETIQUETAS_DE_TIPO,
  ErrorDeRegla,
  MAXIMO_DE_PASOS,
  MENSAJE_DIAS_INVALIDOS,
  cambiarEstadoDeRegla,
  configurarEscalamiento,
  listarReglas,
  pasosDe,
} from "../api/regla";
import type {
  CanalNotificacion,
  ListadoDeReglas,
  PasoDeEscalamiento,
  ReglaDeNegocio,
} from "../api/regla";

export interface PropsDeReglasDeNegocio {
  readonly inicial: ListadoDeReglas;
  /** Sólo el Administrador escribe; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

interface Fila extends PasoDeEscalamiento {
  readonly clave: string;
}

/**
 * Por qué «Quitar» está apagado cuando queda un solo paso.
 *
 * El botón no se puede esconder —la fila tiene que seguir teniendo su acción en el mismo
 * lugar que las demás, y una acción que aparece y desaparece según la cantidad de filas se
 * lee como un error— así que se queda apagado y dice el motivo, en el `title` del control y
 * en un renglón debajo de la lista. Un rectángulo gris sin explicación es la peor de las
 * tres opciones.
 */
const MOTIVO_PASO_UNICO = "Una cadena necesita al menos un recordatorio: el último no se quita.";

function filasDe(reglas: readonly ReglaDeNegocio[]): Fila[] {
  const escalamiento = reglas.find((una) => una.tipo === "ESCALAMIENTO_DE_COBRO");
  if (escalamiento === undefined) {
    return [{ clave: crypto.randomUUID(), dias: 3, canal: "WHATSAPP" }];
  }
  const pasos = pasosDe(escalamiento);
  if (pasos.length === 0) {
    return [{ clave: crypto.randomUUID(), dias: 3, canal: "WHATSAPP" }];
  }
  return pasos.map((paso) => ({ ...paso, clave: crypto.randomUUID() }));
}

export function ReglasDeNegocio({ inicial, puedeEditar }: PropsDeReglasDeNegocio): JSX.Element {
  const [listado, setListado] = useState<ListadoDeReglas>(inicial);
  const [pasos, setPasos] = useState<readonly Fila[]>(() => filasDe(inicial.reglas));
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  /**
   * El prefijo de los `id` de este formulario.
   *
   * `useId()` y no el `clave` de la fila, que es un UUID al azar: ese UUID se genera una vez
   * en el servidor y otra en el cliente, así que el `id` del campo y el `htmlFor` de su
   * etiqueta terminaban siendo distintos —React avisaba del desajuste de hidratación— y hacer
   * clic en la etiqueta dejaba de enfocar el campo. `useId()` produce el mismo valor de los
   * dos lados; el `clave` sigue siendo la key de React, que no viaja al DOM.
   */
  const prefijo = useId();

  const hayDiaInvalido = pasos.some((paso) => !(paso.dias > 0));

  async function recargar(): Promise<void> {
    setListado(await listarReglas());
  }

  function cambiar(clave: string, campo: "dias" | "canal", valor: string): void {
    setPasos((previos) =>
      previos.map((paso) =>
        paso.clave === clave
          ? {
              ...paso,
              ...(campo === "dias"
                ? { dias: Number.parseInt(valor, 10) || 0 }
                : { canal: valor as CanalNotificacion }),
            }
          : paso,
      ),
    );
  }

  async function guardar(): Promise<void> {
    setError(null);
    setGuardando(true);
    try {
      await configurarEscalamiento(pasos.map(({ clave: _clave, ...resto }) => resto));
      await recargar();
    } catch (fallo) {
      setError(fallo instanceof ErrorDeRegla ? fallo.message : "No se pudo guardar la regla.");
    } finally {
      setGuardando(false);
    }
  }

  async function alternar(regla: ReglaDeNegocio): Promise<void> {
    setError(null);
    try {
      await cambiarEstadoDeRegla(regla.id, !regla.activa);
      await recargar();
    } catch (fallo) {
      setError(fallo instanceof ErrorDeRegla ? fallo.message : "No se pudo cambiar el estado.");
    }
  }

  const columnas: readonly Columna<ReglaDeNegocio>[] = [
    { clave: "tipo", titulo: "Tipo", celda: (fila) => ETIQUETAS_DE_TIPO[fila.tipo] },
    { clave: "prioridad", titulo: "Prioridad", celda: (fila) => String(fila.prioridad) },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.activa ? "ok" : "pendiente"}>
          {fila.activa ? "Activa" : "Inactiva"}
        </Badge>
      ),
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <Button variante="secundario" onClick={() => void alternar(fila)}>
            {fila.activa ? "Desactivar" : "Activar"}
          </Button>
        ) : null,
    },
  ];

  // Las dos superficies en una columna y las dos en tarjeta: el listado y el editor son el
  // mismo nivel de la pantalla —lo que rige y lo que se cambia— y antes eran una caja
  // punteada suelta encima de una tarjeta, que se lee como una carga que falló.
  return (
    <div className="cob-reglas">
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <Card titulo="Reglas configuradas">
        <Tabla
          titulo="Reglas configuradas"
          columnas={columnas}
          filas={listado.reglas}
          claveDeFila={(fila) => fila.id}
          vacia="Todavía no configuraste ninguna regla. Rige la cadena por defecto."
        />
      </Card>

      {puedeEditar && (
        <Card titulo="Cadena de recordatorios de cobro">
          <p className="dm-intro">
            Los días se cuentan <strong>desde el vencimiento del cobro</strong>, no desde el
            recordatorio anterior. Un cobro pagado o cancelado deja de recibirlos.
          </p>

          <form
            className="cob-reglas__form"
            onSubmit={(evento) => {
              evento.preventDefault();
              void guardar();
            }}
          >
            {/* Una lista ordenada y no un montón de `div`: la cadena tiene orden, y el
                orden es parte de lo que se está configurando. */}
            <ol className="cob-pasos">
              {pasos.map((paso, indice) => (
                <li className="cob-paso" key={paso.clave}>
                  <Campo
                    id={`${prefijo}-dias-${indice}`}
                    etiqueta={`Días del recordatorio ${indice + 1}`}
                    mono
                    inputMode="numeric"
                    value={String(paso.dias)}
                    onChange={(evento) => cambiar(paso.clave, "dias", evento.target.value)}
                  />
                  <Select
                    id={`${prefijo}-canal-${indice}`}
                    etiqueta="Canal"
                    opciones={CANALES}
                    value={paso.canal}
                    onChange={(evento) => cambiar(paso.clave, "canal", evento.target.value)}
                  />
                  <Button
                    variante="secundario"
                    disabled={pasos.length === 1}
                    // Siempre una cadena y nunca `undefined`: `exactOptionalPropertyTypes`
                    // trata a un `title={undefined}` como un error, no como «sin título».
                    // El nombre accesible lo sigue dando el texto del botón, no esto.
                    title={
                      pasos.length === 1
                        ? MOTIVO_PASO_UNICO
                        : `Quitar el recordatorio ${indice + 1}`
                    }
                    onClick={() =>
                      setPasos((previos) => previos.filter((otro) => otro.clave !== paso.clave))
                    }
                  >
                    Quitar
                  </Button>
                </li>
              ))}
            </ol>

            {pasos.length === 1 && <p className="cob-paso__nota">{MOTIVO_PASO_UNICO}</p>}

            {hayDiaInvalido && <Alert tono="error">{MENSAJE_DIAS_INVALIDOS}</Alert>}

            <div className="cob-reglas__acciones">
              <Button
                variante="secundario"
                disabled={pasos.length >= MAXIMO_DE_PASOS}
                onClick={() =>
                  setPasos((previos) => [
                    ...previos,
                    { clave: crypto.randomUUID(), dias: 30, canal: "WHATSAPP" },
                  ])
                }
              >
                Agregar paso
              </Button>
              <Button type="submit" disabled={hayDiaInvalido} cargando={guardando}>
                Guardar cadena
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
