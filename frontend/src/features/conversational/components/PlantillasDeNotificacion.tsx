/**
 * PAN-CFG-NOT — Configuración · Plantillas (HU-E11-02).
 *
 * **No hay alta ni baja.** Los códigos los define el sistema —son los mensajes que el sistema
 * manda— y lo que un administrador hace es editar el cuerpo. Una plantilla con un código que
 * nadie envía sería una plantilla que no se usa nunca. Por eso el encabezado no tiene CTA: lo
 * que lleva a la derecha es cuántas hay y cuántas están frenadas.
 *
 * **Las variables se ofrecen, no se adivinan.** El backend rechaza `{{saldo}}` en un
 * recordatorio de turno con la frase de la historia; esta pantalla muestra cuáles admite cada
 * plantilla, las inserta donde está el cursor y avisa mientras se escribe. La validación de
 * verdad sigue siendo del backend: dos pestañas pasan cualquier comprobación del navegador.
 *
 * **El editor es una tarjeta a la vista, igual que el alta de respuestas frecuentes.** Son la
 * misma pantalla dos veces —una configura lo que el agente contesta, la otra lo que el sistema
 * avisa— y editar el texto de un recordatorio es querer ver los otros cinco al lado.
 *
 * **El listado no muestra el cuerpo.** Una columna con `Hola {{nombre}}, te esperamos…`
 * repetida seis veces es la misma frase seis veces; lo que distingue una fila de la otra es el
 * mensaje que representa, su canal y si Meta ya la aprobó.
 */

"use client";

import {
  Bell,
  CalendarCheck,
  CalendarClock,
  CalendarSync,
  CalendarX,
  CreditCard,
  Info,
  MessageCircle,
  MessageSquareText,
  Pencil,
  TriangleAlert,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useRef, useState } from "react";

import { Alert, Button } from "@/shared";

import {
  ETIQUETAS_DE_APROBACION,
  ETIQUETAS_DE_CANAL,
  ETIQUETAS_DE_CODIGO,
  ErrorDeFaq,
  MENSAJE_VARIABLE_INVALIDA,
  editarPlantilla,
  listarPlantillas,
  nombreDeIdioma,
  variablesInvalidas,
} from "../api/faq";
import type { ListadoDePlantillas, Plantilla } from "../api/faq";

export interface PropsDePlantillasDeNotificacion {
  readonly inicial: ListadoDePlantillas;
  /** Sólo el Administrador edita; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

/**
 * El nombre legible y no el código del sistema.
 *
 * `recordatorio_de_cobro` es un identificador interno, y una pantalla de configuración que
 * muestra identificadores es una pantalla que obliga a adivinar.
 */
function nombreDe(plantilla: Plantilla): string {
  return ETIQUETAS_DE_CODIGO[plantilla.codigo] ?? plantilla.codigo;
}

/** El ícono de cada mensaje, por su código; uno genérico para el que no se conozca. */
const ICONOS_DE_CODIGO: Readonly<Record<string, LucideIcon>> = {
  turno_confirmado: CalendarCheck,
  turno_cancelado: CalendarX,
  turno_reprogramado: CalendarSync,
  recordatorio_de_turno: CalendarClock,
  recordatorio_de_cobro: Bell,
  cobro_generado: CreditCard,
};

function iconoDe(plantilla: Plantilla): LucideIcon {
  return ICONOS_DE_CODIGO[plantilla.codigo] ?? MessageSquareText;
}

/**
 * El único valor de una columna, o `null` si hay más de uno.
 *
 * Decide si la columna vale su ancho. Hoy las seis plantillas comparten canal e idioma: son
 * doce celdas idénticas ocupando un tercio del listado, mientras «Mensaje» —lo único que
 * distingue una fila de otra— se queda con la mitad de ese lugar. Lo constante se dice una
 * vez arriba; la columna vuelve sola el día que el backend mande dos canales.
 */
function unicoValor<T>(valores: readonly T[]): T | null {
  const distintos = Array.from(new Set(valores));
  return distintos.length === 1 ? (distintos[0] ?? null) : null;
}

export function PlantillasDeNotificacion({
  inicial,
  puedeEditar,
}: PropsDePlantillasDeNotificacion): JSX.Element {
  const [listado, setListado] = useState<ListadoDePlantillas>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [editando, setEditando] = useState<Plantilla | null>(null);
  const [cuerpo, setCuerpo] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  const plantillas = listado.plantillas;
  const frenadas = plantillas.filter((una) => !una.puede_usarse).length;
  const invalidas = editando === null ? [] : variablesInvalidas(cuerpo, editando.variables);

  // Canal e idioma sólo van en la tarjeta cuando de verdad varían entre plantillas.
  const canalUnico = unicoValor(plantillas.map((una) => una.canal));
  const idiomaUnico = unicoValor(plantillas.map((una) => una.idioma));

  async function guardar(): Promise<void> {
    if (editando === null) {
      return;
    }
    setError(null);
    setTrabajando(true);
    try {
      await editarPlantilla(editando.id, cuerpo);
      setListado(await listarPlantillas());
      setEditando(null);
    } catch (fallo) {
      setError(fallo instanceof ErrorDeFaq ? fallo.message : "No se pudo guardar la plantilla.");
    } finally {
      setTrabajando(false);
    }
  }

  /**
   * Inserta la variable donde está el cursor.
   *
   * Al final del texto sería más simple y estaría mal: quien está corrigiendo la mitad de un
   * mensaje tendría que cortar y pegar lo que acaba de insertar. El cursor vuelve detrás de la
   * marca recién en el siguiente cuadro, porque antes React todavía no escribió el valor nuevo
   * y la posición se perdería.
   */
  function insertarVariable(nombre: string): void {
    const marca = `{{${nombre}}}`;
    const control = area.current;
    if (control === null) {
      setCuerpo(`${cuerpo}${marca}`);
      return;
    }
    const desde = control.selectionStart;
    const hasta = control.selectionEnd;
    setCuerpo(`${cuerpo.slice(0, desde)}${marca}${cuerpo.slice(hasta)}`);
    const cursor = desde + marca.length;
    requestAnimationFrame(() => {
      control.focus();
      control.setSelectionRange(cursor, cursor);
    });
  }

  return (
    <>
      <header className="pln-encabezado">
        <span className="pln-encabezado__icono" aria-hidden="true">
          <MessageSquareText size={22} strokeWidth={1.75} />
        </span>
        <div>
          <p className="pln-encabezado__eyebrow">Configuración · Notificaciones</p>
          <h1>Plantillas de notificación</h1>
          <p className="pln-encabezado__intro">
            Los mensajes que el sistema manda a tus clientes. Podés editar el texto y usar las
            variables que cada uno admite; el sistema las reemplaza al enviar.
          </p>
        </div>
      </header>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {frenadas > 0 && (
        // RN-04: una plantilla de WhatsApp sin aprobar no se puede usar por ese canal. Decirlo
        // acá evita que alguien edite el texto y se pregunte por qué el cliente no recibe nada.
        <div className="pln-aviso" role="status">
          <TriangleAlert
            className="pln-aviso__icono"
            size={18}
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <div>
            <p className="pln-aviso__titulo">Hay plantillas sin aprobar</p>
            <p className="pln-aviso__texto">
              WhatsApp exige que Meta apruebe las plantillas antes de poder enviarlas. Mientras
              tanto, el sistema manda el texto de fábrica.
            </p>
          </div>
        </div>
      )}

      {editando !== null && (
        <section className="pln-editor" aria-labelledby="pln-editor-titulo">
          <header className="pln-editor__head">
            <div>
              <p className="pln-editor__eyebrow">Editando el texto</p>
              <h2 className="pln-editor__titulo" id="pln-editor-titulo">
                {nombreDe(editando)}
              </h2>
            </div>
            <span className="pln-editor__meta">
              {ETIQUETAS_DE_CANAL[editando.canal]} · {nombreDeIdioma(editando.idioma)}
            </span>
          </header>

          <form
            className="pln-editor__cuerpo"
            onSubmit={(evento) => {
              evento.preventDefault();
              void guardar();
            }}
          >
            <div className="pln-vars">
              <p className="pln-vars__titulo" id="pln-vars-titulo">
                Variables disponibles
              </p>
              <p className="pln-vars__ayuda">
                Van entre llaves dobles y el sistema las reemplaza al enviar; una que no esté en
                esta lista no se puede guardar. Tocá una para insertarla donde tengas el cursor.
              </p>
              {/* La lista lleva nombre accesible: es la respuesta a «¿qué puedo escribir acá?»,
                  y sin él se anuncia como «lista, 4 elementos» al lado de un cuadro de texto. */}
              <ul className="pln-vars__lista" aria-labelledby="pln-vars-titulo">
                {editando.variables.map((una) => (
                  <li key={una}>
                    <button
                      type="button"
                      className="pln-var"
                      onClick={() => insertarVariable(una)}
                    >{`{{${una}}}`}</button>
                  </li>
                ))}
              </ul>
            </div>

            {/* Un `textarea` y no el `Campo` del catálogo: el cuerpo de una notificación son
                varios renglones, y en mono porque lleva marcas que alguien compara carácter
                por carácter contra la lista de arriba. */}
            <div className="campo">
              <label className="campo__etiqueta" htmlFor="plantilla-cuerpo">
                Texto del mensaje
              </label>
              <textarea
                id="plantilla-cuerpo"
                ref={area}
                className="campo__control pln-area"
                rows={5}
                value={cuerpo}
                onChange={(evento) => setCuerpo(evento.target.value)}
              />
            </div>

            {invalidas.length > 0 && (
              <Alert tono="error" titulo={MENSAJE_VARIABLE_INVALIDA}>
                {invalidas.map((una) => `{{${una}}}`).join(", ")}
              </Alert>
            )}

            <div className="pln-editor__pie">
              <button type="button" className="pln-accion" onClick={() => setEditando(null)}>
                Cancelar
              </button>
              <Button
                type="submit"
                disabled={invalidas.length > 0 || cuerpo.trim() === ""}
                cargando={trabajando}
              >
                Guardar
              </Button>
            </div>
          </form>
        </section>
      )}

      <div className="pln-resumen">
        <p className="pln-resumen__cuenta">
          <b>{plantillas.length}</b> {plantillas.length === 1 ? "plantilla" : "plantillas"} ·{" "}
          <b>{frenadas}</b> {frenadas === 1 ? "espera" : "esperan"} la aprobación de Meta
        </p>
        {/* Lo que todas comparten, dicho una vez: repetido en cada tarjeta no es información. */}
        {(canalUnico !== null || idiomaUnico !== null) && (
          <p className="pln-resumen__constante">
            <MessageCircle size={14} strokeWidth={1.75} aria-hidden="true" />
            <span>
              {canalUnico !== null && (
                <>
                  Todas por <b>{ETIQUETAS_DE_CANAL[canalUnico]}</b>
                </>
              )}
              {canalUnico !== null && idiomaUnico !== null && ", "}
              {idiomaUnico !== null && (
                <>
                  en <b>{nombreDeIdioma(idiomaUnico)}</b>
                </>
              )}
            </span>
          </p>
        )}
      </div>

      {plantillas.length === 0 ? (
        <p className="pln-vacia">
          <Info size={16} strokeWidth={1.75} aria-hidden="true" />
          No hay plantillas configuradas.
        </p>
      ) : (
        <ul className="pln-grilla" aria-label="Plantillas de notificación">
          {plantillas.map((una, indice) => {
            const Icono = iconoDe(una);
            return (
              <li
                key={una.id}
                className="pln-tarjeta"
                data-seleccionada={editando?.id === una.id ? "si" : undefined}
                style={{ animationDelay: `${Math.min(indice, 8) * 40}ms` }}
              >
                <div className="pln-tarjeta__cabeza">
                  <span className="pln-tarjeta__icono" aria-hidden="true">
                    <Icono size={20} strokeWidth={1.75} />
                  </span>
                  <div className="pln-tarjeta__titulos">
                    <span className="pln-nombre">{nombreDe(una)}</span>
                    {(canalUnico === null || idiomaUnico === null) && (
                      <span className="pln-tarjeta__meta">
                        {canalUnico === null && ETIQUETAS_DE_CANAL[una.canal]}
                        {canalUnico === null && idiomaUnico === null && " · "}
                        {idiomaUnico === null && nombreDeIdioma(una.idioma)}
                      </span>
                    )}
                  </div>
                </div>
                <p className="pln-tarjeta__cuerpo">{una.cuerpo}</p>
                <div className="pln-tarjeta__pie">
                  <span className="pln-estado" data-tono={una.puede_usarse ? "ok" : "atencion"}>
                    {ETIQUETAS_DE_APROBACION[una.estado_aprobacion]}
                  </span>
                  {puedeEditar && (
                    <button
                      type="button"
                      className="pln-accion"
                      onClick={() => {
                        setEditando(una);
                        setCuerpo(una.cuerpo);
                      }}
                    >
                      <Pencil size={14} strokeWidth={1.75} aria-hidden="true" />
                      Editar texto
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
