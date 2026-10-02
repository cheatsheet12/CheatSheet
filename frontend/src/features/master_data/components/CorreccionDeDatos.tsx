/**
 * PAN-DM-01 — sección «Formato de los datos existentes» (HU-E4-05 RN-09).
 *
 * Es del Administrador y la página decide si la renderiza; esa decisión es una cortesía, el
 * guard es el backend. El flujo tiene tres pasos y ninguno escribe sin preguntar: revisar
 * (no escribe nada), aplicar (reescribe nombres) y restaurar (los devuelve). Aplicar y
 * restaurar piden confirmación con el mismo diálogo que el resto del panel.
 *
 * Restaurar no es un «deshacer» ciego: lo que alguien editó después de la corrección se
 * conserva, y el resultado dice cuántos registros fueron de cada tipo.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, Button, Card, formatearFechaHora } from "@/shared";

import {
  ErrorDeCorreccion,
  aplicarCorreccion,
  informarCorreccion,
  listarCorridas,
  restaurarCorreccion,
} from "../api/correccion";
import type {
  Corrida,
  EntidadCorregible,
  InformeDeCorreccion,
  MotivoDeOmision,
} from "../api/correccion";

const ENTIDADES: readonly EntidadCorregible[] = ["CLIENTE", "SERVICIO", "CATEGORIA"];

const NOMBRE_DE_ENTIDAD: Readonly<Record<EntidadCorregible, readonly [string, string]>> = {
  CLIENTE: ["cliente", "clientes"],
  SERVICIO: ["servicio", "servicios"],
  CATEGORIA: ["categoría", "categorías"],
};

/** Cada motivo de omisión dicho para quien lo lee, no como el código del backend. */
const MOTIVO_DE_OMISION: Readonly<Record<MotivoDeOmision, string>> = {
  COLISION_DE_CATEGORIA: "Ya existe otra categoría con ese nombre en el mismo ámbito.",
  NOMBRE_INVALIDO: "El nombre corregido no sería válido.",
  DURACION_FUERA_DE_REGLA: "La duración del servicio está fuera de la regla vigente.",
};

const MENSAJE_POR_ESTADO: Readonly<Record<number, string>> = {
  403: "Solo un Administrador puede corregir los datos existentes.",
  409: "Ya hay una corrección en curso. Espere a que termine e intente de nuevo.",
  422: "Esa corrección ya no existe.",
};

function mensajeDeError(fallo: unknown): string {
  if (fallo instanceof ErrorDeCorreccion) {
    return MENSAJE_POR_ESTADO[fallo.estado] ?? "No se pudo completar la operación.";
  }
  return "No se pudo completar la operación.";
}

function registros(cantidad: number): string {
  return `${cantidad} ${cantidad === 1 ? "registro" : "registros"}`;
}

function total(conteos: Readonly<Partial<Record<string, number>>>): number {
  return Object.values(conteos).reduce<number>((suma, n) => suma + (n ?? 0), 0);
}

function Informe({ informe }: { readonly informe: InformeDeCorreccion }): JSX.Element {
  const omitidos = Object.entries(informe.omitidos) as [MotivoDeOmision, number][];
  return (
    <div>
      <ul>
        {ENTIDADES.filter((entidad) => (informe.a_corregir[entidad] ?? 0) > 0).map((entidad) => {
          const cantidad = informe.a_corregir[entidad] ?? 0;
          const [singular, plural] = NOMBRE_DE_ENTIDAD[entidad];
          return (
            <li key={entidad}>
              {cantidad} {cantidad === 1 ? singular : plural} a corregir
              <ul>
                {(informe.ejemplos[entidad] ?? []).map((ejemplo) => (
                  <li key={`${ejemplo.antes}→${ejemplo.despues}`}>
                    <span>{ejemplo.antes}</span> → <span>{ejemplo.despues}</span>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      {omitidos.length > 0 && (
        <Alert tono="advertencia" titulo="Quedan sin corregir">
          <ul>
            {omitidos.map(([motivo, cantidad]) => (
              <li key={motivo}>
                {cantidad} {cantidad === 1 ? "omitido" : "omitidos"} — {MOTIVO_DE_OMISION[motivo]}
              </li>
            ))}
          </ul>
        </Alert>
      )}
    </div>
  );
}

export function CorreccionDeDatos(): JSX.Element {
  const [informe, setInforme] = useState<InformeDeCorreccion | null>(null);
  const [corridas, setCorridas] = useState<readonly Corrida[]>([]);
  const [resultado, setResultado] = useState<readonly string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const recargarCorridas = useCallback(async (): Promise<void> => {
    try {
      setCorridas((await listarCorridas()).corridas);
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    }
  }, []);

  useEffect(() => {
    void recargarCorridas();
  }, [recargarCorridas]);

  /** Corre una operación con el estado común: sin mensajes viejos y sin doble clic. */
  async function ejecutar(operacion: () => Promise<void>): Promise<void> {
    setError(null);
    setResultado([]);
    setOcupado(true);
    try {
      await operacion();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setOcupado(false);
    }
  }

  const revisar = (): Promise<void> =>
    ejecutar(async () => {
      setInforme(await informarCorreccion());
    });

  const aplicar = (): Promise<void> =>
    ejecutar(async () => {
      const aplicada = await aplicarCorreccion();
      setInforme(null);
      setResultado([`Se corrigieron ${registros(total(aplicada.conteos))}.`]);
      await recargarCorridas();
    });

  const restaurar = (corrida: Corrida): Promise<void> =>
    ejecutar(async () => {
      const restaurada = await restaurarCorreccion(corrida.corrida_id);
      const { conservados } = restaurada;
      setResultado([
        `Se restauraron ${registros(restaurada.restaurados)}.`,
        ...(conservados > 0
          ? [
              conservados === 1
                ? "1 se conservó porque se editó después de la corrección."
                : `${conservados} se conservaron porque se editaron después de la corrección.`,
            ]
          : []),
      ]);
      await recargarCorridas();
    });

  function pedirRestauracion(corrida: Corrida): void {
    if (
      window.confirm(
        "¿Restaurar los nombres originales de esta corrección? Lo que se haya editado después se conserva.",
      )
    ) {
      void restaurar(corrida);
    }
  }

  const hayParaCorregir = informe !== null && total(informe.a_corregir) > 0;

  return (
    <Card titulo="Formato de los datos existentes">
      <p>
        Revise cómo quedarían los nombres ya cargados —mayúsculas, espacios y signos repetidos—
        antes de corregirlos. La revisión no cambia nada.
      </p>
      <Button variante="secundario" cargando={ocupado} onClick={() => void revisar()}>
        Revisar formato de los datos existentes
      </Button>

      {error !== null && <Alert tono="error">{error}</Alert>}
      {resultado.length > 0 && (
        <Alert tono="exito">
          {resultado.map((linea) => (
            <p key={linea}>{linea}</p>
          ))}
        </Alert>
      )}

      {informe !== null && !hayParaCorregir && <p>No hay datos para corregir</p>}
      {informe !== null && hayParaCorregir && (
        <>
          <Informe informe={informe} />
          <Button
            cargando={ocupado}
            onClick={() => {
              if (
                window.confirm(
                  "¿Aplicar la corrección? Se reescribirán los nombres y quedará un respaldo para restaurarlos.",
                )
              ) {
                void aplicar();
              }
            }}
          >
            Aplicar corrección
          </Button>
        </>
      )}

      {corridas.length > 0 && (
        <section aria-label="Correcciones aplicadas">
          <h3>Correcciones aplicadas</h3>
          <ul>
            {corridas.map((corrida) => (
              <li key={corrida.corrida_id}>
                {formatearFechaHora(corrida.creada_en)} — {registros(corrida.cantidad)}{" "}
                <Button
                  variante="secundario"
                  disabled={ocupado}
                  onClick={() => pedirRestauracion(corrida)}
                >
                  Restaurar
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Card>
  );
}
