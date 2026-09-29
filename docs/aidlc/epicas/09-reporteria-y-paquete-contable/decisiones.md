# Decisiones — Épico 9 · Reportería y paquete contable

> Lo que este épico decidió, **por qué**, y qué se paga por ello. Una decisión sin costo
> anotado es una decisión que nadie revisó.
>
> Continúan la serie del sistema: D1–D19 en [`units.md`](../../units.md), D20–D27 en el
> [épico 6](../06-cobros-y-recordatorios/decisiones.md), D28–D37 en el
> [épico 7](../07-agenda-y-recursos/decisiones.md) y D38–D50 en el
> [épico 8](../08-agente-de-whatsapp/decisiones.md).

---

## D51 — este contexto **sólo lee**, y sus puertos lo dicen

**Es la decisión que gobierna el épico entero.** `reporting` es el único contexto que cruza los
cuatro contextos con datos —`billing`, `payments`, `scheduling`, `observability`— y el único que
tiene un actor **sin cuenta** del otro lado. Las dos cosas juntas hacen que la pregunta
importante no sea «qué puede hacer», sino «qué no puede hacer aunque quiera».

**Lo que se hizo:** los cuatro ACL (`PortFacturacion`, `PortCobranzas`, `PortAgendaLeida`,
`PortBitacora`) tienen métodos que devuelven números y filas, y **ninguno que cambie nada**. No
hay un `emitir`, ni un `cobrar`, ni un `reservar`. `AgendaViaSchedulingLeida` es deliberadamente
una clase distinta de la que el épico 8 usa para reservar y cancelar sobre el mismo contexto:
la que reporta no necesita poder reservar, y dársela «porque ya está» es cómo un módulo de
lectura termina con permisos de escritura.

**Lo que cuesta:** dos ACL sobre `scheduling` en vez de uno, y una clase más por mantener. Es
barato comparado con la propiedad que compra: un bug en el tablero no puede tocar un
comprobante, y eso no depende de que nadie lo llame — depende de que la llamada no exista.

---

## D52 — el mes se compara contra el **mes** anterior, no contra los treinta y un días previos

HU-E10-01 RN-02 pide la variación «respecto al período anterior». La lectura literal —la
ventana del mismo largo, inmediatamente antes— produce una comparación que no significa nada
cuando el período es un mes: marzo tiene 31 días y febrero 28, así que «el mismo largo justo
antes de marzo» empieza el 29 de enero.

**Lo que se hizo:** `Periodo.anterior` mira si el período es un mes entero. Si lo es, devuelve
el mes calendario anterior; si es un rango cualquiera —uno que alguien eligió a mano en el
selector—, devuelve la ventana del mismo largo, que es lo único que «el anterior» puede
significar ahí.

**Lo que cuesta:** una propiedad más en el value object (`es_un_mes_entero`) y una regla que hay
que conocer para leer el número. A cambio, la variación de un mes deja de moverse todos los
meses por el largo del mes que se mira, que es un ruido que nadie podría explicar.

---

## D53 — la previsualización **no crea nada**, y el verbo lo dice

HU-E10-02 RN-03: «la previsualización no consume el ciclo de generación». Es fácil de cumplir
por accidente y fácil de romper por accidente: basta que alguien decida reusar `GenerarReporte`
«marcando» la fila como provisional.

**Lo que se hizo:** `PrevisualizarReporte` es un caso de uso aparte que no toca
`PortRepositorioReportes` — ni siquiera lo recibe en el constructor, así que no puede escribir
aunque el código cambie. Y la ruta es un `GET`: un `POST` sugeriría que crea algo y alguien
terminaría poniéndole una confirmación.

**Lo que cuesta:** dos caminos que consultan lo mismo. El test de integración afirma la
propiedad desde afuera: tres previsualizaciones, cero filas en el historial.

---

## D54 — el reporte suelto se niega sin datos; **el paquete se genera igual**

Son la misma pregunta con dos respuestas opuestas, y la diferencia es quién está del otro lado.

Un reporte lo pide una persona que está mirando la pantalla: si el mes está vacío, el mensaje de
HU-E10-03 —«No hay datos para generar el reporte en el período seleccionado.»— es más útil que
un CSV con un encabezado, y una fila `FALLIDO` sería ruido en el historial que el último
criterio pide mostrar. Por eso `GenerarReporte` **comprueba antes de crear la fila**.

Un paquete lo arma un barrido a las tres de la mañana y lo recibe un contador que no está
mirando nada. Si un mes sin actividad no produjera paquete, ese contador no podría distinguir
«no hubo movimientos» de «el sistema no me lo mandó» — y esa distinción es la única razón por la
que el envío automático existe.

**Lo que cuesta:** un paquete de un mes vacío es un ZIP con los totales en cero y sin archivos
adentro. Es exactamente lo que se quería decir.

---

## D55 — un mes tiene **un** paquete, y lo garantiza un índice único

El barrido corre sin que nadie mire. Dos procesos de Beat, o un reintento manual sobre uno
automático, producirían dos paquetes de marzo con contenidos distintos y ninguna forma de saber
cuál abrir.

**Lo que se hizo:** `uq_paquete_empresa_periodo` sobre `(empresa_id, periodo_anio, periodo_mes)`
en la migración 0022, y `GenerarPaqueteContable` **rehace** el paquete existente en lugar de
fallar. Es lo que permite apretar dos veces «generar paquete de prueba», y lo que permite
rehacer un paquete cuyo archivo se perdió.

Se prueba **intentando el duplicado** (`test_dos_paquetes_del_mismo_mes_no_entran`), igual que
D14 y D20: confiar en que el código no lo intente no prueba nada sobre el proceso que corre solo.

**Lo que cuesta:** el paquete de un mes es mutable hasta que alguien lo descargue. No hay
versión ni historial de regeneraciones; si eso hiciera falta, es una tabla nueva.

---

## D56 — el `valor_hash` del enlace es único **en toda la tabla**, no por empresa

Es el único índice del sistema que no está acotado por `empresa_id`, y tiene que serlo.

El contador llega **sin sesión**: el enlace es lo único que dice de qué empresa es. La búsqueda
por hash corre entonces *antes* de saber el inquilino, contra la función `SECURITY DEFINER`
`empresa_de_token_contable`. Dos filas con el mismo digesto convertirían esa consulta en una
ambigüedad, y quien la resolvería sería el azar — eligiendo a qué empresa dejar entrar.

**Lo que cuesta:** una colisión de SHA-256 sobre 256 bits aleatorios haría fallar una invitación
con un `IntegrityError` en vez de dar acceso cruzado. Es el modo de falla correcto, y su
probabilidad no es un número que valga la pena escribir.

---

## D57 — el enlace del contador **no vuelve por la API**: sale por mail y se olvida

`InvitarContador` devuelve el enlace en claro a su llamador, pero el router **no lo pone en la
respuesta**: lo que la pantalla recibe es el estado del contador («Invitado con acceso
limitado», el texto del criterio).

Devolvérselo al administrador lo dejaría en el historial del navegador, en el caché del BFF y en
cualquier log de acceso del camino — que es justamente lo que guardar el hash evita del lado de
la base. Si el enlace se perdió, se revoca y se invita de nuevo, y eso además deja rastro.

**Lo que cuesta:** el administrador no puede reenviarle el enlace al contador por WhatsApp. Es
una molestia real, y es el precio de que el enlace exista una sola vez.

---

## D58 — si el mail no sale, **la invitación no ocurrió**

Es la decisión contraria a D33 (el aviso de un turno) y a D48 (el canal del agente), donde un
fallo del canal no deshace el hecho de negocio. La diferencia es cuál es el hecho: allá el turno
ya estaba reservado y el aviso era una consecuencia; acá **el enlace es el mail**.

**Lo que se hizo:** `AvisoAlContadorPorEmail` levanta `InvitacionNoEnviada`, que se propaga y
deshace la transacción — y con ella el token. Un token guardado que nadie recibió no es un
acceso compartido: es una fila que va a hacer que la próxima invitación choque contra «ya hay un
contador con acceso».

**Lo que cuesta:** un servidor de correo caído bloquea la invitación. Es correcto: sin correo no
hay forma de que el contador reciba nada.

---

## D59 — `configuracion_de_paquete` es una tabla que el DER no tiene

El mismo tipo de hueco que H2 en el épico 5: HU-E10-04 RN-02 y RN-03 exigen persistir día de
envío, formato, contenido y email del contador, y el modelo de datos no lo previó.

**Lo que se hizo:** la tabla se crea, con `empresa_id` como **clave primaria** —una
configuración por empresa, no dos que se contradicen— y con dos `CHECK` que repiten invariantes
del agregado: el día va del 1 al 28 y no se puede estar activo sin email de contador. La
repetición es deliberada: el agregado los comprueba para dar el mensaje textual de la historia,
y el `CHECK` los comprueba para que ninguna otra vía de escritura —una migración de datos, un
`psql` a mano— pueda dejar una empresa con un envío que no va a llegar a ningún lado.

**Lo que cuesta:** una tabla que no está en el DER entregado. Queda anotada acá y en el
docstring de la migración.

---

## D60 — hasta 28 y no hasta 31

Febrero existe. Un envío programado para el día 30 no saldría nunca en el mes que más importa
cerrar a tiempo, y el usuario no tendría forma de enterarse: la pantalla mostraría una fecha de
próximo envío que se corre sola.

**Lo que cuesta:** alguien que quiera el paquete «el último día del mes» no puede pedirlo. Está
en los pendientes.

---

## D61 — el barrido es **diario**, no mensual

El día de envío lo elige cada empresa, así que no hay un día del mes en el que corresponda
correr: hay un día por empresa. Beat despacha `reporting.barrer_paquetes` una vez por día, y la
función `empresas_con_paquete_activo(dia)` contesta con las que tienen ese día configurado —y un
email de contador cargado, porque armar un paquete que no va a ir a ningún lado es trabajo
tirado.

El día viaja como **parámetro** y no sale de `now()` adentro de la función: un barrido que se
corre a mano para reponer un envío perdido tiene que poder pedir el día que corresponde.

**Lo que cuesta:** 29 corridas por mes que no hacen nada. Cada una es una consulta que devuelve
cero filas.

---

## D62 — el paquete armado **no manda un correo**

El contador ya tiene su enlace (HU-E10-05), y lo que el enlace muestra es la lista de paquetes
disponibles. Agregarle un mail mensual al barrido sería mandar una notificación que nadie pidió,
con documentación fiscal adjunta, a una casilla que puede haber cambiado de dueño desde que se
cargó.

**Lo que cuesta:** el contador tiene que entrar a mirar. Si el aviso hiciera falta, es una línea
en el barrido y una plantilla — está en los pendientes.

---

## D63 — el formato elegido **no puede vaciar el paquete**

`formatos` en la configuración dice PDF, XML o ambos (RN-02), pero no todos los contenidos
existen en todos los formatos: el reporte de cobros sólo tiene sentido en CSV, y el resumen
ejecutivo sólo en PDF (`FORMATOS_POR_TIPO`).

**Lo que se hizo:** cada contenido sale en los formatos elegidos **que admite**; si no admite
ninguno, sale en el suyo. Alguien que configuró «sólo XML» no está pidiendo que el reporte de
cobros desaparezca del paquete: está diciendo qué prefiere cuando hay opción.

**Lo que cuesta:** el ZIP puede traer un CSV a alguien que pidió XML. Es mejor que traerle un
paquete al que le falta la mitad.

---

## D64 — la generación es **síncrona**, y el estado `EN_CURSO` existe igual

El DER le da estados a `Reporte` y el sistema los usa —`PENDIENTE → EN_CURSO → LISTO | FALLIDO`—
pero el archivo se arma dentro del request: un CSV de un mes de una PyME son kilobytes.
Encolarlo agregaría un worker, una cola y una pantalla de espera para ahorrar medio segundo.

El estado se mantiene porque es lo que hace que el día que deje de ser cierto —un cliente con
cien mil comprobantes— la única obra sea mover la generación a una tarea. La máquina de estados
ya está, la pantalla ya sabe mostrar `EN_CURSO`, y `FALLIDO` ya conserva la fila.

**Lo que cuesta:** un reporte grande ocupa un worker HTTP mientras se arma, y el tope de
`TOPE_DE_FILAS` (5000) es lo que evita que eso se vuelva un problema silencioso.

---

## D65 — un reporte `FALLIDO` **no se reintenta sobre la misma fila**

`TRANSICIONES_LEGALES` no tiene salida desde `FALLIDO`. Un reporte que falló se pide de nuevo, y
eso deja dos filas: la que falló y la que salió.

Reintentar sobre la misma borraría la evidencia de que hubo un problema, que es justo lo que
alguien va a buscar cuando pregunte por qué su contador no recibió nada el mes pasado.

**Lo que cuesta:** el historial tiene filas fallidas. Eso es el punto.

---

## D66 — el CSV va con `;` y con BOM

Excel en español interpreta la coma como separador decimal: un CSV con comas abre en una sola
columna en la máquina del contador. Y sin BOM, los acentos salen rotos.

Las dos cosas se descubren cuando alguien abre el archivo, no antes — y quien lo abre no es
quien lo generó.

**Lo que cuesta:** un CSV con `;` es menos «estándar» y una herramienta que espere comas va a
necesitar una opción. La herramienta que importa acá es Excel en es-AR.

---

## D67 — el XML se arma con `ElementTree`, no concatenando cadenas

Un nombre de cliente con un `&` es entrada de un usuario. Concatenar produciría un XML roto que
el contador no puede abrir, y el error aparecería del otro lado de la cadena — en el estudio
contable, un mes después.

**Lo que cuesta:** nada. Es la biblioteca estándar.

---

## D68 — el digesto del enlace **no comparte función con el del épico 1**

`hashear_token_opaco` vive en `identity/infrastructure/` y la regla R3 prohíbe importarlo desde
otro contexto. La alternativa era promoverlo a `platform/`, que ataría dos credenciales que
**nunca se comparan entre sí** —un refresh token y un enlace de contador no se buscan en la
misma tabla ni se validan en el mismo lugar— para ahorrar tres líneas.

**Lo que se hizo:** `EnlaceContableAleatorio` hace su propio SHA-256, con el mismo criterio
documentado (SHA-256 y no Argon2: no hay nada que adivinar en 256 bits aleatorios, y pagar 19
MiB por verificación haría fácil de saturar la única ruta pública del épico).

**Lo que cuesta:** dos implementaciones de tres líneas. Si un día hay que rotar el algoritmo, son
dos lugares — y son dos lugares que se pueden rotar por separado, que es una ventaja.

---

## D69 — el Operador **no** configura el envío ni reparte llaves

Responde la pregunta **D5** del roadmap. HU-E10-04 RN-04 dice textualmente que la configuración
del envío automático está restringida al Administrador, y el actor de HU-E10-05 también lo es.
Lo que se comparte es la documentación fiscal completa de la empresa.

**Lo que se hizo:** `_exigir_administrador` en `ConfigurarPaquete`, `InvitarContador`,
`RevocarAccesoDelContador` y en la generación de paquetes. El Operador sí genera reportes
sueltos (HU-E10-03), y Solo Lectura y el contador externo ven el tablero (RN-04 y RN-05).

**Lo que cuesta:** una empresa donde el Operador administra de hecho necesita que el
Administrador entre para configurar el paquete. Es lo que la historia pide.

---

## D70 — el administrador **sí** puede generar un paquete de un período arbitrario

Responde la pregunta **D6** del roadmap. `POST /reporteria/paquetes` acepta año y mes; sin
ellos, arma el del mes cerrado, que es el mismo que arma el barrido.

Es lo que hace falta cuando un envío se perdió —el worker estuvo caído, alguien activó el envío
tarde— y es el «paquete de prueba» del cuarto criterio de HU-E10-04, que es el mismo caso de uso
a propósito: un paquete de prueba armado por otro camino probaría otra cosa que la que se manda.

**Lo que cuesta:** se puede rearmar el paquete de un mes ya cerrado con los datos de hoy. Los
comprobantes autorizados no cambian, así que el contenido no debería moverse; si se movió, es
porque algo se emitió tarde, y eso es información y no un error.

---

## D98 — Inicio y Reportes muestran la misma cobranza, medida de la misma manera

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `indicadores-de-cobranza` · HU-E10-01*

La pantalla Inicio no pertenece a ninguna historia; solo se la nombra como destino del ingreso. Lo
más cercano es HU-E10-01, con su selector de período y su «total cobrado», y su precondición
(«existe al menos un comprobante emitido en el período») contradecía su propio criterio de período
sin actividad y dejaba afuera períodos con solo cobros.

**HU-E10-01 cubre Inicio; no hay una historia nueva.** Inicio muestra el resumen de cobros con el
mismo selector de período que Reportes (mes en curso por defecto) y la misma definición de métricas.
Reportes suma «cobrado por semana» y «cobros por estado». «Cobrado» se mide por fecha de pago y los
reembolsos restan en el período de la devolución (D91, D93); la tasa de cobro se calcula solo sobre
lo creado en el período; y «cobros por estado» agrupa lo creado en el período por su estado actual, y
el subtítulo del gráfico lo dice. Se eliminó la precondición del comprobante.

**Para el Gate 1 de `indicadores-de-cobranza`:** este contexto solo lee (D51), así que necesita
`fecha_pago` y la fecha de cada reembolso a través de la capa de `application` de `payments` o de
eventos, sin join; y hay que asignar el código de pantalla de Inicio.
