/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
  document.querySelectorAll("script[data-cargado]").forEach((script) => script.remove());
});

describe("selector de Google", () => {
  it("devuelve el archivo elegido y no crea vínculo al cancelar", async () => {
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_PICKER_CLIENT_ID", "public-client");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_PICKER_API_KEY", "restricted-public-key");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_PICKER_PROJECT_NUMBER", "12345");
    const scripts = ["https://accounts.google.com/gsi/client", "https://apis.google.com/js/api.js"];
    for (const src of scripts) {
      const script = document.createElement("script");
      script.src = src;
      script.dataset.cargado = "true";
      document.head.appendChild(script);
    }
    let onPick: (event: { action: string; docs?: { id: string }[] }) => void = () => undefined;
    let selection: { action: string; docs?: { id: string }[] } = {
      action: "picked",
      docs: [{ id: "sheet-123" }],
    };
    const builder = {
      addView: vi.fn().mockReturnThis(),
      setSelectableMimeTypes: vi.fn().mockReturnThis(),
      setOAuthToken: vi.fn().mockReturnThis(),
      setDeveloperKey: vi.fn().mockReturnThis(),
      setAppId: vi.fn().mockReturnThis(),
      setCallback: vi.fn((callback) => {
        onPick = callback;
        return builder;
      }),
      build: vi.fn(() => ({
        setVisible: () => onPick(selection),
      })),
    };
    vi.stubGlobal("google", {
      accounts: {
        oauth2: {
          initTokenClient: ({
            callback,
          }: {
            callback: (response: { access_token: string }) => void;
          }) => ({
            requestAccessToken: () => callback({ access_token: "short-lived" }),
          }),
        },
      },
      picker: {
        Action: { PICKED: "picked", CANCEL: "cancel" },
        ViewId: { SPREADSHEETS: "spreadsheets" },
        PickerBuilder: vi.fn(() => builder),
      },
    });
    vi.stubGlobal("gapi", { load: (_module: string, callback: () => void) => callback() });

    const { seleccionarPlanillaConGoogle } = await import("../selectorGoogle");
    expect(await seleccionarPlanillaConGoogle()).toBe("sheet-123");
    expect(builder.setOAuthToken).toHaveBeenCalledWith("short-lived");
    expect(builder.setAppId).toHaveBeenCalledWith("12345");
    expect(builder.setSelectableMimeTypes).toHaveBeenCalledWith(
      "application/vnd.google-apps.spreadsheet",
    );
    selection = { action: "cancel" };
    expect(await seleccionarPlanillaConGoogle()).toBeNull();
  });
});
