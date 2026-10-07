import {
  ArrowLeft,
  Headset,
  Inbox,
  MessageCircle,
  MessagesSquare,
  Search,
  SendHorizontal,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";

/**
 * Los tres iconos que dibujan las pantallas del agente, transcriptos del prototipo
 * (`docs/aidlc/inputs/prototipos/agente-whatsapp.html`).
 *
 * Son SVG en línea y no una librería de iconos: son tres formas, pesan menos que el `import`
 * que las traería, y no agregan una dependencia para dibujar un globo de chat.
 *
 * **Todos van con `aria-hidden`**, que lo pone quien los usa. Un icono al lado de un texto que
 * dice lo mismo, anunciado dos veces, es ruido para quien escucha la pantalla.
 */

export function IconoDeChat(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.7-1.2A9 9 0 1 0 12 3Z" />
    </svg>
  );
}

/** El destello del prototipo: marca lo que hizo el agente y no una persona. */
export function IconoDeAgente(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3v3m0 12v3M3 12h3m12 0h3" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  );
}

export function IconoDePregunta(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.2 2.4c-.5.2-.7.6-.7 1.1v.5M12 16.5h.01" />
    </svg>
  );
}

/*
 * Iconos de la bandeja y del hilo (rediseño de PAN-WA-01). Vienen de `lucide-react`, como los
 * del resto del panel; el color sale de `currentColor` y el tamaño lo da el CSS del contenedor.
 */

const TRAZO = 2;

export function IconoDeLupa(): JSX.Element {
  return <Search aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeLimpiar(): JSX.Element {
  return <X aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeBandeja(): JSX.Element {
  return <Inbox aria-hidden="true" strokeWidth={1.7} />;
}

export function IconoDeBurbuja(): JSX.Element {
  return <MessageCircle aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeBurbujas(): JSX.Element {
  return <MessagesSquare aria-hidden="true" strokeWidth={1.6} />;
}

/** El destello del agente: marca lo que escribió el sistema y no una persona. */
export function IconoDeDestello(): JSX.Element {
  return <Sparkles aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeOperador(): JSX.Element {
  return <Headset aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeCliente(): JSX.Element {
  return <UserRound aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeVolver(): JSX.Element {
  return <ArrowLeft aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeEnviar(): JSX.Element {
  return <SendHorizontal aria-hidden="true" strokeWidth={TRAZO} />;
}
