/**
 * El resultado de validar el CUIT contra ARCA, dicho con jerarquía: quién es, en qué condición de
 * IVA está y —lo que importa— qué comprobantes se le pueden emitir (RN-01).
 *
 * Todo es lectura de lo que ARCA contestó: acá no se calcula ni se decide nada.
 */

import { Badge } from "@/shared";

import type { ReceptorValidado } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";

/** `RESPONSABLE_INSCRIPTO` → «Responsable inscripto». */
export function condicionLegible(condicion: string): string {
  const texto = condicion.replaceAll("_", " ").toLowerCase();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** `30712345671` → `30-71234567-1`, para leerlo y dictarlo. Si no son 11 dígitos, tal cual. */
export function cuitConGuiones(cuit: string): string {
  return /^\d{11}$/.test(cuit)
    ? `${cuit.slice(0, 2)}-${cuit.slice(2, 10)}-${cuit.slice(10)}`
    : cuit;
}

export function inicialesDe(nombre: string): string {
  const letras = nombre
    .split(/\s+/)
    .filter((palabra) => /^[\p{L}\p{N}]/u.test(palabra))
    .slice(0, 2)
    .map((palabra) => palabra.charAt(0).toUpperCase());
  return letras.length === 0 ? "?" : letras.join("");
}

export function TarjetaDelReceptor({
  receptor,
}: {
  readonly receptor: ReceptorValidado;
}): JSX.Element {
  return (
    <div className="fac-em-receptor" role="status">
      <div className="fac-em-receptor__persona">
        <span className="fac-em-receptor__avatar" aria-hidden="true">
          {inicialesDe(receptor.nombre)}
        </span>
        <div className="fac-em-receptor__datos">
          <span className="fac-em-receptor__verificado">Verificado en el padrón de ARCA</span>
          <strong className="fac-em-receptor__nombre">{receptor.nombre}</strong>
          <span className="fac-em-receptor__linea">
            <span className="fac-em-receptor__cuit">{cuitConGuiones(receptor.cuit)}</span>
            <Badge estado="ok">{condicionLegible(receptor.condicion_iva)}</Badge>
          </span>
        </div>
      </div>
      <div className="fac-em-receptor__emitible">
        <span className="fac-em-receptor__rotulo">Se le puede emitir</span>
        <ul className="fac-em-receptor__tipos">
          {receptor.tipos_disponibles.map((tipo) => (
            <li key={tipo}>{ETIQUETAS_DE_TIPO[tipo]}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
