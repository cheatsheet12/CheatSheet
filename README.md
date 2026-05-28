# CheatSheet

Plataforma para PyMEs: ingesta de datos, facturación electrónica (AFIP/ARCA),
cobros (MercadoPago), agente conversacional (WhatsApp), reportes contables y un
panel de administración web.

> Este repositorio arranca con la **gestión de la configuración** ya montada
> (estructura, branching, manejo de credenciales, entornos y CI). El plan completo
> está en [`docs/gestion-configuracion-software.md`](docs/gestion-configuracion-software.md).

## Estructura

> **Pendiente de definir.** La estructura de carpetas final dependerá de la
> arquitectura, que aún no está decidida. Por ahora el repo solo contiene la
> infraestructura de configuración (CI, plantillas, documentación y archivos raíz).

Stacks previstos: **Python** para el backend / módulos del sistema y **Next.js** para
el panel de administración web. La organización por módulos propuesta en el plan
(ingesta, facturación, cobros, agente, reportes, core, dashboard) se materializará
cuando se defina la arquitectura.

| Carpeta | Contenido |
| --- | --- |
| `docs/` | Documentación técnica interna (incluye el plan de configuración) |
| `.github/` | CI (GitHub Actions) y plantilla de PR |

## Branching (GitFlow)

- `main` — producción / entrega formal. **Nadie escribe directo.**
- `develop` — integración continua. **Nadie escribe directo.**
- `feature/[módulo]-[descripción]` — nueva funcionalidad → PR a `develop`
- `fix/[módulo]-[descripción]` — corrección de bug → PR a `develop`
- `hotfix/[descripción]` — urgencia en producción → PR a `main` (y luego a `develop`)

Todo cambio entra **exclusivamente por Pull Request revisado**; no se fusiona si el CI falla.

## Entornos

| Entorno | Uso | APIs externas |
| --- | --- | --- |
| `dev` | Local de cada integrante | sandbox / homologación |
| `staging` | Validación integrada del equipo (demos) | sandbox / homologación |
| `prod` | PyMEs piloto reales | producción |

Las **demos ante la cátedra siempre se hacen sobre `staging`**.

## Puesta en marcha local

```bash
# 1. Copiar la plantilla de variables de entorno y completarla
cp .env.example .env        # NUNCA se versiona

# 2. Backend (Python 3.11)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Linter y tests
ruff check .
pytest
```

> Las credenciales reales se distribuyen por un **canal privado y cifrado**, nunca por
> WhatsApp, Discord ni correo en texto plano (ver sección 4.3 del plan).

## Integración continua

El workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada PR a
`develop` o `main` y verifica:

1. **Lint** — `ruff` (Python) y `ESLint` (dashboard).
2. **Tests** — `pytest`.
3. **Credenciales** — `gitleaks` detecta secretos hardcodeados.

## Configuración pendiente en GitHub (lado servidor)

Estos ajustes viven en GitHub y se aplican una sola vez por el **Arquitecto de Software**
(ver [`docs/gestion-configuracion-software.md`](docs/gestion-configuracion-software.md)):

- Repositorio **privado** bajo la organización del proyecto.
- **Protección de ramas** en `main` y `develop`: prohibir push directo, exigir PR con
  al menos una aprobación y que los checks de CI pasen antes de fusionar.
- Distribución de credenciales de `staging` y `prod` por canal seguro.
