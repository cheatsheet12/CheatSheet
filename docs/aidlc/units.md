# Mapa de unidades

> Las unidades de cada épico de [`roadmap.md`](roadmap.md), con su contexto dueño, sus historias,
> sus dependencias y su estado. Hay **un solo** archivo para todo el proyecto: cada sesión de mapeo
> agrega las filas de su épico. La columna `Épico` coincide **textualmente** con el nombre en el
> roadmap — eso es lo que ata los dos documentos.

Estados: `pendiente` · `en curso` · `en revisión` (PR abierto) · `mergeada`.
El estado del épico **se deriva** de estas filas; no se escribe en ningún lado.

| Épico | Unidad | Contexto dueño | HUs | Depende de | Responsable | Rama | Estado |
|---|---|---|---|---|---|---|---|
| Cimientos, identidad y bitácora | cimientos-y-bitacora | observability | HS-T5 | — | Cristian | — | pendiente |
| Cimientos, identidad y bitácora | identidad-y-onboarding | identity | HU-E1-01, HU-E1-02, HU-E1-03 | cimientos-y-bitacora | Cristian | — | pendiente |
| Cimientos, identidad y bitácora | usuarios-y-preferencias | identity | HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07 | identidad-y-onboarding | Cristian | — | pendiente |

---

## Épico 1 — Cimientos, identidad y bitácora

### Qué hace cada unidad

| Unidad | Alcance | Rama prevista |
|---|---|---|
| **cimientos-y-bitacora** | **Las seis unidades técnicas del roadmap §5, completas, más HS-T5.** Backend: composition root de FastAPI (`api/`), healthcheck y manejo uniforme de errores; `platform/settings.py` y sesión de base de datos; migraciones (Alembic); aislamiento multi-tenant con RLS por `tenant_id` (ADR-002); esqueleto de Celery + Beat con las cinco colas (ADR-003), `ClaveDeIdempotencia` y reintentos con backoff (ADR-009); esqueleto de tests (fixtures de base, factories, dobles de servicios externos) con el umbral del 80% corriendo en CI. Dominio: el agregado `RegistroDeAuditoria`, su tabla inmutable y el mecanismo por el que cualquier contexto publica un evento auditable (`observability` como OHS). Frontend: BFF de Next.js, cookie HttpOnly del JWT, layouts `(panel)` y `(public)`, wrapper de fetch y sistema de diseño mínimo. **Sin pantalla de negocio**: leer la bitácora es el épico 10 | `feature/infra-cimientos-y-bitacora` |
| **identidad-y-onboarding** | HU-E1-01, HU-E1-02 y HU-E1-03 — el onboarding entero de punta a punta: agregados `Empresa` y `Usuario`; alta con email/contraseña (Argon2id) y con OAuth2 de Google; login; JWT corto + refresh opaco rotativo con detección de reuso (ADR-011); aceptación de términos con versión y fecha; datos fiscales de la empresa con CUIT y `CondicionIVA` (ver D1); bloqueo del dashboard hasta completar los pasos 1 y 2. Pantallas PAN-ONB-01 y PAN-ONB-02 | `feature/identity-identidad-y-onboarding` |
| **usuarios-y-preferencias** | HU-E1-04, HU-E1-05, HU-E1-06 y HU-E1-07 — todo lo que un Administrador hace sobre los usuarios de su empresa, más lo que cada usuario hace sobre sí mismo: invitación por email y su aceptación, catálogo cerrado de tres roles con RBAC, cambio de rol, desactivación y reactivación, el invariante «siempre al menos un Administrador activo», y `pref_idioma` / `pref_zona_horaria` / `pref_suscripciones`. Pantallas PAN-USR-01 y PAN-USR-02 | `feature/identity-usuarios-y-preferencias` |

### Orden

```
cimientos-y-bitacora ── identidad-y-onboarding ── usuarios-y-preferencias
```

Cadena lineal, un responsable, sin paralelismo. Cada unidad deja la anterior demostrable: la primera
levanta el proceso y la bitácora, la segunda registra una empresa que ya audita cada operación, la
tercera opera sobre los usuarios de esa empresa.

### Notas

- **Unidades gruesas, deliberadamente.** Tres unidades para ocho historias, no ocho para ocho. El
  costo de cada unidad no es solo su código: son tres gates, un plan y un PR. Con historias de esta
  granularidad —HU-E1-03 son dos columnas y un checkbox; HU-E1-07 son tres campos— el plan llegaría
  a ser más largo que el diff, que es justamente el caso que el workflow manda resolver escribiendo
  una línea y ejecutando. Se agrupa por **pantalla y transacción compartida**: las dos pantallas del
  onboarding en una unidad, las dos de configuración de usuarios en otra.
- **El precio, dicho de frente:** los PRs son grandes, sobre todo el de `cimientos-y-bitacora`, y si
  el Gate 2 falla hay más superficie que desandar. Se acepta a cambio de tres ceremonias en lugar de
  ocho. Si una unidad se vuelve inmanejable durante la implementación, se dice y se re-corta el mapa
  con el equipo — nunca partiéndola dentro de la rama (regla 1c).
- **La bitácora entra en la unidad de cimientos y eso la mejora, no la infla.** HS-T5 no tiene
  pantalla y `observability` es OHS: no depende de nadie. Su tabla `registro_de_auditoria` es además
  la **primera tabla real** del sistema, o sea contra qué se prueban de verdad las migraciones, el
  RLS por `tenant_id` y las fixtures. Sin ella, los cimientos se verificarían contra nada. Y va
  antes que identity porque HU-E1-05 RN-04 y HU-E1-06 RN-02 exigen registro en el Log de
  Operaciones: si el sumidero llegara después, identity se entregaría con un criterio incumplido.
- **`cimientos-y-bitacora` cruza `observability` + `platform` + frontend.** Declara `observability`
  como contexto dueño porque es el único que recibe código de dominio; el resto es infraestructura
  sin dueño de negocio. La rama va bajo el módulo `infra` por la misma razón.
- **Trabajo en paralelo: no aplica.** Un solo responsable (Cristian). La regla 1c del workflow sigue
  vigente por si eso cambia.
- **Responsable declarado, rama no.** Cada fila fija su `Rama` al reclamarse (estado → `en curso`),
  no en el mapeo. La columna de arriba es la rama prevista, no la reclamada.

### Decisión D1 — resuelta

El roadmap §6 la dejaba abierta: HU-E1-02 RN-01 exige validar el CUIT contra ARCA en tiempo real
durante el onboarding, pero la credencial fiscal de la empresa recién se carga en el épico 2.

**Resolución (2026-08-12): validación estructural en el épico 1; consulta al padrón en el épico 2.**
`identidad-y-onboarding` valida formato y dígito verificador del CUIT, y `CondicionIVA` se elige
manualmente. No se introduce una credencial ARCA de plataforma.

Consecuencias, explícitas para que nadie las descubra después:

- El épico 1 **cierra con HU-E1-02 RN-01 parcialmente cumplida**. La autocompletación de
  `CondicionIVA` desde el padrón (criterio de aceptación 1 de HU-E1-02) tampoco se cumple todavía.
- **El épico 2 carga con completarla**: cuando HU-E2-01 deja la credencial de ARCA cargada y
  validada, se agrega la consulta de padrón al onboarding y a la edición de datos de la empresa.
  Eso se mapeará como unidad del épico 2, no acá.
- Un CUIT estructuralmente válido pero inexistente en ARCA **entra al sistema** hasta entonces. Es
  aceptable porque ningún comprobante se emite antes del épico 5, y la emisión revalida contra ARCA.

### Fuera de alcance de este épico

- Pantalla de la bitácora (HU-E12-01, HU-E12-02) → épico 10.
- Centro de notificaciones (HU-E11-03) → épico 10. Este épico solo envía el email de invitación.
- Cola de fallos DLQ (HS-T6) → épico 4.
- Consulta de CUIT al padrón de ARCA → épico 2, por D1.
