/**
 * El alta de una excepción de disponibilidad (HU-E7-05): un día sin atención o un horario
 * especial.
 *
 * Hasta #165 sólo existía «Bloquear el día»: el sistema aceptaba la apertura especial, pero el
 * panel no tenía forma de cargarla. La franja del horario especial se arma con
 * `franjaDeApertura`, en la zona de la agenda; una que cierra antes de abrir no se manda y se
 * dice por qué, con la frase de la historia.
 */

"use client";

import { useState } from "react";

import { Alert, Button, Campo, Select, SelectorDeFecha } from "@/shared";

import {
  ETIQUETAS_DE_EXCEPCION,
  MENSAJE_HORARIO_INVERTIDO,
  registrarExcepcion,
} from "../api/recurso";
import type { Recurso, TipoExcepcion } from "../api/recurso";
import { franjaDeApertura } from "./recursosDatos";

const OPCIONES_DE_TIPO = (Object.keys(ETIQUETAS_DE_EXCEPCION) as TipoExcepcion[]).map((tipo) => ({
  valor: tipo,
  etiqueta: ETIQUETAS_DE_EXCEPCION[tipo],
}));

export interface PropsDeFormularioDeExcepcion {
  readonly recurso: Recurso;
  readonly trabajando: boolean;
  readonly onCorrer: (accion: () => Promise<unknown>, porDefecto: string) => Promise<void>;
  readonly onActualizado: (recurso: Recurso) => void;
}

export function FormularioDeExcepcion({
  recurso,
  trabajando,
  onCorrer,
  onActualizado,
}: PropsDeFormularioDeExcepcion): JSX.Element {
  const [tipo, setTipo] = useState<TipoExcepcion>("BLOQUEO");
  const [fecha, setFecha] = useState("");
  const [apertura, setApertura] = useState("");
  const [cierre, setCierre] = useState("");

  const especial = tipo === "APERTURA_ESPECIAL";
  const franja = franjaDeApertura(fecha, apertura, cierre);
  // Las dos horas puestas y en el orden equivocado: se dice. Una que falta sólo deshabilita.
  const invertida = especial && apertura !== "" && cierre !== "" && apertura >= cierre;
  const listo = fecha !== "" && (!especial || franja !== null);

  function guardar(): void {
    void onCorrer(async () => {
      onActualizado(
        await registrarExcepcion(
          recurso.id,
          especial && franja !== null ? { fecha, tipo, ...franja } : { fecha, tipo: "BLOQUEO" },
        ),
      );
      setFecha("");
      setApertura("");
      setCierre("");
    }, "No se pudo agregar la excepción.");
  }

  return (
    <>
      <div className="age-excepcion">
        <Select
          id="excepcion-tipo"
          etiqueta="Tipo de excepción"
          opciones={OPCIONES_DE_TIPO}
          value={tipo}
          onChange={(evento) => setTipo(evento.target.value as TipoExcepcion)}
        />
        <SelectorDeFecha
          id="excepcion-fecha"
          etiqueta="Fecha de la excepción"
          value={fecha}
          alCambiar={setFecha}
        />
        {especial && (
          <>
            <Campo
              id="excepcion-apertura"
              etiqueta="Hora de apertura"
              type="time"
              value={apertura}
              onChange={(evento) => setApertura(evento.target.value)}
            />
            <Campo
              id="excepcion-cierre"
              etiqueta="Hora de cierre"
              type="time"
              value={cierre}
              onChange={(evento) => setCierre(evento.target.value)}
            />
          </>
        )}
        <Button disabled={!listo} cargando={trabajando} onClick={guardar}>
          {especial ? "Guardar horario especial" : "Bloquear el día"}
        </Button>
      </div>
      {invertida && <Alert tono="error">{MENSAJE_HORARIO_INVERTIDO}</Alert>}
    </>
  );
}
