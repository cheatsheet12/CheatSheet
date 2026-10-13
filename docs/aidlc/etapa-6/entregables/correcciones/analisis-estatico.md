---
entregable: correcciones
parte: analisis-estatico
responsable: Vincenzo Dallape
estado: borrador
hu: []
fuentes:
  - Analisis_Estatico_CheatSheet.docx (Drive)
  - docs/aidlc/etapa-6/reparto.md
  - pyproject.toml
  - docs/analisis-estatico/ejemplo_emision.py (commits ec068e0 y 8d5452c, rama feature/infra-validacion-analisis-estatico)
  - docs/adr/0014-arca-web-service-delegation.md
observaciones: >
  Las cifras de la verificación del analizador se volvieron a medir el 13/10/2026 corriendo ruff
  0.14.2 y mypy 1.18.2, con la configuración de pyproject.toml, sobre el archivo de prueba del
  commit ec068e0: ruff informa 17 hallazgos y mypy 5, es decir 22, repartidos en diez reglas
  distintas. El «24» del documento no surge de ninguna corrida y las «10 violaciones» son reglas,
  no hallazgos. La sección 4 que falta se reconstruye con esas corridas y con la prueba del
  float donde se espera un Decimal, que también se volvió a ejecutar. La corrección del punto
  4.2 de la sección 6 refleja un cambio posterior al documento (ADR-0014): se incluye porque el
  documento lo afirma como estado actual.
---

## Correcciones a «Análisis Estático del Código»

| Sección | Dice | Debe decir | Fuente |
|---|---|---|---|
| Encabezado de página | «CheatSheet · Etapa 5 — Diseño del Sistema» | «CheatSheet · Etapa 6 — Desarrollo e Implementación» | Portada del mismo documento: «Etapa 6 — Desarrollo e Implementación · Actividad 2» |
| §1, párrafo inicial | «la respuesta son dos herramientas por lenguaje» | «la respuesta son dos herramientas para Python (ruff y mypy) y una para TypeScript (ESLint)» | Tabla de la §1 del mismo documento |
| Numeración de secciones | Las secciones saltan de la 3 a la 5; la §1 cita «(§4.3)» y la §5 cita «las 10 violaciones» sin que exista la sección que las describe | Agregar la sección «4. Verificación del analizador» entre la 3 y la 5, con los apartados 4.1, 4.2 y 4.3 que se detallan en las filas siguientes. Con eso la cita «(§4.3)» de la §1 queda correcta | `pyproject.toml`; commits `ec068e0` y `8d5452c` |
| §4.1 (nueva), Archivo de prueba | No existe | «Para comprobar que las herramientas detectan lo que deben, se escribió un archivo de prueba, `docs/analisis-estatico/ejemplo_emision.py`, que no forma parte del sistema y viola a propósito las reglas absolutas de CLAUDE.md §3: arma una consulta SQL por concatenación, ejecuta un comando con `shell=True`, captura cualquier excepción y la descarta, registra la fecha de un comprobante sin zona horaria, usa `print()` en lugar del registro estructurado, no anota ningún tipo y calcula el IVA con `float`.» | `git show ec068e0` |
| §4.2 (nueva), Hallazgos | No existe | Tabla con las diez reglas: S608 (SQL por concatenación) · S602 (`shell=True`) · BLE001 y S110 (excepción genérica descartada) · DTZ005 (fecha sin zona horaria) · T201 (`print`) · ANN001 y ANN201 (falta de anotaciones), las ocho de ruff; `no-untyped-def` y `no-untyped-call`, las dos de mypy. Total: **22 hallazgos, 17 de ruff y 5 de mypy**. El commit `8d5452c` corrige las diez reglas y el pipeline queda en verde | Corrida de ruff 0.14.2 y mypy 1.18.2 sobre el commit `ec068e0`, 13/10/2026 |
| §4.3 (nueva), Dinero en float | No existe | «ruff no detecta un `float` usado como dinero. Con la función anotada (`neto: Decimal`, `alicuota: Decimal`), pasarle `1500.50` hace que mypy informe “Argument 1 to "total_con_iva" has incompatible type "float"; expected "Decimal"”, mientras ruff responde “All checks passed!”. Por eso la regla “nunca float para dinero” depende de mypy y de que el código esté anotado.» | Corrida de verificación del 13/10/2026 con la misma configuración |
| §5, tabla de commits, fila `ec068e0` | «El archivo con las 10 violaciones» | «El archivo con diez reglas violadas: 22 hallazgos, 17 de ruff y 5 de mypy (§4.2)» | §4.2 |
| §5, tabla de commits, fila `8d5452c` | «El mismo archivo, con las 10 correcciones» | «El mismo archivo, con las diez reglas corregidas» | Mensaje del commit `8d5452c` |
| §7, segunda conclusión | «La verificación del analizador dio 24 errores y bajó a 0. Sobre un archivo de prueba que viola las reglas absolutas del proyecto, ruff reportó 17 errores y mypy 5.» | «La verificación del analizador dio 22 hallazgos y bajó a 0. Sobre un archivo de prueba que viola diez reglas del proyecto, ruff reportó 17 hallazgos y mypy 5 (§4.2).» | §4.2 |
| §6, tabla, fila 4.2 y apartado «Las variables de AFIP se rediseñaron» | «cada empresa tiene su propio certificado de ARCA y su propio token de MercadoPago» · «El certificado se guarda cifrado en configuracion_de_integracion, no en disco» | «cada empresa tiene su propio token de MercadoPago, que se guarda cifrado en configuracion_de_integracion. Para ARCA, desde ADR-0014 la plataforma usa un único certificado propio, leído de la variable ARCA_CREDENCIAL_PLATAFORMA, y cada empresa delega en la CUIT de CheatSheet el servicio de Facturación Electrónica: ninguna empresa carga un certificado» | `docs/adr/0014-arca-web-service-delegation.md`; `backend/src/cheatsheet/platform/settings.py` |
