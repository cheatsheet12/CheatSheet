/**
 * PAN-AGE-01 — Agenda · Vista de turnos (HU-E7-01).
 *
 * Por recurso y por rango de fechas, con el día en curso por defecto (RN-01). El rango lo
 * decide el backend cuando no se manda ninguno, así que esta pantalla arranca sin filtros y
 * los agrega cuando alguien los toca — un `desde`/`hasta` puesto acá con la fecha del
 * navegador podría no coincidir con el día que el local está atendiendo.
 *
 * **Tres vistas sobre los mismos datos.** Lista (turnos agrupados por día), Semana y Día (una
 * grilla de tiempo). Las de calendario piden a la API con los mismos parámetros `desde`/`hasta`
 * que el filtro de fechas, derivados del período que se mira; la Lista conserva exactamente los
 * filtros que se eligieron.
 *
 * **«Reprogramado» no aparece en ningún lado**, y es a propósito (RN-02): un turno movido se ve
 * en su franja nueva con el estado que tenía. Que se movió lo dice la bitácora.
 *
 * **El encabezado vive acá y no en `page.tsx`.** El CTA verde forma parte del encabezado —es lo
 * único que se hace desde esta pantalla— y quién puede verlo depende del rol, que es un dato
 * que este componente ya tiene.
 *
 * **Los nombres del cliente y del servicio son opcionales.** Un `Turno` viaja con ids; los
 * nombres los resuelve la página del servidor. Cuando no llegan se muestra el id, que es feo
 * pero es cierto: una celda vacía haría pensar que el turno está mal cargado.
 */

"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Alert } from "@/shared";

import { ErrorDeTurno, MENSAJE_SIN_TURNOS, fechaLargaDe, listarTurnos } from "../api/turno";
import type { FiltrosDeAgenda, ListadoDeTurnos, Nombrado } from "../api/turno";
import type { Recurso } from "../api/recurso";
import { BarraDeAgenda } from "./BarraDeAgenda";
import { CalendarioDeTurnos } from "./CalendarioDeTurnos";
import { IconoDeCalendario, IconoDeMas, IconoDeRecurso } from "./iconos";
import { ListaDeTurnos } from "./ListaDeTurnos";
import { diaDe, rangoDeVista, sumarDias } from "./calendario";
import type { VistaDeAgenda } from "./calendario";
import type { NombresDeAgenda } from "./nombres";

export interface PropsDeAgendaDelDia {
  readonly inicial: ListadoDeTurnos;
  readonly recursos: readonly Recurso[];
  /** Administrador y Operador reservan; Solo Lectura sólo mira (HU-E7-01 RN-03). */
  readonly puedeGestionar: boolean;
  /** Los clientes que el catálogo devolvió, para poner un nombre donde hay un id. */
  readonly clientes?: readonly Nombrado[];
  /** Ídem con los servicios agendables. */
  readonly servicios?: readonly Nombrado[];
  /**
   * El instante «ahora» del servidor, para el cintillo.
   *
   * Lo manda la página en vez de calcularlo acá para que el render del servidor y el del
   * navegador escriban el mismo día: dos `new Date()` a los lados de la medianoche no lo
   * hacen, y React descarta el HTML cuando el texto no coincide.
   */
  readonly hoy?: string;
}

/** En un celular una grilla de siete columnas no se lee: las vistas de calendario pasan a lista. */
const CONSULTA_DE_CELULAR = "(max-width: 720px)";

function useEsCelular(): boolean {
  const [celular, setCelular] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return undefined;
    }
    const consulta = window.matchMedia(CONSULTA_DE_CELULAR);
    const actualizar = (): void => setCelular(consulta.matches);
    actualizar();
    consulta.addEventListener("change", actualizar);
    return () => consulta.removeEventListener("change", actualizar);
  }, []);
  return celular;
}

/** Los parámetros del pedido: los filtros tal cual en la Lista; con el período en el calendario. */
function parametrosDe(
  vista: VistaDeAgenda,
  ancla: string,
  filtros: FiltrosDeAgenda,
): FiltrosDeAgenda {
  return vista === "lista" ? filtros : { ...filtros, ...rangoDeVista(vista, ancla) };
}

export function AgendaDelDia({
  inicial,
  recursos,
  puedeGestionar,
  clientes = [],
  servicios = [],
  hoy,
}: PropsDeAgendaDelDia): JSX.Element {
  // El instante «ahora»: el del servidor al principio y el del navegador cada minuto.
  const [ahora, setAhora] = useState(() => hoy ?? new Date().toISOString());
  const [listado, setListado] = useState<ListadoDeTurnos>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeAgenda>({});
  const [vista, setVista] = useState<VistaDeAgenda>("lista");
  const [ancla, setAncla] = useState(() => diaDe(hoy ?? new Date().toISOString()));
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pedidos = useRef(0);
  const celular = useEsCelular();

  useEffect(() => {
    const reloj = setInterval(() => setAhora(new Date().toISOString()), 60_000);
    return () => clearInterval(reloj);
  }, []);

  const hoyDia = diaDe(ahora);
  const nombres = useMemo<NombresDeAgenda>(() => {
    const deRecurso = new Map(recursos.map((uno) => [uno.id, uno.nombre]));
    const deCliente = new Map(clientes.map((uno) => [uno.id, uno.nombre]));
    const deServicio = new Map(servicios.map((uno) => [uno.id, uno.nombre]));
    return {
      cliente: (id) => deCliente.get(id) ?? id,
      servicio: (id) => deServicio.get(id) ?? id,
      // El nombre y no el id: un id en una agenda no le dice nada a quien la mira. Si el
      // recurso no está en la lista —porque se desactivó—, el id es mejor que nada.
      recurso: (id) => deRecurso.get(id) ?? id,
    };
  }, [recursos, clientes, servicios]);

  const cantidad = listado.turnos.length;
  const hayFiltros =
    Boolean(filtros.recurso_id) ||
    Boolean(filtros.estado) ||
    Boolean(filtros.desde) ||
    Boolean(filtros.hasta);
  const enCalendario = vista !== "lista" && !celular;

  async function cargar(
    siguienteVista: VistaDeAgenda,
    siguienteAncla: string,
    siguientesFiltros: FiltrosDeAgenda,
  ): Promise<void> {
    const numero = pedidos.current + 1;
    pedidos.current = numero;
    setError(null);
    setCargando(true);
    try {
      const respuesta = await listarTurnos(
        parametrosDe(siguienteVista, siguienteAncla, siguientesFiltros),
      );
      // Si mientras tanto se pidió otra cosa, esta respuesta ya no es la que se está mirando.
      if (pedidos.current === numero) {
        setListado(respuesta);
      }
    } catch (fallo) {
      if (pedidos.current === numero) {
        setError(
          fallo instanceof ErrorDeTurno ? fallo.message : "No se pudo actualizar la agenda.",
        );
      }
    } finally {
      if (pedidos.current === numero) {
        setCargando(false);
      }
    }
  }

  function aplicar(cambios: FiltrosDeAgenda): void {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    void cargar(vista, ancla, siguientes);
  }

  function limpiar(): void {
    setFiltros({});
    void cargar(vista, ancla, {});
  }

  function elegirVista(siguiente: VistaDeAgenda): void {
    if (siguiente === vista) {
      return;
    }
    setVista(siguiente);
    void cargar(siguiente, ancla, filtros);
  }

  function mover(sentido: -1 | 1): void {
    if (vista === "lista") {
      return;
    }
    const siguiente = sumarDias(ancla, sentido * (vista === "semana" ? 7 : 1));
    setAncla(siguiente);
    void cargar(vista, siguiente, filtros);
  }

  function irAHoy(): void {
    setAncla(hoyDia);
    void cargar(vista, hoyDia, filtros);
  }

  return (
    <div className="age-pantalla">
      <div className="age-encabezado">
        <div>
          <p className="age-encabezado__eyebrow">Operaciones · {fechaLargaDe(ahora)}</p>
          <h1 className="age-encabezado__titulo">Agenda</h1>
          <p className="age-encabezado__intro">
            Los turnos de tu negocio, por día, por semana o por recurso. Un turno reprogramado
            aparece en su franja nueva y conserva su estado.
          </p>
        </div>
        <div className="age-encabezado__acciones">
          <Link className="age-secundario" href="/agenda/recursos">
            <span className="age-secundario__ico" aria-hidden="true">
              <IconoDeRecurso />
            </span>
            Recursos
          </Link>
          {puedeGestionar && (
            <Link className="age-principal" href="/agenda/nuevo">
              <span className="age-principal__ico" aria-hidden="true">
                <IconoDeMas />
              </span>
              Nuevo turno
            </Link>
          )}
        </div>
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <BarraDeAgenda
        vista={vista}
        ancla={ancla}
        filtros={filtros}
        recursos={recursos}
        total={cantidad}
        onVista={elegirVista}
        onMover={mover}
        onHoy={irAHoy}
        onFiltros={aplicar}
        onLimpiar={limpiar}
      />

      <div
        className="age-contenido"
        aria-busy={cargando}
        data-cargando={cargando ? "true" : undefined}
        key={`${enCalendario ? vista : "lista"}-${ancla}`}
      >
        {enCalendario && (
          <>
            {cantidad === 0 && !cargando && (
              <VacioDeAgenda
                compacto
                filtrado={hayFiltros}
                puedeGestionar={puedeGestionar}
                onLimpiar={limpiar}
              />
            )}
            <CalendarioDeTurnos
              vista={vista === "dia" ? "dia" : "semana"}
              ancla={ancla}
              hoy={hoyDia}
              ahora={ahora}
              turnos={listado.turnos}
              recursos={recursos}
              nombres={nombres}
            />
          </>
        )}
        {!enCalendario && cantidad > 0 && (
          <ListaDeTurnos turnos={listado.turnos} hoy={hoyDia} nombres={nombres} />
        )}
        {!enCalendario && cantidad === 0 && (
          <VacioDeAgenda
            filtrado={hayFiltros}
            puedeGestionar={puedeGestionar}
            onLimpiar={limpiar}
          />
        )}
      </div>
    </div>
  );
}

/**
 * El día sin turnos: un día normal, no un error. Con filtros puestos la causa más probable es
 * el filtro, así que ofrece sacarlo; sin filtros ofrece lo único que se hace desde acá.
 */
function VacioDeAgenda({
  filtrado,
  puedeGestionar,
  compacto = false,
  onLimpiar,
}: {
  readonly filtrado: boolean;
  readonly puedeGestionar: boolean;
  readonly compacto?: boolean;
  readonly onLimpiar: () => void;
}): JSX.Element {
  return (
    <div className="age-sinturnos" data-compacto={compacto ? "true" : undefined}>
      <span className="age-sinturnos__icono" aria-hidden="true">
        <IconoDeCalendario />
      </span>
      <div className="age-sinturnos__cuerpo">
        <p className="age-sinturnos__titulo">
          {filtrado ? "Ningún turno coincide con los filtros" : MENSAJE_SIN_TURNOS}
        </p>
        {filtrado && <p className="age-sinturnos__texto">{MENSAJE_SIN_TURNOS}</p>}
      </div>
      <div className="age-sinturnos__acciones">
        {filtrado && (
          <button type="button" className="age-sinturnos__accion" onClick={onLimpiar}>
            Limpiar filtros
          </button>
        )}
        {puedeGestionar && (
          <Link
            className="age-sinturnos__accion age-sinturnos__accion--primaria"
            href="/agenda/nuevo"
          >
            Nuevo turno
          </Link>
        )}
      </div>
    </div>
  );
}
