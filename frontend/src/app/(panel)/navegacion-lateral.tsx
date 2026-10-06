"use client";

/**
 * La navegación de la barra lateral: el mapa de
 * `docs/aidlc/inputs/prototipos/mapa-navegacion-oficial.html`, en cuatro grupos.
 *
 * **Es un componente de cliente por una sola razón: saber en qué pantalla está la persona.**
 * `usePathname` es lo que permite marcar la entrada activa; el resto —los grupos, los
 * textos, los iconos— es datos. Antes la barra era una lista de enlaces idénticos y quien
 * entraba a una pantalla profunda no tenía forma de ubicarse en el mapa.
 *
 * **Los iconos vienen de `lucide-react`**, que se importa glifo por glifo: el bundle
 * lleva sólo los veintitrés que se usan acá y no la librería. Todos son `aria-hidden`; el
 * texto de al lado dice lo mismo.
 */

import {
  Bell,
  BriefcaseBusiness,
  Boxes,
  Building2,
  CalendarDays,
  ChartColumn,
  ChevronDown,
  CloudUpload,
  History,
  House,
  Layers,
  LayoutTemplate,
  LifeBuoy,
  type LucideIcon,
  MessageCircleMore,
  MessageSquareQuote,
  Package,
  Plug,
  ReceiptText,
  Settings,
  SlidersHorizontal,
  Store,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

type NombreDeIcono =
  | "inicio"
  | "ingesta"
  | "clientes"
  | "servicios"
  | "categorias"
  | "facturacion"
  | "cobros"
  | "agenda"
  | "recursos"
  | "whatsapp"
  | "reportes"
  | "log"
  | "empresa"
  | "usuarios"
  | "integraciones"
  | "puntos"
  | "reglas"
  | "respuestas"
  | "plantillas"
  | "paquete"
  | "notificaciones"
  | "preferencias"
  | "soporte";

interface EntradaDeNavegacion {
  readonly href: string;
  readonly etiqueta: string;
  readonly icono: NombreDeIcono;
}

interface GrupoDeNavegacion {
  readonly titulo: string;
  readonly entradas: readonly EntradaDeNavegacion[];
}

export const NAVEGACION: readonly GrupoDeNavegacion[] = [
  { titulo: "General", entradas: [{ href: "/panel", etiqueta: "Inicio", icono: "inicio" }] },
  {
    titulo: "Operaciones",
    entradas: [
      { href: "/ingesta", etiqueta: "Ingesta de datos", icono: "ingesta" },
      { href: "/datos-maestros/clientes", etiqueta: "Clientes", icono: "clientes" },
      { href: "/datos-maestros/servicios", etiqueta: "Servicios", icono: "servicios" },
      { href: "/datos-maestros/categorias", etiqueta: "Categorías", icono: "categorias" },
      { href: "/facturacion", etiqueta: "Facturación", icono: "facturacion" },
      { href: "/cobros", etiqueta: "Cobros", icono: "cobros" },
      { href: "/agenda", etiqueta: "Agenda", icono: "agenda" },
      { href: "/agenda/recursos", etiqueta: "Recursos", icono: "recursos" },
      { href: "/conversaciones", etiqueta: "Agente WhatsApp", icono: "whatsapp" },
    ],
  },
  {
    titulo: "Análisis",
    entradas: [
      { href: "/reportes", etiqueta: "Reportes", icono: "reportes" },
      { href: "/auditoria", etiqueta: "Log de operaciones", icono: "log" },
    ],
  },
  {
    titulo: "Sistema",
    entradas: [
      { href: "/configuracion/empresa", etiqueta: "Empresa", icono: "empresa" },
      { href: "/configuracion/usuarios", etiqueta: "Usuarios", icono: "usuarios" },
      { href: "/configuracion/integraciones", etiqueta: "Integraciones", icono: "integraciones" },
      { href: "/facturacion/puntos-de-venta", etiqueta: "Puntos de venta", icono: "puntos" },
      { href: "/configuracion/reglas", etiqueta: "Reglas de negocio", icono: "reglas" },
      { href: "/configuracion/respuestas", etiqueta: "Respuestas frecuentes", icono: "respuestas" },
      { href: "/configuracion/plantillas", etiqueta: "Plantillas", icono: "plantillas" },
      {
        href: "/configuracion/paquete-contable",
        etiqueta: "Paquete contable",
        icono: "paquete",
      },
      {
        href: "/configuracion/notificaciones",
        etiqueta: "Notificaciones",
        icono: "notificaciones",
      },
      { href: "/configuracion/preferencias", etiqueta: "Mis preferencias", icono: "preferencias" },
      { href: "/soporte", etiqueta: "Soporte", icono: "soporte" },
    ],
  },
];

/**
 * La entrada que corresponde a una ruta: **la más específica que la contiene**.
 *
 * No alcanza con `startsWith`: `/facturacion/puntos-de-venta` empieza con `/facturacion` y
 * `/agenda/recursos` con `/agenda`, y marcar las dos a la vez es peor que no marcar
 * ninguna. Por eso se compara por segmento (`/agenda` no contiene a `/agendamiento`) y gana
 * el `href` más largo.
 */
export function hrefActivo(ruta: string, hrefs: readonly string[]): string | null {
  let mejor: string | null = null;
  for (const href of hrefs) {
    const contiene = ruta === href || ruta.startsWith(`${href}/`);
    if (contiene && (mejor === null || href.length > mejor.length)) {
      mejor = href;
    }
  }
  return mejor;
}

/** El grupo y la etiqueta de la pantalla donde está la persona, para las migas del encabezado. */
export function ubicacionDe(ruta: string): { grupo: string; etiqueta: string } | null {
  const href = hrefActivo(ruta, HREFS);
  for (const grupo of NAVEGACION) {
    const entrada = grupo.entradas.find((candidata) => candidata.href === href);
    if (entrada !== undefined) return { grupo: grupo.titulo, etiqueta: entrada.etiqueta };
  }
  return null;
}

const HREFS = NAVEGACION.flatMap((grupo) => grupo.entradas.map((entrada) => entrada.href));

const ICONOS: Readonly<Record<NombreDeIcono, LucideIcon>> = {
  inicio: House,
  ingesta: CloudUpload,
  clientes: Users,
  servicios: BriefcaseBusiness,
  categorias: Layers,
  facturacion: ReceiptText,
  cobros: Wallet,
  agenda: CalendarDays,
  recursos: Boxes,
  whatsapp: MessageCircleMore,
  reportes: ChartColumn,
  log: History,
  empresa: Building2,
  usuarios: UserRound,
  integraciones: Plug,
  puntos: Store,
  reglas: SlidersHorizontal,
  respuestas: MessageSquareQuote,
  plantillas: LayoutTemplate,
  paquete: Package,
  notificaciones: Bell,
  preferencias: Settings,
  soporte: LifeBuoy,
};

function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  const Glifo = ICONOS[nombre];
  return <Glifo className="nav__icono" size={18} strokeWidth={1.75} aria-hidden="true" />;
}

/** Los grupos que arrancan cerrados: los de uso ocasional, para que lo diario quepa sin scroll. */
const CERRADOS_AL_INICIO: ReadonlySet<string> = new Set(["Sistema"]);

function Chevron(): JSX.Element {
  return <ChevronDown className="nav__chevron" size={14} strokeWidth={2} aria-hidden="true" />;
}

interface PropiedadesDeNavegacion {
  /** Barra reducida a iconos: las etiquetas pasan a `title` y los grupos se muestran abiertos. */
  readonly colapsada?: boolean;
}

export function NavegacionLateral({ colapsada = false }: PropiedadesDeNavegacion): JSX.Element {
  const activo = hrefActivo(usePathname() ?? "", HREFS);
  const nav = useRef<HTMLElement>(null);
  const contenido = useRef<HTMLDivElement>(null);
  const pildora = useRef<HTMLDivElement>(null);

  const grupoActivo = NAVEGACION.find((grupo) =>
    grupo.entradas.some((entrada) => entrada.href === activo),
  )?.titulo;

  const [cerrados, setCerrados] = useState<ReadonlySet<string>>(CERRADOS_AL_INICIO);
  const [sombra, setSombra] = useState({ arriba: false, abajo: false });

  // Un desvanecido arriba y abajo avisa que hay más entradas fuera de la vista.
  const medir = useCallback((): void => {
    const el = nav.current;
    if (el === null) return;
    const arriba = el.scrollTop > 4;
    const abajo = el.scrollTop + el.clientHeight < el.scrollHeight - 4;
    setSombra((actual) =>
      actual.arriba === arriba && actual.abajo === abajo ? actual : { arriba, abajo },
    );
  }, []);

  // La píldora de la entrada activa se desliza hasta ella: se mide su posición dentro del
  // contenido y se la mueve con `transform`, que es lo único que se anima.
  const ubicarPildora = useCallback((): void => {
    const marca = pildora.current;
    if (marca === null) return;
    const entrada = nav.current?.querySelector<HTMLElement>(".nav__item--activo");
    if (entrada === null || entrada === undefined || entrada.offsetHeight === 0) {
      marca.dataset.visible = "false";
      return;
    }
    // Con rectángulos y no con `offsetTop`: las entradas llevan una animación de entrada con
    // `transform`, y Chrome toma entonces al grupo como referencia del `offsetTop`.
    const base = contenido.current?.getBoundingClientRect();
    if (base === undefined) return;
    const arriba = entrada.getBoundingClientRect().top - base.top;
    marca.style.height = `${entrada.offsetHeight}px`;
    marca.style.width = `${entrada.offsetWidth}px`;
    marca.style.transform = `translateY(${arriba}px)`;
    marca.dataset.visible = "true";
  }, []);

  useEffect(() => {
    medir();
    window.addEventListener("resize", medir);
    let observador: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      observador = new ResizeObserver(() => {
        medir();
        ubicarPildora();
      });
      if (nav.current !== null) observador.observe(nav.current);
      if (contenido.current !== null) observador.observe(contenido.current);
    }
    return () => {
      window.removeEventListener("resize", medir);
      observador?.disconnect();
    };
  }, [medir, ubicarPildora]);

  // Llegar a una pantalla de un grupo cerrado lo abre: la entrada activa tiene que verse,
  // y una barra que marca algo que no se ve es peor que una que no marca nada.
  useEffect(() => {
    if (grupoActivo === undefined) return;
    setCerrados((actuales) => {
      if (!actuales.has(grupoActivo)) return actuales;
      const siguientes = new Set(actuales);
      siguientes.delete(grupoActivo);
      return siguientes;
    });
  }, [grupoActivo]);

  // La barra tiene más entradas que alto: sin esto, quien llega a «Puntos de venta» o
  // «Soporte» ve una barra sin ninguna entrada marcada, porque la activa quedó debajo del
  // borde. `nearest` no mueve nada si ya se ve, así que no salta en cada navegación.
  useEffect(() => {
    nav.current
      ?.querySelector<HTMLElement>(".nav__item--activo")
      ?.scrollIntoView({ block: "nearest" });
  }, [activo, cerrados, colapsada]);

  // Un grupo que recién se abre mide cero hasta que termina de desplegarse: se repite la
  // maniobra cuando acaba la animación, para que la entrada activa quede a la vista.
  useEffect(() => {
    const espera = window.setTimeout(() => {
      nav.current
        ?.querySelector<HTMLElement>(".nav__item--activo")
        ?.scrollIntoView({ block: "nearest" });
      ubicarPildora();
    }, 360);
    return () => window.clearTimeout(espera);
  }, [activo, cerrados, colapsada, ubicarPildora]);

  useEffect(() => {
    ubicarPildora();
  }, [activo, cerrados, colapsada, ubicarPildora]);

  const alternar = (titulo: string): void => {
    setCerrados((actuales) => {
      const siguientes = new Set(actuales);
      if (siguientes.has(titulo)) siguientes.delete(titulo);
      else siguientes.add(titulo);
      return siguientes;
    });
  };

  return (
    <div className="nav__marco" data-sombra-arriba={sombra.arriba} data-sombra-abajo={sombra.abajo}>
      <nav ref={nav} aria-label="Secciones" className="nav" onScroll={medir}>
        <div ref={contenido} className="nav__contenido">
          <div ref={pildora} className="nav__pildora" aria-hidden="true" />
          {NAVEGACION.map((grupo, indice) => {
            const abierto = !cerrados.has(grupo.titulo);
            const idLista = `nav-grupo-${grupo.titulo}`;
            const contieneLaActiva = grupo.titulo === grupoActivo;
            return (
              <div
                key={grupo.titulo}
                className="nav__group"
                style={{ "--i": indice } as CSSProperties}
              >
                <button
                  type="button"
                  className="nav__label"
                  aria-expanded={abierto}
                  aria-controls={idLista}
                  data-contiene-activa={contieneLaActiva}
                  onClick={() => alternar(grupo.titulo)}
                >
                  <span className="nav__titulo">
                    {grupo.titulo}
                    {contieneLaActiva && !abierto ? (
                      <span
                        className="nav__punto"
                        role="img"
                        aria-label="(contiene la pantalla actual)"
                      />
                    ) : null}
                  </span>
                  <Chevron />
                </button>
                <div id={idLista} className="nav__lista" data-abierto={abierto}>
                  <div className="nav__lista-interior">
                    {grupo.entradas.map((entrada, posicion) => {
                      const esActiva = entrada.href === activo;
                      return (
                        <Link
                          key={entrada.href}
                          className={esActiva ? "nav__item nav__item--activo" : "nav__item"}
                          href={entrada.href}
                          title={colapsada ? entrada.etiqueta : undefined}
                          style={{ "--k": posicion } as CSSProperties}
                          aria-current={esActiva ? "page" : undefined}
                        >
                          <Icono nombre={entrada.icono} />
                          <span className="nav__texto">{entrada.etiqueta}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
