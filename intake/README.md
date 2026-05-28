# intake — Módulo de ingesta de datos

Responsable de la incorporación de datos al sistema desde múltiples fuentes
(Excel, Google Sheets) y del mapeo semántico asistido por IA.

- **Stack:** Python
- **Entradas externas:** archivos Excel/CSV, Google Sheets API, modelos de IA
- **Variables de entorno relevantes:** `AI_API_KEY`, `AI_MODEL`

Toda integración externa debe agregar sus variables al `.env.example` raíz
(responsabilidad del Analista de Integraciones).
