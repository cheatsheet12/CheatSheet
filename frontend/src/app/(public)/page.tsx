/**
 * `/` — PAN-ONB-01.
 *
 * The route composes the feature and nothing else. All the behaviour lives in
 * `features/identity`, which is what keeps a screen from turning into the place where
 * business rules accumulate.
 */

import { FormularioDeIngreso } from "@/features/identity";

export default function Ingreso(): JSX.Element {
  return <FormularioDeIngreso />;
}
