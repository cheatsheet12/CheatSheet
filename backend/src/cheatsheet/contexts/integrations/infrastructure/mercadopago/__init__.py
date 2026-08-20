"""The MercadoPago adapter (HU-E2-02).

Split the same way the WhatsApp one is: `cliente.py` does HTTP and nothing else,
`mapeo.py` is the whole Anti-Corruption Layer as pure functions, and the rest are thin
implementations of one port each.
"""
