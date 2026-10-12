/** Pick one spreadsheet under the same OAuth client used by the server-side link. */

type TokenResponse = { access_token?: string; error?: string };
type TokenClient = { requestAccessToken: (options?: { prompt?: string }) => void };
type PickerDocument = { id?: string };
type PickerEvent = { action?: string; docs?: PickerDocument[] };

interface GoogleApis {
  accounts: {
    oauth2: {
      initTokenClient: (options: {
        client_id: string;
        scope: string;
        callback: (response: TokenResponse) => void;
      }) => TokenClient;
    };
  };
  picker: {
    Action: { PICKED: string; CANCEL: string };
    ViewId: { SPREADSHEETS: string };
    PickerBuilder: new () => {
      addView: (view: string) => PickerBuilder;
      setOAuthToken: (token: string) => PickerBuilder;
      setDeveloperKey: (key: string) => PickerBuilder;
      setAppId: (id: string) => PickerBuilder;
      setCallback: (callback: (event: PickerEvent) => void) => PickerBuilder;
      build: () => { setVisible: (visible: boolean) => void };
    };
  };
}

interface PickerBuilder {
  addView(view: string): PickerBuilder;
  setOAuthToken(token: string): PickerBuilder;
  setDeveloperKey(key: string): PickerBuilder;
  setAppId(id: string): PickerBuilder;
  setCallback(callback: (event: PickerEvent) => void): PickerBuilder;
  build(): { setVisible(visible: boolean): void };
}

declare global {
  interface Window {
    google?: GoogleApis;
    gapi?: { load: (module: string, callback: () => void) => void };
  }
}

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_PICKER_CLIENT_ID;
const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_PICKER_API_KEY;
const PROJECT_NUMBER = process.env.NEXT_PUBLIC_GOOGLE_PICKER_PROJECT_NUMBER;

export const selectorGoogleConfigurado = Boolean(CLIENT_ID && API_KEY && PROJECT_NUMBER);

function cargarScript(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existente = document.querySelector<HTMLScriptElement>(`script[src="${url}"]`);
    if (existente?.dataset.cargado === "true") {
      resolve();
      return;
    }
    const script = existente ?? document.createElement("script");
    script.src = url;
    script.async = true;
    script.addEventListener(
      "load",
      () => {
        script.dataset.cargado = "true";
        resolve();
      },
      { once: true },
    );
    script.addEventListener(
      "error",
      () => reject(new Error("No se pudo abrir el selector de Google.")),
      { once: true },
    );
    if (!existente) document.head.appendChild(script);
  });
}

export async function seleccionarPlanillaConGoogle(): Promise<string | null> {
  if (!CLIENT_ID || !API_KEY || !PROJECT_NUMBER) {
    throw new Error("Falta configurar el selector de Google Sheets.");
  }
  await Promise.all([
    cargarScript("https://accounts.google.com/gsi/client"),
    cargarScript("https://apis.google.com/js/api.js"),
  ]);
  const google = window.google;
  const gapi = window.gapi;
  if (!google || !gapi) throw new Error("No se pudo abrir el selector de Google.");
  await new Promise<void>((resolve) => gapi.load("picker", resolve));
  const token = await new Promise<string>((resolve, reject) => {
    google.accounts.oauth2
      .initTokenClient({
        client_id: CLIENT_ID,
        scope: "https://www.googleapis.com/auth/drive.file",
        callback: (response) => {
          if (response.error || !response.access_token)
            reject(new Error("No se autorizó Google Sheets."));
          else resolve(response.access_token);
        },
      })
      .requestAccessToken({ prompt: "" });
  });
  return new Promise<string | null>((resolve) => {
    new google.picker.PickerBuilder()
      .addView(google.picker.ViewId.SPREADSHEETS)
      .setOAuthToken(token)
      .setDeveloperKey(API_KEY)
      .setAppId(PROJECT_NUMBER)
      .setCallback((event) => {
        if (event.action === google.picker.Action.PICKED) resolve(event.docs?.[0]?.id ?? null);
        if (event.action === google.picker.Action.CANCEL) resolve(null);
      })
      .build()
      .setVisible(true);
  });
}
