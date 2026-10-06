# Unidad: parametros-fiscales

**HUs**: HS-T4   **Contexto dueño**: reference_data   **Rama**: feature/billing-facturacion-electronica

## Qué hace

Trae de ARCA los catálogos fiscales —tipos de comprobante, alícuotas, condiciones de IVA,
tipos de documento, monedas y unidades de medida— y los guarda **versionados por vigencia**:
un valor nuevo no pisa al anterior, y la facturación usa el que regía el día de emisión y no
el de hoy. Sin pantalla.

Va primera del épico por la misma razón por la que `cimientos-y-bitacora` abrió el épico 1 y
`dlq-y-tareas-asincronas` el 4: **es contra lo que la emisión valida**, y una emisión que
valida contra una tabla vacía no valida.

## Diseño

- **Dominio**: agregado `ParametroFiscal`, con `TipoCatalogoFiscal` cerrado en los seis
  valores del DER. El invariante que vive acá: **los rangos de vigencia de un mismo
  `(tipo, codigo)` no se solapan**. Dos filas vigentes a la vez para la misma alícuota
  significa que la emisión elige una de las dos según el orden en que la base las devuelva.
- **Aplicación**: `SincronizarParametrosFiscales` (el barrido) y `ParametroVigenteA` (la
  consulta que hace `billing`, por fecha y no por «hoy»).
- **Puertos y adaptadores**: `PortRepositorioParametros` y `PortCatalogosFiscales` —el ACL
  contra WSFEv1, adaptador real y simulado según ADR-0008—. El ticket lo pide a
  `integrations` por `ObtenerTicketDeAcceso`, que ya existe y publica `TicketVigente`.
- **Otros contextos**: `integrations` es OHS (ADR-0003) y se llega por servicio de
  aplicación. `billing` va a consumir esta unidad, no al revés.
- **Frontend**: **No aplica.** Ninguna historia pide ver los parámetros.

## Infraestructura

- **Migraciones**: `0016_parametro_fiscal`. La tabla del DER, **sin `empresa_id`**: es el
  catálogo de ARCA y es el mismo para todas las empresas. Eso la hace la **tercera tabla del
  sistema sin RLS**, junto con `empresa` y las de Alembic — y por eso el `GRANT` de la
  aplicación es `SELECT` únicamente: quien escribe es la migración y el barrido, que corre
  con el rol dueño.
- **Trabajo asíncrono**: entrada de Beat `sincronizar-parametros-fiscales`, en la cola
  `integrations_sync`. **Es el barrido menos frecuente del sistema**: los catálogos de ARCA
  se mueven una vez cada varios meses, así que corre a diario y no cada media hora.
- **Configuración**: `ARCA_WSFE_URL_HOMOLOGACION`, `ARCA_WSFE_URL_PRODUCCION` y
  `PARAMETROS_FISCALES_HORAS` en `backend/.env.example`.
- **Integraciones externas**: WSFEv1, métodos `FEParamGet*`, con timeout, tres reintentos con
  backoff y manejo de falla (ADR-0008 y `CLAUDE.md` §5).

## Decisiones

**Fallar conserva lo anterior** (RN-04). Una sincronización que no puede hablar con ARCA
**no borra nada y no marca nada como vencido**: deja el último catálogo vigente y registra el
error. Lo contrario —vaciar y reintentar— dejaría a la facturación sin contra qué validar
durante la ventana de la falla, que es exactamente cuando alguien va a querer emitir.

**Un parámetro nuevo cierra al anterior, no lo reemplaza** (RN-02). Cuando ARCA devuelve un
valor distinto para un `(tipo, codigo)` que ya teníamos, la fila vieja recibe `fecha_hasta`
y se inserta una nueva con `fecha_desde`. El histórico es la razón de ser de la tabla: un
comprobante emitido en marzo se explica con el parámetro de marzo, y si lo pisáramos no
habría forma de reconstruir por qué decía lo que decía.

**La consulta es por fecha, siempre** (RN-03). `ParametroVigenteA(fecha)` y no
`ParametroVigente()`. Un default a «hoy» funciona el 99 % de las veces y falla justo cuando
importa: al reimprimir, al anular con una nota de crédito meses después, o al armar el Libro
IVA del épico 9.

## Riesgos que obligan a tests

- [ ] Toca dinero — indirectamente: las alícuotas que esta tabla guarda son las que después
      multiplican importes. Por eso el `valor` se guarda como texto y lo convierte a
      `Decimal` quien lo usa, nunca por un `float` intermedio
- [x] **Toca comprobantes fiscales / CAE** — es el catálogo contra el que se validan
- [ ] Consume un webhook — no
- [ ] Agrega datos con `empresa_id` — **no**, y es lo que hay que probar: la tabla no lo
      tiene, así que el test es que **todas las empresas ven lo mismo**
- [ ] Usa salida de un LLM — no
- [ ] Datos personales o fiscales — no: son códigos públicos de ARCA

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/reference_data/domain/parametro.py`
- [ ] `backend/src/cheatsheet/contexts/reference_data/application/parametros.py` + `ports.py`
- [ ] `backend/src/cheatsheet/contexts/reference_data/infrastructure/` — modelo, repositorio, ACL de WSFEv1
- [ ] `backend/migrations/versions/0016_parametro_fiscal.py`
- [ ] `backend/src/cheatsheet/workers/beat.py` y `tasks_reference_data.py`
- [ ] `backend/.env.example`
- [ ] `backend/tests/contexts/reference_data/…`

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un parametro nuevo se guarda con su vigencia (RN-01) | unit | **OK** |
| 2 | Un valor que cambio cierra al anterior y no lo pisa (RN-02) | unit | **OK** |
| 3 | La consulta devuelve el vigente **a una fecha dada**, no el de hoy (RN-03) | unit | **OK** |
| 4 | Una sincronizacion fallida conserva el ultimo vigente (RN-04) | unit | **OK** |
| 5 | Una respuesta vacia tampoco borra nada | unit | **OK** |
| 6 | Un valor identico al vigente no crea una fila nueva | unit | **OK** |
| 7 | La sincronizacion queda auditada, con `usuario_id` nulo | unit | **OK** |
| 8 | Pedir un parametro inexistente falla en vez de devolver `None` | unit | **OK** |
| 9 | El simulado trae los codigos **reales** de ARCA | unit | **OK** |
| 10 | Todas las empresas ven el mismo catalogo (la tabla no tiene `empresa_id`) | integracion | **OK** |
| 11 | Tambien se lee sin empresa declarada | integracion | **OK** |
| 12 | El rol de la aplicacion no puede escribir | integracion | **OK** |
| 13 | Dos vigencias abiertas del mismo parametro son rechazadas | integracion | **OK** |
| 14 | El historico cerrado convive sin limite | integracion | **OK** |
| 15 | Un tipo fuera del catalogo es rechazado por el CHECK | integracion | **OK** |
| 16 | Es la entrada de Beat mas espaciada de todas | unit | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   352 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 352 source files
guard_architecture      371 file(s) checked - architecture boundaries intact
pytest --cov            985 passed - 0 skipped - cobertura 94%  (umbral 80)
alembic current         0016 (head)
```

## Lo que aparecio al implementar y el plan no anticipaba

**El transporte SOAP tuvo que salir de `integrations`.** El epico 2 lo habia escrito en
`integrations/infrastructure/arca/soap.py`, y la regla R3 impide que `reference_data` lo
importe. Quedaban dos opciones: duplicarlo -- incluido el guarda contra expansion de
entidades -- o promoverlo. **El propio docstring del modulo ya argumentaba contra
duplicarlo**: «the piece worth copying least is the entity-expansion guard: a defence that
exists in one of two parsers is a defence that does not exist».

Se movio a `platform/soap.py`, donde `CLAUDE.md` seccion 2 pone la infraestructura que
todas las capas comparten, y `integrations` quedo como un envoltorio delgado que traduce a
su propio vocabulario de errores. **Su superficie publica no cambio**, asi que `wsaa.py` y
`padron.py` no se tocaron, y los 969 tests del epico 4 siguieron pasando sin modificar uno.

Lo que se quedo en `integrations` es lo que de verdad es suyo: **que significa una falla**.
`soapenv:Server` es un hipo transitorio de WSAA y la forma normal en que el padron dice «no
existe persona con ese Id» -- el mismo codigo, sentidos opuestos. Eso no puede vivir en
`platform/`.

**Es un refactor de otro contexto en el medio de esta unidad**, y no fue oportunismo: sin el
no habia forma de implementar HS-T4 sin triplicar un parser con implicancias de seguridad.

## Lo que esta unidad deja abierto

**El barrido corre para una empresa y guarda para todas**, porque el catalogo es de ARCA
pero *preguntar* necesita un ticket, y un ticket necesita el certificado de alguien. La
consecuencia, dicha de frente: **si ninguna empresa tiene ARCA conectado, el catalogo nunca
se sincroniza**. Es correcto -- sin nadie que pueda facturar no hay nada contra que validar
-- pero significa que un `parametro_fiscal` vacio es sintoma de un certificado que falta y
no de una tarea rota.

**`catalogos_fiscales()` se construye con un mapa de credenciales vacio.** Resolver el
ticket de cada empresa desde `integrations` es una pieza que `emision-de-comprobantes`
tambien necesita, y se arma una sola vez alli en lugar de dos veces.
