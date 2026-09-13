"""`PaqueteContable` y el enlace del contador (HU-E10-04, HU-E10-05, HU-E10-06).

**El token es toda la seguridad que hay.** El contador entra sin cuenta, desde un mail, a datos
fiscales de una empresa. El DER lo dice con todas las letras y le da tres columnas para que eso
sea sostenible: `vencimiento`, `revocado` y `accesos`.

Este archivo trata esas tres como lo que son:

- **`revocado` corta de inmediato** (RN-03 de HU-E10-05 y RN-04 de HU-E10-06). No hay «revocado
  a partir de», no hay gracia: el enlace deja de funcionar en la consulta siguiente.
- **`vencimiento` existe aunque nadie lo revoque.** Un enlace a documentación fiscal que vive
  para siempre es un enlace que dentro de dos años sigue en la bandeja de alguien que ya no es
  el contador de esa empresa.
- **`accesos` se cuenta** (RN-03 de HU-E10-06). Es lo que hace auditable un acceso sin cuenta:
  la única forma de saber si el enlace se usó, y cuántas veces.

**El valor del token no se guarda en claro.** Se guarda su hash, como los refresh tokens del
épico 1: una base filtrada no puede convertirse en accesos a la documentación fiscal de todas
las empresas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: HU-E10-04, HU-E10-05 y HU-E10-06, palabra por palabra.
MENSAJE_SIN_EMAIL = "Debe indicar el email del contador para activar el envío automático."
MENSAJE_EMAIL_INVALIDO = "Ingrese un email válido."
MENSAJE_ACCESO_NO_DISPONIBLE = "El acceso a este paquete ya no está disponible."

#: Cuánto vive un enlace del contador. Un mes cubre el ciclo contable con margen; más largo
#: sería un enlace que sobrevive al vínculo comercial que lo justificó.
VIGENCIA_DEL_ENLACE = timedelta(days=30)

#: El día del mes en que sale el paquete, si nadie dice otra cosa (HU-E10-04 RN-02).
#:
#: El 5: el mes anterior ya está cerrado y todavía hay tiempo antes de los vencimientos
#: fiscales. El 1 llegaría con comprobantes del último día sin conciliar.
DIA_DE_ENVIO_POR_DEFECTO = 5


class ContenidoDelPaquete(StrEnum):
    """Qué puede llevar adentro (HU-E10-04 RN-03), en las palabras de la historia."""

    FACTURAS = "FACTURAS"
    NOTAS_DE_CREDITO = "NOTAS_DE_CREDITO"
    REPORTE_DE_COBROS = "REPORTE_DE_COBROS"
    LOG_DE_OPERACIONES = "LOG_DE_OPERACIONES"
    RESUMEN_EJECUTIVO = "RESUMEN_EJECUTIVO"


#: Lo que lleva un paquete que nadie configuró. Los cinco: el contador pidió el paquete
#: contable, no una parte de él, y quitar cosas es una decisión que alguien tiene que tomar
#: explícitamente.
CONTENIDO_COMPLETO = frozenset(ContenidoDelPaquete)


@dataclass(slots=True)
class ConfiguracionDelPaquete:
    """Cuándo, en qué formato y con qué contenido sale el paquete (HU-E10-04).

    **El DER no le da tabla a esto**, y la historia la pide entera: día de envío configurable,
    formato configurable, contenido configurable, y un email de contador sin el cual no se puede
    activar. Es el mismo tipo de hueco que H2 —una regla que exige persistir algo que el modelo
    no previó— y se resuelve igual: con la tabla que la regla necesita, declarada como decisión.

    **No se activa sin email** (tercer criterio, textual). Es una invariante del agregado y no
    una validación de pantalla: activar sin destinatario produce un envío mensual que no llega
    a ningún lado y que nadie nota hasta que el contador pregunta.
    """

    empresa_id: EmpresaId
    activo: bool = False
    dia_de_envio: int = DIA_DE_ENVIO_POR_DEFECTO
    formatos: frozenset[str] = field(default_factory=lambda: frozenset({"PDF"}))
    contenido: frozenset[ContenidoDelPaquete] = field(default_factory=lambda: CONTENIDO_COMPLETO)
    email_contador: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.dia_de_envio <= 28:
            # Hasta 28 y no 31: febrero existe, y un envío programado para el 30 no saldría
            # nunca en el mes que más importa cerrar a tiempo.
            raise EntradaInvalida("El día de envío va del 1 al 28")
        if not self.formatos:
            raise EntradaInvalida("El paquete necesita al menos un formato")
        if self.activo and not _email_valido(self.email_contador):
            raise InvarianteViolada(MENSAJE_SIN_EMAIL)

    def configurar(
        self,
        *,
        dia_de_envio: int,
        formatos: frozenset[str],
        contenido: frozenset[ContenidoDelPaquete],
        momento: datetime,
    ) -> None:
        self.dia_de_envio = dia_de_envio
        self.formatos = formatos
        self.contenido = contenido
        self.updated_at = momento
        self.__post_init__()

    def activar(self, momento: datetime) -> None:
        """Tercer criterio de HU-E10-04: sin email del contador, no se activa."""
        if not _email_valido(self.email_contador):
            raise InvarianteViolada(MENSAJE_SIN_EMAIL)
        self.activo = True
        self.updated_at = momento

    def desactivar(self, momento: datetime) -> None:
        self.activo = False
        self.updated_at = momento

    def asignar_contador(self, email: str, momento: datetime) -> None:
        if not _email_valido(email):
            raise EntradaInvalida(MENSAJE_EMAIL_INVALIDO)
        self.email_contador = email.strip().lower()
        self.updated_at = momento

    def proximo_envio(self, ahora: datetime) -> datetime | None:
        """Cuándo sale el próximo (segundo criterio de HU-E10-04). `None` si está desactivado.

        Si el día de este mes ya pasó, es el del mes que viene. La hora es la medianoche de la
        zona del servidor: el paquete lo arma un barrido, no una persona esperando.
        """
        if not self.activo:
            return None
        candidato = ahora.replace(day=self.dia_de_envio, hour=0, minute=0, second=0, microsecond=0)
        if candidato <= ahora:
            adelante = candidato.replace(day=1) + timedelta(days=32)
            candidato = adelante.replace(day=self.dia_de_envio, hour=0, minute=0, second=0)
        return candidato


@dataclass(slots=True)
class PaqueteContable:
    """La documentación fiscal de un mes cerrado.

    `totales_por_tipo` es el `jsonb` del DER: cuántos comprobantes de cada tipo y por cuánto.
    Es lo que hace que el contador pueda verificar que el paquete está completo **sin abrir los
    archivos**, y lo que deja constancia de qué había cuando se armó.
    """

    id: UUID
    empresa_id: EmpresaId
    periodo_anio: int
    periodo_mes: int
    totales_por_tipo: dict[str, dict[str, str]] = field(default_factory=dict)
    referencia_archivo: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.periodo_mes <= 12:
            raise EntradaInvalida("El mes va de 1 a 12")

    @property
    def etiqueta(self) -> str:
        return f"{self.periodo_anio}-{self.periodo_mes:02d}"

    @property
    def esta_disponible(self) -> bool:
        return self.referencia_archivo is not None

    def registrar_totales(self, tipo: str, cantidad: int, total: Decimal) -> None:
        """Cuántos comprobantes de un tipo y por cuánto.

        El total viaja como **texto** dentro del JSONB. Un `float` en un `jsonb` está mal en el
        cuarto decimal, que es donde vive un centavo, y `CLAUDE.md` §3.5 lo prohíbe en todo el
        sistema — incluida una columna que «sólo se muestra».
        """
        self.totales_por_tipo[tipo] = {"cantidad": str(cantidad), "total": str(total)}


@dataclass(slots=True)
class TokenDeAccesoContable:
    """El enlace del contador. Ver el docstring del módulo.

    `valor_hash` y no `valor`: lo que se guarda es el hash, y el valor en claro existe una sola
    vez, en el mail que sale. Es la misma decisión que el épico 1 tomó con los refresh tokens.
    """

    id: UUID
    paquete_id: UUID
    empresa_id: EmpresaId
    valor_hash: str
    email_contador: str
    vencimiento: datetime
    accesos: int = 0
    revocado: bool = False
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not _email_valido(self.email_contador):
            raise EntradaInvalida(MENSAJE_EMAIL_INVALIDO)

    def esta_vigente(self, ahora: datetime) -> bool:
        """Las dos condiciones, y en este orden: revocado primero porque es instantáneo."""
        return not self.revocado and ahora < self.vencimiento

    def registrar_acceso(self, ahora: datetime) -> None:
        """HU-E10-06 RN-03. **Levanta si no está vigente**, en lugar de contar y negar después.

        Contar un acceso que no ocurrió haría que el número dejara de significar «cuántas veces
        el contador entró», que es lo único para lo que sirve.
        """
        if not self.esta_vigente(ahora):
            raise InvarianteViolada(MENSAJE_ACCESO_NO_DISPONIBLE)
        self.accesos += 1

    def revocar(self) -> None:
        """HU-E10-05 RN-03: invalida el enlace **de inmediato**.

        Sin momento y sin estado intermedio: la revocación no se programa. Un `revocado_el` en
        el futuro sería una ventana en la que el enlace sigue sirviendo después de que alguien
        apretó «revocar», que es exactamente lo que ese botón promete que no pasa.
        """
        self.revocado = True


def _email_valido(email: str | None) -> bool:
    """Lo mínimo que hace que un mail pueda salir: algo, arroba, algo con punto.

    Deliberadamente laxo, por lo mismo que `Telefono` en el épico 1: rechazar el mail real de
    un contador es una falla peor que aceptar uno que después rebota. Quien decide de verdad es
    el servidor SMTP.
    """
    if email is None:
        return False
    limpio = email.strip()
    if "@" not in limpio or limpio.startswith("@") or limpio.endswith("@"):
        return False
    dominio = limpio.rsplit("@", 1)[1]
    return "." in dominio and not dominio.startswith(".") and not dominio.endswith(".")


__all__ = [
    "CONTENIDO_COMPLETO",
    "DIA_DE_ENVIO_POR_DEFECTO",
    "MENSAJE_ACCESO_NO_DISPONIBLE",
    "MENSAJE_EMAIL_INVALIDO",
    "MENSAJE_SIN_EMAIL",
    "VIGENCIA_DEL_ENLACE",
    "ConfiguracionDelPaquete",
    "ContenidoDelPaquete",
    "PaqueteContable",
    "TokenDeAccesoContable",
]
