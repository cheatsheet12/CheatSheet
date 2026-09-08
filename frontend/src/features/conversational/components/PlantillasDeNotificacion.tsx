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

import { useRef, useState } from "react";

import { Alert, Badge, Button, Tabla } from "@/shared";
import type { Columna } from "@/shared";

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

  // Canal e idioma sólo son columna cuando de verdad varían entre filas.
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

  // Sin permiso de edición la columna no existe, en vez de existir con el encabezado puesto
  // y las celdas en blanco: una columna vacía se lee como datos que faltan.
  const acciones: Columna<Plantilla> = {
    clave: "acciones",
    titulo: "Acciones",
    alDerecha: true,
    celda: (fila) => (
      <button
        type="button"
        className="plt-accion"
        onClick={() => {
          setEditando(fila);
          setCuerpo(fila.cuerpo);
        }}
      >
        Editar texto
      </button>
    ),
  };

  const columnas: readonly Columna<Plantilla>[] = [
    {
      clave: "codigo",
      titulo: "Mensaje",
      celda: (fila) => <span className="plt-nombre">{nombreDe(fila)}</span>,
    },
    // `WHATSAPP` y `es_AR` nunca se imprimen crudos: es la misma doctrina que aplica
    // `nombreDe` al código, y no había razón para que estas dos columnas quedaran afuera.
    ...(canalUnico !== null
      ? []
      : [
          {
            clave: "canal",
            titulo: "Canal",
            celda: (fila: Plantilla) => (
              <span className="plt-canal">{ETIQUETAS_DE_CANAL[fila.canal]}</span>
            ),
          },
        ]),
    ...(idiomaUnico !== null
      ? []
      : [
          {
            clave: "idioma",
            titulo: "Idioma",
            celda: (fila: Plantilla) => (
              <span className="plt-idioma">{nombreDeIdioma(fila.idioma)}</span>
            ),
          },
        ]),
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.puede_usarse ? "ok" : "atencion"}>
          {ETIQUETAS_DE_APROBACION[fila.estado_aprobacion]}
        </Badge>
      ),
    },
    ...(puedeEditar ? [acciones] : []),
  ];

  return (
    <>
      <header className="plt-encabezado">
        <div>
          <p className="plt-encabezado__eyebrow">Configuración · Notificaciones</p>
          <h1>Plantillas de notificación</h1>
          <p className="plt-encabezado__intro">
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
        <Alert tono="advertencia" titulo="Hay plantillas sin aprobar">
          WhatsApp exige que Meta apruebe las plantillas antes de poder enviarlas. Mientras tanto,
          el sistema manda el texto de fábrica.
        </Alert>
      )}

      {editando !== null && (
        <section className="plt-editor" aria-labelledby="plt-editor-titulo">
          <header className="plt-editor__head">
            <div>
              <p className="plt-editor__eyebrow">Editando el texto</p>
              <h2 className="plt-editor__titulo" id="plt-editor-titulo">
                {nombreDe(editando)}
              </h2>
            </div>
            <span className="plt-editor__meta">
              {ETIQUETAS_DE_CANAL[editando.canal]} · {nombreDeIdioma(editando.idioma)}
            </span>
          </header>

          <form
            className="plt-editor__cuerpo"
            onSubmit={(evento) => {
              evento.preventDefault();
              void guardar();
            }}
          >
            <div className="plt-vars">
              <p className="plt-vars__titulo" id="plt-vars-titulo">
                Variables disponibles
              </p>
              <p className="plt-vars__ayuda">
                Van entre llaves dobles y el sistema las reemplaza al enviar; una que no esté en
                esta lista no se puede guardar. Tocá una para insertarla donde tengas el cursor.
              </p>
              {/* La lista lleva nombre accesible: es la respuesta a «¿qué puedo escribir acá?»,
                  y sin él se anuncia como «lista, 4 elementos» al lado de un cuadro de texto. */}
              <ul className="plt-vars__lista" aria-labelledby="plt-vars-titulo">
                {editando.variables.map((una) => (
                  <li key={una}>
                    <button
                      type="button"
                      className="plt-var"
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
                className="campo__control plt-area"
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

            <div className="plt-editor__pie">
              <button type="button" className="plt-accion" onClick={() => setEditando(null)}>
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

      <div className="plt-barra">
        <p className="plt-barra__cuenta">
          <b>{plantillas.length}</b> {plantillas.length === 1 ? "plantilla" : "plantillas"} ·{" "}
          <b>{frenadas}</b> {frenadas === 1 ? "espera" : "esperan"} la aprobación de Meta
        </p>
        {/* Lo que todas comparten, dicho una vez. Doce celdas con el mismo valor no son
            información: son ancho que le falta a la columna que sí varía. */}
        {(canalUnico !== null || idiomaUnico !== null) && (
          <p className="plt-barra__constante">
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
          </p>
        )}
      </div>

      <div className="plt-panel">
        <Tabla
          titulo="Plantillas de notificación"
          columnas={columnas}
          filas={plantillas}
          claveDeFila={(fila) => fila.id}
          vacia="No hay plantillas configuradas."
        />
      </div>
    </>
  );
}
