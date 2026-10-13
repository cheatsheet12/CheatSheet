# Unidad: corregir-esquema-de-lectura-anthropic

**HUs**: HU-E8-01, HU-E8-02   **Contexto dueño**: conversational   **Rama**: fix/conversational-esquema-de-lectura-anthropic

## Qué hace

Evita que el intérprete del canal de WhatsApp reciba un `400 Bad Request` de Anthropic. Hoy cada
mensaje entrante escalaría a una persona con confianza cero, y la PRU-05 no podría pasar en staging.
`ESQUEMA_DE_LECTURA` se envía en `output_config.format` y declara restricciones que la API no admite
en un esquema crudo. Se quitan del esquema enviado y la validación local, que ya existe, sigue
garantizando lo mismo.

## Diagnóstico y alcance

Es el mismo defecto que se corrigió en `spreadsheet_sync` (#164, `91c00d1`), pero acá hay más
restricciones en juego. Según la documentación de salidas estructuradas de Anthropic, no se admiten
las restricciones numéricas (`minimum`, `maximum`), las restricciones de texto (`minLength`,
`maxLength`) ni las restricciones complejas de arrays.

| Lugar en el esquema | Restricción | Quién la garantiza después del fix |
|---|---|---|
| `confianza` | `minimum: 0`, `maximum: 1` | `_interpretar`: rango 0..1, fuera de rango → `SIN_LECTURA` |
| `resumen` | `maxLength: 200` | `_interpretar`: recorta a 200 |
| `pedido_de_turno.cuandos` | `maxItems: 3` | `PedidoDeTurno`: `MAXIMO_DE_CUANDOS` → `EntradaInvalida` → pedido descartado |
| `pedido_de_turno.servicio` | `maxLength: 60` | `PedidoDeTurno`: `LARGO_MAXIMO_DEL_SERVICIO` → pedido descartado |
| `cuandos[].dia_semana`, `dia`, `mes` | `minimum` / `maximum` | `Cuando`: rangos 0–6, 1–31 y 1–12 → pedido descartado |
| `pedido_de_turno.hora` | `pattern` | `_hora`: regex `HH:MM` → pedido descartado |

`pattern` no figura en la lista de restricciones admitidas. Se quita por la misma razón: la
validación local ya lo cubre, y un patrón que la API rechace deja el canal completo sin lectura.
`pedido_de_turno` usa `type: ["object", "null"]`. Pasa a `anyOf` con `{"type": "null"}`, que sí es
una forma documentada como admitida. El `enum` de `intencion` y `additionalProperties: false` en
todos los objetos se mantienen: son la segunda defensa (D38) y están admitidos.

Fuera de alcance: el esquema de `spreadsheet_sync` (ya corregido en #164) y cualquier cambio de
prompt o de modelo.

## Diseño

- **Dominio**: no cambia. `PedidoDeTurno` y `Cuando` siguen validando sus rangos.
- **Aplicación**: no cambia. Una lectura inválida sigue siendo confianza cero, y eso escala.
- **Puertos y adaptadores**: solo cambian las constantes `_ESQUEMA_DE_CUANDO`, `_ESQUEMA_DE_PEDIDO`
  y `ESQUEMA_DE_LECTURA` de `infrastructure/interprete.py`, con un comentario que explica por qué
  los límites viven del lado nuestro.
- **Otros contextos**: ninguno.
- **Frontend**: no cambia.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no se agregan variables. Staging ya tiene `LLM_ADAPTADOR=anthropic`.
- **Integraciones externas**: el adaptador Anthropic existente, con su timeout y su manejo de fallas.
  Los tests no tocan la red. Después del deploy, la PRU-05 en staging es la validación manual.

## Riesgos que obligan a tests

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [ ] Agrega datos con `empresa_id`
- [x] Usa salida de un LLM: cada límite que sale del esquema tiene un test que prueba que una
      respuesta que lo viola se descarta antes de cualquier efecto
- [ ] Datos personales o fiscales: no cambia lo que se envía al modelo

## Archivos a tocar

- [x] `backend/tests/contexts/conversational/infrastructure/test_interprete.py`: se invierten las
      afirmaciones que exigían `minimum`, `maxItems`, `maxLength` y `pattern`. Se agrega un test
      recursivo de que ningún nodo del esquema usa palabras clave no admitidas, otro de que
      `InterpreteAnthropic.leer` envía ese esquema (con un doble del cliente) y tests de rechazo
      local para cada límite.
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/interprete.py`: el esquema.
- [x] `docs/aidlc/units.md`: la fila de la unidad.
- [x] Este plan: Registro y casilleros.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Ningún nodo de `ESQUEMA_DE_LECTURA` usa `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `minLength`, `maxLength`, `minItems > 1`, `maxItems`, `pattern` ni `type` como lista | unit | aprobado: rojo antes del fix, verde después |
| 2 | `InterpreteAnthropic.leer` envía ese esquema y convierte una respuesta válida en una `Lectura` (doble del cliente que rechaza las palabras no admitidas, igual que #164) | unit, sin red | aprobado: rojo antes del fix, verde después |
| 3 | `intencion` sigue siendo un `enum` cerrado y todos los objetos tienen `additionalProperties: false` | unit existente | aprobado: verde antes y después |
| 4 | Confianza fuera de 0..1 → `SIN_LECTURA` | unit existente | aprobado: verde antes y después |
| 5 | Cuatro días pedidos, servicio de 61 caracteres, `dia_semana` 7, `mes` 13 o `hora` "25:00" → pedido descartado y la lectura sigue sin pedido | unit | aprobado: verde (la validación local ya los descartaba; el test fija el contrato al quitarlos del esquema) |
| 6 | Un `resumen` de más de 200 caracteres se recorta | unit | aprobado: verde (idem) |
| 7 | En staging, la PRU-05 recibe una lectura sin 400 en el log | manual | pendiente (tras el deploy) |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado por Luciano |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Luciano confirmó `LLM_ADAPTADOR=anthropic` en staging: la unidad bloquea la PRU-05.
