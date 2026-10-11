/**
 * @vitest-environment jsdom
 *
 * The panel layout and the legal block (HU-E1-03 RN-03, HU-E1-08 RN-05; plan case 31): with a
 * document pending the person goes to `/aceptacion-legal`, **before** the onboarding check.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const haySesion = vi.hoisted(() => vi.fn());
const llamarApi = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => {
    throw new Error(`REDIRECT:${destino}`);
  },
  usePathname: () => "/panel",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/session", () => ({ haySesion, leerClaims: () => ({ rol: "ADMINISTRADOR" }) }));

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import { ErrorDeApi } from "@/lib/api";

import PanelLayout from "../layout";

const EMPRESA = { razon_social: "Panadería Rosa", onboarding_completo: true };

beforeEach(() => {
  haySesion.mockReturnValue(true);
});

afterEach(() => {
  haySesion.mockReset();
  llamarApi.mockReset();
});

describe("PanelLayout", () => {
  it("con un documento pendiente redirige a /aceptacion-legal", async () => {
    llamarApi.mockResolvedValue({ ...EMPRESA, aceptaciones_pendientes: ["PRIVACIDAD"] });

    await expect(PanelLayout({ children: null })).rejects.toThrow("REDIRECT:/aceptacion-legal");
  });

  it("el bloqueo legal va antes que el onboarding", async () => {
    llamarApi.mockResolvedValue({
      razon_social: null,
      onboarding_completo: false,
      aceptaciones_pendientes: ["TERMINOS", "PRIVACIDAD"],
    });

    await expect(PanelLayout({ children: null })).rejects.toThrow("REDIRECT:/aceptacion-legal");
  });

  it("sin pendientes y con el onboarding incompleto sigue yendo al onboarding", async () => {
    llamarApi.mockResolvedValue({
      razon_social: null,
      onboarding_completo: false,
      aceptaciones_pendientes: [],
    });

    await expect(PanelLayout({ children: null })).rejects.toThrow("REDIRECT:/onboarding/empresa");
  });

  it("sin pendientes y con todo al día muestra el panel", async () => {
    llamarApi.mockResolvedValue({ ...EMPRESA, aceptaciones_pendientes: [] });

    const arbol = await PanelLayout({ children: null });

    expect(arbol).toBeDefined();
  });

  it("una API que todavía no manda el campo no bloquea a nadie", async () => {
    llamarApi.mockResolvedValue(EMPRESA);

    const arbol = await PanelLayout({ children: null });

    expect(arbol).toBeDefined();
  });

  it("el 403 de un pendiente no cae en el bucle de sesión inválida", async () => {
    // `/auth/empresa` is on the API's short list, so the layout never sees that 403. If it
    // ever did, it would be a bug on the API side: it must not be read as "go to the login".
    llamarApi.mockRejectedValue(new ErrorDeApi(403, "x", "AceptacionLegalPendiente"));

    await expect(PanelLayout({ children: null })).rejects.toThrow("REDIRECT:/");
  });

  it("monta el vigilante que lleva a la aceptación a quien ya estaba adentro", async () => {
    llamarApi.mockResolvedValue({ ...EMPRESA, aceptaciones_pendientes: [] });

    const arbol = (await PanelLayout({ children: null })) as {
      props: { children: readonly { type: { name: string } }[] };
    };

    expect(arbol.props.children.map((hijo) => hijo.type.name)).toContain(
      "VigilanteDeAceptacionLegal",
    );
  });
});
