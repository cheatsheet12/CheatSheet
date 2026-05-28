# Gestión de la configuración del software

## 1. Herramienta de control de versiones

El equipo utilizará **Git** como sistema de control de versiones distribuido, con **GitHub** como plataforma de alojamiento centralizado del repositorio.

| Elemento | Definición |
| ----- | ----- |
| **Plataforma** | GitHub |
| **Tipo de repositorio** | Privado, bajo una organización de GitHub creada para el proyecto |
| **Acceso** | Todos los integrantes del equipo tienen acceso como colaboradores con permisos de escritura sobre ramas de trabajo |
| **Responsable de administración** | Arquitecto de Software |

---

## 2. Estructura del repositorio

El repositorio central está organizado por módulo funcional del sistema, reflejando la separación de responsabilidades entre los integrantes del equipo:

```
cheatsheet/
├── intake/            # Módulo de ingesta de datos (Excel, Google Sheets, IA)
├── billing/           # Módulo de facturación electrónica (AFIP/ARCA)
├── payments/          # Módulo de cobros (MercadoPago)
├── agent/             # Agente conversacional (WhatsApp)
├── dashboard/         # Panel de administración web (Frontend)
├── reports/           # Módulo de reportes y paquetes contables
├── core/              # Motor de orquestación y lógica central
├── tests/             # Casos de prueba por módulo
├── docs/              # Documentación técnica interna del repositorio
└── .github/           # Configuración de GitHub Actions y plantillas de PR
```

---

## 3. Estrategia de branching

El equipo adopta la metodología **GitFlow** con la siguiente estructura de ramas permanentes y temporales:

### 3.1 Ramas permanentes

| Rama | Propósito | Quién puede escribir directamente |
| ----- | ----- | ----- |
| `main` | Código en estado de producción o entrega formal. Representa la versión estable del sistema. | Nadie — solo acepta merges desde `develop` mediante Pull Request aprobado |
| `develop` | Rama de integración continua. Contiene el trabajo integrado y funcional del sprint actual. | Nadie — solo acepta merges desde ramas de trabajo mediante Pull Request aprobado |

### 3.2 Ramas temporales

| Tipo | Nomenclatura | Ejemplo | Cuándo se crea | Cuándo se elimina |
| ----- | ----- | ----- | ----- | ----- |
| Nueva funcionalidad | `feature/[módulo]-[descripción]` | `feature/ingesta-mapeo-semantico` | Al iniciar una tarea nueva | Al hacer merge a `develop` |
| Corrección de error | `fix/[módulo]-[descripción]` | `fix/facturacion-validacion-cuit` | Al detectar un bug en `develop` | Al hacer merge a `develop` |
| Corrección urgente en producción | `hotfix/[descripción]` | `hotfix/error-webhook-mercadopago` | Solo ante fallas críticas en `main` | Al hacer merge a `main` y `develop` |

**Regla absoluta:** Ningún integrante escribe código directamente en `main` ni en `develop`. Todo cambio nace en una rama de trabajo y se incorpora exclusivamente mediante Pull Request revisado.

---

## 4. Gestión de credenciales y variables de entorno

El sistema interactúa con servicios externos que requieren credenciales sensibles: AFIP/ARCA, MercadoPago, WhatsApp Business y modelos de IA. El manejo incorrecto de estas credenciales representa un riesgo legal y de seguridad crítico.

### 4.1 Reglas de seguridad

* **Prohibición absoluta de credenciales en el código:** Ninguna clave, token, secreto o contraseña puede aparecer escrita directamente en el código fuente (*hardcoded*). Cualquier Pull Request que contenga credenciales es rechazado de forma inmediata.
* **Archivo `.env` excluido del repositorio:** El archivo `.gitignore` del repositorio incluye explícitamente los archivos `.env` y cualquier variante (`*.env`, `.env.local`, `.env.production`) para impedir su subida accidental.
* **Variables de entorno por entorno:** Cada entorno (desarrollo, testing, producción) tiene su propio conjunto de variables de entorno, gestionadas de forma separada y nunca compartidas entre entornos.

### 4.2 Estructura de variables de entorno

Cada integrante que trabaja en una integración externa dispone de un archivo `.env.example` versionado en el repositorio, que lista las variables necesarias sin sus valores reales:

```bash
# Integración AFIP/ARCA
AFIP_CUIT=
AFIP_CERT_PATH=
AFIP_KEY_PATH=
AFIP_WSAA_URL=
AFIP_WSFE_URL=

# Integración MercadoPago
MP_ACCESS_TOKEN=
MP_WEBHOOK_SECRET=

# Integración WhatsApp Business
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=

# Modelos de IA
AI_API_KEY=
AI_MODEL=

# Base de datos
DATABASE_URL=
```

### 4.3 Distribución segura de credenciales

Las credenciales reales de cada entorno se comparten entre los integrantes autorizados mediante un canal privado y cifrado, **nunca por WhatsApp, Discord ni correo electrónico en texto plano**. El Arquitecto de Software es el responsable de gestionar y distribuir las credenciales de los entornos de testing y producción.

---

## 5. Definición de entornos

El proyecto opera con tres entornos claramente diferenciados, cada uno con un propósito específico y una configuración independiente:

| Entorno | Propósito | Integraciones externas | Datos |
| ----- | ----- | ----- | ----- |
| **Desarrollo** (`dev`) | Trabajo diario de cada integrante en su máquina local | APIs en modo sandbox/homologación (AFIP homologación, MercadoPago sandbox, WhatsApp número de prueba, IA con cuenta de desarrollo) | Datos ficticios generados por el equipo |
| **Testing** (`staging`) | Validación integrada del sistema antes de cada entrega o demo. Entorno compartido del equipo. | APIs en modo sandbox/homologación | Datos de prueba controlados por el Analista de QA |
| **Producción** (`prod`) | Sistema funcionando con PyMEs piloto reales | APIs en modo producción (AFIP producción, MercadoPago producción, WhatsApp número real) | Datos reales — acceso restringido |

**Regla de demos:** Todas las demostraciones ante la cátedra se realizan sobre el entorno de **testing (staging)**, nunca sobre el entorno de desarrollo local de un integrante ni sobre el entorno de producción.

---

## 6. Integración continua (CI)

El repositorio cuenta con un pipeline de integración continua configurado en **GitHub Actions** que se ejecuta automáticamente ante cada Pull Request dirigido a `develop` o `main`. El pipeline realiza las siguientes verificaciones:

| Verificación | Descripción | Condición de falla |
| ----- | ----- | ----- |
| Análisis estático de código | Ejecución del linter sobre el código del PR | El código no cumple las convenciones de estilo definidas |
| Ejecución de tests automáticos | Corrida del conjunto de pruebas del módulo afectado | Al menos un test falla |
| Verificación de variables de entorno | Detección de posibles credenciales hardcodeadas en el código | Se detecta un patrón de credencial en el código |

**Un Pull Request no puede ser fusionado si el pipeline falla.** Esta regla es automática y no puede ser salteada manualmente.

---

## 7. Responsabilidades

| Responsabilidad | Rol |
| ----- | ----- |
| Creación y administración del repositorio | Arquitecto de Software |
| Configuración y mantenimiento del pipeline de CI | Arquitecto de Software |
| Auditoría del cumplimiento de las políticas de configuración | Analista de QA |
| Gestión y distribución de credenciales de entornos | Arquitecto de Software |
| Actualización del archivo `.env.example` ante nuevas integraciones | Analista de Integraciones |
| Verificación periódica de que ninguna credencial fue subida al repositorio | Analista de QA |
