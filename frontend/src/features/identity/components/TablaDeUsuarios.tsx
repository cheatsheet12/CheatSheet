/**
 * PAN-USR-01 — the company's users (HU-E1-04, HU-E1-05, HU-E1-06).
 *
 * Gap P9: no prototype defines this screen. The layout is the one decided in the unit
 * plan — the four columns the acceptance criterion names (nombre, email, rol, estado),
 * per-row actions, and a modal for the invitation.
 *
 * **The role governs what is rendered, and that is cosmetic, not security.** An Operador
 * sees the list — HU-E1-05's third criterion has them in the section finding the action
 * unavailable — and none of the actions. What actually refuses is the backend, on every
 * endpoint; hiding the button only avoids offering something that would be rejected.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, Select, Tabla } from "@/shared";
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

export interface PropsDeTablaDeUsuarios {
  readonly usuarios: readonly UsuarioDeLaEmpresa[];
  readonly rolDelUsuarioActual: RolUsuario;
  /** The id of whoever is looking, so the row cannot offer to deactivate itself blindly. */
  readonly usuarioActualId: string;
}

const ETIQUETA_DE_ROL: Record<RolUsuario, string> = {
  ADMINISTRADOR: "Administrador",
  OPERADOR: "Operador",
  SOLO_LECTURA: "Solo lectura",
};

const ROLES = Object.entries(ETIQUETA_DE_ROL).map(([valor, etiqueta]) => ({ valor, etiqueta }));

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

  const ejecutar = async (
    usuarioId: string,
    accion: () => Promise<void>,
    mensaje: string,
  ): Promise<void> => {
    setOcupado(usuarioId);
    setError(null);
    setAviso(null);
    try {
      await accion();
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

  const columnas: readonly Columna<UsuarioDeLaEmpresa>[] = [
    { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
    { clave: "email", titulo: "Email", celda: (fila) => fila.email },
    {
      clave: "rol",
      titulo: "Rol",
      celda: (fila) =>
        esAdministrador && fila.estado !== "INVITADO" ? (
          <Select
            id={`rol-${fila.id}`}
            etiqueta={`Rol de ${fila.nombre}`}
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
        ) : (
          ETIQUETA_DE_ROL[fila.rol]
        ),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={TONO_DE_ESTADO[fila.estado]}>{ETIQUETA_DE_ESTADO[fila.estado]}</Badge>
      ),
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) => <span className="tabla__acciones">{acciones(fila)}</span>,
    },
  ];

  function acciones(fila: UsuarioDeLaEmpresa): JSX.Element | null {
    if (!esAdministrador) {
      return null;
    }
    if (fila.estado === "INVITADO" && fila.invitacion_id !== null) {
      const invitacionId = fila.invitacion_id;
      return (
        <>
          <Button
            variante="secundario"
            cargando={ocupado === fila.id}
            onClick={() => {
              void ejecutar(
                fila.id,
                async () => {
                  await reenviarInvitacion(invitacionId);
                },
                `Invitación reenviada a ${fila.email}.`,
              );
            }}
          >
            Reenviar
          </Button>
          <Button
            variante="destructivo"
            confirmacion={`¿Revocar la invitación de ${fila.email}?`}
            cargando={ocupado === fila.id}
            onClick={() => {
              void ejecutar(
                fila.id,
                async () => {
                  await revocarInvitacion(invitacionId);
                  setFilas((previas) => previas.filter((otra) => otra.id !== fila.id));
                },
                `Invitación revocada. Podés volver a invitar a ${fila.email}.`,
              );
            }}
          >
            Revocar
          </Button>
        </>
      );
    }
    if (fila.estado === "INACTIVO") {
      return (
        <Button
          variante="secundario"
          cargando={ocupado === fila.id}
          onClick={() => {
            void ejecutar(
              fila.id,
              async () => reemplazar(await reactivarUsuario(fila.id)),
              `${fila.nombre} vuelve a tener acceso, con su rol anterior.`,
            );
          }}
        >
          Reactivar
        </Button>
      );
    }
    return (
      <Button
        variante="destructivo"
        confirmacion={
          fila.id === usuarioActualId
            ? "Vas a desactivar tu propia cuenta y vas a perder el acceso. ¿Seguro?"
            : `¿Desactivar a ${fila.nombre}? Pierde el acceso de inmediato.`
        }
        cargando={ocupado === fila.id}
        onClick={() => {
          void ejecutar(
            fila.id,
            async () => reemplazar(await desactivarUsuario(fila.id)),
            `${fila.nombre} ya no tiene acceso.`,
          );
        }}
      >
        Desactivar
      </Button>
    );
  }

  return (
    <Card titulo="Usuarios de la empresa">
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      {esAdministrador && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <Button onClick={() => setInvitando(true)}>Invitar usuario</Button>
        </div>
      )}

      <Tabla
        titulo="Usuarios de la empresa"
        columnas={columnas}
        filas={filas}
        claveDeFila={(fila) => fila.id}
        vacia="Todavía no hay nadie más en la empresa."
      />

      <ModalDeInvitacion
        abierto={invitando}
        onCerrar={() => setInvitando(false)}
        onInvitado={(usuario) => {
          setFilas((previas) => [...previas, usuario]);
          setInvitando(false);
          setAviso(`Invitación enviada a ${usuario.email}.`);
        }}
      />
    </Card>
  );
}
