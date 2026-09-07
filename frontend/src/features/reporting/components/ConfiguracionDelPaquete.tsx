/**
 * PAN-REP-02 — Reportería · Configuración automática (HU-E10-04 y HU-E10-05).
 *
 * Una pantalla con dos mitades: cuándo y qué sale el paquete, y quién puede descargarlo.
 *
 * **Un solo botón guarda todo.** El backend recibe la configuración entera en un `PUT`, así
 * que no hay estados intermedios donde el envío quedó activo con un día que el usuario todavía
 * no confirmó.
 *
 * **El mensaje de «falta el email» lo escribe el backend.** La pantalla no lo adivina: lo
 * muestra tal como viene, porque es la frase que el criterio de aceptación pide palabra por
 * palabra y una copia local se desactualiza sin que nadie lo note.
 *
 * **El enlace del contador no se muestra nunca.** No está porque no existe de este lado: sale
 * una sola vez, por mail. Lo que la pantalla dice es «Invitado con acceso limitado», que es
 * exactamente lo que el criterio pide.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Tabla, formatearFechaHora } from "@/shared";
import type { Columna } from "@/shared";

import {
  CONTENIDOS,
  DIA_MAXIMO_DE_ENVIO,
  ETIQUETAS_DE_CONTENIDO,
  ErrorDePaquete,
  generarPaquete,
  guardarConfiguracion,
  invitarContador,
  listarPaquetes,
  revocarContador,
  urlDePaquete,
} from "../api/paquete";
import type {
  ConfiguracionDelPaquete as Configuracion,
  ContenidoDelPaquete,
  Paquete,
} from "../api/paquete";

export interface PropsDeConfiguracionDelPaquete {
  readonly inicial: Configuracion;
  readonly paquetes: readonly Paquete[];
  /** HU-E10-04 RN-04: configurar el envío automático es exclusivo del Administrador. */
  readonly puedeConfigurar: boolean;
}

const FORMATOS: readonly string[] = ["PDF", "XML"];

export function ConfiguracionDelPaquete({
  inicial,
  paquetes: paquetesIniciales,
  puedeConfigurar,
}: PropsDeConfiguracionDelPaquete): JSX.Element {
  const [configuracion, setConfiguracion] = useState<Configuracion>(inicial);
  const [paquetes, setPaquetes] = useState<readonly Paquete[]>(paquetesIniciales);
  const [dia, setDia] = useState(String(inicial.dia_de_envio));
  const [formatos, setFormatos] = useState<readonly string[]>(inicial.formatos);
  const [contenido, setContenido] = useState<readonly ContenidoDelPaquete[]>(inicial.contenido);
  const [email, setEmail] = useState(inicial.email_contador ?? "");
  const [emailDelContador, setEmailDelContador] = useState(inicial.contador.email ?? "");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  function alternar<T extends string>(lista: readonly T[], valor: T): readonly T[] {
    return lista.includes(valor) ? lista.filter((uno) => uno !== valor) : [...lista, valor];
  }

  async function conManejo(trabajo: () => Promise<void>): Promise<void> {
    setTrabajando(true);
    setError(null);
    setAviso(null);
    try {
      await trabajo();
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDePaquete ? fallo.message : "No se pudo completar la operación.",
      );
    } finally {
      setTrabajando(false);
    }
  }

  async function guardar(activo: boolean): Promise<void> {
    await conManejo(async () => {
      setConfiguracion(
        await guardarConfiguracion({
          dia_de_envio: Number(dia),
          formatos,
          contenido,
          email_contador: email.trim() === "" ? null : email.trim(),
          activo,
        }),
      );
      setAviso("Configuración guardada.");
    });
  }

  async function generar(): Promise<void> {
    await conManejo(async () => {
      await generarPaquete();
      setPaquetes((await listarPaquetes()).paquetes);
      setAviso("El paquete quedó disponible para descargar.");
    });
  }

  async function invitar(): Promise<void> {
    await conManejo(async () => {
      const contador = await invitarContador(emailDelContador.trim());
      setConfiguracion({ ...configuracion, contador });
      setAviso("Le mandamos el enlace de acceso al contador.");
    });
  }

  async function revocar(): Promise<void> {
    await conManejo(async () => {
      await revocarContador();
      setConfiguracion({
        ...configuracion,
        contador: { ...configuracion.contador, invitado: false, vence: null },
      });
      setAviso("El enlace quedó invalidado.");
    });
  }

  const columnas: readonly Columna<Paquete>[] = [
    { clave: "periodo", titulo: "Período", celda: (fila) => fila.periodo },
    {
      clave: "contenido",
      titulo: "Contenido",
      celda: (fila) =>
        Object.entries(fila.totales_por_tipo)
          .filter(([, totales]) => totales.cantidad !== "0")
          .map(([clave, totales]) => `${clave}: ${totales.cantidad}`)
          .join(" · ") || "Sin movimientos",
    },
    {
      clave: "archivo",
      titulo: "Archivo",
      alDerecha: true,
      celda: (fila) =>
        fila.disponible ? (
          <a href={urlDePaquete(fila.id)} download>
            Descargar
          </a>
        ) : (
          "—"
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
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <Card titulo="Envío automático">
        <p className="dm-intro">
          {configuracion.activo && configuracion.proximo_envio !== null
            ? `Activo. Próximo envío: ${formatearFechaHora(configuracion.proximo_envio)}.`
            : "Desactivado. El paquete no sale solo."}
        </p>

        <Campo
          id="paq-dia"
          etiqueta="Día de envío"
          type="number"
          min={1}
          max={DIA_MAXIMO_DE_ENVIO}
          value={dia}
          disabled={!puedeConfigurar}
          ayuda="Del 1 al 28: el paquete lleva los datos del mes cerrado."
          onChange={(evento) => setDia(evento.target.value)}
        />

        <fieldset className="rep-grupo">
          <legend>Formato</legend>
          {FORMATOS.map((uno) => (
            <label key={uno} className="rep-grupo__opcion">
              <input
                type="checkbox"
                checked={formatos.includes(uno)}
                disabled={!puedeConfigurar}
                onChange={() => setFormatos(alternar(formatos, uno))}
              />
              {uno}
            </label>
          ))}
        </fieldset>

        <fieldset className="rep-grupo">
          <legend>Contenido</legend>
          {CONTENIDOS.map((uno) => (
            <label key={uno} className="rep-grupo__opcion">
              <input
                type="checkbox"
                checked={contenido.includes(uno)}
                disabled={!puedeConfigurar}
                onChange={() => setContenido(alternar(contenido, uno))}
              />
              {ETIQUETAS_DE_CONTENIDO[uno]}
            </label>
          ))}
        </fieldset>

        <Campo
          id="paq-email"
          etiqueta="Email del contador"
          type="email"
          value={email}
          disabled={!puedeConfigurar}
          ayuda="Sin este dato no se puede activar el envío automático."
          onChange={(evento) => setEmail(evento.target.value)}
        />

        {puedeConfigurar && (
          <div className="rep-acciones">
            <Button onClick={() => void guardar(configuracion.activo)} cargando={trabajando}>
              Guardar
            </Button>
            {configuracion.activo ? (
              <Button variante="secundario" onClick={() => void guardar(false)}>
                Desactivar envío
              </Button>
            ) : (
              <Button variante="secundario" onClick={() => void guardar(true)}>
                Activar envío
              </Button>
            )}
            <Button variante="secundario" onClick={() => void generar()}>
              Generar paquete de prueba
            </Button>
          </div>
        )}
      </Card>

      <Card titulo="Acceso del contador">
        {configuracion.contador.invitado ? (
          <>
            <p className="dm-intro">
              <Badge estado="ok">Invitado con acceso limitado</Badge> {configuracion.contador.email}
            </p>
            <p className="rep-comparacion">
              Puede ver los reportes mensuales y descargar los paquetes contables. No accede a
              facturación, cobros, configuración ni datos de clientes.
              {configuracion.contador.vence !== null &&
                ` El enlace vence el ${formatearFechaHora(configuracion.contador.vence)}.`}{" "}
              Accesos registrados: {configuracion.contador.accesos}.
            </p>
            {puedeConfigurar && (
              <Button
                variante="destructivo"
                confirmacion="El enlace deja de funcionar de inmediato. ¿Revocar el acceso?"
                onClick={() => void revocar()}
              >
                Revocar acceso
              </Button>
            )}
          </>
        ) : (
          <>
            <p className="dm-intro">Todavía no invitaste a ningún contador.</p>
            {puedeConfigurar && (
              <>
                <Campo
                  id="paq-contador"
                  etiqueta="Email del contador"
                  type="email"
                  value={emailDelContador}
                  onChange={(evento) => setEmailDelContador(evento.target.value)}
                />
                <Button onClick={() => void invitar()} cargando={trabajando}>
                  Invitar
                </Button>
              </>
            )}
          </>
        )}
      </Card>

      <Card titulo="Paquetes generados">
        <Tabla
          titulo="Paquetes contables"
          columnas={columnas}
          filas={paquetes}
          claveDeFila={(fila) => fila.id}
          vacia="Todavía no hay ningún paquete contable."
        />
      </Card>
    </>
  );
}
