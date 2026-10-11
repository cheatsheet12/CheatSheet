"""The use cases of HU-E2-05, and the connection path the following units reuse.

Together with `ports.py`, this is the published contract of ADR-0003. It imports from no
other context — the role arrives as a `RolUsuario` from the Shared Kernel, not from
`identity`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    PermisoDenegado,
    ProveedorNoDisponible,
    SistemaNoConfigurable,
)
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    PortVerificadorDeConexion,
    ResultadoDeVerificacion,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.eventos import CambioDeEstado
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_CUIT,
    CLAVE_ETIQUETA,
    SISTEMAS_EN_PANTALLA,
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

ROLES_QUE_PUEDEN_LEER = frozenset({RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR})


@dataclass(frozen=True, slots=True)
class SinVeredicto:
    """The check could not be completed: a timeout, an unreachable host, no adapter.

    Distinct from a `ResultadoDeVerificacion` carrying `NO_CONECTADO`, and the difference
    is not pedantic — one is the provider saying no, the other is us failing to ask. The
    aggregate needs to tell them apart to keep a `PENDIENTE` integration pending when the
    network fails mid-poll; see `registrar_intento_fallido`.
    """

    detalle: str


async def verificar_con_timeout(
    *,
    configuracion: ConfiguracionDeIntegracion,
    adaptadores: PortRegistroDeAdaptadores,
    cifrado: PortCifradoDeCredenciales,
    timeout_segundos: int,
) -> ResultadoDeVerificacion | SinVeredicto:
    """Ask one provider about one integration, bounded in time. Never raises.

    Shared by the on-screen check of HU-E2-05 and by the background poll of HU-E2-03,
    because the guarantee both need is identical: whatever happens to one provider, the
    caller gets an answer back and decides what it means.
    """
    verificador = adaptadores.verificador(configuracion.sistema)
    if verificador is None:
        return SinVeredicto("No hay verificador registrado para este sistema")
    try:
        return await asyncio.wait_for(
            _consultar(verificador, configuracion, cifrado), timeout=timeout_segundos
        )
    except TimeoutError:
        return SinVeredicto(f"El servicio no respondio en {timeout_segundos} segundos")
    except ProveedorNoDisponible as exc:
        return SinVeredicto(str(exc))


async def _consultar(
    verificador: PortVerificadorDeConexion,
    configuracion: ConfiguracionDeIntegracion,
    cifrado: PortCifradoDeCredenciales,
) -> ResultadoDeVerificacion:
    """Decrypt and ask. The plaintext lives in this frame and nowhere else.

    Point 3 of ADR-0003: the credential is decrypted inside this context, handed to the
    adapter, and never stored back on the aggregate.
    """
    plano = cifrado.descifrar(configuracion.credencial)
    return await verificador.verificar(plano, configuracion.parametros)


def aplicar_resultado(
    configuracion: ConfiguracionDeIntegracion,
    resultado: ResultadoDeVerificacion | SinVeredicto,
    ahora: datetime,
) -> CambioDeEstado | None:
    """Fold one check's outcome into the aggregate. Shared with the pending-poll task.

    Two branches, and the split is the whole point: a verdict is recorded as one — with
    whatever the provider reported about itself merged in (RN-03) — while a failure to
    obtain a verdict goes through `registrar_intento_fallido`, which is what keeps a
    `PENDIENTE` integration pending across a network blip.
    """
    if isinstance(resultado, SinVeredicto):
        return configuracion.registrar_intento_fallido(resultado.detalle, ahora)
    configuracion.actualizar_parametros(resultado.parametros)
    return configuracion.registrar_verificacion(resultado.estado, resultado.detalle, ahora)


@dataclass(frozen=True, slots=True)
class VistaDeIntegracion:
    """One card of PAN-CFG-INT.

    `configurada` is what separates "never connected" from "connected and currently
    down": both read `NO_CONECTADO`, and the screen offers "Conectar" for the first and
    "Reconectar" for the second, which is the acceptance criterion "indica la acción para
    reconectarla".
    """

    sistema: SistemaExterno
    estado: EstadoDeConexion
    detalle: str | None
    ambiente: Ambiente | None
    verificado_en: datetime | None
    configurada: bool
    #: HU-E2-03 RN-03's verified display name, and whatever the equivalent turns out to be
    #: for the next provider. Only named parameters cross this boundary: everything else in
    #: `parametros` either identifies the account to the provider or drives a simulation,
    #: and neither belongs in a response.
    etiqueta: str | None = None
    #: The tax id the provider says the credential belongs to. Published because `identity`
    #: compares it with the CUIT the company entered — see `RevalidarDatosFiscales`. It is
    #: not a secret: it is printed on every document the company issues.
    cuit_declarado: str | None = None


def _exigir_lectura(rol: RolUsuario) -> None:
    """HU-E2-05 names Administrador *and* Operador as its actors."""
    if rol not in ROLES_QUE_PUEDEN_LEER:
        raise PermisoDenegado("Se requiere rol Administrador u Operador para ver las integraciones")


def exigir_administrador(rol: RolUsuario) -> None:
    """Public because `CompletarAutorizacion` checks it too, and before it burns a `state`."""
    if rol is not RolUsuario.ADMINISTRADOR:
        raise PermisoDenegado("Solo un Administrador puede conectar una integracion")


def _ambiente_del_despliegue(es_produccion: bool) -> Ambiente:
    """Decision D-b: derived from `APP_ENV`, never from the request.

    A dropdown here would let a company sit in homologación believing it is invoicing,
    or issue a real irreversible document from a deployment meant for testing.
    """
    return Ambiente.PRODUCCION if es_produccion else Ambiente.HOMOLOGACION


class ListarIntegraciones:
    """The screen's initial read: the catalogue, joined against whatever rows exist.

    Returns one entry per system on PAN-CFG-INT even with an empty table, because the
    four cards come from `SISTEMAS_EN_PANTALLA` and not from the database — see the
    aggregate's module docstring.
    """

    def __init__(self, *, integraciones: PortRepositorioIntegraciones) -> None:
        self._integraciones = integraciones

    async def ejecutar(self, *, empresa_id: EmpresaId, rol: RolUsuario) -> list[VistaDeIntegracion]:
        _exigir_lectura(rol)
        configuradas = {c.sistema: c for c in await self._integraciones.listar(empresa_id)}
        return [_vista(sistema, configuradas.get(sistema)) for sistema in SISTEMAS_EN_PANTALLA]


class VerificarConexiones:
    """HU-E2-05: check every configured integration live and report what came back.

    **Decision D-a — synchronous and in parallel, with a per-provider timeout.** The four
    checks run concurrently, so the response takes as long as the slowest one rather than
    the sum, and a provider that hangs is cut at `timeout_segundos` instead of holding the
    request open.

    **One provider never breaks the answer.** A timeout, an unreachable host or an adapter
    that raises turns into `NO_CONECTADO` with a detail for *that* integration; the other
    three are reported normally. That is the whole reason this does not simply await four
    calls in a row.
    """

    def __init__(
        self,
        *,
        integraciones: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        adaptadores: PortRegistroDeAdaptadores,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        timeout_segundos: int,
    ) -> None:
        self._integraciones = integraciones
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._publicador = publicador
        self._reloj = reloj
        self._timeout = timeout_segundos

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        usuario_id: UsuarioId | None = None,
        direccion_ip: str | None = None,
    ) -> list[VistaDeIntegracion]:
        _exigir_lectura(rol)
        configuradas = await self._integraciones.listar(empresa_id)
        ahora = self._reloj.ahora()

        # gather rather than a loop of awaits: the response takes as long as the slowest
        # provider instead of the sum, and each one is cut at its own timeout.
        resultados = await asyncio.gather(
            *(self._verificar_una(c) for c in configuradas),
        )

        for configuracion, resultado in zip(configuradas, resultados, strict=True):
            cambio = aplicar_resultado(configuracion, resultado, ahora)
            await self._integraciones.guardar(configuracion)
            if cambio is not None:
                await self._publicador.publicar(
                    evento_auditable(
                        cambio,
                        empresa_id=empresa_id,
                        usuario_id=usuario_id,
                        direccion_ip=direccion_ip,
                        ahora=ahora,
                    )
                )

        por_sistema = {c.sistema: c for c in configuradas}
        return [_vista(sistema, por_sistema.get(sistema)) for sistema in SISTEMAS_EN_PANTALLA]

    async def _verificar_una(
        self, configuracion: ConfiguracionDeIntegracion
    ) -> ResultadoDeVerificacion | SinVeredicto:
        return await verificar_con_timeout(
            configuracion=configuracion,
            adaptadores=self._adaptadores,
            cifrado=self._cifrado,
            timeout_segundos=self._timeout,
        )


class ConectarIntegracion:
    """Store a credential once the provider accepted it.

    The order is the rule of HU-E2-01 RN-02 and HU-E2-02 RN-02: validate against the
    external service **first**, encrypt and persist **after**. Invalid credentials leave
    the integration not connected and nothing is written.

    Idempotent by `(empresa_id, sistema)`: connecting twice replaces the credential rather
    than creating a second row, matching the unique index the migration declares.
    """

    def __init__(
        self,
        *,
        integraciones: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        adaptadores: PortRegistroDeAdaptadores,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        es_produccion: bool,
    ) -> None:
        self._integraciones = integraciones
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._publicador = publicador
        self._reloj = reloj
        self._es_produccion = es_produccion

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        sistema: SistemaExterno,
        contenido: bytes,
        parametros: dict[str, Any] | None = None,
        efimeros: dict[str, str] | None = None,
        usuario_id: UsuarioId | None = None,
        direccion_ip: str | None = None,
    ) -> VistaDeIntegracion:
        exigir_administrador(rol)
        conector = self._adaptadores.conector(sistema)
        if conector is None:
            raise SistemaNoConfigurable(
                f"La conexion de {sistema.value} no forma parte de este epico"
            )

        material = MaterialDeConexion(
            contenido=contenido,
            parametros=dict(parametros or {}),
            efimeros=dict(efimeros or {}),
        )
        try:
            respuesta = await conector.conectar(material)
        except ProveedorNoDisponible as exc:
            raise ConexionRechazada(f"No se pudo validar contra {sistema.value}: {exc}") from exc

        ahora = self._reloj.ahora()
        ambiente = _ambiente_del_despliegue(self._es_produccion)
        credencial = self._cifrado.cifrar(respuesta.credencial)
        # What the caller supplied plus what the provider added — Meta answers with the
        # phone number's display name and the account it belongs to. `efimeros` is
        # deliberately absent: it is what must not survive the handshake.
        parametros_finales = {**material.parametros, **respuesta.parametros}

        existente = await self._integraciones.buscar(empresa_id, sistema)
        if existente is None:
            configuracion = ConfiguracionDeIntegracion.registrar(
                id=uuid4(),
                empresa_id=empresa_id,
                sistema=sistema,
                credencial=credencial,
                ambiente=ambiente,
                ahora=ahora,
                estado=respuesta.estado,
                detalle=respuesta.detalle,
                parametros=parametros_finales,
            )
            await self._integraciones.agregar(configuracion)
            # A first connection is itself the transition worth recording: there was no
            # row, so `registrar_verificacion` had no previous state to compare against.
            cambio: CambioDeEstado | None = CambioDeEstado(
                sistema=sistema,
                anterior=EstadoDeConexion.NO_CONECTADO,
                nuevo=configuracion.estado,
                detalle=configuracion.detalle_estado,
            )
        else:
            configuracion = existente
            cambio = configuracion.reconectar(
                credencial=credencial,
                ambiente=ambiente,
                ahora=ahora,
                estado=respuesta.estado,
                detalle=respuesta.detalle,
                parametros=parametros_finales,
            )
            await self._integraciones.guardar(configuracion)

        if cambio is not None:
            await self._publicador.publicar(
                evento_auditable(
                    cambio,
                    empresa_id=empresa_id,
                    usuario_id=usuario_id,
                    direccion_ip=direccion_ip,
                    ahora=ahora,
                )
            )
        return _vista(sistema, configuracion)


def evento_auditable(
    cambio: CambioDeEstado,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    direccion_ip: str | None,
    ahora: datetime,
) -> EventoAuditable:
    """Turn a state transition into the audit row HS-T5 stores.

    Built here and not in the aggregate for the reason `domain/eventos.py` explains: only
    the use case knows who asked. `usuario_id=None` is the system acting, which is what a
    scheduled re-verification will be once a real provider exists.
    """
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=ahora,
        modulo=Modulo.INTEGRATIONS,
        accion=cambio.descripcion,
        entidad_afectada=f"ConfiguracionDeIntegracion:{cambio.sistema.value}",
        resultado=Resultado.COMPLETADO,
        usuario_id=usuario_id,
        direccion_ip=direccion_ip,
    )


def _vista(
    sistema: SistemaExterno, configuracion: ConfiguracionDeIntegracion | None
) -> VistaDeIntegracion:
    if configuracion is None:
        return VistaDeIntegracion(
            sistema=sistema,
            estado=EstadoDeConexion.NO_CONECTADO,
            detalle=None,
            ambiente=None,
            verificado_en=None,
            configurada=False,
        )
    return VistaDeIntegracion(
        sistema=sistema,
        estado=configuracion.estado,
        detalle=configuracion.detalle_estado,
        ambiente=configuracion.ambiente,
        verificado_en=configuracion.verificado_en,
        configurada=True,
        etiqueta=_parametro(configuracion, CLAVE_ETIQUETA),
        cuit_declarado=_parametro(configuracion, CLAVE_CUIT),
    )


def _parametro(configuracion: ConfiguracionDeIntegracion, clave: str) -> str | None:
    """A named parameter, or nothing. `parametros` is free-form, so its types are too."""
    valor = configuracion.parametros.get(clave)
    return valor if isinstance(valor, str) and valor else None
