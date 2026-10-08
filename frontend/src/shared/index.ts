/**
 * Shared across features: design system, common types, cross-feature utilities.
 *
 * Depends on NO feature (rule R5). Everything imports this, so it must import
 * nothing back.
 *
 * The components implement §1.3 of the Etapa 5 specification
 * (`docs/aidlc/inputs/prototipos/maquetacion-pantallas.pdf`). A screen composes these;
 * it does not invent a button.
 */

export { Alert } from "@/shared/ui/Alert";
export type { PropsDeAlerta, TonoDeAlerta } from "@/shared/ui/Alert";
export { Badge } from "@/shared/ui/Badge";
export type { EstadoDeBadge, PropsDeBadge } from "@/shared/ui/Badge";
export { Button } from "@/shared/ui/Button";
export type { PropsDeBoton, VarianteDeBoton } from "@/shared/ui/Button";
export { Campo, Casilla } from "@/shared/ui/Campo";
export type { PropsDeCampo, PropsDeCasilla } from "@/shared/ui/Campo";
export { Card } from "@/shared/ui/Card";
export type { PropsDeCard } from "@/shared/ui/Card";
export { Desplegable } from "@/shared/ui/Desplegable";
export { SelectorDeFecha } from "@/shared/ui/SelectorDeFecha";
export type { PropsDeSelectorDeFecha } from "@/shared/ui/SelectorDeFecha";
export type {
  PropsDeDesplegable,
  PropsDeGrupo,
  VarianteDeDesplegable,
} from "@/shared/ui/Desplegable";
export { Modal } from "@/shared/ui/Modal";
export type { PropsDeModal } from "@/shared/ui/Modal";
export { Select } from "@/shared/ui/Select";
export type { OpcionDeSelect, PropsDeSelect } from "@/shared/ui/Select";
export { Stepper } from "@/shared/ui/Stepper";
export type { Paso, PropsDeStepper } from "@/shared/ui/Stepper";
export { Tabla } from "@/shared/ui/Tabla";
export type { Columna, PropsDeTabla } from "@/shared/ui/Tabla";
export {
  formatearFecha,
  formatearFechaHora,
  formatearHora,
  formatearNumero,
  PREFERENCIAS_POR_DEFECTO,
} from "@/shared/formato";
export { motivoDeFalla } from "@/shared/motivos-de-falla";
export type { PreferenciasDeFormato } from "@/shared/formato";
export { useAccionConNavegacion } from "@/shared/navegacion";
export type {
  AccionConNavegacion,
  OpcionesDeEjecucion,
  RouterDeNavegacion,
} from "@/shared/navegacion";
