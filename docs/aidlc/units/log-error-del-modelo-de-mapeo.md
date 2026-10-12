# Unidad: log-error-del-modelo-de-mapeo

**HUs**: HU-E3-01   **Contexto dueño**: spreadsheet_sync
**Rama**: fix/spreadsheet_sync-log-error-del-modelo-de-mapeo

## Qué hace

Diagnóstico, no fix funcional todavía. Durante la prueba manual de HU-E3-01 (Etapa 6, responsable
Juan) se confirmó que `ANTHROPIC_API_KEY` no estaba cargada en staging — causa por la que el
mapeo asistido nunca proponía nada (corría el adaptador simulado, y sus coincidencias de texto
quedan por debajo de `UMBRAL_CONFIANZA_MEDIA = 0.75`, así que RN-03 las muestra como "Sin
asignar"). Se cargó la credencial en Render (`ANTHROPIC_API_KEY`, `LLM_ADAPTADOR=anthropic`,
`LLM_MODELO=claude-sonnet-5-5`) y se repitió la prueba: el adaptador real ahora **sí llama a la
API** (confirmado en el log de Render — `HTTP Request: POST https://api.anthropic.com/v1/messages
"HTTP/1.1 400 Bad Request"`), pero la llamada es rechazada con 400.

El código actual no deja ver **por qué** — `ModeloDeLenguajeAnthropic.proponer_mapeo` atrapa
cualquier `anthropic.AnthropicError` y solo loguea `modelo_sin_respuesta_para_el_mapeo` con la
cantidad de columnas, sin el mensaje ni el cuerpo del error que manda Anthropic. Sin eso, elegir
entre las hipótesis sobre qué parte de `ESQUEMA_DE_MAPEO` o del `output_config` rechaza la API es
adivinar.

**Esta unidad agrega el detalle al log que ya existe.** No cambia el schema, no cambia el
comportamiento de degradación (sigue devolviendo `()` y dejando todo "Sin asignar" ante cualquier
falla, que es RN-03) — solo hace visible el motivo exacto la próxima vez que falle, para poder
plantear el fix de verdad con evidencia y no por descarte.

## Diseño

- **Dominio**: no cambia.
- **Aplicación**: no cambia.
- **Puertos y adaptadores**: `backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/modelo.py`,
  método `ModeloDeLenguajeAnthropic.proponer_mapeo`. El `except self._errores_del_cliente as exc:`
  pasa a loguear, además de `columnas`: `status_code` (`getattr(exc, "status_code", None)`),
  `mensaje` (`getattr(exc, "message", str(exc))`) y `cuerpo` (`getattr(exc, "body", None)`,
  convertido a `str` y recortado — es el detalle de Anthropic sobre qué rechazó, nunca contiene
  datos de la empresa: Decisión D12 ya impide que una fila de cliente llegue al modelo). Nada de
  esto es información personal ni de negocio — son nombres de columna del propio pedido y el
  mensaje de error de un proveedor externo, así que no choca con `CLAUDE.md` §5 ("nunca loguear
  secretos ni datos personales").
- **Otros contextos**: ninguno.
- **Frontend**: no cambia.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica (la credencial ya se cargó en Render, fuera de este repo).
- **Integraciones externas**: no aplica — no se toca el cliente de Anthropic, solo qué se loguea
  del error que ya devuelve.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [ ] Agrega datos con `tenant_id`
- [ ] Usa salida de un LLM
- [ ] Datos personales o fiscales

Ninguno aplica directamente: es una línea de logging agregada a un `except` ya existente y ya
testeado (caso 9 de `mapeo-asistido.md`: "Un modelo caído deja todo sin asignar y no bloquea").

## Archivos a tocar

- [x] backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/modelo.py

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El test ya existente ("un modelo caído deja todo sin asignar y no bloquea") sigue en verde con el log ampliado | unit | aprobado |

No se agrega un test nuevo que afirme sobre el contenido exacto del log: es diagnóstico temporal,
no un contrato de comportamiento que valga la pena congelar en un test.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | aprobado |
| 2 · Verificación | 2026-10-12 | `ruff format --check .` (866 archivos), `ruff check .` y `mypy .` (861 archivos) verdes. `pytest` completo: 3269 passed, 654 skipped (necesitan Postgres/Redis locales). Sin cambios de frontend |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Encontrado y decidido en el momento durante la prueba manual de HU-E3-01 en staging — se
  prioriza ver el error real de Anthropic antes de proponer un fix de schema a ciegas.
