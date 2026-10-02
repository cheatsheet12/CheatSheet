# Reparto del trabajo restante — Etapa 6

Seis integrantes, una carga estimada de **≈ 32 h por persona** entre el 02/10 y el 31/10/2026.
Cómo se escribe cada parte está en [`reglas.md`](reglas.md); este archivo dice **quién** hace
**qué** y con **qué nombre de archivo**.

## 1. Criterio

La autoría salió de git (líneas agregadas por contexto, sin merges), no de `../units.md`:

| Integrante | Rol | Código escrito |
|---|---|---|
| Cristian Suarez | Arquitecto de Software | identity, integrations, base de observability, fix de payments |
| Juan Caballero | Analista de Infraestructura y Datos | master_data; base de datos de staging |
| Vincenzo Dallape | Gestión de Configuración y Documentación | billing, spreadsheet_sync, reporting, conversational, scheduling, payments, panel de observability |
| Paula Ferreira | Analista Funcional y Diseño de Experiencia | — |
| Emanuel Gomez | Analista de QA | — |
| Luciano Oro | Analista de Integraciones | — |

1. Quien escribió un módulo lo prueba, mientras la carga lo permita.
2. Lo que Vincenzo no puede absorber se reparte entre quienes no tienen commits.
3. **Quien prueba, corrige**; **el autor del código revisa el PR** del arreglo. Si Vincenzo tiene
   más de dos PRs esperando su revisión, los toma Cristian.

## 2. Módulo que prueba y corrige cada integrante

Suman los 68 ítems de la matriz.

| Integrante | Módulos | Ítems | HU / HS | Revisa sus PRs |
|---|---|---|---|---|
| **Cristian** | Identidad y Acceso · Usuarios y Permisos · Integraciones Externas | 12 | HU-E1-01 … HU-E1-07, HU-E2-01 … HU-E2-05 | Juan |
| **Juan** | Datos Maestros · Ingesta y Sincronización de Planillas | 11 | HU-E4-01 … HU-E4-04, HU-E3-01 … HU-E3-07 | Vincenzo (ingesta) · Cristian (datos maestros) |
| **Vincenzo** | Facturación Electrónica · Tablero e Indicadores · Reportería y Paquete Contable | 12 | HU-E5-01 … HU-E5-05, HS-T4, HU-E10-01 … HU-E10-06 | Cristian |
| **Paula** | Cobros · Configuración del Negocio (reglas) | 10 | HU-E6-01 … HU-E6-07, HS-T1, HS-T3, HU-E11-01 | Vincenzo |
| **Emanuel** | Agenda y Recursos · Auditoría y Bitácora · Notificaciones y Soporte | 12 | HU-E7-01 … HU-E7-06, HU-E12-01, HU-E12-02, HS-T5, HS-T6, HU-E11-03, HU-E9-03 | Vincenzo · Cristian (HS-T5) |
| **Luciano** | Canal Conversacional (WhatsApp) · Atención y Escalamiento · Configuración del Negocio (plantillas) | 11 | HU-E8-01 … HU-E8-05, HS-T2, HS-T7, HU-E9-01, HU-E9-02, HU-E9-04, HU-E11-02 | Vincenzo |

### Unidades de código pendientes

Cierran los seis ítems que siguen *En desarrollo*. Van por el flujo AI-DLC completo (plan de
unidad, verificación, PR).

| Unidad | Responsable | Revisa | Cierra |
|---|---|---|---|
| Canal real de WhatsApp para recordatorios y avisos, en reemplazo de `EnvioPorConsola` y `AvisoPorConsola` (pendiente 11 del épico 8) | Luciano | Cristian | HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 |
| ADR del proveedor de embeddings y de transcripción, y sus dos adaptadores (pendientes 1 y 2 del épico 8) | Vincenzo | Cristian | HU-E8-03, HS-T7 |

## 3. Documentación

### 3.1 Pruebas — integra **Emanuel**

| Archivo | Tipo | Qué verifica | HU | Pantalla | Responsable |
|---|---|---|---|---|---|
| `pruebas/00-introduccion.md` | — | Alcance, entorno, datos de prueba, resumen de resultados | — | — | Emanuel |
| `pruebas/PRU-01.md` | Funcional | Emitir un comprobante y obtener su CAE | HU-E5-03 | PAN-FAC-03 | Vincenzo |
| `pruebas/PRU-02.md` | Funcional | Generar un link de cobro para un cliente | HU-E6-03 | PAN-COB-03 | Paula |
| `pruebas/PRU-03.md` | Funcional | Procesar la carga inicial de una planilla | HU-E3-03 | PAN-ING-01 | Juan |
| `pruebas/PRU-04.md` | Funcional | Crear un turno manualmente desde el panel | HU-E7-06 | PAN-AGE-02 | Emanuel |
| `pruebas/PRU-05.md` | Integración | Una reserva hecha por WhatsApp aparece en la agenda y en la bitácora | HU-E8-01, HU-E7-01, HU-E12-01 | PAN-AGE-01, PAN-LOG-01 | Luciano |
| `pruebas/PRU-06.md` | Integración | El webhook de MercadoPago aprueba el cobro, que aparece en el listado y en los indicadores del tablero | HS-T1, HU-E6-01, HU-E10-01 | PAN-COB-01, PAN-REP-01 | Paula |
| `pruebas/PRU-07.md` | Seguridad | Solo Lectura no puede emitir un comprobante, ni en el panel ni llamando a la API | HU-E1-05, HU-E5-03 | PAN-FAC-03 | Cristian |
| `pruebas/PRU-08.md` | Seguridad | Operador no puede gestionar usuarios ni reembolsar un cobro | HU-E1-04, HU-E6-05 | PAN-USR-01, PAN-COB-02 | Cristian |
| `pruebas/PRU-09.md` | Seguridad | Solo Lectura no puede crear clientes; paso adicional: un usuario de otra empresa no ve los clientes de la primera | HU-E4-01 | PAN-DM-01 | Juan |

### 3.2 Manual de usuario del Administrador — integra **Paula**

| Archivo | Capítulo | HU que cubre | Responsable |
|---|---|---|---|
| `manual/00-ingreso-y-navegacion.md` | Ingreso al sistema (login) y navegación entre pantallas | HU-E1-01 (login), menú lateral | Paula |
| `manual/10-acceso-y-usuarios.md` | Datos de la empresa y gestión de usuarios | HU-E1-02 … HU-E1-07 | Cristian |
| `manual/20-integraciones.md` | Conexión con ARCA, MercadoPago y WhatsApp | HU-E2-01 … HU-E2-03, HU-E2-05 | Cristian |
| `manual/30-datos-maestros.md` | Clientes, servicios y categorías | HU-E4-01 … HU-E4-04 | Juan |
| `manual/40-planillas.md` | Vínculo, mapeo, carga y sincronización de planillas | HU-E2-04, HU-E3-01 … HU-E3-07 | Juan |
| `manual/50-facturacion.md` | Comprobantes, notas de crédito y puntos de venta | HU-E5-01 … HU-E5-05 | Vincenzo |
| `manual/60-cobros.md` | Cobros, reembolsos y reglas de recordatorio | HU-E6-01 … HU-E6-07, HU-E11-01 | Paula |
| `manual/70-agenda.md` | Agenda, turnos y disponibilidad de recursos | HU-E7-01 … HU-E7-06 | Emanuel |
| `manual/80-agente-y-atencion.md` | Conversaciones escaladas, FAQ y plantillas | HU-E9-01, HU-E9-02, HU-E9-04, HU-E11-02 | Luciano |
| `manual/90-bitacora-y-notificaciones.md` | Bitácora, notificaciones y soporte | HU-E12-01, HU-E12-02, HU-E11-03, HU-E9-03 | Emanuel |
| `manual/95-reportes.md` | **Sección de reportes** (exigida por la consigna): tablero, reportes y paquete contable | HU-E10-01 … HU-E10-05 | Vincenzo |

### 3.3 Plan de implementación — integra **Cristian**

| Archivo | Sección de la consigna | Responsable |
|---|---|---|
| `plan/00-introduccion-y-metodo.md` | Método elegido (piloto) y **fecha D** de puesta en producción. **Se entrega primero: el 03/10**, porque las demás secciones fechan respecto de D | Cristian |
| `plan/01-puesta-en-produccion.md` | 1 · Plan de puesta en producción | Cristian |
| `plan/02-entorno-de-produccion.md` | 2 · Preparar el entorno de producción | Juan |
| `plan/03-despliegue.md` | 3 · Realizar el despliegue | Juan |
| `plan/04-carga-inicial.md` | 4 · Carga inicial de datos | Paula |
| `plan/05-usuarios-y-permisos.md` | 5 · Usuarios, perfiles y permisos | Emanuel |
| `plan/06-validacion-en-produccion.md` | 6 · Pruebas de validación en producción | Emanuel |
| `plan/07-comunicacion.md` | 7 · Comunicación e inicio de operaciones | Paula |
| `plan/08-contingencia.md` | 8 · Plan de contingencia y rollback | Luciano |

### 3.4 Matriz y documentos ya entregados

| Archivo | Tarea | Responsable |
|---|---|---|
| `matriz/filas-<apellido>.md` | Filas de los ítems propios (§2), actualizadas cada semana | Cada integrante |
| — | Consolidar la **matriz V4** en el `.docx` de Drive, cada semana y para la Demo 2 | Cristian |
| `correcciones/arquitectura.md` | Desactualizado al 25/08: contextos con código, workers y Beat desplegados (PR #42), proveedor de LLM (ADR-0007), cliente WSFEv1 (ADR-0008) | Juan |
| `correcciones/analisis-estatico.md` | Numeración (falta §4 y se cita «§4.3»), cifras que no cierran (24 / 17 + 5 / 10), encabezado «Etapa 5» | Vincenzo |
| `correcciones/capacitacion.md` | Duraciones del resumen por rol que no suman con la tabla; módulo 10 marcado solo para Operador pero contado al Administrador | Paula |

## 4. Carga estimada

| Integrante | Probar | Corregir | PRU | Manual | Plan | Integración / otros | Total |
|---|---|---|---|---|---|---|---|
| Cristian | 8 | 6 | 3 | 4 | 4 | Matriz V4 y plan 5 · revisión 2 | 32 |
| Juan | 8 | 6 | 3 | 4 | 5 | Arquitectura 6 | 32 |
| Vincenzo | 8 | 6 | 1,5 | 5 | — | Análisis estático 1,5 · embeddings y transcripción 10 | 32 |
| Paula | 8 | 6 | 3 | 4 | 5,5 | Manual 4 · capacitación 1 | 31,5 |
| Emanuel | 8 | 6 | 1,5 | 4 | 6 | Pruebas 6 | 31,5 |
| Luciano | 8 | 6 | 1,5 | 4 | 3 | Canal de WhatsApp 10 | 32,5 |

Las horas de corrección son un promedio: dependen de cuántos bugs aparezcan. Si un integrante no
puede corregir con la asistencia de Claude Code, documenta el bug con el test que lo reproduce, el
autor del módulo lo corrige, y el primero toma documentación del segundo a cambio.
