/**
 * Los iconos de las tres pantallas de Datos Maestros.
 *
 * SVG en línea y no una librería: son dos trazos, pesan menos que el `import` que los traería
 * y `CLAUDE.md` §5 no quiere una dependencia nueva para dibujar un «+». Es la misma decisión
 * —y el mismo archivo— que tomó la agenda en `features/scheduling/components/iconos.tsx`.
 *
 * **El `aria-hidden` lo pone quien los usa**, no el icono. Un «+» al lado de un texto que ya
 * dice «Nuevo cliente», anunciado dos veces, es ruido para quien escucha la pantalla; por eso
 * tampoco llevan `<title>`.
 *
 * El `viewBox` es 24×24 y el color sale de `currentColor`: así el mismo trazo sirve dentro del
 * CTA verde y dentro de un botón fantasma sin una variante por cada tono.
 */

/** El «+» de los tres CTA: «Nuevo cliente», «Nuevo servicio» y «Nueva categoría». */
export function IconoDeMas(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}
