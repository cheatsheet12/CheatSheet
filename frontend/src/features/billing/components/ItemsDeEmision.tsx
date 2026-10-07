/**
 * Las filas de ítems del paso 3.
 *
 * **Nada acá multiplica nada.** Cantidad, precio e IVA son texto, viajan como texto y lo que se le
 * cobra al cliente lo decide el backend y lo autoriza ARCA (`CLAUDE.md` §5).
 *
 * Los servicios activos del catálogo se piden una sola vez al montar el paso, y si el pedido falla
 * no pasa nada: el campo de descripción sigue funcionando como texto libre.
 */

"use client";

import { useEffect, useState } from "react";

import { listarServicios } from "@/features/master_data";
import type { Servicio } from "@/features/master_data";
import { Button, Campo, Select } from "@/shared";

import { ALICUOTAS } from "../api/comprobante";
import type { ItemNuevo } from "../api/comprobante";
import { CampoDeServicio } from "./CampoDeServicio";
import { IconoDeBasura, IconoDeMas } from "./iconosEmision";

export interface Linea extends ItemNuevo {
  readonly clave: string;
}

export function lineaVacia(): Linea {
  return {
    clave: crypto.randomUUID(),
    descripcion: "",
    cantidad: "1",
    precio_unitario: "",
    alicuota_iva: "0.21",
  };
}

export interface PropsDeItemsDeEmision {
  readonly lineas: readonly Linea[];
  readonly alCambiarLineas: (cambio: (previas: readonly Linea[]) => readonly Linea[]) => void;
}

export function ItemsDeEmision({ lineas, alCambiarLineas }: PropsDeItemsDeEmision): JSX.Element {
  const [servicios, setServicios] = useState<readonly Servicio[]>([]);

  useEffect(() => {
    let vigente = true;
    listarServicios({ soloActivos: true })
      .then((listado) => {
        if (vigente) {
          setServicios(listado.servicios.filter((servicio) => servicio.activo));
        }
      })
      .catch(() => {
        // Silencioso a propósito: sin catálogo, la descripción es texto libre.
      });
    return () => {
      vigente = false;
    };
  }, []);

  function cambiar(clave: string, campos: Partial<ItemNuevo>): void {
    alCambiarLineas((previas) =>
      previas.map((linea) => (linea.clave === clave ? { ...linea, ...campos } : linea)),
    );
  }

  function aplicarServicio(clave: string, servicio: Servicio): void {
    // Precio y alícuota tal como vienen: texto. Si la alícuota no es una de las que ofrece el
    // select, se deja la que la fila ya tenía en vez de inventar una opción.
    const alicuota = ALICUOTAS.find((una) => una.valor === servicio.alicuota_iva);
    cambiar(clave, {
      descripcion: servicio.nombre,
      precio_unitario: servicio.precio,
      ...(alicuota !== undefined ? { alicuota_iva: alicuota.valor } : {}),
    });
  }

  return (
    <>
      <div className="fac-em-items">
        {lineas.map((linea, indice) => (
          <div className="fac-em-item" key={linea.clave}>
            <div className="fac-em-item__descripcion">
              <CampoDeServicio
                id={`item-descripcion-${linea.clave}`}
                etiqueta={`Descripción ${indice + 1}`}
                valor={linea.descripcion}
                servicios={servicios}
                alCambiar={(texto) => cambiar(linea.clave, { descripcion: texto })}
                alElegir={(servicio) => aplicarServicio(linea.clave, servicio)}
              />
            </div>
            <Campo
              id={`item-cantidad-${linea.clave}`}
              etiqueta="Cantidad"
              mono
              inputMode="decimal"
              value={linea.cantidad}
              onChange={(evento) => cambiar(linea.clave, { cantidad: evento.target.value })}
            />
            <Campo
              id={`item-precio-${linea.clave}`}
              etiqueta="Precio unitario"
              mono
              inputMode="decimal"
              // Text and not `type="number"`: a number input hands back a JavaScript
              // float, which is the type this system refuses to let near money.
              value={linea.precio_unitario}
              onChange={(evento) => cambiar(linea.clave, { precio_unitario: evento.target.value })}
            />
            <Select
              id={`item-iva-${linea.clave}`}
              etiqueta="IVA"
              opciones={ALICUOTAS}
              value={linea.alicuota_iva}
              onChange={(evento) => cambiar(linea.clave, { alicuota_iva: evento.target.value })}
            />
            <div className="fac-em-item__quitar">
              <Button
                variante="secundario"
                aria-label={`Quitar ítem ${indice + 1}`}
                title="Quitar ítem"
                disabled={lineas.length === 1}
                onClick={() =>
                  alCambiarLineas((previas) => previas.filter((otra) => otra.clave !== linea.clave))
                }
              >
                <IconoDeBasura />
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="fac-em-items__agregar">
        <Button
          variante="secundario"
          onClick={() => alCambiarLineas((previas) => [...previas, lineaVacia()])}
        >
          <IconoDeMas />
          Agregar ítem
        </Button>
      </div>
    </>
  );
}
