# Unidad: infra-ci-local

**HUs**: ninguna — trabajo de entorno   **Contexto dueño**: ninguno (`platform` + operaciones)
**Rama**: `feature/infra-ci-local`   **Responsable**: Luciano

> **Por qué esta unidad existe sin HU detrás, y por qué no tiene fila en `units.md`.**
> Mismo razonamiento que [`infra-staging-database`](infra-staging-database.md) e
> [`infra-staging-deployment`](infra-staging-deployment.md): `units.md` ata unidades a épicos del
> roadmap por el nombre del épico y `.claude/hooks/aidlc_next.py` lee esa correspondencia; una fila
> con un épico inventado rompería el mapa, y una con un épico real falsearía su estado. El plan vive
> acá. **Divergencia respecto del pedido original**, que mencionaba una fila «como las otras unidades
> de infra»: no existe ninguna fila de ese tipo, así que se siguió el precedente.
> Estado de la unidad: **en curso** (el responsable es Luciano; ver Registro).

---

## Qué hace

La cuota de GitHub Actions de la organización está agotada hasta el 1 de noviembre: todo run de CI
falla en segundos y `CLAUDE.md` §3.4 prohíbe saltear el CI. Esta unidad agrega un script que
reproduce **localmente, paso a paso**, lo que corre `.github/workflows/ci.yml` y emite un resumen en
Markdown (SHA, rama, fecha, cada paso PASS/FAIL/SKIPPED, veredicto) para pegar en el PR. Y propone,
en un ADR **Proposed**, la regla temporal que permite mergear con ese resumen mientras el CI alojado
no esté disponible.

---

## Diseño

- **Dominio / Aplicación / Puertos y adaptadores / Otros contextos / Frontend**: no aplica. Ni una
  línea dentro de `contexts/`.
- **Dónde vive el script — `backend/scripts/local_ci/` + lanzador `backend/scripts/run_local_ci.py`.**
  - `ALLOWED_TOPLEVEL` solo admite `.claude`, `.github`, `backend`, `frontend`, `docs`, y crear un
    directorio raíz exige ADR + hook: descartado.
  - `.claude/` es para agentes y hooks (y el script no es de Claude Code); `.github/` es para lo que
    GitHub interpreta. `backend/scripts/` ya aloja el tooling de operaciones que `ci.yml` invoca
    (`verify_rls.py`, `init-db.sql`) y es donde `CLAUDE.md` §2.3 manda lo que acompaña al backend.
    Aunque el script también corre pasos del frontend y de los guards, su centro de gravedad es el job
    `tests` (PostgreSQL, Redis, RLS), que es del backend. Se justifica por cercanía a lo que invoca.
  - Los tests viven en `backend/tests/scripts/` para entrar en `testpaths`, en la cobertura del 80 % y
    en el CI sin tocar su configuración de descubrimiento.
- **Estructura (todo ≤ 400 líneas / ≤ 50 por función, mypy strict)**: `model.py` (resultados y
  veredicto), `selection.py`, `guard.py` (el host debe ser local), `conventions.py`, `context.py`
  (entorno hijo), `execution.py` (subprocesos con timeout), `runner.py`, `summary.py`, `cli.py` y los
  pasos en `steps_static.py`, `steps_backend.py`, `steps_frontend.py`.
- **Pasos**: los del CI, en su orden, más `worktree-clean` (el SHA del resumen debe ser el código
  verificado) y `frontend-build` (extra opcional, no está en el CI). Obligatorios: todos menos
  `frontend-build`.
- **Códigos de salida**: 0 completo · 1 hay un FAIL · 2 uso · 3 sin FAIL pero un paso obligatorio
  quedó SKIPPED/NOT RUN. Un subconjunto (`--only`) nunca da «complete».

## Infraestructura

- **Migraciones**: no aplica. **Trabajo asíncrono**: no aplica. **Integraciones externas**: no aplica.
- **Contenedores**: proyecto compose propio `cheatsheet-localci` sobre `backend/docker-compose.yml`
  (mismos puertos 5433/6380 que el desarrollo local; volúmenes frescos en cada corrida, que se
  eliminan al final salvo `--keep-containers`). `init-db.sql` se ejecuta con `docker compose exec`
  porque el host puede no tener `psql`.
- **Configuración**: sin variables nuevas ni `.env.example`. El script arma las URLs, descarta las
  del entorno y nunca lee ni escribe `.env`.
- **`pyproject.toml`** (raíz): `backend/scripts` entra en `pythonpath` de pytest y en `mypy_path`, para
  que `local_ci` sea importable desde los tests y verificable por mypy. No relaja ninguna regla.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero · [ ] Comprobantes fiscales / CAE · [ ] Webhooks · [ ] Datos con `empresa_id`
- [ ] Salida de un LLM · [ ] Datos personales o fiscales

Ninguno aplica. El riesgo propio de esta unidad es otro: **un resumen que diga «completo» sin serlo**
(un paso salteado contado como pasado, un subconjunto presentado como total, un árbol sucio) y **correr
la suite destructiva contra una base que no es local**. Ambos tienen tests (veredicto, selección,
guard de host, que una herramienta faltante es SKIPPED).

## Archivos a tocar

- [x] `backend/scripts/local_ci/*.py`, `backend/scripts/local_ci/README.md`
- [x] `backend/scripts/run_local_ci.py`
- [x] `backend/tests/scripts/test_local_ci_pure.py`
- [x] `docs/adr/0016-local-ci-verification.md` (+ índice en `docs/adr/README.md`)
- [x] `pyproject.toml` (`pythonpath`, `mypy_path`)
- [x] `docs/aidlc/units/infra-ci-local.md`
- [x] `backend/tests/README.md` (enlace)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Veredicto: complete / incomplete / failed y sus códigos de salida distintos | unit | pasa |
| 2 | Selección: por defecto todo, `--only` arrastra prerequisitos, `--skip`, id desconocido | unit | pasa |
| 3 | Guard de host: acepta loopback, rechaza remoto y no imprime credenciales | unit | pasa |
| 4 | El entorno hijo descarta `DATABASE_URL` ajeno y fija `APP_ENV=test` | unit | pasa |
| 5 | Reglas de rama y de commits idénticas a las del CI | unit | pasa |
| 6 | Herramienta faltante → SKIPPED; prerequisito caído → SKIPPED; no seleccionado → NOT RUN | unit | pasa |
| 7 | Resumen: SHA, rama, veredicto, escape de `\|`, bloque de salida del FAIL | unit | pasa |
| 8 | Localización de bash (Git Bash, no el lanzador de WSL) y poda de directorios | unit | pasa |
| 9 | Corrida real de los pasos sin Docker (lint, mypy, arquitectura, guards-settings/compile) | manual | pasa |
| 10 | Corrida de extremo a extremo con Docker (servicios, RLS, pytest, integración) | manual | **pendiente: sin Docker todavía** |
| 11 | `guards-behaviour` y `secret-scan` (necesitan `jq` y `gitleaks`) | manual | **pendiente** |
| 12 | Pasos del frontend (necesitan `npm ci`) | manual | **pendiente** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-08 | pedido por Luciano; este plan se escribió junto con la implementación, a pedido expreso |
| 2 · Verificación | | pendiente: los pasos con Docker, `jq`, `gitleaks` y Node no se pudieron ejecutar todavía |
| 3 · PR | | no se hace push ni PR hasta que Luciano lo pida |

## Decisiones tomadas durante la unidad

- ADR propuesto como **0016**: el 0014 es la delegación de ARCA (ya en `develop`) y el 0015 lo reserva `origin/feature/infra-adr-temporizadores-de-beat`.
- Sin fila en `units.md`: se siguió el precedente de las otras unidades `infra-*` (ver arriba).
- `mypy` recibe la lista de archivos por stdin y no por argumentos: la línea de comandos de Windows
  no admite los ~330 archivos que CI pasa con `xargs`.
- En Windows, `bash` del PATH suele ser el lanzador de WSL y se cuelga: se usa el de Git for Windows.
- El ADR queda **Proposed**: aceptarlo y enmendar `CLAUDE.md` §3.4 es decisión del equipo, no de esta
  unidad.
