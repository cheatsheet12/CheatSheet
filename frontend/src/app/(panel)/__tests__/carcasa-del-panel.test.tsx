/**
 * @vitest-environment jsdom
 *
 * La carcasa: cajón móvil, barra reducida con persistencia y menú de cuenta.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ruta = vi.hoisted(() => ({ actual: "/panel" }));
vi.mock("next/navigation", () => ({ usePathname: () => ruta.actual }));

import { CarcasaDelPanel } from "../carcasa-del-panel";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.clear();
});

afterEach(cleanup);

function montar(): ReturnType<typeof render> {
  return render(
    <CarcasaDelPanel
      nombre="Estudio Demo"
      rol="ADMIN"
      renovador={null}
      salida={<button type="button">Cerrar sesión</button>}
    >
      <p>contenido</p>
    </CarcasaDelPanel>,
  );
}

describe("CarcasaDelPanel", () => {
  it("el cajón se abre con la hamburguesa y se cierra con Escape", () => {
    const { container } = montar();
    const app = container.querySelector(".app");
    const abrir = screen.getByRole("button", { name: "Abrir el menú" });

    expect(abrir.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(abrir);
    expect(app?.getAttribute("data-cajon")).toBe("true");
    expect(abrir.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(app?.getAttribute("data-cajon")).toBe("false");
  });

  it("reducir la barra se recuerda en localStorage", () => {
    const { container } = montar();

    fireEvent.click(screen.getByRole("button", { name: "Reducir la barra lateral" }));

    expect(container.querySelector(".app")?.getAttribute("data-colapsada")).toBe("true");
    expect(window.localStorage.getItem("cheatsheet.barra-colapsada")).toBe("1");
  });

  it("arranca reducida si la preferencia guardada lo dice", () => {
    window.localStorage.setItem("cheatsheet.barra-colapsada", "1");
    const { container } = montar();

    expect(container.querySelector(".app")?.getAttribute("data-colapsada")).toBe("true");
  });

  it("funciona aunque localStorage lance", () => {
    const leer = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    const guardar = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    const { container } = montar();

    fireEvent.click(screen.getByRole("button", { name: "Reducir la barra lateral" }));
    expect(container.querySelector(".app")?.getAttribute("data-colapsada")).toBe("true");

    leer.mockRestore();
    guardar.mockRestore();
  });

  it("el menú de cuenta abre y cierra con Escape devolviendo el foco", () => {
    montar();
    const disparador = screen.getByRole("button", { name: "Cuenta de Estudio Demo" });

    expect(disparador.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(disparador);
    expect(disparador.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(disparador.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(disparador);
  });

  it("muestra las migas de la pantalla actual", () => {
    ruta.actual = "/cobros";
    montar();

    expect(screen.getAllByText("Operaciones").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Cobros").length).toBeGreaterThan(0);
  });

  it("los botones de icono muestran el icono y ningún texto suelto", () => {
    // Un ternario fuera de las llaves de JSX compila y se pinta como texto: «colapsada ? (…».
    // TypeScript no lo ve, así que se comprueba lo que llega al DOM.
    montar();

    for (const nombre of ["Reducir la barra lateral", "Abrir el menú", "Cerrar el menú"]) {
      const boton = screen.queryByRole("button", { name: nombre });
      if (boton === null) continue;
      expect(boton.querySelector("svg")).not.toBeNull();
      expect(boton.textContent).toBe("");
    }
  });
});
