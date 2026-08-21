"""Anti-Corruption Layer for Meta's WhatsApp Cloud API (HU-E2-03, ADR-008).

One package per provider, never a generic one. Nothing outside this package knows the
words `name_status`, `verified_name` or `quality_rating`: `mapeo.py` translates them into
`EstadoDeConexion` and a plain detail string, and that is all the rest of the system sees.
"""
