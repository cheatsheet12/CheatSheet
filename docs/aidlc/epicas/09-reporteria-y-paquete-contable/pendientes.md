# Pendientes — Épico 9 · Reportería y paquete contable

> Lo que este épico deja abierto, con **por qué se dejó** y **quién lo cierra**. Un pendiente
> sin dueño es un pendiente que nadie va a mirar, así que cada uno dice de qué épico es.

---

## Lo que bloquea una demo real

### 1. El paquete y los reportes viven en el almacenamiento en memoria · **decisión de despliegue**

`AlmacenamientoEnMemoria` guarda los bytes en un `dict` del proceso y **se niega a construirse en
producción**, así que no se puede desplegar sin que alguien se entere. En local eso significa que
un reinicio del backend deja los reportes y los paquetes con su fila en la base y sin archivo —
`es_descargable` contesta `False` y la pantalla muestra un guion, que es correcto pero confunde
en una demo.

**Lo que hace falta:** configurar R2 (`ALMACENAMIENTO_ADAPTADOR=r2` y las cuatro variables de
`backend/.env.example`). El adaptador ya existe desde el épico 3 y `reporting` es su tercer
consumidor.

### 2. El correo del contador sale por consola · **decisión de despliegue**

Con `EMAIL_ADAPTADOR=consola` el enlace se imprime en el log en vez de mandarse. Es lo que
permite recorrer el flujo entero sin servidor de correo, y `Settings` se niega a aceptarlo en
producción.

**Lo que hace falta:** las variables de SMTP. El transporte compartido ya existe desde el épico 2.

---

## Lo que este épico decidió no hacer

### 3. Un paquete armado no avisa al contador · **decisión D62, revisable**

El contador tiene que entrar por su enlace a ver si hay algo nuevo. Mandarle un correo mensual
con documentación fiscal adjunta a una casilla que puede haber cambiado de dueño es una decisión
que alguien tiene que tomar explícitamente, no un efecto secundario del barrido.

**Lo que hace falta si se decide que sí:** una plantilla más en
`reporting/infrastructure/plantillas/` y tres líneas en `armar_paquete`. El puerto
(`PortAvisoAlContador`) ya está.

### 4. El día de envío llega hasta 28 · **decisión D60**

«El último día del mes» no se puede pedir. Modelarlo bien no es cambiar el `CHECK` a 31: es
agregar un valor especial —`ULTIMO`— al agregado, a la tabla y a la pantalla, porque «31» en
febrero no significa nada.

**Quién lo cierra:** el épico que traiga la primera empresa que lo pida.

### 5. La generación es síncrona · **decisión D64**

Un reporte se arma dentro del request, con un tope de `TOPE_DE_FILAS = 5000` filas. Una empresa
con cien mil comprobantes en un mes se comería un worker HTTP y llegaría al tope sin decir que lo
alcanzó — **el archivo saldría truncado y nadie se enteraría**, que es la parte fea de este
pendiente.

**Lo que hace falta:** que `_filas_de` devuelva también si hubo corte, y que el reporte lo
registre; después, mover la generación a una tarea de Celery. La máquina de estados ya tiene
`EN_CURSO` para eso (D64), así que la pantalla no cambia.

### 6. El tablero recorre los comprobantes en Python · **deuda de performance conocida**

`FacturacionViaBilling.totales` trae los comprobantes autorizados del período y suma en memoria.
Para una PyME —decenas o cientos por mes— es correcto y es una consulta menos que mantener; para
la empresa del punto anterior son cien mil objetos hidratados para producir cuatro números.

**Lo que hace falta:** una consulta agregada en el repositorio de `billing` —`SUM ... GROUP BY
tipo`— publicada por su capa de aplicación. Es trabajo de `billing`, no de este contexto: el
puerto de acá ya pide totales y no filas, así que el cambio no toca `reporting`.

### 7. El gráfico son barras hechas con `div` · **decisión de alcance**

No hay librería de gráficos en el repositorio y este épico no la introduce. Cuatro o cinco
barras con su valor al lado dicen lo mismo, pesan cero y no agregan una dependencia de front que
después hay que versionar.

**Quién lo cierra:** quien pida un gráfico que las barras no puedan dibujar.

---

## Huecos del modelo que este épico documenta

### 8. `configuracion_de_paquete` no está en el DER · **decisión D59**

La tabla se creó porque HU-E10-04 la exige. Es el mismo caso que H2 del épico 5 y queda anotado
en los dos lugares donde alguien la va a encontrar: el docstring de la migración 0022 y
`decisiones.md`.

**Quién lo cierra:** la actualización del DER, si la cátedra la pide.

### 9. `TokenDeAccesoContable.paquete_id` ata el enlace a **un** paquete

El DER lo modela así y el código lo respeta: el token se emite apuntando al paquete más reciente.
Pero lo que el contador ve al entrar es la **lista** de paquetes de la empresa, acotada por RLS
—que es lo que HU-E10-06 RN-01 pide: «ver reportes mensuales… y descargar paquetes contables»—.

Es decir: la columna existe y se guarda, y hoy no decide qué se ve. No es un bug; es una columna
que quedó más angosta que la regla.

**Lo que hace falta si se quiere ajustar:** o el DER cambia y el token deja de apuntar a un
paquete, o el acceso se limita a ese paquete y HU-E10-06 RN-01 se relee. Es una conversación con
la cátedra, no un cambio de código.

---

## Cobertura y pruebas

### 10. `workers/tasks_reporting.py` está al 51 % de líneas

Lo que está probado es el reparto: que la tarea por empresa se encole en la cola correcta, que un
fallo del broker no aborte el bucle y que la entrada de Beat exista con el nombre que el worker
registra. Lo que no está probado con base real es `armar_paquete` de punta a punta.

El total del backend queda en **87 %**, bien por encima del umbral, y el caso de uso que la tarea
llama (`GenerarPaqueteContable`) tiene 99 % y su propio test de integración a través de la API.

**Lo que hace falta:** un test en `tests/integracion` que active el envío de una empresa y corra
`barrer_paquetes` + `armar_paquete` contra PostgreSQL. Es media hora y no cambia código.

---

## Lo que hereda el épico 10

### 11. La bitácora se lee pero todavía no se pagina

Este épico agregó a `observability` lo mínimo que la métrica de operaciones necesitaba:
`FiltrosDeBitacora`, `listar` y `contar`, con un `limite` obligatorio. El panel de auditoría de
HU-E12-01 va a necesitar paginación real, filtro por usuario y por resultado, y probablemente un
cursor.

**Quién lo cierra:** el épico 10, que es su dueño. La forma del puerto ya está y no debería
cambiar: lo que crece es el filtro.
