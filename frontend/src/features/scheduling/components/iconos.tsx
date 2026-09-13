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

/** Una persona, un espacio o un equipo: lo que se reserva. */
export function IconoDeRecurso(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="3.4" />
      <path d="M4.8 20a7.2 7.2 0 0 1 14.4 0" strokeLinecap="round" />
    </svg>
  );
}
