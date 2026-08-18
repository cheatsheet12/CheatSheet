# Prototipos y sistema de diseño

> Índice de [`prototipos/`](prototipos/), el material de maquetación de Etapa 5. Como con el DER,
> **los originales mandan** y este archivo solo los hace navegables.

## Qué hay, y qué gobierna cada cosa

| Archivo | Qué es | Autoridad |
|---|---|---|
| [`prototipos/maquetacion-pantallas.pdf`](prototipos/maquetacion-pantallas.pdf) | **La especificación escrita del sistema de diseño**: paleta con nombre de token y uso, tipografía, catálogo de componentes con sus estados y su comportamiento, y los principios de UX. 32 páginas | Normativa |
| [`prototipos/styles.css`](prototipos/styles.css) | **El sistema implementado**: 157 custom properties. Es lo que las ocho pantallas realmente usan | Normativa |
| [`prototipos/pantallas/*.html`](prototipos/pantallas/) | Las ocho pantallas prototipadas, en HTML funcional | Normativa |
| [`prototipos/render/*.png`](prototipos/render/) | Las mismas ocho, renderizadas. Útiles para comparar de un vistazo | Referencia |
| `prototipos/guia-visual*.html` | La guía visual. La variante `-oficial` es la misma información «(formato documento)», maquetada para imprimir — no es otra versión | Normativa |
| `prototipos/mapa-navegacion*.html` | Mapa de navegación: qué pantalla lleva a cuál, y los códigos `PAN-…` | Normativa |
| `prototipos/anotaciones-comportamiento*.html` | Comportamiento esperado de cada pantalla: estados, validaciones, mensajes | Normativa |
| `prototipos/estilo-doc.css` | Hoja de estilos de las variantes `-oficial`. Sin ella no renderizan | Auxiliar |

### Qué quedó deliberadamente afuera

El material original (`~/Downloads/CheatSheet/`) trae tres cosas más que **no** se importaron:

- `stories/*.txt` — son las mismas 66 historias que ya están en
  [`historias-de-usuario.md`](historias-de-usuario.md). Dos copias de un insumo es una copia que se
  desactualiza.
- `uploads/*.docx` — los documentos fuente de los que salió lo anterior.
- `screenshots/` — 48 capturas intermedias del proceso de diseño. Las ocho finales están en
  `render/`.

## Las ocho pantallas

| Prototipo | Códigos `PAN-…` | Épico |
|---|---|---|
| `pantallas/onboarding.html` | PAN-ONB-01, PAN-ONB-02, PAN-ONB-03 | **1** (ONB-03 es integraciones, épico 2) |
| `pantallas/ingesta.html` | PAN-ING-01, PAN-ING-02, PAN-ING-03 | 4 |
| `pantallas/cobros.html` | PAN-COB-01, PAN-COB-02, PAN-COB-03 | 6 |
| `pantallas/agente-whatsapp.html` | PAN-AGE-01, PAN-AGE-02, PAN-AGE-03 | 8 |
| `pantallas/reportes.html` | PAN-REP-01, PAN-REP-02 | 9 |
| `pantallas/reporte-libro-iva.html` | PAN-FAC-01 … PAN-FAC-05 | 5 |
| `pantallas/logs.html` | PAN-LOG-01, PAN-SOP-01 | 10 |
| `pantallas/dashboard.html` | (tablero de KPIs) | 9 |

**Solo `onboarding.html` pertenece al épico 1.** Las otras siete son insumo de épicos posteriores y
no se tocan todavía.

No hay prototipo de **PAN-USR-01 ni PAN-USR-02** (usuarios y preferencias personales), que son las
pantallas de la unidad `usuarios-y-preferencias`. Es el hueco P9 de abajo.

## Los tokens

La paleta, según la especificación (PDF §1.1). Los nombres son los del documento:

| Token | Hex | Uso |
|---|---|---|
| `color-primary` / sidebar-bg | `#1E1E2E` | Fondo del sidebar, títulos, texto de alto contraste |
| `color-mid` / sidebar-hover | `#3A3A5C` | Hover del sidebar, secciones destacadas |
| `color-accent` / cta-primary | `#00C48C` | CTA, éxito, badges «Conectado», progreso |
| `color-warning` / alert-amber | `#FDCB6E` | Advertencias, «Atención», «En generación», confianza Media |
| `color-bg` | `#F8F7FF` | Fondo del panel. El tinte violeta reduce fatiga visual |
| `color-success-light` | `#E8FAF5` | Fondo de cajas de éxito |
| `color-error` | `#CC0000` | Errores, «En mora», validación fallida |
| `color-surface` | `#FFFFFF` | Tarjetas, paneles, tablas, modales |
| `color-text-body` | `#555555` | Cuerpo de texto |
| `color-text-secondary` | `#888888` | Captions, placeholders, metadatos |

Tipografía: **DM Sans** para el panel (24/18/14/14/12 px), **JetBrains Mono** para CUIT, CAE,
números de comprobante y tokens.

Contrastes ya validados por el documento: CTA `#00C48C` sobre `#1E1E2E` es AAA; texto `#1E1E2E`
sobre `#F8F7FF` es AA+; **el ámbar `#FDCB6E` nunca va como color de texto sobre blanco**, solo como
fondo o borde.

## ⚠️ El PDF y `styles.css` no coinciden

Ocho valores difieren entre la especificación escrita y el CSS que las pantallas realmente usan.
No es una diferencia de matiz: la tipografía es otra.

| # | Concepto | PDF (especificación) | `styles.css` (implementado) |
|---|---|---|---|
| P1 | Tipografía del panel | **DM Sans** | Stack del sistema (`-apple-system, …`). DM Sans no aparece en ningún archivo |
| P2 | Color de error | `#CC0000` | `--err: #DC2B3A` |
| P3 | Fondo de éxito | `#E8FAF5` | `--ok-bg: #E4F8F1` |
| P4 | Texto de cuerpo | `#555555` (gris neutro) | `--ink-700: #3d3d52` (gris frío, derivado del primary) |
| P5 | Texto secundario | `#888888` | `--ink-500: #6b6b80` / `--ink-400: #8a8a9c` |
| P6 | Ancho del sidebar | 180 px | `--sidebar-w: 244px` |
| P7 | Alto de la topbar | 56 px | `--topbar-h: 68px` |
| P8 | Radio del botón | 8 px | `--radius: 14px` (existe `--radius-xs: 8px`) |

Además, `styles.css` tiene una escala de grises fríos (`--ink-900` … `--ink-300`) que el PDF no
documenta, y el PDF nombra tokens (`color-text-body`) que el CSS no define con ese nombre.

**Cuál gana es una decisión, no un detalle**, y está registrada en el plan de la unidad que
construye la primera pantalla.

## Huecos

| # | Hueco | Unidad afectada |
|---|---|---|
| P1–P8 | El PDF y `styles.css` discrepan (arriba) | la primera unidad que escriba una pantalla |
| P9 | No hay prototipo de PAN-USR-01 ni PAN-USR-02 | `usuarios-y-preferencias` |
| P10 | El prototipo de onboarding **sí** trae el alta con Google y el checkbox de términos. Lo que no encontré es el flujo de **re-aceptación** cuando cambia la versión (HU-E1-03 RN-03); hay que buscarlo en las anotaciones de comportamiento al construir la pantalla, y si no está, decidirlo | `identidad-y-onboarding` |
