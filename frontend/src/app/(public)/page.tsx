/**
 * Landing route (`/`).
 *
 * A placeholder, and it says so rather than pretending: PAN-ONB-01 is built by the
 * `identidad-y-onboarding` unit. What it does prove is that the shell holds together
 * — root layout, route group, design tokens and the shared components.
 */

import { Alert, Card } from "@/shared";

export default function Landing(): JSX.Element {
  return (
    <Card titulo="CheatSheet">
      <Alert tono="info" titulo="Cimientos en pie">
        La plataforma está montada: API, base de datos con aislamiento por empresa, bitácora de
        operaciones y cola de tareas. El registro y el inicio de sesión (PAN-ONB-01) llegan con la
        unidad de identidad.
      </Alert>
    </Card>
  );
}
