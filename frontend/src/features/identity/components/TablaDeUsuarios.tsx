/**
 * PAN-USR-01 — the company's users (HU-E1-04, HU-E1-05, HU-E1-06).
 *
 * Gap P9: no prototype defines this screen. The four columns the acceptance criterion
 * names (nombre, email, rol, estado) are the ones it has, with per-row actions and a modal
 * for the invitation.
 *
 * **The role governs what is rendered, and that is cosmetic, not security.** An Operador
 * sees the list — HU-E1-05's third criterion has them in the section finding the action
 * unavailable — and none of the actions. What actually refuses is the backend, on every
 * endpoint; hiding the button only avoids offering something that would be rejected.
 *
 * **El encabezado lo dibuja este componente y no la página.** El CTA depende del rol y abre
 * un modal, así que necesita estado; dejar el título en el server component y el botón acá
 * los separaba en dos bloques, y el botón terminaba adentro de la tarjeta arriba de la
 * tabla, leyéndose como si actuara sobre una fila. Título, bajada y acción son una pieza,
 * como en la agenda y en las respuestas frecuentes.
 *
 * **La confirmación de las bajas sigue siendo un `confirm` del navegador.** No es la forma
 * que tiene el resto del panel —ahí la baja se confirma en un modal— y está anotado en el
 * informe: los casos 40 y 41 de `TablaDeUsuarios.test.tsx` piden que un solo clic en
 * «Desactivar» llame a la API, y un modal necesita dos. Lo que sí cambió es el botón: era
 * una caja con borde rojo permanente en cada fila y ahora es texto, como en auditoría y en
 * las respuestas frecuentes.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Select, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import type { RolUsuario, UsuarioDeLaEmpresa } from "../api/cliente";
import {
  ErrorDeFormulario,
  cambiarRol,
  desactivarUsuario,
  reactivarUsuario,
  reenviarInvitacion,
  revocarInvitacion,
} from "../api/cliente";
import { ModalDeInvitacion } from "./ModalDeInvitacion";
import { ETIQUETA_DE_ROL, QUE_PUEDE, ROLES } from "./roles";

export interface PropsDeTablaDeUsuarios {
  readonly usuarios: readonly UsuarioDeLaEmpresa[];
  readonly rolDelUsuarioActual: RolUsuario;
  /** The id of whoever is looking, so the row cannot offer to deactivate itself blindly. */
  readonly usuarioActualId: string;
}

const TONO_DE_ESTADO: Record<UsuarioDeLaEmpresa["estado"], EstadoDeBadge> = {
  ACTIVO: "ok",
  INVITADO: "pendiente",
  INACTIVO: "error",
};

const ETIQUETA_DE_ESTADO: Record<UsuarioDeLaEmpresa["estado"], string> = {
  ACTIVO: "Activo",
  INVITADO: "Invitación pendiente",
  INACTIVO: "Inactivo",
};

/**
 * La inicial del disco.
 *
 * Una invitación pendiente todavía no tiene nombre —viaja como «(invitación pendiente)»—,
 * así que ahí la letra sale del email, que es lo único que se sabe de esa persona. Un
 * paréntesis adentro del círculo no identifica a nadie.
 */
function inicialDe(fila: UsuarioDeLaEmpresa): string {
  const fuente = /^\p{L}/u.test(fila.nombre) ? fila.nombre : fila.email;
  return fuente.trim().slice(0, 1).toUpperCase();
}

/** «1 persona» y no «1 personas»: el conteo se lee, y un plural mal puesto se nota. */
function palabra(cantidad: number, singular: string, plural: string): string {
  return cantidad === 1 ? singular : plural;
}

/** El «+» del CTA, en línea: `shared` no tiene catálogo de iconos y R5 prohíbe traerlo de otra feature. */
function IconoDeMas(): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path d="M8 3.2v9.6M3.2 8h9.6" strokeLinecap="round" />
    </svg>
  );
}

export function TablaDeUsuarios({
  usuarios,
  rolDelUsuarioActual,
  usuarioActualId,
}: PropsDeTablaDeUsuarios): JSX.Element {
  const [filas, setFilas] = useState<readonly UsuarioDeLaEmpresa[]>(usuarios);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [invitando, setInvitando] = useState(false);

  const esAdministrador = rolDelUsuarioActual === "ADMINISTRADOR";
  const pendientes = filas.filter((fila) => fila.estado === "INVITADO").length;

  const ejecutar = async (
    usuarioId: string,
    accionAsincronica: () => Promise<void>,
    mensaje: string,
  ): Promise<void> => {
    setOcupado(usuarioId);
    setError(null);
    setAviso(null);
    try {
      await accionAsincronica();
      setAviso(mensaje);
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeFormulario
          ? fallo.detalle
          : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      );
    } finally {
      setOcupado(null);
    }
  };

  const reemplazar = (actualizado: UsuarioDeLaEmpresa): void => {
    setFilas((previas) => previas.map((fila) => (fila.id === actualizado.id ? actualizado : fila)));
  };

  const columnas: Columna<UsuarioDeLaEmpresa>[] = [
    {
      clave: "nombre",
      titulo: "Nombre",
      celda: (fila) => (
        <span className="cfg-persona">
          <span
            className={`cfg-persona__inicial${
              fila.id === usuarioActualId ? " cfg-persona__inicial--yo" : ""
            }`}
            aria-hidden="true"
          >
            {inicialDe(fila)}
          </span>
          {/* El id lo referencia el `aria-describedby` de las acciones de la fila:
              «Desactivar» suelto no dice a quién, y el nombre accesible del botón no se
              puede tocar sin cambiar lo que buscan los casos 38 y 40. */}
          <span className="cfg-persona__nombre" id={`usuario-${fila.id}`}>
            {fila.nombre}
          </span>
          {fila.id === usuarioActualId && <span className="cfg-yo">· vos</span>}
        </span>
      ),
    },
    {
      clave: "email",
      titulo: "Email",
      celda: (fila) => <span className="cfg-email">{fila.email}</span>,
    },
    {
      clave: "rol",
      titulo: "Rol",
      celda: (fila) =>
        esAdministrador && fila.estado !== "INVITADO" ? (
          <span className="cfg-rol">
            <Select
              id={`rol-${fila.id}`}
              etiqueta={`Rol de ${fila.nombre}`}
              etiquetaOculta
              opciones={ROLES}
              value={fila.rol}
              disabled={ocupado === fila.id}
              onChange={(evento) => {
                const rol = evento.target.value as RolUsuario;
                void ejecutar(
                  fila.id,
                  async () => reemplazar(await cambiarRol(fila.id, rol)),
                  `Rol actualizado: ${fila.nombre} ahora es ${ETIQUETA_DE_ROL[rol]}.`,
                );
              }}
            />
          </span>
        ) : (
          <span className="cfg-rol--fijo">{ETIQUETA_DE_ROL[fila.rol]}</span>
        ),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={TONO_DE_ESTADO[fila.estado]}>{ETIQUETA_DE_ESTADO[fila.estado]}</Badge>
      ),
    },
  ];

  // The actions column is not rendered empty for somebody who has no actions: a header
  // over five blank cells looks like a screen that failed to load its buttons.
  if (esAdministrador) {
    columnas.push({
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) => <span className="tabla__acciones">{acciones(fila)}</span>,
    });
  }

  /**
   * Una acción de fila.
   *
   * `confirmacion` corre antes de tocar la API, igual que lo hacía el `Button` destructivo
   * del catálogo: acá el botón pasó a ser texto y la baranda tenía que venirse con él.
   */
  function accion(
    fila: UsuarioDeLaEmpresa,
    texto: string,
    correr: () => Promise<void>,
    opciones: { readonly baja?: boolean; readonly confirmacion?: string } = {},
  ): JSX.Element {
    return (
      <button
        type="button"
        className={`cfg-accion${opciones.baja === true ? " cfg-accion--baja" : ""}`}
        aria-describedby={`usuario-${fila.id}`}
        disabled={ocupado === fila.id}
        aria-busy={ocupado === fila.id}
        onClick={() => {
          if (opciones.confirmacion !== undefined && !window.confirm(opciones.confirmacion)) {
            return;
          }
          void correr();
        }}
      >
        {texto}
      </button>
    );
  }

  function acciones(fila: UsuarioDeLaEmpresa): JSX.Element | null {
    if (!esAdministrador) {
      return null;
    }
    if (fila.estado === "INVITADO" && fila.invitacion_id !== null) {
      const invitacionId = fila.invitacion_id;
      return (
        <>
          {accion(fila, "Reenviar", () =>
            ejecutar(
              fila.id,
              async () => {
                await reenviarInvitacion(invitacionId);
              },
              `Invitación reenviada a ${fila.email}.`,
            ),
          )}
          {accion(
            fila,
            "Revocar",
            () =>
              ejecutar(
                fila.id,
                async () => {
                  await revocarInvitacion(invitacionId);
                  setFilas((previas) => previas.filter((otra) => otra.id !== fila.id));
                },
                `Invitación revocada. Podés volver a invitar a ${fila.email}.`,
              ),
            { baja: true, confirmacion: `¿Revocar la invitación de ${fila.email}?` },
          )}
        </>
      );
    }
    if (fila.estado === "INACTIVO") {
      return accion(fila, "Reactivar", () =>
        ejecutar(
          fila.id,
          async () => reemplazar(await reactivarUsuario(fila.id)),
          `${fila.nombre} vuelve a tener acceso, con su rol anterior.`,
        ),
      );
    }
    return accion(
      fila,
      "Desactivar",
      () =>
        ejecutar(
          fila.id,
          async () => reemplazar(await desactivarUsuario(fila.id)),
          `${fila.nombre} ya no tiene acceso.`,
        ),
      {
        baja: true,
        confirmacion:
          fila.id === usuarioActualId
            ? "Vas a desactivar tu propia cuenta y vas a perder el acceso. ¿Seguro?"
            : `¿Desactivar a ${fila.nombre}? Pierde el acceso de inmediato.`,
      },
    );
  }

  return (
    <>
      <header className="cfg-encabezado">
        <div>
          <span className="cfg-encabezado__eyebrow">Configuración · Usuarios</span>
          <h1>Usuarios</h1>
          <p className="cfg-encabezado__intro">
            Quién entra a la empresa y con qué rol. Una invitación queda pendiente hasta que la
            persona elige su contraseña.
          </p>
        </div>
        {esAdministrador && (
          <div className="cfg-encabezado__acciones">
            <Button onClick={() => setInvitando(true)}>
              <span className="cfg-cta__icono" aria-hidden="true">
                <IconoDeMas />
              </span>
              Invitar usuario
            </Button>
          </div>
        )}
      </header>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <div className="cfg-panel">
        <div className="cfg-panel__cab">
          {/* No repite el `<h1>`: aquel nombra la pantalla, este nombra la lista. */}
          <h2 className="cfg-panel__titulo">Quién tiene acceso</h2>
          <p className="cfg-panel__cuenta">
            <b>{filas.length}</b> {palabra(filas.length, "persona", "personas")}
            {pendientes > 0 && (
              <>
                {" · "}
                <b>{pendientes}</b> sin aceptar todavía
              </>
            )}
          </p>
        </div>

        <Tabla
          titulo="Usuarios de la empresa"
          columnas={columnas}
          filas={filas}
          claveDeFila={(fila) => fila.id}
          vacia={
            esAdministrador
              ? "Todavía no invitaste a nadie más. Con «Invitar usuario» le llega un enlace para entrar."
              : "Todavía no hay nadie más en la empresa."
          }
        />

        {/* La leyenda de la columna «Rol», al pie de la tabla que explica. En una tarjeta
            aparte quedaba lejos de lo que nombra, y con una sola persona en la empresa el
            panel se veía a medio cargar. */}
        <dl className="cfg-roles">
          {ROLES.map((rol) => (
            <div key={rol.valor}>
              <dt className="cfg-roles__nombre">{rol.etiqueta}</dt>
              <dd className="cfg-roles__que">{QUE_PUEDE[rol.valor]}</dd>
            </div>
          ))}
        </dl>
      </div>

      <ModalDeInvitacion
        abierto={invitando}
        onCerrar={() => setInvitando(false)}
        onInvitado={(usuario) => {
          setFilas((previas) => [...previas, usuario]);
          setInvitando(false);
          setAviso(`Invitación enviada a ${usuario.email}.`);
        }}
      />
    </>
  );
}
