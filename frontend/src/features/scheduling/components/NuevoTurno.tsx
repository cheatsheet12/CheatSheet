/**
 * PAN-AGE-02 — Agenda · Nuevo turno (HU-E7-06).
 *
 * **El horario se elige de una lista, no se escribe.** El backend sabe qué franjas ofrece cada
 * recurso —patrón semanal más excepciones— y cuáles ya están tomadas; un campo libre haría que
 * la mitad de los intentos terminaran en «El recurso no atiende en el horario seleccionado».
 *
 * **La lista puede quedar vieja.** Entre que se pide y que se aprieta «Reservar» puede entrar
 * otro turno, y ahí el que decide es PostgreSQL (decisión D28). Por eso el error del backend
 * se muestra tal cual y la lista se vuelve a pedir: es el aviso de que alguien se adelantó.
 *
 * **Los servicios se filtran por recurso** (RN-03): sólo los asociados aparecen. Un servicio
 * que el recurso no presta no es una opción que haya que rechazar después.
 *
 * **La grilla de slots y el campo «Horario» son el mismo valor, no dos decisiones.** La grilla
 * existe porque es la única forma de ver *el día entero*: muestra también los turnos ocupados,
 * que son la respuesta a «¿por qué no me deja a las 15?». El `<select>` es el campo del
 * formulario —el que tiene etiqueta visible, el que se llega tabulando y el que el teléfono
 * abre como rueda—, y refleja lo que la grilla marca. Apretar un slot es un atajo sobre ese
 * campo, no un control paralelo: por eso los slots son botones y no radios.
 *
 * **Los turnos no se agendan en el pasado** (D95). El campo de fecha lleva `min` = hoy, pero es
 * una cortesía: el backend compara el instante y es quien rechaza. La única excepción es del
 * Administrador —«Registrar una atención ya realizada»—, que reemplaza la grilla por un campo
 * de fecha y hora con `max` = ahora, porque una atención pasada no se elige de los horarios
 * que el recurso ofrece.
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, Button, Campo, Casilla, Select } from "@/shared";

import {
  ErrorDeTurno,
  fechaDeHoy,
  horaDe,
  instanteDeAhora,
  reservarTurno,
  verDisponibilidad,
} from "../api/turno";
import type { Horario } from "../api/turno";
import type { Recurso, ServicioAgendable } from "../api/recurso";
import { IconoDeReloj } from "./iconos";

export interface PropsDeNuevoTurno {
  /** A quién se le agenda. Se elige antes, como en la emisión y en el cobro. */
  readonly clienteId: string;
  readonly recursos: readonly Recurso[];
  readonly servicios: readonly ServicioAgendable[];
  /** Sólo el Administrador puede cargar una atención ya realizada (HU-E7-06 RN-07). */
  readonly puedeRegistrarAPosteriori?: boolean;
}

export function NuevoTurno({
  clienteId,
  recursos,
  servicios,
  puedeRegistrarAPosteriori = false,
}: PropsDeNuevoTurno): JSX.Element {
  const router = useRouter();
  const [recursoId, setRecursoId] = useState("");
  const [servicioId, setServicioId] = useState("");
  const [fecha, setFecha] = useState("");
  const [horarios, setHorarios] = useState<readonly Horario[]>([]);
  const [elegido, setElegido] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [reservando, setReservando] = useState(false);
  const [aPosteriori, setAPosteriori] = useState(false);
  const [inicioPasado, setInicioPasado] = useState("");
  // Después de montar y no en el render: el servidor puede estar en otra zona horaria.
  const [limites, setLimites] = useState<{ hoy: string; ahora: string } | undefined>(undefined);
  useEffect(() => {
    setLimites({ hoy: fechaDeHoy(), ahora: instanteDeAhora() });
  }, []);

  const recurso = recursos.find((uno) => uno.id === recursoId);
  // RN-03: sólo los servicios asociados al recurso elegido.
  const disponibles = servicios.filter((uno) => recurso?.servicios.includes(uno.id) ?? false);
  const libres = horarios.filter((uno) => !uno.ocupado);
  const consultado = !aPosteriori && recursoId !== "" && fecha !== "";
  const conServicio = servicioId !== "";
  const inicioElegido = aPosteriori
    ? inicioPasado === ""
      ? ""
      : new Date(inicioPasado).toISOString()
    : elegido;

  async function buscar(idRecurso: string, idServicio: string, dia: string): Promise<void> {
    setElegido("");
    setHorarios([]);
    // La duración del turno es la del servicio (D96): sin los tres datos no hay grilla.
    if (idRecurso === "" || idServicio === "" || dia === "") {
      return;
    }
    setError(null);
    setBuscando(true);
    try {
      setHorarios((await verDisponibilidad(idRecurso, dia, idServicio)).horarios);
    } catch (fallo) {
      setError(fallo instanceof ErrorDeTurno ? fallo.message : "No se pudieron leer los horarios.");
    } finally {
      setBuscando(false);
    }
  }

  async function reservar(): Promise<void> {
    setError(null);
    setReservando(true);
    try {
      const turno = await reservarTurno({
        cliente_id: clienteId,
        servicio_id: servicioId,
        recurso_id: recursoId,
        inicio: inicioElegido,
        ...(aPosteriori ? { a_posteriori: true } : {}),
      });
      router.push(`/agenda/${turno.id}`);
    } catch (fallo) {
      // «El horario seleccionado no está disponible.» llega por acá cuando alguien se
      // adelantó. La lista se vuelve a pedir para que el próximo intento sirva — y el mensaje
      // se pone **después**, porque `buscar` limpia el error para no dejar uno viejo colgado
      // cuando alguien cambia de recurso.
      if (!aPosteriori) {
        await buscar(recursoId, servicioId, fecha);
      }
      setError(fallo instanceof ErrorDeTurno ? fallo.message : "No se pudo crear el turno.");
    } finally {
      setReservando(false);
    }
  }

  return (
    <form
      className="age-panel age-form"
      onSubmit={(evento) => {
        evento.preventDefault();
        void reservar();
      }}
    >
      <div className="age-panel__head">
        <span className="age-panel__icono" aria-hidden="true">
          <IconoDeReloj />
        </span>
        <div>
          <h2>Datos del turno</h2>
          <p>Elegí el recurso y el día; los horarios los ofrece el recurso.</p>
        </div>
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo reservar">
          {error}
        </Alert>
      )}

      <div className="age-form__campos">
        <Select
          id="turno-recurso"
          etiqueta="Recurso"
          opciones={[
            { valor: "", etiqueta: "Elegí un recurso" },
            // Sólo los activos: un recurso desactivado no acepta reservas nuevas (RN-03), y
            // ofrecerlo sería ofrecer un camino que termina en 422.
            ...recursos
              .filter((uno) => uno.activo)
              .map((uno) => ({ valor: uno.id, etiqueta: uno.nombre })),
          ]}
          value={recursoId}
          onChange={(evento) => {
            setRecursoId(evento.target.value);
            setServicioId("");
            void buscar(evento.target.value, "", fecha);
          }}
        />

        <Select
          id="turno-servicio"
          etiqueta="Servicio"
          ayuda="Sólo los servicios que se prestan en ese recurso."
          opciones={[
            { valor: "", etiqueta: "Elegí un servicio" },
            ...disponibles.map((uno) => ({
              valor: uno.id,
              etiqueta: `${uno.nombre} — ${uno.duracion_estandar_min} min`,
            })),
          ]}
          value={servicioId}
          onChange={(evento) => {
            setServicioId(evento.target.value);
            // Cambiar de servicio cambia la duración, y con ella la grilla: se vuelve a pedir
            // y no queda elegido un horario que era de la grilla anterior.
            void buscar(recursoId, evento.target.value, fecha);
          }}
        />

        {aPosteriori ? (
          <Campo
            id="turno-inicio-realizado"
            etiqueta="Fecha y hora de la atención"
            ayuda="Tiene que haber terminado. No se le avisa nada al cliente."
            type="datetime-local"
            max={limites?.ahora}
            value={inicioPasado}
            onChange={(evento) => setInicioPasado(evento.target.value)}
          />
        ) : (
          <Campo
            id="turno-fecha"
            etiqueta="Fecha"
            type="date"
            min={limites?.hoy}
            value={fecha}
            onChange={(evento) => {
              setFecha(evento.target.value);
              void buscar(recursoId, servicioId, evento.target.value);
            }}
          />
        )}
      </div>

      {puedeRegistrarAPosteriori && (
        <Casilla
          id="turno-a-posteriori"
          checked={aPosteriori}
          onChange={(evento) => {
            setAPosteriori(evento.target.checked);
            setElegido("");
            setHorarios([]);
            setInicioPasado("");
            setError(null);
          }}
        >
          Registrar una atención ya realizada
        </Casilla>
      )}

      {consultado && (
        <section className="age-slots" aria-labelledby="turno-slots-titulo">
          <div className="age-slots__head">
            <h3 className="age-slots__titulo" id="turno-slots-titulo">
              Disponibilidad del recurso
            </h3>
            {conServicio && (
              <span className="age-slots__cuenta">
                {buscando
                  ? "buscando…"
                  : `${libres.length} de ${horarios.length} ${horarios.length === 1 ? "libre" : "libres"}`}
              </span>
            )}
          </div>

          {!conServicio && <Alert tono="neutral">Elegí el servicio para ver los horarios</Alert>}

          {conServicio && horarios.length > 0 && (
            <>
              <div className="age-slots__grilla">
                {horarios.map((horario) => (
                  <button
                    key={horario.inicio}
                    type="button"
                    className={`age-slot${horario.ocupado ? " age-slot--ocupado" : ""}${
                      elegido === horario.inicio ? " age-slot--elegido" : ""
                    }`}
                    disabled={horario.ocupado}
                    aria-pressed={elegido === horario.inicio}
                    onClick={() => setElegido(horario.inicio)}
                  >
                    <span className="age-slot__hora">{horaDe(horario.inicio)}</span>
                  </button>
                ))}
              </div>
              {/* Los ocupados se muestran, no se esconden: una grilla con huecos sin
                  explicación deja pensando si el recurso atiende a esa hora o no. La frase que
                  los explica aparece sólo cuando hay alguno: explicar un tachado que no está en
                  la pantalla hace dudar de si uno se lo perdió. */}
              <p className="age-slots__leyenda">
                {libres.length < horarios.length
                  ? "Los horarios tachados ya están tomados. Elegir uno acá completa el campo «Horario»."
                  : "Elegir un horario acá completa el campo «Horario»."}
              </p>
            </>
          )}

          {conServicio && !buscando && horarios.length === 0 && (
            <Alert tono="neutral">
              El recurso no tiene horarios libres ese día. Puede ser un feriado configurado, un día
              que no atiende, o que ya esté completo.
            </Alert>
          )}
        </section>
      )}

      {!aPosteriori && libres.length > 0 && (
        <Select
          id="turno-horario"
          etiqueta="Horario"
          ayuda="El mismo que marca la grilla de arriba."
          opciones={[
            { valor: "", etiqueta: "Elegí un horario" },
            ...libres.map((uno) => ({ valor: uno.inicio, etiqueta: horaDe(uno.inicio) })),
          ]}
          value={elegido}
          onChange={(evento) => setElegido(evento.target.value)}
        />
      )}

      <div className="age-form__acciones">
        <Button variante="secundario" onClick={() => router.push("/agenda")}>
          Cancelar
        </Button>
        <Button
          type="submit"
          disabled={servicioId === "" || inicioElegido === ""}
          cargando={reservando}
        >
          {aPosteriori ? "Registrar atención" : "Reservar turno"}
        </Button>
      </div>
    </form>
  );
}
