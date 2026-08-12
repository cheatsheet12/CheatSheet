# Insumos — material de Etapa 5

Lo que hay acá **no se reescribe**. Es la entrada del flujo AI-DLC, no un producto de
trabajo suyo: se importa una vez, se consume siempre y se cita por `HU-ID`.

| Archivo | Contenido | Origen |
|---|---|---|
| `historias-de-usuario.md` | Catálogo completo: 12 épicas con 59 HUs (`HU-E<n>-<nn>`) y 7 historias de sistema (`HS-T<n>`), cada una con actor, acción del Bloque K, prioridad, complejidad, pantalla o disparador, precondiciones, reglas de negocio y criterios de aceptación | Etapa 5 — `TodoEnUno.docx`, importado verbatim |

Copia textual: ni un `HU-ID`, ni un código de pantalla (`PAN-…`), ni una regla de negocio
fue tocada al importar. Si una historia está mal, se corrige acá **y se dice**, nunca en
silencio dentro de un plan de unidad.

## Qué falta importar

- **Requisitos** (funcionales y no funcionales) de Etapa 5.
- **Prototipos** — las pantallas `PAN-…` que las HUs referencian.

Ambos siguen fuera del repositorio. Mientras no estén, un plan de unidad que necesite el
detalle de una pantalla tiene que pedirlo, no inventarlo.

## Numeración: dos ejes distintos

Las "Épicas 1…12" de `historias-de-usuario.md` son una **agrupación temática por bounded
context**, no un orden de construcción. El orden de construcción vive en
[`../roadmap.md`](../roadmap.md), que las re-corta y las reordena. Las dos numeraciones
conviven a propósito y la tabla de trazabilidad del roadmap las vincula.
