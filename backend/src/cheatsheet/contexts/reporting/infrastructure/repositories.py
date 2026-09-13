"""Adaptadores PostgreSQL de los tres repositorios de `reporting`.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue
una dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**La excepción está al final del archivo, y es a propósito.** `empresa_de_token_contable` y
`empresas_con_paquete_activo` corren **fuera** de RLS, contra funciones `SECURITY DEFINER`, por
la misma razón que las ocho anteriores del sistema: la pregunta que contestan no es de ninguna
empresa. La primera es la más delicada de las nueve —traduce un enlace de correo en un
inquilino—, y por eso devuelve un id y nada más: quien decide si el acceso vale es el caso de
uso, mirando `revocado` y `vencimiento` ya dentro de la sesión de esa empresa.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.reporting.domain.paquete import (
    ConfiguracionDelPaquete,
    ContenidoDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import (
    EstadoReporte,
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.contexts.reporting.infrastructure.models import (
    ConfiguracionDePaqueteORM,
    PaqueteContableORM,
    ReporteORM,
    TokenDeAccesoContableORM,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


def _a_reporte(fila: ReporteORM) -> Reporte:
    return Reporte(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        usuario_id=UsuarioId(fila.usuario_id),
        tipo=TipoReporte(fila.tipo),
        formato=FormatoReporte(fila.formato),
        periodo=Periodo(desde=fila.periodo_desde, hasta=fila.periodo_hasta),
        estado=EstadoReporte(fila.estado),
        filtros=dict(fila.filtros),
        referencia_archivo=fila.referencia_archivo,
        created_at=fila.created_at,
    )


class RepositorioReportePostgres:
    """`PortRepositorioReportes`. Sin `eliminar`: el historial es la respuesta a «qué le mandé
    a mi contador y cuándo»."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, reporte: Reporte) -> None:
        self._sesion.add(
            ReporteORM(
                id=reporte.id,
                empresa_id=reporte.empresa_id,
                usuario_id=reporte.usuario_id,
                tipo=reporte.tipo.value,
                formato=reporte.formato.value,
                periodo_desde=reporte.periodo.desde,
                periodo_hasta=reporte.periodo.hasta,
                estado=reporte.estado.value,
                filtros=reporte.filtros,
                referencia_archivo=reporte.referencia_archivo,
                created_at=reporte.created_at or datetime.now().astimezone(),
            )
        )
        await self._sesion.flush()

    async def guardar(self, reporte: Reporte) -> None:
        fila = await self._sesion.get(ReporteORM, reporte.id)
        if fila is None:
            raise LookupError(f"El reporte {reporte.id} no existe para esta empresa")
        fila.estado = reporte.estado.value
        fila.referencia_archivo = reporte.referencia_archivo
        fila.filtros = dict(reporte.filtros)
        await self._sesion.flush()

    async def buscar_por_id(self, reporte_id: UUID) -> Reporte | None:
        fila = await self._sesion.get(ReporteORM, reporte_id)
        return _a_reporte(fila) if fila is not None else None

    async def listar(self, *, limite: int = 50) -> list[Reporte]:
        consulta = select(ReporteORM).order_by(ReporteORM.created_at.desc()).limit(limite)
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_reporte(fila) for fila in filas]


def _a_paquete(fila: PaqueteContableORM) -> PaqueteContable:
    return PaqueteContable(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        periodo_anio=fila.periodo_anio,
        periodo_mes=fila.periodo_mes,
        totales_por_tipo={
            clave: dict(valor) for clave, valor in dict(fila.totales_por_tipo).items()
        },
        referencia_archivo=fila.referencia_archivo,
        created_at=fila.created_at,
    )


def _a_configuracion(fila: ConfiguracionDePaqueteORM) -> ConfiguracionDelPaquete:
    return ConfiguracionDelPaquete(
        empresa_id=EmpresaId(fila.empresa_id),
        activo=fila.activo,
        dia_de_envio=fila.dia_de_envio,
        formatos=frozenset(fila.formatos),
        contenido=frozenset(ContenidoDelPaquete(uno) for uno in fila.contenido),
        email_contador=fila.email_contador,
        updated_at=fila.updated_at,
    )


class RepositorioPaquetePostgres:
    """`PortRepositorioPaquetes`: los paquetes de una empresa y la configuración de su envío.

    Las dos cosas en el mismo repositorio porque se leen juntas —PAN-REP-02 muestra el estado
    del envío arriba y los paquetes abajo— y porque partirlas dejaría dos adaptadores con una
    sola tabla cada uno y ninguna operación propia.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, paquete: PaqueteContable) -> None:
        self._sesion.add(
            PaqueteContableORM(
                id=paquete.id,
                empresa_id=paquete.empresa_id,
                periodo_anio=paquete.periodo_anio,
                periodo_mes=paquete.periodo_mes,
                totales_por_tipo=paquete.totales_por_tipo,
                referencia_archivo=paquete.referencia_archivo,
                created_at=paquete.created_at or datetime.now().astimezone(),
            )
        )
        await self._sesion.flush()

    async def guardar(self, paquete: PaqueteContable) -> None:
        fila = await self._sesion.get(PaqueteContableORM, paquete.id)
        if fila is None:
            raise LookupError(f"El paquete {paquete.id} no existe para esta empresa")
        fila.totales_por_tipo = dict(paquete.totales_por_tipo)
        fila.referencia_archivo = paquete.referencia_archivo
        await self._sesion.flush()

    async def buscar_por_id(self, paquete_id: UUID) -> PaqueteContable | None:
        fila = await self._sesion.get(PaqueteContableORM, paquete_id)
        return _a_paquete(fila) if fila is not None else None

    async def del_periodo(self, anio: int, mes: int) -> PaqueteContable | None:
        consulta = select(PaqueteContableORM).where(
            PaqueteContableORM.periodo_anio == anio, PaqueteContableORM.periodo_mes == mes
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_paquete(fila) if fila is not None else None

    async def listar(self, *, limite: int = 24) -> list[PaqueteContable]:
        consulta = (
            select(PaqueteContableORM)
            .order_by(PaqueteContableORM.periodo_anio.desc(), PaqueteContableORM.periodo_mes.desc())
            .limit(limite)
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_paquete(fila) for fila in filas]

    async def configuracion(self) -> ConfiguracionDelPaquete | None:
        consulta = select(ConfiguracionDePaqueteORM).limit(1)
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_configuracion(fila) if fila is not None else None

    async def guardar_configuracion(self, configuracion: ConfiguracionDelPaquete) -> None:
        """Crea la fila o la actualiza. Una empresa, una configuración.

        `merge` sobre la clave primaria y no un `INSERT ... ON CONFLICT`: la clave es
        `empresa_id`, y la sesión ya está acotada a esa empresa, así que el conflicto que
        habría que resolver es siempre con la propia fila.
        """
        fila = await self._sesion.get(ConfiguracionDePaqueteORM, configuracion.empresa_id)
        momento = configuracion.updated_at or datetime.now().astimezone()
        if fila is None:
            self._sesion.add(
                ConfiguracionDePaqueteORM(
                    empresa_id=configuracion.empresa_id,
                    activo=configuracion.activo,
                    dia_de_envio=configuracion.dia_de_envio,
                    formatos=sorted(configuracion.formatos),
                    contenido=sorted(uno.value for uno in configuracion.contenido),
                    email_contador=configuracion.email_contador,
                    updated_at=momento,
                )
            )
        else:
            fila.activo = configuracion.activo
            fila.dia_de_envio = configuracion.dia_de_envio
            fila.formatos = sorted(configuracion.formatos)
            fila.contenido = sorted(uno.value for uno in configuracion.contenido)
            fila.email_contador = configuracion.email_contador
            fila.updated_at = momento
        await self._sesion.flush()


def _a_token(fila: TokenDeAccesoContableORM) -> TokenDeAccesoContable:
    return TokenDeAccesoContable(
        id=fila.id,
        paquete_id=fila.paquete_id,
        empresa_id=EmpresaId(fila.empresa_id),
        valor_hash=fila.valor_hash,
        email_contador=fila.email_contador,
        vencimiento=fila.vencimiento,
        accesos=fila.accesos,
        revocado=fila.revocado,
        created_at=fila.created_at,
    )


class RepositorioTokenContablePostgres:
    """`PortRepositorioTokens`. El enlace del contador, siempre por su hash."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, token: TokenDeAccesoContable) -> None:
        self._sesion.add(
            TokenDeAccesoContableORM(
                id=token.id,
                paquete_id=token.paquete_id,
                empresa_id=token.empresa_id,
                valor_hash=token.valor_hash,
                email_contador=token.email_contador,
                vencimiento=token.vencimiento,
                accesos=token.accesos,
                revocado=token.revocado,
                created_at=token.created_at or datetime.now().astimezone(),
            )
        )
        await self._sesion.flush()

    async def guardar(self, token: TokenDeAccesoContable) -> None:
        fila = await self._sesion.get(TokenDeAccesoContableORM, token.id)
        if fila is None:
            raise LookupError(f"El token {token.id} no existe para esta empresa")
        fila.accesos = token.accesos
        fila.revocado = token.revocado
        await self._sesion.flush()

    async def activo_de_la_empresa(self) -> TokenDeAccesoContable | None:
        """El más reciente sin revocar. RN-04 dice **uno a la vez**, y esto es lo que lo mide.

        No filtra por vencimiento: un enlace vencido sigue siendo el último que se emitió, y la
        pantalla necesita poder decir «venció» en vez de «nunca invitaste a nadie».
        """
        consulta = (
            select(TokenDeAccesoContableORM)
            .where(TokenDeAccesoContableORM.revocado.is_(False))
            .order_by(TokenDeAccesoContableORM.created_at.desc())
            .limit(1)
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_token(fila) if fila is not None else None

    async def buscar_por_hash(self, valor_hash: str) -> TokenDeAccesoContable | None:
        consulta = select(TokenDeAccesoContableORM).where(
            TokenDeAccesoContableORM.valor_hash == valor_hash
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_token(fila) if fila is not None else None


async def empresa_de_token_contable(sesion: AsyncSession, valor_hash: str) -> EmpresaId | None:
    """De qué empresa es un enlace de contador. **Corre fuera de RLS.**

    La novena función `SECURITY DEFINER` del sistema y la más angosta de todas: recibe un
    digesto y devuelve un id. No dice si el token está vigente, ni de qué paquete es, ni a qué
    correo se mandó — eso se lee después, ya adentro de la sesión de esa empresa, donde la
    política acota todo lo demás.

    La sesión que se le pasa tiene que ser una **sin** empresa (`sesion_sin_empresa`): es la
    misma trampa que documenta `identity/infrastructure/resolucion.py` — resolver primero, en
    una sesión que no puede escribir nada, y recién después abrir la unidad de trabajo real.
    """
    resultado = await sesion.execute(
        text("SELECT empresa_de_token_contable(:hash)"), {"hash": valor_hash}
    )
    valor = resultado.scalar()
    return EmpresaId(valor) if valor is not None else None


async def empresas_con_paquete_activo(sesion: AsyncSession, dia: int) -> list[EmpresaId]:
    """Qué empresas tienen el envío automático configurado para hoy (HU-E10-04 RN-02).

    También fuera de RLS, y también devolviendo ids y nada más. El día viaja como parámetro en
    vez de que la función lo saque de `now()`: un barrido que se corre a mano para reponer un
    envío perdido tiene que poder pedir el día que corresponde y no el de hoy.
    """
    filas = await sesion.execute(
        text("SELECT empresa_id FROM empresas_con_paquete_activo(:dia)"), {"dia": dia}
    )
    return [EmpresaId(fila[0]) for fila in filas]


__all__ = [
    "RepositorioPaquetePostgres",
    "RepositorioReportePostgres",
    "RepositorioTokenContablePostgres",
    "empresa_de_token_contable",
    "empresas_con_paquete_activo",
]
