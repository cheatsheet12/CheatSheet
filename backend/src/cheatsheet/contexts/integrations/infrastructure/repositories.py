"""PostgreSQL adapter for `PortRepositorioIntegraciones`, plus one deliberate exception.

Every query of the repository class is scoped to a company the caller is already
authenticated into, so Row-Level Security on `empresa_id` is exactly the barrier that
should apply — no escape needed.

The exception is `empresas_con_integracion_pendiente` at the bottom, which the scheduled
poll needs and which is the only thing here that crosses tenants. It is a `SECURITY
DEFINER` function and it returns nothing but company ids; the reasoning is with it.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.models import ConfiguracionDeIntegracionORM
from cheatsheet.shared.empresa import EmpresaId


def _a_dominio(fila: ConfiguracionDeIntegracionORM) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        sistema=SistemaExterno(fila.sistema),
        credencial=CredencialCifrada(
            contenido=fila.credencial_contenido_cifrado,
            algoritmo=fila.credencial_algoritmo,
        ),
        ambiente=Ambiente(fila.ambiente),
        estado=EstadoDeConexion(fila.estado),
        detalle_estado=fila.detalle_estado,
        verificado_en=fila.verificado_en,
        pendiente_desde=fila.pendiente_desde,
        parametros=dict(fila.parametros or {}),
    )


def _volcar(configuracion: ConfiguracionDeIntegracion, fila: ConfiguracionDeIntegracionORM) -> None:
    fila.credencial_contenido_cifrado = configuracion.credencial.contenido
    fila.credencial_algoritmo = configuracion.credencial.algoritmo
    fila.parametros = dict(configuracion.parametros)
    fila.ambiente = configuracion.ambiente.value
    fila.estado = configuracion.estado.value
    fila.detalle_estado = configuracion.detalle_estado
    fila.verificado_en = configuracion.verificado_en
    fila.pendiente_desde = configuracion.pendiente_desde


class RepositorioIntegracionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        fila = ConfiguracionDeIntegracionORM(
            id=configuracion.id,
            empresa_id=configuracion.empresa_id,
            sistema=configuracion.sistema.value,
            credencial_contenido_cifrado=configuracion.credencial.contenido,
            credencial_algoritmo=configuracion.credencial.algoritmo,
            parametros=dict(configuracion.parametros),
            ambiente=configuracion.ambiente.value,
            estado=configuracion.estado.value,
            detalle_estado=configuracion.detalle_estado,
            verificado_en=configuracion.verificado_en,
            pendiente_desde=configuracion.pendiente_desde,
        )
        self._sesion.add(fila)
        await self._sesion.flush()

    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        fila = await self._sesion.get(ConfiguracionDeIntegracionORM, configuracion.id)
        if fila is None:  # pragma: no cover — the aggregate was loaded from this session
            return
        _volcar(configuracion, fila)
        await self._sesion.flush()

    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None:
        consulta = select(ConfiguracionDeIntegracionORM).where(
            ConfiguracionDeIntegracionORM.empresa_id == empresa_id,
            ConfiguracionDeIntegracionORM.sistema == sistema.value,
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None

    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        consulta = (
            select(ConfiguracionDeIntegracionORM)
            .where(ConfiguracionDeIntegracionORM.empresa_id == empresa_id)
            .order_by(ConfiguracionDeIntegracionORM.sistema)
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def listar_pendientes(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        """The rows waiting on an asynchronous provider. Today, only WhatsApp reaches this.

        Filtered in SQL rather than in Python because the poll runs for every company on a
        schedule: reading every integration of every company every 30 minutes to discard
        almost all of them is work that grows with the customer base and buys nothing.
        """
        consulta = (
            select(ConfiguracionDeIntegracionORM)
            .where(
                ConfiguracionDeIntegracionORM.empresa_id == empresa_id,
                ConfiguracionDeIntegracionORM.estado == EstadoDeConexion.PENDIENTE.value,
            )
            .order_by(ConfiguracionDeIntegracionORM.sistema)
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_dominio(fila) for fila in filas]


async def empresas_con_integracion_pendiente(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have something waiting. **The only cross-tenant read in this context.**

    Beat runs with no company: `app.current_empresa` is unset and the RLS policy on the
    table correctly shows it nothing. That is the same problem sign-in has — discovering
    which company something belongs to before knowing the company — and it gets the same
    answer the identity migrations already use four times: a `SECURITY DEFINER` function,
    granted to `cheatsheet_app` and revoked from `PUBLIC`.

    **It returns company ids and nothing else.** A function that steps around Row-Level
    Security is a hole in the only multi-tenant barrier this system has, so it is kept
    narrow enough that what comes through it is useless on its own. The per-company task
    this feeds then opens an ordinary session, with RLS applying normally.
    """
    filas = await sesion.execute(
        text("SELECT empresa_id FROM empresas_con_integracion_pendiente()")
    )
    return [EmpresaId(valor) for (valor,) in filas.all()]
