/**
 * PAN-ONB-02 — the company's fiscal data (HU-E1-02), in its two homes.
 *
 * The same form serves step 2 of the onboarding and the edit screen in the panel. That is
 * not reuse for its own sake: it is the consequence of where the padrón lookup can happen.
 * Validating a CUIT against ARCA needs the company's own certificate, and the certificate
 * is loaded *after* the onboarding — so the screen that can actually validate is the one
 * in the panel, and it is the same six fields.
 *
 * **Three answers, not two.** «Validar contra ARCA» can come back with the data, with «no
 * lo encuentro» — which blocks — or with «no pude preguntar», which does not block and
 * says why. Turning the last two into one error message would mean an outage at ARCA
 * reading to the Administrator exactly like a rejected CUIT.
 *
 * **What arrives from ARCA fills gaps; it never overwrites.** An empty razón social gets
 * filled in (acceptance criterion 1). One that disagrees with what was typed is *offered*,
 * with a button, because a company's own name is not something to rewrite behind its back.
 *
 * **El cromo del paso sólo existe en el onboarding.** Stepper, «PASO 2 DE 3» y barra de
 * progreso hablan de una secuencia; en Configuración → Empresa no hay secuencia, hay una
 * pantalla que se edita cuando hace falta, y dibujarle un paso 2 sería mentir.
 *
 * **Los campos se arman una vez y se acomodan dos.** El onboarding los apila en una tarjeta
 * angosta —una columna, una pregunta por vez— y el panel los agrupa en secciones de dos
 * columnas, porque a 1440 px un campo de once dígitos estirado a todo el ancho es un
 * renglón vacío de un metro. Es la misma lista de campos con dos maquetados, no dos
 * formularios: dos copias de «Razón social» son dos lugares donde arreglar un solo bug.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Select, Stepper, useAccionConNavegacion } from "@/shared";

import type { ConsultaDePadron, EmpresaActual } from "../api/cliente";
import { ErrorDeFormulario, consultarPadron, guardarEmpresa } from "../api/cliente";
import { errorDeCuit, esCuitValido, formatearCuit, normalizarCuit } from "../validacion/cuit";
import { PASOS_DEL_ONBOARDING, avanceDelPaso } from "./pasos";

const CONDICIONES = [
  { valor: "RESPONSABLE_INSCRIPTO", texto: "Responsable Inscripto" },
  { valor: "MONOTRIBUTO", texto: "Monotributo" },
  { valor: "EXENTO", texto: "Exento" },
  { valor: "CONSUMIDOR_FINAL", texto: "Consumidor Final" },
] as const;

const OPCIONES_DE_CONDICION = CONDICIONES.map((condicion) => ({
  valor: condicion.valor,
  etiqueta: condicion.texto,
}));

export type ModoDeFormularioDeEmpresa = "onboarding" | "edicion";

export interface PropsDeFormularioDeEmpresa {
  readonly modo?: ModoDeFormularioDeEmpresa;
  readonly iniciales?: EmpresaActual | null;
}

/** What the padrón answered, once it has been turned into something the screen can show. */
interface Sugerencia {
  readonly razonSocial: string | null;
  readonly condicionIva: string | null;
}

export function FormularioDeEmpresa({
  modo = "onboarding",
  iniciales = null,
}: PropsDeFormularioDeEmpresa): JSX.Element {
  const router = useRouter();
  const [razonSocial, setRazonSocial] = useState(iniciales?.razon_social ?? "");
  const [cuit, setCuit] = useState(iniciales?.cuit ?? "");
  const [condicionIva, setCondicionIva] = useState<string>(
    iniciales?.condicion_iva ?? CONDICIONES[0].valor,
  );
  // Whether the VAT status is a *choice* or just the select's default. The select always
  // shows something, so "empty" does not exist for it the way it does for a text field —
  // and without this the padrón could never fill it in, or would always overwrite it.
  const [condicionElegida, setCondicionElegida] = useState(
    iniciales !== null && iniciales.condicion_iva !== null,
  );
  const [nombreResponsable, setNombreResponsable] = useState(iniciales?.nombre_responsable ?? "");
  const [emailContacto, setEmailContacto] = useState(iniciales?.email_contacto ?? "");
  const [general, setGeneral] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);
  const { pendiente: enviando, ejecutar } = useAccionConNavegacion();
  const [consulta, setConsulta] = useState<ConsultaDePadron | null>(null);
  const [consultando, setConsultando] = useState(false);
  const [sugerencia, setSugerencia] = useState<Sugerencia | null>(null);

  const enOnboarding = modo === "onboarding";
  const errorCuit = errorDeCuit(cuit);
  const cuitOk = esCuitValido(cuit);
  const rechazadoPorArca = consulta?.estado === "NO_ENCONTRADO";
  const completo =
    cuitOk &&
    !rechazadoPorArca &&
    razonSocial.trim() !== "" &&
    nombreResponsable.trim() !== "" &&
    emailContacto.trim() !== "";

  const cambiarCuit = (valor: string): void => {
    setCuit(valor);
    // Lo que ARCA dijo era sobre el CUIT anterior. Dejarlo en pantalla sería mentir.
    setConsulta(null);
    setSugerencia(null);
  };

  const validar = async (): Promise<void> => {
    setConsultando(true);
    setSugerencia(null);
    try {
      const resultado = await consultarPadron(normalizarCuit(cuit));
      setConsulta(resultado);
      if (resultado.estado === "ENCONTRADO" && resultado.datos !== null) {
        aplicar(resultado.datos.razon_social, resultado.datos.condicion_iva);
      }
    } catch (error) {
      setConsulta({
        estado: "NO_DISPONIBLE",
        datos: null,
        motivo:
          error instanceof ErrorDeFormulario
            ? error.detalle
            : "No pudimos consultar el padrón de ARCA.",
      });
    } finally {
      setConsultando(false);
    }
  };

  /** Rellena lo que está vacío; ofrece —sin aplicar— lo que difiere. */
  const aplicar = (razon: string | null, condicion: string | null): void => {
    const razonVacia = razonSocial.trim() === "";
    if (razon !== null && razonVacia) {
      setRazonSocial(razon);
    }
    if (condicion !== null && !condicionElegida) {
      setCondicionIva(condicion);
      setCondicionElegida(true);
    }
    const razonDifiere = razon !== null && !razonVacia && razon !== razonSocial;
    const condicionDifiere = condicion !== null && condicionElegida && condicion !== condicionIva;
    if (razonDifiere || condicionDifiere) {
      setSugerencia({
        razonSocial: razonDifiere ? razon : null,
        condicionIva: condicionDifiere ? condicion : null,
      });
    }
  };

  const aceptarSugerencia = (): void => {
    if (sugerencia === null) {
      return;
    }
    if (sugerencia.razonSocial !== null) {
      setRazonSocial(sugerencia.razonSocial);
    }
    if (sugerencia.condicionIva !== null) {
      setCondicionIva(sugerencia.condicionIva);
      setCondicionElegida(true);
    }
    setSugerencia(null);
  };

  const enviar = async (evento: React.FormEvent): Promise<void> => {
    evento.preventDefault();
    setGeneral(null);
    setGuardado(false);
    try {
      await ejecutar(
        async () => {
          await guardarEmpresa({
            razon_social: razonSocial,
            cuit: normalizarCuit(cuit),
            condicion_iva: condicionIva,
            nombre_responsable: nombreResponsable,
            email_contacto: emailContacto,
          });
          // Edición: la confirmación se muestra ya, sin esperar el refresco de la página.
          if (!enOnboarding) {
            setGuardado(true);
          }
        },
        (_resultado, router) => (enOnboarding ? router.push("/panel") : router.refresh()),
      );
    } catch (error) {
      setGeneral(
        error instanceof ErrorDeFormulario
          ? error.detalle
          : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      );
    }
  };

  /*
   * Los campos, armados una vez. Abajo se acomodan de dos maneras distintas.
   *
   * El CUIT se reescribe con guiones al salir del campo y no mientras se tipea: mover el
   * cursor por debajo de quien está escribiendo es cómo se pierde un dígito en el medio.
   * Al backend viaja normalizado igual, así que los guiones son presentación y nada más.
   */
  const campoCuit = (
    <Campo
      id="cuit"
      etiqueta="CUIT"
      mono
      inputMode="numeric"
      required
      placeholder="30-71234567-1"
      ayuda={enOnboarding ? "Se valida contra el padrón de ARCA." : undefined}
      error={errorCuit ?? undefined}
      value={cuit}
      onChange={(evento) => cambiarCuit(evento.target.value)}
      onBlur={() => setCuit((previo) => formatearCuit(previo))}
    />
  );

  const campoCondicion = (
    <Select
      id="condicion-iva"
      etiqueta="Condición IVA"
      opciones={OPCIONES_DE_CONDICION}
      value={condicionIva}
      ayuda={enOnboarding ? "ARCA la completa cuando encuentra el CUIT." : undefined}
      onChange={(evento) => {
        setCondicionIva(evento.target.value);
        setCondicionElegida(true);
      }}
    />
  );

  const botonValidar = cuitOk ? (
    <Button
      type="button"
      variante="secundario"
      cargando={consultando}
      onClick={() => void validar()}
    >
      Validar contra ARCA
    </Button>
  ) : null;

  /*
   * La respuesta de ARCA, con la clase del envoltorio como parámetro.
   *
   * En el panel el aviso es lo último de su sección y separa por arriba; en el alta guiada
   * queda en el medio de una columna de campos y separa por abajo. Es la misma respuesta
   * con dos aires distintos, no dos bloques.
   */
  const respuestaDelPadron = (clase: string): JSX.Element => (
    <>
      {consulta !== null && (
        <div className={clase}>
          <Alert tono={tonoDe(consulta)}>{mensajeDe(consulta)}</Alert>
        </div>
      )}

      {/* Lo que el padrón devolvió, tal cual llegó y separado de los campos editables: es
          la única forma de que se vea qué dijo ARCA sin confundirlo con lo que se tipeó. */}
      {consulta !== null && consulta.datos !== null && (
        <dl className="onb-padron">
          <div className="onb-padron__titulo">Lo que devolvió el padrón</div>
          <dt>Denominación</dt>
          <dd>{consulta.datos.razon_social ?? "—"}</dd>
          <dt>Condición</dt>
          <dd>
            {consulta.datos.condicion_iva === null
              ? "—"
              : etiquetaDeCondicion(consulta.datos.condicion_iva)}
          </dd>
          <dt>Situación</dt>
          <dd>{consulta.datos.activo ? "Activa" : "Inactiva"}</dd>
        </dl>
      )}

      {sugerencia !== null && (
        <div className={clase}>
          <Alert tono="advertencia">
            {textoDeSugerencia(sugerencia)}
            <div style={{ marginTop: "var(--space-2)" }}>
              <Button type="button" variante="secundario" onClick={aceptarSugerencia}>
                Usar los datos de ARCA
              </Button>
            </div>
          </Alert>
        </div>
      )}
    </>
  );

  const campoRazonSocial = (
    <Campo
      id="razon-social"
      etiqueta="Razón social"
      required
      value={razonSocial}
      onChange={(evento) => setRazonSocial(evento.target.value)}
    />
  );

  const campoResponsable = (
    <Campo
      id="responsable"
      etiqueta="Nombre del responsable"
      required
      value={nombreResponsable}
      onChange={(evento) => setNombreResponsable(evento.target.value)}
    />
  );

  const campoEmail = (
    <Campo
      id="email-contacto"
      etiqueta="Email de contacto"
      type="email"
      required
      value={emailContacto}
      onChange={(evento) => setEmailContacto(evento.target.value)}
    />
  );

  const avisos = (
    <>
      {general !== null && (
        <div className="acc-aviso">
          <Alert tono="error">{general}</Alert>
        </div>
      )}
      {guardado && (
        <div className="acc-aviso">
          <Alert tono="exito">Guardamos los datos de la empresa.</Alert>
        </div>
      )}
    </>
  );

  // El título lo pone la página: repetirlo en la tarjeta daría dos encabezados iguales
  // seguidos, que es lo que hacía antes.
  if (!enOnboarding) {
    return (
      <>
        {avisos}
        <div className="cfg-panel">
          <div className="cfg-panel__cab">
            <h2 className="cfg-panel__titulo">Datos fiscales</h2>
            {/* El CUIT con guiones vive acá, en la cabecera, y no dentro del campo: el
                campo es editable y reescribirlo mientras alguien tipea mueve el cursor por
                debajo de su mano. Acá se lee de un vistazo y en el formato en el que se
                dicta por teléfono. */}
            {cuitOk ? (
              <p className="cfg-panel__cuenta">CUIT {formatearCuit(cuit)}</p>
            ) : (
              <p className="cfg-panel__nota">Se imprimen en cada comprobante</p>
            )}
          </div>

          <form onSubmit={(evento) => void enviar(evento)} noValidate>
            <section className="cfg-seccion">
              <h3 className="cfg-seccion__titulo">Identificación ante ARCA</h3>
              <p className="cfg-seccion__nota">
                El CUIT y la condición con la que se emite. Validalos contra el padrón antes de
                facturar: un comprobante mal identificado no se corrige, se anula.
              </p>

              <div className="cfg-campos">
                {/* El botón va pegado al campo que valida. Suelto entre «Condición IVA» y
                    «Razón social» no pertenecía a ninguno de los dos. */}
                <div className="cfg-cuit cfg-campos__ancho">
                  {campoCuit}
                  {botonValidar}
                </div>
                {campoCondicion}
              </div>

              {respuestaDelPadron("cfg-aviso")}
            </section>

            <section className="cfg-seccion">
              <h3 className="cfg-seccion__titulo">Quién figura y a quién escribirle</h3>
              <p className="cfg-seccion__nota">
                La razón social sale impresa en el comprobante. El email es al que llegan los avisos
                de facturación.
              </p>

              <div className="cfg-campos">
                <div className="cfg-campos__ancho">{campoRazonSocial}</div>
                {campoResponsable}
                {campoEmail}
              </div>
            </section>

            <div className="cfg-panel__pie">
              <Button type="submit" cargando={enviando} disabled={!completo}>
                Guardar
              </Button>
            </div>
          </form>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="onb-stepper">
        <div className="onb-stepper__caja">
          <Stepper pasos={PASOS_DEL_ONBOARDING} actual={2} />
        </div>
      </div>

      <section className="acc-tarjeta">
        <p className="onb-etiqueta">
          <span className="onb-etiqueta__paso">PASO 2 DE 3</span>
          <span className="onb-etiqueta__titulo">DATOS DE TU EMPRESA</span>
        </p>
        <div className="onb-progreso">
          <span className="onb-progreso__avance" style={{ width: avanceDelPaso(2) }} />
        </div>

        <h1 className="onb-titulo">Contanos sobre tu negocio</h1>
        <p className="onb-sub">Solo lo esencial para conectarte con ARCA.</p>

        {avisos}

        <form onSubmit={(evento) => void enviar(evento)} noValidate>
          <div className="onb-dos-columnas">
            {campoCuit}
            {campoCondicion}
          </div>

          {botonValidar !== null && (
            <div style={{ marginBottom: "var(--space-4)" }}>{botonValidar}</div>
          )}

          {respuestaDelPadron("cfg-aviso cfg-aviso--abajo")}

          {campoRazonSocial}
          {campoResponsable}
          {campoEmail}

          <div className="onb-proteccion">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="4" y="11" width="16" height="9" rx="2" />
              <path d="M8 11V8a4 4 0 0 1 8 0v3" />
            </svg>
            <p style={{ margin: 0 }}>
              <b>Tus datos están protegidos.</b> Se usan únicamente para conectar con ARCA. No los
              compartimos con terceros.
            </p>
          </div>

          {/* «"Continuar" permanece deshabilitado mientras el CUIT no sea válido», y ahora
              también mientras ARCA diga que ese CUIT no existe (RN-01). */}
          <div className="onb-acciones">
            <Button variante="secundario" onClick={() => router.back()}>
              Volver
            </Button>
            <span className="onb-acciones__separador" />
            <Button type="submit" cargando={enviando} disabled={!completo}>
              Continuar
            </Button>
          </div>
        </form>
      </section>
    </>
  );
}

function tonoDe(consulta: ConsultaDePadron): "exito" | "error" | "advertencia" {
  if (consulta.estado === "NO_ENCONTRADO") {
    return "error";
  }
  if (consulta.estado === "NO_DISPONIBLE") {
    return "advertencia";
  }
  return consulta.datos !== null && !consulta.datos.activo ? "advertencia" : "exito";
}

function mensajeDe(consulta: ConsultaDePadron): string {
  if (consulta.estado === "NO_ENCONTRADO") {
    return "ARCA no encuentra este CUIT en su padrón. Revisalo antes de continuar.";
  }
  if (consulta.estado === "NO_DISPONIBLE") {
    // El caso de todos los días hasta que la empresa conecta ARCA. No bloquea nada.
    const motivo = consulta.motivo === null ? "" : `: ${consulta.motivo}`;
    return `No pudimos consultar el padrón de ARCA${motivo}. Podés continuar y validarlo más tarde.`;
  }
  if (consulta.datos !== null && !consulta.datos.activo) {
    return "ARCA conoce este CUIT, pero figura como inactivo en su padrón.";
  }
  const razon = consulta.datos === null ? null : consulta.datos.razon_social;
  return `CUIT verificado en ARCA${razon === null ? "" : `: ${razon}`}.`;
}

function textoDeSugerencia(sugerencia: Sugerencia): string {
  const partes: string[] = [];
  if (sugerencia.razonSocial !== null) {
    partes.push(`razón social «${sugerencia.razonSocial}»`);
  }
  if (sugerencia.condicionIva !== null) {
    partes.push(`condición IVA ${etiquetaDeCondicion(sugerencia.condicionIva)}`);
  }
  return `En ARCA figura con ${partes.join(" y ")}.`;
}

function etiquetaDeCondicion(valor: string): string {
  return CONDICIONES.find((condicion) => condicion.valor === valor)?.texto ?? valor;
}
