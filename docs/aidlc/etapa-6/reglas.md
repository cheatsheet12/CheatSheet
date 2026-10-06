# Reglas de los entregables de la Etapa 6

**Este archivo es normativo.** Toda parte de un entregable —la escriba una persona o un modelo de
IA— cumple estas reglas. El integrador de cada documento **rechaza** la parte que no las cumpla, en
lugar de corregirla él: así el costo de la regla lo paga quien la rompe, una vez, y no el integrador
en cada parte.

El objetivo es uno solo: que el integrador de cada documento pueda **concatenar sus partes en orden
de nombre de archivo** y obtener un documento coherente, sin reescribir nada. Son varios documentos
finales, uno por entregable de la consigna (§2).

---

## 1. Para el modelo de IA que redacta una parte

Antes de escribir una línea, leé:

1. `CLAUDE.md` §0 (idioma) y §3 (reglas absolutas — en particular, nada de datos reales).
2. Este archivo, completo.
3. Tu fila en [`reparto.md`](reparto.md): qué archivos te tocan y con qué HU.
4. Las HU que cita tu parte, en [`../inputs/historias-de-usuario.md`](../inputs/historias-de-usuario.md),
   y las pantallas en [`../inputs/prototipos.md`](../inputs/prototipos.md).
5. **El código que implementa esas HU**: la ruta del panel en `frontend/src/app/`, la feature en
   `frontend/src/features/<contexto>/` y los casos de uso en
   `backend/src/cheatsheet/contexts/<contexto>/application/`. Los pendientes conocidos de cada
   épico están en [`../epicas/`](../epicas/).

### Lo que la IA no hace nunca

- **No inventa funcionalidad.** Describe lo que el sistema hace **hoy, según el código**, no lo que
  la HU promete. Si difieren, describe el código y anota la diferencia en `observaciones` del
  encabezado (§3), para que el integrador la vea.
- **No inventa resultados ni evidencia.** En una prueba, los campos *Resultado obtenido*, *Estado* y
  *Evidencia* los completa la persona que la ejecutó en staging. La IA deja exactamente
  `PENDIENTE DE EJECUCIÓN` en los tres. Una parte con ese texto no se integra.
- **No escribe datos reales.** Ni CUIT, ni nombres, ni teléfonos, ni correos, ni montos de una
  empresa o persona real. Usa los datos ficticios de §6.
- **No toca archivos de otro integrante**, ni los de integración (`00-…`), salvo que la tarea sea
  suya según `reparto.md`.
- **No promete fechas absolutas** en el plan de implementación: usa la notación relativa de §5.3.
- **No traduce el lenguaje del negocio** (§4).

---

## 2. Dónde vive cada parte

```
docs/aidlc/etapa-6/entregables/
├── pruebas/      PRU-01.md … PRU-09.md, más 00-introduccion.md (integrador)
│   └── capturas/ PRU-05_3.png …
├── manual/       00-ingreso-y-navegacion.md … 95-reportes.md
│   └── capturas/ MAN-60_2.png …
├── plan/         00-introduccion-y-metodo.md … 08-contingencia.md
├── matriz/       filas-<apellido>.md
└── correcciones/ arquitectura.md · analisis-estatico.md · capacitacion.md
```

**Cada carpeta es un documento final distinto**, que se entrega por separado:

| Carpeta | Documento final | Actividad de la consigna |
|---|---|---|
| `pruebas/` | Pruebas del sistema (PRU-01 … PRU-09) | Planificación, ejecución y documentación de pruebas |
| `manual/` | Manual de usuario — Administrador | Manual de usuario |
| `plan/` | Plan de implementación | Planificación de la implementación |
| `matriz/` | Matriz de trazabilidad consolidada (V4 y siguientes) | Codificación del sistema |
| `correcciones/` | No genera documento: corrige los ya entregados en Drive | Arquitectura · Análisis estático · Capacitación |

Una parte pertenece a un solo documento y nunca cita el número de sección o página de otro: cita
por ID (§4.4).

- **Un archivo por parte**, con el nombre exacto que asigna `reparto.md`. El prefijo numérico es el
  orden en el documento final: no se cambia.
- Cada parte entra por **su propio PR**, desde una rama `feature/infra-e6-<parte>-<apellido>`
  (por ejemplo `feature/infra-e6-manual-cobros-ferreira`), con commit
  `docs(infra): <qué agrega>`. Como cada uno toca solo sus archivos, no hay conflictos de merge.
- Las capturas van en `capturas/` del mismo entregable, en PNG.

---

## 3. Encabezado obligatorio de cada archivo

Todo archivo empieza con este bloque, que el integrador **borra** al armar el documento:

```markdown
---
entregable: manual            # pruebas | manual | plan | matriz | correcciones
parte: 60-cobros
responsable: Paula Ferreira
estado: borrador              # borrador | revisado | listo
hu: [HU-E6-01, HU-E6-02, HU-E6-03]
fuentes:                      # archivos del repo leídos para escribir esta parte
  - frontend/src/features/payments/
  - backend/src/cheatsheet/contexts/payments/application/
observaciones: >              # diferencias entre HU y código, dudas para el integrador; o "ninguna"
  ninguna
---
```

El integrador solo toma partes en `estado: listo`. Pasa a `listo` quien la revisó (§7), no quien
la escribió.

---

## 4. Reglas de redacción — todas las partes

### 4.1 Formato Markdown permitido

Solo esto, porque es lo que se convierte a Google Docs sin pérdida:

- Títulos `##`, `###`, `####`. **Nunca `#`**: el título 1 es del integrador. Cada parte abre con
  un único `##`.
- Párrafos, listas con `-` o numeradas, **negrita**, *cursiva*, `código` para rutas y nombres de
  campo.
- Tablas Markdown, con fila de encabezado.
- Imágenes: `![Figura PRU-05-3 — La agenda muestra el turno reservado](capturas/PRU-05_3.png)`.

Prohibido: HTML, emojis, notas al pie, Mermaid u otros diagramas en texto (no sobreviven a la
conversión: un diagrama va como PNG), enlaces a URLs externas, colores, separadores `---` en el
cuerpo.

### 4.2 Estilo

- Español neutro formal. **Sin voseo y sin «usted»**: tercera persona y tiempo presente
  («El Administrador genera el link», no «Generás el link»).
- En los pasos del manual y de las pruebas, **infinitivo**: «Ingresar a Cobros», «Completar el
  monto».
- Fechas `dd/mm/aaaa`. Montos con `$`, separador de miles `.` y decimales `,`: `$ 12.500,00`.
- Sin primera persona («nosotros», «hicimos») y sin referencias a la IA, al prompt ni a este
  archivo.
- Nada de introducciones genéricas («En la actualidad, la gestión…»). La primera oración dice qué
  hace la funcionalidad.

### 4.3 Vocabulario cerrado

| Se escribe | Nunca |
|---|---|
| Administrador, Operador, Solo Lectura | admin, usuario común, lector, invitado |
| el panel | la app, la aplicación, la web, el dashboard (salvo la pantalla «Tablero») |
| empresa | tenant, cliente (para referirse a la empresa usuaria), organización |
| cliente | para el cliente **de la empresa** (el que paga o reserva) |
| comprobante, cobro, turno, recurso, mapeo, planilla, CAE, CUIT, condición frente al IVA, punto de venta, nota de crédito | factura (salvo «Factura A/B/C» como tipo), pago (por cobro), cita, reserva (por turno) |
| ARCA | AFIP (salvo al citar un nombre técnico existente) |
| MercadoPago, WhatsApp, Google Sheets | Mercado Pago, Whatsapp, GSheets |
| staging (entorno de pruebas) | testing, QA, desarrollo |

**Nombres de módulo** — exactamente estos quince, como en la matriz:
Identidad y Acceso · Usuarios y Permisos · Integraciones Externas · Configuración del Negocio ·
Datos Maestros · Ingesta y Sincronización de Planillas · Facturación Electrónica · Cobros ·
Agenda y Recursos · Canal Conversacional (WhatsApp) · Atención y Escalamiento · Tablero e
Indicadores · Reportería y Paquete Contable · Auditoría y Bitácora · Notificaciones y Soporte.

### 4.4 Referencias

- **Siempre por ID, nunca por página ni por «más arriba»:** `HU-E6-03`, `HS-T1`, `PAN-COB-02`,
  `PRU-05`, `MAN-60` (capítulo del manual), `PLAN-§4`.
- Los IDs se copian de `../inputs/historias-de-usuario.md` y `../inputs/prototipos.md`. Un ID que
  no aparece ahí no existe.
- La primera mención de una HU lleva su título: «HU-E6-03 — Generar un link de cobro para un
  cliente». Las siguientes, solo el ID.

### 4.5 Capturas

- **Solo de staging**, con los datos ficticios de §6. Nunca del entorno local ni de producción.
- Nombre: `<ID>_<n>.png` (`PRU-05_3.png`, `MAN-60_2.png`). Ancho mínimo 1280 px, sin la barra del
  navegador ni el escritorio.
- Epígrafe en el texto alternativo: `Figura <ID>-<n> — <qué muestra>`.
- La captura la toma una persona. La IA solo deja el lugar: `![Figura MAN-60-2 — …](capturas/MAN-60_2.png)`.

---

## 5. Plantillas por tipo de entregable

Las secciones van **en este orden y con estos títulos exactos**. No se agregan ni se quitan.
Los comentarios `<!-- … -->` de las plantillas son indicaciones para quien escribe: **no se copian**
a la parte.

### 5.1 Prueba (`pruebas/PRU-nn.md`)

```markdown
## PRU-05 — Una reserva hecha por WhatsApp aparece en la agenda

**Tipo:** Integración          <!-- Funcional | Integración | Seguridad y control de acceso -->

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-05 |
| CU/HU referenciado | HU-E8-01, HU-E7-01 |
| Pantalla / Reporte | PAN-AGE-01 |
| Datos de entrada | Datos concretos de §6 |
| Pasos | 1. … <br> 2. … |
| Resultado esperado | Copia de los criterios de aceptación de la HU que verifica |
| Resultado obtenido | PENDIENTE DE EJECUCIÓN |
| Estado | PENDIENTE DE EJECUCIÓN |
| Evidencia | PENDIENTE DE EJECUCIÓN |

### Módulos involucrados          <!-- solo en pruebas de integración -->
### Comprobación en el backend    <!-- solo en pruebas de seguridad: la petición directa a la API
                                       y la respuesta esperada (403 / 404), además de la pantalla -->
```

- Es el **único** lugar donde se permite `<br>` (para numerar pasos dentro de la celda).
- Estado admite solo: **Aprobada · Fallida · Re-ejecutada**. Si falló, se abre un issue, se corrige y
  se vuelve a ejecutar: el estado queda *Re-ejecutada* y *Resultado obtenido* cuenta las dos
  corridas.
- Una prueba de seguridad verifica **las dos capas**: que el panel no muestre la acción y que la API
  la rechace aunque se la llame directamente.

### 5.2 Capítulo del manual (`manual/NN-<tema>.md`)

Manual del rol **Administrador**, organizado por funcionalidad.

```markdown
## Cobros

### Para qué sirve
### Quién puede usarla        <!-- roles con permiso, según el código -->
### Cómo llegar               <!-- ruta del menú lateral: «Menú › Cobros» -->
### <Funcionalidad 1>         <!-- una por HU del capítulo, con el título de la acción -->
#### Paso a paso              <!-- numerado, una acción por paso, en infinitivo -->
#### Mensajes y errores frecuentes   <!-- tabla: Mensaje · Qué significa · Qué hacer -->
### <Funcionalidad 2>
…
```

- Un capítulo ocupa entre una y cuatro páginas.
- El texto de un botón, campo o mensaje se copia **literal del código del frontend**, entre comillas
  latinas: «Generar link».

### 5.3 Sección del plan de implementación (`plan/NN-<tema>.md`)

```markdown
## 4. Carga inicial de datos

### Objetivo
### Actividades
| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 4.1 | … | Analista de Infraestructura y Datos | D-5 | 2.3 |
### Criterio de listo
### Riesgos
| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
```

- **Fechas relativas a D**, el día de puesta en producción: `D-10`, `D`, `D+3`. La fecha real de D
  y el método de implementación los fija únicamente `plan/00-introduccion-y-metodo.md`. Así las
  ocho secciones no se contradicen.
- Los responsables se nombran por **rol** (Arquitecto de Software, Analista de Infraestructura y
  Datos, Analista Funcional y Diseño de Experiencia, Analista de QA, Analista de Integraciones,
  Gestión de Configuración y Documentación), nunca por nombre de persona.
- La columna *Depende de* cita actividades de otras secciones por su número (`2.3`), lo que obliga
  a leer la sección de la que se depende antes de escribir.
- Lo que el sistema ya resuelve se cita, no se reinventa: el despliegue de staging
  (`docs/staging-deployment.md`, `render.yaml`), el rol de base de datos
  (`backend/scripts/provision_app_role.py`), la verificación de aislamiento (`verify_rls.py`).
  La producción **no está decidida** (ADR-0006): el plan la propone, no la da por hecha.

### 5.4 Filas de la matriz (`matriz/filas-<apellido>.md`)

Una tabla con **las mismas 9 columnas de la V3**, una fila por ítem asignado:

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |

- *Estado de codificación*: **No iniciado · En desarrollo · Codificado · Probado**.
- *Integración real*: **No aplica · Simulada · pendiente de validar · Sin implementar**.
- Regla de la V3: si una regla de negocio de la HU exige un servicio o canal sin adaptador real, el
  ítem es *En desarrollo* aunque tenga tests.
- *Probado* exige el PR mergeado a `develop`, sus tests en verde **y** la prueba manual del módulo
  sin bugs críticos abiertos.

### 5.5 Correcciones (`correcciones/*.md`)

Una lista de cambios sobre el documento de Drive, no el documento entero:

```markdown
## Correcciones a «CheatSheet - Arquitectura del Sistema»

| Sección | Dice | Debe decir | Fuente |
|---|---|---|---|
| §8 | «Tres contextos con código» | … | `git log`, `backend/src/cheatsheet/contexts/` |
```

---

## 6. Datos ficticios — los únicos permitidos

| Dato | Valor |
|---|---|
| Empresa | **Estudio Ejemplo SRL** · Responsable Inscripto · CUIT según la tabla de abajo |
| Segunda empresa (pruebas de aislamiento) | **Taller Muestra SA** · CUIT `30-11111111-8` |
| Administrador | `admin.<apellido>@estudio-ejemplo.test` (por ejemplo, `admin.ferreira@estudio-ejemplo.test`) |
| Operador | `operador.<apellido>@estudio-ejemplo.test` |
| Solo Lectura | `lectura.<apellido>@estudio-ejemplo.test` |
| Clientes | Ana Prueba · Bruno Ficticio · Carla Demo, CUIT `20-22222222-3`, `20-22222223-1` y `20-22222224-9` |
| Teléfono WhatsApp | `+54 9 11 0000-0000` y siguientes |
| Servicios | Consulta general ($ 15.000,00, IVA 21 %), Sesión de seguimiento ($ 9.500,00, IVA 21 %) |

**Staging es compartido y el sistema no admite dos empresas con el mismo CUIT ni dos cuentas con
el mismo email.** Por eso cada integrante registra **su propia** Estudio Ejemplo SRL, con su CUIT y
sus correos:

| Integrante | CUIT de su Estudio Ejemplo SRL |
|---|---|
| Cristian Suarez | `30-00000001-5` (ya registrada el 05/10/2026) |
| Juan Caballero | `30-00000002-3` |
| Vincenzo Dallape | `30-00000003-1` |
| Paula Ferreira | `30-00000004-9` |
| Emanuel Gomez | `30-00000005-8` |
| Luciano Oro | `30-00000006-6` |

Todos los CUIT de esta sección tienen el dígito verificador correcto: el panel y la API rechazan
uno inválido y el onboarding no avanza. `30-00000000-7` ya está tomado en staging: no se usa.

El dominio `.test` está reservado y nunca resuelve: un correo de prueba no le llega a nadie.

---

## 7. Revisión e integración

1. **Revisión cruzada:** cada parte la revisa **otro** integrante antes de pasar a `listo`, contra
   esta checklist:
   - [ ] Encabezado completo (§3), con `fuentes` reales.
   - [ ] Estructura y títulos exactos de su plantilla (§5).
   - [ ] Solo el Markdown permitido (§4.1). Ningún `#`.
   - [ ] Vocabulario cerrado (§4.3) y nombres de módulo exactos.
   - [ ] Todos los IDs existen en los insumos (§4.4).
   - [ ] Lo descrito coincide con el código, no solo con la HU.
   - [ ] Ningún dato real (§6). Ningún `PENDIENTE DE EJECUCIÓN` si es una prueba ya ejecutada.
2. **Integración:** el integrador del documento (ver `reparto.md`):
   1. toma las partes en `listo`, en orden de nombre de archivo;
   2. borra los encabezados;
   3. escribe su `00-…` (introducción y título 1);
   4. importa el resultado a un Google Doc en la carpeta del proyecto y aplica el estilo de los
      documentos ya entregados (Arial, apaisado solo la matriz);
   5. si una parte no cumple las reglas, **la devuelve** a su responsable con el ítem de la
      checklist que falla. No la corrige.

---

## 8. Pruebas manuales y bugs

1. Cada integrante prueba **su módulo** (ver `reparto.md`) en **staging**, recorriendo **cada
   criterio de aceptación** de cada HU asignada, con los tres roles.
2. Cada bug es un **issue de GitHub** con: módulo, HU, pasos, resultado esperado, resultado obtenido,
   captura y severidad:
   - **Crítico** — dinero, comprobante fiscal, datos de otra empresa, pérdida de datos, o bloquea la
     HU entera.
   - **Mayor** — un criterio de aceptación no se cumple.
   - **Menor** — texto, estilo, comportamiento con alternativa.
3. **Quien encuentra el bug lo corrige**, siguiendo el flujo AI-DLC del repositorio: rama
   `fix/<módulo>-<descripción>`, plan de unidad, **un test que reproduce el bug antes del arreglo**
   (`CLAUDE.md` §5), y el PR lo revisa el autor original del módulo (ver `reparto.md`).
4. Los críticos de Facturación, Cobros y Agenda se cierran **antes del 13/10** (Demo 2).
5. Un ítem de la matriz no pasa a *Probado* con un bug crítico o mayor abierto.
