/**
 * The notice on the accountant's page (HU-E1-08 RN-08).
 *
 * The accountant reaches the system through a link, is not a `Usuario`, and so accepts
 * nothing and nothing is recorded: this only tells them how the data they are looking at is
 * treated and where to read it. No checkbox, no button, on purpose.
 */

export function AvisoDePrivacidad(): JSX.Element {
  return (
    <p className="legal__aviso">
      Los datos de este paquete se tratan según la{" "}
      <a className="acc-enlace" href="/privacidad" target="_blank" rel="noopener noreferrer">
        Política de Privacidad
      </a>{" "}
      de CheatSheet.
    </p>
  );
}
