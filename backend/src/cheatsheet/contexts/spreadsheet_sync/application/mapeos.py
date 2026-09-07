"""The use cases of HU-E3-01 and HU-E3-02 — proposing a mapping and confirming it.

**The destination attributes come from `master_data`'s own vocabulary**, listed here as
constants rather than reflected off the aggregates. Reflection would couple the model's
answer to a field rename in another context, and rule R3 forbids reaching into
`master_data/domain` anyway. The list is short and changes when a story changes it.

**The header fingerprint is a hash of the column names, in order.** RN-02 wants the mapping
reused «mientras la estructura no cambie», so the fingerprint has to change when and only
when the structure does. Order is included because a spreadsheet whose columns were
reordered is a spreadsheet whose data lands in different fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.errors import VinculoInexistente
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    PortModeloDeLenguaje,
    PortRepositorioMapeo,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import (
    EntradaDeMapeo,
    Mapeo,
    NivelDeConfianza,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: What a spreadsheet column can map to. The vocabulary of `master_data`, restated -- see
#: the module docstring on why this is a list and not reflection.
ATRIBUTOS_DE_CLIENTE: tuple[str, ...] = (
    "nombre",
    "cuit",
    "condicion_iva",
    "contacto_whatsapp",
    "contacto_email",
)
ATRIBUTOS_DE_SERVICIO: tuple[str, ...] = (
    "nombre",
    "precio",
    "alicuota_iva",
    "agendable",
    "duracion_estandar_min",
)

#: Without these, a processed row produces a record nobody can use: a customer with no
#: name, a service with no price. HU-E3-02 RN-02 blocks confirmation until they are fed.
OBLIGATORIOS_DE_CLIENTE = frozenset({"nombre"})
OBLIGATORIOS_DE_SERVICIO = frozenset({"nombre", "precio"})


def huella_de(columnas: tuple[str, ...]) -> str:
    """RN-02's `huella_encabezado`: identifies a structure, not a spreadsheet.

    Case and surrounding whitespace are normalised away -- `Nombre` and `nombre ` are the
    same column to a person, and treating them as a structural change would pause the sync
    every time somebody tidied a header. Order is **not** normalised: reordered columns are
    a different structure, because the data lands in different fields.
    """
    canonico = "".join(columna.strip().lower() for columna in columnas)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VistaDeMapeo:
    """What PAN-ING-02 renders: the mapping plus what is missing to confirm it."""

    mapeo: Mapeo
    faltantes: tuple[str, ...]
    #: True when the model was not consulted -- it failed, or a stored mapping was reused.
    propuesto_por_el_modelo: bool

    @property
    def puede_confirmarse(self) -> bool:
        return not self.faltantes


class ProponerMapeo:
    """HU-E3-01 — the model reads the headers and proposes; the user decides.

    **Reuse first** (RN-02): if a mapping with this fingerprint exists, it is returned
    untouched and the model is not called. That is the third acceptance criterion, and it
    is also what keeps a daily sync from paying for a model call every morning.
    """

    def __init__(
        self,
        *,
        mapeos: PortRepositorioMapeo,
        vinculos: PortRepositorioVinculo,
        modelo: PortModeloDeLenguaje,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._mapeos = mapeos
        self._vinculos = vinculos
        self._modelo = modelo
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        vinculo_id: UUID,
        columnas: tuple[str, ...],
        ejemplos: dict[str, str] | None = None,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> VistaDeMapeo:
        if not columnas:
            raise EntradaInvalida("La planilla no tiene encabezados que mapear")

        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")

        huella = huella_de(columnas)
        atributos = ATRIBUTOS_DE_SERVICIO if para_servicios else ATRIBUTOS_DE_CLIENTE
        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE

        existente = await self._mapeos.buscar_por_huella(huella)
        if existente is not None:
            vinculo.asignar_mapeo(existente.id, ahora=ahora)
            await self._vinculos.actualizar(vinculo)
            return VistaDeMapeo(
                mapeo=existente,
                faltantes=existente.faltantes(obligatorios),
                propuesto_por_el_modelo=False,
            )

        # The model sees column names and the destination vocabulary. Nothing else: the
        # samples below are read from the sheet and never leave this process (D12).
        propuestas = await self._modelo.proponer_mapeo(columnas=columnas, atributos=atributos)
        por_columna = {p.columna: p for p in propuestas}

        mapeo = Mapeo(
            id=uuid4(),
            empresa_id=empresa_id,
            huella_encabezado=huella,
            entradas=[
                _entrada(columna, por_columna.get(columna), (ejemplos or {}).get(columna))
                for columna in columnas
            ],
            created_at=ahora,
            updated_at=ahora,
        )
        await self._mapeos.agregar(mapeo)

        vinculo.asignar_mapeo(mapeo.id, ahora=ahora)
        await self._vinculos.actualizar(vinculo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="proponer_mapeo",
                entidad_afectada=f"Mapeo:{mapeo.id}",
                # The proposal succeeded even when the model did not answer: the screen
                # gets a mapping to work on either way. What failed, if anything, is in
                # the adapter's log, not in the business record.
                resultado=Resultado.COMPLETADO,
            )
        )
        return VistaDeMapeo(
            mapeo=mapeo,
            faltantes=mapeo.faltantes(obligatorios),
            propuesto_por_el_modelo=bool(propuestas),
        )


def _entrada(columna: str, propuesta: object, ejemplo: str | None) -> EntradaDeMapeo:
    """One column's entry. No proposal means `Sin asignar` with a zero score.

    That is the degradation path of ADR-0007 made concrete: when the model does not
    answer, every column arrives unassigned and the user maps by hand — which is exactly
    the state RN-03 already defines for low confidence, so the screen needs nothing new.
    """
    score = getattr(propuesta, "score", Decimal("0"))
    atributo = getattr(propuesta, "atributo", None)
    # RN-03: below the threshold the column is `Sin asignar`, whatever the model said.
    if NivelDeConfianza.desde_score(score).requiere_revision:
        atributo = None
    return EntradaDeMapeo(
        id=uuid4(), columna_origen=columna, atributo_destino=atributo, score=score, ejemplo=ejemplo
    )


class CorregirMapeo:
    """HU-E3-02 RN-01 — the user fixes an assignment before confirming."""

    def __init__(self, mapeos: PortRepositorioMapeo) -> None:
        self._mapeos = mapeos

    async def ejecutar(
        self,
        *,
        mapeo_id: UUID,
        rol: RolUsuario,
        columna: str,
        atributo: str | None,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> VistaDeMapeo:
        _exigir_que_pueda_mapear(rol)
        mapeo = await self._exigir(mapeo_id)

        atributos = ATRIBUTOS_DE_SERVICIO if para_servicios else ATRIBUTOS_DE_CLIENTE
        if atributo is not None and atributo not in atributos:
            raise EntradaInvalida(f"'{atributo}' no es un campo del sistema")

        mapeo.corregir(columna=columna, atributo=atributo, ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE
        return VistaDeMapeo(
            mapeo=mapeo, faltantes=mapeo.faltantes(obligatorios), propuesto_por_el_modelo=False
        )

    async def _exigir(self, mapeo_id: UUID) -> Mapeo:
        mapeo = await self._mapeos.buscar_por_id(mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo no existe")
        return mapeo


class ConfirmarMapeo:
    """HU-E3-02 RN-03 — confirming is what unlocks the processing of the spreadsheet."""

    def __init__(self, *, mapeos: PortRepositorioMapeo, publicador: PublicadorDeEventos) -> None:
        self._mapeos = mapeos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        mapeo_id: UUID,
        ahora: datetime,
        para_servicios: bool = False,
    ) -> Mapeo:
        _exigir_que_pueda_mapear(rol)

        mapeo = await self._mapeos.buscar_por_id(mapeo_id)
        if mapeo is None:
            raise EntradaInvalida("El mapeo no existe")

        obligatorios = OBLIGATORIOS_DE_SERVICIO if para_servicios else OBLIGATORIOS_DE_CLIENTE
        mapeo.confirmar(obligatorios=obligatorios, ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="confirmar_mapeo",
                entidad_afectada=f"Mapeo:{mapeo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return mapeo


def _exigir_que_pueda_mapear(rol: RolUsuario) -> None:
    """HU-E3-01 and HU-E3-02: «Administrador u Operador». Solo Lectura looks.

    Wider than HU-E2-04, which is the Administrador alone -- and that difference is the
    stories', not an oversight: linking a spreadsheet decides where the catalogue comes
    from, while mapping its columns is day-to-day work.
    """
    if rol is RolUsuario.SOLO_LECTURA:
        raise EntradaInvalida("Un usuario de Solo Lectura no puede modificar el mapeo")
