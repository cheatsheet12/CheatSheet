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

import { useId, useState } from "react";

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
  nombreDeClaveDePaquete,
  nombreDelPeriodo,
  revocarContador,
  urlDePaquete,
} from "../api/paquete";
import type {
  ConfiguracionDelPaquete as Configuracion,
  ContenidoDelPaquete,
  Paquete,
} from "../api/paquete";
import { IconoDescarga } from "./Iconos";

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
  /**
   * El prefijo de los `id` de las casillas.
   *
   * Cada casilla necesita su propio `id` y su `label htmlFor`: envolverlas en un `<label>` sin
   * más funciona con el mouse, pero un lector de pantalla anuncia «casilla» sin decir cuál — y
   * son siete decisiones sobre qué va adentro del paquete que le llega al contador.
   */
  const prefijo = useId();
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
    {
      clave: "periodo",
      titulo: "Período",
      /**
       * El mes en castellano y, debajo, el código del período.
       *
       * El código no es ruido: es como se llama el archivo que se descarga y es lo que el
       * contador escribe cuando pide «el de 2026-03». Lo que no puede ser es lo único que se
       * ve, porque nadie lee un mes en un número de dos dígitos.
       */
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
            href={urlDePaquete(fila.id)}
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
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      {/* Dos columnas: a la izquierda qué sale y cuándo, a la derecha quién lo recibe. En una
          sola columna de 1500 px, un campo para escribir «5» ocupa el ancho de la pantalla y
          deja de parecer un número del 1 al 28. */}
      <div className="rep-cfg">
        <div className="rep-cfg__col">
          <Card titulo="Envío automático">
            {/* Sin punto final después de la fecha: `formatearFechaHora` termina en la hora, y un
            punto pegado a un valor formateado es el que produjo «9:00 p. m..». Lo que cierra
            la línea es el dato, no la puntuación. */}
            <p className="dm-intro">
              {configuracion.activo && configuracion.proximo_envio !== null
                ? `Activo · Próximo envío el ${formatearFechaHora(configuracion.proximo_envio)}`
                : "Desactivado. El paquete no sale solo."}
            </p>

            {/* El ancho del campo es una pista sobre lo que espera adentro: un día del mes
                son dos dígitos, y un cuadro de mil píxeles para escribir «5» hace dudar. */}
            <div className="rep-campo--corto">
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
            </div>

            <fieldset className="rep-grupo">
              <legend>Formato</legend>
              {FORMATOS.map((uno) => (
                <label
                  key={uno}
                  className="rep-grupo__opcion"
                  htmlFor={`${prefijo}-formato-${uno}`}
                >
                  <input
                    id={`${prefijo}-formato-${uno}`}
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
                <label
                  key={uno}
                  className="rep-grupo__opcion"
                  htmlFor={`${prefijo}-contenido-${uno}`}
                >
                  <input
                    id={`${prefijo}-contenido-${uno}`}
                    type="checkbox"
                    checked={contenido.includes(uno)}
                    disabled={!puedeConfigurar}
                    onChange={() => setContenido(alternar(contenido, uno))}
                  />
                  {ETIQUETAS_DE_CONTENIDO[uno]}
                </label>
              ))}
            </fieldset>

            <div className="rep-campo--medio">
              <Campo
                id="paq-email"
                etiqueta="Email del contador"
                type="email"
                value={email}
                disabled={!puedeConfigurar}
                ayuda="Sin este dato no se puede activar el envío automático."
                onChange={(evento) => setEmail(evento.target.value)}
              />
            </div>

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

          <Card titulo="Paquetes generados">
            <Tabla
              titulo="Paquetes contables"
              columnas={columnas}
              filas={paquetes}
              claveDeFila={(fila) => fila.id}
              vacia="Todavía no hay ningún paquete contable."
            />
          </Card>
        </div>

        <aside className="rep-cfg__aside">
          <Card titulo="Acceso del contador">
            {configuracion.contador.invitado ? (
              <>
                <p className="dm-intro">
                  <Badge estado="ok">Invitado con acceso limitado</Badge>{" "}
                  {configuracion.contador.email}
                </p>
                <p className="rep-comparacion">
                  Puede ver los reportes mensuales y descargar los paquetes contables. No accede a
                  facturación, cobros, configuración ni datos de clientes.
                </p>
                {/* El vencimiento y los accesos salen de la frase corrida y pasan a una lista de
                dato-y-valor: metidos en el párrafo hay que leerlo entero para encontrarlos, y
                era ahí donde una fecha con punto final terminaba en «9:20 p. m..». */}
                <dl className="rep-datos">
                  <div className="rep-kv">
                    <dt>El enlace vence</dt>
                    <dd>
                      {configuracion.contador.vence === null
                        ? "—"
                        : formatearFechaHora(configuracion.contador.vence)}
                    </dd>
                  </div>
                  <div className="rep-kv">
                    <dt>Accesos registrados</dt>
                    <dd>{configuracion.contador.accesos}</dd>
                  </div>
                </dl>
                {puedeConfigurar && (
                  // Acción de texto y no un botón rojo con caja: es una acción entre otras dentro
                  // de la tarjeta, no la acción principal de la pantalla. El componente sigue
                  // siendo `Button` para no reimplementar la confirmación que exige §1.3.
                  <span className="rep-accion-destructiva">
                    <Button
                      variante="destructivo"
                      confirmacion="El enlace deja de funcionar de inmediato. ¿Revocar el acceso?"
                      onClick={() => void revocar()}
                    >
                      Revocar acceso
                    </Button>
                  </span>
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
        </aside>
      </div>
    </>
  );
}
