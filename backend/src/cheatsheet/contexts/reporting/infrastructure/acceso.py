"""El enlace del contador: cómo se emite y cómo se resume.

Misma construcción que el token de invitación del épico 1: 256 bits del CSPRNG del sistema
operativo vía `secrets`, y SHA-256 para el digesto que se guarda.

**No reusa `hashear_token_opaco` de `identity`**, y no es un descuido: esa función vive en el
`infrastructure/` de otro contexto y la regla R3 prohíbe importarla. La alternativa era
promoverla a `platform/`, que ataría dos credenciales que **nunca se comparan entre sí** —un
refresh token y un enlace de contador no se buscan en la misma tabla ni se validan en el mismo
lugar— para ahorrar tres líneas. Lo que sí importa es que las dos guarden el hash y no el
valor, y eso es una regla, no una función compartida.

**SHA-256 y no Argon2**, por lo mismo que el épico 1 documenta: el costo de Argon2 existe para
frenar la adivinación de una contraseña elegida por una persona. Acá no hay nada que adivinar,
y pagar 19 MiB por verificación sólo haría fácil de saturar la única ruta pública del épico.
"""

from __future__ import annotations

import hashlib
import secrets

#: 32 bytes: los mismos que el refresh token y el de invitación.
BYTES_DEL_ENLACE = 32


class EnlaceContableAleatorio:
    """Implementa `PortTokenDeAcceso`."""

    def emitir(self) -> str:
        return secrets.token_urlsafe(BYTES_DEL_ENLACE)

    def hashear(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = ["BYTES_DEL_ENLACE", "EnlaceContableAleatorio"]
