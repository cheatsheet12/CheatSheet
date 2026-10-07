"""Dobles del reintento de recordatorios (U7, tramo ii): una bitácora común ordena lo que pasa.

La pregunta central del tramo es **en qué orden** ocurren las cosas: la fila se confirma antes de
hablar con Meta, y el resultado se confirma después. Los dobles escriben en la misma lista.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from cheatsheet.contexts.payments.application.ports_de_recordatorios import ResultadoDeEnvio
from cheatsheet.contexts.payments.application.recordatorios import (
    DespacharRecordatorios,
    ResultadoDeBarrido,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    AHORA,
    EMPRESA,
    AislamientoFalso,
    CadenaFalsa,
    RecordatoriosFalsos,
    TransaccionFalsa,
    _cobro,
)
from tests.contexts.payments.application.test_confirmacion import CobrosFalsos, PublicadorFalso


class RecordatoriosConBitacora(RecordatoriosFalsos):
    """Los recordatorios en memoria, **con semántica de base**: se guardan y se leen copias.

    Sin eso, el doble comparte los objetos con el caso de uso y un `guardar` que falla no
    deshace lo que el dominio ya mutó: el doble mentiría justo en lo que estos tests prueban
    (qué queda en la base cuando el resultado no se pudo guardar).
    """

    def __init__(self, transaccion: TransaccionFalsa) -> None:
        super().__init__()
        self.transaccion = transaccion

    async def agregar(self, recordatorio: Recordatorio) -> None:
        await super().agregar(replace(recordatorio))
        self.transaccion.escribio("agregar")

    async def guardar(self, recordatorio: Recordatorio) -> None:
        indice = next(i for i, uno in enumerate(self.guardados) if uno.id == recordatorio.id)
        self.guardados[indice] = replace(recordatorio)
        self.transaccion.escribio("guardar")

    async def buscar_para_actualizar(self, recordatorio_id: UUID) -> Recordatorio | None:
        uno = await super().buscar_para_actualizar(recordatorio_id)
        return replace(uno) if uno is not None else None

    async def pendientes_de_reintento(self, ahora: datetime) -> list[Recordatorio]:
        return [replace(uno) for uno in await super().pendientes_de_reintento(ahora)]

    async def de_cobro(self, cobro_id: UUID) -> list[Recordatorio]:
        return [replace(uno) for uno in await super().de_cobro(cobro_id)]

    async def de_cobros(self, cobro_ids: list[UUID]) -> dict[UUID, list[Recordatorio]]:
        return {
            cobro_id: [replace(uno) for uno in unos]
            for cobro_id, unos in (await super().de_cobros(cobro_ids)).items()
        }


class EnvioGuionado:
    """Devuelve, intento a intento, lo que se le indicó; anota si había algo sin confirmar."""

    def __init__(
        self,
        transaccion: TransaccionFalsa,
        *resultados: ResultadoDeEnvio | BaseException,
        al_enviar: Callable[[], None] | None = None,
    ) -> None:
        self._transaccion = transaccion
        self._resultados = list(resultados)
        self._al_enviar = al_enviar
        self.llamadas = 0
        self.enviados: list[tuple[UUID, int]] = []
        #: Verdadero si en algún envío había escrituras sin confirmar: E/S con la transacción
        #: abierta, que es lo que este tramo elimina.
        self.con_transaccion_abierta = False

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> ResultadoDeEnvio:
        del empresa_id, canal
        self.llamadas += 1
        self._transaccion.bitacora.append("enviar")
        self.con_transaccion_abierta = (
            self.con_transaccion_abierta or self._transaccion.sin_confirmar
        )
        self.enviados.append((cobro.id, paso))
        if self._al_enviar is not None:
            self._al_enviar()
        resultado = (
            self._resultados.pop(0)
            if self._resultados
            else ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id="wamid-ok")
        )
        if isinstance(resultado, BaseException):
            raise resultado
        return resultado


def transitoria(codigo: str = "SATURADA") -> ResultadoDeEnvio:
    return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo=codigo, transitoria=True)


def permanente(codigo: str = "131026") -> ResultadoDeEnvio:
    return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo=codigo)


def incierto() -> ResultadoDeEnvio:
    return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="INCIERTO")


def enviado(wamid: str = "wamid-ok") -> ResultadoDeEnvio:
    return ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id=wamid)


#: El primer paso de `CadenaFalsa` es a los 3 días del vencimiento.
BARRIDO_1 = AHORA + timedelta(days=4)


@dataclass
class Escenario:
    barrido: DespacharRecordatorios
    cobros: CobrosFalsos
    recordatorios: RecordatoriosConBitacora
    envio: EnvioGuionado
    transaccion: TransaccionFalsa
    publicador: PublicadorFalso

    @property
    def fila(self) -> Recordatorio:
        (fila,) = self.recordatorios.guardados
        return fila

    async def barrer(self, ahora: datetime) -> ResultadoDeBarrido:
        return await self.barrido.ejecutar(empresa_id=EMPRESA, ahora=ahora)


def _escenario(
    *resultados: object,
    cobros: CobrosFalsos | None = None,
    recordatorios: RecordatoriosConBitacora | None = None,
    transaccion: TransaccionFalsa | None = None,
) -> Escenario:
    transaccion = transaccion or TransaccionFalsa()
    cobros = cobros or CobrosFalsos()
    recordatorios = recordatorios or RecordatoriosConBitacora(transaccion)
    envio = EnvioGuionado(transaccion, *resultados)  # type: ignore[arg-type]
    publicador = PublicadorFalso()
    barrido = DespacharRecordatorios(
        cobros=cobros,
        recordatorios=recordatorios,
        envio=envio,
        cadena=CadenaFalsa(),
        publicador=publicador,
        aislamiento=AislamientoFalso(),
        transaccion=transaccion,
    )
    return Escenario(barrido, cobros, recordatorios, envio, transaccion, publicador)


async def _con_un_cobro(*resultados: object) -> tuple[Escenario, Cobro]:
    escenario = _escenario(*resultados)
    cobro = _cobro(vence_en_dias=0)
    await escenario.cobros.agregar(cobro)
    return escenario, cobro
