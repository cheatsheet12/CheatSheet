/**
 * Accepting an invitation — HU-E1-04 RN-02.
 *
 * Public: whoever arrives here has no session, which is the whole point.
 *
 * **The token comes in the URL and stays out of everything else.** `noindex` keeps it out
 * of a search engine, and nothing on this page links anywhere with a referrer that would
 * carry it. It is a credential that happens to travel as a path segment, because a link
 * in an email cannot carry it any other way.
 */

import { FormularioDeAceptacion } from "@/features/identity";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Activá tu cuenta · CheatSheet",
  robots: { index: false, follow: false },
};

export default function PaginaDeInvitacion({
  params,
}: {
  readonly params: { readonly token: string };
}): JSX.Element {
  return <FormularioDeAceptacion token={params.token} />;
}
