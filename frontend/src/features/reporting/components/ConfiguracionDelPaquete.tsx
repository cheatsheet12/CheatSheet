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

import {
  ChartColumn,
  ClipboardList,
  FileCode2,
  FileMinus,
  FileText,
  Mail,
  PackageCheck,
  Power,
  ReceiptText,
  ScrollText,
  Send,
  UserPlus,
  type LucideIcon,
} from "lucide-react";

import { Alert, Badge, Button, Campo, formatearFechaHora } from "@/shared";

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
import { IconoDescarga, IconoTilde } from "./Iconos";

export interface PropsDeConfiguracionDelPaquete {
  readonly inicial: Configuracion;
  readonly paquetes: readonly Paquete[];
  /** HU-E10-04 RN-04: configurar el envío automático es exclusivo del Administrador. */
  readonly puedeConfigurar: boolean;
}

const FORMATOS: readonly string[] = ["PDF", "XML"];

/** El pictograma de cada formato y de cada contenido: decorativos, el texto manda. */
const ICONO_DE_FORMATO: Readonly<Record<string, LucideIcon>> = { PDF: FileText, XML: FileCode2 };

const ICONO_DE_CONTENIDO: Readonly<Record<ContenidoDelPaquete, LucideIcon>> = {
  FACTURAS: ReceiptText,
  NOTAS_DE_CREDITO: FileMinus,
  REPORTE_DE_COBROS: ChartColumn,
  LOG_DE_OPERACIONES: ScrollText,
  RESUMEN_EJECUTIVO: ClipboardList,
};

interface PropsDeOpcion {
  readonly id: string;
  readonly etiqueta: string;
  readonly Icono: LucideIcon;
  readonly marcada: boolean;
  readonly deshabilitada: boolean;
  readonly alCambiar: () => void;
}

/**
 * Una opción del paquete dibujada como baldosa seleccionable.
 *
 * Sigue siendo una casilla real: el `<input type="checkbox">` está en el DOM, con su `id` y su
 * `label htmlFor`, sólo que invisible y superpuesto. Teclado, lector de pantalla y tests ven lo
 * mismo que antes; lo que cambia es que el estado marcado se dibuja en la baldosa.
 */
function Opcion({
  id,
  etiqueta,
  Icono,
  marcada,
  deshabilitada,
  alCambiar,
}: PropsDeOpcion): JSX.Element {
  return (
    <label className="pqt-opcion" htmlFor={id}>
      <input
        id={id}
        className="pqt-opcion__input"
        type="checkbox"
        checked={marcada}
        disabled={deshabilitada}
        onChange={alCambiar}
      />
      <span className="pqt-opcion__caja">
        <span className="pqt-opcion__ic">
          <Icono strokeWidth={1.8} aria-hidden="true" focusable="false" />
        </span>
        <span className="pqt-opcion__texto">{etiqueta}</span>
        <span className="pqt-opcion__tilde">
          <IconoTilde />
        </span>
      </span>
    </label>
  );
}

function FilaDePaquete({ fila }: { readonly fila: Paquete }): JSX.Element {
  const partes = Object.entries(fila.totales_por_tipo).filter(
    ([, totales]) => totales.cantidad !== "0",
  );
  return (
    <tr>
      <td data-etiqueta="Período">
        {/* El mes en castellano y, al lado, el código del período: es como se llama el archivo
        que se descarga y lo que el contador escribe cuando pide «el de 2026-03». */}
        <span className="pqt-periodo">
          <span className="pqt-periodo__mes" aria-hidden="true">
            <b>{String(fila.mes).padStart(2, "0")}</b>
            <small>{fila.anio}</small>
          </span>
          <span className="pqt-periodo__texto">
            <b>{nombreDelPeriodo(fila.anio, fila.mes)}</b>
            <small>{fila.periodo}</small>
          </span>
        </span>
      </td>
      <td data-etiqueta="Contenido">
        {partes.length === 0 ? (
          <span className="pqt-sin">Sin movimientos</span>
        ) : (
          <span className="pqt-chips">
            {partes.map(([clave, totales]) => (
              <span key={clave} className="pqt-chip">
                {nombreDeClaveDePaquete(clave)} <b>{totales.cantidad}</b>
              </span>
            ))}
          </span>
        )}
      </td>
      <td data-etiqueta="Archivo" className="pqt-tabla__der">
        {fila.disponible ? (
          <a
            className="pqt-descarga"
            href={urlDePaquete(fila.id)}
            download
            aria-label={`Descargar el paquete de ${nombreDelPeriodo(fila.anio, fila.mes)}`}
          >
            <IconoDescarga />
            Descargar
          </a>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}

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

  const inicialDelContador = (configuracion.contador.email ?? "?").trim().charAt(0).toUpperCase();

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <div className="pqt">
        <div className="pqt__col">
          <section className="pqt-card">
            <header className="pqt-card__cab">
              <span className="pqt-card__ic">
                <PackageCheck strokeWidth={1.8} aria-hidden="true" focusable="false" />
              </span>
              <div>
                <h2 className="pqt-card__titulo">Envío automático</h2>
                {/* Sin punto final después de la fecha: `formatearFechaHora` termina en la hora, y
                un punto pegado a un valor formateado es el que produjo «9:00 p. m..». Lo que
                cierra la línea es el dato, no la puntuación. */}
                <p className={`pqt-estado${configuracion.activo ? " pqt-estado--activo" : ""}`}>
                  <span className="pqt-estado__punto" aria-hidden="true" />
                  {configuracion.activo && configuracion.proximo_envio !== null
                    ? `Activo · Próximo envío el ${formatearFechaHora(configuracion.proximo_envio)}`
                    : "Desactivado. El paquete no sale solo."}
                </p>
              </div>
            </header>

            <div className="pqt-card__cuerpo">
              <div className="pqt-dia pqt-con-icono pqt-con-icono--dia">
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

              <fieldset className="pqt-grupo">
                <legend>Formato</legend>
                <div className="pqt-opciones pqt-opciones--formato">
                  {FORMATOS.map((uno) => (
                    <Opcion
                      key={uno}
                      id={`${prefijo}-formato-${uno}`}
                      etiqueta={uno}
                      Icono={ICONO_DE_FORMATO[uno] ?? FileText}
                      marcada={formatos.includes(uno)}
                      deshabilitada={!puedeConfigurar}
                      alCambiar={() => setFormatos(alternar(formatos, uno))}
                    />
                  ))}
                </div>
              </fieldset>

              <fieldset className="pqt-grupo">
                <legend>Contenido</legend>
                <div className="pqt-opciones">
                  {CONTENIDOS.map((uno) => (
                    <Opcion
                      key={uno}
                      id={`${prefijo}-contenido-${uno}`}
                      etiqueta={ETIQUETAS_DE_CONTENIDO[uno]}
                      Icono={ICONO_DE_CONTENIDO[uno]}
                      marcada={contenido.includes(uno)}
                      deshabilitada={!puedeConfigurar}
                      alCambiar={() => setContenido(alternar(contenido, uno))}
                    />
                  ))}
                </div>
              </fieldset>

              <div className="pqt-email pqt-con-icono pqt-con-icono--mail">
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
            </div>

            {puedeConfigurar && (
              <footer className="pqt-pie">
                <Button onClick={() => void guardar(configuracion.activo)} cargando={trabajando}>
                  Guardar
                </Button>
                {configuracion.activo ? (
                  <span className="pqt-pie__baja">
                    <Button variante="secundario" onClick={() => void guardar(false)}>
                      <Power size={15} strokeWidth={1.9} aria-hidden="true" focusable="false" />
                      Desactivar envío
                    </Button>
                  </span>
                ) : (
                  <Button variante="secundario" onClick={() => void guardar(true)}>
                    Activar envío
                  </Button>
                )}
                <span className="pqt-pie__prueba">
                  <Button variante="secundario" onClick={() => void generar()}>
                    <Send size={15} strokeWidth={1.9} aria-hidden="true" focusable="false" />
                    Generar paquete de prueba
                  </Button>
                </span>
              </footer>
            )}
          </section>

          <section className="pqt-card">
            <header className="pqt-card__cab">
              <span className="pqt-card__ic">
                <ReceiptText strokeWidth={1.8} aria-hidden="true" focusable="false" />
              </span>
              <div>
                <h2 className="pqt-card__titulo">Paquetes generados</h2>
              </div>
              <span className="pqt-cuenta">{paquetes.length}</span>
            </header>
            {paquetes.length === 0 ? (
              <div className="pqt-vacio">
                <span className="pqt-vacio__ic">
                  <PackageCheck strokeWidth={1.6} aria-hidden="true" focusable="false" />
                </span>
                <p>Todavía no hay ningún paquete contable.</p>
              </div>
            ) : (
              <div className="pqt-tabla-caja">
                <table className="pqt-tabla" aria-label="Paquetes contables">
                  <thead>
                    <tr>
                      <th scope="col">Período</th>
                      <th scope="col">Contenido</th>
                      <th scope="col" className="pqt-tabla__der">
                        Archivo
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {paquetes.map((fila) => (
                      <FilaDePaquete key={fila.id} fila={fila} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <aside className="pqt__aside">
          <section className="pqt-card">
            <header className="pqt-card__cab">
              <span className="pqt-card__ic">
                <UserPlus strokeWidth={1.8} aria-hidden="true" focusable="false" />
              </span>
              <div>
                <h2 className="pqt-card__titulo">Acceso del contador</h2>
              </div>
            </header>
            <div className="pqt-card__cuerpo">
              {configuracion.contador.invitado ? (
                <>
                  <div className="pqt-contador">
                    <span className="pqt-contador__avatar" aria-hidden="true">
                      {inicialDelContador}
                    </span>
                    <div className="pqt-contador__datos">
                      <p className="pqt-contador__email">{configuracion.contador.email}</p>
                      <Badge estado="ok">Invitado con acceso limitado</Badge>
                    </div>
                  </div>
                  <p className="pqt-nota">
                    Puede ver los reportes mensuales y descargar los paquetes contables. No accede a
                    facturación, cobros, configuración ni datos de clientes.
                  </p>
                  {/* El vencimiento y los accesos salen de la frase corrida y pasan a una lista de
                  dato-y-valor: metidos en el párrafo hay que leerlo entero para encontrarlos. */}
                  <dl className="rep-datos pqt-datos">
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
                    // Acción de texto y no un botón rojo con caja: es una acción entre otras
                    // dentro de la tarjeta. El componente sigue siendo `Button` para no
                    // reimplementar la confirmación que exige §1.3.
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
                  <p className="pqt-nota">Todavía no invitaste a ningún contador.</p>
                  {puedeConfigurar && (
                    <div className="pqt-invitar">
                      <div className="pqt-con-icono pqt-con-icono--mail">
                        <Campo
                          id="paq-contador"
                          etiqueta="Email del contador"
                          type="email"
                          value={emailDelContador}
                          onChange={(evento) => setEmailDelContador(evento.target.value)}
                        />
                      </div>
                      <Button onClick={() => void invitar()} cargando={trabajando}>
                        <Mail size={15} strokeWidth={1.9} aria-hidden="true" focusable="false" />
                        Invitar
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </section>
        </aside>
      </div>
    </>
  );
}
