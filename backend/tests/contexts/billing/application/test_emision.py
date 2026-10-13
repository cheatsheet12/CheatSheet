"""HU-E5-03 — la emisión, y sobre todo **lo que pasa cuando no sabemos qué pasó**.

El bloque que más importa de este archivo es el de la reconciliación (decisión D17). Todo
lo demás son reglas de la historia; ese prueba la única falla del sistema que no se arregla
con un deploy: ARCA autorizó, la respuesta se perdió, y reintentar emitiría un **segundo
comprobante legal por una sola venta**.

Los dobles son honestos sobre lo que no pueden simular. `PuntosFalsos.tomar_para_emitir` no
tiene candado, así que la serialización de D14 no se prueba acá — vive en
`tests/integracion/test_puntos_de_venta_postgres.py`, contra el motor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.billing.application.emision import (
    MENSAJE_RECEPTOR_INACTIVO,
    MENSAJE_SIN_CONDICION,
    AutorizarComprobante,
    EmitirComprobante,
    ReconciliarComprobante,
    ValidarReceptor,
    item,
)
from cheatsheet.contexts.billing.application.errors import (
    ArcaNoDisponible,
    ComprobanteInexistente,
    PuntoDeVentaInexistente,
    TipoDeComprobanteInvalido,
)
from cheatsheet.contexts.billing.application.ports import (
    DatosDelReceptor,
    FiltrosDeComprobante,
    RespuestaDeArca,
)
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    MENSAJE_CUIT_INVALIDO,
    MENSAJE_CUIT_NO_ENCONTRADO,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.fiscal import CondicionIVA
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RI = CondicionIVA.RESPONSABLE_INSCRIPTO
CUIT_VALIDO = "30712345671"
UN_CAE = CAE(codigo="75123456789012", vence_el=date(2026, 9, 17))


class PuntosFalsos:
    def __init__(self, punto: PuntoDeVenta) -> None:
        self.punto = punto
        self.guardados = 0

    async def agregar(self, punto: PuntoDeVenta) -> None: ...

    async def guardar(self, punto: PuntoDeVenta) -> None:
        del punto  # El doble guarda en memoria: el objeto ya es el mismo.
        self.guardados += 1

    async def buscar_por_id(self, punto_id: UUID) -> PuntoDeVenta | None:
        return self.punto if punto_id == self.punto.id else None

    async def listar(self) -> list[PuntoDeVenta]:
        return [self.punto]

    async def tomar_para_emitir(self, punto_id: UUID) -> PuntoDeVenta | None:
        # Sin candado: acá no hay motor. Lo que este doble **no** puede simular es
        # justamente lo que hace correcto al metodo real (D14).
        return self.punto if punto_id == self.punto.id else None


class ComprobantesFalsos:
    def __init__(self) -> None:
        self.guardados: dict[UUID, Comprobante] = {}

    async def agregar(self, comprobante: Comprobante) -> None:
        self.guardados[comprobante.id] = comprobante

    async def guardar(self, comprobante: Comprobante) -> None:
        self.guardados[comprobante.id] = comprobante

    async def buscar_por_id(self, comprobante_id: UUID) -> Comprobante | None:
        return self.guardados.get(comprobante_id)

    async def listar(self, filtros: FiltrosDeComprobante) -> list[Comprobante]:
        del filtros
        return list(self.guardados.values())

    async def notas_de(self, origen_id: UUID) -> list[Comprobante]:
        return [c for c in self.guardados.values() if c.comprobante_origen_id == origen_id]

    async def en_vuelo(self, *, anteriores_a: datetime) -> list[Comprobante]:
        return [
            c
            for c in self.guardados.values()
            if c.esta_en_vuelo and c.fecha_emision is not None and c.fecha_emision < anteriores_a
        ]


class ArcaFalso:
    """El doble de WSFEv1, con las tres respuestas que importan y una cuenta de llamadas.

    `solicitudes` es lo que hace afirmable la propiedad central de D17: **cuántas veces se
    mandó `FECAESolicitar`**. Un sistema que emite dos comprobantes por una venta lo hace
    incrementando ese número, y eso es lo que hay que ver.
    """

    def __init__(
        self,
        *,
        respuesta: RespuestaDeArca | None = None,
        registrado: RespuestaDeArca | None = None,
        caido: bool = False,
        consulta_caida: bool = False,
        ultimo: int = 0,
    ) -> None:
        self.respuesta = respuesta or RespuestaDeArca(autorizado=True, cae=UN_CAE)
        self.registrado = registrado
        self.caido = caido
        self.consulta_caida = consulta_caida
        self.ultimo = ultimo
        self.solicitudes = 0
        self.consultas = 0

    async def solicitar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca:
        del empresa_id, comprobante
        self.solicitudes += 1
        if self.caido:
            raise ArcaNoDisponible("ARCA no respondio")
        return self.respuesta

    async def consultar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca | None:
        del empresa_id, comprobante
        self.consultas += 1
        if self.consulta_caida:
            raise ArcaNoDisponible("ARCA no respondio")
        return self.registrado

    async def ultimo_autorizado(
        self, *, empresa_id: EmpresaId, punto: PuntoDeVenta, tipo: TipoComprobante
    ) -> int:
        del empresa_id, punto, tipo
        return self.ultimo


class ColaFalsa:
    def __init__(self) -> None:
        self.encolados: list[UUID] = []

    async def encolar(self, *, empresa_id: EmpresaId, comprobante_id: UUID) -> None:
        del empresa_id
        self.encolados.append(comprobante_id)


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


class ReceptoresFalsos:
    def __init__(self, datos: DatosDelReceptor | None) -> None:
        self.datos = datos

    async def validar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDelReceptor | None:
        del empresa_id, cuit
        return self.datos


@pytest.fixture
def punto() -> PuntoDeVenta:
    return PuntoDeVenta(id=uuid4(), empresa_id=EMPRESA, numero=1, created_at=AHORA)


def _comprobante(punto: PuntoDeVenta, *, receptor: CondicionIVA = RI) -> Comprobante:
    comprobante = Comprobante(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        punto_de_venta_id=punto.id,
        tipo=TipoComprobante.FACTURA_A,
        receptor=Receptor(nombre="Acme SA", cuit=CUIT_VALIDO, condicion_iva=receptor),
        emisor_condicion_iva=RI,
        created_at=AHORA,
    )
    comprobante.agregar_item(
        item(
            descripcion="Corte de pelo",
            cantidad="1",
            precio_unitario="1000.00",
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
    )
    return comprobante


# ------------------------------------------------------------------ validar el receptor


async def test_un_cuit_con_digito_verificador_malo_no_consulta_a_arca() -> None:
    """HU-E5-03 lo dice con esas palabras: «y no consulta a ARCA»."""
    receptores = ReceptoresFalsos(None)

    with pytest.raises(EntradaInvalida) as exc:
        await ValidarReceptor(receptores).ejecutar(empresa_id=EMPRESA, cuit="30712345670")

    assert str(exc.value) == MENSAJE_CUIT_INVALIDO


async def test_un_cuit_valido_que_el_padron_no_conoce_bloquea_la_emision() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        await ValidarReceptor(ReceptoresFalsos(None)).ejecutar(empresa_id=EMPRESA, cuit=CUIT_VALIDO)

    assert str(exc.value) == MENSAJE_CUIT_NO_ENCONTRADO


async def test_un_cuit_valido_completa_razon_social_y_condicion() -> None:
    receptores = ReceptoresFalsos(
        DatosDelReceptor(cuit=CUIT_VALIDO, razon_social="Acme SA", condicion_iva=RI, activo=True)
    )

    receptor = await ValidarReceptor(receptores).ejecutar(empresa_id=EMPRESA, cuit=CUIT_VALIDO)

    assert receptor.nombre == "Acme SA"
    assert receptor.condicion_iva is RI


async def test_un_cuit_dado_de_baja_no_es_lo_mismo_que_uno_inexistente() -> None:
    """Llevan a conversaciones opuestas con el cliente, así que se dicen distinto."""
    receptores = ReceptoresFalsos(
        DatosDelReceptor(cuit=CUIT_VALIDO, razon_social="Acme SA", condicion_iva=RI, activo=False)
    )

    with pytest.raises(EntradaInvalida) as exc:
        await ValidarReceptor(receptores).ejecutar(empresa_id=EMPRESA, cuit=CUIT_VALIDO)

    assert str(exc.value) == MENSAJE_RECEPTOR_INACTIVO


async def test_sin_condicion_de_iva_no_se_adivina() -> None:
    """Inventarla decidiría qué tipo de comprobante se puede emitir."""
    receptores = ReceptoresFalsos(
        DatosDelReceptor(cuit=CUIT_VALIDO, razon_social="Acme", condicion_iva=None, activo=True)
    )

    with pytest.raises(EntradaInvalida) as exc:
        await ValidarReceptor(receptores).ejecutar(empresa_id=EMPRESA, cuit=CUIT_VALIDO)

    assert str(exc.value) == MENSAJE_SIN_CONDICION


# ------------------------------------------------------------------------- emitir


def _emisor(
    punto: PuntoDeVenta, arca: ArcaFalso, comprobantes: ComprobantesFalsos, cola: ColaFalsa
) -> tuple[EmitirComprobante, PuntosFalsos, PublicadorFalso]:
    puntos = PuntosFalsos(punto)
    publicador = PublicadorFalso()
    return (
        EmitirComprobante(
            comprobantes=comprobantes,
            puntos=puntos,
            arca=arca,
            cola=cola,
            publicador=publicador,
        ),
        puntos,
        publicador,
    )


async def test_emitir_deja_el_comprobante_en_vuelo_y_lo_encola(punto: PuntoDeVenta) -> None:
    """El criterio de aceptación: «aparece en el listado con estado Pendiente»."""
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)
    comprobante = _comprobante(punto)

    await emitir.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        comprobante=comprobante,
        ahora=AHORA,
    )

    assert comprobante.estado is EstadoComprobante.ENVIADO_A_ARCA
    assert comprobante.numero == 1
    assert cola.encolados == [comprobante.id]
    # Persistido **antes** de que salga el sobre: es de lo que depende toda la D17.
    assert comprobantes.guardados[comprobante.id] is comprobante
    # Y esta capa no habla con `FECAESolicitar`.
    assert arca.solicitudes == 0


async def test_emitir_pregunta_a_arca_donde_va_la_numeracion(punto: PuntoDeVenta) -> None:
    """**D18.** ARCA es la autoridad de la correlatividad; nuestro contador es un caché.

    Si nuestra fila dice 0 y ARCA ya autorizó el 40, emitir el 1 se rechaza con «numero de
    comprobante no correlativo» — y sigue rechazando hasta que los dos coincidan.
    """
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso(ultimo=40)
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)
    comprobante = _comprobante(punto)

    await emitir.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        comprobante=comprobante,
        ahora=AHORA,
    )

    assert comprobante.numero == 41


async def test_un_tipo_invalido_para_el_par_de_condiciones_no_sale(punto: PuntoDeVenta) -> None:
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)
    comprobante = _comprobante(punto, receptor=CondicionIVA.CONSUMIDOR_FINAL)

    with pytest.raises(TipoDeComprobanteInvalido):
        await emitir.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            comprobante=comprobante,
            ahora=AHORA,
        )

    assert cola.encolados == []


async def test_solo_lectura_no_emite(punto: PuntoDeVenta) -> None:
    """RN-04 de HU-E5-01: ve y filtra, no inicia acciones."""
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)

    with pytest.raises(OperacionNoPermitida):
        await emitir.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.SOLO_LECTURA,
            comprobante=_comprobante(punto),
            ahora=AHORA,
        )

    assert cola.encolados == []


async def test_un_punto_de_venta_inexistente_no_consume_numero(punto: PuntoDeVenta) -> None:
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)
    comprobante = _comprobante(punto)
    comprobante.punto_de_venta_id = uuid4()

    with pytest.raises(PuntoDeVentaInexistente):
        await emitir.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            comprobante=comprobante,
            ahora=AHORA,
        )


async def test_un_punto_desactivado_no_emite(punto: PuntoDeVenta) -> None:
    """RN-04 de HU-E5-05, verificada desde el otro lado."""
    punto.desactivar()
    comprobantes, cola, arca = ComprobantesFalsos(), ColaFalsa(), ArcaFalso()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)

    with pytest.raises(Exception, match="desactivado"):
        await emitir.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            comprobante=_comprobante(punto),
            ahora=AHORA,
        )


# ------------------------------------------------------------------------ autorizar


async def _emitido(punto: PuntoDeVenta, arca: ArcaFalso) -> tuple[Comprobante, ComprobantesFalsos]:
    comprobantes, cola = ComprobantesFalsos(), ColaFalsa()
    emitir, _, _ = _emisor(punto, arca, comprobantes, cola)
    comprobante = _comprobante(punto)
    await emitir.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        comprobante=comprobante,
        ahora=AHORA,
    )
    return comprobante, comprobantes


def _autorizador(
    punto: PuntoDeVenta, comprobantes: ComprobantesFalsos, arca: ArcaFalso
) -> AutorizarComprobante:
    return AutorizarComprobante(
        comprobantes=comprobantes,
        puntos=PuntosFalsos(punto),
        arca=arca,
        publicador=PublicadorFalso(),
    )


async def test_arca_autoriza_y_el_comprobante_guarda_su_cae(punto: PuntoDeVenta) -> None:
    arca = ArcaFalso()
    comprobante, comprobantes = await _emitido(punto, arca)

    resuelto = await _autorizador(punto, comprobantes, arca).ejecutar(
        empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA
    )

    assert resuelto.estado is EstadoComprobante.AUTORIZADO
    assert resuelto.cae == UN_CAE
    assert resuelto.es_descargable


async def test_arca_rechaza_y_el_motivo_se_guarda_con_sus_palabras(punto: PuntoDeVenta) -> None:
    """HU-E5-03: «Error 10016: el comprobante no cumple la resolución general vigente.»

    Las palabras son de ARCA. Traducirlas sería decidir qué significan cuarenta códigos
    numéricos y equivocarse en uno, en un mensaje que alguien le lleva a su contador.
    """
    arca = ArcaFalso()
    comprobante, comprobantes = await _emitido(punto, arca)
    arca.respuesta = RespuestaDeArca(
        autorizado=False,
        codigo="10016",
        descripcion="el comprobante no cumple la resolucion general vigente",
    )

    resuelto = await _autorizador(punto, comprobantes, arca).ejecutar(
        empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA
    )

    assert resuelto.estado is EstadoComprobante.RECHAZADO
    assert resuelto.motivo_de_rechazo is not None
    assert "10016" in resuelto.motivo_de_rechazo
    assert not resuelto.es_descargable
    # Un rechazo es una respuesta: ARCA no registró nada bajo ese numero y vuelve al pool.
    assert punto.ultimo_numero(TipoComprobante.FACTURA_A) == 0


async def test_una_tarea_redelivered_no_reenvia_un_comprobante_ya_resuelto(
    punto: PuntoDeVenta,
) -> None:
    """Celery reentrega. Un reenvío acá emitiría un segundo comprobante legal."""
    arca = ArcaFalso()
    comprobante, comprobantes = await _emitido(punto, arca)
    autorizador = _autorizador(punto, comprobantes, arca)

    await autorizador.ejecutar(empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA)
    await autorizador.ejecutar(empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA)

    assert arca.solicitudes == 1


async def test_autorizar_uno_inexistente_falla(punto: PuntoDeVenta) -> None:
    arca = ArcaFalso()
    with pytest.raises(ComprobanteInexistente):
        await _autorizador(punto, ComprobantesFalsos(), arca).ejecutar(
            empresa_id=EMPRESA, comprobante_id=uuid4(), ahora=AHORA
        )


async def test_arca_caida_deja_el_comprobante_donde_estaba(punto: PuntoDeVenta) -> None:
    """**No hacer nada es la acción correcta.**

    El comprobante queda en `ENVIADO_A_ARCA`, que significa «no sabemos», y el número
    **no** vuelve al pool. Devolverlo acá sería entregarlo otra vez a un comprobante
    distinto mientras ARCA quizá ya autorizó el primero con ese número.
    """
    arca = ArcaFalso()
    comprobante, comprobantes = await _emitido(punto, arca)
    arca.caido = True

    with pytest.raises(ArcaNoDisponible):
        await _autorizador(punto, comprobantes, arca).ejecutar(
            empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA
        )

    assert comprobante.esta_en_vuelo
    assert punto.ultimo_numero(TipoComprobante.FACTURA_A) == 1


# ------------------------------------------------------- reconciliar · decisión D17


def _reconciliador(
    punto: PuntoDeVenta, comprobantes: ComprobantesFalsos, arca: ArcaFalso
) -> ReconciliarComprobante:
    return ReconciliarComprobante(
        comprobantes=comprobantes,
        puntos=PuntosFalsos(punto),
        arca=arca,
        publicador=PublicadorFalso(),
    )


MAS_TARDE = AHORA + timedelta(minutes=30)


async def test_si_arca_lo_tiene_registrado_se_guarda_ese_cae_y_no_se_emite_de_nuevo(
    punto: PuntoDeVenta,
) -> None:
    """**El caso que justifica toda la decisión D17.**

    ARCA autorizó, la respuesta se perdió. Un reintento a ciegas de `FECAESolicitar` sería
    un segundo comprobante legal por una sola venta. La reconciliación **pregunta**, y lo
    que encuentra es el CAE que ya existe.
    """
    arca = ArcaFalso()
    comprobante, comprobantes = await _emitido(punto, arca)
    arca.caido = True
    with pytest.raises(ArcaNoDisponible):
        await _autorizador(punto, comprobantes, arca).ejecutar(
            empresa_id=EMPRESA, comprobante_id=comprobante.id, ahora=AHORA
        )

    # ARCA vuelve, y resulta que sí lo tenía.
    arca.registrado = RespuestaDeArca(autorizado=True, cae=UN_CAE)
    solicitudes_antes = arca.solicitudes

    resueltos = await _reconciliador(punto, comprobantes, arca).ejecutar(
        empresa_id=EMPRESA, ahora=MAS_TARDE
    )

    assert [c.id for c in resueltos] == [comprobante.id]
    assert comprobante.estado is EstadoComprobante.AUTORIZADO
    assert comprobante.cae == UN_CAE
    # Lo que hay que ver: **no se volvió a pedir la autorizacion**.
    assert arca.solicitudes == solicitudes_antes
    assert arca.consultas == 1


async def test_si_arca_no_lo_tiene_el_comprobante_se_puede_volver_a_emitir(
    punto: PuntoDeVenta,
) -> None:
    """Sin registro en ARCA significa que nunca llegó. Recién ahí se libera el número."""
    arca = ArcaFalso(registrado=None)
    comprobante, comprobantes = await _emitido(punto, arca)

    await _reconciliador(punto, comprobantes, arca).ejecutar(empresa_id=EMPRESA, ahora=MAS_TARDE)

    assert comprobante.estado is EstadoComprobante.RECHAZADO
    assert comprobante.motivo_de_rechazo is not None
    assert "SIN_REGISTRO" in comprobante.motivo_de_rechazo
    assert punto.ultimo_numero(TipoComprobante.FACTURA_A) == 0


async def test_si_tampoco_se_puede_preguntar_no_se_toca_nada(punto: PuntoDeVenta) -> None:
    """Un resultado desconocido que se deja quieto sigue siendo recuperable."""
    arca = ArcaFalso(consulta_caida=True)
    comprobante, comprobantes = await _emitido(punto, arca)

    resueltos = await _reconciliador(punto, comprobantes, arca).ejecutar(
        empresa_id=EMPRESA, ahora=MAS_TARDE
    )

    assert resueltos == []
    assert comprobante.esta_en_vuelo
    assert punto.ultimo_numero(TipoComprobante.FACTURA_A) == 1


async def test_un_comprobante_recien_enviado_no_se_reconcilia(punto: PuntoDeVenta) -> None:
    """La ventana existe para no arrebatarle el comprobante a la tarea que lo está
    esperando. Reconciliar dos segundos después sería competir con ella."""
    arca = ArcaFalso(registrado=None)
    comprobante, comprobantes = await _emitido(punto, arca)

    resueltos = await _reconciliador(punto, comprobantes, arca).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(seconds=2)
    )

    assert resueltos == []
    assert comprobante.esta_en_vuelo


async def test_reconciliar_dos_veces_no_pisa_el_cae(punto: PuntoDeVenta) -> None:
    """Idempotencia, y viene de que `AUTORIZADO → AUTORIZADO` no está en la tabla.

    Sin eso, un barrido que corre dos veces reemplazaría el código legal por otro.
    """
    arca = ArcaFalso(registrado=RespuestaDeArca(autorizado=True, cae=UN_CAE))
    comprobante, comprobantes = await _emitido(punto, arca)
    reconciliador = _reconciliador(punto, comprobantes, arca)

    await reconciliador.ejecutar(empresa_id=EMPRESA, ahora=MAS_TARDE)
    segunda = await reconciliador.ejecutar(empresa_id=EMPRESA, ahora=MAS_TARDE)

    assert segunda == []
    assert comprobante.cae == UN_CAE
