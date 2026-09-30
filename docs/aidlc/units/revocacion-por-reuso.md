# Unidad: revocacion-por-reuso

**HUs**: HU-E1-01 (la detección de reuso de ADR-011 que esa historia entregó) **Contexto dueño**: identity **Rama**: fix/identity-revocacion-por-reuso

> Origen: hallazgo de seguridad por lectura de código, **anterior a esta unidad** (existe desde el
> commit `1d48d21`, 2026-08-13, `identidad-y-onboarding`). Es un `fix/…` cortado de `develop`, **no** de
> la cadena de ramas de las unidades en curso: el PR va a `develop` y no depende de ninguna de ellas.

## Qué hace

La detección de reuso de un refresh token (ADR-011) **no funciona**: cuando llega un token ya usado,
`RefrescarSesion` revoca la familia y levanta `ReusoDeRefreshDetectado`, pero la transacción se
descarta y la revocación se pierde. Quien robó un refresh token y lo reusa recibe el error, pero
**conserva su sesión** (el token hijo sigue vivo), y la víctima también. Esta unidad hace que la
revocación de la familia se **confirme en la base** antes de responder el error.

Comportamiento observable después del fix: reusar un refresh ya rotado responde **el mismo error de
hoy** (sin cambio de contrato), pero **todos los tokens de esa familia quedan revocados en la base**: el
token hijo ya no refresca y ambas partes tienen que volver a iniciar sesión.

**Fuera de esta unidad:**
- Cambiar la semántica de `sesion_de_empresa` / `unidad_de_trabajo` (ver opción C, descartada).
- Los otros lugares con la misma clase de bug que **no** son de seguridad de sesión (ver «Radio de
  impacto»): se reportan, no se arreglan acá.
- La carrera de dos refresh **simultáneos** con el mismo token (ver «Preguntas abiertas», P3).
- `revocacion-inmediata-de-sesion` (HU-E1-05/06) es otra unidad, pendiente. Toca la misma zona
  (`sesiones.py`, `auth.py`) pero es de otro mecanismo (consultar al usuario en cada request).

## El bug, con evidencia

Ruta `POST /auth/refresh` (`api/routers/auth.py`, ~235-253):

```python
async for unidad in unidad_de_trabajo(recursos, empresa_id):
    ...
    sesion = await RefrescarSesion(...).ejecutar(...)   # revoca la familia y LEVANTA
```

`unidad_de_trabajo` (`api/dependencies.py:109`) es un generador asíncrono que hace
`yield` **dentro** de `sesion_de_empresa` (`platform/database.py:158`), y ese hace el `commit()`
justo **después** del `yield`. Cuando el cuerpo del `async for` lanza, la excepción ocurre en el
**consumidor**: el generador nunca se reanuda, no llega a `commit()`, y el cierre de la sesión hace
rollback implícito. `revocar_familia` hizo `UPDATE … SET revocado = true` + `flush()`, nunca `commit()`:
el `UPDATE` se pierde.

Por qué nadie lo vio: el único test de la regla es unitario con fakes
(`tests/contexts/identity/application/test_registro_y_sesiones.py::test_reusar_un_refresh_revoca_toda_la_familia`);
los fakes no tienen transacción. Ningún test de integración reusa un refresh.

## Diseño

### Opciones consideradas

| | Opción | A favor | En contra |
|---|---|---|---|
| **A** | El caso de uso **devuelve** un resultado (`Sesion` o `ReusoDetectado`) en vez de levantar; el router levanta después del bucle | El tipo obliga al llamador a decidir; sin excepciones para control de flujo | Cambia el contrato del caso de uso y su test; el caso de uso ya expresa bien «esto es un error» |
| **B** | El router **atrapa** `ReusoDeRefreshDetectado` dentro del cuerpo del `async for`, deja que el generador termine (commit) y **relevanta después del bucle** | Cambio mínimo (~6 líneas) en el único lugar que conoce la frontera transaccional; el caso de uso y su test unitario no cambian; el contrato HTTP no cambia | Es una convención que hay que recordar → se documenta en `unidad_de_trabajo` y la protege el test de integración |
| **C** | Cambiar `sesion_de_empresa`/`unidad_de_trabajo` para que confirmen ante ciertos errores | Arregla la clase entera | Toca ~166 callers; confirmar ante un `ErrorDeDominio` rompe la atomicidad de todos los casos de uso que escriben y luego validan (persistirían escrituras parciales). **Descartada** |
| **D** | Transacción aparte para la revocación (segunda sesión) | La revocación sobrevive a cualquier rollback de la primera | Dos transacciones, más piezas, y hoy no hay nada más que revertir en esa ruta |

### Recomendación: **B**

La frontera de la transacción es del router (la capa de aplicación no ve la sesión, R2), así que ahí
es donde corresponde decidir «confirmá y después fallá». B no toca el caso de uso ni su contrato, y
deja el error HTTP idéntico. A es válida, pero mueve una decisión de HTTP al tipo de retorno de un
caso de uso solo para esquivar una convención que un docstring y un test ya cubren.

### Cambio concreto (opción B)

- `api/routers/auth.py`, ruta `/refresh`:
  ```python
  reuso: ReusoDeRefreshDetectado | None = None
  salida: SesionSalida | None = None
  async for unidad in unidad_de_trabajo(recursos, empresa_id):
      piezas = Identidad.armar(unidad, recursos.settings)
      try:
          sesion = await RefrescarSesion(...).ejecutar(...)
      except ReusoDeRefreshDetectado as detectado:
          # La revocación de la familia ya se escribió: hay que confirmarla. Levantar acá
          # descartaría la transacción y el ladrón conservaría su sesión.
          reuso = detectado
      else:
          salida = await _salida_de(piezas, empresa_id, sesion)
  if reuso is not None:
      raise reuso
  return _exigir(salida)
  ```
  Solo se atrapa `ReusoDeRefreshDetectado` (no `SesionInvalida` ni `Exception`): los demás rechazos no
  escribieron nada y siguen descartando la transacción como hasta hoy. Se cuida la complejidad
  ciclomática de `_rutas_de_sesion` (límite 10, ruff C901): si la supera, la ruta se extrae a una
  función privada.
- `api/dependencies.py`: solo el **docstring** de `unidad_de_trabajo`, que documenta la trampa: «una
  excepción en el cuerpo descarta la transacción; para confirmar una escritura y después fallar, atrapar
  dentro del cuerpo y relevantar después del bucle».
- **Sin cambios**: `RefrescarSesion`, el repositorio, `sesion_de_empresa`, el schema, el frontend/BFF.

### Otros contextos · Frontend
No aplica. El código HTTP y el cuerpo del error no cambian (`ReusoDeRefreshDetectado` hereda de
`SesionInvalida` → `ErrorDeDominio`; hoy `api/errors.py` lo mapea al 409 por defecto).

## Radio de impacto — la misma clase de bug en otros lugares

Búsqueda: casos de uso de `application/` que escriben y después levantan, bajo `unidad_de_trabajo`. Los
routers no atrapan estas excepciones, así que el `raise` cae en el consumidor y **todo lo escrito antes
se descarta**.

| Dónde | Qué se pierde | ¿Seguridad? |
|---|---|---|
| `identity/application/sesiones.py:148` (`RefrescarSesion`) | Revocación de la familia | **Sí** — esta unidad |
| `payments/application/cobros.py:415-427` (reembolso rechazado por MercadoPago) | El cobro guardado como «reembolso en proceso» (la propia nota del código dice que se persiste **antes** de pedirlo «para que quede rastro»), el `rechazar_reembolso` y el evento de auditoría con `Resultado.ERROR` | **No** de sesión. Sí de **integridad de la bitácora**: el intento rechazado no deja rastro, contradiciendo RN-03 y el comentario del propio código |
| `reporting/application/generacion.py:139-146` (`GenerarReporte`) | La fila del reporte en `FALLIDO` («que la fila quede en FALLIDO y no desaparezca», dice el comentario) | No. Funcional |
| `reporting/application/paquete.py:302-309` (paquete contable) | Solo un `logger.warning` y, si se agregó antes, la fila del paquete | No. Funcional/menor |

No se encontraron otros casos escritura → raise en `application/`. **Solo se revisó `application/` y las
rutas de `api/`**: las tareas de `workers/` usan el mismo `unidad_de_trabajo` y no se auditaron acá.

**No se amplía esta unidad.** Los tres últimos son el mismo mecanismo pero sin impacto de seguridad de
sesión; el de reembolso toca **dinero y auditoría** (contexto `payments`, otro dueño), así que amerita
su propia unidad `fix/payments-…`. Ver P2.

## Infraestructura
- **Migraciones · Trabajo asíncrono · Configuración · Integraciones externas**: **No aplica.**

## Riesgos que obligan a tests
- [ ] Toca dinero — no aplica
- [ ] Comprobantes fiscales — no aplica
- [ ] Webhook — no aplica
- [x] Datos por empresa (`empresa_id`) — la revocación corre bajo RLS con la empresa del token; se prueba
      que reusar un token de una empresa **no** revoca familias de otra
- [ ] Salida de un LLM — no aplica
- [ ] Datos personales a un LLM — no aplica
- [x] **Seguridad de sesión (ADR-011)** — el test de integración contra PostgreSQL es el que importa:
      el unitario con fakes ya existía y pasaba con el bug presente

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/api/routers/auth.py` (ruta `/refresh`)
- [x] `backend/src/cheatsheet/api/dependencies.py` (solo docstring de `unidad_de_trabajo`)
- [x] `backend/tests/integracion/test_api_sesiones.py` (nuevo)
- [x] `backend/tests/api/test_refresh_confirma_la_revocacion.py` (nuevo, unitario local)

### Docs
- [ ] `docs/aidlc/units.md` (fila nueva de la unidad, ver Registro)

Sin cambios en `RefrescarSesion` ni en el frontend.

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código, **por el motivo
correcto** (el hijo sigue refrescando / la familia sigue sin revocar), no por un error de armado del test.

Los de integración usan `httpx.ASGITransport` contra la app real y PostgreSQL con RLS, como
`test_api_usuarios.py`: `POST /auth/registro` da el refresh inicial `R0`; `engine_dueno` (dueño de las
tablas, sin RLS) sirve para **mirar la base** sin pasar por el código bajo prueba.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED**: `R0` → refresh OK (`R1`); reusar `R0` → error de reuso; **`R1` ya no refresca** (rechazado, no 200) | integración (PostgreSQL) | escrito, sin correr (sin Docker); corre en CI. RED contra PostgreSQL pendiente del CI sobre el commit del test solo |
| 2 | **RED**: tras el reuso, en la base **todas** las filas de `refresh_token` de esa familia tienen `revocado = true` (consulta directa con `engine_dueno`) | integración (PostgreSQL) | escrito, sin correr (sin Docker); corre en CI |
| 3 | El reuso responde el mismo código y `error = "ReusoDeRefreshDetectado"` que hoy (el contrato no cambia) | integración (API) | escrito, sin correr (sin Docker); va dentro del caso 1 (409 + `ReusoDeRefreshDetectado`) |
| 4 | Otra sesión del mismo usuario (segundo `login`, otra familia) **sigue viva** tras el reuso de la primera | integración (PostgreSQL) | escrito, sin correr (sin Docker); corre en CI |
| 5 | Reusar un token de la empresa A no revoca nada de la empresa B (RLS) | integración (PostgreSQL) | escrito, sin correr (sin Docker); corre en CI |
| 6 | Reusar un token ya revocado por reuso otra vez → sigue rechazado, idempotente, sin 500 | integración (PostgreSQL) | escrito, sin correr (sin Docker); corre en CI |
| 7 | Un refresh desconocido / vencido sigue descartando la transacción y responde su error de siempre (no se atrapó de más) | integración + unit | integración escrita, sin correr (sin Docker). Unit: verde (rechazo `SesionInvalida` no confirma) |
| 8 | **RED**: a nivel router, con `unidad_de_trabajo` reemplazada por un doble que replica el contrato de `sesion_de_empresa` (confirma **solo si el cuerpo termina sin excepción**) y `RefrescarSesion` reemplazada por un doble que levanta `ReusoDeRefreshDetectado`: el doble **confirmó** y la respuesta es el error de reuso | unit (corre local, sin Docker) | **RED observado** (`confirmo=False`, 1 failed) antes del fix; **GREEN observado** después (3 passed) |
| 9 | Guardia del doble del caso 8: con un cuerpo que levanta, el doble **no** confirma (demuestra que el doble modela el bug y que el RED es real) | unit (local) | verde (pasa antes y después del fix; el doble no confirma si el cuerpo levanta) |
| 10 | El test unitario existente `test_reusar_un_refresh_revoca_toda_la_familia` sigue en verde sin cambios | unit | verde en la suite completa (sin cambios) |

**Sobre el test local (8-9).** No hay Docker acá, así que 1-7 se validan recién en CI. El 8 lo cubre en
parte: no prueba PostgreSQL, prueba que **el router deja terminar el generador** cuando hay reuso. Su
límite es que el doble reproduce a mano el contrato de `sesion_de_empresa`; por eso el 9, y por eso los
casos 1-2 contra la base real son los que cierran el hallazgo. Mientras no haya Docker, la evidencia local
del RED es el 8 en rojo; el RED contra PostgreSQL lo confirma la primera corrida de CI **sobre el commit
del test solo** (el commit del test va antes que el del fix en la historia de la rama).

## Gate 2 — verificación (además de los comandos del repositorio)

```bash
ruff format --check . && ruff check . && mypy . && pytest
```
(El frontend no cambia; los comandos de `npm` no aplican salvo que el CI los pida.)

- **Verificador independiente (identity/auth)**: un subagente que **no escribió el fix** revisa el diff
  contra ADR-011 y responde: (1) ¿toda ruta que detecta reuso confirma la revocación antes de responder?;
  (2) ¿se atrapa **solo** `ReusoDeRefreshDetectado` y nada que oculte errores?; (3) ¿el código HTTP y el
  cuerpo son idénticos a los anteriores?; (4) ¿la revocación sigue acotada a la familia y a la empresa?;
  (5) ¿`/logout`, `/login`, invitaciones y Google callback tienen el mismo patrón escribe-y-levanta? (ya se
  buscó en `application/`; que lo confirme por su cuenta). Su informe se pega en el Registro.
- **CI**: los casos 1-7 corren solo allí (PostgreSQL). **El Gate 2 no se cierra sin el resultado verde del
  CI en esos casos**, y se reporta la salida real, no una suposición.
- Definition of Done (`CLAUDE.md` §7): sin secretos; sin integración nueva (`.env.example` no aplica);
  **sin ADR**: no hay decisión arquitectónica nueva, se cumple la ya tomada (ADR-011, que vive en los
  documentos de diseño de la Etapa 5; `docs/adr/` no la tiene).

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-30 | aprobado; las seis preguntas según la recomendación |
| 2 · Verificación | | |
| 3 · PR | 2026-09-30 | PR draft [#47](https://github.com/cheatsheet12/CheatSheet/pull/47) contra `develop`; draft para que la CI corra los casos 1 a 7 contra PostgreSQL |

Fila propuesta para `units.md` (épico existente «Cimientos, identidad y bitácora»; solo esa línea, como
`cancelacion-invalida-el-link`):

`| Cimientos, identidad y bitácora | revocacion-por-reuso | identity | HU-E1-01 | — | Luciano | fix/identity-revocacion-por-reuso | en curso |`

## Preguntas abiertas

1. **P1 — Opción de fix.** Recomendación: **B** (atrapar dentro del cuerpo, relevantar después del bucle).
   Alternativa razonable: A. ¿Vamos con B?
2. **P2 — Los otros hallazgos (reembolso rechazado, reportes fallidos).** Recomendación: **no** tocarlos
   acá; abrir una unidad `fix/payments-…` para el reembolso (dinero + auditoría) y dejar reportes para
   otra. ¿Las registro en `units.md` como unidades pendientes?
3. **P3 — Carrera de dos refresh simultáneos con el mismo token.** `buscar_por_hash` no toma `FOR UPDATE`,
   así que dos requests concurrentes pueden pasar ambas la verificación `fue_usado` y rotar las dos: el
   reuso queda sin detectar en esa ventana. Es otro bug del mismo control, **no** el que se arregla acá.
   Recomendación: dejarlo fuera y abrir una unidad aparte con su propio test de concurrencia.
4. **P4 — HU de la fila.** Recomendación: **HU-E1-01** (login + refresh + detección de reuso). ¿O va como
   unidad técnica sin HU?
5. **P5 — Fricción con `revocacion-inmediata-de-sesion`.** Esa rama ya existe con su plan y toca la misma
   zona. Recomendación: mergear este fix primero (es chico) y que esa unidad se sincronice con `develop`.
6. **P6 — Comunicación.** El bug existe desde 2026-08-13 y los reusos previos nunca revocaron nada.
   Recomendación: anotar en el PR que, tras el deploy en `staging`/`prod`, conviene revocar los refresh
   tokens vivos.

## Decisiones tomadas durante la unidad
- P1: opción B. La ruta `/refresh` atrapa `ReusoDeRefreshDetectado` dentro del cuerpo, deja que `sesion_de_empresa` confirme la revocación y lo relanza después del bucle. El caso de uso y el contrato HTTP no cambian.
- P2: el reembolso rechazado (payments) y el reporte fallido (reporting) no se tocan acá; se registran en `units.md` como unidades `fix/` pendientes.
- P3: la carrera de dos refresh simultáneos queda fuera; se registra como unidad pendiente con su propio test de concurrencia.
- P4: la fila va con HU-E1-01.
- P5: este fix se mergea antes que `revocacion-inmediata-de-sesion`.
- P6: el PR anota que, tras el deploy, conviene revocar los refresh tokens vivos.
