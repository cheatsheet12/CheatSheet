"""Superficie HTTP de la agenda (HU-E7-01 … HU-E7-06).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**No hay `DELETE` en ninguna de las dos entidades.** Un turno se cancela —queda en la agenda,
con su estado, que es lo que hace auditable la ocupación de un recurso— y un recurso se
desactiva (HU-E7-04 RN-03). Borrar cualquiera de los dos dejaría la agenda histórica apuntando
a algo que ya no existe.

**El rango por defecto es el día en curso** (HU-E7-01 RN-01), y se calcula acá y no en el caso
de uso: «hoy» depende de la zona horaria de la agenda, que es presentación, mientras que
`VerAgenda` contesta por cualquier rango — que es lo que van a necesitar el agente del épico 8
y el reporte del épico 9.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, TypeVar
from uuid import UUID

from cheatsheet.api.agenda import armar_avisador, armar_catalogo
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.scheduling.application.disponibilidad import VerHorariosDisponibles
from cheatsheet.contexts.scheduling.application.ports import FiltrosDeAgenda
from cheatsheet.contexts.scheduling.application.recursos import (
    AsociarServicios,
    CambiarEstadoDeRecurso,
    ConfigurarDisponibilidad,
    ListarRecursos,
    QuitarExcepcion,
    RegistrarExcepcion,
    RegistrarRecurso,
)
from cheatsheet.contexts.scheduling.application.turnos import (
    CancelarTurno,
    RegistrarAsistencia,
    ReprogramarTurno,
    ReservarTurno,
    VerAgenda,
    VerTurno,
)
from cheatsheet.contexts.scheduling.domain.recurso import (
    ZONA_DE_LA_AGENDA,
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoExcepcion,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Turno
from cheatsheet.contexts.scheduling.infrastructure.ensamblado import Agenda
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel

_T = TypeVar("_T")


# -- entradas -------------------------------------------------------------------------


class PatronEntrada(BaseModel):
    dia_semana: int
    #: `"09:00"`. Se parsea acá porque `time` es lo que el dominio guarda: mandar minutos
    #: desde medianoche haría que la fila de la base ya no se pudiera leer a ojo.
    hora_inicio: time
    hora_fin: time
    duracion_slot_min: int


class RecursoEntrada(BaseModel):
    nombre: str
    tipo: str
    patrones: list[PatronEntrada] = []
    servicios: list[UUID] = []
    #: HU-E7-04 RN-06. `None`: 0 al registrar, y al configurar conserva el actual.
    intervalo_entre_turnos_min: int | None = None


class DisponibilidadEntrada(BaseModel):
    patrones: list[PatronEntrada]
    intervalo_entre_turnos_min: int | None = None


class ServiciosEntrada(BaseModel):
    servicios: list[UUID]


class EstadoEntrada(BaseModel):
    activo: bool


class ExcepcionEntrada(BaseModel):
    fecha: date
    tipo: str
    franja_inicio: datetime | None = None
    franja_duracion_min: int | None = None


class TurnoEntrada(BaseModel):
    cliente_id: UUID
    servicio_id: UUID
    recurso_id: UUID
    inicio: datetime
    #: La duración es siempre la del servicio (HU-E7-06 RN-08): si un cliente viejo manda
    #: `duracion_min`, Pydantic lo ignora y nunca llega al caso de uso.
    #: La carga a posteriori (HU-E7-06 RN-07): sólo el Administrador, y siempre explícita. Un
    #: inicio pasado sin este indicador se rechaza igual que para cualquier rol.
    a_posteriori: bool = False


class ReprogramacionEntrada(BaseModel):
    inicio: datetime
    #: La corrección a posteriori (HU-E7-02 RN-07). Ver `TurnoEntrada.a_posteriori`.
    a_posteriori: bool = False


class AsistenciaEntrada(BaseModel):
    asistio: bool


# -- salidas --------------------------------------------------------------------------


class PatronSalida(BaseModel):
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    duracion_slot_min: int


class ExcepcionSalida(BaseModel):
    fecha: date
    tipo: str
    franja_inicio: datetime | None
    franja_duracion_min: int | None


class RecursoSalida(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    activo: bool
    patrones: list[PatronSalida]
    excepciones: list[ExcepcionSalida]
    servicios: list[UUID]
    intervalo_entre_turnos_min: int


class ListadoDeRecursos(BaseModel):
    recursos: list[RecursoSalida]


class TurnoSalida(BaseModel):
    id: UUID
    cliente_id: UUID
    servicio_id: UUID
    recurso_id: UUID
    cobro_id: UUID | None
    inicio: datetime
    duracion_min: int
    fin: datetime
    estado: str
    canal_reserva: str
    #: HU-E7-03 RN-01: la pantalla ofrece marcar asistencia sólo si esto es `True`.
    ya_transcurrio: bool
    #: HU-E7-03 RN-02: un turno completado habilita emitir el comprobante del servicio.
    habilita_facturacion: bool


class ListadoDeTurnos(BaseModel):
    turnos: list[TurnoSalida]


class ServicioSalida(BaseModel):
    id: UUID
    nombre: str
    duracion_estandar_min: int


class HorarioSalida(BaseModel):
    inicio: datetime
    ocupado: bool


class DisponibilidadSalida(BaseModel):
    """Los horarios que el recurso ofrece ese día, con los que ya están tomados marcados.

    **`ocupado` es una ayuda, no una garantía.** Entre esta respuesta y el `POST` que reserva
    puede entrar otro turno; quien decide es la restricción de exclusión (decisión D28), y por
    eso reservar puede fallar aunque acá figurara libre.
    """

    fecha: date
    horarios: list[HorarioSalida]


def _a_recurso(recurso: RecursoReservable) -> RecursoSalida:
    return RecursoSalida(
        id=recurso.id,
        nombre=recurso.nombre,
        tipo=recurso.tipo.value,
        activo=recurso.activo,
        patrones=[
            PatronSalida(
                dia_semana=uno.dia_semana,
                hora_inicio=uno.hora_inicio,
                hora_fin=uno.hora_fin,
                duracion_slot_min=uno.duracion_slot_min,
            )
            for uno in recurso.patrones
        ],
        excepciones=[
            ExcepcionSalida(
                fecha=una.fecha,
                tipo=una.tipo.value,
                franja_inicio=una.franja_inicio,
                franja_duracion_min=una.franja_duracion_min,
            )
            for una in recurso.excepciones
        ],
        servicios=sorted(recurso.servicios),
        intervalo_entre_turnos_min=recurso.intervalo_entre_turnos_min,
    )


def _a_turno(turno: Turno, ahora: datetime) -> TurnoSalida:
    return TurnoSalida(
        id=turno.id,
        cliente_id=turno.cliente_id,
        servicio_id=turno.servicio_id,
        recurso_id=turno.recurso_id,
        cobro_id=turno.cobro_id,
        inicio=turno.franja.inicio,
        duracion_min=turno.franja.duracion_min,
        fin=turno.franja.fin,
        estado=turno.estado.value,
        canal_reserva=turno.canal_reserva,
        ya_transcurrio=turno.ya_transcurrio(ahora),
        habilita_facturacion=turno.habilita_facturacion,
    )


def _patrones(entradas: list[PatronEntrada]) -> tuple[PatronDeDisponibilidad, ...]:
    return tuple(
        PatronDeDisponibilidad(
            dia_semana=uno.dia_semana,
            hora_inicio=uno.hora_inicio,
            hora_fin=uno.hora_fin,
            duracion_slot_min=uno.duracion_slot_min,
        )
        for uno in entradas
    )


def _tipo_de_recurso(texto: str) -> TipoRecurso:
    if texto not in TipoRecurso.__members__:
        raise EntradaInvalida(f"«{texto}» no es un tipo de recurso valido")
    return TipoRecurso[texto]


def _excepcion(entrada: ExcepcionEntrada) -> ExcepcionDeDisponibilidad:
    if entrada.tipo not in TipoExcepcion.__members__:
        raise EntradaInvalida(f"«{entrada.tipo}» no es un tipo de excepcion valido")
    return ExcepcionDeDisponibilidad(
        fecha=entrada.fecha,
        tipo=TipoExcepcion[entrada.tipo],
        franja_inicio=entrada.franja_inicio,
        franja_duracion_min=entrada.franja_duracion_min,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _rango(desde: datetime | None, hasta: datetime | None, hoy: date) -> tuple[datetime, datetime]:
    """El rango pedido, o el día en curso (HU-E7-01 RN-01).

    El día se define en la zona de la agenda y no en UTC: un turno de las 22 de un martes es
    del martes para quien lo atiende, aunque en UTC ya sea miércoles.
    """
    if desde is not None and hasta is not None:
        return desde, hasta
    inicio = datetime.combine(hoy, time.min, tzinfo=ZONA_DE_LA_AGENDA)
    return desde or inicio, hasta or inicio + timedelta(days=1)


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["scheduling"])
    router.include_router(_rutas_de_recursos(recursos), prefix="/recursos")
    router.include_router(_rutas_de_turnos(recursos), prefix="/turnos")
    return router


def _rutas_de_recursos(recursos: Recursos) -> APIRouter:
    """PAN-AGE-03 (HU-E7-04 y HU-E7-05). Todos leen; sólo el Administrador escribe."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, solo_activos: Annotated[bool, Query()] = False
    ) -> ListadoDeRecursos:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeRecursos | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            encontrados = await ListarRecursos(piezas.recursos).ejecutar(solo_activos=solo_activos)
            salida = ListadoDeRecursos(recursos=[_a_recurso(uno) for uno in encontrados])
        return _exigir(salida)

    @router.get("/servicios")
    async def servicios_agendables(request: Request) -> list[ServicioSalida]:
        """Los servicios que se pueden reservar, para poblar el selector de PAN-AGE-02.

        Vive bajo `/recursos` y no bajo `/servicios` a propósito: el catálogo completo es de
        `master_data` y ya tiene su ruta; esto es la vista que la agenda necesita, filtrada por
        una regla de este épico.
        """
        empresa_id, _, rol = _actor(request)
        salida: list[ServicioSalida] = []
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            catalogo = armar_catalogo(unidad, empresa_id=empresa_id, rol=rol)
            salida = [
                ServicioSalida(
                    id=uno.id,
                    nombre=uno.nombre,
                    duracion_estandar_min=uno.duracion_estandar_min,
                )
                for uno in await catalogo.listar_agendables()
            ]
        return salida

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(request: Request, entrada: RecursoEntrada) -> RecursoSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await RegistrarRecurso(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                nombre=entrada.nombre,
                tipo=_tipo_de_recurso(entrada.tipo),
                patrones=_patrones(entrada.patrones),
                servicios=frozenset(entrada.servicios),
                intervalo_entre_turnos_min=entrada.intervalo_entre_turnos_min or 0,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    router.include_router(_rutas_de_configuracion(recursos), prefix="/{recurso_id}")
    router.include_router(_rutas_de_excepciones(recursos), prefix="/{recurso_id}")
    return router


def _rutas_de_configuracion(recursos: Recursos) -> APIRouter:
    """Los tres `PUT` de HU-E7-04, en su propio grupo para no pasar del límite de complejidad.

    Los tres **reemplazan** en vez de acumular, que es lo que hace que configurar un recurso
    sea una operación y no una serie de parches con orden significativo.
    """
    router = APIRouter()

    @router.put("/disponibilidad")
    async def disponibilidad(
        request: Request, recurso_id: UUID, entrada: DisponibilidadEntrada
    ) -> RecursoSalida:
        """`PUT` y no `POST`: **reemplaza** el horario semanal (HU-E7-04 RN-01)."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await ConfigurarDisponibilidad(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                patrones=_patrones(entrada.patrones),
                intervalo_entre_turnos_min=entrada.intervalo_entre_turnos_min,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    @router.put("/servicios")
    async def asociar(
        request: Request, recurso_id: UUID, entrada: ServiciosEntrada
    ) -> RecursoSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await AsociarServicios(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                servicios=frozenset(entrada.servicios),
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    @router.put("/estado")
    async def estado(request: Request, recurso_id: UUID, entrada: EstadoEntrada) -> RecursoSalida:
        """Activar o desactivar. Lo que la configuración tiene en lugar de un borrado."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await CambiarEstadoDeRecurso(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                activo=entrada.activo,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    return router


def _rutas_de_excepciones(recursos: Recursos) -> APIRouter:
    """HU-E7-05, en su propio grupo para no pasar del límite de complejidad del archivo."""
    router = APIRouter()

    @router.post("/excepciones", status_code=status.HTTP_201_CREATED)
    async def agregar(
        request: Request, recurso_id: UUID, entrada: ExcepcionEntrada
    ) -> RecursoSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await RegistrarExcepcion(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                excepcion=_excepcion(entrada),
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    @router.delete("/excepciones/{fecha}")
    async def quitar(request: Request, recurso_id: UUID, fecha: date) -> RecursoSalida:
        """El único `DELETE` del épico, y no borra una entidad del negocio.

        Una excepción es una anotación sobre un calendario: sacarla es volver al horario
        habitual, no perder un registro. Corregir una es quitarla y volver a agregarla, lo que
        evita tener que decidir qué significa cambiarle el tipo.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await QuitarExcepcion(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                fecha=fecha,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_recurso(recurso)
        return _exigir(salida)

    return router


def _rutas_de_turnos(recursos: Recursos) -> APIRouter:
    """PAN-AGE-01 y PAN-AGE-02. Todos leen; Administrador y Operador gestionan."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        recurso_id: Annotated[UUID | None, Query()] = None,
        desde: Annotated[datetime | None, Query()] = None,
        hasta: Annotated[datetime | None, Query()] = None,
        estado: Annotated[str | None, Query()] = None,
    ) -> ListadoDeTurnos:
        """PAN-AGE-01 (HU-E7-01 RN-01). Sin rango explícito, el día en curso."""
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeTurnos | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            ahora = unidad.reloj.ahora()
            inicio, fin = _rango(desde, hasta, ahora.astimezone(ZONA_DE_LA_AGENDA).date())
            # Un estado desconocido se vuelve «sin filtro» y no un 422: el query string viene
            # de una URL que alguien pudo editar, y la respuesta honesta a un filtro que no
            # entendemos es la agenda sin filtrar.
            estados = (
                (EstadoTurno[estado],)
                if estado is not None and estado in EstadoTurno.__members__
                else ()
            )
            piezas = Agenda.armar(unidad)
            turnos = await VerAgenda(piezas.turnos).ejecutar(
                FiltrosDeAgenda(recurso_id=recurso_id, desde=inicio, hasta=fin, estados=estados)
            )
            salida = ListadoDeTurnos(turnos=[_a_turno(uno, ahora) for uno in turnos])
        return _exigir(salida)

    @router.get("/disponibilidad")
    async def disponibilidad(
        request: Request,
        recurso_id: Annotated[UUID, Query()],
        fecha: Annotated[date, Query()],
        servicio_id: Annotated[UUID, Query()],
    ) -> DisponibilidadSalida:
        """Los horarios que ese recurso ofrece ese día **para ese servicio**, con los ocupados.

        Lo que puebla el selector de PAN-AGE-02. La duración del turno es la del servicio, así
        que sin `servicio_id` no hay grilla (D96). Ver la advertencia de `DisponibilidadSalida`.
        """
        empresa_id, _, rol = _actor(request)
        salida: DisponibilidadSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            horarios = await VerHorariosDisponibles(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=rol),
            ).ejecutar(
                recurso_id=recurso_id,
                servicio_id=servicio_id,
                fecha=fecha,
                # Los que ya pasaron no se ofrecen (D95). La carga a posteriori no usa esta
                # grilla: el Administrador escribe la fecha y la hora.
                ahora=unidad.reloj.ahora(),
            )
            salida = DisponibilidadSalida(
                fecha=fecha,
                horarios=[
                    HorarioSalida(inicio=uno.inicio, ocupado=uno.ocupado) for uno in horarios
                ],
            )
        return _exigir(salida)

    @router.get("/{turno_id}")
    async def ver(request: Request, turno_id: UUID) -> TurnoSalida:
        """PAN-AGE-02. Todos los roles leen (HU-E7-01 RN-03)."""
        empresa_id, _, _ = _actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await VerTurno(piezas.turnos).ejecutar(turno_id)
            salida = _a_turno(turno, unidad.reloj.ahora())
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def reservar(request: Request, entrada: TurnoEntrada) -> TurnoSalida:
        """HU-E7-06. **201**: cuando esto contesta, la franja quedó tomada de verdad.

        Si estaba ocupada, el repositorio levanta `FranjaOcupada` y la respuesta es un 422 con
        la frase que escribió la historia.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await ReservarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=rol),
                avisador=armar_avisador(unidad, recursos.settings, empresa_id=empresa_id, rol=rol),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cliente_id=entrada.cliente_id,
                servicio_id=entrada.servicio_id,
                recurso_id=entrada.recurso_id,
                inicio=entrada.inicio,
                ahora=unidad.reloj.ahora(),
                a_posteriori=entrada.a_posteriori,
            )
            salida = _a_turno(turno, unidad.reloj.ahora())
        return _exigir(salida)

    router.include_router(_rutas_de_gestion(recursos), prefix="/{turno_id}")
    return router


def _rutas_de_gestion(recursos: Recursos) -> APIRouter:
    """Las tres acciones de HU-E7-02 y HU-E7-03, en su propio grupo por complejidad."""
    router = APIRouter()

    @router.post("/cancelacion")
    async def cancelar(request: Request, turno_id: UUID) -> TurnoSalida:
        """HU-E7-02. Sin cuerpo: cancelar un turno no pide motivo.

        Distinto de cancelar un cobro, que sí lo pide (HU-E6-04 RN-02). La diferencia es del
        negocio y no del diseño: ahí se está dando de baja una deuda y acá se está liberando
        una franja, y ninguna historia de este épico pide el motivo.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await CancelarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                avisador=armar_avisador(unidad, recursos.settings, empresa_id=empresa_id, rol=rol),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_turno(turno, unidad.reloj.ahora())
        return _exigir(salida)

    @router.post("/reprogramacion")
    async def reprogramar(
        request: Request, turno_id: UUID, entrada: ReprogramacionEntrada
    ) -> TurnoSalida:
        """HU-E7-02 RN-02: mueve la franja y **conserva el estado**."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await ReprogramarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                avisador=armar_avisador(unidad, recursos.settings, empresa_id=empresa_id, rol=rol),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                inicio=entrada.inicio,
                ahora=unidad.reloj.ahora(),
                a_posteriori=entrada.a_posteriori,
            )
            salida = _a_turno(turno, unidad.reloj.ahora())
        return _exigir(salida)

    @router.post("/asistencia")
    async def asistencia(
        request: Request, turno_id: UUID, entrada: AsistenciaEntrada
    ) -> TurnoSalida:
        """HU-E7-03. Una sola ruta para las dos marcas: son la misma decisión con dos valores.

        Dos rutas —una por resultado— habrían hecho que agregar un tercero fuera una ruta más
        en vez de un valor más, y el frontend tendría que elegir a cuál llamar en lugar de
        mandar lo que el usuario apretó.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await RegistrarAsistencia(piezas.turnos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                asistio=entrada.asistio,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_turno(turno, unidad.reloj.ahora())
        return _exigir(salida)

    return router
