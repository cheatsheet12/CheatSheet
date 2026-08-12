/**
 * Everything reachable without a session: onboarding (PAN-ONB-01/02, next unit) and
 * the accountant's token-gated download (HU-E10-06, epic 9).
 *
 * Centred single column, no navigation. There is nowhere to navigate to yet — the
 * user is either creating an account or following a link.
 */

import type { ReactNode } from "react";

export default function PublicLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <main
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        padding: "var(--espacio-6)",
      }}
    >
      <div style={{ width: "100%", maxWidth: "26rem" }}>{children}</div>
    </main>
  );
}
