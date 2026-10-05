# Unidad: telefono-del-operador

**HUs**: HU-E9-01   **Contexto dueño**: conversational   **Rama**: fix/conversational-telefono-del-operador

> Origen: hallazgo de revisión sobre `agente-y-atencion-humana` (mergeada). Severidad: **Mayor
> (seguridad)**. Es un `fix/…` cortado de `develop` (`2eff3a0`); el PR va a `develop` y no depende de
> ninguna otra unidad.

## Qué hace

Cuando un Operador o Administrador le responde al cliente desde PAN-WA-01, el número de destino
**viene en el cuerpo del request** (`RespuestaEntrada.telefono`) y el backend nunca lo compara con el
cliente de la conversación. Cualquier usuario con rol gestor puede mandar texto arbitrario a
**cualquier número** desde la cuenta de WhatsApp Business verificada de la empresa: spam o phishing
con el número de la empresa, costo por conversación iniciada y daño a la calificación de calidad de
Meta.

Comportamiento observable después del fix: el mensaje del operador sale **siempre** al WhatsApp del
cliente dueño del hilo, que el backend resuelve en `master_data` a partir de `conversacion.cliente_id`.
El request deja de llevar `telefono`; si un cliente viejo lo sigue mandando, se ignora (Pydantic
descarta campos extra por defecto), así que el despliegue no rompe nada. Si el cliente del hilo no
tiene WhatsApp registrado, la respuesta es 422 con una frase clara y no se envía nada.

**Fuera de esta unidad:**
- El agente (`agente.py`): responde al `entrante.telefono` del webhook firmado por Meta, que es el
  número que escribió. No tiene el hueco.
- Guardar el teléfono en la `conversacion` (columna nueva): el DER no la tiene y duplicaría el dato
  de `master_data` (ver Alternativa descartada).
- Quién puede leer `GET /clientes/{id}` (y con él el teléfono): no es este bug.

## La historia

> **HU-E9-01 — Atender una conversación escalada** (Operador / Administrador, PAN-WA-01)
>
> * RN-02: Al tomar el escalamiento, el operador asume el control y el agente deja de responder en
>   ese hilo.
> * RN-04: Los mensajes enviados por el operador se distinguen visualmente de los del agente en el
>   historial.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Envío un mensaje al cliente | El mensaje se envía por WhatsApp y se distingue del agente en el historial | PAN-WA-01 |

«Al cliente» es el cliente **de esa conversación**. El criterio no admite otro destinatario.

## Hallazgos

| Dónde | Qué |
|---|---|
| `api/routers/conversaciones.py:61-65` | `RespuestaEntrada.telefono: str`; el comentario dice que el backend no lo re-deriva «para no consultar `master_data` en cada mensaje» |
| `api/routers/conversaciones.py:283-296` | la ruta pasa `entrada.telefono` tal cual a `ResponderComoOperador` |
| `contexts/conversational/application/atencion.py:196-222` | `ejecutar(..., telefono: str, ...)` busca la conversación y el escalamiento abierto, pero llama a `mensajeria.enviar(telefono=telefono, …)` sin compararlo con nada |
| `contexts/conversational/domain/conversacion.py:179-186` | `Conversacion` sólo tiene `cliente_id`; **no guarda teléfono** (igual que la tabla `conversacion` del DER, §BC9) |
| `contexts/master_data/domain/cliente.py:46` | el teléfono vive en `Cliente.contacto_whatsapp: Telefono | None` (value object del Shared Kernel, `shared/contacto.py:56`, guarda dígitos) |
| `contexts/master_data/application/ports.py:91` | `PortRepositorioCliente.buscar_por_id(cliente_id)` ya existe |
| `contexts/conversational/application/ports.py:244-258` | `PortDirectorio`: el ACL de `conversational` sobre `master_data` (`cliente_de`, `alta_rapida`) |
| `contexts/conversational/infrastructure/acl.py:186-233` | `DirectorioViaMasterData` implementa ese puerto con `PortRepositorioCliente` y lee el resultado por atributo, sin importar el dominio ajeno (R3) |
| `api/conversacional.py:133-154` | `armar_directorio(unidad, settings, empresa_id=…, usuario_id=…)`, el ensamblado del ACL |
| `frontend/src/app/(panel)/conversaciones/[conversacionId]/page.tsx:45,70-77` | la página pide `GET /clientes/{id}` sólo para sacar `contacto_whatsapp` y pasarlo al componente |
| `frontend/src/features/conversational/components/HiloDeConversacion.tsx:36,57,151` | prop `telefono`, usada **únicamente** para `responder(hilo.id, texto, telefono)` |
| `frontend/src/features/conversational/api/conversacion.ts:151-165` | `responder(conversacionId, texto, telefono)` manda `{ texto, telefono }` |
| `backend/tests/contexts/conversational/application/` | **no hay test de aplicación de `ResponderComoOperador`**; sólo los dos de integración (`tests/integracion/test_api_conversacional.py:340-388`), que mandan el teléfono correcto y no miran el destino |

## Diseño

**Fix elegido: el servidor deriva el destino de la conversación y el request deja de llevar
`telefono`.** Una sola fuente de verdad: el número es un dato del cliente, y el cliente del hilo ya
lo fija `conversacion.cliente_id`. Lo que el request no trae, el request no puede falsificar. Además
borra código en el frontend (la consulta a `/clientes/{id}` de la página) en lugar de agregar.

Alternativa descartada, en una línea: mantener el campo y rechazar con 422 si no coincide con el del
cliente. Hace la misma consulta a `master_data` y conserva un dato redundante en el contrato que no
aporta nada; no hay ningún otro consumidor de este endpoint que obligue a mantenerlo.

- **Dominio**: sin cambios.
- **Aplicación** (`atencion.py`, `ResponderComoOperador`):
  - el constructor recibe `directorio: PortDirectorio`;
  - `ejecutar` pierde el parámetro `telefono`;
  - después de comprobar el escalamiento abierto y **antes** de enviar:
    `telefono = await self._directorio.telefono_de(conversacion.cliente_id)`; si es `None`, levanta
    `ClienteSinWhatsApp` (nueva, en `application/errors.py`, hereda de `EntradaInvalida` → 422) con
    «El cliente de esta conversación no tiene un WhatsApp registrado», y no envía ni guarda nada.
  - El orden de los chequeos no cambia: rol, texto vacío, conversación inexistente, escalamiento
    sin tomar, y recién ahí la consulta del teléfono.
- **Puertos y adaptadores**:
  - `PortDirectorio` suma `async def telefono_de(self, cliente_id: UUID) -> str | None`.
  - `DirectorioViaMasterData.telefono_de` usa `self._clientes.buscar_por_id(cliente_id)` y devuelve
    `str(cliente.contacto_whatsapp)` o `None` si no hay cliente o no tiene WhatsApp. Lee por
    atributo, igual que `cliente_de`: no importa nada del dominio de `master_data`.
  - Un cliente desactivado (`activo = False`) **sí** recibe la respuesta: el hilo está abierto y el
    escalamiento tomado; la baja en el catálogo no es un motivo para dejar a alguien sin contestar.
- **API** (`api/routers/conversaciones.py`): `RespuestaEntrada` queda sólo con `texto` (se borra el
  campo y su comentario); la ruta `responder` arma el directorio con
  `armar_directorio(unidad, recursos.settings, empresa_id=empresa_id, usuario_id=usuario_id)` y se
  lo pasa al caso de uso. El contrato de salida (`MensajeSalida`, 201) no cambia.
- **Otros contextos**: `conversational → master_data` por `PortRepositorioCliente` (puerto de
  aplicación), detrás del ACL que ya existe. **Es un edge que el Context Map ya permite** (el mismo
  que usa `cliente_de` desde el épico 8); R1–R5 se respetan y **no hace falta ADR**.
- **Frontend** (`features/conversational`):
  - `api/conversacion.ts`: `responder(conversacionId, texto)` manda `{ texto }`.
  - `components/HiloDeConversacion.tsx`: se borra la prop `telefono` de `PropsDeHiloDeConversacion`.
  - `app/(panel)/conversaciones/[conversacionId]/page.tsx`: se borran `telefonoDe`, `ClienteDelHilo`
    y la llamada a `/clientes/{id}`; actualizar el comentario de cabecera.
  - `index.ts`: sin cambios (los tipos exportados no incluyen la prop).

Consecuencia aceptada: si el cliente cambió su WhatsApp en el catálogo después de abrir el hilo, la
respuesta va al número **actual**. Es lo correcto con una sola fuente de verdad.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica (el envío del operador es síncrono, dentro del request).
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica; WhatsApp ya tiene timeout y manejo de falla
  (`MensajeriaNoDisponible`). El fix agrega una lectura a PostgreSQL dentro de la misma transacción,
  no una llamada externa.

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica
- [ ] Comprobantes fiscales / CAE: no aplica
- [ ] Webhook: no aplica
- [x] Datos con `empresa_id`: la búsqueda del cliente corre bajo la RLS de la empresa del request;
      un `cliente_id` de otra empresa no se encuentra (lo cubre la RLS de `cliente`, ya probada en
      `master_data`)
- [ ] Salida de un LLM: no aplica
- [ ] Datos personales a un LLM: no aplica
- [x] **Seguridad (destinatario arbitrario)**: el destino no puede venir del usuario; casos 1, 2 y 6

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/conversational/application/atencion.py`
- [x] `backend/src/cheatsheet/contexts/conversational/application/ports.py` (`PortDirectorio.telefono_de`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/errors.py` (`ClienteSinWhatsApp`)
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/acl.py` (`DirectorioViaMasterData.telefono_de`)
- [x] `backend/src/cheatsheet/api/routers/conversaciones.py`
- [x] `backend/tests/contexts/conversational/application/dobles.py` (`DirectorioEnMemoria.telefono_de`)
- [x] `backend/tests/contexts/conversational/application/test_atencion.py` (nuevo)
- [x] `backend/tests/contexts/conversational/infrastructure/test_directorio_via_master_data.py`
- [x] `backend/tests/integracion/test_api_conversacional.py`

### Frontend
- [x] `frontend/src/features/conversational/api/conversacion.ts`
- [x] `frontend/src/features/conversational/api/__tests__/clientes.test.ts`
- [x] `frontend/src/features/conversational/components/HiloDeConversacion.tsx`
- [x] `frontend/src/features/conversational/components/__tests__/pantallas.test.tsx`
- [x] `frontend/src/app/(panel)/conversaciones/[conversacionId]/page.tsx`
- [x] `frontend/src/app/(panel)/conversaciones/__tests__/pagina.test.tsx`

### Docs
- [x] `docs/aidlc/units.md` (fila de la unidad)
- [x] `docs/aidlc/units/telefono-del-operador.md` (este plan)

## Casos de prueba

Modo: **test primero** (`CLAUDE.md`: todo bug arreglado empieza con un test que lo reproduce). El RED
tiene que fallar contra el código actual **por el motivo correcto** (el mensaje salió al número
ajeno), no por un error de armado. El commit del test va antes que el del fix. Ningún test toca la
red: la mensajería es `MensajeriaEnMemoria` (dobles.py:185) o un monkeypatch de `armar_mensajeria`.

Armado del caso 1: `ResponderComoOperador` real con `RepositorioConversacionEnMemoria`,
`RepositorioMensajeEnMemoria`, `RepositorioEscalamientoEnMemoria` (con un escalamiento tomado),
`MensajeriaEnMemoria`, `PublicadorEnMemoria` y un `DirectorioEnMemoria` que conoce el cliente del
hilo con `5491112345678`. Para que el RED compile contra el código de hoy, el test llama a
`ejecutar` con `telefono="5491199999999"` (número ajeno); en el commit del fix, ese argumento
desaparece del test junto con el parámetro.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED**: el operador responde un hilo tomado indicando un número ajeno → `mensajeria.enviados == [("5491112345678", texto)]`. **Hoy falla**: el envío sale a `5491199999999` | unit (aplicación) | pasa |
| 2 | **RED de API**: con la conversación del webhook ya tomada, `POST /conversaciones/{id}/mensajes` con `{"texto": …, "telefono": "5491199999999"}` y `armar_mensajeria` monkeypatcheado a `MensajeriaEnMemoria` → 201 y el único envío es a `TELEFONO` (el número que escribió). **Hoy falla**: sale al número ajeno | integración (PostgreSQL) | CI |
| 3 | El cliente del hilo no tiene WhatsApp (`telefono_de` → `None`) → `ClienteSinWhatsApp` (422), `enviados == []`, ningún mensaje guardado, ningún evento de auditoría | unit (aplicación) | pasa |
| 4 | El orden de las guardas no cambia: sin escalamiento tomado → 422 y **no** se consulta el directorio; rol `SOLO_LECTURA` → rechazo; texto vacío → rechazo | unit (aplicación) | pasa |
| 5 | Camino feliz: el mensaje se guarda con `origen = OPERADOR`, `externo_id` del canal, y se audita `responder_como_operador` | unit (aplicación) | pasa |
| 6 | `DirectorioViaMasterData.telefono_de`: cliente con WhatsApp → los dígitos; cliente sin WhatsApp → `None`; `cliente_id` inexistente → `None` (con `RepositorioClienteEnMemoria` de `tests/contexts/master_data/conftest.py`) | unit (infraestructura) | pasa |
| 7 | Los dos integración existentes (`test_no_se_le_puede_escribir_al_cliente_sin_tomar_el_escalamiento`, `test_el_mensaje_del_operador_se_distingue_del_agente`) siguen verdes mandando sólo `{"texto": …}` | integración (existente, ajustado) | CI |
| 8 | Frontend `clientes.test.ts`: `responder` manda **sólo** `{ texto }` (reemplaza «responder manda el texto y el telefono») | unit frontend (Vitest) | pasa |
| 9 | Frontend `pantallas.test.tsx`: `HiloDeConversacion` sin la prop `telefono`; enviar llama a `responder(id, texto)` | unit frontend (Vitest) | pasa |
| 10 | Frontend `pagina.test.tsx`: la página del hilo **no** llama a `/clientes/…`; se reemplaza «muestra el hilo aunque no pueda resolver el telefono», que deja de tener sentido | unit frontend (Vitest) | pasa |
| 11 | `test_agente.py` sigue verde sin cambios (el agente no usa `telefono_de`) | unit (existente) | pasa |

El 1 es la evidencia local del RED. El 2 lo confirma contra la base real y la ruta HTTP; sin Docker
local se saltea y su RED lo muestra la primera corrida de CI sobre el commit del test.

## Verificaciones que no se pueden hacer acá

- El caso 2 y el 7 necesitan PostgreSQL: se saltean sin Docker y **el Gate 2 no se cierra sin la
  salida real del CI** en esos casos.
- El envío real por la Graph API de Meta no se prueba (los tests no tocan la red). Probar en staging
  que la respuesta del operador llega al cliente del hilo queda en `docs/aidlc/TODO.md` (sandbox).

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-03 | aprobado |
| 2 · Verificación | 2026-10-04 | Aprobado por Luciano con la evidencia local; los casos 2 y 7 (PostgreSQL) se confirman en la CI del PR |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- ¿Un cliente desactivado sigue recibiendo la respuesta del operador? → Sí: con el escalamiento
  abierto, cortar la conversación es peor que responder.
- ¿Si el cliente cambió su WhatsApp en el catálogo, a qué número va la respuesta? → Al número
  actual del catálogo, que es la fuente de verdad (mismo comportamiento que el panel de hoy).
