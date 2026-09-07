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
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Select } from "@/shared";

import { ErrorDeTurno, horaDe, reservarTurno, verDisponibilidad } from "../api/turno";
import type { Horario } from "../api/turno";
import type { Recurso, ServicioAgendable } from "../api/recurso";

export interface PropsDeNuevoTurno {
  /** A quién se le agenda. Se elige antes, como en la emisión y en el cobro. */
  readonly clienteId: string;
  readonly recursos: readonly Recurso[];
  readonly servicios: readonly ServicioAgendable[];
}

export function NuevoTurno({ clienteId, recursos, servicios }: PropsDeNuevoTurno): JSX.Element {
  const router = useRouter();
  const [recursoId, setRecursoId] = useState("");
  const [servicioId, setServicioId] = useState("");
  const [fecha, setFecha] = useState("");
  const [horarios, setHorarios] = useState<readonly Horario[]>([]);
  const [elegido, setElegido] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [reservando, setReservando] = useState(false);

  const recurso = recursos.find((uno) => uno.id === recursoId);
  // RN-03: sólo los servicios asociados al recurso elegido.
  const disponibles = servicios.filter((uno) => recurso?.servicios.includes(uno.id) ?? false);
  const libres = horarios.filter((uno) => !uno.ocupado);

  async function buscar(idRecurso: string, dia: string): Promise<void> {
    setElegido("");
    setHorarios([]);
    if (idRecurso === "" || dia === "") {
      return;
    }
    setError(null);
    setBuscando(true);
    try {
      setHorarios((await verDisponibilidad(idRecurso, dia)).horarios);
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
        inicio: elegido,
      });
      router.push(`/agenda/${turno.id}`);
    } catch (fallo) {
      // «El horario seleccionado no está disponible.» llega por acá cuando alguien se
      // adelantó. La lista se vuelve a pedir para que el próximo intento sirva — y el mensaje
      // se pone **después**, porque `buscar` limpia el error para no dejar uno viejo colgado
      // cuando alguien cambia de recurso.
      await buscar(recursoId, fecha);
      setError(fallo instanceof ErrorDeTurno ? fallo.message : "No se pudo crear el turno.");
    } finally {
      setReservando(false);
    }
  }

  return (
    <form
      className="dm-formulario"
      onSubmit={(evento) => {
        evento.preventDefault();
        void reservar();
      }}
    >
      {error !== null && (
        <Alert tono="error" titulo="No se pudo reservar">
          {error}
        </Alert>
      )}

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
          void buscar(evento.target.value, fecha);
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
        onChange={(evento) => setServicioId(evento.target.value)}
      />

      <Campo
        id="turno-fecha"
        etiqueta="Fecha"
        type="date"
        value={fecha}
        onChange={(evento) => {
          setFecha(evento.target.value);
          void buscar(recursoId, evento.target.value);
        }}
      />

      {recursoId !== "" && fecha !== "" && !buscando && libres.length === 0 && (
        <Alert tono="neutral">
          El recurso no tiene horarios libres ese día. Puede ser un feriado configurado, un día que
          no atiende, o que ya esté completo.
        </Alert>
      )}

      {libres.length > 0 && (
        <Select
          id="turno-horario"
          etiqueta="Horario"
          opciones={[
            { valor: "", etiqueta: "Elegí un horario" },
            ...libres.map((uno) => ({ valor: uno.inicio, etiqueta: horaDe(uno.inicio) })),
          ]}
          value={elegido}
          onChange={(evento) => setElegido(evento.target.value)}
        />
      )}

      <div className="dm-formulario__acciones">
        <Button variante="secundario" onClick={() => router.push("/agenda")}>
          Cancelar
        </Button>
        <Button type="submit" disabled={servicioId === "" || elegido === ""} cargando={reservando}>
          Reservar turno
        </Button>
      </div>
    </form>
  );
}
