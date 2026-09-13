"""`FAQ` — una pregunta frecuente, y el vector con el que se la encuentra.

HU-E8-03 RN-02 pide que la búsqueda sea **por significado y no por coincidencia exacta de
palabras**: «¿cuánto sale un corte?» y «precio del corte» tienen que dar la misma respuesta.
Eso es una búsqueda vectorial, y el DER ya la previó — `embedding_vector vector(1536)` con
`pgvector`, más dos columnas que este archivo respeta y que valen la pena entender:

- **`embedding_modelo_version`** dice con qué modelo se calculó el vector. Sin eso, cambiar de
  modelo de embeddings dejaría la tabla con vectores de dos espacios distintos mezclados, y
  una búsqueda sobre esa mezcla devuelve resultados que parecen razonables y no lo son.

- **`embedding_obsoleto`** marca lo que hay que recalcular. Permite migrar de modelo sin
  recalcular todo de golpe: lo obsoleto se sigue sirviendo con su vector viejo hasta que el
  barrido lo alcance, que es mucho mejor que no responder nada.

**El umbral de similitud es una regla de negocio y vive acá.** Por debajo, el agente ofrece
derivar a una persona (RN-03) en lugar de contestar una FAQ que no venía al caso — que es la
falla que hace que alguien deje de usar el canal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

#: HU-E9-04, segundo criterio, palabra por palabra.
MENSAJE_CAMPOS_OBLIGATORIOS = "La pregunta y la respuesta son obligatorias."

#: Cuánta similitud hace falta para contestar con una FAQ en vez de ofrecer un asesor.
#:
#: 0.75 sobre similitud coseno es alto a propósito: el costo de los dos errores no es
#: simétrico. Contestar la FAQ equivocada le da al cliente una respuesta falsa con tono seguro;
#: ofrecerle un asesor de más le cuesta un mensaje. **El primero es peor**, así que el umbral
#: se pone donde falla hacia el segundo.
UMBRAL_DE_SIMILITUD = 0.75

#: La dimensión que el DER fija para la columna. Está acá para que el adaptador de embeddings
#: y la migración no puedan discrepar en silencio: un vector de otra dimensión es un `INSERT`
#: que falla, pero uno truncado sería una búsqueda que anda mal.
DIMENSION_DEL_VECTOR = 1536


@dataclass(slots=True)
class FAQ:
    """Una pregunta disparadora y su respuesta.

    `usos` es el contador de HU-E9-04 RN-02 («cuántas veces fue usada en el período») y de
    HU-E8-03 RN-04 («el sistema registra el uso de cada FAQ»). Es un contador y no una tabla
    de eventos porque las dos reglas piden un número, y una tabla de usos sería un dato que
    crece sin techo para contestar una pregunta que un entero contesta.
    """

    id: UUID
    empresa_id: EmpresaId
    pregunta: str
    respuesta: str
    categoria_id: UUID | None = None
    embedding_modelo_version: str | None = None
    #: `True` cuando el vector se calculó con un modelo que ya no es el vigente, o cuando la
    #: pregunta cambió y todavía no se recalculó. Ver el docstring del módulo.
    embedding_obsoleto: bool = True
    usos: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.pregunta.strip() or not self.respuesta.strip():
            # HU-E9-04, segundo criterio: la frase de la historia, letra por letra.
            raise EntradaInvalida(MENSAJE_CAMPOS_OBLIGATORIOS)

    def editar(self, *, pregunta: str, respuesta: str, momento: datetime) -> None:
        """Cambia el texto y **marca el vector como obsoleto si la pregunta cambió**.

        Cambiar la respuesta no invalida el vector —se busca por la pregunta— y por eso no lo
        marca: recalcular embeddings cuesta plata y una llamada de red, y hacerlo cuando no
        cambió nada de lo que se indexa es gastar las dos por nada.
        """
        if not pregunta.strip() or not respuesta.strip():
            raise EntradaInvalida(MENSAJE_CAMPOS_OBLIGATORIOS)
        if pregunta.strip() != self.pregunta:
            self.embedding_obsoleto = True
        self.pregunta = pregunta.strip()
        self.respuesta = respuesta.strip()
        self.updated_at = momento

    def marcar_indexada(self, version: str, momento: datetime) -> None:
        self.embedding_modelo_version = version
        self.embedding_obsoleto = False
        self.updated_at = momento

    def registrar_uso(self) -> None:
        """HU-E8-03 RN-04. Se llama cuando el agente **contestó** con esta FAQ.

        No cuando la encontró: una FAQ que quedó por debajo del umbral no se usó, y contarla
        haría que el número de HU-E9-04 RN-02 dijera algo distinto de lo que la pantalla
        promete.
        """
        self.usos += 1


@dataclass(frozen=True, slots=True)
class CoincidenciaDeFAQ:
    """Una FAQ encontrada, con cuánto se parecía.

    La similitud viaja con la FAQ y no se descarta en el repositorio, porque quien decide si
    alcanza es el dominio (`UMBRAL_DE_SIMILITUD`) y no la consulta SQL: un umbral en el `WHERE`
    haría que cambiarlo fuera cambiar una consulta, y que nadie pudiera ver qué tan cerca
    estuvo lo que se descartó.
    """

    faq: FAQ
    similitud: float

    @property
    def alcanza(self) -> bool:
        return self.similitud >= UMBRAL_DE_SIMILITUD
