# Unidad: delegacion-arca

**HUs**: HU-E2-01 (RN-01, corregida), HU-E1-02 (RN-01), HU-E5-03   **Contexto dueño**: integrations   **Rama**: feature/integrations-delegacion-arca

> Implementa [ADR-0014](../../adr/0014-arca-web-service-delegation.md). Por pedido explícito del
> usuario (08/10/2026) se hizo sin Gate 1: el ADR fija las decisiones y este registro cuenta qué se
> hizo y cómo se verificó.

## Qué cambia

- **Una empresa ya no carga certificados.** Delega «Facturación Electrónica» en la CUIT de
  CheatSheet desde el Administrador de Relaciones de Clave Fiscal, y en Integraciones › ARCA toca
  «Verificar delegación».
- **CheatSheet llega a ARCA con un solo certificado de plataforma** (`ARCA_CREDENCIAL_PLATAFORMA`),
  en representación de la CUIT de cada empresa.
- **El padrón se consulta como la plataforma**: ya no exige que la empresa haya conectado ARCA, y
  el paso 2 del onboarding puede validar el CUIT (cierra la diferencia D-08 del guion de prueba).

## Evidencia previa (homologación, 08/10/2026)

WSASS aceptó autorizar el certificado de plataforma a `wsfe` con «CUIT representado» `30000000015`
(Estudio Ejemplo SRL, ficticia), y `FECompUltimoAutorizado` con `<Cuit>30000000015</Cuit>` respondió
HTTP 200 y `CbteNro 0`.

## Piezas

| Capa | Pieza |
|---|---|
| Dominio | `TicketDePlataforma` (`domain/ticket.py`) |
| Aplicación | `ObtenerTicketDePlataforma`, `PortRepositorioTicketsDePlataforma`, `TicketTodaviaVigente`; `ConsultarPadron` con el ticket y la CUIT de la plataforma |
| Infraestructura | `arca/delegacion.py` (`ConsultaDeDelegacion`, `ConectorDelegacionArca`, `VerificadorDelegacionArca`), `ArcaSimuladoPorDelegacion`, `RepositorioTicketsDePlataformaSQL` con `FOR UPDATE`, migración `0036_ticket_de_plataforma` |
| Composición | `Integraciones.armar` arma el ticket de plataforma; `api/arca.py` y `api/padron.py` lo usan; el router toma la CUIT de `identity` y **ignora el cuerpo** para ARCA |
| Frontend | `FormularioDeArca`: instrucciones de delegación y «Verificar delegación»; la página pasa `CUIT_DE_CHEATSHEET` |
| Configuración | `ARCA_CREDENCIAL_PLATAFORMA` (API y worker), `CUIT_DE_CHEATSHEET` (panel), en los `.env.example` y en `render.yaml` |

`ConectorArca`, `VerificadorArca`, `ObtenerTicketDeAcceso` y la tabla `ticket_de_acceso` quedan en
el código, sin uso en el armado, con sus tests: los borra una unidad posterior.

## Verificación (08/10/2026, con PostgreSQL y Redis)

```
ruff format --check / ruff check   sin cambios · All checks passed!
mypy .                             Success: no issues found in 696 source files
guard_architecture --scan          801 file(s) checked — architecture boundaries intact
pytest --cov                       2885 passed · 88,60 %
frontend: vitest 1154 passed · 90,14 % · tsc, eslint, prettier limpios · next build ok
```

Tests nuevos o reescritos: `test_tickets_de_plataforma.py` (6), `test_arca_delegacion.py` (11),
`test_arca_simulado_por_delegacion.py` (5), `test_credencial_de_plataforma.py` (4),
`test_padron.py` de integrations (9), `test_arca_ciclo_de_vida.py` (11, contra PostgreSQL),
y los ajustes de `test_api_empresa_padron.py`, `test_api_clientes.py` y la grilla del panel.

## Para ponerlo en staging

1. En WSASS, autorizar el certificado de plataforma (`cheatsheet`) a `wsfe` con CUIT representado
   = la CUIT de cada empresa de prueba, y a `ws_sr_padron_a5` con la propia CUIT de la plataforma.
2. En Render: `ARCA_CREDENCIAL_PLATAFORMA` (API y worker) y `CUIT_DE_CHEATSHEET` (panel), y recién
   después `ARCA_ADAPTADOR=arca`: con ARCA real y sin la credencial, la API y el worker no arrancan.
   Staging hoy corre ARCA simulada, así que el merge solo no rompe nada.
3. En el panel, Integraciones › ARCA › «Verificar delegación».
