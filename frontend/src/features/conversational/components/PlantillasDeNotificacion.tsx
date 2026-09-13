/**
 * PAN-CFG-NOT — Configuración · Plantillas (HU-E11-02).
 *
 * **No hay alta ni baja.** Los códigos los define el sistema —son los mensajes que el sistema
 * manda— y lo que un administrador hace es editar el cuerpo. Una plantilla con un código que
 * nadie envía sería una plantilla que no se usa nunca.
 *
 * **Las variables se ofrecen, no se adivinan.** El backend rechaza `{{saldo}}` en un
 * recordatorio de turno con la frase de la historia; esta pantalla muestra cuáles admite cada
 * plantilla y avisa mientras se escribe. La validación de verdad sigue siendo del backend: dos
 * pestañas pasan cualquier comprobación del navegador.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Modal, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_APROBACION,
  ETIQUETAS_DE_CODIGO,
  ErrorDeFaq,
  MENSAJE_VARIABLE_INVALIDA,
  editarPlantilla,
  listarPlantillas,
  variablesInvalidas,
} from "../api/faq";
import type { ListadoDePlantillas, Plantilla } from "../api/faq";

export interface PropsDePlantillasDeNotificacion {
  readonly inicial: ListadoDePlantillas;
  /** Sólo el Administrador edita; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
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

  const invalidas = editando === null ? [] : variablesInvalidas(cuerpo, editando.variables);

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

  const columnas: readonly Columna<Plantilla>[] = [
    {
      clave: "codigo",
      titulo: "Mensaje",
      // El nombre legible y no el código: una pantalla de configuración que muestra
      // identificadores del sistema es una pantalla que obliga a adivinar.
      celda: (fila) => ETIQUETAS_DE_CODIGO[fila.codigo] ?? fila.codigo,
    },
    { clave: "canal", titulo: "Canal", celda: (fila) => fila.canal },
    { clave: "idioma", titulo: "Idioma", celda: (fila) => fila.idioma },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.puede_usarse ? "ok" : "atencion"}>
          {ETIQUETAS_DE_APROBACION[fila.estado_aprobacion]}
        </Badge>
      ),
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <Button
            variante="secundario"
            onClick={() => {
              setEditando(fila);
              setCuerpo(fila.cuerpo);
            }}
          >
            Editar texto
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {listado.plantillas.some((una) => !una.puede_usarse) && (
        // RN-04: una plantilla de WhatsApp sin aprobar no se puede usar por ese canal. Decirlo
        // acá evita que alguien edite el texto y se pregunte por qué el cliente no recibe nada.
        <Alert tono="advertencia" titulo="Hay plantillas sin aprobar">
          WhatsApp exige que Meta apruebe las plantillas antes de poder enviarlas. Mientras tanto,
          el sistema manda el texto de fábrica.
        </Alert>
      )}

      <Tabla
        titulo="Plantillas de notificación"
        columnas={columnas}
        filas={listado.plantillas}
        claveDeFila={(fila) => fila.id}
        vacia="No hay plantillas configuradas."
      />

      <Modal
        abierto={editando !== null}
        titulo={editando === null ? "" : (ETIQUETAS_DE_CODIGO[editando.codigo] ?? editando.codigo)}
        onCerrar={() => setEditando(null)}
      >
        {editando !== null && (
          <form
            className="dm-formulario"
            onSubmit={(evento) => {
              evento.preventDefault();
              void guardar();
            }}
          >
            <Card titulo="Variables disponibles">
              <p className="dm-intro">
                Escribilas entre llaves dobles. El sistema las reemplaza al enviar; una que no esté
                en esta lista no se puede guardar.
              </p>
              <p className="fac-mono">{editando.variables.map((una) => `{{${una}}}`).join("  ")}</p>
            </Card>

            <Campo
              id="plantilla-cuerpo"
              etiqueta="Texto del mensaje"
              value={cuerpo}
              onChange={(evento) => setCuerpo(evento.target.value)}
            />

            {invalidas.length > 0 && (
              <Alert tono="error" titulo={MENSAJE_VARIABLE_INVALIDA}>
                {invalidas.map((una) => `{{${una}}}`).join(", ")}
              </Alert>
            )}

            <div className="dm-formulario__acciones">
              <Button variante="secundario" onClick={() => setEditando(null)}>
                Volver
              </Button>
              <Button
                type="submit"
                disabled={invalidas.length > 0 || cuerpo.trim() === ""}
                cargando={trabajando}
              >
                Guardar
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
