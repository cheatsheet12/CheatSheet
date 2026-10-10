# Unidad: wamid-entrante-largo

**HUs**: HS-T2   **Contexto dueño**: conversational   **Rama**: fix/conversational-wamid-entrante-largo

> **Gate 1 aprobado el 2026-10-09.** Origen: TODO §22.58, registrado en el Gate 2 del tramo 1 de
> `entregas-de-whatsapp` (U7). **La entrada §22.58 todavía no está en `develop`**: vive en las ramas
> de U7 (`origin/feature/conversational-entregas-de-whatsapp-reintento` y `-avisos`,
> `docs/aidlc/TODO.md:683`) y llega a `develop` cuando U7 se mergee. Evidencia leída sobre
> `origin/develop` (`cc4fe5b`) y sobre `origin/feature/conversational-entregas-de-whatsapp-avisos`
> (`23c0880`).

## Qué hace

Un mensaje entrante de WhatsApp cuyo `id` (`wamid`) no entra en la columna (más de 160
caracteres) o viene vacío deja de producir un 500 que Meta reintenta: se descarta en el borde, con
un log sin datos personales, y la notificación contesta 200. Es el mismo trato que U7 ya les da a
los `statuses[]` con un id inutilizable.

**Fuera de esta unidad:**
- Ensanchar la columna `mensaje.externo_id` o cambiar `LARGO_MAXIMO_EXTERNO_ID` (ver D1).
- Los `wamid` salientes y los de `statuses[]`: U7 ya los cubre (`shared/externo_id.py`).
- Procesar imágenes, stickers o ubicaciones (pendiente del épico 8).

## Hallazgos

| Dónde (`origin/develop`) | Qué |
|---|---|
| `api/routers/whatsapp.py:215-220` | `_traducir` sólo exige que `id` sea `str`. No mira el largo ni que no esté vacío |
| `api/routers/whatsapp.py:238-239` | El `wamid` pasa tal cual a `MensajeEntrante.externo_id` |
| `contexts/conversational/infrastructure/models.py:89` · `migrations/versions/0021_agente_conversacional.py:200` | `mensaje.externo_id` es `String(160)` |
| `contexts/conversational/infrastructure/repositories.py:139-141` | `agregar` hace `flush()`: el `INSERT` con más de 160 caracteres falla ahí con un error de base no capturado → 500 |
| `contexts/conversational/application/agente.py:165,172,175` | Antes del `INSERT` ya corrieron `_resolver_cliente` (puede dar de alta un cliente) y `_texto_de` (**transcribe el audio contra el proveedor**). Todo se deshace, pero cada reintento de Meta vuelve a pagar la transcripción |
| `migrations/versions/0021_agente_conversacional.py:83-85` · `repositories.py:151-153` | El índice único excluye `externo_id = ''`, pero `buscar_por_externo_id('')` encuentra cualquier mensaje anterior con id vacío: un segundo entrante con id vacío se toma como **ya procesado** y se pierde en silencio |
| `contexts/conversational/application/ports.py:111` | `MensajeEntrante.externo_id: str` es la **clave de idempotencia** (D20), no un dato opcional |
| `shared/externo_id.py` (**sólo en ramas de U7**) | `LARGO_MAXIMO_EXTERNO_ID = 160` y `externo_id_o_ninguno`. No existe en `develop` |
| `api/whatsapp_notificaciones.py:138-141` (rama `-avisos`) | Precedente de U7: un id de `statuses[]` vacío o de más de `LARGO_MAXIMO_EXTERNO_ID` se descarta (`return None`) |
| `api/routers/whatsapp.py:325-331` (rama `-avisos`) | U7 no cambia `_traducir`: el defecto sigue después de U7 |

**Por qué no sirve `externo_id_o_ninguno` tal cual, como sugiere §22.58.** Devuelve `None` para un
id largo. En el entrante, `None` no es «sin estado de entrega» como en el saliente: es **sin
idempotencia**. Cada reintento de Meta procesaría el mensaje otra vez (otra respuesta del agente,
otra reserva de turno). Se reusa la **constante** de ese módulo, no la función.

## Dependencias y orden de migraciones

- **Depende de U7 mergeada** (`shared/externo_id.py`, y U7 modifica `api/routers/whatsapp.py`
  con +146 líneas). Cortar de `develop` después del merge de U7 evita el conflicto y la constante
  duplicada.
- **Migración: ninguna** con la opción recomendada (D1). Si se eligiera ensanchar la columna, la
  migración encadena después de la última de U8: hoy `develop` termina en `0036`; U6/U7/U8 se
  renumeran a `0037..0041`; esta sería la `0042`, con `down_revision` igual a la última de U8, y
  habría que tocar también `recordatorio.externo_id` (comparten la constante).

## Diseño

- **Dominio**: sin cambios.
- **Aplicación**: sin cambios. `ProcesarMensajeEntrante` sigue confiando en que `externo_id` es una
  clave válida; el borde es quien lo garantiza (único productor: `whatsapp.py:238`).
- **Adaptador de entrada** (`api/routers/whatsapp.py`, `_traducir`): si `id` no es `str`, está
  vacío o supera `LARGO_MAXIMO_EXTERNO_ID`, devuelve `None` y registra
  `whatsapp_id_entrante_inutilizable` con el **largo** y el motivo — nunca el id, el teléfono ni el
  texto. El resto de la notificación se procesa y la respuesta es 200.
- **Otros contextos / frontend**: no aplica.

Consecuencia aceptada: un mensaje con id inutilizable se pierde. Meta no lo reenvía con otro id, y
procesarlo sin clave de idempotencia es peor (efectos duplicados). En la práctica un `wamid` real
ronda los 60 caracteres y el webhook está firmado (HMAC), así que el caso es de defensa.

## Infraestructura

- **Migraciones**: no aplica (ver D1).
- **Trabajo asíncrono / configuración / integraciones**: no aplica.

## Riesgos que obligan a tests

- [x] Consume un webhook → una notificación con un mensaje inutilizable y uno válido procesa el
      válido una sola vez y contesta 200.
- [x] Datos personales → el log del descarte no lleva id, teléfono ni texto.

## Archivos a tocar

- [x] `backend/src/cheatsheet/api/routers/whatsapp.py`
- [x] `backend/tests/api/test_webhook_entrante_robustez.py` (nuevo; mismo estilo que
      `test_webhook_estados_robustez.py` de U7, sin base)
- [x] `docs/aidlc/TODO.md` (§22.58 → resuelta) · `docs/aidlc/units.md` (fila)

## Casos de prueba (TDD: cada uno RED antes del cambio)

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — `id` de 161 caracteres: hoy pasa a `MensajeEntrante`; después, `_mensajes_de` lo omite | unit | hecho |
| 2 | `id` de exactamente 160 caracteres se procesa (borde) | unit | hecho |
| 3 | **RED** — `id` vacío: hoy pasa; después se omite | unit | hecho |
| 4 | Notificación con uno inutilizable y uno válido → 200 y el válido llega al caso de uso una vez | API (montaje en memoria) | hecho |
| 5 | El log del descarte lleva largo y motivo, y no lleva id, teléfono ni texto (`capture_logs`) | API | hecho |

## Decisiones para el responsable

| # | Pregunta | Recomendación |
|---|---|---|
| D1 | ¿Descartar en el borde, guardar un sustituto determinista (hash del id) o ensanchar la columna? | **Descartar.** Es el precedente de U7 para `statuses[]`, no lleva migración ni toca la constante compartida. El hash conserva el mensaje pero suma un id que no es el de Meta para un caso que no ocurre; ensanchar sólo corre el límite y obliga a una migración que encadena tras U8 |
| D2 | ¿Incluir el id vacío en la misma guarda? | **Sí.** Mismo borde, mismo trato que `statuses[]`, y hoy produce una pérdida silenciosa peor que el 500 |
| D3 | ¿Esperar a U7 o empezar ya definiendo la constante localmente? | **Esperar a U7.** Evita el conflicto en `whatsapp.py` y una segunda definición del 160 que `shared/externo_id.py` existe para evitar |

## Tamaño estimado

Chica: ~15 líneas de producción, ~80 de tests, docs. Un commit `fix(conversational): …`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-09 | Aprobado por Luciano con las recomendaciones D1–D3 |
| 2 · Verificación | 2026-10-09 | Aprobado por Luciano. RED observado en 4 de 5 casos; ruff, mypy, pytest y arquitectura en verde. El CI local completo se corre en el Gate 3, cuando U7 entre a `develop` |
| 3 · PR | 2026-10-10 | PR a develop, después de `entregas-de-whatsapp` (#122). GitHub Actions sin cuota hasta el 2026-11-01: verificado con el CI local (`backend/scripts/run_local_ci.py`), resumen en el PR |

## Decisiones tomadas durante la unidad

- D1: se descarta en el borde, sin migración ni cambio de `LARGO_MAXIMO_EXTERNO_ID`.
- D2: el id vacío entra en la misma guarda.
- D3: se implementa sobre el código de U7 (rama apilada sobre el tramo iii, `b4dc80a`); se mergea `develop` cuando U7 entre.

