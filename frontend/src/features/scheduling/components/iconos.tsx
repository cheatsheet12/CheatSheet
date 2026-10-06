/**
 * Los cuatro iconos que dibujan las pantallas de la agenda.
 *
 * SVG en línea y no una librería: son cuatro trazos, pesan menos que el `import` que los
 * traería y CLAUDE.md §5 no quiere una dependencia nueva para dibujar un reloj.
 *
 * **Todos van con `aria-hidden`, que lo pone quien los usa.** Un icono al lado de un texto que
 * dice lo mismo, anunciado dos veces, es ruido para quien escucha la pantalla; el `<svg>` no
 * lleva `<title>` por la misma razón.
 *
 * El `viewBox` es 24×24 y el color sale de `currentColor`: así el mismo icono sirve en el
 * cintillo del encabezado y adentro de una tarjeta sin una variante por cada tono.
 */

/** El «+» del CTA. */
export function IconoDeMas(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

/** El reloj de la disponibilidad: la pregunta que el alta de un turno contesta. */
export function IconoDeReloj(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.2l3.4 2" strokeLinecap="round" />
    </svg>
  );
}

/** El calendario del formulario de alta. */
export function IconoDeCalendario(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
      <path d="M3.5 10h17M8.5 3v4M15.5 3v4" strokeLinecap="round" />
    </svg>
  );
}

/** Flecha de navegación: `izquierda` retrocede el período, `derecha` lo avanza. */
export function IconoDeFlecha({
  sentido = "derecha",
}: {
  readonly sentido?: "izquierda" | "derecha";
}): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path
        d={sentido === "derecha" ? "M9.5 5.5 16 12l-6.5 6.5" : "M14.5 5.5 8 12l6.5 6.5"}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Las tres filas de la vista Lista. */
export function IconoDeLista(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
      <path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20" strokeLinecap="round" />
      <path d="M4 6.5h.01M4 12h.01M4 17.5h.01" strokeLinecap="round" strokeWidth="2.6" />
    </svg>
  );
}

/** La grilla de la vista Semana. */
export function IconoDeSemana(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9.2 4.5v15M14.8 4.5v15M3.5 10h17" strokeLinecap="round" />
    </svg>
  );
}

/** La columna de la vista Día. */
export function IconoDeDia(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M3.5 10h17M8 14h8" strokeLinecap="round" />
    </svg>
  );
}

/** Los deslizadores de «Más filtros». */
export function IconoDeFiltro(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" strokeLinecap="round" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="17" r="2" />
    </svg>
  );
}

/** La «x» de «Limpiar filtros». */
export function IconoDeLimpiar(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" strokeLinecap="round" />
    </svg>
  );
}

/** Una persona, un espacio o un equipo: lo que se reserva. */
export function IconoDeRecurso(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="3.4" />
      <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" strokeLinecap="round" />
    </svg>
  );
}
