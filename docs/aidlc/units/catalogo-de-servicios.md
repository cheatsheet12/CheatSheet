# Unidad: catalogo-de-servicios

**HUs**: HU-E4-02 **Contexto dueño**: master_data **Rama**: feature/master_data-catalogo-de-servicios

## Qué hace

Un Administrador u Operador entra a **PAN-DM-02**, ve el catálogo de servicios de su empresa
—nombre, precio, IVA, duración y estado—, crea uno nuevo, edita los existentes y los desactiva.
Un servicio agendable declara su duración estándar; uno que no lo es, no.

Es la segunda unidad de `master_data` y hereda todo lo que estrenó `catalogo-de-clientes`:
repositorio con RLS, patrón de migración, router, `features/master_data`. **Lo único que trae de
nuevo a nivel plataforma es el dinero** — es el primer `Decimal` del sistema.

---

## El dinero entra al sistema en esta unidad

Hoy no hay un solo `Decimal` en `backend/src`. `precio` es el primero, y lo que se decida acá lo
van a copiar `billing` (épico 5), `payments` (épico 6) y la seña de turno (épico 7). Por eso las
reglas de [`docs/code-standards.md`](../../code-standards.md) §2.5 se aplican al pie y se dicen
explícitas:

- **`float` no toca dinero, nunca.** Ni en el dominio, ni en el ORM, ni en el esquema pydantic del
  router. La columna es `NUMERIC`, no `FLOAT`.
- **Los `Decimal` se construyen desde `str`**, jamás desde un literal float. El hook `guard_edit.py`
  bloquea justamente ese caso, que es el que no se ve leyendo.
- **El redondeo es explícito**, con `quantize` y modo declarado: `ROUND_HALF_UP`.

**`precio` se cuantiza a dos decimales** (`Decimal("0.01")`). No es una decisión obvia y por eso se
escribe: el peso argentino tiene centavos, los precios de lista de una PyME se cargan en pesos con
centavos, y un precio unitario con más precisión de la que se puede facturar produce totales que no
cierran contra el comprobante. Si algún día aparece un rubro que necesita precio unitario con cuatro
decimales, eso es un cambio de esquema y una decisión con su historia detrás, no un parche.

**Este catálogo no calcula IVA.** Guarda el precio sin IVA y la alícuota; multiplicar es del épico 5,
que además tiene que redondear una vez por comprobante y no una vez por ítem. Acá no hay ninguna
operación aritmética sobre dinero — sólo validación y persistencia.

---

## La pregunta que el mapa dejó para este Gate

### ¿La alícuota de IVA es de `master_data` o sale de `reference_data`?

El mapa la dejó abierta porque `reference_data` es, en el DER, el dueño del catálogo fiscal:
`parametro_fiscal` tiene `tipo_catalogo_fiscal` con un valor `ALICUOTA_IVA`, y está versionado por
vigencia (`fecha_desde` / `fecha_hasta`) justamente para que un comprobante se valide contra el
parámetro que regía el día que se emitió.

**Resolución: un enum `AlicuotaIVA` propio de `master_data`, con los tres valores que nombra
HU-E4-02 RN-02 — 0 %, 10,5 % y 21 %.** No se toca `reference_data`.

Tres razones, en orden de peso:

1. **La historia pide un enum cerrado, no un catálogo vigente.** RN-02 dice «la alícuota de IVA es un
   enum cerrado: 0 %, 10.5 % o 21 %», y el criterio de aceptación es un combo en un formulario. Lo
   que `parametro_fiscal` resuelve —qué alícuota regía en marzo de 2024— es una pregunta que **sólo
   tiene sentido al emitir**, y emitir es el épico 5.
2. **`reference_data` no tiene una sola línea de código, y construirlo acá sería trabajo sin historia
   detrás** — la escalada que el workflow manda frenar. No es tampoco una *unidad técnica* declarada
   en el roadmap §5, así que no hay excepción que aplicar.
3. **El Context Map no permite el edge.** La fila de `reference_data` dice
   `reference_data → billing, reporting`; `master_data` no está, y agregarlo sería un ADR para
   habilitar una dependencia que esta historia no necesita.

**Lo que esto cuesta, dicho de frente.** Si ARCA cambiara una alícuota, habría que tocar el enum y
desplegar, en lugar de insertar una fila. Es aceptable porque el conjunto no se movió en décadas y
porque el precio pagado por adelantarse sería construir un contexto entero sin nadie que lo consuma.

**Lo que el épico 5 hereda, para que no lo descubra.** Cuando `billing` construya `reference_data`
con su propia historia, `Servicio.alicuota_iva` **no** pasa a leerse de ahí: sigue siendo lo que el
usuario eligió en el formulario. El `Comprobante` desnormaliza su propia alícuota —el DER ya lo
declara así, «un comprobante emitido no cambia porque el cliente edite sus datos»— y es *esa* copia
la que se valida contra el parámetro vigente al emitir.

### La columna sigue siendo `decimal`, como manda el DER

`servicio.alicuota_iva` es `decimal NN` en el DER y **se deja así**. El enum vive en el dominio y
persiste su valor numérico (`0.00`, `0.105`, `0.21`), no su nombre. Así el DER no se contradice, y
el día que el épico 5 compare esta alícuota contra un `parametro_fiscal` está comparando números
contra números.

---

## Diseño

### Dominio — `contexts/master_data/domain/`

- **`Servicio`** (`servicio.py`), agregado raíz. Campos del DER: `id`, `empresa_id`, `nombre`,
  `precio`, `alicuota_iva`, `agendable`, `duracion_estandar_min`, `origen`, `presente_en_planilla`,
  `activo`, `created_at` / `updated_at`.
  - `Servicio.registrar(...)`, `renombrar`, `cambiar_precio`, `cambiar_alicuota`,
    `volver_agendable(duracion)`, `dejar_de_ser_agendable()`, `desactivar`, `reactivar`.
  - **`origen` no tiene setter**, igual que en `Cliente` y por la misma regla (RN-01 de HU-E4-01
    describe el campo, que es de las dos entidades).
  - `categoria_id` **no se crea** — decisión D8 del mapa.
- **`AlicuotaIVA`** (`valores.py`), enum cerrado con los tres valores de RN-02 y su `Decimal`
  asociado. Se agrega al módulo que ya tiene `OrigenDato`.
- **`Precio`** — **no** se crea un value object. `Decimal` con la validación en el agregado alcanza,
  y un wrapper que sólo envuelve un `Decimal` agrega una capa que hay que desenvolver en el
  repositorio, en el router y en cada test. Si aparece una segunda moneda, ahí sí: la regla de
  `code-standards` §2.5 —«any function returning an amount declares its currency in the type or the
  name»— se cumple hoy con el nombre del campo, porque el sistema es de una sola moneda.

**Los dos invariantes, vivos en el dominio y no en el formulario:**

| Regla | Dónde | Qué pasa si no se cumple |
|---|---|---|
| RN-02 — el precio es mayor a cero | `Servicio` | `EntradaInvalida("El precio debe ser mayor a cero.")` |
| RN-03 — agendable exige duración | `Servicio` | `EntradaInvalida("La duracion es obligatoria para servicios agendables.")` |

Los dos mensajes son **textualmente** los de los criterios de aceptación. El de la duración va sin
acento, como el resto de los mensajes del sistema.

**Un servicio que deja de ser agendable pierde su duración**, en la misma operación. La alternativa
—dejarla ahí por si vuelve— es un dato que la pantalla no muestra, que nadie mantiene y que el
épico 7 podría leer creyendo que significa algo.

### Aplicación — `contexts/master_data/application/servicios.py`

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ListarServicios` | `empresa_id`, `rol`, filtros (texto, agendable, sólo activos), paginado | `ListadoDeServicios` | Lectura con los mismos tres roles que el catálogo de clientes |
| `RegistrarServicio` | `empresa_id`, `usuario_id`, `rol`, datos | `Servicio` | `origen = PANEL`; los dos invariantes; audita |
| `EditarServicio` | ídem + `servicio_id` | `Servicio` | No toca `origen`; audita |
| `CambiarEstadoDeServicio` | `empresa_id`, `usuario_id`, `rol`, `servicio_id`, `activo` | `Servicio` | RN-04: oculta del catálogo activo sin tocar nada histórico |

**Autorización**: se reutiliza `application/autorizacion.py` tal como está — mismos roles, misma
pantalla del mapa de navegación §5. No se agrega nada.

**Sin unicidad de nombre.** Ninguna regla la pide, y dos servicios que se llamen «Corte» en dos
sucursales son un caso real. Se dice acá para que la ausencia no se lea como olvido.

**Auditoría**: `EventoAuditable` con `Modulo.MASTER_DATA`, por el mismo mecanismo. Acciones:
`servicio_registrado`, `servicio_editado`, `servicio_desactivado`, `servicio_reactivado`.

### Puertos y adaptadores

Uno solo: **`PortRepositorioServicio`** en el `ports.py` que ya existe, con
`RepositorioServicioPostgres` al lado del de clientes. **Ningún puerto nuevo hacia afuera**: esta
unidad no habla con ningún sistema externo.

### Otros contextos

**Ninguno.** A diferencia de `catalogo-de-clientes`, acá no hay llamada a `integrations` ni a nadie:
el precio y la alícuota los escribe el usuario. `scheduling` (épico 7) y `billing` (épico 5) van a
leer `Servicio`, pero todavía no existen.

### Frontend

- **`features/master_data`** ya existe; se agregan `ListadoDeServicios.tsx` y
  `FormularioDeServicio.tsx`, y su `index.ts` los exporta.
- **Ruta**: `app/(panel)/datos-maestros/servicios/page.tsx`, más la entrada en la navegación.
- **BFF**: `app/api/servicios/route.ts` (GET, POST), `[servicioId]/route.ts` (PUT) y
  `[servicioId]/estado/route.ts` (PUT). **Con sus tests de ruta desde el principio** — la deuda que
  la unidad anterior descubrió tarde.
- **El precio viaja como string en el JSON**, no como número. Un `number` de JavaScript es un float
  de 64 bits: `19999.99` sobrevive, pero la regla de que el dinero no toca `float` no admite
  excepciones por tamaño, y el día que alguien sume dos precios en el panel el error ya está hecho.
  El input es de texto con validación de formato, y pydantic lo recibe como `Decimal`.
- **El panel no calcula el precio con IVA.** Muestra precio y alícuota por separado, como pide el
  criterio de aceptación. Calcularlo sería lógica de negocio en el frontend (`CLAUDE.md` §5).
- **Sin prototipo** (hueco P10): se construye con el catálogo de componentes del PDF §1.3, reusando
  la forma que ya tiene PAN-DM-01.

---

## Infraestructura

### Migraciones

Una sola, **`0009_servicio.py`**, sobre 0008.

- Tabla `servicio` con las columnas del DER menos `categoria_id` (D8).
- **`precio NUMERIC(12, 2)`** y **`alicuota_iva NUMERIC(5, 4)`**. La escala de 4 en la alícuota es
  para que `0.105` entre exacto; con 2 se guardaría `0.11` y el IVA del épico 5 saldría mal.
  Doce enteros en el precio son mil millones de pesos, que es holgura razonable con inflación.
- Índice `ix_servicio_empresa`.
- **Sin índice único**: no hay regla de unicidad (ver arriba).
- **RLS igual que `cliente`**: `ENABLE` + `FORCE`, política contra `app.current_empresa`, `GRANT`
  de `SELECT, INSERT, UPDATE` a `cheatsheet_app` y **`DELETE` deliberadamente ausente**, por RN-04 y
  por la misma razón que en clientes: `comprobante` y `turno` referencian el servicio por id.
- **Reversible, sin backfill.**
- `backend/migrations/env.py` ya importa los modelos de `master_data` desde la unidad anterior; no
  hace falta tocarlo.

### Trabajo asíncrono · Configuración · Integraciones externas

**No aplica** en los tres casos. Nada de esta unidad es diferido, no hay variables nuevas y no se
habla con ningún proveedor.

---

## Riesgos que obligan a tests

- [x] **Toca dinero** (`Decimal`, redondeo `ROUND_HALF_UP`) → test de redondeo, y test de que un
      `float` no entra ni por el router ni por el repositorio. **Es el primer dinero del sistema.**
- [ ] Toca comprobantes fiscales / CAE — no. El épico 5 los emitirá usando esto.
- [ ] Consume un webhook — no.
- [x] **Agrega datos con `empresa_id`** → test de aislamiento entre empresas contra PostgreSQL real.
- [ ] Usa salida de un LLM — no.
- [ ] Datos personales o fiscales — no: un servicio no describe a una persona.

---

## Archivos a tocar

### Backend

- [ ] `backend/src/cheatsheet/contexts/master_data/domain/servicio.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/valores.py` — recibe `AlicuotaIVA`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/ports.py` — recibe el puerto
- [ ] `backend/src/cheatsheet/contexts/master_data/application/errors.py` — `ServicioNoEncontrado`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/servicios.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/models.py` — `ServicioORM`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/repositories.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/ensamblado.py`
- [ ] `backend/src/cheatsheet/api/routers/servicios.py`
- [ ] `backend/src/cheatsheet/api/main.py` — monta el router
- [ ] `backend/migrations/versions/0009_servicio.py`
- [ ] `backend/tests/contexts/master_data/domain/test_servicio.py`
- [ ] `backend/tests/contexts/master_data/application/test_servicios.py`
- [ ] `backend/tests/contexts/master_data/conftest.py` — doble del repositorio
- [ ] `backend/tests/integracion/test_servicios_postgres.py`
- [ ] `backend/tests/integracion/test_api_servicios.py`
- [ ] `backend/tests/integracion/conftest.py` — `DELETE FROM servicio` en la limpieza

### Frontend

- [ ] `frontend/src/features/master_data/api/servicio.ts`
- [ ] `frontend/src/features/master_data/components/ListadoDeServicios.tsx`
- [ ] `frontend/src/features/master_data/components/FormularioDeServicio.tsx`
- [ ] `frontend/src/features/master_data/components/__tests__/…` (los dos)
- [ ] `frontend/src/features/master_data/index.ts`
- [ ] `frontend/src/app/(panel)/datos-maestros/servicios/page.tsx`
- [ ] `frontend/src/app/(panel)/layout.tsx` — entrada de navegación
- [ ] `frontend/src/app/api/servicios/route.ts` · `[servicioId]/route.ts` · `[servicioId]/estado/route.ts`
- [ ] `frontend/src/app/api/servicios/__tests__/rutas.test.ts`
- [ ] `frontend/src/shared/componentes.css` — lo que la pantalla necesite

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Precio cero: «El precio debe ser mayor a cero.» y no guarda | unit | pendiente |
| 2 | Precio negativo: mismo mensaje | unit | pendiente |
| 3 | Agendable sin duración: «La duracion es obligatoria para servicios agendables.» | unit | pendiente |
| 4 | Agendable con duración cero o negativa: tampoco guarda | unit | pendiente |
| 5 | No agendable **sí** puede no tener duración | unit | pendiente |
| 6 | Dejar de ser agendable borra la duración en la misma operación | unit | pendiente |
| 7 | El precio se cuantiza a dos decimales con `ROUND_HALF_UP`: `10.005` → `10.01`, `10.004` → `10.00` | unit | pendiente |
| 8 | Un `float` como precio es rechazado, no convertido en silencio | unit | pendiente |
| 9 | Las tres alícuotas son las de RN-02, y `0.105` sobrevive el viaje a la base sin redondearse | integración | pendiente |
| 10 | `origen = PANEL` al crear, y no cambia al editar | unit | pendiente |
| 11 | Desactivar oculta del catálogo activo y el servicio sigue existiendo | integración | pendiente |
| 12 | **Aislamiento**: la empresa A no ve, no edita ni desactiva un servicio de la empresa B | integración | pendiente |
| 13 | La aplicación no tiene permiso de `DELETE` sobre `servicio` | integración | pendiente |
| 14 | `SOLO_LECTURA` lista y no escribe; `OPERADOR` hace las cuatro cosas | unit | pendiente |
| 15 | Cada escritura deja un `RegistroDeAuditoria` con `Modulo.MASTER_DATA` | integración | pendiente |
| 16 | Ida y vuelta de todos los campos por el repositorio real | integración | pendiente |
| 17 | El listado muestra nombre, precio, IVA, duración y estado | frontend | pendiente |
| 18 | El formulario esconde la duración cuando el servicio no es agendable | frontend | pendiente |
| 19 | El precio viaja como string en el JSON, nunca como `number` | frontend | pendiente |
| 20 | Las rutas del BFF rechazan sin sesión y reenvían el query string entero | frontend | pendiente |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-01 | pendiente de aprobación |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- 2026-09-01 · ¿La alícuota sale de `reference_data`? → **No.** Enum propio de `master_data` con los
  tres valores de RN-02; `reference_data` se construye en el épico 5, con su historia detrás.
- 2026-09-01 · ¿`precio` es un value object? → **No.** `Decimal` con validación en el agregado.
- 2026-09-01 · ¿Se exige nombre único? → **No.** Ninguna regla lo pide.
