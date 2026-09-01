/**
 * @vitest-environment jsdom
 *
 * Las tres pantallas de Datos Maestros, como *páginas*.
 *
 * **Es el primer test de un `page.tsx` del proyecto**, y no se escribió por cobertura: las
 * páginas tienen lógica propia y hasta ahora nadie la miraba. Concretamente dos cosas, y
 * las dos importan:
 *
 * - **el redirect sin sesión.** El layout ya lo hace, pero cada página lo repite y una que
 *   se olvidara de repetirlo no fallaría en ninguna prueba;
 * - **el mapeo de rol a `puedeEditar`.** `SOLO_LECTURA` tiene que llegar al componente con
 *   `false`. Que el backend igual rechace no lo hace irrelevante: el panel no debe ofrecer
 *   una acción que va a ser rechazada, y ese es exactamente el criterio de la matriz de
 *   acceso del mapa de navegación §5.
 *
 * Se llama a la página como la función asincrónica que es y se renderiza lo que devuelve.
 */

import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();
const redirect = vi.fn(() => {
  // El `redirect` de Next corta la ejecución lanzando; el doble hace lo mismo para que
  // la página no siga como si hubiera sesión.
  throw new Error("REDIRECT");
});

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

vi.mock("next/navigation", () => ({ redirect: () => redirect() }));

const PaginaDeClientes = (await import("@/app/(panel)/datos-maestros/clientes/page")).default;
const PaginaDeServicios = (await import("@/app/(panel)/datos-maestros/servicios/page")).default;
const PaginaDeCategorias = (await import("@/app/(panel)/datos-maestros/categorias/page")).default;

const CLAIMS_OPERADOR = { rol: "OPERADOR", empresa_id: "e-1", usuario_id: "u-1" };
const CLAIMS_SOLO_LECTURA = { ...CLAIMS_OPERADOR, rol: "SOLO_LECTURA" };

const paginas = [
  {
    nombre: "clientes",
    pagina: PaginaDeClientes,
    respuesta: { clientes: [], total: 0 },
    ruta: "/clientes",
    titulo: "Clientes",
    boton: "Nuevo cliente",
  },
  {
    nombre: "servicios",
    pagina: PaginaDeServicios,
    respuesta: { servicios: [], total: 0 },
    ruta: "/servicios",
    titulo: "Servicios",
    boton: "Nuevo servicio",
  },
  {
    nombre: "categorias",
    pagina: PaginaDeCategorias,
    respuesta: { categorias: [] },
    ruta: "/categorias",
    titulo: "Categorias",
    boton: "Nueva categoria",
  },
];

afterEach(() => {
  vi.clearAllMocks();
});

describe.each(paginas)("$nombre", ({ pagina, respuesta, ruta, titulo, boton }) => {
  it("sin sesion redirige y no llama a la API", async () => {
    leerClaims.mockReturnValue(null);

    await expect(pagina()).rejects.toThrow("REDIRECT");
    expect(redirect).toHaveBeenCalled();
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("pide su listado a la API y lo renderiza", async () => {
    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    llamarApi.mockResolvedValue(respuesta);

    const html = renderToString(await pagina());

    expect(llamarApi).toHaveBeenCalledWith(ruta);
    expect(html).toContain(titulo);
  });

  it("un Operador ve las acciones de escritura", async () => {
    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    llamarApi.mockResolvedValue(respuesta);

    const html = renderToString(await pagina());

    expect(html).toContain(boton);
  });

  it("un Solo Lectura no las ve", async () => {
    leerClaims.mockReturnValue(CLAIMS_SOLO_LECTURA);
    llamarApi.mockResolvedValue(respuesta);

    const html = renderToString(await pagina());

    expect(html).not.toContain(boton);
  });
});
