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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.errors import CuentaDeWhatsAppEnUso
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.ticket import (
    ServicioDeArca,
    TicketDeAcceso,
    TicketDePlataforma,
)
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.models import (
    ConfiguracionDeIntegracionORM,
    TicketDeAccesoORM,
    TicketDePlataformaORM,
)
from cheatsheet.shared.empresa import EmpresaId

#: The unique index of migration 0036: one WhatsApp business account, one empresa.
INDICE_WABA_UNICO = "uq_integracion_waba"
MENSAJE_CUENTA_EN_USO = (
    "Esa cuenta de WhatsApp Business ya está vinculada a otra empresa. "
    "Verificá el ID de la cuenta que pegaste."
)


async def _volcar_a_la_base(sesion: AsyncSession) -> None:
    """Flush, turning only the WABA index violation into a domain error (409, never a 500).

    By name, as the payments repository does for its own index: any other violation is a
    real defect and must stay one.
    """
    try:
        await sesion.flush()
    except IntegrityError as exc:
        if INDICE_WABA_UNICO not in str(exc.orig):
            raise
        raise CuentaDeWhatsAppEnUso(MENSAJE_CUENTA_EN_USO) from exc


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
        await _volcar_a_la_base(self._sesion)

    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        fila = await self._sesion.get(ConfiguracionDeIntegracionORM, configuracion.id)
        if fila is None:  # pragma: no cover — the aggregate was loaded from this session
            return
        _volcar(configuracion, fila)
        await _volcar_a_la_base(self._sesion)

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


class RepositorioTicketsSQL:
    """Implements `PortRepositorioTickets`.

    Company-scoped like everything else in this context, so Row-Level Security is the
    barrier — which matters more here than elsewhere: a ticket is a live session, and one
    company reading another's would be speaking to ARCA as that company.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, ticket: TicketDeAcceso) -> None:
        self._sesion.add(
            TicketDeAccesoORM(
                id=ticket.id,
                empresa_id=ticket.empresa_id,
                servicio=ticket.servicio.value,
                contenido_cifrado=ticket.contenido.contenido,
                algoritmo=ticket.contenido.algoritmo,
                expira_en=ticket.expira_en,
            )
        )
        await self._sesion.flush()

    async def guardar(self, ticket: TicketDeAcceso) -> None:
        fila = await self._sesion.get(TicketDeAccesoORM, ticket.id)
        if fila is None:  # pragma: no cover — loaded from this same session
            return
        fila.contenido_cifrado = ticket.contenido.contenido
        fila.algoritmo = ticket.contenido.algoritmo
        fila.expira_en = ticket.expira_en
        await self._sesion.flush()

    async def buscar(
        self, empresa_id: EmpresaId, servicio: ServicioDeArca
    ) -> TicketDeAcceso | None:
        consulta = select(TicketDeAccesoORM).where(
            TicketDeAccesoORM.empresa_id == empresa_id,
            TicketDeAccesoORM.servicio == servicio.value,
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if fila is None:
            return None
        return TicketDeAcceso(
            id=fila.id,
            empresa_id=EmpresaId(fila.empresa_id),
            servicio=ServicioDeArca(fila.servicio),
            contenido=CredencialCifrada(contenido=fila.contenido_cifrado, algoritmo=fila.algoritmo),
            expira_en=fila.expira_en,
        )


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


async def empresas_con_integracion_de_arca(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have ARCA connected. The second cross-tenant read.

    Its own function rather than a parameter on the pending one, for the reason the
    migration states: a `SECURITY DEFINER` function is a hole in the multi-tenant barrier,
    and one that takes an argument is a hole whose shape the caller chooses.

    Feeds the daily expiry sweep. Returns company ids and nothing else — not the
    certificate, not its expiry date, not the state.
    """
    filas = await sesion.execute(text("SELECT empresa_id FROM empresas_con_integracion_de_arca()"))
    return [EmpresaId(valor) for (valor,) in filas.all()]


async def empresas_con_whatsapp_conectado(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have WhatsApp connected, with a WABA. The fourth cross-tenant read.

    Feeds the reconciliation of WhatsApp templates (`plantillas-de-whatsapp-en-meta`). Its own
    function, for the reason migration 0006 states: one question, no arguments, company ids and
    nothing else — not the token, not the WABA id.
    """
    filas = await sesion.execute(text("SELECT empresa_id FROM empresas_con_whatsapp_conectado()"))
    return [EmpresaId(valor) for (valor,) in filas.all()]


async def empresas_de_la_cuenta_de_whatsapp(sesion: AsyncSession, waba_id: str) -> list[EmpresaId]:
    """The company that owns a WABA id: the template webhook arrives at the app, not a company.

    Meta does not allow a callback override for template status updates, so the event is routed
    by the `entry[].id` it carries (the WABA id) and never by URL. It returns **only** company ids,
    and **a list**: two companies claiming the same WABA is a configuration error the caller must
    refuse to guess about.
    """
    filas = await sesion.execute(
        text("SELECT empresa_id FROM empresa_de_la_cuenta_de_whatsapp(:waba_id)"),
        {"waba_id": waba_id},
    )
    return [EmpresaId(valor) for (valor,) in filas.all()]


async def empresas_con_integracion_de_mercadopago(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have MercadoPago connected. The third cross-tenant read.

    Its own function rather than a parameter on either of the other two, for the reason
    migration 0006 states: a `SECURITY DEFINER` function is a hole in the multi-tenant
    barrier, and one that takes an argument is a hole whose shape the caller chooses.

    Feeds the daily renewal. Returns company ids and nothing else — not the tokens, not
    the expiry, not the state.
    """
    filas = await sesion.execute(
        text("SELECT empresa_id FROM empresas_con_integracion_de_mercadopago()")
    )
    return [EmpresaId(valor) for (valor,) in filas.all()]


class RepositorioTicketsDePlataformaSQL:
    """Implements `PortRepositorioTicketsDePlataforma` (ADR-0014).

    `buscar_para_renovar` takes a row lock (`FOR UPDATE`) so two requests minting at once
    queue behind each other instead of both asking WSAA, which would hand a ticket to one
    and `coe.alreadyAuthenticated` to the other.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def buscar_para_renovar(self, servicio: ServicioDeArca) -> TicketDePlataforma | None:
        consulta = (
            select(TicketDePlataformaORM)
            .where(TicketDePlataformaORM.servicio == servicio.value)
            .with_for_update()
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if fila is None:
            return None
        return TicketDePlataforma(
            servicio=ServicioDeArca(fila.servicio),
            contenido=CredencialCifrada(contenido=fila.contenido_cifrado, algoritmo=fila.algoritmo),
            expira_en=fila.expira_en,
        )

    async def guardar(self, ticket: TicketDePlataforma) -> None:
        fila = await self._sesion.get(TicketDePlataformaORM, ticket.servicio.value)
        if fila is None:
            self._sesion.add(
                TicketDePlataformaORM(
                    servicio=ticket.servicio.value,
                    contenido_cifrado=ticket.contenido.contenido,
                    algoritmo=ticket.contenido.algoritmo,
                    expira_en=ticket.expira_en,
                )
            )
        else:
            fila.contenido_cifrado = ticket.contenido.contenido
            fila.algoritmo = ticket.contenido.algoritmo
            fila.expira_en = ticket.expira_en
        await self._sesion.flush()
