/**
 * @vitest-environment jsdom
 *
 * Las cuatro páginas de la agenda como *páginas* (HU-E7-01 … HU-E7-06).
 *
 * Mismo patrón que las de los épicos 5 y 6: el redirect sin sesión y el mapeo de rol a
 * permisos. Dos cosas propias de este épico se prueban acá y no en los componentes, porque son
 * del servidor:
 *
 * - **Solo Lectura no llega al formulario de alta.** El caso de uso lo rechaza igual, pero
 *   renderizarle el formulario entero para contestarle 403 en «Reservar» le hace perder la
 *   tarde a alguien.
 * - **El nombre del recurso y el del servicio se resuelven del lado del servidor.** Un id en
 *   una pantalla no le dice nada a quien la mira.
 */

import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const leerClaims = vi.fn();
const llamarApi = vi.fn();
const redirect = vi.fn(() => {
  throw new Error("REDIRECT");
});
const notFound = vi.fn(() => {
  throw new Error("NOT_FOUND");
});

vi.mock("@/lib/session", async () => {
  const real = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...real, leerClaims: () => leerClaims() };
});

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");

vi.mock("next/navigation", () => ({
  redirect: () => redirect(),
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn() }),
}));

const PaginaDeAgenda = (await import("@/app/(panel)/agenda/page")).default;
const PaginaDeTurno = (await import("@/app/(panel)/agenda/[turnoId]/page")).default;
const PaginaDeNuevoTurno = (await import("@/app/(panel)/agenda/nuevo/page")).default;
const PaginaDeRecursos = (await import("@/app/(panel)/agenda/recursos/page")).default;

const CLAIMS_ADMIN = { rol: "ADMINISTRADOR", empresa_id: "e-1", usuario_id: "u-1" };
const CLAIMS_OPERADOR = { ...CLAIMS_ADMIN, rol: "OPERADOR" };
const CLAIMS_LECTURA = { ...CLAIMS_ADMIN, rol: "SOLO_LECTURA" };

const SERVICIO = { id: "s1", nombre: "Corte de pelo", duracion_estandar_min: 30 };

const RECURSO = {
  id: "r1",
  nombre: "Consultorio 1",
  tipo: "ESPACIO",
  activo: true,
  patrones: [],
  excepciones: [],
  servicios: [SERVICIO.id],
};

const TURNO = {
  id: "t1",
  cliente_id: "cl1",
  servicio_id: SERVICIO.id,
  recurso_id: RECURSO.id,
  cobro_id: null,
  inicio: "2027-09-07T18:00:00+00:00",
  duracion_min: 60,
  fin: "2027-09-07T19:00:00+00:00",
  estado: "RESERVADO",
  canal_reserva: "PANEL",
  ya_transcurrio: true,
  habilita_facturacion: false,
};

const CLIENTE = {
  id: "cl1",
  nombre: "Ana Prueba",
  cuit: "20-22222222-3",
  condicion_iva: null,
  contacto_whatsapp: "5491100000000",
  contacto_email: "ana.prueba@estudio-ejemplo.test",
  origen: "PANEL",
  activo: true,
};

/** Contesta según la ruta: estas páginas piden dos o tres cosas distintas cada una. */
function porRuta(ruta: string): unknown {
  if (ruta.startsWith("/clientes/")) {
    return CLIENTE;
  }
  if (ruta.startsWith("/clientes")) {
    return { clientes: [CLIENTE], total: 1 };
  }
  if (ruta.startsWith("/turnos/")) {
    return TURNO;
  }
  if (ruta.startsWith("/turnos")) {
    return { turnos: [TURNO] };
  }
  if (ruta === "/recursos/servicios") {
    return [SERVICIO];
  }
  return { recursos: [RECURSO] };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("PaginaDeAgenda", () => {
  it("redirige sin sesion y no le pregunta nada al backend", async () => {
    leerClaims.mockReturnValue(null);
    await expect(PaginaDeAgenda()).rejects.toThrow("REDIRECT");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("le da gestion al Operador y se la niega a Solo Lectura", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    expect(renderToString(await PaginaDeAgenda())).toContain("Nuevo turno");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    expect(renderToString(await PaginaDeAgenda())).not.toContain("Nuevo turno");
  });
});

describe("PaginaDeTurno", () => {
  it("contesta 404 cuando el turno no es de esta empresa", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(422, "No existe", "TurnoInexistente"));

    await expect(PaginaDeTurno({ params: { turnoId: "ajeno" } })).rejects.toThrow("NOT_FOUND");
  });

  it("deja pasar un fallo del backend en vez de disfrazarlo de 404", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockRejectedValue(new ErrorDeApi(500, "Se cayo", "ErrorInterno"));

    await expect(PaginaDeTurno({ params: { turnoId: "t1" } })).rejects.toThrow(ErrorDeApi);
    expect(notFound).not.toHaveBeenCalled();
  });

  it("muestra el nombre del recurso y del servicio, no sus ids", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    const html = renderToString(await PaginaDeTurno({ params: { turnoId: "t1" } }));

    expect(html).toContain("Consultorio 1");
    expect(html).toContain("Corte de pelo");
  });

  // #167: el detalle no decía para quién era el turno.
  it("muestra el cliente del turno con su CUIT y su contacto", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    const html = renderToString(await PaginaDeTurno({ params: { turnoId: "t1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/clientes/cl1");
    expect(html).toContain("Ana Prueba");
    expect(html).toContain("20-22222222-3");
    expect(html).toContain("5491100000000");
    expect(html).toContain("ana.prueba@estudio-ejemplo.test");
  });

  it("sigue en pie si el cliente no se pudo leer, con «—» en sus datos", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) =>
      ruta.startsWith("/clientes/")
        ? Promise.reject(new ErrorDeApi(422, "No existe", "ClienteNoEncontrado"))
        : Promise.resolve(porRuta(ruta)),
    );

    const html = renderToString(await PaginaDeTurno({ params: { turnoId: "t1" } }));

    expect(html).toContain("Consultorio 1");
    expect(html).not.toContain("Ana Prueba");
    expect(html.match(/<dd>—<\/dd>/g)).toHaveLength(4);
  });

  it("le esconde las acciones a Solo Lectura", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const conOperador = renderToString(await PaginaDeTurno({ params: { turnoId: "t1" } }));
    expect(conOperador).toContain("Cancelar turno");

    leerClaims.mockReturnValue(CLAIMS_LECTURA);
    const conLectura = renderToString(await PaginaDeTurno({ params: { turnoId: "t1" } }));
    expect(conLectura).not.toContain("Cancelar turno");
  });
});

describe("PaginaDeNuevoTurno", () => {
  it("saca a Solo Lectura antes de renderizar el formulario", async () => {
    leerClaims.mockReturnValue(CLAIMS_LECTURA);

    await expect(PaginaDeNuevoTurno({ searchParams: { cliente: "cl1" } })).rejects.toThrow(
      "REDIRECT",
    );
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("pide elegir un cliente antes que nada", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);

    const html = renderToString(await PaginaDeNuevoTurno({ searchParams: {} }));

    expect(html).toContain("Elegí primero para quién es el turno");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  // #167: el cliente viajaba solo en la URL; el formulario no decía para quién era el turno.
  it("dice para qué cliente es el turno", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    const html = renderToString(await PaginaDeNuevoTurno({ searchParams: { cliente: "cl1" } }));

    expect(llamarApi).toHaveBeenCalledWith("/clientes/cl1");
    expect(html).toContain("Ana Prueba");
  });

  it("pide solo los recursos activos", async () => {
    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    renderToString(await PaginaDeNuevoTurno({ searchParams: { cliente: "cl1" } }));

    // Ofrecer un recurso desactivado sería ofrecer un camino que termina en 422.
    expect(llamarApi).toHaveBeenCalledWith("/recursos?solo_activos=true");
  });
});

describe("PaginaDeRecursos", () => {
  it("le muestra el listado a todos y el editor solo al Administrador", async () => {
    llamarApi.mockImplementation((ruta: string) => Promise.resolve(porRuta(ruta)));

    leerClaims.mockReturnValue(CLAIMS_ADMIN);
    expect(renderToString(await PaginaDeRecursos())).toContain("Agregar recurso");

    leerClaims.mockReturnValue(CLAIMS_OPERADOR);
    const conOperador = renderToString(await PaginaDeRecursos());
    expect(conOperador).toContain("Consultorio 1");
    expect(conOperador).not.toContain("Agregar recurso");
  });
});
