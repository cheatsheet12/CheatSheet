/**
 * Los pictogramas de las tres pantallas de reportería.
 *
 * **SVG en línea y no una librería de iconos.** Son once trazos: una dependencia nueva
 * traería mil, un archivo de fuente y una decisión de licencia para dibujar una flecha.
 * Todos comparten `currentColor`, así que el color lo decide la clase que los contiene y
 * no hay un solo valor de color acá adentro.
 *
 * Son decorativos: el texto que acompaña a cada uno ya dice lo que el icono ilustra, y un
 * lector de pantalla que los anunciara leería dos veces lo mismo. De ahí el `aria-hidden`.
 */

import type { ReactNode } from "react";

function Trazo({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function IconoDocumento(): JSX.Element {
  return (
    <Trazo>
      <path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" />
      <path d="M14 2v5h5" />
    </Trazo>
  );
}

export function IconoTarjeta(): JSX.Element {
  return (
    <Trazo>
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
      <path d="M2.5 9.5h19" />
    </Trazo>
  );
}

export function IconoCalendario(): JSX.Element {
  return (
    <Trazo>
      <rect x="3" y="4.5" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 2.5v4M16 2.5v4" />
    </Trazo>
  );
}

export function IconoReloj(): JSX.Element {
  return (
    <Trazo>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Trazo>
  );
}

export function IconoLista(): JSX.Element {
  return (
    <Trazo>
      <path d="M8 4h11M8 9h11M8 14h11M8 19h11" />
      <circle cx="3.5" cy="4" r="1.2" />
      <circle cx="3.5" cy="9" r="1.2" />
      <circle cx="3.5" cy="14" r="1.2" />
      <circle cx="3.5" cy="19" r="1.2" />
    </Trazo>
  );
}

export function IconoBarras(): JSX.Element {
  return (
    <Trazo>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </Trazo>
  );
}

export function IconoDescarga(): JSX.Element {
  return (
    <Trazo>
      <path d="M12 3v12m0 0-4-4m4 4 4-4M5 19h14" />
    </Trazo>
  );
}

export function IconoTilde(): JSX.Element {
  return (
    <Trazo>
      <path d="M5 13l4 4L19 7" />
    </Trazo>
  );
}

export function IconoCruz(): JSX.Element {
  return (
    <Trazo>
      <path d="M18 6 6 18M6 6l12 12" />
    </Trazo>
  );
}

export function IconoEnvio(): JSX.Element {
  return (
    <Trazo>
      <path d="M12 3v3m0 12v3M3 12h3m12 0h3" />
      <circle cx="12" cy="12" r="4" />
    </Trazo>
  );
}

export function IconoPersona(): JSX.Element {
  return (
    <Trazo>
      <path d="M16 7a4 4 0 1 0-8 0M4 21v-1a6 6 0 0 1 12 0v1M19 8v6M22 11h-6" />
    </Trazo>
  );
}

export function IconoPregunta(): JSX.Element {
  return (
    <Trazo>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 0 1 4.5 1.5c0 1.5-2 2-2 3.5" />
      <circle cx="12" cy="17.5" r="0.6" fill="currentColor" />
    </Trazo>
  );
}

export function IconoOjo(): JSX.Element {
  return (
    <Trazo>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </Trazo>
  );
}
