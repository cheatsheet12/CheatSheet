/**
 * Shared across features: design system, common types, cross-feature utilities.
 *
 * Depends on NO feature (rule R5). Everything imports this, so it must import
 * nothing back.
 */

export { Alert } from "@/shared/ui/Alert";
export type { PropsDeAlerta, TonoDeAlerta } from "@/shared/ui/Alert";
export { Button } from "@/shared/ui/Button";
export type { PropsDeBoton, VarianteDeBoton } from "@/shared/ui/Button";
export { Card } from "@/shared/ui/Card";
export type { PropsDeCard } from "@/shared/ui/Card";
