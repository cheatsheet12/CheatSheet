# tests — Casos de prueba por módulo

Pruebas automáticas organizadas por módulo. El pipeline de CI ejecuta este conjunto
ante cada Pull Request dirigido a `develop` o `main`.

- **Framework:** pytest
- **Convención:** un subdirectorio o archivo por módulo (`test_intake.py`, `test_billing.py`, ...)

Ejecución local:

```bash
pytest
```
