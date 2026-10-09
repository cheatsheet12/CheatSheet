/**
 * PAN-CFG-NOT — Configuración · Plantillas (HU-E11-02).
 *
 * El listado se pide siempre: el backend siembra las plantillas de fábrica que falten la
 * primera vez que una empresa entra acá.
 *
 * El encabezado lo dibuja el componente, igual que en respuestas frecuentes: las dos pantallas
 * de configuración del canal comparten la misma cabecera, y tenerla en un solo lado es lo que
 * evita que se separen con el tiempo.
 */

import { redirect } from "next/navigation";

import { agendaDe } from "@/features/business_config";
import type { ListadoDeReglasCrudo } from "@/features/business_config";
import { AdvertenciaDeRecordatorio, PlantillasDeNotificacion } from "@/features/conversational";
import type { ListadoDePlantillas } from "@/features/conversational";
import type { ListadoDeIntegraciones } from "@/features/integrations";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Plantillas · CheatSheet" };

/**
 * Un dato que solo afina la advertencia: si no se puede leer, la advertencia se muestra (el
 * comportamiento de antes) en lugar de romper la pantalla de plantillas.
 */
async function leerOpcional<T>(ruta: string): Promise<T | null> {
  try {
    return await llamarApi<T>(ruta);
  } catch {
    return null;
  }
}

export default async function PaginaDePlantillas(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const [listado, reglas, integraciones] = await Promise.all([
    llamarApi<ListadoDePlantillas>("/plantillas"),
    leerOpcional<ListadoDeReglasCrudo>("/reglas"),
    leerOpcional<ListadoDeIntegraciones>("/integraciones"),
  ]);
  // Sin regla de agenda rige el recordatorio por defecto: encendido. Es el backend quien decide.
  const agenda = reglas === null ? null : agendaDe(reglas);
  const recordatoriosActivos = agenda === null || agenda.activa;
  const whatsappConectado =
    integraciones === null ||
    integraciones.integraciones.some((i) => i.sistema === "WHATSAPP" && i.estado === "CONECTADO");

  return (
    <>
      <AdvertenciaDeRecordatorio
        plantillas={listado.plantillas}
        recordatoriosActivos={recordatoriosActivos}
        whatsappConectado={whatsappConectado}
      />
      <PlantillasDeNotificacion inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
