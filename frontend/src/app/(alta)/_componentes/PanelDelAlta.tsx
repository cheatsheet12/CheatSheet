/**
 * La columna izquierda del alta. Es un componente de cliente sólo por una razón: el paso
 * en el que está la persona sale de la ruta (`usePathname`), y un layout del servidor no la
 * conoce. No hay estado ni efectos; todo el movimiento es CSS y se apaga con
 * `prefers-reduced-motion`.
 */

"use client";

import { ArrowRight, Check, FileCheck2, KeyRound, ShieldCheck, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import type { CSSProperties } from "react";

interface PasoDelAlta {
  readonly nombre: string;
  readonly detalle: string;
}

/** Los mismos tres pasos que el stepper del formulario, con la bajada de cada uno. */
const PASOS: readonly PasoDelAlta[] = [
  { nombre: "Cuenta", detalle: "Tu email y una contraseña." },
  { nombre: "Empresa", detalle: "CUIT y condición frente al IVA." },
  { nombre: "Integraciones", detalle: "ARCA, MercadoPago y WhatsApp." },
];

const PASO_EMPRESA = 2;

const PORQUE_EMPRESA = [
  "Con el CUIT validamos tu empresa contra el padrón de ARCA.",
  "La condición frente al IVA define qué comprobantes podés emitir.",
  "Podés corregir todo después, desde Configuración.",
] as const;

interface Beneficio {
  readonly icono: LucideIcon;
  readonly titulo: string;
  readonly detalle: string;
}

const INVITACION: readonly Beneficio[] = [
  { icono: Users, titulo: "Un lugar en el equipo", detalle: "Tu empresa ya te agregó." },
  { icono: KeyRound, titulo: "Tu propia contraseña", detalle: "Sólo vos la conocés." },
  { icono: ShieldCheck, titulo: "Acceso con tu rol", detalle: "Ves lo que te corresponde." },
];

function retardo(indice: number): CSSProperties {
  return { "--i": indice } as CSSProperties;
}

export function PanelDelAlta(): JSX.Element {
  const ruta = usePathname();
  return ruta.startsWith("/invitacion") ? <PanelDeInvitacion /> : <PanelDeOnboarding />;
}

function PanelDeOnboarding(): JSX.Element {
  return (
    <div className="lgn-marca__centro">
      <p className="lgn-marca__etiqueta">Paso {PASO_EMPRESA} de 3</p>
      <h2 className="lgn-marca__titular">
        Casi listo,
        <br />
        <span>contanos de tu empresa.</span>
      </h2>
      <p className="lgn-marca__bajada">
        Pedimos sólo lo esencial para dejar tu cuenta conectada con ARCA.
      </p>

      <ol className="alta-pasos" aria-label="Pasos del alta">
        {PASOS.map((paso, indice) => {
          const numero = indice + 1;
          const estado =
            numero < PASO_EMPRESA ? "hecho" : numero === PASO_EMPRESA ? "actual" : "pendiente";
          return (
            <li
              key={paso.nombre}
              className={`alta-paso alta-paso--${estado}`}
              style={retardo(indice)}
              aria-current={estado === "actual" ? "step" : undefined}
            >
              <span className="alta-paso__marca" aria-hidden="true">
                {estado === "hecho" ? <Check size={16} strokeWidth={2.6} /> : numero}
              </span>
              <span className="alta-paso__texto">
                <strong>{paso.nombre}</strong>
                <small>{paso.detalle}</small>
              </span>
              {estado === "actual" && (
                <ArrowRight className="alta-paso__flecha" size={16} aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ol>

      <div className="alta-nota" style={retardo(PASOS.length)}>
        <p className="alta-nota__titulo">
          <FileCheck2 size={15} aria-hidden="true" /> Para qué te lo pedimos
        </p>
        <ul>
          {PORQUE_EMPRESA.map((texto) => (
            <li key={texto}>{texto}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PanelDeInvitacion(): JSX.Element {
  return (
    <div className="lgn-marca__centro">
      <p className="lgn-marca__etiqueta">Invitación</p>
      <h2 className="lgn-marca__titular">
        Te invitaron
        <br />
        <span>a CheatSheet.</span>
      </h2>
      <p className="lgn-marca__bajada">
        Elegí tu contraseña y entrás al panel de la empresa que te invitó.
      </p>

      <ul className="lgn-lista">
        {INVITACION.map(({ icono: Icono, titulo, detalle }, indice) => (
          <li key={titulo} className="lgn-lista__item" style={retardo(indice)}>
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
  );
}
