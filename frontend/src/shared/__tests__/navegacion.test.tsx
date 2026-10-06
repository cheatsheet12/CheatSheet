/**
 * @vitest-environment jsdom
 *
 * The contract of `useAccionConNavegacion`, which eight screens rely on: the pending state
 * lasts from the click until the destination is displayed, not until the request answers.
 *
 * The router is the one in `router-que-suspende.tsx`, whose navigations take time. With a
 * plain `vi.fn()` every one of these would pass for the wrong reason.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

const { useAccionConNavegacion } = await import("@/shared/navegacion");
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);

type Ejecutar = ReturnType<typeof useAccionConNavegacion>["ejecutar"];

interface Sonda {
  ejecutar: Ejecutar;
  /** The value of `pendiente` on every committed render, in order. */
  readonly renders: boolean[];
}

function montar(): { sonda: Sonda; desmontar: () => void } {
  const sonda: Sonda = { ejecutar: async () => undefined, renders: [] };
  function Componente(): JSX.Element {
    const { pendiente, ejecutar } = useAccionConNavegacion();
    sonda.ejecutar = ejecutar;
    // Recorded in an effect, i.e. once per *committed* render: a render React starts and
    // then abandons because the transition suspends is not something the user ever sees.
    useEffect(() => {
      sonda.renders.push(pendiente);
    });
    return <p data-testid="estado">{pendiente ? "pendiente" : "libre"}</p>;
  }
  const { unmount } = render(
    <ArnesDeRouter>
      <Componente />
    </ArnesDeRouter>,
  );
  return { sonda, desmontar: unmount };
}

function estado(): string {
  return screen.getByTestId("estado").textContent ?? "";
}

/** A promise the test settles by hand, standing for the mutation's HTTP request. */
function diferida<T>(): { promesa: Promise<T>; resolver: (valor: T) => void } {
  let resolver: (valor: T) => void = () => undefined;
  const promesa = new Promise<T>((resolverPromesa) => {
    resolver = resolverPromesa;
  });
  return { promesa, resolver };
}

afterEach(() => {
  cleanup();
  reiniciarRouter();
});

describe("useAccionConNavegacion", () => {
  it("queda pendiente hasta que la navegación termina, aunque la acción ya respondió", async () => {
    const { sonda } = montar();

    await act(async () => {
      await sonda.ejecutar(
        async () => "/panel",
        (destino, router) => router.push(destino),
      );
    });

    expect(routerQueSuspende.push).toHaveBeenCalledWith("/panel");
    expect(estado()).toBe("pendiente");

    await resolverNavegacion();
    expect(estado()).toBe("libre");
  });

  it("si la acción rechaza, se libera, relanza el error y no navega", async () => {
    const { sonda } = montar();
    const navegar = vi.fn();
    const fallo = new Error("rechazada");

    let capturado: unknown;
    await act(async () => {
      capturado = await sonda
        .ejecutar(async () => Promise.reject(fallo), navegar)
        .then(() => undefined)
        .catch((error: unknown) => error);
    });

    expect(capturado).toBe(fallo);
    expect(navegar).not.toHaveBeenCalled();
    expect(estado()).toBe("libre");
  });

  it("una segunda llamada mientras está pendiente, incluso en el mismo tick, no invoca la acción", async () => {
    const { sonda } = montar();
    const respuesta = diferida<string>();
    const accion = vi.fn(() => respuesta.promesa);
    const navegar = vi.fn((destino: string, router: { push: (ruta: string) => void }) =>
      router.push(destino),
    );

    await act(async () => {
      const primera = sonda.ejecutar(accion, navegar);
      const segunda = sonda.ejecutar(accion, navegar);
      respuesta.resolver("/panel");
      await Promise.all([primera, segunda]);
    });
    expect(accion).toHaveBeenCalledTimes(1);

    // And again once the first has resolved but its navigation is still going.
    await act(async () => {
      await sonda.ejecutar(accion, navegar);
    });
    expect(accion).toHaveBeenCalledTimes(1);
  });

  it("se puede volver a ejecutar cuando la anterior terminó con error", async () => {
    const { sonda } = montar();
    const accion = vi.fn(async () => Promise.reject(new Error("falló")));

    await act(async () => {
      await sonda.ejecutar(accion, vi.fn()).catch(() => undefined);
    });
    await act(async () => {
      await sonda.ejecutar(accion, vi.fn()).catch(() => undefined);
    });

    expect(accion).toHaveBeenCalledTimes(2);
  });

  it("desmontado antes de que la acción responda, no navega", async () => {
    const { sonda, desmontar } = montar();
    const respuesta = diferida<string>();
    const navegar = vi.fn();

    let ejecucion: Promise<void> = Promise.resolve();
    await act(async () => {
      ejecucion = sonda.ejecutar(() => respuesta.promesa, navegar);
    });
    desmontar();
    await act(async () => {
      respuesta.resolver("/panel");
      await ejecucion;
    });

    expect(navegar).not.toHaveBeenCalled();
    expect(routerQueSuspende.push).not.toHaveBeenCalled();
  });

  it("un refresh() sobre la misma página mantiene el pendiente hasta que resuelve", async () => {
    const { sonda } = montar();

    await act(async () => {
      await sonda.ejecutar(
        async () => undefined,
        (_resultado, router) => router.refresh(),
      );
    });

    expect(routerQueSuspende.refresh).toHaveBeenCalledTimes(1);
    expect(estado()).toBe("pendiente");

    await resolverNavegacion();
    expect(estado()).toBe("libre");
  });

  it("no hay ningún render con pendiente en false entre el fin de la acción y el inicio de la transición", async () => {
    const { sonda } = montar();
    const respuesta = diferida<string>();

    let ejecucion: Promise<void> = Promise.resolve();
    await act(async () => {
      ejecucion = sonda.ejecutar(
        () => respuesta.promesa,
        (destino, router) => router.push(destino),
      );
    });
    const rendersAlEsperar = sonda.renders.length;
    expect(sonda.renders[rendersAlEsperar - 1]).toBe(true);

    await act(async () => {
      respuesta.resolver("/panel");
      await ejecucion;
    });
    const rendersAntesDeLlegar = sonda.renders.length;
    await resolverNavegacion();

    // From the click until the destination is displayed, every render is pending.
    const durante = sonda.renders.slice(sonda.renders.indexOf(true), rendersAntesDeLlegar);
    expect(durante.length).toBeGreaterThan(1);
    expect(durante.every((pendiente) => pendiente)).toBe(true);
    expect(sonda.renders[sonda.renders.length - 1]).toBe(false);
  });

  it("con saleDeLaPagina el pendiente no se libera tras navegar: la página se va", async () => {
    const { sonda } = montar();
    const navegar = vi.fn();

    await act(async () => {
      await sonda.ejecutar(async () => "https://destino.example", navegar, {
        saleDeLaPagina: true,
      });
    });

    expect(navegar).toHaveBeenCalledTimes(1);
    expect(estado()).toBe("pendiente");
  });

  it("con saleDeLaPagina, volver con «atrás» desde la caché del navegador libera el botón", async () => {
    const { sonda } = montar();
    const accion = vi.fn(async () => "https://destino.example");

    await act(async () => {
      await sonda.ejecutar(accion, vi.fn(), { saleDeLaPagina: true });
    });
    expect(estado()).toBe("pendiente");

    // The browser restores the page from its back/forward cache: same React state, but the
    // person is back on this screen and the page they went to is gone.
    act(() => {
      const evento = new Event("pageshow");
      Object.defineProperty(evento, "persisted", { value: true });
      window.dispatchEvent(evento);
    });
    expect(estado()).toBe("libre");

    await act(async () => {
      await sonda.ejecutar(accion, vi.fn(), { saleDeLaPagina: true });
    });
    expect(accion).toHaveBeenCalledTimes(2);
  });
});
