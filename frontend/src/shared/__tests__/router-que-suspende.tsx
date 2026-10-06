/**
 * A router whose navigations take time, the way Next 14.2.15's do.
 *
 * A `vi.fn()` as `push` finishes the moment it is called, so any implementation of a
 * "stay pending until the navigation completes" rule passes against it. The real router
 * does not finish: `push`, `replace` and `refresh` dispatch a state update inside
 * `startTransition`, and the router tree then suspends on the server's answer
 * (`use-reducer-with-devtools.js`, `useUnwrapState`) until the RSC payload arrives.
 *
 * This double reproduces that mechanism. Each call sets state on a harness component
 * inside a transition; the harness then renders a child that suspends on a promise the
 * test controls. `resolverNavegacion()` is "the RSC payload arrived".
 */

import { act } from "@testing-library/react";
import { Suspense, startTransition, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { vi } from "vitest";

interface NavegacionEnCurso {
  readonly promesa: Promise<void>;
  readonly resolver: () => void;
  resuelta: boolean;
}

type Despachador = (navegacion: NavegacionEnCurso) => void;

let despachar: Despachador | null = null;
let enCurso: NavegacionEnCurso[] = [];

function iniciarNavegacion(): void {
  let resolver: () => void = () => undefined;
  const promesa = new Promise<void>((resolverPromesa) => {
    resolver = resolverPromesa;
  });
  const navegacion: NavegacionEnCurso = { promesa, resolver, resuelta: false };
  enCurso.push(navegacion);
  // Same shape as Next's `dispatchNavigateAction`: a transition around a state update.
  startTransition(() => despachar?.(navegacion));
}

/** What `useRouter()` returns in a test. Spies, so tests can assert on the calls too. */
export const routerQueSuspende = {
  push: vi.fn((_ruta: string): void => iniciarNavegacion()),
  replace: vi.fn((_ruta: string): void => iniciarNavegacion()),
  refresh: vi.fn((): void => iniciarNavegacion()),
};

/** Renders nothing itself; it only suspends while a navigation is unresolved. */
function Suspensor({
  navegaciones,
}: {
  readonly navegaciones: readonly NavegacionEnCurso[];
}): null {
  const sinResolver = navegaciones.find((navegacion) => !navegacion.resuelta);
  if (sinResolver !== undefined) {
    // React 18 treats a thrown promise as "suspend until it settles".
    throw sinResolver.promesa;
  }
  return null;
}

/**
 * Wrap the component under test in this. It owns the state the fake router writes to, so
 * a navigation suspends the tree and the previous screen stays on display, as in Next.
 */
export function ArnesDeRouter({ children }: { readonly children: ReactNode }): JSX.Element {
  const [navegaciones, setNavegaciones] = useState<readonly NavegacionEnCurso[]>([]);

  useEffect(() => {
    despachar = (navegacion) => setNavegaciones((previas) => [...previas, navegacion]);
    return () => {
      despachar = null;
    };
  }, []);

  return (
    <>
      {children}
      <Suspense fallback={null}>
        <Suspensor navegaciones={navegaciones} />
      </Suspense>
    </>
  );
}

/** "The server answered": every navigation started so far completes and is shown. */
export async function resolverNavegacion(): Promise<void> {
  await act(async () => {
    for (const navegacion of enCurso) {
      navegacion.resuelta = true;
      navegacion.resolver();
    }
    await Promise.resolve();
  });
}

/** Call from `afterEach`: forget the previous test's navigations and calls. */
export function reiniciarRouter(): void {
  enCurso = [];
  despachar = null;
  routerQueSuspende.push.mockClear();
  routerQueSuspende.replace.mockClear();
  routerQueSuspende.refresh.mockClear();
}
