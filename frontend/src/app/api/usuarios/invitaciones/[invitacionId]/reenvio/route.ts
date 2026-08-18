/**
 * BFF — resend an invitation (HU-E1-04 RN-04).
 *
 * The new token never comes back through here: the backend hands it straight to the
 * queue that sends the email. The browser gets confirmation, not a credential.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly invitacionId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/usuarios/invitaciones/${params.invitacionId}/reenvio`, "POST", {});
}
