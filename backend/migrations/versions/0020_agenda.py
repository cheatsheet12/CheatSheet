"""recurso_reservable, su disponibilidad y turno — el épico 7 entero en una migración.

Cinco tablas juntas y no cinco migraciones, porque **un turno no significa nada sin el recurso
que lo presta ni sin el horario que lo hace posible**: separarlas daría cinco pasos de los que
sólo el último deja el sistema en un estado usable.

Tres cosas del esquema hacen trabajo que el código no puede hacer solo:

1. **`excl_turno_recurso_franja`** — la restricción de exclusión que impide el doble booking.
   Es la decisión **D28**, y es *la* razón por la que este épico existe sin miedo. Ninguna
   comprobación en Python la reemplaza: entre el `SELECT` que dice «libre» y el `INSERT` que
   reserva hay una ventana, y dos requests concurrentes caben en ella. Acá el motor compara
   los rangos dentro de la misma transacción y rechaza el segundo, siempre.

   Es **parcial**: sólo los turnos `RESERVADO` y `CONFIRMADO` ocupan la franja. Un turno
   cancelado la liberó y uno completado ya pasó; que siguieran bloqueando obligaría a mover un
   turno viejo para poder anotar una atención que sí ocurrió.

2. **`uq_excepcion_recurso_fecha`** — una sola excepción por recurso y fecha (HU-E7-05 RN-02).
   «Que contradiga otra existente» se resuelve garantizando que no haya dos, y eso lo sostiene
   el índice, no el `if` del agregado, que pierde contra dos pestañas abiertas.

3. **`ck_patron_horario`** — la hora de inicio es anterior a la de fin (HU-E7-04, criterio 3).
   El agregado ya lo impone con la frase de la historia; esto es lo que un bug futuro no puede
   saltear.

**Sin `DELETE` en las dos entidades del negocio.** Un turno se cancela —queda en la agenda con
su estado, que es lo que hace auditable la ocupación— y un recurso se desactiva (RN-03). Las
tres tablas hijas sí se borran, porque son partes de un agregado que se reemplaza entero: un
patrón sin recurso no es nada.

**La asimetría con `cobro` es del DER y es deliberada.** `turno.cobro_id` **sí** lleva FK y
`cobro.turno_id` **no** (hallazgo H4): el turno se creó primero, así que el cobro puede
apuntarlo sin que la FK ordene la creación al revés. En el código las dos direcciones cruzan
por id y sin join, que es lo que R3 pide.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un
# SQL interpolado se le parece a un escáner exactamente a la inyección que no es.
POLITICA_RECURSO = """
CREATE POLICY aislamiento_por_empresa ON recurso_reservable
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_TURNO = """
CREATE POLICY aislamiento_por_empresa ON turno
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: Las tres hijas no tienen `empresa_id` propio -- el DER no se lo da, y agregarlo sería una
#: segunda copia del mismo hecho que puede separarse. Se acotan por su padre, que RLS ya acota.
POLITICA_PATRON = """
CREATE POLICY aislamiento_por_recurso ON patron_de_disponibilidad
    USING (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = patron_de_disponibilidad.recurso_id))
    WITH CHECK (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = patron_de_disponibilidad.recurso_id));
"""

POLITICA_EXCEPCION = """
CREATE POLICY aislamiento_por_recurso ON excepcion_de_disponibilidad
    USING (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = excepcion_de_disponibilidad.recurso_id))
    WITH CHECK (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = excepcion_de_disponibilidad.recurso_id));
"""

POLITICA_SERVICIO_DE_RECURSO = """
CREATE POLICY aislamiento_por_recurso ON servicio_de_recurso
    USING (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = servicio_de_recurso.recurso_id))
    WITH CHECK (EXISTS (SELECT 1 FROM recurso_reservable r WHERE r.id = servicio_de_recurso.recurso_id));
"""

#: El rango de una franja, como función **inmutable**.
#:
#: Existe porque `timestamptz + interval` está marcado `STABLE` en PostgreSQL, y una
#: restricción de exclusión sólo acepta expresiones inmutables. La marca `STABLE` es correcta
#: en general —un intervalo con meses o días depende de la zona horaria— pero **no** para el
#: caso de acá: `n * interval '1 minute'` sólo tiene parte de tiempo, y sumarle tiempo a un
#: `timestamptz` es aritmética sobre el instante, independiente de la zona.
#:
#: Es decir: la función no está mintiendo para pasar el chequeo. Es inmutable de verdad, y
#: este comentario existe para que nadie la «arregle» aceptando un intervalo arbitrario.
FUNCION_FRANJA = """
CREATE OR REPLACE FUNCTION franja_de_turno(inicio timestamptz, duracion_min integer)
RETURNS tstzrange
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT tstzrange(inicio, inicio + (duracion_min * interval '1 minute'), '[)')
$$;
"""

#: **Decisión D28.** Ver el docstring del módulo.
#:
#: `[)` en el rango: un turno de 15 a 16 y otro de 16 a 17 conviven. Tiene que coincidir con
#: `Franja.se_solapa_con` del dominio — si dijeran cosas distintas, la pantalla y la base
#: darían respuestas opuestas sobre el mismo par de turnos.
EXCLUSION_SOLAPAMIENTO = """
ALTER TABLE turno ADD CONSTRAINT excl_turno_recurso_franja
EXCLUDE USING gist (
    recurso_id WITH =,
    franja_de_turno(franja_inicio, franja_duracion_min) WITH &&
)
WHERE (estado IN ('RESERVADO', 'CONFIRMADO'));
"""

#: HU-E7-05 RN-02, en el esquema.
INDICE_EXCEPCION = """
CREATE UNIQUE INDEX uq_excepcion_recurso_fecha
    ON excepcion_de_disponibilidad (recurso_id, fecha);
"""

#: Sin `DELETE` en `recurso_reservable` ni en `turno`. Ver el docstring del módulo.
RLS_Y_PERMISOS = (
    "ALTER TABLE recurso_reservable ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE recurso_reservable FORCE ROW LEVEL SECURITY",
    "ALTER TABLE patron_de_disponibilidad ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE patron_de_disponibilidad FORCE ROW LEVEL SECURITY",
    "ALTER TABLE excepcion_de_disponibilidad ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE excepcion_de_disponibilidad FORCE ROW LEVEL SECURITY",
    "ALTER TABLE servicio_de_recurso ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE servicio_de_recurso FORCE ROW LEVEL SECURITY",
    "ALTER TABLE turno ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE turno FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON recurso_reservable TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON turno TO cheatsheet_app",
    # Las tres hijas sí aceptan `DELETE`: son partes de un agregado que se reemplaza entero.
    "GRANT SELECT, INSERT, UPDATE, DELETE ON patron_de_disponibilidad TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON excepcion_de_disponibilidad TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON servicio_de_recurso TO cheatsheet_app",
    "GRANT EXECUTE ON FUNCTION franja_de_turno(timestamptz, integer) TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "recurso_reservable",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recurso_empresa_activo", "recurso_reservable", ["empresa_id", "activo"])

    op.create_table(
        "patron_de_disponibilidad",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recurso_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurso_reservable.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Lunes 0, domingo 6: el de Python, que es el que el dominio usa. El de PostgreSQL
        # empieza el domingo, y traducir en el repositorio es el seam donde una traducción a
        # medias corre la agenda un día entero.
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("duracion_slot_min", sa.Integer(), nullable=False),
        sa.CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_patron_dia"),
        sa.CheckConstraint("hora_inicio < hora_fin", name="ck_patron_horario"),
        sa.CheckConstraint("duracion_slot_min > 0", name="ck_patron_slot"),
    )
    op.create_index("ix_patron_recurso", "patron_de_disponibilidad", ["recurso_id", "dia_semana"])

    op.create_table(
        "excepcion_de_disponibilidad",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recurso_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurso_reservable.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(24), nullable=False),
        sa.Column("franja_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("franja_duracion_min", sa.Integer(), nullable=True),
        # Un bloqueo cierra el día entero y no lleva horario; una apertura especial lo exige.
        # Las dos formas a medias producirían filas que dos lectores interpretan distinto.
        sa.CheckConstraint(
            "(tipo = 'BLOQUEO' AND franja_inicio IS NULL AND franja_duracion_min IS NULL)"
            " OR (tipo = 'APERTURA_ESPECIAL' AND franja_inicio IS NOT NULL"
            " AND franja_duracion_min > 0)",
            name="ck_excepcion_forma",
        ),
    )

    op.create_table(
        "servicio_de_recurso",
        sa.Column(
            "recurso_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurso_reservable.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "servicio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("servicio.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "turno",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cliente.id"),
            nullable=False,
        ),
        sa.Column(
            "servicio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("servicio.id"),
            nullable=False,
        ),
        sa.Column(
            "recurso_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurso_reservable.id"),
            nullable=False,
        ),
        # HU-E6-07. Con FK, a diferencia de `cobro.turno_id`: ver el docstring del módulo.
        sa.Column(
            "cobro_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cobro.id"), nullable=True
        ),
        sa.Column("franja_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("franja_duracion_min", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("canal_reserva", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "franja_duracion_min > 0 AND franja_duracion_min <= 1440", name="ck_turno_duracion"
        ),
    )
    op.create_index("ix_turno_empresa_franja", "turno", ["empresa_id", "franja_inicio"])
    op.create_index("ix_turno_recurso_franja", "turno", ["recurso_id", "franja_inicio"])
    op.create_index("ix_turno_cliente", "turno", ["cliente_id"])

    op.execute(FUNCION_FRANJA)
    op.execute(EXCLUSION_SOLAPAMIENTO)
    op.execute(INDICE_EXCEPCION)
    op.execute(POLITICA_RECURSO)
    op.execute(POLITICA_PATRON)
    op.execute(POLITICA_EXCEPCION)
    op.execute(POLITICA_SERVICIO_DE_RECURSO)
    op.execute(POLITICA_TURNO)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_table("turno")
    op.drop_table("servicio_de_recurso")
    op.drop_table("excepcion_de_disponibilidad")
    op.drop_table("patron_de_disponibilidad")
    op.drop_table("recurso_reservable")
    # Después de las tablas: la restricción de exclusión depende de ella.
    op.execute("DROP FUNCTION IF EXISTS franja_de_turno(timestamptz, integer)")
