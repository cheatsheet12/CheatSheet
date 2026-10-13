# Unidad: ticket-de-plataforma-persistido

**HUs**: HU-E2-01, HU-E2-05, HU-E5-03   **Contexto dueño**: integrations   **Rama**: fix/integrations-ticket-de-plataforma-persistido

## Qué hace

El ticket de acceso que ARCA entrega al certificado de plataforma queda guardado **apenas ARCA lo
entrega**, aunque la operación que lo pidió falle después. Hoy se guarda en la transacción del
pedido: si la conexión se rechaza (una empresa que no delegó) o la emisión de un comprobante
falla, la transacción se deshace con el ticket adentro. ARCA no entrega otro mientras ese siga
vigente (`coe.alreadyAuthenticated`), así que durante unas 12 horas **ninguna empresa** puede
reconectar ARCA ni obtener CAE.

## Diagnóstico

Reproducido en staging el 13/10/2026 (hora UTC, log de la API):

| Hora | Qué pasó |
|---|---|
| 18:57:07 | Verificación de delegación de una empresa sin delegar (30-71555551-0): `LoginCms` 200, ticket WSFE emitido y guardado con `flush` dentro de la transacción del pedido |
| 18:57:08 | `ConexionRechazada` (la CUIT no delegó) → 422 → `sesion_de_empresa` hace `rollback`: el ticket se pierde |
| 18:58:58 y 19:00:50 | Reconexión de Estudio Ejemplo SRL: no hay ticket guardado, se pide otro, `LoginCms` 500 `coe.alreadyAuthenticated` → «No se pudo completar la operacion» |

La causa está en el diseño, no en un caso raro: `RepositorioTicketsDePlataformaSQL` escribe en la
sesión de la unidad de trabajo (`api/arca.py` lo dice a propósito: «that row has to be written
together with everything else the request does»). Cualquier excepción posterior a la emisión del
ticket lo descarta. En producción, un cliente que se equivoque al conectar deja a **todas** las
empresas sin facturar medio día.

## Diseño

- **Dominio**: sin cambios. `TicketDePlataforma` y sus reglas de renovación (`hay_que_renovar`,
  `vigente`) quedan como están.
- **Aplicación**: `ObtenerTicketDePlataforma.ejecutar` conserva su contrato (entrada: servicio;
  salida: `TicketVigente`; error: `TicketNoDisponible`) y su lógica de ADR-0004 (reusar hasta el
  margen, volver al guardado si renovar falla). Cambia **dónde** ocurre: todo el ciclo
  leer-con-bloqueo → emitir → guardar corre dentro de una **reserva** que el repositorio abre y
  confirma por su cuenta.
- **Puertos y adaptadores**: `PortRepositorioTicketsDePlataforma` reemplaza
  `buscar_para_renovar` + `guardar` por `reservar(servicio)`, un context manager asíncrono que
  entrega una `ReservaDeTicket` (`guardado: TicketDePlataforma | None` y `guardar(ticket)`). El
  adaptador SQL abre **su propia sesión y transacción** sobre el mismo engine (`sesion.bind` de
  la unidad de trabajo, así ninguno de los 15 lugares que arman `Integraciones` cambia), toma el
  `FOR UPDATE`, y al salir confirma; si algo adentro lanza, deshace. La tabla no tiene RLS
  (ADR-0014 §2), así que esa sesión no necesita declarar empresa.
  - Efecto secundario bueno: el bloqueo de la fila dura lo que tarda `LoginCms` (~1 s), no todo el
    pedido. Hoy una emisión lenta retiene a cualquier otro pedido que necesite ticket.
  - Costo: un pedido que usa ARCA toma dos conexiones del pool por un instante, en lugar de una.
- **Otros contextos**: ninguno nuevo. `billing` y `reference_data` siguen llegando por
  `api/arca.py` → `ObtenerTicketDePlataforma`, sin cambiar su llamada; solo se corrige el
  docstring de `armar_credenciales`, que hoy justifica el diseño equivocado.
- **Frontend**: no aplica.

## Infraestructura

- **Migraciones**: no aplica. La tabla `ticket_de_plataforma` ya existe (0036).
- **Trabajo asíncrono**: no aplica. Los workers que emiten comprobantes usan el mismo caso de uso
  y quedan corregidos con él.
- **Configuración**: no aplica.
- **Integraciones externas**: WSAA sin cambios de timeout ni reintentos. Lo que cambia es que un
  ticket emitido nunca se pierde por un rollback ajeno.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → no aplica
- [x] Toca comprobantes fiscales / CAE → la emisión depende de este ticket; el test de integración
  cubre que una falla después de emitirlo no lo pierde
- [ ] Consume un webhook → no aplica
- [ ] Agrega datos con `empresa_id` → no aplica: la tabla no es de una empresa (ADR-0014 §2)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales → no aplica

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/integrations/application/ports.py` — `reservar` y `ReservaDeTicket`
- [ ] `backend/src/cheatsheet/contexts/integrations/application/tickets_de_plataforma.py`
- [ ] `backend/src/cheatsheet/contexts/integrations/infrastructure/repositories.py` — `RepositorioTicketsDePlataformaSQL` con sesión propia
- [ ] `backend/src/cheatsheet/api/arca.py` — docstring de `armar_credenciales`
- [ ] `backend/tests/contexts/integrations/application/test_tickets_de_plataforma.py` — el doble en memoria pasa a la reserva
- [ ] `backend/tests/contexts/integrations/application/test_padron.py` — si usa el doble anterior
- [ ] `backend/tests/integracion/test_ticket_de_plataforma.py` — nuevo, contra PostgreSQL
- [ ] `docs/adr/0014-arca-web-service-delegation.md` — una línea en §Decision 2: el ticket se confirma en su propia transacción
- [ ] `docs/aidlc/TODO.md` — registrar el bug y su cierre

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **Reproduce el bug** (rojo primero): dentro de una unidad de trabajo se obtiene un ticket nuevo y después se lanza una excepción; tras el rollback, una sesión nueva encuentra el ticket guardado | integración | rojo antes del arreglo (`0 == 1`), verde después |
| 2 | Después de ese rollback, un segundo pedido reutiliza el ticket guardado y el emisor no se llama de nuevo | integración | rojo antes del arreglo (2 llamadas al emisor), verde después |
| 3 | Dos pedidos simultáneos sin ticket guardado llaman al emisor **una sola vez**: el segundo espera el bloqueo y reutiliza | integración | rojo antes del arreglo (`UniqueViolation`: el `FOR UPDATE` no bloquea una fila que no existe), verde después |
| 4 | Si el emisor falla con `TicketTodaviaVigente` y hay uno guardado vigente, se devuelve el guardado y no se escribe nada | unit | verde |
| 5 | Si el emisor falla y no hay ticket utilizable, `TicketNoDisponible` y nada se escribe | unit | verde |
| 6 | El ticket se guarda cifrado; el texto plano nunca llega a la fila | integración | verde (ya cubierto por `test_arca_ciclo_de_vida.py::test_el_ticket_de_plataforma_se_guarda_cifrado`) |
| 7 | **Staging**: verificar delegación con una empresa sin delegar (rechazo) y enseguida reconectar Estudio Ejemplo SRL → Conectada, con un solo `LoginCms` en el log | manual | pendiente |

El caso 7 recién puede correrse cuando venza el ticket huérfano de hoy (≈ 06:57 UTC del 14/10/2026),
o antes con un certificado de homologación nuevo.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado |
| 2 · Verificación | 2026-10-13 | aprobado: ruff, mypy, arquitectura y guardas limpios; pytest 3986 pasan con PostgreSQL local; cobertura 90.05 %. Caso 7 (staging) pendiente del despliegue y del vencimiento del ticket huérfano |
| 3 · PR | 2026-10-13 | push de la rama; PR abierto por el responsable |

## Decisiones tomadas durante la unidad

- **El bloqueo es un advisory lock por servicio (`pg_advisory_xact_lock`), no `FOR UPDATE`.** El caso 3
  mostró que `FOR UPDATE` no bloquea nada cuando la fila todavía no existe: los dos primeros pedidos
  pedían ticket a la vez. Decidido al implementar; no cambia el alcance aprobado.
- **El engine se toma de la sesión recién al reservar**, no al construir el repositorio: dos tests de
  ensamblado arman las piezas con una sesión falsa y no deben tocar la base.
