/**
 * PAN-DSH-01 — el inicio del panel.
 *
 * **No tiene endpoint propio, y no se le inventó uno.** Lo que muestra ya existe repartido en
 * dos lecturas que otras pantallas usan: `GET /reporteria/tablero` (HU-E10-01) trae las cuatro
 * métricas con su variación, lo pendiente y lo en mora; `GET /bitacora` (HU-E12-01) trae las
 * últimas operaciones. Un tercer endpoint que devolviera lo mismo sería una segunda definición
 * de «facturado» esperando a discrepar con la primera.
 *
 * **Los importes son texto de punta a punta.** Llegan como string porque un número JSON es un
 * float y un float se equivoca en el cuarto decimal, que es donde vive el centavo. Acá se
 * formatean con `formatearNumero` y nunca se convierten: nada se calcula en esta pantalla.
 *
 * **La bitácora puede negarse, y eso no es una falla.** El rol Solo Lectura recibe un 422 con
 * el motivo (HU-E12-01 RN-05). La sección se dibuja igual, con la explicación en lugar de la
 * tabla: una pantalla que se cae entera porque una de sus seis secciones no le corresponde al
 * usuario es peor que una sección que dice por qué está vacía.
 *
 * **Las métricas son «del período» y no «de hoy».** El prototipo dice «Turnos del día» porque
 * dibuja un día; el tablero real devuelve un rango. Etiquetarlo «hoy» sería poner un cartel
 * encima de un número que cuenta otra cosa.
 */

import { ArrowRight, Bot, UserRound } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { MENSAJE_SIN_ACTIVIDAD, ResumenDeCobros, textoDePeriodo } from "@/features/reporting";
import type { Metrica, TableroRespuesta } from "@/features/reporting";
import { ETIQUETAS_DE_MODULO, ETIQUETAS_DE_RESULTADO } from "@/features/observability";
import type { ListadoDeOperaciones, Operacion } from "@/features/observability";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";
import { Badge, Card, Tabla, formatearFecha, formatearFechaHora, formatearNumero } from "@/shared";
import type { Columna } from "@/shared";

import { Icono } from "./iconos";
import type { NombreDeIcono } from "./iconos";
import { SelectorDePeriodoEnUrl } from "./SelectorDePeriodoEnUrl";

export const dynamic = "force-dynamic";

export const metadata = { title: "Inicio · CheatSheet" };

/** Cuántas operaciones entran en «Actividad reciente» sin convertirla en el log completo. */
const OPERACIONES_VISIBLES = 5;

interface Actividad {
  readonly listado: ListadoDeOperaciones;
  /** La frase del backend cuando el rol no accede a la bitácora. Ver el docstring. */
  readonly motivo?: string;
}

export interface PropsDeInicio {
  /** El período vive en la URL (`/panel?desde=…&hasta=…`); sin él, el backend usa el mes en curso. */
  readonly searchParams?: Readonly<Record<string, string | string[] | undefined>>;
}

/** La ruta del tablero con el período de la URL, la misma que usa Reportes. */
function rutaDelTablero(searchParams: PropsDeInicio["searchParams"]): string {
  const consulta = new URLSearchParams();
  for (const clave of ["desde", "hasta"]) {
    const valor = searchParams?.[clave];
    if (typeof valor === "string" && valor !== "") {
      consulta.set(clave, valor);
    }
  }
  const texto = consulta.toString();
  return texto === "" ? "/reporteria/tablero" : `/reporteria/tablero?${texto}`;
}

export default async function PanelHome({
  searchParams,
}: PropsDeInicio = {}): Promise<JSX.Element> {
  if (leerClaims() === null) {
    redirect("/");
  }

  // Las dos lecturas van en paralelo: son independientes y la pantalla necesita las dos para
  // su primer pintado. `leerActividad` atrapa su propio rechazo, así que un 422 de bitácora no
  // arrastra al tablero.
  const [tablero, actividad] = await Promise.all([
    llamarApi<TableroRespuesta>(rutaDelTablero(searchParams)),
    leerActividad(),
  ]);

  return (
    <>
      <div className="dsh-encabezado">
        <div>
          <p className="dsh-eyebrow">
            Período {formatearFecha(tablero.desde)} – {formatearFecha(tablero.hasta)}
          </p>
          <h1 className="dsh-titulo">Resumen de tu negocio</h1>
          <p className="dsh-subtitulo">
            Los números del período y lo último que el sistema ejecutó en nombre de tu empresa.
          </p>
        </div>
        <div className="dsh-encabezado__acciones">
          <Link className="dsh-enlace" href="/reportes">
            <Icono nombre="barras" />
            Ver reportes
          </Link>
          <Link className="dsh-enlace-cta" href="/ingesta">
            <Icono nombre="mas" />
            Nueva carga de planilla
          </Link>
        </div>
      </div>

      <SelectorDePeriodoEnUrl
        desde={tablero.desde}
        hasta={tablero.hasta}
        resumen={textoDePeriodo(tablero.desde, tablero.hasta)}
      />

      {tablero.sin_actividad && (
        <div className="dsh-aviso" role="status">
          <span className="dsh-aviso__ico" aria-hidden="true">
            <Icono nombre="barras" />
          </span>
          <div>
            <p className="dsh-aviso__titulo">Sin actividad</p>
            <p className="dsh-aviso__texto">{MENSAJE_SIN_ACTIVIDAD}</p>
          </div>
        </div>
      )}

      <div className="dsh-stats dsh-stats--tres">
        <TarjetaDeMetrica
          icono="documento"
          tono="menta"
          etiqueta="Facturación emitida"
          valor={`$ ${formatearNumero(tablero.facturado.valor)}`}
          variacion={tablero.facturado.variacion}
          pie={`Período anterior · $ ${formatearNumero(tablero.facturado.anterior)}`}
        />
        <TarjetaDeMetrica
          icono="calendario"
          tono="tinta"
          etiqueta="Turnos del período"
          valor={cantidad(tablero.turnos)}
          variacion={tablero.turnos.variacion}
          pie={`Período anterior · ${formatearNumero(tablero.turnos.anterior, undefined, 0)}`}
        />
        <TarjetaDeMetrica
          icono="actividad"
          tono="ambar"
          etiqueta="Operaciones registradas"
          valor={cantidad(tablero.operaciones)}
          variacion={tablero.operaciones.variacion}
          pie={`Período anterior · ${formatearNumero(tablero.operaciones.anterior, undefined, 0)}`}
        />
      </div>

      <ResumenDeCobros
        cobrado={tablero.cobrado}
        pendiente={tablero.pendiente}
        enMora={tablero.en_mora}
        tasaDeCobro={tablero.tasa_de_cobro}
      />

      <div className="dsh-grid">
        <Card>
          <div className="dsh-seccion">
            <div>
              <h2 className="dsh-seccion__titulo">Actividad reciente</h2>
              <p className="dsh-seccion__sub">
                {actividad.motivo === undefined
                  ? `Últimas operaciones del sistema · ${actividad.listado.total} en total`
                  : "Últimas operaciones del sistema"}
              </p>
            </div>
            <Link className="dsh-seccion__enlace" href="/auditoria">
              Ver log completo
              <ArrowRight size={14} strokeWidth={2.2} aria-hidden="true" />
            </Link>
          </div>
          {actividad.motivo === undefined ? (
            <Tabla
              titulo="Actividad reciente"
              columnas={COLUMNAS_DE_ACTIVIDAD}
              filas={actividad.listado.operaciones.slice(0, OPERACIONES_VISIBLES)}
              claveDeFila={(operacion) => operacion.id}
              vacia="Todavía no hay operaciones registradas."
            />
          ) : (
            <p className="dsh-vacio">{actividad.motivo}</p>
          )}
        </Card>

        <Card>
          <div className="dsh-seccion">
            <div>
              <h2 className="dsh-seccion__titulo">Accesos directos</h2>
              <p className="dsh-seccion__sub">Tus módulos más usados</p>
            </div>
          </div>
          <div className="dsh-accesos">
            {ACCESOS.map((acceso, indice) => (
              <Link key={acceso.href} className="dsh-acceso" href={acceso.href}>
                <span className={`dsh-acceso__ico dsh-acceso__ico--${TONOS_DE_ACCESO[indice % 3]}`}>
                  <Icono nombre={acceso.icono} />
                </span>
                <span className="dsh-acceso__texto">
                  <b className="dsh-acceso__nombre">{acceso.nombre}</b>
                  <span className="dsh-acceso__sub">{acceso.detalle}</span>
                </span>
                <ArrowRight
                  className="dsh-acceso__flecha"
                  size={16}
                  strokeWidth={2}
                  aria-hidden="true"
                />
              </Link>
            ))}
          </div>
        </Card>
      </div>

      <p className="dsh-nota">
        CheatSheet iPaaS · Datos del {formatearFecha(tablero.desde)} al{" "}
        {formatearFecha(tablero.hasta)}
      </p>
    </>
  );
}

/**
 * La bitácora, con su negativa convertida en un valor.
 *
 * Un 4xx acá es una regla de negocio contándose (el rol no accede), no una avería; un 5xx sí
 * es una avería y sube, porque un tablero que disimula que el backend se cayó es un tablero
 * que miente.
 */
async function leerActividad(): Promise<Actividad> {
  try {
    return { listado: await llamarApi<ListadoDeOperaciones>("/bitacora") };
  } catch (error) {
    if (!(error instanceof ErrorDeApi) || error.status >= 500) {
      throw error;
    }
    return { listado: { operaciones: [], total: 0 }, motivo: error.detalle };
  }
}

/** Un conteo, no un importe: sin decimales, pero con separador de miles. */
function cantidad(metrica: Metrica): string {
  return formatearNumero(metrica.valor, undefined, 0);
}

function TarjetaDeMetrica({
  icono,
  tono,
  etiqueta,
  valor,
  variacion,
  pie,
}: {
  readonly icono: NombreDeIcono;
  readonly tono: "menta" | "ambar" | "tinta";
  readonly etiqueta: string;
  readonly valor: string;
  readonly variacion: string | null;
  readonly pie: string;
}): JSX.Element {
  return (
    <div className="dsh-stat">
      <div className="dsh-stat__top">
        <span className={`dsh-stat__ico dsh-stat__ico--${tono}`}>
          <Icono nombre={icono} />
        </span>
        <span className="dsh-stat__tag" data-sentido={sentidoDeVariacion(variacion)}>
          {textoDeVariacion(variacion)}
        </span>
      </div>
      <p className="dsh-stat__label">{etiqueta}</p>
      <p className="dsh-stat__valor">{valor}</p>
      <p className="dsh-stat__pie">{pie}</p>
    </div>
  );
}

/**
 * Un guion no es un cero.
 *
 * Cuando no hay período anterior la variación llega en `null`; mostrar «0%» le diría a alguien
 * que su negocio no creció, cuando la verdad es que no hay con qué comparar.
 */
function textoDeVariacion(variacion: string | null): string {
  if (variacion === null) {
    return "—";
  }
  return Number(variacion) >= 0 ? `↗ +${variacion}%` : `↘ ${variacion}%`;
}

/** Hacia dónde fue la cifra, para pintar la etiqueta: sin período anterior no hay sentido. */
function sentidoDeVariacion(variacion: string | null): "sube" | "baja" | "neutro" {
  if (variacion === null) {
    return "neutro";
  }
  return Number(variacion) >= 0 ? "sube" : "baja";
}

/** Los tonos de los azulejos de los accesos, en rotación: seis tarjetas del mismo verde son una pared. */
const TONOS_DE_ACCESO = ["menta", "tinta", "ambar"] as const;

/** Qué dibujo lleva cada módulo en la tabla de actividad. Lo que no se conoce usa el genérico. */
const ICONO_DE_MODULO: Readonly<Record<string, NombreDeIcono>> = {
  billing: "documento",
  payments: "tarjeta",
  scheduling: "calendario",
  spreadsheet_sync: "subir",
  reporting: "barras",
};

/** `autorizar_comprobante` → «Autorizar comprobante»: el identificador técnico no es un título. */
function nombreDeAccion(accion: string): string {
  const texto = accion.replace(/_/g, " ").trim();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/**
 * `Comprobante:2f6d9478-3c56-…` → el tipo («Comprobante») y una referencia corta (`2f6d9478`).
 *
 * El identificador completo son 36 caracteres que parten la fila en dos renglones y no le
 * dicen nada a nadie; se conserva entero en el `title` para quien lo necesite copiar.
 */
function partirEntidad(entidad: string): {
  readonly tipo: string;
  readonly referencia: string | null;
  readonly completa: string;
} {
  const corte = entidad.indexOf(":");
  if (corte === -1) {
    return { tipo: entidad, referencia: null, completa: entidad };
  }
  const tipo = entidad
    .slice(0, corte)
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase();
  const id = entidad.slice(corte + 1);
  return {
    tipo: tipo.charAt(0).toUpperCase() + tipo.slice(1),
    referencia: /^[0-9a-f]{8}-/i.test(id) ? id.slice(0, 8) : id,
    completa: id,
  };
}

const COLUMNAS_DE_ACTIVIDAD: readonly Columna<Operacion>[] = [
  {
    clave: "operacion",
    titulo: "Operación",
    celda: (operacion) => (
      <span className="dsh-op">
        <span
          className={`dsh-op__ico dsh-op__ico--${operacion.resultado === "error" ? "error" : "ok"}`}
        >
          <Icono
            nombre={
              operacion.resultado === "error"
                ? "alerta"
                : (ICONO_DE_MODULO[operacion.modulo] ?? "actividad")
            }
          />
        </span>
        <span>
          <b className="dsh-op__nombre">{nombreDeAccion(operacion.accion)}</b>
          <span className="dsh-op__ref">
            {ETIQUETAS_DE_MODULO[operacion.modulo] ?? operacion.modulo}
          </span>
        </span>
      </span>
    ),
  },
  {
    clave: "entidad",
    titulo: "Entidad afectada",
    celda: (operacion) => {
      const entidad = partirEntidad(operacion.entidad_afectada);
      const automatica = operacion.iniciador !== "usuario";
      return (
        <span>
          <b className="dsh-entidad">
            {entidad.tipo}
            {entidad.referencia !== null && (
              <code className="dsh-entidad__id" title={entidad.completa}>
                {entidad.referencia}
              </code>
            )}
          </b>
          <span className="dsh-entidad__quien">
            {automatica ? (
              <Bot size={13} strokeWidth={2} aria-hidden="true" />
            ) : (
              <UserRound size={13} strokeWidth={2} aria-hidden="true" />
            )}
            {automatica ? "Automática" : "Iniciada por una persona"}
          </span>
        </span>
      );
    },
  },
  {
    clave: "resultado",
    titulo: "Estado",
    celda: (operacion) => (
      <Badge estado={operacion.resultado === "error" ? "error" : "ok"}>
        {ETIQUETAS_DE_RESULTADO[operacion.resultado]}
      </Badge>
    ),
  },
  {
    clave: "fecha",
    titulo: "Fecha y hora",
    alDerecha: true,
    celda: (operacion) => {
      // «15/9/26, 16:35»: la fecha arriba y la hora abajo, que se leen de un vistazo.
      const [fecha = "", hora = ""] = formatearFechaHora(operacion.timestamp).split(", ");
      return (
        <span className="dsh-fecha">
          <b>{fecha}</b>
          <span>{hora}</span>
        </span>
      );
    },
  },
];

interface AccesoDirecto {
  readonly href: string;
  readonly icono: NombreDeIcono;
  readonly nombre: string;
  readonly detalle: string;
}

/**
 * Los seis accesos del prototipo.
 *
 * Todos llevan a una pantalla que existe y está en la navegación del `(panel)/layout.tsx`. Un
 * atajo que va a un 404 es peor que no tener el atajo: enseña a desconfiar del resto.
 */
const ACCESOS: readonly AccesoDirecto[] = [
  {
    href: "/ingesta",
    icono: "subir",
    nombre: "Subir planilla",
    detalle: "Importar datos desde Excel o Sheets",
  },
  {
    href: "/facturacion",
    icono: "documento",
    nombre: "Ver facturas",
    detalle: "Comprobantes emitidos y borradores",
  },
  {
    href: "/cobros",
    icono: "tarjeta",
    nombre: "Gestionar cobros",
    detalle: "Links de pago y conciliación",
  },
  {
    href: "/agenda",
    icono: "calendario",
    nombre: "Ver agenda",
    detalle: "Turnos y entregas programadas",
  },
  {
    href: "/reportes",
    icono: "barras",
    nombre: "Reportes del período",
    detalle: "Ingresos, IVA y proyecciones",
  },
  {
    href: "/auditoria",
    icono: "lista",
    nombre: "Log de operaciones",
    detalle: "Historial técnico detallado",
  },
];
