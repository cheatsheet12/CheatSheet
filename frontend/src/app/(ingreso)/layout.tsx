/**
 * El ingreso (PAN-ONB-01): la primera pantalla del producto, con maqueta propia de dos
 * columnas. A la izquierda la marca y lo que la plataforma hace; a la derecha el formulario.
 *
 * Vive en su propio grupo de rutas y no en `(public)` porque las demás pantallas sin sesión
 * (onboarding, invitación, acceso del contador) son una columna centrada y no necesitan, ni
 * querrían, un panel de marca al lado. La URL no cambia: los grupos no forman parte de ella.
 *
 * Todo el movimiento de la columna izquierda es CSS puro y se apaga con
 * `prefers-reduced-motion`; no hay estado ni JavaScript de cliente acá.
 */

import {
  CalendarCheck,
  CreditCard,
  FileSpreadsheet,
  MessageCircle,
  ReceiptText,
} from "lucide-react";
import Image from "next/image";
import type { CSSProperties, ReactNode } from "react";

const CAPACIDADES = [
  {
    icono: FileSpreadsheet,
    titulo: "Tus planillas, sincronizadas",
    detalle: "Seguís trabajando en Excel o Google Sheets.",
  },
  {
    icono: ReceiptText,
    titulo: "Facturación con CAE de ARCA",
    detalle: "Comprobantes válidos, sin salir del panel.",
  },
  {
    icono: CreditCard,
    titulo: "Cobros con MercadoPago",
    detalle: "Link de pago y conciliación automática.",
  },
  {
    icono: CalendarCheck,
    titulo: "Agenda y turnos",
    detalle: "Sin superposiciones ni dobles reservas.",
  },
  {
    icono: MessageCircle,
    titulo: "Atención por WhatsApp",
    detalle: "Un agente que reserva y deriva a una persona.",
  },
] as const;

export default function LayoutDeIngreso({
  children,
}: {
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <div className="lgn">
      <aside className="lgn-marca" aria-label="Sobre CheatSheet">
        <div className="lgn-fondo" aria-hidden="true">
          <span className="lgn-fondo__mancha lgn-fondo__mancha--a" />
          <span className="lgn-fondo__mancha lgn-fondo__mancha--b" />
          <span className="lgn-fondo__mancha lgn-fondo__mancha--c" />
          <span className="lgn-fondo__grilla" />
        </div>

        <div className="lgn-marca__logo">
          <Image src="/logo-simbolo.png" alt="" width={44} height={44} priority />
          <span className="lgn-marca__nombre">
            Cheat<em>Sheet</em>
          </span>
        </div>

        <div className="lgn-marca__centro">
          <p className="lgn-marca__etiqueta">Automatización para PyMEs</p>
          <h2 className="lgn-marca__titular">
            Tu negocio,
            <br />
            <span>sin trabajo repetido.</span>
          </h2>
          <p className="lgn-marca__bajada">
            Planillas, facturas, cobros y turnos en un solo lugar, sin cambiar las herramientas que
            ya usás.
          </p>

          <ul className="lgn-lista">
            {CAPACIDADES.map(({ icono: Icono, titulo, detalle }, indice) => (
              <li
                key={titulo}
                className="lgn-lista__item"
                style={{ "--i": indice } as CSSProperties}
              >
                <span className="lgn-lista__icono">
                  <Icono size={18} strokeWidth={2} aria-hidden="true" />
                </span>
                <span>
                  <strong>{titulo}</strong>
                  <small>{detalle}</small>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="lgn-flota" aria-hidden="true">
          <div className="lgn-flota__ficha lgn-flota__ficha--a">
            <span className="lgn-flota__punto" />
            Factura emitida
          </div>
          <div className="lgn-flota__ficha lgn-flota__ficha--b">
            <span className="lgn-flota__punto" />
            Cobro acreditado
          </div>
          <div className="lgn-flota__ficha lgn-flota__ficha--c">
            <span className="lgn-flota__punto" />
            Turno confirmado
          </div>
        </div>

        <p className="lgn-marca__pie">Plataforma de gestión para pequeñas y medianas empresas</p>
      </aside>

      <main className="lgn-form">
        <div className="lgn-form__marca-movil">
          <Image src="/logo-simbolo.png" alt="" width={36} height={36} priority />
          <span className="lgn-form__nombre">
            Cheat<em>Sheet</em>
          </span>
        </div>
        <div className="lgn-form__contenido">{children}</div>
      </main>
    </div>
  );
}
