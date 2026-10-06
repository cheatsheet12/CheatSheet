"use client";

/**
 * La carcasa del panel: barra lateral, encabezado y el hueco donde va cada pantalla.
 *
 * **Es de cliente porque tiene dos estados que sólo existen en el navegador**: si la barra
 * está reducida a iconos (se recuerda en `localStorage`) y si el cajón móvil está abierto.
 * El layout de servidor sigue haciendo lo que le toca —sesión, onboarding, datos de la
 * empresa— y le pasa esto ya resuelto; las pantallas llegan como `children`, así que siguen
 * renderizándose en el servidor.
 *
 * **`localStorage` se lee en un efecto y no en el render**, para que el HTML del servidor y
 * el primer render del cliente coincidan; y cada acceso va en `try/catch` porque puede lanzar
 * en una ventana privada o con los datos del sitio bloqueados. Sin él, la barra queda abierta.
 *
 * **En pantallas angostas la barra es un cajón**: sale por la izquierda con un velo detrás y
 * un botón de hamburguesa en el encabezado. Escape lo cierra y navegar también.
 */

import { ChevronLeft, ChevronRight, Menu, X } from "lucide-react";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { MenuDeUsuario } from "./menu-de-usuario";
import { NavegacionLateral, ubicacionDe } from "./navegacion-lateral";

const CLAVE_DE_COLAPSO = "cheatsheet.barra-colapsada";

interface PropiedadesDeLaCarcasa {
  readonly nombre: string;
  readonly rol: string;
  readonly salida: ReactNode;
  readonly renovador: ReactNode;
  readonly children: ReactNode;
}

/** Las dos iniciales de la empresa, para el avatar. */
function iniciales(nombre: string): string {
  return nombre
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((palabra) => palabra[0])
    .join("")
    .toUpperCase();
}

export function CarcasaDelPanel({
  nombre,
  rol,
  salida,
  renovador,
  children,
}: PropiedadesDeLaCarcasa): JSX.Element {
  const ruta = usePathname() ?? "";
  const [colapsada, setColapsada] = useState(false);
  const [cajonAbierto, setCajonAbierto] = useState(false);
  const [desplazada, setDesplazada] = useState(false);

  // El encabezado gana sombra cuando la página se desplazó: lo separa del contenido.
  useEffect(() => {
    const alDesplazar = (): void => setDesplazada(window.scrollY > 4);
    alDesplazar();
    window.addEventListener("scroll", alDesplazar, { passive: true });
    return () => window.removeEventListener("scroll", alDesplazar);
  }, []);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(CLAVE_DE_COLAPSO) === "1") setColapsada(true);
    } catch {
      // Sin almacenamiento la barra arranca abierta y no se recuerda: no es un error.
    }
  }, []);

  const alternarColapso = (): void => {
    const siguiente = !colapsada;
    setColapsada(siguiente);
    try {
      window.localStorage.setItem(CLAVE_DE_COLAPSO, siguiente ? "1" : "0");
    } catch {
      // Ídem: la preferencia vale para esta visita aunque no se pueda guardar.
    }
  };

  // Navegar cierra el cajón: la persona eligió una pantalla y quiere verla.
  useEffect(() => {
    setCajonAbierto(false);
  }, [ruta]);

  useEffect(() => {
    if (!cajonAbierto) return;
    const alTeclear = (evento: KeyboardEvent): void => {
      if (evento.key === "Escape") setCajonAbierto(false);
    };
    const anterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.body.style.overflow = anterior;
      document.removeEventListener("keydown", alTeclear);
    };
  }, [cajonAbierto]);

  const ubicacion = ubicacionDe(ruta);
  const rolLegible = rol.toLowerCase();

  return (
    <div className="app" data-colapsada={colapsada} data-cajon={cajonAbierto}>
      {renovador}
      <aside id="barra-lateral" className="sidebar" aria-label="Barra lateral">
        <div className="sidebar__brand">
          <Image
            className="sidebar__logo"
            src="/logo-simbolo.png"
            alt=""
            width={44}
            height={44}
            priority
          />
          <span className="sidebar__marca">
            <b className="sidebar__nombre">CheatSheet</b>
            <small className="sidebar__version">iPaaS · panel</small>
          </span>
          <button
            type="button"
            className="sidebar__cerrar"
            aria-label="Cerrar el menú"
            onClick={() => setCajonAbierto(false)}
          >
            <X size={18} strokeWidth={1.9} aria-hidden="true" />
          </button>
        </div>

        <NavegacionLateral colapsada={colapsada} />

        <div className="sidebar__pie">
          <div className="sidebar__empresa" title={colapsada ? nombre : undefined}>
            <span className="sidebar__avatar" aria-hidden="true">
              {iniciales(nombre)}
            </span>
            <span className="sidebar__empresa-datos">
              <b>{nombre}</b>
              <small>{rolLegible}</small>
            </span>
          </div>
          <button
            type="button"
            className="sidebar__colapsar"
            aria-pressed={colapsada}
            aria-label={colapsada ? "Expandir la barra lateral" : "Reducir la barra lateral"}
            title={colapsada ? "Expandir la barra lateral" : "Reducir la barra lateral"}
            onClick={alternarColapso}
          >
            {colapsada ? (
              <ChevronRight size={18} strokeWidth={1.9} aria-hidden="true" />
            ) : (
              <ChevronLeft size={18} strokeWidth={1.9} aria-hidden="true" />
            )}
          </button>
        </div>
      </aside>

      {cajonAbierto ? (
        <button
          type="button"
          className="sidebar__velo"
          aria-label="Cerrar el menú"
          tabIndex={-1}
          onClick={() => setCajonAbierto(false)}
        />
      ) : null}

      <div className="app__main">
        <header className="topbar" data-desplazada={desplazada}>
          <button
            type="button"
            className="topbar__menu"
            aria-label="Abrir el menú"
            aria-expanded={cajonAbierto}
            aria-controls="barra-lateral"
            onClick={() => setCajonAbierto(true)}
          >
            <Menu size={18} strokeWidth={1.9} aria-hidden="true" />
          </button>
          {ubicacion === null ? null : (
            <p className="topbar__migas">
              <span>{ubicacion.grupo}</span>
              <span className="topbar__separador" aria-hidden="true">
                /
              </span>
              <b>{ubicacion.etiqueta}</b>
            </p>
          )}
          <div className="topbar__right">
            <MenuDeUsuario
              nombre={nombre}
              rol={rolLegible}
              iniciales={iniciales(nombre)}
              salida={salida}
            />
          </div>
        </header>
        <main className="page">{children}</main>
      </div>
    </div>
  );
}
