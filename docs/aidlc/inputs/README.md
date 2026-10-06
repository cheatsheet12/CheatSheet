# Insumos — material de Etapa 5

Lo que hay acá **no se reescribe**. Es la entrada del flujo AI-DLC, no un producto de
trabajo suyo: se importa una vez, se consume siempre y se cita por `HU-ID`.

| Archivo | Contenido | Origen |
|---|---|---|
| `historias-de-usuario.md` | Catálogo completo: 12 épicas con 61 HUs (`HU-E<n>-<nn>`) y 7 historias de sistema (`HS-T<n>`), cada una con actor, acción del Bloque K, prioridad, complejidad, pantalla o disparador, precondiciones, reglas de negocio y criterios de aceptación | Etapa 5 — **Documento Oficial V3**, §17 Modelo funcional, transcrito verbatim |
| `DER.pdf` | Diagrama entidad-relación: 34 tablas, 21 enums, con tipos, nulabilidad y claves. **Fuente de verdad del modelo físico** | Etapa 5 — export de dbdiagram.io |
| `der-por-contexto.jpg` | El mismo modelo **agrupado por bounded context** (BC1…BC12), marcando cuáles son Core. Vista lógica: omite `created_at` / `updated_at` | Etapa 5 |
| `der.md` | Transcripción de los dos, organizada por contexto | Derivado de los anteriores |
| `prototipos/` | Maquetación de Etapa 5: la especificación escrita del sistema de diseño (PDF, 32 páginas), el CSS y el `chrome.js` compartidos, las ocho pantallas en HTML funcional, las 15 capturas entregadas, la identidad de marca (logo e imagotipo), la guía visual, el mapa de navegación y las anotaciones de comportamiento | Etapa 5 |
| `prototipos.md` | Índice de lo anterior: qué gobierna cada archivo, qué `PAN-…` cubre cada pantalla, la tabla de tokens y los huecos | Derivado |

Copia textual: ni un `HU-ID`, ni un código de pantalla (`PAN-…`), ni una regla de negocio
fue tocada al importar. Si una historia está mal, se corrige acá **y se dice**, nunca en
silencio dentro de un plan de unidad.

### Por qué el DER está tres veces

Cada archivo aporta algo que los otros no tienen:

- **`DER.pdf`** es el más completo — tipos, `NOT NULL`, claves, únicos, `created_at`/`updated_at`.
- **`der-por-contexto.jpg`** es el único que dice **a qué bounded context pertenece cada tabla**,
  que es lo que decide en qué carpeta del backend vive cada modelo.
- **`der.md`** existe porque los otros dos son ciegos como insumo de trabajo: el export de
  dbdiagram.io **convierte el texto en trazos vectoriales**, así que el PDF se ve pero no se puede
  grepear, ni citar por línea, ni comparar en un diff; el JPG, menos todavía.

**Ante cualquier diferencia, valen los diagramas** y la transcripción se corrige. Los dos
diagramas coinciden atributo por atributo; donde uno tiene más detalle que el otro, se toma el
más específico.

## Cómo se usa el DER

Es tan normativo como las historias. Ninguna migración inventa una tabla, una columna o un tipo
que el DER no tenga: si hace falta algo que no está, eso es un **hueco del DER** y se resuelve
en el Gate 1 de la unidad que lo necesita, declarándolo — nunca agregando la columna en silencio.
Los huecos ya detectados están al final de [`der.md`](der.md).

## Qué falta importar

- **Requisitos** (funcionales y no funcionales) de Etapa 5.

Siguen fuera del repositorio. Mientras no estén, un plan de unidad que los necesite tiene
que pedirlos, no inventarlos.

## Numeración: dos ejes distintos

Las "Épicas 1…12" de `historias-de-usuario.md` son una **agrupación temática por bounded
context**, no un orden de construcción. El orden de construcción vive en
[`../roadmap.md`](../roadmap.md), que las re-corta y las reordena. Las dos numeraciones
conviven a propósito y la tabla de trazabilidad del roadmap las vincula.
