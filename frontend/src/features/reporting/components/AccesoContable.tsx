/**
 * La pantalla del contador externo (HU-E10-06). **Sin sesión.**
 *
 * Lo que muestra es lo único que el enlace habilita: los indicadores del período y los
 * paquetes para descargar. No hay navegación a ningún otro módulo, y no es una cuestión de
 * ocultar botones — no existe ninguna otra ruta que este enlace pueda abrir.
 *
 * **Si el enlace no sirve, lo que se ve es la frase de la historia y nada más.** Ni un menú,
 * ni un formulario de login, ni una sugerencia de escribirle a alguien: el enlace venció o lo
 * revocaron, y las dos cosas dicen lo mismo a propósito.
 */

"use client";

import { Alert, Card, Tabla, formatearFechaHora, formatearNumero } from "@/shared";
import type { Columna } from "@/shared";

import { nombreDeClaveDePaquete, nombreDelPeriodo, urlDePaqueteDelContador } from "../api/paquete";
import type { AccesoDelContador, Paquete } from "../api/paquete";
import { IconoDescarga } from "./Iconos";

export interface PropsDeAccesoContable {
  /** El valor del enlace, que es la credencial: viaja en cada descarga. */
  readonly valor: string;
  readonly acceso: AccesoDelContador | null;
  /** El texto que el backend contestó cuando el enlace no sirve. */
  readonly motivo?: string | undefined;
}

export function AccesoContable({ valor, acceso, motivo }: PropsDeAccesoContable): JSX.Element {
  if (acceso === null) {
    return (
      <Alert tono="error" titulo="Acceso no disponible">
        {motivo ?? "El acceso a este paquete ya no está disponible."}
      </Alert>
    );
  }

  const columnas: readonly Columna<Paquete>[] = [
    {
      clave: "periodo",
      titulo: "Período",
      // El mes en castellano y, debajo, el código: así se llama el archivo que se baja y es
      // lo que el contador cita cuando pide «el de 2026-03».
      celda: (fila) => (
        <span className="rep-celda-periodo">
          <b>{nombreDelPeriodo(fila.anio, fila.mes)}</b>
          <small>{fila.periodo}</small>
        </span>
      ),
    },
    {
      clave: "contenido",
      titulo: "Contenido",
      celda: (fila) => {
        const partes = Object.entries(fila.totales_por_tipo).filter(
          ([, totales]) => totales.cantidad !== "0",
        );
        if (partes.length === 0) {
          return "Sin movimientos";
        }
        return (
          <span className="rep-chips">
            {partes.map(([clave, totales]) => (
              <span key={clave} className="rep-chip">
                {nombreDeClaveDePaquete(clave)} <b>{totales.cantidad}</b>
              </span>
            ))}
          </span>
        );
      },
    },
    {
      clave: "archivo",
      titulo: "Archivo",
      alDerecha: true,
      celda: (fila) =>
        fila.disponible ? (
          <a
            className="rep-descarga"
            href={urlDePaqueteDelContador(valor, fila.id)}
            download
            aria-label={`Descargar el paquete de ${nombreDelPeriodo(fila.anio, fila.mes)}`}
          >
            <IconoDescarga />
            Descargar
          </a>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <>
      <p className="dm-intro">
        Tenés acceso de sólo lectura a los reportes y paquetes contables de tu cliente. El enlace
        vence el {formatearFechaHora(acceso.vence)}.
      </p>

      <div className="fac-detalle">
        <Card titulo="Facturado">
          <p className="fac-totales__final">$ {formatearNumero(acceso.tablero.facturado.valor)}</p>
        </Card>
        <Card titulo="Cobrado">
          <p className="fac-totales__final">$ {formatearNumero(acceso.tablero.cobrado.valor)}</p>
        </Card>
        <Card titulo="Pendiente de cobro">
          <p className="fac-totales__final">$ {formatearNumero(acceso.tablero.pendiente)}</p>
        </Card>
        <Card titulo="En mora">
          <p className="fac-totales__final">$ {formatearNumero(acceso.tablero.en_mora)}</p>
        </Card>
      </div>

      <Card titulo="Paquetes contables">
        <Tabla
          titulo="Paquetes disponibles"
          columnas={columnas}
          filas={acceso.paquetes.paquetes}
          claveDeFila={(fila) => fila.id}
          vacia="Tu cliente todavía no generó ningún paquete contable."
        />
      </Card>
    </>
  );
}
