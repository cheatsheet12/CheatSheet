# DER — modelo físico de datos

> **Transcripción** de los dos diagramas de Etapa 5, que son la fuente de verdad:
>
> | Archivo | Qué aporta |
> |---|---|
> | [`DER.pdf`](DER.pdf) | Todas las columnas con su tipo, nulabilidad, PK/FK/único, y los 21 enums. Incluye `created_at` / `updated_at` |
> | [`der-por-contexto.jpg`](der-por-contexto.jpg) | **A qué bounded context pertenece cada tabla.** Vista lógica: omite `created_at` / `updated_at` |
>
> Los dos coinciden atributo por atributo en las 34 tablas. Donde uno tiene más detalle que el
> otro, se toma el más específico: los tipos y las marcas `NN` salen del PDF, la asignación a
> contexto sale del JPG. **Este archivo es una transcripción**: ante cualquier diferencia, valen
> los diagramas.
>
> Existe porque el export de dbdiagram.io convierte el texto en trazos vectoriales — el PDF se
> ve, pero no se puede grepear, ni citar por línea, ni comparar en un diff.

## Cómo está compuesto

**34 tablas = 27 agregados raíz + 7 entidades internas**, que es exactamente lo que declara
[`docs/architecture.md`](../../architecture.md) §3. Las tres fuentes cierran, y eso no es
casualidad: es la comprobación de que el modelo físico y el modelo de dominio son el mismo.

Las **7 entidades internas** son las únicas sin `empresa_id`: no son agregados, viven colgadas de
su padre y heredan de él la empresa.

| Entidad interna | Cuelga de |
|---|---|
| `item_de_comprobante` | `comprobante` |
| `entrada_de_mapeo` | `mapeo` |
| `error_de_fila` | `procesamiento_de_planilla` |
| `patron_de_disponibilidad` | `recurso_reservable` |
| `excepcion_de_disponibilidad` | `recurso_reservable` |
| `recordatorio` | `cobro` |
| `token_de_acceso_contable` | `paquete_contable` |

De los 27 agregados, **25 llevan `empresa_id`**. Las dos excepciones:

- **`empresa`** — es el tenant. Su propio `id` es lo que las demás referencian.
- **`parametro_fiscal`** — catálogo global de ARCA, compartido por todas las empresas.

Esa cuenta es la regla operativa de la política RLS: **25 tablas llevan política de aislamiento
por `empresa_id`**, las 7 internas se protegen por su padre, y las 2 restantes se tratan aparte.

## Convenciones

- `id uuid` como clave primaria en las 34.
- `NN` = NOT NULL · `E` = tipo enumerado · `U` = único.
- `created_at` / `updated_at` en `timestamptz` (solo en el PDF; el JPG los omite por ser vista lógica).

---

## BC1 — Identidad y Organización · `contexts/identity`

### `empresa`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| razon_social | varchar | NN |
| cuit | varchar | NN, **U** |
| condicion_iva | `condicion_iva` E | NN |
| activa | boolean | NN |
| terminos_version | varchar | |
| terminos_fecha_aceptacion | timestamptz | |
| created_at / updated_at | timestamptz | NN |

### `usuario`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK → empresa |
| email | varchar | NN |
| rol | `rol_usuario` E | NN |
| activo | boolean | NN |
| pref_idioma | varchar | NN |
| pref_zona_horaria | varchar | NN |
| pref_suscripciones | jsonb | |
| created_at / updated_at | timestamptz | NN |

> ⚠️ **H1** — El DER no modela hash de contraseña, ni nombre, ni estado de invitación pendiente.
> HU-E1-01 RN-01 exige contraseña, HU-E1-04 RN-02 exige el ciclo de invitación y PAN-USR-01 lista
> el nombre. Se resuelve en el Gate 1 de `identidad-y-onboarding`.

---

## BC2 — Datos Maestros · `contexts/master_data`

### `cliente`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| categoria_id | uuid | FK → categoria_empresa |
| nombre | varchar | NN |
| cuit | varchar | |
| condicion_iva | `condicion_iva` E | |
| contacto_whatsapp | varchar | |
| contacto_email | varchar | |
| origen | `origen_dato` E | NN |
| presente_en_planilla | boolean | NN |
| referencia_fila_planilla | varchar | |
| activo | boolean | NN |
| created_at / updated_at | timestamptz | NN |

### `servicio`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| categoria_id | uuid | FK |
| nombre | varchar | NN |
| precio | decimal | NN |
| alicuota_iva | decimal | NN |
| agendable | boolean | NN |
| duracion_estandar_min | integer | |
| origen | `origen_dato` E | NN |
| presente_en_planilla | boolean | NN |
| activo | boolean | NN |
| created_at / updated_at | timestamptz | NN |

### `categoria_empresa`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| nombre | varchar | NN |
| aplica_a | `aplica_a` E | NN |
| created_at | timestamptz | NN |

> `origen` + `presente_en_planilla` son ADR-006 y ADR-007 hechos columna: la planilla de la
> empresa manda sobre los datos maestros, y lo que desaparece de ella se marca ausente, nunca
> se borra.

---

## BC3 — Configuración de Negocio · `contexts/business_config`

### `regla_de_negocio`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| tipo | `tipo_regla` E | NN |
| configuracion | jsonb | NN |
| prioridad | integer | NN |
| activa | boolean | NN |
| created_at / updated_at | timestamptz | NN |

### `plantilla_de_notificacion`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| codigo | varchar | NN |
| idioma | varchar | NN |
| canal | `canal_notificacion` E | NN |
| cuerpo | text | NN |
| estado_aprobacion_meta | varchar | |
| created_at / updated_at | timestamptz | NN |

---

## BC4 — Integración con Sistemas Externos · `contexts/integrations`

### `configuracion_de_integracion`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| sistema | `sistema_externo` E | NN |
| credencial_contenido_cifrado | bytea | NN |
| credencial_algoritmo | varchar | NN |
| parametros | jsonb | |
| ambiente | varchar | NN |
| activa | boolean | NN |
| created_at / updated_at | timestamptz | NN |

> La credencial se guarda cifrada (AES-256-GCM, ADR-011) y el algoritmo queda registrado en su
> propia columna para poder rotarlo sin adivinar con qué se cifró cada fila.

---

## BC5 — Sincronización de Planillas · `contexts/spreadsheet_sync` **[CORE]**

### `mapeo`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| huella_encabezado | varchar | NN |
| estado | `estado_mapeo` E | NN |
| version | integer | NN |
| created_at / updated_at | timestamptz | NN |

### `entrada_de_mapeo` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| mapeo_id | uuid | NN, FK |
| columna_origen | varchar | NN |
| atributo_destino | varchar | NN |
| score | decimal | NN |

### `vinculo_de_planilla`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| configuracion_integracion_id | uuid | FK |
| mapeo_vigente_id | uuid | FK → mapeo |
| proveedor | `proveedor_planilla` E | NN |
| direccion | `direccion_sync` E | NN |
| ultima_lectura | timestamptz | |
| ultima_escritura | timestamptz | |
| hoja_empresa | varchar | NN |
| hoja_cheatsheet | varchar | |
| created_at / updated_at | timestamptz | NN |

### `procesamiento_de_planilla`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| vinculo_id | uuid | NN, FK |
| mapeo_id | uuid | NN, FK |
| estado | `estado_procesamiento` E | NN |
| filas_totales / filas_ok / filas_error | integer | NN |
| duracion_ms | integer | |
| referencia_archivo | varchar | |
| created_at | timestamptz | NN |

### `error_de_fila` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| procesamiento_id | uuid | NN, FK |
| numero_fila | integer | NN |
| motivo | varchar | NN |

---

## BC6 — Facturación · `contexts/billing` **[CORE]**

### `comprobante`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| cliente_id | uuid | NN, FK |
| punto_de_venta_id | uuid | NN, FK |
| tipo | `tipo_comprobante` E | NN |
| estado | `estado_comprobante` E | NN |
| numero | integer | |
| receptor_nombre | varchar | NN |
| receptor_cuit | varchar | NN |
| receptor_condicion_iva | `condicion_iva` E | NN |
| receptor_domicilio | varchar | |
| cae_codigo | varchar | |
| cae_fecha_vencimiento | date | |
| subtotal / total_iva / total / saldo_pendiente | decimal | NN |
| comprobante_origen_id | uuid | FK → comprobante (nota de crédito) |
| turno_id | uuid | (referencia a BC8, sin FK) |
| fecha_emision | timestamptz | |
| created_at / updated_at | timestamptz | NN |

> Single Table Inheritance (ADR-010): un discriminador `tipo` y columnas nullable — lo obligatorio
> por tipo se impone con `CHECK` condicional o dentro del agregado. Los datos del receptor están
> desnormalizados a propósito: un comprobante emitido no cambia porque el cliente edite sus datos
> después. Los cuatro montos son `decimal`, nunca `float` (CLAUDE.md §3.5).

### `item_de_comprobante` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| comprobante_id | uuid | NN, FK |
| descripcion | varchar | NN |
| cantidad / precio_unitario / alicuota_iva / subtotal | decimal | NN |

### `punto_de_venta`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| numero | integer | NN |
| descripcion | varchar | |
| activo | boolean | NN |
| numerador_por_tipo | jsonb | NN |
| created_at | timestamptz | NN |

---

## BC7 — Cobros · `contexts/payments` **[CORE]**

### `cobro`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| cliente_id | uuid | NN, FK |
| comprobante_id | uuid | FK → comprobante |
| turno_id | uuid | (referencia a BC8, sin FK) |
| monto | decimal | NN |
| descripcion | varchar | |
| estado | `estado_cobro` E | NN |
| mp_preference_id / mp_payment_id / mp_url_pago | varchar | |
| created_at / updated_at | timestamptz | NN |

### `recordatorio` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| cobro_id | uuid | NN, FK |
| paso | integer | NN |
| canal | `canal_notificacion` E | NN |
| enviado_en | timestamptz | |
| estado_entrega | `estado_entrega` E | |

> `paso` es lo que hace verificable la cadena de escalamiento de HS-T3: el recordatorio número N
> se envía una sola vez.

---

## BC8 — Agenda · `contexts/scheduling` **[CORE]**

### `turno`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| cliente_id | uuid | NN, FK |
| servicio_id | uuid | NN, FK |
| recurso_id | uuid | NN, FK |
| cobro_id | uuid | FK → cobro (seña, HU-E6-07) |
| franja_inicio | timestamptz | NN |
| franja_duracion_min | integer | NN |
| estado | `estado_turno` E | NN |
| canal_reserva | varchar | |
| created_at / updated_at | timestamptz | NN |

> La franja es inicio + duración, no un rango. La restricción de exclusión con `btree_gist` que
> impide el doble booking se construye sobre esas dos columnas.

### `recurso_reservable`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| tipo | `tipo_recurso` E | NN |
| nombre | varchar | NN |
| activo | boolean | NN |
| created_at | timestamptz | NN |

### `patron_de_disponibilidad` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| recurso_id | uuid | NN, FK |
| dia_semana | integer | NN |
| hora_inicio / hora_fin | time | NN |
| duracion_slot_min | integer | NN |

### `excepcion_de_disponibilidad` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| recurso_id | uuid | NN, FK |
| fecha | date | NN |
| tipo | `tipo_excepcion` E | NN |
| franja_inicio | timestamptz | |
| franja_duracion_min | integer | |

---

## BC9 — Canal Conversacional · `contexts/conversational` **[CORE]**

### `conversacion`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| cliente_id | uuid | NN, FK |
| estado | `estado_conversacion` E | NN |
| contador | integer | NN |
| ultimo_mensaje_en | timestamptz | |
| ventana_maximo | integer | NN |
| created_at | timestamptz | NN |

### `mensaje`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| conversacion_id | uuid | NN, FK |
| empresa_id | uuid | NN, FK |
| direccion | `direccion_mensaje` E | NN |
| tipo_contenido | `tipo_contenido_mensaje` E | NN |
| contenido | text | |
| intencion | varchar | |
| estado_entrega | `estado_entrega` E | |
| timestamp | timestamptz | NN |

### `escalamiento`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| conversacion_id | uuid | NN, FK |
| empresa_id | uuid | NN, FK |
| usuario_asignado_id | uuid | FK → usuario |
| motivo | varchar | NN |
| estado | `estado_escalamiento` E | NN |
| created_at / updated_at | timestamptz | NN |

### `faq`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| categoria_id | uuid | FK |
| pregunta | text | NN |
| respuesta | text | NN |
| embedding_vector | vector(1536) | (`pgvector`) |
| embedding_modelo_version | varchar | |
| embedding_obsoleto | boolean | NN |
| created_at / updated_at | timestamptz | NN |

> `embedding_modelo_version` + `embedding_obsoleto` existen para que cambiar de modelo de
> embeddings no obligue a recalcular todo de golpe ni a servir búsquedas con vectores de dos
> modelos mezclados.

---

## BC10 — Observabilidad y Auditoría · `contexts/observability`

### `registro_de_auditoria`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| usuario_id | uuid | FK → usuario (**nullable**: hay operaciones del sistema) |
| accion | varchar | NN |
| entidad_afectada | varchar | NN |
| resultado | varchar | NN |
| direccion_ip | varchar | |
| timestamp | timestamptz | NN |

> ⚠️ **H2** — No tiene columna `modulo` y **HS-T5 RN-02 la exige** («el registro captura módulo,
> operación, entidad afectada, iniciador, resultado y timestamp»); HU-E12-01 además filtra la
> bitácora por módulo. Conflicto declarado entre dos insumos de Etapa 5.

### `notificacion`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| destinatario_id | uuid | FK → usuario |
| plantilla_id | uuid | FK → plantilla_de_notificacion |
| categoria | varchar | NN |
| severidad | varchar | NN |
| cuerpo | text | NN |
| leida | boolean | NN |
| created_at | timestamptz | NN |

### `tarea_asincrona`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| tipo | varchar | NN |
| payload | jsonb | |
| estado | `estado_tarea` E | NN |
| intentos | integer | NN |
| clave_idempotencia | varchar | NN |
| resultado | text | |
| created_at / updated_at | timestamptz | NN |

### `solicitud_de_soporte`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| usuario_id | uuid | NN, FK |
| asunto | varchar | NN |
| descripcion | text | NN |
| prioridad | varchar | NN |
| estado | `estado_solicitud_soporte` E | NN |
| created_at / updated_at | timestamptz | NN |

---

## BC11 — Reportería · `contexts/reporting`

### `reporte`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| usuario_id | uuid | NN, FK |
| tipo | varchar | NN |
| formato | varchar | NN |
| filtro_desde / filtro_hasta | date | |
| filtros | jsonb | |
| estado | `estado_reporte` E | NN |
| referencia_archivo | varchar | |
| created_at | timestamptz | NN |

### `paquete_contable`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| empresa_id | uuid | NN, FK |
| periodo_anio / periodo_mes | integer | NN |
| totales_por_tipo | jsonb | NN |
| referencia_archivo | varchar | |
| created_at | timestamptz | NN |

### `token_de_acceso_contable` *(entidad interna)*
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| paquete_id | uuid | NN, FK |
| valor | varchar | NN, **U** |
| email_contador | varchar | NN |
| vencimiento | timestamptz | NN |
| accesos | integer | NN |
| revocado | boolean | NN |
| created_at | timestamptz | NN |

> `accesos`, `vencimiento` y `revocado` son las tres cosas que hacen que un enlace público a datos
> fiscales sea auditable y cortable. El contador entra sin cuenta (HU-E10-06), así que el token es
> toda la seguridad que hay.

---

## BC12 — Catálogos de Referencia · `contexts/reference_data`

### `parametro_fiscal`
| Columna | Tipo | |
|---|---|---|
| id | uuid | PK |
| tipo | `tipo_catalogo_fiscal` E | NN |
| codigo | varchar | NN |
| valor | varchar | NN |
| fecha_desde | date | NN |
| fecha_hasta | date | |
| created_at | timestamptz | NN |

> **Sin `empresa_id`**: es el catálogo de ARCA, igual para todas las empresas. `fecha_desde` /
> `fecha_hasta` lo hacen versionado por vigencia — un comprobante se valida contra el parámetro
> que regía el día que se emitió, no contra el de hoy.

---

## Enums

```
rol_usuario:              ADMINISTRADOR · OPERADOR · SOLO_LECTURA
condicion_iva:            RESPONSABLE_INSCRIPTO · MONOTRIBUTO · EXENTO · CONSUMIDOR_FINAL
origen_dato:              PLANILLA · PANEL · AGENTE
estado_comprobante:       BORRADOR · VALIDADO · ENVIADO_A_ARCA · AUTORIZADO · RECHAZADO · ANULADO
tipo_comprobante:         FACTURA_A · FACTURA_B · FACTURA_C · NOTA_CREDITO_A · NOTA_CREDITO_B · NOTA_CREDITO_C
estado_cobro:             PENDIENTE · APROBADO · VENCIDO · CANCELADO · REEMBOLSADO
estado_turno:             RESERVADO · CONFIRMADO · CANCELADO · COMPLETADO · NO_SHOW
tipo_recurso:             PERSONA · ESPACIO · EQUIPO
tipo_excepcion:           BLOQUEO · APERTURA_ESPECIAL
estado_escalamiento:      ABIERTO · ASIGNADO · RESUELTO
estado_conversacion:      ACTIVA · ARCHIVADA
canal_notificacion:       WHATSAPP · EMAIL · PANEL
direccion_mensaje:        ENTRANTE · SALIENTE
estado_mapeo:             BORRADOR · VALIDADO
tipo_contenido_mensaje:   TEXTO · AUDIO · IMAGEN
proveedor_planilla:       GOOGLE_SHEETS · EXCEL_ONLINE
estado_entrega:           ENVIADO · ENTREGADO · LEIDO · FALLIDO
direccion_sync:           SOLO_LECTURA · LECTURA_Y_ESCRITURA
estado_procesamiento:     EN_CURSO · COMPLETADO · FALLIDO
tipo_catalogo_fiscal:     TIPO_COMPROBANTE · ALICUOTA_IVA · CONDICION_IVA · TIPO_DOCUMENTO · MONEDA · UNIDAD_MEDIDA
estado_tarea:             PENDIENTE · EN_CURSO · COMPLETADA · FALLIDA · DLQ
sistema_externo:          ARCA · MERCADOPAGO · WHATSAPP · GOOGLE_SHEETS · EXCEL_ONLINE
estado_reporte:           PENDIENTE · EN_CURSO · LISTO · FALLIDO
tipo_regla:               ESCALAMIENTO_DE_COBRO · POLITICA_DE_TURNO · AGENDA_DE_NOTIFICACION
estado_solicitud_soporte: ABIERTA · EN_REVISION · RESUELTA · CERRADA
aplica_a:                 CLIENTE · SERVICIO · FAQ · TURNO
```

---

## Huecos del DER, para resolver en el Gate 1 que los toque

Ninguno se resuelve acá. Se listan para que la unidad que llegue a ellos los vea **antes** de
codear, y no después.

| # | Hueco | Unidad afectada |
|---|---|---|
| H1 | `usuario` no tiene hash de contraseña, ni nombre, ni estado de invitación pendiente. HU-E1-01 RN-01, HU-E1-04 RN-02 y PAN-USR-01 los exigen | `identidad-y-onboarding`, `usuarios-y-preferencias` |
| H2 | `registro_de_auditoria` no tiene `modulo`; HS-T5 RN-02 y HU-E12-01 sí lo piden | `cimientos-y-bitacora` |
| H3 | No hay tabla de refresh tokens rotativos con detección de reuso (ADR-011) | `identidad-y-onboarding` |
| H4 | `turno.cobro_id` existe como FK, pero `comprobante.turno_id` y `cobro.turno_id` referencian a `turno` **sin** FK declarada. Es coherente con R3 —se referencia por id, no por join entre contextos— pero conviene que sea decisión explícita y no omisión | épicos 5, 6 y 7 |
| H5 | El DER no declara índices ni políticas de RLS: son decisión de cada migración (ver [`backend/migrations/README.md`](../../../backend/migrations/README.md)) | todas |
| H6 | Ninguna entidad interna lleva `empresa_id`. Su política de RLS tiene que ir por el padre (`EXISTS` sobre él) o llevar la columna denormalizada. Decisión pendiente, y aplica a las 7 | primera unidad que persista una entidad interna |
