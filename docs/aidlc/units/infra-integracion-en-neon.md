# Unidad: integracion-en-neon

**HUs**: ninguna — trabajo de entorno   **Contexto dueño**: ninguno (tests de integración + operaciones)
**Rama**: `feature/infra-integracion-en-neon`

> **Por qué existe.** GitHub Actions se quedó sin cuota, así que la suite de integración contra
> PostgreSQL (`backend/tests/integracion/`, ~545 tests, 61 archivos) ya no corre en CI. Se corre en
> local contra una rama de Neon dedicada. Es una unidad técnica de entorno, sin HU.

---

## Qué hace

Permite correr la suite de integración contra Neon **sin poder destruir staging por accidente**, y
con TLS verificado en todas las conexiones de los tests.

---

## Diseño

- **Dominio / Aplicación / Puertos / Otros contextos / Frontend**: no aplica. Ni una línea dentro de
  `contexts/` ni de `src/`.
- **Rama de Neon `integracion`** con una base llamada exactamente `cheatsheet_integracion`. Staging
  usa la base `neondb`, en otra rama: no comparten datos ni cómputo.
- **Guarda** (`backend/tests/integracion/guarda.py`, función pura `verificar_destino`), invocada por
  una fixture autouse de sesión en `conftest.py` de la que depende `esquema_migrado`: nada migra, ni
  baja de versión, ni borra antes de que pase. Reglas: ambas URLs comparten host, puerto y base; si
  el host no es local (`HOSTS_LOCALES`, no se duplica), la base tiene que ser
  `cheatsheet_integracion`. Falla la sesión con `pytest.exit` y un mensaje sin credenciales.
  CI contra `localhost` (base `cheatsheet`) no cambia.
- **Corrección de TLS**: todo `create_async_engine` de los tests que usa esas URLs pasa
  `connect_args=argumentos_de_conexion(url)` (TLS verificado y timeout para hosts no locales).
  Antes, `conftest.py` y 7 archivos conectaban a Neon sin TLS verificado y sin timeout.
- **Documentación**: `backend/tests/README.md` (inglés): variables, formato de URL, credenciales
  fuera del repo, la guarda y cómo reiniciar la base al cambiar de rama con otra cabeza de migración.

---

## Infraestructura

- **Migraciones**: no aplica. La suite migra la base dedicada a `head` en cada sesión.
- **Trabajo asíncrono / Integraciones externas**: no aplica.
- **Configuración**: variables `DATABASE_URL` y `DATABASE_URL_MIGRATIONS` apuntando a la rama
  `integracion`, guardadas en un archivo fuera del repositorio. Sin variables nuevas.

## Riesgos

- [ ] Toca dinero / comprobantes / webhooks / `empresa_id` / LLM / datos personales: no.
- **Latencia**: cada test dispara ~50 `DELETE` por red. Se **mide en la primera corrida**; agrupar
  la limpieza queda **explícitamente fuera de alcance**.
- **Cuota gratuita de Neon**: una corrida completa consume horas de cómputo. Se anota el consumo
  de la primera corrida.
- **Tests con Redis**: se saltean sin `REDIS_URL`; una corrida verde sin Redis no los cubre.
- **Cambio de rama de git**: si las cabezas de migración difieren, hay que reiniciar la base
  (procedimiento en el README).

## Archivos a tocar
- [x] backend/tests/integracion/guarda.py (nuevo)
- [x] backend/tests/integracion/conftest.py
- [x] backend/tests/integracion/test_*.py (7 archivos con engines propios)
- [x] backend/tests/platform/test_guarda_de_integracion.py (nuevo)
- [x] backend/tests/README.md

## Casos de prueba
| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | URLs de CI (localhost, `cheatsheet`) pasan | unit | hecho |
| 2 | Host local con otro nombre de base pasa | unit | hecho |
| 3 | Neon + `cheatsheet_integracion` pasa | unit | hecho |
| 4 | Neon + `neondb` se rechaza | unit | hecho |
| 5 | Host, puerto o base distintos entre las dos URLs se rechazan | unit | hecho |
| 6 | El mensaje no filtra credenciales y apunta al README | unit | hecho |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-08 | aprobado |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- ¿Dónde corre la suite de integración sin CI? → **Rama `integracion` de Neon**, base
  `cheatsheet_integracion`, separada de staging (2026-10-08).
- ¿Se agrupa la limpieza para ahorrar latencia? → **No**, fuera de alcance; primero se mide.
- ¿Dónde viven los tests de la guarda? → En `tests/platform/`, no en `tests/integracion/`: allí la
  fixture autouse `base_limpia` exigiría una base para tests que no la necesitan.
