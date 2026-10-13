# Unidad: agenda-con-una-sola-fecha

**HUs**: HU-E7-01   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-agenda-con-una-sola-fecha

> Origen: issue #85 (Luciano, 05/10/2026), reconfirmado en la prueba manual de la Etapa 6 del
> 12/10/2026 (comentario en #85). Severidad: Menor según el issue; en la vista Lista es el único
> filtro de fechas que hay. Es un `fix/…` cortado de `develop` (`9676a1f`); el PR va a `develop`.

## Qué hace

En la vista Lista de la agenda, el filtro «Más filtros › Desde / Hasta» da resultados equivocados
en tres casos. Esta unidad hace que el filtro por fechas funcione **por días completos, en la zona de
la agenda**:

| Se elige | Hoy | Después del fix |
|---|---|---|
| Solo «Desde» = 14/10 | vacío (rango invertido `[14/10, mañana)`) | ver P1 |
| Solo «Hasta» = 14/10 | desde **hoy** hasta el 14/10 a las 00:00 (el 14 queda afuera) | ver P1 |
| «Desde» = «Hasta» = 14/10 | vacío (`hasta` exclusivo: `[14/10 00:00, 14/10 00:00)`) | los turnos del 14/10 |
| «Desde» 12/10, «Hasta» 14/10 | 12 y 13; **el 14 queda afuera** | 12, 13 y 14 |

**Fuera de esta unidad:**
- Las vistas Día, Semana y Mes: ya mandan rangos completos con zona (`rangoDeVista`) y funcionan.
- La paginación de la agenda (pendiente 5 del épico 7).
- La vista por defecto «Mes» (#170): es decisión de diseño documentada en `agenda/page.tsx`.

## La historia

> **HU-E7-01 — Ver la agenda de turnos desde el panel**
>
> RN-01: La agenda puede visualizarse por recurso y por rango de fechas; la vista por defecto es el
> día en curso.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Abro la agenda | Veo los turnos del recurso y rango seleccionados con su estado | PAN-AGE-01 |

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `frontend/src/features/scheduling/components/BarraDeAgenda.tsx:182-192` | «Desde» y «Hasta» guardan la fecha tal cual (`"2026-10-14"`) |
| `frontend/src/features/scheduling/components/AgendaDelDia.tsx:91-97` | En la vista Lista los filtros viajan **sin convertir**; en las otras vistas se reemplazan por `rangoDeVista` |
| `frontend/src/features/scheduling/components/calendario.ts:98-117` | `rangoDeVista` ya arma rangos `[día T00:00-03:00, día siguiente T00:00-03:00)`, con `hasta` exclusivo |
| `backend/src/cheatsheet/api/routers/agenda_turnos.py:40-49` | `_rango`: con una sola punta completa la otra con **el día en curso**; con las dos, las usa tal cual |
| `backend/src/cheatsheet/api/routers/agenda_turnos.py:59-60` | `desde` y `hasta` son `datetime`: una fecha sola llega como medianoche **sin zona** |

El hueco tiene dos mitades: el frontend manda fechas donde la API espera instantes con `hasta`
exclusivo, y la API completa una punta faltante con «hoy» en lugar de con la fecha que sí llegó.

## Preguntas

1. **P1 — Qué muestra una sola fecha.** (La confirma una persona en el Gate 1.)

   | | Opción | A favor | En contra |
   |---|---|---|---|
   | **A** | Una sola fecha = **ese día completo** | Es la propuesta del issue #85; nunca trae una consulta sin tope (la agenda no pagina) | «Desde» solo no significa «en adelante» |
   | **B** | Solo «Desde» = de ese día **en adelante**; solo «Hasta» = **hasta** ese día inclusive | Es lo que sugiere la palabra | Consulta sin tope; con «Hasta» solo, ¿desde cuándo? |

   **Recomendación: A**, la del issue, porque la agenda no tiene paginación (pendiente 5 del épico 7).

   **Respuesta (Gate 1, 12/10/2026): A.**

## Diseño

- **Dominio**: no aplica.
- **Aplicación**: no aplica (`VerAgenda` y `FiltrosDeAgenda` no cambian).
- **API** (`agenda_turnos.py`, `_rango`), para que la API sea correcta aunque la llame otro cliente:
  - Una fecha **sin hora ni zona** se interpreta en la zona de la agenda (`ZONA_DE_LA_AGENDA`).
  - Con una sola punta, la otra se completa **desde esa punta** (opción A: `[desde, desde + 1 día)`
    o `[hasta − 1 día, hasta)`), nunca desde «hoy».
  - Sin ninguna punta: el día en curso, como hoy.
  - El contrato de los instantes no cambia: `hasta` sigue siendo exclusivo, y las vistas de
    calendario siguen mandando lo mismo.
- **Frontend** (`AgendaDelDia.tsx`, `parametrosDe`): en la vista Lista, las fechas elegidas se
  convierten en el mismo formato que ya usa `rangoDeVista`: «Desde» → `día T00:00:00-03:00`,
  «Hasta» → `día siguiente T00:00:00-03:00` (inclusivo para quien elige, exclusivo para la API).
  Con una sola fecha se manda ese día completo.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [ ] Datos con `empresa_id` → no cambia el aislamiento: el filtro sigue corriendo bajo RLS
- [ ] Usa salida de un LLM → no aplica
- [x] **Zona horaria**: un turno de las 22:00 es del día local aunque en UTC sea el siguiente (D34). Test con un turno nocturno en el borde del día.

## Archivos a tocar
- [x] backend/src/cheatsheet/api/routers/agenda_turnos.py (`_rango`)
- [x] backend/tests/api/test_rango_de_la_agenda.py (nuevo)
- [x] frontend/src/features/scheduling/components/AgendaDelDia.tsx (`parametrosDe`)
- [x] frontend/src/features/scheduling/components/calendario.ts (un helper del rango de días, junto a `rangoDeVista`)
- [x] frontend/src/features/scheduling/components/__tests__/… (tests del helper y del filtro)
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/agenda-con-una-sola-fecha.md

## Casos de prueba

Los casos 1 a 3 se escriben **antes** del arreglo y tienen que fallar con el código actual.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `_rango` con solo `desde` = 14/10 devuelve `[14/10 00:00, 15/10 00:00)` en la zona de la agenda (reproduce #85) | unit (pytest) | ✅ (falló antes del arreglo) |
| 2 | `_rango` con solo `hasta` devuelve el día anterior completo, no «desde hoy» | unit (pytest) | ✅ (falló antes del arreglo) |
| 3 | Una fecha sin zona se interpreta en la zona de la agenda, no en UTC | unit (pytest) | ✅ (falló antes del arreglo) |
| 4 | Sin puntas, sigue siendo el día en curso; con las dos, se usan tal cual | unit (pytest, regresión) | ✅ |
| 5 | En la vista Lista, «Desde» = «Hasta» = 14/10 pide `[14/10 T00:00-03:00, 15/10 T00:00-03:00)` | unit (vitest) | ✅ (falló antes: mandaba `"2026-10-14"` en crudo) |
| 6 | En la vista Lista, solo «Desde» = 14/10 pide ese día completo | unit (vitest) | ✅ |
| 7 | Las vistas Día, Semana y Mes siguen pidiendo lo mismo | unit (vitest, regresión) | ✅ (113 tests de agenda en verde) |
| 8 | Verificación manual en staging después del merge: «Desde» 14/10 muestra los turnos del 14 | manual | pendiente (después del merge) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | aprobado con la opción A de P1: una sola fecha = ese día completo |
| 2 · Verificación | 2026-10-13 | Backend: ruff ✔, mypy ✔ (862 archivos), pytest 3275 ✔ / 655 omitidos (sin PostgreSQL ni Redis locales). Frontend: lint ✔, typecheck ✔, 1429 tests ✔, cobertura 90,92 %. Hook de pre-commit ✔ con el arreglo de `mypy-en-pre-commit` |
| 3 · PR | 2026-10-13 | PR #203 a `develop`, apoyado en #202 (hook `mypy` de pre-commit). CI bloqueado por la facturación de Actions de la organización |

## Decisiones tomadas durante la unidad
- El test de la fecha sin zona arma el `datetime` con `fromisoformat` en lugar de silenciar la regla DTZ001 de ruff: es lo mismo que recibe FastAPI del query string.
- P1 → A: una sola fecha muestra ese día completo (Gate 1, 12/10/2026).
- La rama se apoya en `fix/infra-mypy-en-pre-commit`: el hook `mypy` de pre-commit fallaba en cualquier commit con Python (entorno aislado sin dependencias). Hasta que ese PR se mergee, este PR muestra también su commit.
- El fix va en las dos puntas: la API deja de completar con «hoy» (correcta para cualquier cliente) y el frontend manda días completos con zona, como ya hace `rangoDeVista`.
