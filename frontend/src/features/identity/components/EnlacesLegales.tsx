/**
 * The two links every screen that asks for trust must carry: the terms and the privacy
 * policy (HU-E1-03 RN-04, HU-E1-08 RN-06).
 *
 * They open in another tab so that reading a text never costs somebody the form they were
 * filling in. The routes are the stable public ones; the version in force is the page's
 * business, not this link's.
 */

export function EnlacesLegales({ className }: { readonly className?: string }): JSX.Element {
  return (
    <nav
      aria-label="Información legal"
      className={className === undefined ? "acc-legales" : `acc-legales ${className}`}
    >
      <a className="acc-enlace" href="/terminos" target="_blank" rel="noopener noreferrer">
        Términos y Condiciones
      </a>
      <a className="acc-enlace" href="/privacidad" target="_blank" rel="noopener noreferrer">
        Política de Privacidad
      </a>
    </nav>
  );
}
