/**
 * The panel's home (`/panel`).
 *
 * Empty on purpose: the dashboard KPIs are HU-E10-01, epic 9. What this route proves
 * is that the `(panel)` group's session guard works — reaching it without a cookie
 * redirects.
 */

import { Card } from "@/shared";

export default function PanelHome(): JSX.Element {
  return (
    <Card titulo="Panel">
      <p style={{ color: "var(--color-texto-suave)", margin: 0 }}>
        El tablero de indicadores se construye en el épico de reportería (HU-E10-01).
      </p>
    </Card>
  );
}
