/**
 * The authenticated admin panel.
 *
 * The session check lives here, at the group boundary, so that no screen inside can
 * forget it. It does two things now, where it used to do one:
 *
 * 1. **There is a session.** No cookie, no panel.
 * 2. **The onboarding is finished.** HU-E1-01 RN-04 keeps the dashboard closed until the
 *    company has its fiscal data, and doing it here means every screen added later is
 *    covered without anybody remembering to.
 *
 * The second check costs one API call per navigation. Carrying the flag in the JWT would
 * save it and be wrong: the token lives fifteen minutes, so somebody who just finished
 * step 2 would keep being bounced back to it.
 *
 * **La navegación es una barra lateral, y eso es un arreglo y no una preferencia.** Antes era
 * una fila de enlaces arriba: con veinte pantallas esa fila se partía en tres líneas y cortaba
 * los nombres al medio — que es exactamente lo que muestra la captura de PRU-09. El prototipo
 * (`docs/aidlc/inputs/prototipos/styles.css`) los pone en una columna fija de 244 px agrupados
 * por para qué sirven, y una columna crece hacia abajo sin empujar nada.
 *
 * **Los grupos son el mapa, no decoración.** «Operaciones» es el día a día, «Análisis» es lo
 * que se lee después, «Sistema» es lo que se configura una vez. Quien busca dónde invitar a un
 * usuario no tiene que leer veinte etiquetas, sólo tres grupos.
 *
 * The navigation lists what exists. Entries are added by the unit that builds the screen
 * behind them, never in advance: a menu item leading nowhere is a bug report waiting to
 * be filed.
 */

import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { BotonDeSalida } from "@/features/identity";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion, leerClaims } from "@/lib/session";

interface EstadoDeEmpresa {
  readonly razon_social: string | null;
  readonly onboarding_completo: boolean;
}

interface EntradaDeNavegacion {
  readonly href: string;
  readonly etiqueta: string;
}

interface GrupoDeNavegacion {
  readonly titulo: string;
  readonly entradas: readonly EntradaDeNavegacion[];
}

/** El mapa de `docs/aidlc/inputs/prototipos/mapa-navegacion-oficial.html`, en cuatro grupos. */
const NAVEGACION: readonly GrupoDeNavegacion[] = [
  { titulo: "General", entradas: [{ href: "/panel", etiqueta: "Inicio" }] },
  {
    titulo: "Operaciones",
    entradas: [
      { href: "/ingesta", etiqueta: "Ingesta de datos" },
      { href: "/datos-maestros/clientes", etiqueta: "Clientes" },
      { href: "/datos-maestros/servicios", etiqueta: "Servicios" },
      { href: "/datos-maestros/categorias", etiqueta: "Categorías" },
      { href: "/facturacion", etiqueta: "Facturación" },
      { href: "/cobros", etiqueta: "Cobros" },
      { href: "/agenda", etiqueta: "Agenda" },
      { href: "/agenda/recursos", etiqueta: "Recursos" },
      { href: "/conversaciones", etiqueta: "Agente WhatsApp" },
    ],
  },
  {
    titulo: "Análisis",
    entradas: [
      { href: "/reportes", etiqueta: "Reportes" },
      { href: "/auditoria", etiqueta: "Log de operaciones" },
    ],
  },
  {
    titulo: "Sistema",
    entradas: [
      { href: "/configuracion/empresa", etiqueta: "Empresa" },
      { href: "/configuracion/usuarios", etiqueta: "Usuarios" },
      { href: "/configuracion/integraciones", etiqueta: "Integraciones" },
      { href: "/facturacion/puntos-de-venta", etiqueta: "Puntos de venta" },
      { href: "/configuracion/reglas", etiqueta: "Reglas de negocio" },
      { href: "/configuracion/respuestas", etiqueta: "Respuestas frecuentes" },
      { href: "/configuracion/plantillas", etiqueta: "Plantillas" },
      { href: "/configuracion/paquete-contable", etiqueta: "Paquete contable" },
      { href: "/configuracion/notificaciones", etiqueta: "Notificaciones" },
      { href: "/configuracion/preferencias", etiqueta: "Mis preferencias" },
      { href: "/soporte", etiqueta: "Soporte" },
    ],
  },
];

/** Las dos iniciales de la empresa, para el avatar del encabezado. */
function iniciales(nombre: string): string {
  return nombre
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((palabra) => palabra[0])
    .join("")
    .toUpperCase();
}

export default async function PanelLayout({
  children,
}: {
  readonly children: ReactNode;
}): Promise<JSX.Element> {
  if (!haySesion()) {
    redirect("/");
  }

  const empresa = await estadoDeEmpresa();
  if (empresa === null) {
    // The cookie exists but the API rejected it: expired or revoked. Back to the door.
    redirect("/");
  }
  if (!empresa.onboarding_completo) {
    redirect("/onboarding/empresa");
  }

  const claims = leerClaims();
  const nombre = empresa.razon_social ?? "Tu empresa";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true">
            CS
          </span>
          <span>
            <b className="sidebar__nombre">CheatSheet</b>
            <small className="sidebar__version">iPaaS</small>
          </span>
        </div>

        <nav aria-label="Secciones" className="nav">
          {NAVEGACION.map((grupo) => (
            <div key={grupo.titulo} className="nav__group">
              <p className="nav__label">{grupo.titulo}</p>
              {grupo.entradas.map((entrada) => (
                <Link key={entrada.href} className="nav__item" href={entrada.href}>
                  {entrada.etiqueta}
                </Link>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar__help">
          <b>¿Necesitás ayuda?</b>
          <Link href="/soporte">Abrir una solicitud</Link>
        </div>
      </aside>

      <div className="app__main">
        <header className="topbar">
          <div className="org-switch">
            <span className="org-switch__avatar" aria-hidden="true">
              {iniciales(nombre)}
            </span>
            <span className="org-switch__datos">
              <b>{nombre}</b>
              <small>{claims?.rol.toLowerCase() ?? ""}</small>
            </span>
          </div>
          <div className="topbar__right">
            <BotonDeSalida />
          </div>
        </header>
        <main className="page">{children}</main>
      </div>
    </div>
  );
}

async function estadoDeEmpresa(): Promise<EstadoDeEmpresa | null> {
  try {
    return await llamarApi<EstadoDeEmpresa>("/auth/empresa");
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
