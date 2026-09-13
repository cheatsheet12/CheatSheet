/**
 * Los iconos de PAN-DSH-01, transcriptos de `docs/aidlc/inputs/prototipos/dashboard.html`.
 *
 * **Son marcado y no una dependencia.** Traer una librería de iconos por ocho glifos suma
 * cientos de kilobytes y un árbol de dependencias que hay que auditar; ocho paths de 24×24
 * pesan lo que pesan las líneas que se ven acá abajo.
 *
 * **Todos son `aria-hidden`.** Ninguno aporta información que el texto de al lado no diga: el
 * icono del calendario acompaña a la palabra «Turnos». Un `<svg>` anunciado además del texto
 * hace que el lector de pantalla lea la fila dos veces.
 */

export type NombreDeIcono =
  | "documento"
  | "tarjeta"
  | "calendario"
  | "reloj"
  | "barras"
  | "mas"
  | "subir"
  | "lista"
  | "alerta";

const TRAZOS: Readonly<Record<NombreDeIcono, JSX.Element>> = {
  documento: (
    <>
      <path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" />
      <path d="M14 2v5h5" />
    </>
  ),
  tarjeta: (
    <>
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
      <path d="M2.5 9.5h19" />
    </>
  ),
  calendario: (
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 2.5v4M16 2.5v4" />
    </>
  ),
  reloj: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  barras: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" />,
  mas: <path d="M12 5v14M5 12h14" strokeLinecap="round" />,
  subir: (
    <>
      <path d="M12 16V4m0 0L7 9m5-5 5 5" strokeLinecap="round" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
    </>
  ),
  lista: (
    <>
      <path d="M8 4h12M8 9h12M8 14h12M8 19h12" />
      <circle cx="4" cy="4" r="1" />
      <circle cx="4" cy="9" r="1" />
      <circle cx="4" cy="14" r="1" />
      <circle cx="4" cy="19" r="1" />
    </>
  ),
  alerta: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16h.01" />
    </>
  ),
};

export function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      {TRAZOS[nombre]}
    </svg>
  );
}
