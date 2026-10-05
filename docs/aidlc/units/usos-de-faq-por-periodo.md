# Unidad: usos-de-faq-por-periodo

**HUs**: HU-E9-04 (enmendada por ADR-0012), HU-E8-03 RN-04 **Contexto dueño**: conversational (más una constante en `shared/`) **Rama**: feature/conversational-usos-de-faq-por-periodo

> Origen: B6 de la revisión de la fase C (`C:\Dev\traspasos\fase-c\plan-de-trabajo.md`, decisiones
> G3a y G3b, unidad U4). Salió de `ajustes-menores-del-agente`. **Depende del ADR-0012 aceptado**
> (enmienda de HU-E9-04): sin la enmienda, «este mes», «mes anterior», «total» y la participación son
> reglas que viven solo en este plan y que la verificación no puede contrastar con la historia
> (`CLAUDE.md` §0). No depende del canal real de WhatsApp (U5). Tamaño: M.

## Qué hace

Hoy PAN-WA-02 dice «Usos en el período» y muestra el total desde que la FAQ existe: `faq.usos` es un
entero sin fecha. Además se cuenta antes de mandar el WhatsApp (un envío fallido suma) y con una
lectura-modificación-escritura de toda la fila (dos respuestas simultáneas pierden un uso, y una
respuesta del agente que se cruza con una edición del administrador **le pisa la edición**). Esta
unidad registra cada uso como una fila inmutable en `faq_uso` —solo cuando el mensaje salió—, muestra
por FAQ «Este mes», «Mes anterior» y «Total» con los meses en hora de Argentina, y agrega un detalle
con la participación de la FAQ antes y después de su última edición.

**Fuera de esta unidad:**
- Los bugs de mes en UTC de payments y reporting (`docs/aidlc/TODO.md` §22.5 y §22.6): siguen siendo
  hallazgos sin unidad. Esta unidad deja la zona en `shared/`, que es lo que les faltaba (payments
  tampoco puede importar reporting), y lo anota en esas dos filas.
- Reapuntar `ZONA_DEL_REPORTE` (reporting) y `ZONA_DE_LA_AGENDA` (scheduling) a la constante nueva:
  sería tocar dos contextos que funcionan para ganar nada observable. Se anota en TODO §22.
- Que un fallo de entrega informado después por Meta (callbacks, U7) descuente el uso: no lo
  descuenta (ADR-0012, punto 1).
- La carrera «el administrador borra la FAQ en el mismo instante en que el agente la usa» más allá de
  lo que dice Riesgos (aceptada y documentada).
- La pérdida del registro cuando el `COMMIT` falla después de que el mensaje salió: es la misma de hoy
  para todo lo que hace el agente, y la trata el canal real (U5, ADR-0011).
- B5 y B7 (intención del entrante, pedido de persona): unidad `ajustes-menores-del-agente`.

## Lo que se encontró (evidencia)

| Dónde | Qué |
|---|---|
| `contexts/conversational/application/agente.py:327-331` | `_responder_faq` hace `mejor.faq.registrar_uso()` y `self._faqs.guardar(mejor.faq)` **antes** de `_responder`. Si `enviar` falla, `_responder` guarda el saliente `FALLIDO` y devuelve `None`, y el uso ya quedó contado |
| `contexts/conversational/infrastructure/repositories.py:207-212` · `354-365` | `guardar` hace `session.get` + `_faq_a_fila`, que copia **todas** las columnas (`pregunta`, `respuesta`, `embedding_obsoleto`, `usos`) desde el agregado leído. Dos respuestas concurrentes escriben `usos = n+1` las dos. Una edición del administrador confirmada entre la lectura del agente y su `COMMIT` se revierte |
| `contexts/conversational/domain/faq.py:51-55` · `95-102` | El docstring justifica el entero: «las dos reglas piden un número». Con la enmienda piden tres números y una comparación por ventanas: deja de ser cierto |
| `contexts/conversational/domain/faq.py:75-93` | `editar` pone `updated_at` aunque el texto no cambie, y `marcar_indexada` (barrido de embeddings) también lo pone. **`updated_at` no sirve como «última edición»**: hace falta `editada_en` |
| `migrations/versions/0021_agente_conversacional.py:83-85` | `uq_mensaje_externo_id (empresa_id, externo_id)`: la garantía contra el webhook repetido. `agente.py:143-144` lo consulta primero; un repetido concurrente choca con el índice en `_guardar_entrante` (paso 3), antes de llegar a la FAQ, y su transacción entera se revierte |
| `api/routers/whatsapp.py:128-163` | **Una transacción por mensaje entrante** (`unidad_de_trabajo`): el envío ocurre dentro de la transacción y el `COMMIT` viene después. Un `INSERT` en `faq_uso` dentro de esa transacción queda atómico con el saliente guardado |
| `migrations/versions/0021_agente_conversacional.py:144` | `faq` es la única tabla con `DELETE` para `cheatsheet_app`; `RepositorioFAQPostgres.eliminar` es un `DELETE` real (`repositories.py:218-221`) |
| `migrations/versions/0027_reembolsos.py:108-121` | El patrón de tabla inmutable: política `aislamiento_por_empresa`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, `REVOKE ALL` y `GRANT SELECT, INSERT` |
| `backend/scripts/verify_rls.py:104` · `200-212` | `_check_politicas` recorre **toda** tabla con columna `empresa_id` y exige política: `faq_uso` queda cubierta sin tocar el script |
| `contexts/reporting/infrastructure/acl.py:69` · `scheduling/domain/recurso.py:46` · `identity/domain/usuario.py:30` | La zona argentina está declarada tres veces; ninguna es importable desde conversational (R3) |
| `api/routers/conversaciones.py` (486 líneas) · `application/agente.py` (456) | Ya pasan las 400 de `CLAUDE.md` §5. Esta unidad no los agranda: las rutas de FAQ salen a su propio módulo, y en `agente.py` el cambio es neto ~+10 líneas, compensado por B7 de `ajustes-menores-del-agente`, que saca `PEDIDOS_DE_HUMANO` |
| `frontend/.../RespuestasFrecuentes.tsx:68` · `152-157` · `263-264` | Suma `usos` de todas las FAQ y la rotula «en el período»; columna «Usos en el período» |
| `docs/aidlc/inputs/prototipos/agente-whatsapp.html:301` | «Respondida 47 veces este mes»; el listado del prototipo está ordenado por ese número |

## Diseño

- **Dominio** (`contexts/conversational/domain/`):
  - `uso_de_faq.py` (nuevo, sin I/O ni framework, R1):
    - `UsoDeFAQ` (frozen): `id`, `empresa_id`, `faq_id`, `mensaje_id`, `usado_en`.
    - `ConteoDeUsos` (frozen): `este_mes`, `mes_anterior`, `desde_el_seguimiento`; y
      `total(usos_anteriores) = usos_anteriores + desde_el_seguimiento`.
    - `VENTANA_MAXIMA_DE_COMPARACION = timedelta(days=30)`.
    - `ventana_de_comparacion(*, editada_en, seguimiento_desde, ahora) -> VentanaDeComparacion |
      MotivoSinComparacion`: `L = min(30 d, días enteros desde editada_en, días enteros entre
      seguimiento_desde y editada_en)`. `editada_en is None` → `SIN_EDICIONES`; días desde la
      edición `< 1` → `EDICION_RECIENTE`; días previos `< 1` → `SIN_HISTORIA_PREVIA`. Si no, la
      ventana con `antes = [E − L, E)` y `despues = [E, E + L)`.
    - `Participacion` (frozen): `usos`, `total`; `porcentaje -> Decimal | None` (`None` si
      `total == 0`, «sin consultas respondidas por FAQ»), `quantize(Decimal("0.1"),
      ROUND_HALF_UP)`. No es dinero, pero un porcentaje que se redondea distinto en dos lugares es el
      mismo problema; se usa la misma regla.
  - `faq.py`:
    - `usos` pasa a `usos_anteriores` (línea de base congelada, nadie la incrementa) y se borra
      `registrar_uso`. Docstring reescrito: el porqué del entero deja de valer (ADR-0012).
    - Campos nuevos `editada_en: datetime | None` y `seguimiento_desde: datetime | None` (en
      `CrearFAQ` = `created_at`).
    - `editar` pone `editada_en = momento` **solo si cambió** la pregunta o la respuesta
      (comparando ya con `strip`). `updated_at` sigue como hoy.
- **Shared Kernel** (`shared/zona_horaria.py`, nuevo): `ZONA_ARGENTINA = ZoneInfo(
  "America/Argentina/Buenos_Aires")` y `MesCalendario` con `del_instante(ahora) ->
  MesCalendario` (`inicio`, `fin`, `anterior()`), todo en instantes UTC con zona. Es un value object
  transversal que ya necesitan tres contextos (R4: no importa nada de `contexts/`). Se agrega una
  línea al docstring de `shared/__init__.py` si enumera los módulos.
- **Aplicación** (`contexts/conversational/application/`):
  - `ports.py`: puerto nuevo `PortUsosDeFAQ`:
    - `registrar(uso: UsoDeFAQ) -> None` — idempotente por `mensaje_id`.
    - `conteos(mes: MesCalendario) -> dict[UUID, ConteoDeUsos]` — una consulta para todo el listado.
    - `contar(*, desde, hasta, faq_id: UUID | None) -> int` — `None` = todas las respuestas por FAQ
      de la empresa (incluye las de FAQ borradas).
    - `PortRepositorioFAQ.listar` deja de ordenar por `usos` (ordena por `created_at`); el orden por
      «Este mes» lo pone el caso de uso.
  - `agente.py`:
    - `ProcesarMensajeEntrante.__init__` recibe `usos: PortUsosDeFAQ`.
    - `_responder` se parte en `_enviar(...) -> Mensaje` (envía y guarda el saliente, como hoy) y
      `_responder`, que llama a `_enviar` y devuelve `texto | None` igual que ahora (los demás
      llamadores no cambian).
    - `_responder_faq`: sin `registrar_uso` ni `guardar`. Llama a `_enviar`; **si el saliente quedó
      `ENVIADO`**, `await self._usos.registrar(UsoDeFAQ(id=uuid4(), empresa_id=…, faq_id=
      mejor.faq.id, mensaje_id=saliente.id, usado_en=ahora))`. `usado_en = ahora` del reloj
      inyectado (el mismo instante que el `momento` del saliente).
  - `faqs.py`:
    - `ListarFAQs.ejecutar(*, ahora) -> list[FAQConUsos]` (modelo de lectura: `faq` + `conteo`),
      ordenado por `este_mes` desc, después total desc, después `created_at`.
    - `VerUsoDeFAQ.ejecutar(*, faq_id, ahora) -> DetalleDeUso` (nuevo): conteo, `editada_en`, y la
      comparación (`dias`, `antes: Participacion`, `despues: Participacion`) o el motivo. Cuatro
      `contar` (FAQ y empresa, por ventana). `FAQInexistente` si no está (mismo 404 que hoy).
    - `EditarFAQ` devuelve también su conteo (la respuesta HTTP lo lleva).
    - Todos los roles leen, como hoy `ListarFAQs` (sin cambio de autorización).
- **Puertos y adaptadores** (`contexts/conversational/infrastructure/`):
  - `models.py`: `FAQUsoORM` (tabla `faq_uso`) y en `FAQORM` `usos` → `usos_anteriores`, más
    `editada_en`, `seguimiento_desde`.
  - `repositories.py` → **módulo nuevo `usos_de_faq.py`** (`repositories.py` tiene 383 líneas):
    `RepositorioUsosDeFAQPostgres`:
    - `registrar`: `INSERT … ON CONFLICT (mensaje_id) DO NOTHING` (SQL explícito, literal).
    - `conteos`: un `SELECT faq_id, count(*) FILTER (WHERE usado_en >= :inicio AND usado_en < :fin)
      AS este_mes, count(*) FILTER (WHERE … mes anterior …), count(*) FROM faq_uso WHERE faq_id IS
      NOT NULL GROUP BY faq_id`. Los límites llegan como instantes UTC calculados en Python con
      `MesCalendario`: la consulta es comparable por índice y la lógica del mes se prueba sin
      PostgreSQL (no hay Docker local). RLS filtra la empresa.
    - `contar`: `count(*)` con `usado_en` en `[desde, hasta)` y, si viene, `faq_id`.
  - `_faq_a_fila`: en `guardar` **no** escribe `usos_anteriores` ni `seguimiento_desde` (solo en
    `agregar`). Nadie más que la migración escribe la línea de base.
  - `ensamblado.py`: `Conversaciones` suma `usos=RepositorioUsosDeFAQPostgres(unidad.sesion)`.
  - `api/routers/whatsapp.py`: pasa `usos=piezas.usos` a `ProcesarMensajeEntrante`.
- **Otros contextos**: ninguno. `shared/` no es un contexto; conversational importa
  `shared.zona_horaria`, que R1–R4 permiten. No hay arista nueva en el Context Map.
- **API** (`api/routers/respuestas_frecuentes.py`, nuevo; `conversaciones.py` deja de tener las rutas
  de FAQ y las monta desde ahí, mismo prefijo `/faqs`):
  - `FAQSalida`: `id`, `pregunta`, `respuesta`, `sin_indexar`, `usos_este_mes`,
    `usos_mes_anterior`, `usos_total`, `editada_en: datetime | None`. **Se quita `usos`** (el único
    consumidor es el panel, que se despliega junto; precedente: `fecha-de-pago`, pregunta 1).
  - `GET /faqs/{faq_id}/uso` → `DetalleDeUsoSalida`: los tres conteos, `editada_en`,
    `comparacion: {dias, antes: {usos, total, participacion}, despues: {…}} | null` y
    `motivo_sin_comparacion: "SIN_EDICIONES" | "EDICION_RECIENTE" | "SIN_HISTORIA_PREVIA" | null`.
    `participacion` es `Decimal | None` (viaja como texto, `"12.5"`); `None` = sin consultas en ese
    lapso.
  - `POST /faqs` responde con los tres conteos en cero; `PUT` con los suyos.
- **Frontend** (`features/conversational`):
  - `api/faq.ts`: `Faq` con `usos_este_mes`, `usos_mes_anterior`, `usos_total`, `editada_en`;
    `verUsoDeFaq(id)` y los tipos `DetalleDeUso`, `Comparacion`, `MotivoSinComparacion`; textos como
    constantes (`MENSAJE_SIN_EDICIONES`, `MENSAJE_EDICION_RECIENTE`, `MENSAJE_SIN_HISTORIA_PREVIA`,
    `MENSAJE_SIN_CONSULTAS`).
  - `components/RespuestasFrecuentes.tsx`: columnas «Este mes», «Mes anterior» y «Total» (al
    derecha) en lugar de «Usos en el período»; la barra dice «N usos este mes» (suma de
    `usos_este_mes`); acción «Ver uso» para **todos** los roles (la columna de acciones hoy existe
    solo para el Administrador: se separa «Ver uso» de «Editar/Eliminar»).
  - `components/DetalleDeUsoDeFaq.tsx` (nuevo; el componente ya tiene 319 líneas): tarjeta a la vista
    —mismo criterio que el formulario: no tapa el listado— con «Respondida N veces este mes» (la
    frase del prototipo), mes anterior, total, y «Participación: X % en los N días antes de la
    edición del DD/MM/AAAA · Y % en los N días después», o el texto del motivo. Formatea el
    porcentaje con `es-AR` («12,5 %») y la fecha en hora de Argentina con el formateador que ya
    exista en `shared/` (buscarlo antes de escribir uno). No calcula nada: muestra lo que da la API.
  - `app/api/faqs/[faqId]/uso/route.ts` (nuevo): reenvío `GET` al backend como los otros BFF.
  - `index.ts`: sin cambios (los tipos nuevos los usa solo la propia feature).

## Infraestructura

- **Migraciones**: una, con el **número libre al momento del merge**, encadenada al head de
  `develop` (hoy `0030`; `0031` reservada por `tipos-de-comprobante-por-receptor`). SQL literal,
  como 0027.
  1. `CREATE TABLE faq_uso (id uuid PRIMARY KEY, empresa_id uuid NOT NULL REFERENCES empresa (id) ON
     DELETE CASCADE, faq_id uuid NULL REFERENCES faq (id) ON DELETE SET NULL, mensaje_id uuid NOT
     NULL REFERENCES mensaje (id), usado_en timestamptz NOT NULL, CONSTRAINT uq_faq_uso_mensaje
     UNIQUE (mensaje_id))`.
  2. Índices: `ix_faq_uso_empresa_faq_usado (empresa_id, faq_id, usado_en)` (conteos por FAQ y
     total, recorrido solo de índice) e `ix_faq_uso_empresa_usado (empresa_id, usado_en)`
     (denominador de la participación).
  3. Política `aislamiento_por_empresa`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, `REVOKE ALL` y
     `GRANT SELECT, INSERT ON faq_uso TO cheatsheet_app`.
  4. `faq`: `RENAME COLUMN usos TO usos_anteriores` (y `ck_faq_usos` → `ck_faq_usos_anteriores`);
     `ADD COLUMN editada_en timestamptz NULL`; `ADD COLUMN seguimiento_desde timestamptz NOT NULL
     DEFAULT now()` y después `DROP DEFAULT` (las existentes quedan con el instante del despliegue,
     las nuevas las escribe la aplicación).
  - **Backfill**: no se inventa nada. `usos_anteriores` conserva el contador viejo; `editada_en`
    queda `NULL` (no hay forma honesta de saber la última edición: `updated_at` lo mueve también el
    barrido de embeddings), así que las FAQ existentes muestran «sin ediciones» hasta su próxima
    edición real. `faq_uso` arranca vacía.
  - **`ON DELETE SET NULL` sobre una tabla sin `UPDATE`**: la acción referencial la ejecuta
    PostgreSQL con los permisos del dueño de `faq_uso` (el rol de migraciones, `BYPASSRLS`,
    ADR-0005), no con los de `cheatsheet_app`. **Se verifica en CI** (caso 16), no se asume.
  - **Reversible sin perder el total**: `downgrade` primero suma los eventos a la línea de base
    (`UPDATE faq SET usos_anteriores = usos_anteriores + (SELECT count(*) FROM faq_uso u WHERE
    u.faq_id = faq.id)`), después borra `faq_uso`, `editada_en` y `seguimiento_desde`, y renombra a
    `usos`. Pérdida declarada en el docstring: las fechas de los usos y los usos de FAQ ya borradas.
- **Trabajo asíncrono**: no aplica (nada de Beat: los meses se calculan al leer).
- **Configuración**: no aplica (sin variables nuevas).
- **Integraciones externas**: no aplica. El envío de WhatsApp no cambia; solo se lee su resultado.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → no es dinero; el porcentaje usa la misma
      regla de redondeo y tiene su test (caso 5)
- [ ] Toca comprobantes fiscales / CAE
- [x] Consume un webhook → test de entrega duplicada: un mismo mensaje entrante, un solo uso (casos
      13 y 14)
- [x] Agrega datos con `empresa_id` → test de aislamiento entre empresas (caso 15) y `verify_rls.py`
- [ ] Usa salida de un LLM → la intención del modelo ya pasa por el esquema cerrado; esta unidad no
      agrega salida de LLM. Lo que decide el uso es la similitud contra el umbral (determinista) y el
      resultado del envío
- [ ] Datos personales o fiscales → `faq_uso` no guarda texto ni teléfono: ids e instantes
- [x] **Concurrencia** (no está en la plantilla): dos respuestas simultáneas cuentan dos (caso 12) y
      responder no pisa una edición (caso 11)
- [x] **Borde de mes en hora argentina** (TODO §22.5/§22.6 muestran que este error ya pasó dos
      veces): casos 1–3 y 17

**Riesgos aceptados y documentados:**
- **Crecimiento de `faq_uso`.** Una fila por respuesta con FAQ, sin poda. Una PyME responde del orden
  de miles por mes; el `count(*)` del total es un recorrido de índice por empresa. Si algún día se
  poda, se pliega en `usos_anteriores` en la misma transacción (ADR-0012).
- **FAQ borrada en el mismo instante en que el agente la usa.** Si el `DELETE` del administrador se
  confirma entre la búsqueda y el `INSERT` del uso, la FK falla y la transacción del mensaje entrante
  se revierte después de que el WhatsApp salió; Meta reintenta (el webhook contesta 500) y el
  reproceso contesta con otra FAQ o deriva. Ventana de milisegundos, mismo efecto que hoy tendría un
  `guardar` sobre una FAQ borrada (`LookupError`). No se agrega maquinaria para esto.
- **`COMMIT` que falla después del envío**: el uso no queda, igual que el saliente; es la regla
  general del agente y la cubre U5 (ADR-0011).

## Archivos a tocar
- [ ] `backend/src/cheatsheet/shared/zona_horaria.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/conversational/domain/uso_de_faq.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/conversational/domain/faq.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/application/ports.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/application/agente.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/application/faqs.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/models.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/repositories.py` (`listar`,
      `_faq_a_fila`, `_faq_a_dominio`)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/usos_de_faq.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/ensamblado.py`
- [ ] `backend/src/cheatsheet/api/routers/respuestas_frecuentes.py` (nuevo: rutas y esquemas de FAQ)
- [ ] `backend/src/cheatsheet/api/routers/conversaciones.py` (salen las rutas de FAQ; se montan desde
      el módulo nuevo)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py` (un argumento)
- [ ] `backend/migrations/versions/00NN_usos_de_faq.py` (nuevo; número libre al mergear)
- [ ] `backend/tests/shared/test_zona_horaria.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/domain/test_uso_de_faq.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/domain/test_agregados.py` (`registrar_uso` → `editar`
      y `editada_en`)
- [ ] `backend/tests/contexts/conversational/application/dobles.py` (`UsosDeFAQEnMemoria`;
      `MensajeriaEnMemoria` ya tiene `caida=True`)
- [ ] `backend/tests/contexts/conversational/application/test_agente.py`
- [ ] `backend/tests/contexts/conversational/application/test_faqs.py` (nuevo)
- [ ] `backend/tests/integracion/test_conversacional_postgres.py`
- [ ] `backend/tests/integracion/test_api_conversacional.py`
- [ ] `frontend/src/features/conversational/api/faq.ts`
- [ ] `frontend/src/features/conversational/components/RespuestasFrecuentes.tsx`
- [ ] `frontend/src/features/conversational/components/DetalleDeUsoDeFaq.tsx` (nuevo)
- [ ] `frontend/src/app/api/faqs/[faqId]/uso/route.ts` (nuevo)
- [ ] `frontend/src/features/conversational/components/__tests__/pantallas.test.tsx`
- [ ] `frontend/src/features/conversational/api/__tests__/clientes.test.ts`
- [ ] `frontend/src/app/(panel)/conversaciones/__tests__/pagina.test.tsx` (fixture `FAQ` con los
      campos nuevos)
- [ ] `docs/aidlc/inputs/der.md`, `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md`,
      `docs/aidlc/TODO.md` §22 — **solo si el PR del ADR-0012 no los cambió ya** (el ADR los lista;
      lo normal es que vayan con él)
- [ ] `docs/aidlc/units.md` (estado de la unidad)

## Casos de prueba

Test primero: los marcados **RED** fallan hoy y se escriben y se ven fallar antes del código.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** `MesCalendario.del_instante(2026-10-31T23:30-03:00)` → inicio `2026-10-01T03:00Z`, fin `2026-11-01T03:00Z`; el mismo instante en UTC (`2026-11-01T02:30Z`) **no** cae en noviembre | unit (shared) | pendiente |
| 2 | **RED** Borde exacto: `2026-11-01T00:00-03:00` pertenece a noviembre; `2026-10-31T23:59:59.999999-03:00` a octubre. `anterior()` de enero es diciembre del año anterior | unit (shared) | pendiente |
| 3 | **RED** Un uso a las 22:00 ART del 31/10 cuenta en «Este mes» si `ahora` es 31/10 23:00 ART y en «Mes anterior» si `ahora` es 01/11 00:30 ART (fake de usos + `ListarFAQs`) | unit (aplicación) | pendiente |
| 4 | **RED** `ventana_de_comparacion`: sin edición → `SIN_EDICIONES`; editada hace 10 h → `EDICION_RECIENTE`; editada a las 6 h del seguimiento → `SIN_HISTORIA_PREVIA`; editada hace 10 días con 40 de historia → `L = 10`; hace 50 días → `L = 30`; hace 10 días con 3 de historia → `L = 3` | unit (dominio) | pendiente |
| 5 | **RED** `Participacion`: 1/3 → `33.3`; 1/6 → `16.7` (half up); 0/5 → `0.0`; 0/0 → `None` | unit (dominio) | pendiente |
| 6 | **RED** `FAQ.editar` con el mismo texto (incluso con espacios alrededor) no mueve `editada_en`; cambiar solo la respuesta sí; `marcar_indexada` no la mueve | unit (dominio) | pendiente |
| 7 | **RED** Respuesta con FAQ y canal sano → el fake de usos tiene **una** fila con `faq_id`, `mensaje_id` del saliente `ENVIADO` y `usado_en = ahora`; el repositorio de FAQ **no recibió `guardar`** | unit (aplicación) | pendiente |
| 8 | **RED** Respuesta con FAQ y `MensajeriaEnMemoria(caida=True)` → saliente `FALLIDO` y **cero** usos. Hoy falla: `usos == 1` | unit (aplicación) | pendiente |
| 9 | FAQ por debajo del umbral → ofrece asesor y cero usos (el actual `test_sin_faq_por_encima_del_umbral…` reescrito sobre el fake de usos) | unit (aplicación) | pendiente |
| 10 | `VerUsoDeFAQ`: FAQ editada hace 10 días; 2 de 8 respuestas antes y 6 de 12 después → `25.0` y `50.0`, `dias = 10`; ventana posterior sin respuestas de la empresa → `despues.participacion is None`; FAQ inexistente → `FAQInexistente` | unit (aplicación) | pendiente |
| 11 | **RED** Responder con una FAQ no escribe la fila `faq`: se edita la pregunta en otra sesión y se confirma entre la búsqueda y el `COMMIT` del agente → la pregunta editada queda. Hoy falla: el `guardar` del agente la revierte | integración (PostgreSQL) | CI |
| 12 | **RED** Dos sesiones registran a la vez un uso de la misma FAQ (`asyncio.gather`, dos mensajes distintos) → `conteos` da 2. Hoy el equivalente con `guardar` da 1 | integración (PostgreSQL) | CI |
| 13 | Webhook firmado repetido (mismo `externo_id`, dos veces seguidas) → 200 las dos, **un** uso | integración (API + PostgreSQL) | CI |
| 14 | Dos webhooks iguales **concurrentes** (`asyncio.gather` sobre el cliente ASGI) → un solo uso y un solo saliente; el perdedor choca con `uq_mensaje_externo_id` y su transacción no deja nada | integración (API + PostgreSQL) | CI |
| 15 | **RLS**: con la empresa B en `app.current_empresa`, `faq_uso` de A no se lee (`count = 0`) y un `INSERT` con `empresa_id` de A falla (`WITH CHECK`); `GET /faqs` de B no ve conteos de A | integración (PostgreSQL) | CI |
| 16 | Borrar una FAQ con usos como `cheatsheet_app` funciona (la acción `SET NULL` corre como dueño) y el total de la empresa en la ventana no cambia: la participación de otra FAQ es la misma antes y después del borrado | integración (PostgreSQL) | CI |
| 17 | `conteos` en PostgreSQL con usos a las `02:59Z` y `03:00Z` del 1/11 → uno en octubre, uno en noviembre (la frontera ART llega bien a SQL) | integración (PostgreSQL) | CI |
| 18 | Mes vacío: FAQ con usos solo el mes pasado → `usos_este_mes = 0`, `usos_mes_anterior = n`; empresa sin ningún uso → todos en cero, sin error | unit (aplicación) + integración | pendiente / CI |
| 19 | Total = `usos_anteriores` + eventos: FAQ migrada con `usos_anteriores = 47` y 3 eventos → `usos_total = 50`, `usos_este_mes = 3` | integración (PostgreSQL) | CI |
| 20 | Migración: `upgrade` sobre una base con `faq.usos = 47` → `usos_anteriores = 47`, `editada_en NULL`, `seguimiento_desde` no nulo; `downgrade` con 3 eventos → `usos = 50`; `upgrade` otra vez limpio. `verify_rls.py` verde con la tabla nueva | integración (migraciones) | CI |
| 21 | API: `GET /faqs` trae `usos_este_mes`, `usos_mes_anterior`, `usos_total`, `editada_en` y **no** `usos`; ordenado por «Este mes»; `POST` responde con los tres en cero (primer criterio enmendado); `GET /faqs/{id}/uso` de una FAQ nunca editada → `comparacion: null`, `motivo_sin_comparacion: "SIN_EDICIONES"`; FAQ inexistente → 404; un rol `SOLO_LECTURA` lee el detalle | integración (API) | CI |
| 22 | **RED** Pantalla: columnas «Este mes», «Mes anterior» y «Total» con sus números; la barra dice «N usos este mes»; ya no aparece «en el período» | unit (frontend, Vitest) | pendiente |
| 23 | **RED** Pantalla: «Ver uso» abre el detalle con «Respondida 47 veces este mes» y «Participación: 25,0 % … 50,0 %» con los días y la fecha de edición; con `motivo_sin_comparacion` muestra el texto del motivo y ningún porcentaje; con `participacion: null` muestra «Sin consultas respondidas por FAQ» | unit (frontend, Vitest) | pendiente |
| 24 | Pantalla con `puedeEditar={false}`: «Ver uso» está, «Editar» y «Eliminar» no | unit (frontend, Vitest) | pendiente |
| 25 | `verUsoDeFaq` llama `GET /api/faqs/{id}/uso` y propaga `ErrorDeFaq` con el `detalle` del backend; el BFF reenvía al backend | unit (frontend, Vitest) | pendiente |
| 26 | El resto de `test_agente.py`, `test_api_conversacional.py`, `pantallas.test.tsx` y `pagina.test.tsx` sigue verde con los fixtures actualizados | unit + integración (existente) | pendiente |

Gates de §7 al cerrar: `ruff format --check . && ruff check .`, `mypy .`, `pytest` (cobertura de
conversational sin bajar), `npm run lint`, `npm run typecheck`, `npm test` en `frontend/`, y
`bash .claude/hooks/test_guards.sh`.

## Verificaciones que no se pueden hacer acá

- **PostgreSQL**: casos 11–17, 19–21 y la ejecución real de `verify_rls.py` necesitan PostgreSQL
  (sin Docker en esta máquina): se saltean localmente y se confirman en la CI del PR. Se dice así en
  el Gate 2, con la salida real de la CI.
- **WhatsApp real**: que un mensaje con FAQ enviado por un número de prueba de Meta sume un uso y
  uno fallido no. Va a `docs/aidlc/TODO.md` §25 «WhatsApp (sandbox)» y depende de U5.
- **La pantalla en el navegador** (columnas y tarjeta de detalle en escritorio y celular): va a
  `docs/aidlc/TODO.md` §22 con la unidad como dueña, verificable con `run-local`.

## Coordinación con `ajustes-menores-del-agente` (U3)

U3 (`fix/conversational-ajustes-menores-del-agente`, ya con su test RED de B5 en `d05970f`) toca el
mismo `agente.py` y el mismo `test_agente.py`:
- B5 cambia `_guardar_entrante` (devuelve el `Mensaje`) y el flujo de `ejecutar` alrededor de
  `self._interprete.leer`; B7 saca `PEDIDOS_DE_HUMANO` y `_pide_una_persona` a
  `domain/pedido_de_persona.py`.
- Esta unidad toca `__init__` (un argumento), `_responder_faq` y `_responder` (se parte en
  `_enviar`). Son bloques distintos: no se espera conflicto de texto en `agente.py`. En
  `test_agente.py` las dos agregan tests, y esta además agrega `usos` a `Escena`: conflicto probable
  pero mecánico.
- **Orden de merge: primero U3, después esta.** U3 está más adelante (Gate 1 aprobado) y, al sacar
  B7, deja `agente.py` con margen para las ~10 líneas de esta unidad. Esta rama se rebasa sobre
  `develop` después del merge de U3 y antes de su PR. Si esta llegara primero, U3 rebasa: el
  conflicto sigue siendo mecánico.
- La migración no choca: U3 no tiene migración.

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- (vacío hasta el Gate 1)

## Preguntas del Gate 1

Solo decisiones de producto; lo técnico quedó resuelto arriba con su evidencia. Las tres están
escritas en el ADR-0012 como propuesta: lo que se responda acá ajusta el ADR antes de aceptarlo.

1. **¿Cuántos días, como máximo, compara la participación antes y después de la edición?**
   **Recomendación: 30 días** (menos si la edición o la FAQ son más recientes). Un mes calendario es
   la unidad con la que la pantalla ya habla («Este mes»), y una ventana más larga mezcla el efecto de
   la edición con la estacionalidad del negocio; una más corta (7 días) en una PyME con pocas
   consultas por FAQ da porcentajes que saltan con dos mensajes.

2. **Cuando se borra una FAQ, ¿sus usos siguen contando en el total de consultas respondidas de la
   empresa?** **Recomendación: sí** (`ON DELETE SET NULL`, RN-08 de la enmienda). Si se borraran con
   la FAQ, eliminar una respuesta vieja cambiaría hacia atrás la participación de todas las demás, y
   el administrador vería que una FAQ que no tocó «mejoró» sola. El costo es guardar filas sin FAQ,
   sin texto ni datos personales.

3. **¿El «Total» incluye los usos contados antes de esta unidad?** **Recomendación: sí**, como línea
   de base sin fecha (`usos_anteriores`): el número que el administrador ya vio no desaparece al
   desplegar, y no suma a ningún mes ni a la participación. Hay que aceptar que esa base incluye los
   envíos fallidos que la regla vieja contaba y que no se pueden separar. La alternativa (el total
   arranca en cero el día del despliegue) es exacta pero borra a la vista meses de historia.
