---
entregable: pruebas
parte: 00-introduccion
responsable: Emanuel Gomez
estado: borrador
hu: []
fuentes:
  - docs/aidlc/etapa-6/reglas.md
  - docs/aidlc/etapa-6/reparto.md
  - docs/aidlc/etapa-6/entregables/pruebas/
  - docs/staging-deployment.md
observaciones: >
  Borrador del integrador, armado el 13/10/2026 con las partes que existían ese día. Faltan PRU-01
  (Vincenzo) y PRU-05 (Luciano). PRU-02 y PRU-06 se
  corrigieron el 13/10/2026 al valor de Estado que admite reglas.md §5.1, y PRU-02 quedó con la
  fecha de su ejecución. La tabla de resultados se completa cuando todas
  las partes estén en estado listo.
---

# Pruebas del sistema

## Introducción

Este documento reúne las nueve pruebas documentadas de CheatSheet: qué verifica cada una, cómo se
ejecutó y qué resultado dio. Las pruebas cubren las tres clases que exige la planificación:
**funcionales** (una funcionalidad hace lo que su historia de usuario promete), **de integración**
(dos o más módulos o un servicio externo trabajan juntos de punta a punta) y **de seguridad y
control de acceso** (un rol no puede hacer lo que no le corresponde, ni desde el panel ni llamando
a la API directamente).

Cada prueba se ejecutó a mano en **staging**, el entorno de pruebas compartido, recorriendo los
criterios de aceptación de las historias que cita. Cuando una prueba falló, el defecto se registró
como issue, se corrigió y la prueba se volvió a ejecutar.

## Alcance

| Prueba | Qué verifica | Tipo | Historias | Responsable |
|---|---|---|---|---|
| PRU-01 | Emitir un comprobante y obtener su CAE | Funcional | HU-E5-03 | Vincenzo Dallape |
| PRU-02 | Generar un link de cobro para un cliente | Funcional | HU-E6-03 | Paula Ferreira |
| PRU-03 | Procesar la carga inicial de una planilla | Funcional | HU-E3-03 | Juan Caballero |
| PRU-04 | Crear un turno manualmente desde el panel | Funcional | HU-E7-06 | Emanuel Gomez |
| PRU-05 | Una reserva hecha por WhatsApp aparece en la agenda y en la bitácora | Integración | HU-E8-01, HU-E7-01, HU-E12-01 | Luciano Oro |
| PRU-06 | El webhook de MercadoPago aprueba el cobro, que aparece en el listado y en los indicadores del tablero | Integración | HS-T1, HU-E6-01, HU-E10-01 | Paula Ferreira |
| PRU-07 | Solo Lectura no puede emitir un comprobante, ni en el panel ni llamando a la API | Seguridad y control de acceso | HU-E1-05, HU-E5-03 | Cristian Suarez |
| PRU-08 | Operador no puede gestionar usuarios ni reembolsar un cobro | Seguridad y control de acceso | HU-E1-04, HU-E6-05 | Cristian Suarez |
| PRU-09 | Solo Lectura no puede crear clientes, y un usuario de otra empresa no ve los clientes de la primera | Seguridad y control de acceso | HU-E4-01 | Juan Caballero |

Las pruebas de seguridad verifican **las dos capas**: que el panel no ofrezca la acción y que la
API la rechace con un código 403 aunque se la llame directamente, sin pasar por la pantalla.

## Entorno de prueba

Todas las pruebas se ejecutaron en **staging**, que se actualiza solo con cada cambio aprobado en la
rama `develop`: aplica las migraciones de la base de datos y verifica el aislamiento entre empresas
antes de publicar cada versión. Ninguna prueba se ejecutó en un entorno local ni en producción.

| Componente | Cómo está en staging |
|---|---|
| Panel y API | Desplegados en Render, con la versión de `develop` vigente el día de cada prueba |
| Base de datos | PostgreSQL con aislamiento por empresa (seguridad a nivel de fila) |
| ARCA | Homologación: los comprobantes obtienen un CAE de prueba, sin validez fiscal |
| MercadoPago | Cuentas de prueba: los pagos y sus webhooks no mueven dinero real |
| WhatsApp | Sin conexión validada en staging: los avisos al cliente no se pueden verificar en el teléfono |
| Correo | En modo consola: las invitaciones no salen por email y el enlace queda en el registro del servidor |

## Datos de prueba

Se usaron exclusivamente los datos ficticios definidos para la Etapa 6; ninguna prueba contiene datos
de una persona o empresa real.

- **Empresa:** Estudio Ejemplo SRL, Responsable Inscripto. Como staging es compartido y no admite dos
  empresas con el mismo CUIT, cada integrante registró la suya con su propio CUIT ficticio
  (`30-00000001-5` a `30-00000006-6`). La segunda empresa de las pruebas de aislamiento es Taller
  Muestra SA.
- **Usuarios:** un Administrador, un Operador y un Solo Lectura por integrante, con correos del
  dominio reservado `estudio-ejemplo.test`, que nunca recibe correo.
- **Clientes:** Ana Prueba, Bruno Ficticio y Carla Demo.
- **Servicios:** Consulta general ($ 15.000,00, IVA 21 %) y Sesión de seguimiento ($ 9.500,00, IVA 21 %).

## Criterio de resultado

Cada prueba termina en uno de tres estados:

| Estado | Significado |
|---|---|
| Aprobada | El resultado obtenido coincide con el esperado en la primera ejecución |
| Fallida | El resultado no coincide; se abrió un issue y la corrección está pendiente |
| Re-ejecutada | Falló, se corrigió el defecto y la segunda ejecución coincidió con lo esperado; el resultado obtenido cuenta las dos corridas |

## Resumen de resultados

| Prueba | Fecha | Estado | Defectos encontrados |
|---|---|---|---|
| PRU-01 | — | Pendiente de entrega | — |
| PRU-02 | 05/10/2026 | Aprobada | El detalle del cobro no ofrece regenerar el link (bug de frontend) |
| PRU-03 | 12/10/2026 | Aprobada | — |
| PRU-04 | 12/10/2026 | Aprobada | — |
| PRU-05 | — | Pendiente de entrega | — |
| PRU-06 | 12/10/2026 | Aprobada | — |
| PRU-07 | 11/10/2026 | Re-ejecutada | La API rechazaba con 422 en lugar de 403; corregido y verificado en la segunda corrida |
| PRU-08 | 12/10/2026 | Aprobada | — |
| PRU-09 | 12/10/2026 | Aprobada | — |

Además de las nueve pruebas documentadas, cada integrante recorrió en staging todos los criterios de
aceptación de las historias de su módulo con los tres roles. Los defectos que encontraron se
registraron como issues con su severidad (crítico, mayor o menor) y se corrigen por el flujo de
desarrollo del repositorio, con una prueba automática que reproduce cada defecto antes de su
corrección.
