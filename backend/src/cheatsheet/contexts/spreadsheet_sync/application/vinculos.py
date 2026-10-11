"""The use cases of HU-E2-04 — getting a spreadsheet into the system.

Three ways in, one aggregate out. The OAuth2 pair (`IniciarVinculacionConGoogle` and
`ConfirmarVinculacionConGoogle`) is split because the user leaves for Google in between:
the first builds the URL and remembers nothing but a `state`, the second is what the
callback lands on.

**The role check lives here and not only in the router**, for the reason
`identity/application/autorizacion.py` states and PRU-09 proved: the rule has to travel
with the operation. HU-E2-04's actor is the Administrador; a spreadsheet link decides
where the company's whole customer catalogue comes from, and an Operador redirecting it is
not a smaller version of the same problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
    VinculoInexistente,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    PortAlmacenamientoDeArchivos,
    PortProveedorDePlanilla,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    MENSAJE_SIN_PERMISOS,
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
    validar_extension,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import OperacionNoPermitida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: Content type stored alongside every uploaded workbook. Not sniffed from the bytes: R2
#: never serves these to a browser, only back to our own parser, so the value is metadata
#: for a human reading the bucket and nothing depends on it being exact.
TIPO_DE_CONTENIDO = "application/octet-stream"


def _exigir_administrador(rol: RolUsuario, motivo: str) -> None:
    """The guard, restated for this context rather than imported from `identity`.

    Rule R3 forbids reaching into another context's application layer for this, and it is
    right to: a permission check is not a service another context provides, it is a
    statement each context makes about its own operations.
    """
    if rol is not RolUsuario.ADMINISTRADOR:
        raise OperacionNoPermitida(motivo)


MOTIVO_VINCULAR = "Solo un Administrador puede vincular una planilla"
MOTIVO_DESVINCULAR = "Solo un Administrador puede desvincular una planilla"


@dataclass(frozen=True, slots=True)
class AutorizacionPendiente:
    """What the panel needs to send the user to Google (RN-01)."""

    url: str
    estado: str


class IniciarVinculacionConGoogle:
    """RN-01 — build the consent URL for one file, not for the whole Drive.

    The `state` is generated here and handed back so the caller can stash it; the callback
    compares it. Without that, anybody who can make the user's browser hit the callback can
    attach a spreadsheet of their choosing to that user's company.
    """

    def __init__(self, proveedor: PortProveedorDePlanilla) -> None:
        self._proveedor = proveedor

    def ejecutar(self, *, rol: RolUsuario) -> AutorizacionPendiente:
        _exigir_administrador(rol, MOTIVO_VINCULAR)
        estado = uuid4().hex
        return AutorizacionPendiente(
            url=self._proveedor.url_de_autorizacion(estado=estado), estado=estado
        )


class ConfirmarVinculacionConGoogle:
    """RN-01 and RN-02 — the callback: exchange the code, read the sheet, save the link.

    A declined consent is not an error to log and move past: RN-01's acceptance criterion
    says the system shows a specific message and **does not create the link**. The order
    here is what makes that true — the exchange happens before anything is persisted.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        proveedor: PortProveedorDePlanilla,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._vinculos = vinculos
        self._proveedor = proveedor
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        codigo: str,
        identificador_documento: str,
        direccion: DireccionSync,
        ahora: datetime,
        configuracion_integracion_id: UUID | None = None,
    ) -> VinculoDePlanilla:
        _exigir_administrador(rol, MOTIVO_VINCULAR)

        if not codigo.strip():
            raise PermisosDePlanillaInsuficientes(MENSAJE_SIN_PERMISOS)

        token = await self._proveedor.canjear_codigo(codigo)
        documento = await self._proveedor.describir_documento(
            token=token, identificador=identificador_documento
        )

        vinculo = VinculoDePlanilla(
            id=uuid4(),
            empresa_id=empresa_id,
            proveedor=ProveedorPlanilla.GOOGLE_SHEETS,
            direccion=direccion,
            # The first sheet of the workbook. HU-E2-04 does not offer a chooser and the
            # prototype does not draw one; when a story asks for it, this is the line.
            hoja_empresa=documento.hojas[0].nombre,
            identificador_externo=documento.identificador_externo,
            configuracion_integracion_id=configuracion_integracion_id,
            created_at=ahora,
            updated_at=ahora,
        )
        await self._vinculos.agregar(vinculo)
        await self._publicar(
            vinculo, usuario_id=usuario_id, ahora=ahora, accion="vincular_planilla"
        )
        return vinculo

    async def _publicar(
        self, vinculo: VinculoDePlanilla, *, usuario_id: UsuarioId, ahora: datetime, accion: str
    ) -> None:
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=vinculo.empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion=accion,
                entidad_afectada=f"VinculoDePlanilla:{vinculo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )


class SubirPlanilla:
    """HU-E3-03's entry path, and D10's `ARCHIVO` link.

    The two validations run **before** the bytes reach R2. Storing first and validating
    after would leave a 30 MB object in the bucket for every rejected upload, and nothing
    would ever delete it.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        almacenamiento: PortAlmacenamientoDeArchivos,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._vinculos = vinculos
        self._almacenamiento = almacenamiento
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        nombre_de_archivo: str,
        contenido: bytes,
        ahora: datetime,
    ) -> VinculoDePlanilla:
        _exigir_administrador(rol, MOTIVO_VINCULAR)

        nombre = validar_extension(nombre_de_archivo)
        # `ReferenciaDeArchivo` enforces the size limit, so it is built before the upload
        # and the check cannot be skipped by a caller that forgets it.
        vinculo_id = uuid4()
        referencia = ReferenciaDeArchivo(
            # Keyed by company and link, never by the company's own file name: two
            # customers uploading `clientes.xlsx` must not collide, and a name from a
            # spreadsheet is not something to hand an object store verbatim.
            clave=f"planillas/{empresa_id}/{vinculo_id}{_extension(nombre)}",
            nombre_original=nombre,
            tamano_bytes=len(contenido),
        )

        await self._almacenamiento.guardar(
            clave=referencia.clave, contenido=contenido, tipo_de_contenido=TIPO_DE_CONTENIDO
        )

        vinculo = VinculoDePlanilla(
            id=vinculo_id,
            empresa_id=empresa_id,
            proveedor=ProveedorPlanilla.ARCHIVO,
            direccion=DireccionSync.SOLO_LECTURA,
            # A workbook uploaded through the panel has one sheet as far as this unit is
            # concerned; which one is read is decided when it is parsed, in unit 4.
            hoja_empresa=nombre,
            archivo=referencia,
            created_at=ahora,
            updated_at=ahora,
        )
        await self._vinculos.agregar(vinculo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="subir_planilla",
                # The name, not the content. The rows are full of CUITs and phone numbers.
                entidad_afectada=f"VinculoDePlanilla:{vinculo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return vinculo


class ListarVinculos:
    """Every role reads. `Cargas recientes` of PAN-ING-01 is a read, and HU-E3-05 RN-04
    gives Solo Lectura the right to look without acting."""

    def __init__(self, vinculos: PortRepositorioVinculo) -> None:
        self._vinculos = vinculos

    async def ejecutar(self) -> list[VinculoDePlanilla]:
        return await self._vinculos.listar()


class DesvincularPlanilla:
    """Removes the link. Ingested data stays, which is ADR-007 and not an oversight.

    The stored file is deleted with it: it is a copy the company can upload again, and
    keeping bytes nobody can reach through the panel is how an object store fills up with
    other people's personal data.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        almacenamiento: PortAlmacenamientoDeArchivos,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._vinculos = vinculos
        self._almacenamiento = almacenamiento
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        vinculo_id: UUID,
        ahora: datetime,
    ) -> None:
        _exigir_administrador(rol, MOTIVO_DESVINCULAR)

        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")

        if vinculo.archivo is not None:
            await self._almacenamiento.eliminar(vinculo.archivo.clave)
        await self._vinculos.eliminar(vinculo_id)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="desvincular_planilla",
                entidad_afectada=f"VinculoDePlanilla:{vinculo_id}",
                resultado=Resultado.COMPLETADO,
            )
        )


def _extension(nombre: str) -> str:
    _, punto, resto = nombre.rpartition(".")
    return f".{resto.lower()}" if punto else ""
