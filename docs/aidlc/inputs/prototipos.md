# Prototipos y sistema de diseño

> Índice de [`prototipos/`](prototipos/), el material de maquetación de Etapa 5. Como con el DER,
> **los originales mandan** y este archivo solo los hace navegables.

## Qué hay, y qué gobierna cada cosa

| Archivo | Qué es | Autoridad |
|---|---|---|
| [`prototipos/maquetacion-pantallas.pdf`](prototipos/maquetacion-pantallas.pdf) | **La especificación escrita del sistema de diseño**: paleta con nombre de token y uso, tipografía, catálogo de componentes con sus estados y su comportamiento, y los principios de UX. 32 páginas | Normativa |
| [`prototipos/styles.css`](prototipos/styles.css) | **El sistema implementado**: 157 custom properties. Es lo que las ocho pantallas realmente usan | Normativa |
| [`prototipos/chrome.js`](prototipos/chrome.js) | El sidebar y la topbar compartidos, montados por script. **Siete de las ocho pantallas lo cargan**: sin él renderizan sin navegación | Normativa |
| `prototipos/*.html` (las ocho pantallas) | Las ocho pantallas prototipadas, en HTML funcional | Normativa |
| [`prototipos/capturas/*.png`](prototipos/capturas/) | **Las 15 capturas entregadas**, a 1919 px. Cubren los 13 mockups: cada pestaña, cada drawer y cada scroll | Referencia |
| [`prototipos/render/*.png`](prototipos/render/) | Ocho renders a 1425 px, uno por archivo, sólo el estado por defecto. Más chicos y recortados que las capturas | Referencia |
| `prototipos/logo.html` · `logo-rediseno.html` · `imagotipo.html` | La identidad de marca: logo, su rediseño y el imagotipo con sus usos | Normativa |
| `prototipos/guia-visual*.html` | La guía visual. La variante `-oficial` es la misma información «(formato documento)», maquetada para imprimir — no es otra versión | Normativa |
| `prototipos/mapa-navegacion*.html` | Mapa de navegación: qué pantalla lleva a cuál, y los códigos `PAN-…` | Normativa |
| `prototipos/anotaciones-comportamiento*.html` | Comportamiento esperado de cada pantalla: estados, validaciones, mensajes | Normativa |
| `prototipos/estilo-doc.css` | Hoja de estilos de las variantes `-oficial`. Sin ella no renderizan | Auxiliar |

### Qué quedó deliberadamente afuera

El material original trae tres cosas más que **no** se importaron:

- `stories/*.txt` — el export de los `.docx` de trabajo. Son **una revisión anterior** de las
  historias: les faltan HU-E3-07 y HU-E7-06, y sus criterios de aceptación son más pobres que los del
  Documento Oficial V3. [`historias-de-usuario.md`](historias-de-usuario.md) se transcribe del
  documento oficial, no de acá.
- `uploads/*.docx` — los documentos fuente de los que salió lo anterior.
- `screenshots/` — 48 capturas intermedias del proceso de diseño (iteraciones del logo, del mapa,
  versiones v2/v3/v4 de pantallas). Las entregadas están en `capturas/`.

Sí se importó `uploads/pasted-1780129349373-0.png`, porque `logo-rediseno.html` la referencia y sin
ella la página no renderiza completa.

### Todo en una carpeta, a propósito

Las ocho pantallas están **junto a** `styles.css` y `chrome.js`, no en una subcarpeta. No es
desprolijidad: los HTML enlazan `styles.css`, `chrome.js` y entre sí con rutas relativas planas, tal
como se entregaron. Moverlos a `pantallas/` rompía las tres cosas a la vez — las pantallas perdían
estilos y navegación, y el mapa de navegación perdía sus ocho enlaces.

## Las ocho pantallas

Los códigos salen de la matriz de trazabilidad del documento oficial (§19.5) y del mapa de navegación.
La columna «épico» es la del [`roadmap.md`](../roadmap.md), no la numeración de épicas del documento.

| Prototipo | Códigos `PAN-…` | Vistas `CS-…` | Épico |
|---|---|---|---|
| `onboarding.html` | PAN-ONB-01, PAN-ONB-02, PAN-ONB-03 (agrupadas como PAN-CFG-INT en §19.5) | CS-01/02/03 | **1** (ONB-03 es integraciones, épico 2) |
| `dashboard.html` | PAN-DSH-01 | CS-04 | 2 · 10 (HU-E2-05 y HU-E12-01) |
| `ingesta.html` | PAN-ING-01, PAN-ING-02, PAN-ING-03 (drawer de detalle) | CS-05/06 | 4 |
| `cobros.html` | PAN-COB-01, PAN-COB-02, PAN-COB-03 | CS-07/08 | 6 |
| `agente-whatsapp.html` | PAN-WA-01 (conversaciones), PAN-WA-02 (configuración y FAQ) | CS-09/10 | 8 |
| `reportes.html` | PAN-REP-01, PAN-REP-02 | CS-11/12 | 9 |
| `reporte-libro-iva.html` | PAN-REP-01 — salida fiscal (`REP-IVA` en el mapa de navegación) | CS-13 | 5 · 9 |
| `logs.html` | PAN-LOG-01, PAN-LOG-02 (drawer de detalle) | CS-14/15 | 10 |

**`PAN-AGE-…` es la Agenda, no el agente de WhatsApp.** El mapa de navegación las separa:
`PAN-AGE-01/02/03` son vista de agenda, detalle de turno y recursos; el agente es `PAN-WA-01/02`.
La Agenda **no tiene prototipo** — es el hueco P11.

**Solo `onboarding.html` pertenece al épico 1.** Las otras siete son insumo de épicos posteriores y
no se tocan todavía.

## Las capturas

`capturas/` tiene las 15 entregadas, nombradas por el `PAN-…` que muestran. Cubren estados que los
renders no: la pestaña de configuración del agente, los drawers de cobros y de bitácora, el mapeo de
IA y las dos mitades de la configuración automática de reportes.

| Captura | Muestra | Prototipo |
|---|---|---|
| `01-dashboard-PAN-DSH-01.png` | Dashboard principal | `dashboard.html` |
| `02-onboarding-PAN-ONB-01-02-03.png` | Los tres pasos del onboarding, lado a lado | `onboarding.html` |
| `03-ingesta-carga-PAN-ING-01.png` | Carga de planilla | `ingesta.html` |
| `04-ingesta-mapeo-ia-PAN-ING-02.png` | Revisión del mapeo propuesto por IA, con niveles de confianza | `ingesta.html` |
| `05-cobros-listado-PAN-COB-01.png` | Listado de cobros | `cobros.html` |
| `06-cobros-detalle-PAN-COB-02.png` | Detalle con panel lateral: link de pago y cadena de recordatorios | `cobros.html` |
| `07-agente-conversaciones-PAN-WA-01.png` | Conversaciones del agente | `agente-whatsapp.html` |
| `08-agente-configuracion-PAN-WA-02.png` | Horarios, FAQ, mensaje de bienvenida y número conectado | `agente-whatsapp.html` |
| `09-reportes-dashboard-PAN-REP-01.png` | Dashboard de reportes | `reportes.html` |
| `10-reportes-dashboard-scroll-PAN-REP-01.png` | El mismo, más abajo: reportes y paquetes contables | `reportes.html` |
| `11-libro-iva-ventas-PAN-REP-01-fiscal.png` | Libro IVA Ventas (salida fiscal) | `reporte-libro-iva.html` |
| `12-reportes-config-automatica-PAN-REP-02.png` | Configuración automática, bloque 01 | `reportes.html` |
| `13-reportes-config-scroll-PAN-REP-02.png` | Bloques 02 y 03: contenido del paquete y acceso del contador | `reportes.html` |
| `14-bitacora-listado-PAN-LOG-01.png` | Bitácora de operaciones | `logs.html` |
| `15-bitacora-detalle-PAN-LOG-02.png` | Detalle de una operación fiscal con CAE y respuesta de ARCA | `logs.html` |

Dos capturas (`02` y `13`) traen encima la banda «claude.ai — Para salir de la pantalla completa» del
navegador con que se tomaron. Es un artefacto de captura, no parte del diseño.

## Cobertura

Las 13 pantallas maquetadas (15 vistas `CS-…`) cubren 30 historias de usuario y una de sistema.
Del resto del mapa de navegación **no hay prototipo**: `PAN-USR-01/02` (usuarios y preferencias),
`PAN-DM-01/02/03` (datos maestros), `PAN-FAC-01 … PAN-FAC-05` (facturación), `PAN-AGE-01/02/03`
(agenda), `PAN-CFG-RN`, `PAN-CFG-NOT` y `PAN-SOP-01`. Son los huecos P9 y P11 de abajo.

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
| P11 | No hay prototipo de las pantallas de facturación (`PAN-FAC-…`), datos maestros (`PAN-DM-…`), agenda (`PAN-AGE-…`), reglas de negocio, plantillas ni soporte. El mapa de navegación y las anotaciones de comportamiento son lo único que las describe | los épicos 3, 5, 7 y 10 |
| P10 | El prototipo de onboarding **sí** trae el alta con Google y el checkbox de términos. Lo que no encontré es el flujo de **re-aceptación** cuando cambia la versión (HU-E1-03 RN-03); hay que buscarlo en las anotaciones de comportamiento al construir la pantalla, y si no está, decidirlo | `identidad-y-onboarding` |
