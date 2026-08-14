/**
 * PAN-ONB-02 — the company's fiscal data (HU-E1-02).
 *
 * **Two deliberate differences from the prototype**, both traceable to decisions already
 * recorded, and neither invented here:
 *
 * 1. **No autocomplete from ARCA.** The annotations say «Valida el CUIT contra ARCA,
 *    autocompleta razón social y condición IVA». Decision D1 of the roadmap put the
 *    padrón lookup in epic 2, because the company's fiscal credential is only loaded
 *    there. So the CUIT is validated structurally — which is enough to honour «"Continuar"
 *    permanece deshabilitado mientras el CUIT no sea válido» — and razón social and
 *    condición IVA are entered by hand. The success message says what is actually true.
 * 2. **Two fields the prototype does not show.** HU-E1-02 RN-03 lists «nombre del
 *    responsable y email de contacto» among the mandatory fields; the prototype's field
 *    list omits them. The story governs what data is required (gap H7 of the DER), the
 *    prototype governs the layout.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Campo, Card, Stepper } from "@/shared";

import { ErrorDeFormulario, guardarEmpresa } from "../api/cliente";
import { errorDeCuit, esCuitValido, normalizarCuit } from "../validacion/cuit";

const PASOS = [
  { numero: 1, nombre: "Cuenta" },
  { numero: 2, nombre: "Empresa" },
  { numero: 3, nombre: "Integraciones" },
] as const;

const CONDICIONES = [
  { valor: "RESPONSABLE_INSCRIPTO", texto: "Responsable Inscripto" },
  { valor: "MONOTRIBUTO", texto: "Monotributo" },
  { valor: "EXENTO", texto: "Exento" },
  { valor: "CONSUMIDOR_FINAL", texto: "Consumidor Final" },
] as const;

export function FormularioDeEmpresa(): JSX.Element {
  const router = useRouter();
  const [razonSocial, setRazonSocial] = useState("");
  const [cuit, setCuit] = useState("");
  const [condicionIva, setCondicionIva] = useState<string>(CONDICIONES[0].valor);
  const [nombreResponsable, setNombreResponsable] = useState("");
  const [emailContacto, setEmailContacto] = useState("");
  const [general, setGeneral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const errorCuit = errorDeCuit(cuit);
  const cuitOk = esCuitValido(cuit);
  const completo =
    cuitOk &&
    razonSocial.trim() !== "" &&
    nombreResponsable.trim() !== "" &&
    emailContacto.trim() !== "";

  const enviar = async (evento: React.FormEvent): Promise<void> => {
    evento.preventDefault();
    setEnviando(true);
    setGeneral(null);
    try {
      await guardarEmpresa({
        razon_social: razonSocial,
        cuit: normalizarCuit(cuit),
        condicion_iva: condicionIva,
        nombre_responsable: nombreResponsable,
        email_contacto: emailContacto,
      });
      router.push("/panel");
    } catch (error) {
      setGeneral(
        error instanceof ErrorDeFormulario
          ? error.detalle
          : "No pudimos completar la operación. Probá de nuevo en unos minutos.",
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Card titulo="Datos de tu empresa">
      <Stepper pasos={PASOS} actual={2} />

      {general !== null && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <Alert tono="error">{general}</Alert>
        </div>
      )}

      <form onSubmit={(evento) => void enviar(evento)} noValidate>
        <Campo
          id="cuit"
          etiqueta="CUIT"
          mono
          inputMode="numeric"
          required
          placeholder="30-71234567-1"
          error={errorCuit ?? undefined}
          value={cuit}
          onChange={(evento) => setCuit(evento.target.value)}
        />

        {cuitOk && (
          <div style={{ marginBottom: "var(--space-4)" }}>
            {/* Not "verificados contra ARCA": that happens in epic 2, and saying it now
                would be a claim the system cannot back. */}
            <Alert tono="exito">
              CUIT válido — verificaremos los datos contra ARCA al conectar tu cuenta fiscal.
            </Alert>
          </div>
        )}

        <Campo
          id="razon-social"
          etiqueta="Razón social"
          required
          value={razonSocial}
          onChange={(evento) => setRazonSocial(evento.target.value)}
        />

        <div className="campo">
          <label className="campo__etiqueta" htmlFor="condicion-iva">
            Condición IVA
          </label>
          <select
            id="condicion-iva"
            className="campo__control"
            value={condicionIva}
            onChange={(evento) => setCondicionIva(evento.target.value)}
          >
            {CONDICIONES.map((condicion) => (
              <option key={condicion.valor} value={condicion.valor}>
                {condicion.texto}
              </option>
            ))}
          </select>
        </div>

        <Campo
          id="responsable"
          etiqueta="Nombre del responsable"
          required
          value={nombreResponsable}
          onChange={(evento) => setNombreResponsable(evento.target.value)}
        />

        <Campo
          id="email-contacto"
          etiqueta="Email de contacto"
          type="email"
          required
          value={emailContacto}
          onChange={(evento) => setEmailContacto(evento.target.value)}
        />

        {/* «"Continuar" permanece deshabilitado mientras el CUIT no sea válido». */}
        <Button type="submit" cargando={enviando} disabled={!completo}>
          Continuar
        </Button>
      </form>
    </Card>
  );
}
