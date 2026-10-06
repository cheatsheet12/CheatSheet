"use client";

/**
 * La navegación de la barra lateral: el mapa de
 * `docs/aidlc/inputs/prototipos/mapa-navegacion-oficial.html`, en cuatro grupos.
 *
 * **Es un componente de cliente por una sola razón: saber en qué pantalla está la persona.**
 * `usePathname` es lo que permite marcar la entrada activa; el resto —los grupos, los
 * textos, los iconos— es datos. Antes la barra era una lista de enlaces idénticos y quien
 * entraba a una pantalla profunda no tenía forma de ubicarse en el mapa.
 *
 * **Los iconos son marcado y no una dependencia**, por la misma razón que los del
 * dashboard (`panel/iconos.tsx`): veintitrés paths de 24×24 no justifican un árbol de
 * dependencias. Todos son `aria-hidden`; el texto de al lado dice lo mismo.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

type NombreDeIcono =
  | "inicio"
  | "ingesta"
  | "clientes"
  | "servicios"
  | "categorias"
  | "facturacion"
  | "cobros"
  | "agenda"
  | "recursos"
  | "whatsapp"
  | "reportes"
  | "log"
  | "empresa"
  | "usuarios"
  | "integraciones"
  | "puntos"
  | "reglas"
  | "respuestas"
  | "plantillas"
  | "paquete"
  | "notificaciones"
  | "preferencias"
  | "soporte";

interface EntradaDeNavegacion {
  readonly href: string;
  readonly etiqueta: string;
  readonly icono: NombreDeIcono;
}

interface GrupoDeNavegacion {
  readonly titulo: string;
  readonly entradas: readonly EntradaDeNavegacion[];
}

export const NAVEGACION: readonly GrupoDeNavegacion[] = [
  { titulo: "General", entradas: [{ href: "/panel", etiqueta: "Inicio", icono: "inicio" }] },
  {
    titulo: "Operaciones",
    entradas: [
      { href: "/ingesta", etiqueta: "Ingesta de datos", icono: "ingesta" },
      { href: "/datos-maestros/clientes", etiqueta: "Clientes", icono: "clientes" },
      { href: "/datos-maestros/servicios", etiqueta: "Servicios", icono: "servicios" },
      { href: "/datos-maestros/categorias", etiqueta: "Categorías", icono: "categorias" },
      { href: "/facturacion", etiqueta: "Facturación", icono: "facturacion" },
      { href: "/cobros", etiqueta: "Cobros", icono: "cobros" },
      { href: "/agenda", etiqueta: "Agenda", icono: "agenda" },
      { href: "/agenda/recursos", etiqueta: "Recursos", icono: "recursos" },
      { href: "/conversaciones", etiqueta: "Agente WhatsApp", icono: "whatsapp" },
    ],
  },
  {
    titulo: "Análisis",
    entradas: [
      { href: "/reportes", etiqueta: "Reportes", icono: "reportes" },
      { href: "/auditoria", etiqueta: "Log de operaciones", icono: "log" },
    ],
  },
  {
    titulo: "Sistema",
    entradas: [
      { href: "/configuracion/empresa", etiqueta: "Empresa", icono: "empresa" },
      { href: "/configuracion/usuarios", etiqueta: "Usuarios", icono: "usuarios" },
      { href: "/configuracion/integraciones", etiqueta: "Integraciones", icono: "integraciones" },
      { href: "/facturacion/puntos-de-venta", etiqueta: "Puntos de venta", icono: "puntos" },
      { href: "/configuracion/reglas", etiqueta: "Reglas de negocio", icono: "reglas" },
      { href: "/configuracion/respuestas", etiqueta: "Respuestas frecuentes", icono: "respuestas" },
      { href: "/configuracion/plantillas", etiqueta: "Plantillas", icono: "plantillas" },
      {
        href: "/configuracion/paquete-contable",
        etiqueta: "Paquete contable",
        icono: "paquete",
      },
      {
        href: "/configuracion/notificaciones",
        etiqueta: "Notificaciones",
        icono: "notificaciones",
      },
      { href: "/configuracion/preferencias", etiqueta: "Mis preferencias", icono: "preferencias" },
      { href: "/soporte", etiqueta: "Soporte", icono: "soporte" },
    ],
  },
];

/**
 * La entrada que corresponde a una ruta: **la más específica que la contiene**.
 *
 * No alcanza con `startsWith`: `/facturacion/puntos-de-venta` empieza con `/facturacion` y
 * `/agenda/recursos` con `/agenda`, y marcar las dos a la vez es peor que no marcar
 * ninguna. Por eso se compara por segmento (`/agenda` no contiene a `/agendamiento`) y gana
 * el `href` más largo.
 */
export function hrefActivo(ruta: string, hrefs: readonly string[]): string | null {
  let mejor: string | null = null;
  for (const href of hrefs) {
    const contiene = ruta === href || ruta.startsWith(`${href}/`);
    if (contiene && (mejor === null || href.length > mejor.length)) {
      mejor = href;
    }
  }
  return mejor;
}

const HREFS = NAVEGACION.flatMap((grupo) => grupo.entradas.map((entrada) => entrada.href));

const TRAZOS: Readonly<Record<NombreDeIcono, JSX.Element>> = {
  inicio: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
    </>
  ),
  ingesta: (
    <>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
    </>
  ),
  clientes: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M16 4.7a3.5 3.5 0 0 1 0 6.6M18 14.2a6.5 6.5 0 0 1 3.5 5.8" />
    </>
  ),
  servicios: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 13h18" />
    </>
  ),
  categorias: (
    <>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </>
  ),
  facturacion: (
    <>
      <path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" />
      <path d="M14 2v5h5M8.5 13h7M8.5 17h5" />
    </>
  ),
  cobros: (
    <>
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
      <path d="M2.5 9.5h19M6 15h3" />
    </>
  ),
  agenda: (
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 2.5v4M16 2.5v4" />
    </>
  ),
  recursos: (
    <>
      <path d="m12 3 8.5 4.5v9L12 21l-8.5-4.5v-9L12 3Z" />
      <path d="M12 12 3.8 7.7M12 12l8.2-4.3M12 12v9" />
    </>
  ),
  whatsapp: (
    <>
      <path d="M4 20l1.3-4.2A8.5 8.5 0 1 1 8.3 18.8L4 20Z" />
      <path d="M9 10c.4 2 2 3.6 4 4l1.4-1.2 2 .9c-.3 1.2-1.4 1.8-2.4 1.6-3-.6-5.4-3-6-6-.2-1 .5-2.1 1.7-2.4l.9 2L9 10Z" />
    </>
  ),
  reportes: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  log: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  empresa: (
    <>
      <path d="M4 21V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v16M14 10h5a1 1 0 0 1 1 1v10M2 21h20" />
      <path d="M8 8h2M8 12h2M8 16h2" />
    </>
  ),
  usuarios: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  integraciones: (
    <>
      <path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0V8Z" />
      <path d="M12 17v4" />
    </>
  ),
  puntos: (
    <>
      <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.5" />
    </>
  ),
  reglas: (
    <>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </>
  ),
  respuestas: (
    <>
      <path d="M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V5Z" />
      <path d="M8 9h8M8 12h5" />
    </>
  ),
  plantillas: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 9v12" />
    </>
  ),
  paquete: (
    <>
      <path d="m12 3 8.5 4.5v9L12 21l-8.5-4.5v-9L12 3Z" />
      <path d="m7.5 5.5 8.5 4.7M3.5 7.5 12 12l8.5-4.5" />
    </>
  ),
  notificaciones: (
    <>
      <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z" />
      <path d="M10 21h4" />
    </>
  ),
  preferencias: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
    </>
  ),
  soporte: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="m5.6 5.6 3.9 3.9M14.5 14.5l3.9 3.9M18.4 5.6l-3.9 3.9M9.5 14.5l-3.9 3.9" />
    </>
  ),
};

function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  return (
    <svg
      className="nav__icono"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {TRAZOS[nombre]}
    </svg>
  );
}

export function NavegacionLateral(): JSX.Element {
  const activo = hrefActivo(usePathname() ?? "", HREFS);
  const nav = useRef<HTMLElement>(null);

  // La barra tiene más entradas que alto: sin esto, quien llega a «Puntos de venta» o
  // «Soporte» ve una barra sin ninguna entrada marcada, porque la activa quedó debajo del
  // borde. `nearest` no mueve nada si ya se ve, así que no salta en cada navegación.
  useEffect(() => {
    nav.current
      ?.querySelector<HTMLElement>(".nav__item--activo")
      ?.scrollIntoView({ block: "nearest" });
  }, [activo]);

  return (
    <nav ref={nav} aria-label="Secciones" className="nav">
      {NAVEGACION.map((grupo) => (
        <div key={grupo.titulo} className="nav__group">
          <p className="nav__label">{grupo.titulo}</p>
          {grupo.entradas.map((entrada) => {
            const esActiva = entrada.href === activo;
            return (
              <Link
                key={entrada.href}
                className={esActiva ? "nav__item nav__item--activo" : "nav__item"}
                href={entrada.href}
                aria-current={esActiva ? "page" : undefined}
              >
                <Icono nombre={entrada.icono} />
                <span>{entrada.etiqueta}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
