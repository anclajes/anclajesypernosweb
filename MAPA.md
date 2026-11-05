# MAPA DEL SISTEMA (Anclajes y Pernos Perú SAC / Import Bolts & Estructure SAC)

ERP en Flask + SQLAlchemy (Postgres en Render), archivos en S3, PDF con xhtml2pdf y Excel con openpyxl.
Se despliega con GitHub → Render (`Procfile`: `gunicorn app:app`). Las tablas y columnas nuevas se crean
solas al arrancar (`_agregar_columnas_si_faltan`): no hay que correr migraciones.

**Para trabajar con Claude:** abrir una conversación nueva por tema y empezar con
"lee MAPA.md". Así no hace falta arrastrar el historial de conversaciones anteriores.

## Estructura

```
app.py                 núcleo y módulos antiguos (todavía juntos) + carga de modulos/
models.py              modelos del núcleo + importa los modelos de cada módulo (al final)
modulos/
  insumos/             INSUMOS INTERNOS
    modelos.py           tablas: Insumo, InsumoStock, InsumoLote, InsumoSalidaLote, ingresos, salidas, movimientos, documentos...
    base.py              empresas, permisos (_ruta_insumos), tablas, LOTES PEPS (entrar/sacar/poner precio), migración a lotes
    inventario.py        inventario por empresa, importar Excel, maestro de insumos, proveedores de insumos
    movimientos.py       ingresos (factura / desde OC), salidas (PDF y firma), kardex valorizado, precio de un lote
    gasto_config.py      gasto por área, configuración, vaciar el módulo
    estadisticas.py      ficha de precios de un insumo (/insumos/ficha/<id>: lotes, históricos, gráfico por proveedor)
                         y ESTADÍSTICAS (/insumos/estadisticas: mejores precios, proveedores, más comprado / gastado / consumido, alertas)
  compras/             ÓRDENES DE COMPRA / SERVICIO y REQUERIMIENTOS
    modelos.py           tablas: OrdenCompra, OrdenCompraItem, entregas, eventos, documentos, proveedores,
                         cuentas, motivos, requerimientos, OCConfig
    base.py              roles (ROLES_OC_*), empresas, catálogos, tablas, permisos (_ruta_oc), numeración,
                         _leer_orden_form (validación e IGV), recepción (_oc_recepcion) y pagos
    ordenes.py           lista (con aprobación rápida), Excel, crear/editar (incluye cambiar de empresa),
                         detalle y flujo (enviar, aprobar, rechazar, anular, observación)
    reportes.py          REPORTES DE COMPRAS (/ordenes/reportes): tablero con Visión ejecutiva y Visión operativa, Excel
    mejores_precios.py   MEJORES PRECIOS (/ordenes/precios, también el menú "Mejores Precios"): por producto, por proveedor,
                         detalle, gráficos, ahorro potencial y Excel con gráficos (productos, insumos y servicios)
    en_camino.py         EN CAMINO (solo Gerencia): en los inventarios de Anclajes, Import Bolts e Insumos, por producto,
                         lo que viene en OC aprobadas (en camino / llegó / por sumar / sumado hace X días) y la línea de tiempo
    entregas.py          llegadas totales/parciales, conformidad, pago y factura, cuentas bancarias,
                         cliente, ingresos pendientes al inventario e ingreso al Kardex
    uso_directo.py       USO DIRECTO (/ordenes/uso-directo): bienes que no van a ningún inventario (PC, muebles...):
                         registrar / corregir la entrega (a quién, dónde, serie y garantía) y el registro con Excel
    certificados.py      CERTIFICADOS POR SUBIR (/ordenes/certificados): importaciones sin certificado de calidad
                         (el certificado es opcional: nunca frena la conformidad ni el ingreso)
    pdf_proveedores_config.py   PDF de la orden, proveedores y contactos, buscador de productos, configuración
    requerimientos.py    requerimientos de compra (Inventario General o Insumos internos), seguimiento, novedades
    vaciar_menu.py       vaciar datos de órdenes (pruebas) y los números del menú
  kardex/              KARDEX (lo nuevo; el resto del Kardex sigue en app.py)
    modelos.py           tabla MovimientoEliminado (auditoría de movimientos eliminados)
    eliminar.py          ELIMINAR un movimiento registrado por error (Gerencia y Jefe de Almacén): revierte el stock, corrige
                         los saldos posteriores y guarda la copia en "Movimientos eliminados" (/kardex/eliminados)
    venta_servicio.py    salida a MAESTRANZA / TRANSFORMACIÓN que sale como VENTA (cliente, OC del cliente opcional y
                         editable después) y su vínculo con las Órdenes de Servicio (desde el movimiento, el Kardex o la OS)
  avisos/              CAMPANA Y AVISOS
    modelos.py           Notificacion, NotificacionConfig, PushSuscripcion
    notificaciones.py    tipos de aviso, configuración por usuario, API de la campana, aprobación rápida
    push.py              aviso de Windows con la página cerrada (Web Push, /sw.js)
    agente.py            PROGRAMA DE AVISOS de Windows: llega con el navegador CERRADO del todo. Instalador .cmd por PC
                         (Campana → Configurar), el programa (PowerShell) pregunta cada minuto a /notificaciones/agente/api
                         con su clave (tabla aviso_agente, solo la huella). "Quitar" → el programa se desinstala solo.
                         Mientras funciona, el Web Push y la campana no repiten el aviso de Windows de ese usuario.
templates/             plantillas (todas en una carpeta; prefijos: oc_*, insumos_*, notificaciones, _campana...)
                       _en_camino.html: panel, botones por producto y ventana de "En camino" (inventarios de Anclajes,
                       Import Bolts, Insumos y el Inventario General con los dos: `script_varios([ec1, ec2])`)
                       _graficos.html: BASE COMÚN DE GRÁFICOS (ver "Gráficos" más abajo)
                       _mov_venta_servicio.html: bloque "Sale como VENTA" del Movimiento de Kardex (los 2 inventarios)
                       _kardex_venta.html: cómo se ve la venta tras servicio en los 2 Kardex y su ventana de edición
```

## Cómo se cargan los archivos de `modulos/`

- **Modelos** (`modulos/*/modelos.py`): son módulos normales de Python. `models.py` los importa al final,
  así que `from models import OrdenCompra` sigue funcionando igual en todo el sistema.
- **Rutas y funciones** (todos los demás `.py` de `modulos/`): **no se importan**. `app.py` los carga, en el orden de la
  lista `MODULOS_EN_ARCHIVOS` (cerca del final de `app.py`), dentro de su propio espacio. Es exactamente como si su
  código estuviera escrito ahí: usan directamente `app`, `db`, los modelos y las funciones de `app.py`
  (`hora_peru`, `registrar_log`, `_borrar_de_s3`...) y de los archivos cargados antes.
  - Los nombres de las rutas no cambiaron (`url_for('oc_detalle')`, `url_for('insumos_inventario')`...).
  - Si se agrega un archivo nuevo, hay que sumarlo a `MODULOS_EN_ARCHIVOS` en el orden correcto.
  - El editor (VS Code) puede marcar nombres "no definidos" en esos archivos: es normal (vienen de `app.py`).
  - Los errores en Render muestran el archivo y la línea real (por ejemplo `modulos/compras/entregas.py`, línea 120).

## Lo que sigue en `app.py` (líneas aproximadas)

| Líneas | Contenido |
|---|---|
| 1–650 | imports, configuración, S3, utilidades, auditoría (períodos, fotos) |
| 650–1690 | dashboards de inicio (admin, ventas) |
| 1690–3320 | control de acceso de usuarios, login, actividad de usuarios y alertas |
| 3320–5910 | búsqueda flexible, inventario Anclajes (CRUD, kardex, movimientos) |
| 5910–7420 | maestro de productos (Excel MAESTROV2) |
| 7420–9360 | kardex: documentos adjuntos, procesos por OC, consumo interno |
| 9360–9620 | picking (salidas de almacén) |
| 9620–10400 | inventario ImportBolts (CRUD, exportar, categorías) |
| 10400–11640 | rotación de stock |
| 11640–14260 | auditorías (auditor, fotos, panel admin, catálogos, motivos, estado físico, campos, períodos, correcciones) |
| 14260–14720 | reset de datos de prueba y backups |
| 14720–15610 | dashboards de ventas por toneladas y gráficos PDF |
| 15610– | carga de `modulos/` y arranque |

Próximos candidatos para separar (cuando se trabajen): inventario Anclajes/ImportBolts, auditorías, usuarios/actividad.

## Roles

admin (Gerencia), administracion, logistica, almacen, almacen_visor (solo lectura del Inventario General), vendedor, chofer.
- Compras: ven `ROLES_OC_VEN` (admin, logistica, administracion); editan admin y logistica; aprueba solo admin.
- Mejores precios: solo `ROLES_OC_VEN` (admin, logistica, administracion). En camino: solo admin (Gerencia).

## Importaciones

- Precio por pieza (USD/PCS, hasta 7 decimales) como la factura comercial; se guarda también el precio por 1000 piezas (derivado).
  Las órdenes antiguas (por 1000 piezas) ya tienen su precio por pieza en `precio_unitario`.
- Certificado de calidad: opcional. En importaciones queda "pendiente" (aviso en la orden y lista "Certificados por subir").
- Proveedor del exterior sin Tax ID: se guarda con un código temporal `SINTAXID001...` y se completa desde la orden
  ("Completar Tax ID"); se corrige también en sus órdenes.
- Requerimientos: los crean admin, logistica, almacen y almacen_visor; los atienden admin y logistica.
- Insumos: editan admin, almacen y logistica.

## Insumos: lotes PEPS, precio pendiente y documentos de la OC

- **Sin promedios: cada compra es un LOTE** (`insumo_lote`) con su precio real (S/ o US$, sin convertir). Las salidas sacan
  **primero del lote más antiguo** (orden por `fecha`, `id`); si toman de dos lotes, cada parte va a su precio
  (`insumo_salida_lote` guarda de qué lote salió cada parte). `insumo_stock` solo guarda totales, recalculados desde los lotes
  (`_sincronizar_stock`); su `costo_promedio` es solo de referencia. El valor del inventario es la suma exacta de los lotes.
- **Paso a lotes (una vez, al arrancar):** `_migrar_a_lotes` convierte el stock que había en lotes "Saldo anterior" a su costo
  promedio (si era 0, quedan **sin precio**). Marca `SystemConfig('insumos_lotes')`. Con Postgres usa un candado para que lo haga un solo proceso.
- **# Factura opcional** en Nuevo ingreso (se agrega o corrige después en el detalle del ingreso).
- **Precio pendiente:** el lote entra con `costo_unitario = None`. Sale en su turno "sin precio" (movimiento `moneda='SC'`).
  Al ponerle el precio (`_poner_precio_lote`: en el ingreso, en la ficha del insumo o con "usar el precio de esta compra" en
  una reposición) **se recalculan todas sus salidas** y el gasto por área. Corregir un precio ya puesto: solo Gerencia, con motivo
  (Kardex: AJUSTE DE COSTO). Poner un precio pendiente: Kardex PRECIO COMPLETADO (`concepto='VALORIZACION'`).
- **Anulaciones:** anular un ingreso exige su lote completo (lote ANULADO). Anular una salida devuelve lo despachado a los mismos lotes.
  En el Kardex, lo anulado y su anulación se marcan y **no cuentan en los totales** (botón para ocultarlos).
- Carga desde Excel: lo que se agrega entra como lote "Carga Excel" con el costo del archivo (vacío = sin precio); lo que sobra se descuenta por PEPS.
- La OC de cada ingreso se guarda en `insumo_ingreso.orden_compra_id` (los antiguos se encuentran por `orden_compra.insumo_ingreso_id`).
  Kardex, Ingresos y el detalle muestran la OC (PDF) y todos sus documentos con ver/descargar. Menú reutilizable: `templates/_oc_docs_menu.html`.
- Órdenes de compra (lista): muestra quién **creó** la orden, filtro "Creó", y el menú 📎 con todos los documentos.

## Compras: OC de TEMA CONTABLE (no suma al inventario)

- Se elige como **Motivo de la compra → "TEMA CONTABLE"** (motivo del sistema `MOTIVO_CONTABLE`: se crea solo, no se borra ni se
  renombra en Configuración). Al elegirlo el formulario explica qué hace. Marca `orden_compra.es_contable` y el "detalle o referencia"
  queda como `contable_nota`. Solo en OC (no en OS). Si el proveedor es la otra empresa (mismo RUC) el formulario sugiere elegirlo.
  Uso: compras solo para contabilidad, p. ej. Anclajes le compra a Import Bolts material que **ya está** en los inventarios.
- Sigue el flujo normal (aprobación, llegada, conformidad, pago). Al estar CONFORME **no se ingresa**: en "Ingresos pendientes" (y en
  el detalle) sale "Confirmar tema contable" (`oc_contable_confirmar`, roles `ROLES_OC_CONTABLE`: admin, logística, administración,
  almacén). Guarda quién/cuándo en `fecha_kardex` / `kardex_registrado_por_id` / `nota_seguimiento`. Gerencia puede quitar la confirmación.
- Se ve en todo el flujo: chip CONTABLE en la lista, detalle, aprobación rápida de Gerencia (campana), Ingresos pendientes; filtro
  "Tema contable" y botón "Contables" en la lista; columnas en el Excel. No entra en "En camino", en "Ingresos pendientes" para sumar,
  en Insumos pendientes ni en "Mejores precios" (no es precio de mercado). Sí cuenta en los reportes de gasto.

## Compras: destino USO DIRECTO (bienes que no van a ningún inventario)

- Tercer destino de una OC: **"Uso directo"** (`destino = 'DIRECTO'`, en `DESTINOS_OC`). Para bienes que la empresa compra para USARLOS
  (componentes de PC, celulares, muebles, herramientas, maquinaria...). No va al inventario general ni a insumos. Solo OC (no OS) y no
  se combina con TEMA CONTABLE. Los ítems se escriben a mano (no se enlazan a productos ni insumos). Se pueden jalar de un
  REQUERIMIENTO de "Uso directo" (ver abajo).
- Al crear la orden: **Categoría** (catálogo `OC_DIRECTO_CATEGORIA`) y **Ubicación / a dónde va** (catálogo `OC_DIRECTO_UBICACION`), obligatorias;
  "Para qué / detalle" y **Activo fijo** opcionales. Columnas `orden_compra.directo_categoria/_ubicacion/_detalle/_activo_fijo/_entregado_a`.
  Los dos catálogos están en Configuración (pestañas "Categorías de uso directo" y "Ubicaciones") y se siembran solos si están vacíos.
- Flujo normal (aprobación, llegada, conformidad, pago). Al estar CONFORME se **registra la entrega** (`modulos/compras/uso_directo.py`,
  ruta `oc_directo_entregar`, roles `ROLES_OC_CONTABLE`): a quién (obligatorio), ubicación final, nota y, por ítem, **N° de serie**
  (`orden_compra_item.serie`) y **garantía hasta** (`garantia_hasta`), ambos opcionales. Se hace desde el detalle (modal) o desde
  "Ingresos pendientes" (tarjeta naranja). Quién/cuándo en `fecha_kardex` / `kardex_registrado_por_id`; nota en `nota_seguimiento`.
  Después se puede **corregir** (queda en el historial `DIRECTO_EDITADO`); Gerencia puede quitar el registro (`oc_directo_deshacer`).
  Una vez entregada ya no se re-edita la orden (hay que deshacer la entrega).
- **Por ítem**: la categoría y la ubicación de la orden son el valor por defecto; cada ítem puede tener las suyas
  (`orden_compra_item.directo_categoria/_ubicacion`, selects `directo_cat_item[]` / `directo_ubi_item[]` en el formulario; '' = la de la
  orden). En la entrega también se elige a dónde queda cada ítem (`ubicacion_<id>`). Categoría "ÚTILES Y SUMINISTROS DE OFICINA" agregada
  una vez (SystemConfig `oc_directo_utiles_v1`).
- **Registro de uso directo** (`/ordenes/uso-directo`, `oc_registro_directo`, plantilla `oc_uso_directo.html`): un renglón por bien con
  categoría, ubicación, entregado a, serie, garantía (vigente / vence en ≤30 días / vencida), orden, proveedor y monto; filtros y Excel.
- Se ve en todo el flujo: chip USO DIRECTO (`templates/_oc_directo.html`), lista (filtro Destino, botón "Uso directo"), detalle,
  campana (aviso "Bien de uso directo por entregar"), Ingresos pendientes y contador del menú; columnas en el Excel de órdenes.
  En "Mejores precios" es la clase "Uso directo".

## Compras: EN CAMINO en los inventarios (solo Gerencia)

- `_en_camino_calcular` (modulos/compras/en_camino.py) arma por orden: quién la creó (`creo`), una frase clara de en qué va (`frase`:
  cuándo llega / atrasada / llegó y falta revisar / revisada y conforme en planta, falta sumar / TERMINADA con fecha, quién la sumó y
  cuándo se deja de mostrar), la línea de tiempo con el ENCARGADO de cada paso (`pasos[].quien`: aprobó, recibió, dio conformidad,
  sumó al inventario), el PDF y los documentos (`docs`) y la lista COMPLETA de ítems (`todos`). `ord_map` = órdenes por id.
- `_en_camino.html`: tarjetas con descripciones completas (ya no se cortan), "Ver los N ítems" / "Ver completa" abre el modal de la orden;
  clic en el estado de un producto abre sus órdenes con la lista completa y ESE producto en verde, más PDF y documentos para ver/descargar.
  Las terminadas (todo sumado) salen en verde y se ocultan a los `DIAS_INGRESO_RECIENTE` días.
- Inventario General: dos paneles (Anclajes e Import Bolts) y el estado en cada producto según su origen.
- Importaciones: el resumen del panel (antes de "Ver detalle") muestra un chip azul "N IMPORTACIONES (x en camino · y en planta ·
  z terminadas)" (`resumen.imp_total/imp_camino/imp_planta/imp_terminadas`); en tarjetas y modal la etiqueta `.ec-imp` es azul, grande y con 🌐.

## Requerimientos de USO DIRECTO y borrar códigos creados por error

- Requerimientos (`modulos/compras/requerimientos.py`, `DESTINOS_REQ`): tercer destino **"Uso directo"** (`destino='DIRECTO'`) para útiles,
  equipos, muebles... que no van a ningún inventario. Los bienes se escriben a mano (campo `descripcion[]`, `codigo=''`), con cantidad y U.M.
  Al cambiar un requerimiento a Uso directo se conservan descripciones y cantidades. Pide CATEGORÍA y A DÓNDE VA (obligatorios) y
  "para qué" (opcional): columnas `requerimiento_compra.directo_categoria/_ubicacion/_detalle`; al jalarlo a la OC se copian. Logística arma la OC con destino "Uso directo" y el
  avance termina en "Entregado" (cuando se registra la entrega de la OC).
- Si un requerimiento del Inventario General pide un código que ya no existe, el detalle avisa y pide pasarlo a Uso directo.
- Maestro (`admin_maestro_eliminar` en app.py): Logística también puede borrar un código (`ROLES_ELIMINAN_MAESTRO_ESTRICTO`), solo si tiene
  stock 0 en los dos inventarios, ningún ingreso ni salida (solo el Saldo Inicial en 0) y ningún conteo. Para TODOS los roles se bloquea si
  el código está en una OC activa. Si está en requerimientos pendientes se borra igual: quedan escritos y reciben un aviso en su historial.

## Compras: numeración al guardar (varios usuarios a la vez)

- El número de una OC/OS se asigna AL GUARDAR (`_siguiente_numero_oc` = mayor número de esa empresa y tipo + 1, índice único
  `uq_orden_compra_emp_tipo_num`). Si dos usuarios guardan en el mismo instante, `_oc_guardar_datos` reintenta solo (3 veces) con el
  siguiente libre. Si aun así falla, vuelve a mostrar el formulario CON lo escrito y un mensaje claro (`_oc_error_unico` distingue
  "número ocupado" de otro dato repetido, con el detalle técnico).
- El formulario consulta cada 20 s (y con el botón ↻ junto al número) `/ordenes/siguiente-numero` (`oc_siguiente_numero`): si otro
  usuario registró una orden de la misma empresa y tipo, actualiza solo el número mostrado y avisa quién fue. No recarga ni borra nada.
  Al guardar, si el número que se veía (`numero_visto`) lo tomó otro, el mensaje final dice cuál le tocó y quién tomó el otro.
- Cambiar de empresa al editar: la orden toma el siguiente número libre de la otra empresa (empresa y número se cambian juntos antes
  de guardar; antes se guardaba la empresa nueva con el número viejo y chocaba → salía "Otro usuario registró una orden al mismo tiempo").

## Compras: rechazo parcial (Gerencia marca ítems a QUITAR)

- Al **Rechazar** una orden (detalle, modal `mRechazar`) Gerencia puede marcar, además del motivo general, los ítems que hay que
  **quitar** (llegó mal, se devuelve, no es lo pedido, precio incorrecto, ya no se necesita, otro; `MOTIVOS_QUITAR_ITEM`) con un detalle.
  El modal muestra en vivo el total actual, cuánto se quita y el **total sin esos ítems**. No se pueden marcar todos (sería rechazo total).
- Se guarda en `orden_compra_item.rechazo_quitar` / `rechazo_item_motivo`; `_oc_quitar_resumen(orden)` calcula ítems y montos
  (en proporción al subtotal: mismo % de IGV). Va en el evento RECHAZADA y en el aviso a Logística.
- Es una RECOMENDACIÓN: en la orden rechazada sale el recuadro con los ítems y montos y las filas tachadas con "QUITAR (recomendado)".
  Al "Corregir y volver a enviar" esos ítems NO se quitan solos: salen en rojo en el formulario (`quitar_rec` en `_orden_a_previo`) y
  Logística decide. Al guardar, el evento CORREGIDA dice cuántos se quitaron y cuáles se mantuvieron. En la lista: "Recomienda quitar N ítem(s)". (Queda la ruta `oc_duplicar` con `sin_rechazados=1`
  para hacer una copia con número nuevo sin esos ítems; ya no tiene botón.)

## Compras: corregir una orden RECHAZADA (misma orden, mismo número)

- Una OC/OS RECHAZADA la corrige Logística (`_oc_permisos` → `corregir`; bloqueada si `_oc_bloqueo_reedicion`): botón
  "Corregir y volver a enviar" → `oc_editar` (abre el formulario con el aviso rojo, el motivo del rechazo y los ítems recomendados en rojo).
  El bloqueo se revisa con `_oc_bloqueo_correccion` (pagada, ingresada, etc.; NO con `_oc_bloqueo_reedicion`, que es para aprobadas).
  Una ANULADA ya no se corrige. "Duplicar (número nuevo)" sigue disponible.
- Es obligatorio escribir "¿Qué corregiste?" (campo `motivo_edicion`, mín. 10 letras). Al guardar (`_oc_guardar_datos(..., correccion=True)`):
  `rechazo_previo` = foto del rechazo (motivo, quién, cuándo, ítems a quitar), `correcciones` + 1, `correccion_nota`,
  `correccion_pendiente = True`, evento CORREGIDA, y queda en BORRADOR o se ENVÍA a Gerencia.
- Gerencia lo ve como CORRECCIÓN mientras `correccion_pendiente`: recuadro en el detalle (por qué se rechazó, qué se corrigió, cambios),
  chip "Corrección" en la lista y en la campana, aviso en la aprobación rápida y título "CORREGIDA · ..." en la notificación.
  Al aprobar o volver a rechazar, `correccion_pendiente` vuelve a False (la aprobada muestra "Aprobada después de N corrección(es)").

## Kardex

- Salida con motivo que "Inicia una OC" (Catálogos → Motivos, ej. REQUERIMIENTO DE MAESTRANZA): por defecto **sale como VENTA**
  (no se abre proceso por OC). Pide el cliente; la OC del cliente y la Orden de Servicio son opcionales y se completan después
  desde el Kardex (lápiz). En el Kardex sale como VENTA y cuenta en los dashboards de ventas (toneladas).
  Filtros: `?oc_cliente=`, `?os=`, `?venta_srv=1`. Desmarcada, sigue el proceso por OC de siempre (salida → reingreso → venta final).
- **Eliminar un movimiento registrado por error** (botón "Eliminar" en la columna Usuario de los dos Kardex): Gerencia cualquiera;
  Jefe de Almacén (rol `almacen`) solo de los últimos 7 días (`DIAS_ELIMINAR_ALMACEN`). Pide motivo; revierte el stock (salida vuelve,
  entrada se descuenta) y corrige el saldo de los posteriores; no deja stock negativo. No se eliminan los de OC, proceso por OC, pedidos (NP-),
  inter-empresa, saldo inicial ni auditorías. Auditoría completa en "Movimientos eliminados".
- Borrar un código del Maestro: el "Saldo Inicial" (carga del Excel) no cuenta como movimiento; si es el único, se borra con el código.

## Avisos de Windows

- Quién recibe qué (`TIPOS_NOTIF` en `notificaciones.py`; cada usuario lo cambia en Campana → Configurar):
  Gerencia: OC/OS por aprobar. Logística: aprobadas, rechazadas, requerimientos nuevos.
  **Jefe de Almacén (rol `almacen`)**: solo `ING_PENDIENTE` (material conforme por ingresar al inventario y OS terminadas,
  "Ingresos pendientes (OC)") e `INSUMO_PENDIENTE` (compras de insumos internos conformes, "Pendientes de Orden de Compra",
  Anclajes o Import Bolts). Se crean al dar la conformidad (`oc_conforme`) o al cerrar el saldo (`_notif_por_ingresar`).
  Salen en la sección "Por ingresar" de la campana, calculada de las órdenes (`_notif_por_ingresar_json`): desaparecen
  solas al ingresarlo y se recuerdan cada X min mientras sigan pendientes. Su aviso de Windows se queda hasta cerrarlo.
- Página abierta: la campana (cada 30 s). Pestaña cerrada pero navegador abierto: Web Push (`push.py`).
- Navegador cerrado del todo / PC recién prendida: Programa de avisos (`agente.py`). Se instala en
  `%LOCALAPPDATA%\AvisosImportBolts` y arranca con Windows (acceso directo en la carpeta Inicio del usuario).
  No necesita administrador. Usa la misma configuración del usuario (tipos, recordar cada X min).

## Gráficos: base común (`templates/_graficos.html`) y plan de mejora

- Uso: `{% import '_graficos.html' as gr %}`, `{{ gr.estilos() }}`, `{{ gr.botones_moneda('grMoneda', 'PEN') }}` y al final
  `{{ gr.librerias() }}` (carga Chart.js 4.4.0 UNA vez y crea `window.GR`). Sin plugins externos: las etiquetas de valor
  (plugin propio `grEtiquetas`, formato en `dataset.grFormato`) y la línea de promedio / mejor precio se dibujan ahí mismo.
- Colores fijos: soles azul `#0B3D91`, dólares verde azulado `#0f766e`; verde = mejor / a tiempo, ámbar = alerta / ahorro,
  rojo = solo lo malo. Categorías sin significado con `GR.CAT` (sin rojo ni verde). Montos cortos "S/ 125 mil" (`GR.fmtCorto`).
- Funciones: `GR.barras` (columnas + promedio), `GR.barrasH` (top N + "Otros", valor y %, nombre completo en el tooltip, clic),
  `GR.historial` (fechas a su distancia real + línea del mejor precio), `GR.monedaGlobal` (botones S/ | US$ que redibujan todo),
  `GR.vacio` (mensaje "sin datos"). Cada canvas guarda su gráfico y se destruye antes de redibujar.
- Mejores precios (v16): resumen sin donas ni doble eje; moneda global; condición de pago por MONTO sin IGV (antes con IGV)
  y n° de órdenes en el tooltip; clic en un proveedor → vista "Por producto" filtrada por él (`res.prov_graf`).
- Más funciones (v17): `GR.mini` (mini tendencia de los KPIs), `GR.pareto`, `GR.proceso` (línea del proceso: mediana vs meta,
  rojo si pasa la meta), `GR.semaforo` (barra 100% por proveedor), `GR.burbujas` (matriz de riesgo con cuadrantes: `data.grCuadrantes`).
  En barras apiladas el valor va dentro del tramo (`dataset.grDentro`). Montos cortos propios: "850 · 12.5 mil · 1.2 M".
- Plan: Fase 3 (v18) precios finos (pesas, Pareto del ahorro, cascada precio/volumen,
  ahorro vs. compra anterior). Fase 4: dashboards de ventas / admin / insumos con esta base; PPV cuando exista precio estándar.

## Reportes de compras: tablero (`modulos/compras/reportes.py`, `templates/oc_reportes.html`)

- Cuentan las órdenes APROBADAS (aprobada, llegó, conforme) por FECHA DE LA ORDEN. Montos SIN IGV (`_oc_monto` = subtotal) igual que
  Mejores precios; `?igv=1` = con IGV. Soles y dólares nunca se suman: botones S/ | US$ redibujan los gráficos.
- Comparación ▲▼: periodos de 6 a 12 meses contra las mismas fechas del año anterior; periodos cortos contra el periodo anterior del mismo largo.
- FILTRO CRUZADO (`FILTROS_CRUZADOS_OC`): clic en una barra (proveedor, empresa, área, motivo, cliente, solicitante) recarga con
  `?prov=...` (etc.) y TODO el tablero queda filtrado (chips con ✕ para quitar). Clic en un mes = solo ese mes.
- Pestañas (se recuerdan con `#operativa`), cada una se dibuja al abrirse. Modo presentación: pantalla completa sin menú ni filtros.
- Ejecutiva: resumen accionable (`_oc_insights`: gasto vs anterior, Pareto 80%, OTIF, proveedor más atrasado con botón de filtro,
  paso fuera de meta, órdenes detenidas con botón "Aprobarlas / Verlas"), KPIs (gasto S/ y US$, órdenes, OTIF), gasto por mes,
  por empresa, Pareto de proveedores, área / motivo / cliente / solicitó, y tablas exactas plegables.
- Operativa: órdenes DETENIDAS AHORA (`_oc_detenidas`, no dependen del periodo): por enviar, por aprobar, esperando al proveedor
  (fuera de meta si pasó la fecha prometida), falta conformidad, falta ingresar al inventario; clic = ventana con las órdenes.
  Línea del proceso (mediana vs meta), semáforo (desde `MIN_ORDENES_RANKING_OC` = 3 órdenes juzgadas), matriz de riesgo
  (alerta desde `ATRASO_ALERTA_PCT_OC` = 25%), OTIF por motivo y tabla de tiempos.
- OTIF (`_oc_otif_orden`): llegó TODO (sin saldo cerrado) a más tardar en la fecha prometida; las que aún están en plazo no se juzgan.
  Motivos: ok / tarde / incompleto / no_llego.
- Metas por paso: `METAS_PASOS_OC` (días); se pueden cambiar con SystemConfig `oc_metas_pasos` = JSON (p. ej. {"enviada_aprobada": 2}).
- Entregas de muchas órdenes en 2 consultas (`_oc_entregas_de`). Excel: gasto, atrasos, OTIF, tiempos con meta, detenidas y órdenes.

## Pruebas (en el entorno de Claude)

- `test/oc/test_oc.py` (compras, requerimientos, avisos, push) y `test/insumos/test_insumos.py`:
  cargan los archivos de `modulos/` en el mismo orden que `app.py`, con una base de datos simulada.
- Revisión visual con un navegador automático sobre un servidor de demostración.

## Subir cambios

```
git add .
git commit -m "..."
git push
```
Render vuelve a desplegar solo. Los archivos nuevos de `modulos/` tienen que subirse (con `git add .` se incluyen).
