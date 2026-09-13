/**
 * Los iconos de las tres pantallas de ingesta, transcriptos de
 * `docs/aidlc/inputs/prototipos/ingesta.html`.
 *
 * **Son marcado y no una dependencia**, por lo mismo que en el resto del panel: una librería
 * de iconos por nueve glifos son cientos de kilobytes y un árbol de dependencias que auditar.
 *
 * **Todos son `aria-hidden`.** Ninguno dice algo que su texto de al lado no diga; anunciarlos
 * haría que el lector de pantalla lea la fila dos veces.
 */

export type NombreDeIcono =
  | "nube"
  | "archivo"
  | "planilla"
  | "candado"
  | "chispa"
  | "refrescar"
  | "documento"
  | "alerta"
  | "tilde";

const TRAZOS: Readonly<Record<NombreDeIcono, JSX.Element>> = {
  nube: (
    <>
      <path d="M12 16V7m0 0L8 11m4-4 4 4" />
      <path d="M20 16.5A4.5 4.5 0 0 0 17 8a6 6 0 0 0-11.6 1.5A4 4 0 0 0 6 17" />
    </>
  ),
  archivo: (
    <>
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <path d="M5 3h9l5 5v11a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
    </>
  ),
  planilla: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 3v18" />
    </>
  ),
  candado: (
    <>
      <rect x="4" y="11" width="16" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  chispa: (
    <>
      <path d="M12 3v3m0 12v3M3 12h3m12 0h3" />
      <circle cx="12" cy="12" r="4" />
    </>
  ),
  refrescar: <path d="M21 12a9 9 0 1 1-2.6-6.3M21 4v4h-4" strokeLinecap="round" />,
  documento: (
    <>
      <path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" />
      <path d="M14 2v5h5" />
    </>
  ),
  alerta: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16h.01" />
    </>
  ),
  tilde: <path d="M5 13l4 4L19 7" />,
};

export function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      {TRAZOS[nombre]}
    </svg>
  );
}
