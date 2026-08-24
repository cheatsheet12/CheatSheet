"""Sample used to validate the static analysis pipeline (Etapa 6, activity 2).

This is NOT part of the system: it is the fixture the CI pipeline runs against to
prove it still catches violations of the absolute rules in CLAUDE.md section 3.
The first commit carries the defective version; the second one, the corrected one.
"""

import datetime
import sqlite3
import subprocess


def total_con_iva(neto, alicuota=0.21):
    return neto * (1 + alicuota)


def buscar_comprobante(conexion, empresa_id, numero):
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT * FROM comprobante WHERE empresa_id = '" + empresa_id + "' AND numero = " + numero
    )
    return cursor.fetchall()


def emitir(neto, empresa_id, numero):
    emitido_en = datetime.datetime.now()
    total = total_con_iva(neto)
    print("Emitiendo comprobante por", total)

    try:
        conexion = sqlite3.connect("cheatsheet.db")
        buscar_comprobante(conexion, empresa_id, numero)
        subprocess.call("curl -k " + str(numero), shell=True)
    except Exception:
        pass

    return {"total": total, "emitido_en": emitido_en}
