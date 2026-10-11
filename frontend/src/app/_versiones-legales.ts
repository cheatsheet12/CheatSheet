/**
 * The versions of the legal texts in force, read on the server for the screens that ask for
 * consent (HU-E1-08 RN-03/04): sign-up and accepting an invitation.
 *
 * **Never throws.** These pages are the way in, and a legal endpoint that is briefly down
 * must not take the sign-in form with it. `null` means "could not read them": the form still
 * lets an existing user sign in and refuses to create an account, saying why. Revalidated
 * every minute so a version that takes effect today is picked up quickly, while Next keeps
 * serving the last good copy if the backend is unreachable.
 */

import type { VersionesVigentes } from "@/features/identity";
import { llamarApi } from "@/lib/api";

const REVALIDAR_CADA_SEGUNDOS = 60;

export async function leerVersionesVigentes(): Promise<VersionesVigentes | null> {
  try {
    return await llamarApi<VersionesVigentes>("/legal/vigentes", {
      revalidarCadaSegundos: REVALIDAR_CADA_SEGUNDOS,
    });
  } catch {
    return null;
  }
}
