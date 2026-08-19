"""Anti-Corruption Layer for ARCA's WSAA (HU-E2-01, ADR-008 and ADR-0004).

Split into four files on purpose, because they fail in different ways and are tested by
different means:

- `firma.py` — pure cryptography. Parses the credential, builds the login ticket request
  and signs it. No socket, no clock skew, no provider quirks
- `wsaa.py` — the SOAP call, its timeout and its bounded retry
- `mapeo.py` — ARCA's fault codes translated into this system's vocabulary
- `conector.py` / `verificador.py` / `emisor.py` — the three ports, each a thin composition

Nothing outside this package knows the words `loginTicketRequest`, `sign` or
`coe.alreadyAuthenticated`.
"""
