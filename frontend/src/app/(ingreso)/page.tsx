/**
 * `/` — PAN-ONB-01.
 *
 * The route composes the feature and nothing else. All the behaviour lives in
 * `features/identity`, which is what keeps a screen from turning into the place where
 * business rules accumulate. It reads two things on the server: the legal versions in force
 * (the form sends back the ones it showed) and the `?error=` the BFF leaves when the Google
 * flow ends without a usable account (HU-E1-08 RN-03).
 */

import { FormularioDeIngreso } from "@/features/identity";

import { leerVersionesVigentes } from "@/app/_versiones-legales";

export default async function Ingreso({
  searchParams,
}: {
  readonly searchParams: { readonly error?: string };
}): Promise<JSX.Element> {
  const versiones = await leerVersionesVigentes();
  return <FormularioDeIngreso versiones={versiones} errorInicial={searchParams.error} />;
}
