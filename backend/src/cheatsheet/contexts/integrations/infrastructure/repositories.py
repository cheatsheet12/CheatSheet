"""PostgreSQL adapter for `PortRepositorioIntegraciones`.

Nothing here needs the `SECURITY DEFINER` escape that identity's login lookup needs: every
query in this context is scoped to a company that the caller is already authenticated
into, so Row-Level Security on `empresa_id` is exactly the barrier that should apply.
"""

from __future__ import annotations

from sqlalchemy import select
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
