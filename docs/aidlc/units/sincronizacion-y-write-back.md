# Unidad: sincronizacion-y-write-back

**HUs**: HU-E3-04, HU-E3-07   **Contexto dueño**: spreadsheet_sync   **Rama**: feature/spreadsheet_sync-sincronizacion-de-planillas

## Qué hace

Cierra el círculo del épico: detecta cuándo la estructura de una planilla cambió y **pausa**
la sincronización en lugar de ingerir mal, y escribe de vuelta en la hoja propia protegida
lo que se creó desde el panel o desde el agente.

## Lo que define la unidad: que el sistema no se coma su propia cola

Un write-back que escribiera en la hoja que también lee ingeriría su propia salida en el
barrido siguiente, para siempre. ADR-007 lo evita con **tres guardas**, y esta unidad los
implementa como tres cosas separadas a propósito:

1. **Sólo vínculos `LECTURA_Y_ESCRITURA`** (RN-01), que el agregado ya se niega a poner en
   algo que no sea Google Sheets.
2. **Sólo la hoja propia**, nunca la de la empresa (RN-02). **Este es el guarda
   estructural**: lo que escribimos cae en un lugar que nunca leemos, así que el bucle es
   imposible en lugar de improbable.
3. **Sólo registros con `origen` PANEL o AGENTE** (RN-03). Lo que vino de la planilla no
   vuelve a la planilla.

Tener los tres significa que un bug en cualquiera no produce una sincronización infinita.
Cada uno tiene su propio test, por eso mismo.

## Decisiones

**El filtro por `origen` vive en `master_data`, no acá.** El guard de arquitectura atajó la
primera versión, que importaba `FiltrosDeCliente` del dominio ajeno. `origen` es un concepto
de ese contexto: `spreadsheet_sync` pregunta «qué tengo que escribir de vuelta» y la
respuesta es una decisión sobre el catálogo.

**Pausar y no re-mapear solo.** La empresa renombró una columna; lo que pasa después es una
decisión que tiene que ver, porque la alternativa es cuarenta mil filas cayendo en los
campos equivocados en un horario que nadie está mirando. El mapeo vuelve a borrador **con
sus entradas**: rehacer cuarenta asignaciones por una columna renombrada es cómo una pausa
se convierte en un abandono.

**El puerto de escritura es angosto a propósito.** Escribe una hoja nombrada y nada más: no
tiene `borrar`, no tiene `reemplazar_hoja`, y la única hoja que este contexto le pasa es la
que él mismo creó. Un adaptador capaz de sobrescribir una hoja arbitraria está a un
argumento equivocado de borrar la lista de clientes de alguien.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un vínculo de solo lectura no se escribe **ni se consulta** (guarda 1) | unit | **OK** |
| 2 | Excel Online y un archivo nunca se escriben (HU-E3-07, 4.º criterio) | unit | **OK** |
| 3 | Se escribe en la hoja de CheatSheet y nunca en la de la empresa (guarda 2) | unit | **OK** |
| 4 | La hoja ya creada se reusa | unit | **OK** |
| 5 | Sin registros pendientes no se toca la planilla | unit | **OK** |
| 6 | La escritura queda auditada, con `usuario_id` nulo | unit | **OK** |
| 7 | El mismo encabezado no pausa nada | unit | **OK** |
| 8 | Una columna renombrada pausa con el texto exacto de RN-03 | unit | **OK** |
| 9 | Reordenar las columnas también pausa | unit | **OK** |
| 10 | Un vínculo pausado deja de ser candidato al barrido | unit | **OK** |
| 11 | La escritura simulada es rechazada en `production` | unit | **OK** |
| 12 | Las cinco entradas de Beat conviven, y el sync va en `incremental_sync` | unit | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | pendiente: lo pedis vos |

```
ruff format --check .   335 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 335 source files
guard_architecture      361 file(s) checked - architecture boundaries intact
pytest --cov            969 passed - 0 skipped - cobertura 94%  (umbral 80)
alembic current         0015 (head)
```

## Lo que queda sin terminar, dicho de frente

**La lectura incremental no lee todavía.** `sincronizar_empresa` hace la mitad del
write-back y **no vuelve a leer la hoja viva**. Lo que falta para eso es el token OAuth por
empresa: `escritura_de_planilla()` construye el adaptador con un token vacío, porque
resolver la credencial cifrada de cada empresa desde `integrations` (ADR-0003) es una pieza
que esta unidad no llegó a armar.

Se implementó primero la mitad con riesgo de bucle —los tres guardas— y no la mitad que
sólo lee, porque los guardas son los que conviene tener en producción antes de que algo
empiece a escribir por horario. **La consecuencia concreta:** los criterios «se modifica
una fila en la planilla y el sistema lo sincroniza» y «se agregan filas nuevas» de HU-E3-04
**no se cumplen todavía**. La detección de cambio de estructura sí está, y el write-back
también, pero el disparador que los usa contra una planilla real necesita esa credencial.

Es lo mismo que le pasó a ARCA, a WhatsApp y a MercadoPago en el épico 2: el código está y
falta la credencial. La diferencia es que acá parte de una historia queda incumplida, y por
eso se dice acá y en `TODO.md` en lugar de darla por cerrada.
