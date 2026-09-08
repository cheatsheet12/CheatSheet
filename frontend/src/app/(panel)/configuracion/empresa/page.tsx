/**
 * Configuración → Empresa. The same PAN-ONB-02 form, in the one place it can validate.
 *
 * There is no separate screen code for this in the navigation map, and inventing one
 * would be inventing a design. What the unit map asked for is «la edición de datos de la
 * empresa», and the honest way to build it is the screen that already edits them —
 * without the stepper, which belongs to a sequence this one is not part of.
 *
 * It has to exist because of where the padrón lookup lives: at step 2 of the onboarding
 * there is no fiscal certificate yet, so «Validar contra ARCA» can only work from inside
 * the panel, after Configuración → Integraciones.
 */

import { FormularioDeEmpresa } from "@/features/identity";
import type { EmpresaActual } from "@/features/identity";
import { llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Datos de la empresa · CheatSheet" };

export default async function PaginaDeEmpresa(): Promise<JSX.Element> {
  const actuales = await llamarApi<EmpresaActual>("/auth/empresa");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Configuración</span>
          <h1>Datos de la empresa</h1>
          <p className="dm-intro">
            Los datos fiscales con los que se emite cada comprobante. Desde acá se los valida contra
            el padrón de ARCA, que es la única pantalla que puede hacerlo.
          </p>
        </div>
      </header>
      <FormularioDeEmpresa modo="edicion" iniciales={actuales} />
    </>
  );
}
