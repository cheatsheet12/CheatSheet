/**
 * PAN-COB-03 — Cobros · Nuevo cobro (HU-E6-03, HU-E6-06).
 *
 * Dos validaciones se muestran acá antes de mandar nada, y las dos las impone el backend
 * igual: el concepto es obligatorio y el monto tiene que ser mayor a cero. Mostrarlas de este
 * lado es la diferencia entre un formulario que se explica y uno que contesta 422 después de
 * que alguien escribió todo.
 *
 * **El monto es un campo de texto.** Un `<input type="number">` devuelve un `number` de
 * JavaScript, que es el float que este sistema no deja acercarse a la plata.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Alert,
  Button,
  Campo,
  Card,
  montoDesdeTexto,
  Select,
  useAccionConNavegacion,
} from "@/shared";

import {
  CODIGO_CLAVE_REUSADA,
  ErrorDeCobro,
  MENSAJE_MONTO_NO_POSITIVO,
  MENSAJE_SIN_CONCEPTO,
  generarCobro,
} from "../api/cobro";

/** PAN-COB-03: el texto de la historia para el botón sin cliente elegido. */
const MENSAJE_SIN_CLIENTE = "Debe seleccionar un cliente.";

export interface PropsDeNuevoCobro {
  /**
   * A quién se le cobra, o `null` mientras no se eligió. Lo elige el selector que la página
   * pone arriba (la URL es la fuente de verdad): este formulario no importa nada de
   * `master_data` (R5), solo recibe el id y se niega a generar sin él.
   */
  readonly clienteId: string | null;
  /** HU-E6-06: los comprobantes con saldo, para poder asociar el cobro a uno. */
  readonly comprobantes: readonly { readonly id: string; readonly etiqueta: string }[];
}

export function NuevoCobro({ clienteId, comprobantes }: PropsDeNuevoCobro): JSX.Element {
  const router = useRouter();
  const [descripcion, setDescripcion] = useState("");
  const [monto, setMonto] = useState("");
  const [comprobanteId, setComprobanteId] = useState("");
  // El error recuerda de que cliente era: un rechazo del backend («el comprobante no
  // corresponde al cliente elegido») no debe quedar colgado cuando se elige otro cliente.
  const [fallido, setFallido] = useState<{
    mensaje: string;
    clienteId: string;
    claveReusada: boolean;
  } | null>(null);
  // **La clave identifica el pedido** (ADR-0013): una por formulario, la misma en cada envío o
  // reintento. No se renueva al fallar ni al editar: si el primer pedido llegó pero la respuesta
  // no (un 504 del BFF), reenviar con la misma clave encuentra el cobro en vez de crear otro.
  const [clave, setClave] = useState(() => crypto.randomUUID());
  const { pendiente: generando, ejecutar } = useAccionConNavegacion();

  const visible = fallido !== null && fallido.clienteId === clienteId ? fallido : null;
  const error = visible !== null ? visible.mensaje : null;
  const sinCliente = clienteId === null;
  const sinConcepto = descripcion.trim() === "";
  // Al cambiar de cliente los comprobantes ofrecidos cambian, y el elegido puede ya no estar:
  // no se manda el comprobante de Ana con el cobro de Bruno. Lo escrito no se pierde.
  const comprobanteVigente = comprobantes.some((uno) => uno.id === comprobanteId)
    ? comprobanteId
    : "";
  // Lo escrito en formato argentino («1.234,56») pasa a la forma que lee la API. `Number`
  // sólo decide si el botón está gris: lo que viaja es el texto, y quien decide si el monto
  // vale es el backend.
  const montoNormalizado = montoDesdeTexto(monto);
  const montoInvalido = montoNormalizado === null || !(Number(montoNormalizado) > 0);

  async function generar(): Promise<void> {
    if (clienteId === null) {
      return;
    }
    setFallido(null);
    try {
      await ejecutar(
        () =>
          generarCobro(
            {
              cliente_id: clienteId,
              monto: montoNormalizado ?? monto,
              descripcion,
              comprobante_id: comprobanteVigente === "" ? null : comprobanteVigente,
            },
            clave,
          ),
        // Derecho al detalle: es la pantalla que muestra el link recién generado. El botón
        // sigue ocupado hasta que se muestra: un segundo clic generaría un segundo cobro.
        (cobro, destino) => {
          // Recién después de un éxito: si el navegador restaura esta pantalla (bfcache), un
          // nuevo envío es un cobro nuevo y no devuelve el anterior.
          setClave(crypto.randomUUID());
          destino.push(`/cobros/${cobro.id}`);
        },
      );
    } catch (fallo) {
      // «No se pudo generar el link de pago. Intente nuevamente.» y «El monto no puede superar
      // el saldo pendiente del comprobante.» llegan por acá, con el texto del backend.
      setFallido({
        mensaje: fallo instanceof ErrorDeCobro ? fallo.message : "No se pudo generar el cobro.",
        clienteId,
        claveReusada: fallo instanceof ErrorDeCobro && fallo.codigo === CODIGO_CLAVE_REUSADA,
      });
    }
  }

  // En tarjeta y con ancho acotado, como el resto de los formularios del panel: un campo de
  // texto de 1400 px no es más fácil de completar, y sin superficie propia el formulario se
  // lee como texto suelto sobre el fondo.
  return (
    <div className="cob-alta">
      <Card titulo="Datos del cobro">
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void generar();
          }}
        >
          {error !== null && (
            <Alert tono="error" titulo="No se pudo generar">
              {error}
              {visible !== null && visible.claveReusada && (
                <>
                  {" "}
                  <Link href="/cobros">Ver el listado de cobros</Link>
                </>
              )}
            </Alert>
          )}

          <Campo
            id="cobro-concepto"
            etiqueta="Concepto"
            error={descripcion !== "" && sinConcepto ? MENSAJE_SIN_CONCEPTO : undefined}
            value={descripcion}
            onChange={(evento) => setDescripcion(evento.target.value)}
          />

          <Campo
            id="cobro-monto"
            etiqueta="Monto"
            mono
            ayuda="En pesos argentinos."
            error={monto !== "" && montoInvalido ? MENSAJE_MONTO_NO_POSITIVO : undefined}
            value={monto}
            onChange={(evento) => setMonto(evento.target.value)}
          />

          {comprobantes.length > 0 && (
            <Select
              id="cobro-comprobante"
              etiqueta="Comprobante asociado"
              ayuda="Opcional. Al pagarse, el cobro baja el saldo pendiente del comprobante."
              opciones={[
                { valor: "", etiqueta: "Sin comprobante" },
                ...comprobantes.map((uno) => ({ valor: uno.id, etiqueta: uno.etiqueta })),
              ]}
              value={comprobanteVigente}
              onChange={(evento) => setComprobanteId(evento.target.value)}
            />
          )}

          {sinCliente && <Alert tono="neutral">{MENSAJE_SIN_CLIENTE}</Alert>}
          {sinConcepto && <Alert tono="neutral">{MENSAJE_SIN_CONCEPTO}</Alert>}

          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={() => router.push("/cobros")}>
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={sinCliente || sinConcepto || montoInvalido}
              cargando={generando}
            >
              Generar link de pago
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
