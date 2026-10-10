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

`ConectorArca`, `VerificadorArca`, `ObtenerTicketDeAcceso` y la tabla `ticket_de_acceso` quedaron en
el código, sin uso en el armado, hasta el 10/10/2026: ver «Cuarta parte».

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

## Segunda parte — hallazgos del 08/10/2026 a la noche

**Prueba local con ARCA simulada.** Funcionaron el onboarding con «Validar contra ARCA» antes de
conectar ARCA, «Continuar» al paso 3, «Verificar delegación» (conectada) y el rechazo de una CUIT
sin delegar. Dos defectos encontrados y corregidos en esta rama:

- **Mayor:** cambiar la CUIT de la empresa dejaba ARCA conectada con la anterior. Ahora la
  desconecta (`InvalidarDelegacionPorCambioDeCuit`) y queda en la bitácora.
- **Menor:** el error de una verificación rechazada quedaba detrás del modal. Ahora se ve adentro.

**Padrón real de homologación**, consultado con el certificado de plataforma:

| CUIT | Respuesta |
|---|---|
| `30000000015` (Estudio Ejemplo SRL, ficticia) | No existe |
| `20222222223` (cliente ficticio) | No existe |
| `33693450239` (ARCA) | Existe con datos de prueba: «PRUEBA F713 WEB 2», sin condición de IVA |

Por eso se agrega **`ARCA_PADRON_ADAPTADOR`**: en staging el padrón queda simulado y WSFE real, así
los datos ficticios de `etapa-6/reglas.md` §6 sirven en todo el panel y la facturación obtiene
un CAE real. En producción el padrón simulado no arranca.

## Tercera parte — prueba con ARCA real, 10/10/2026

API local con `ARCA_ADAPTADOR=arca`, `CATALOGOS_FISCALES_ADAPTADOR=wsfe` y padrón simulado, contra
homologación, con el certificado de plataforma.

| Paso | Resultado |
|---|---|
| Onboarding › «Validar contra ARCA» (padrón simulado) | OK, pero pidió un ticket real a WSAA |
| Integraciones › ARCA › «Verificar delegación» | **Conectado** (WSAA + `FECompUltimoAutorizado` reales) |
| `FEParamGetPtosVenta` para `30000000015` | `602 Sin Resultados` → el alta del punto de venta 1 se rechazó |
| `FECAESolicitar` directo, Factura B, PtoVta 1, consumidor final, $121 | **`Resultado A`, CAE otorgado** (vto. 20/10/2026) |

Conclusión: **homologación da CAE a la empresa ficticia aunque no exista en su padrón**, así que
staging puede facturar de verdad sin datos fiscales reales. Tres defectos encontrados y corregidos
en `fix/integrations-arca-real-en-homologacion`:

- **Mayor:** homologación no lleva registro de puntos de venta, y el alta los pide (HU-E5-05
  RN-03): en staging no se podía dar de alta ninguno. Fuera de producción se usa la habilitación
  simulada (1 a 5 habilitados, 99 bloqueado); en producción sigue siendo la de ARCA.
- **Menor:** con el padrón simulado, la consulta igual pedía un ticket real a WSAA para
  `ws_sr_padron_a5`. Ahora usa `TicketDePadronSimulado`, que no sale del proceso ni se guarda.
- **Menor:** el certificado que entrega WSASS termina sin salto de línea; `cat crt key` pegaba
  los bloques PEM y la API informaba «la clave privada no es un PEM sin cifrar». La configuración
  ahora separa los bloques pegados, y `.env.example` muestra el comando con `echo`.

## Cuarta parte — sin el modelo 1, 10/10/2026

Rama `feature/integrations-sin-modelo-1-de-arca`. Se borra lo que solo servía al certificado
por empresa: `ObtenerTicketDeAcceso`, `TicketDeAcceso`, `PortRepositorioTickets`,
`RepositorioTicketsSQL`, `ConectorArca`, `VerificadorArca`, la base `ArcaSimulado` (queda solo
`ArcaSimuladoPorDelegacion`), `estado_por_vencimiento` y `ARCA_AVISO_VENCIMIENTO_DIAS`, y el campo
`tickets` de `ResultadoDeConexion`. La migración `0042_sin_ticket_de_acceso` elimina la tabla; su
downgrade la recrea vacía, con la misma política de RLS.

Queda sin aviso el vencimiento del **certificado de plataforma** (07/10/2028): el aviso de
vencimiento era por empresa y se fue con el modelo 1. Pendiente para una unidad posterior.

