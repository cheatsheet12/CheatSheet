## Descripción

<!-- ¿Qué resuelve este PR? Contexto breve y motivación. -->

## Módulo afectado

<!-- Marcar el/los módulo(s) tocados. -->

- [ ] intake
- [ ] billing
- [ ] payments
- [ ] agent
- [ ] dashboard
- [ ] reports
- [ ] core
- [ ] tests / docs / infra

## Tipo de cambio

- [ ] `feature/` — nueva funcionalidad
- [ ] `fix/` — corrección de error en `develop`
- [ ] `hotfix/` — corrección urgente en `main`

## Checklist de configuración (obligatorio)

- [ ] **No incluyo credenciales, tokens ni secretos** en el código (hardcoded).
- [ ] Si agregué una integración externa, **actualicé `.env.example`** con las nuevas variables (sin valores).
- [ ] La rama sigue la nomenclatura `feature/` · `fix/` · `hotfix/` y apunta a la rama destino correcta.
- [ ] Agregué/actualicé **tests** del módulo afectado.
- [ ] El pipeline de **CI pasa** (lint + tests + escaneo de credenciales).

> Recordatorio: nadie escribe directo en `main` ni `develop`. Todo cambio entra por PR
> revisado y aprobado, y no puede fusionarse si el CI falla.
