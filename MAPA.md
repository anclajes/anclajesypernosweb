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
    herramientas.py      HERRAMIENTAS (activos, v30): registro por unidad, préstamo/devolución con firma, baja aprobada (ver "## Insumos: inventario General…")
    revertir.py          REVERTIR desde el Kardex de insumos (v31): ingresos, salidas, cargas Excel y "pasó a herramientas" (ver "## Insumos: revertir…")
    tableta.py           TABLETA DE ALMACÉN (v37): trabajadores piden insumos con su PIN; Almacén entrega (ver "## Tableta de almacén")
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
    en_camino.py         EN CAMINO (Gerencia, Logística y Almacén desde v35): en los inventarios de Anclajes, Import Bolts e Insumos, por producto,
                         lo que viene en OC aprobadas (en camino / llegó / por sumar / sumado hace X días) y la línea de tiempo
    entregas.py          llegadas totales/parciales, conformidad, pago y factura, cuentas bancarias,
                         cliente, ingresos pendientes al inventario e ingreso al Kardex
    uso_directo.py       USO DIRECTO (/ordenes/uso-directo): bienes que no van a ningún inventario (PC, muebles...):
                         registrar / corregir la entrega (a quién, dónde, serie y garantía) y el registro con Excel
    duplicados.py        POSIBLES ÓRDENES DUPLICADAS: en vivo en el formulario, aviso en detalle/lista, "No es duplicada", "Anular por duplicada"
    movilidad.py         PLANILLA POR GASTO DE MOVILIDAD por OC/OS (/ordenes/<id>/movilidad/nueva, /ordenes/movilidad):
                         crear/editar, firma en pantalla u hoja firmada, anular, PDF (pdf_movilidad.html) y lista del mes
    certificados.py      CERTIFICADOS POR SUBIR (/ordenes/certificados): importaciones sin certificado de calidad
                         (el certificado es opcional: nunca frena la conformidad ni el ingreso)
    pdf_proveedores_config.py   PDF de la orden, proveedores y contactos, buscador de productos, configuración
    vista_previa.py      v38: VISTA PREVIA de la orden SIN guardar (foto rápida / PDF / Excel) y EXCEL de una orden guardada
    requerimientos.py    requerimientos de compra (Inventario General o Insumos internos), seguimiento, novedades
    vaciar_menu.py       vaciar datos de órdenes (pruebas) y los números del menú
  kardex/              KARDEX (lo nuevo; el resto del Kardex sigue en app.py)
    modelos.py           tabla MovimientoEliminado (auditoría de movimientos eliminados)
    eliminar.py          ELIMINAR un movimiento registrado por error (Gerencia y Jefe de Almacén): revierte el stock, corrige
                         los saldos posteriores y guarda la copia en "Movimientos eliminados" (/kardex/eliminados)
    revertir_oc.py       REVERTIR EL INGRESO AL KARDEX de una OC (v28): lo pide Almacén, lo confirma Logística (ver "## Kardex")
    maestro_familias.py  MAESTRO · FAMILIAS (v29): "Nueva familia" sola (Category + CategoryImportBolts, máx. 50 letras, sin
    maestro_codigos.py   v36: CAMBIAR CÓDIGO de un producto y ver DÓNDE QUEDA en el orden de su familia (ver "## Maestro: códigos y orden")
    novedades.py         v33: PRODUCTOS NUEVOS (Maestro, últimos N días, si ya llegaron) y ÚLTIMAS SALIDAS (Gerencia y Vendedores) (ver "## Novedades del inventario")
                         repetir ignorando mayúsc./espacios) y "Pasar a otra familia" de los productos marcados con los checks del
                         catálogo (misma selección en localStorage que "Imprimir códigos"; máx. 500): cambia MaestroProducto.familia,
                         Product.categoria y ProductImportBolts.categoria, con MaestroCambioLog campo 'familia' (lote FAM-...).
                         Global `maestro_familias_conteo()` (familias con cuántos productos; 0 = vacía). UI en admin_maestro.html.
                         v29.1: mientras se escribe busca familias PARECIDAS (JS famParecido: sin acentos/puntos, palabras
                         en común, errores de tipeo) y bloquea la igual; el servidor compara con `_familia_norm`. "Pasar a otra
                         familia" muestra la familia de ORIGEN (`admin_maestro_familia_origen`) y "De: X ➜ A: Y".
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
- Mejores precios: solo `ROLES_OC_VEN` (admin, logistica, administracion). En camino: `ROLES_EN_CAMINO` = admin, logistica, almacen (v35); Almacén no ve el enlace a la ficha de la OC (no tiene `ver`), sí el PDF y los documentos.

## Importaciones

- Precio por pieza (USD/PCS, hasta 7 decimales) como la factura comercial; se guarda también el precio por 1000 piezas (derivado).
  Las órdenes antiguas (por 1000 piezas) ya tienen su precio por pieza en `precio_unitario`.
- Certificado de calidad: opcional. En importaciones queda "pendiente" (aviso en la orden y lista "Certificados por subir").
- Proveedor del exterior sin Tax ID: se guarda con un código temporal `SINTAXID001...` y se completa desde la orden
  ("Completar Tax ID"); se corrige también en sus órdenes.
- Requerimientos: los crean admin, logistica, almacen y almacen_visor; los atienden admin y logistica.
- Insumos: editan admin, almacen y logistica.

## Insumos: inventario General, salida de varias bolsas y Herramientas (v30)

- **Inventario General** = tercera "empresa" de Insumos (`EMPRESAS_INSUMOS['GENERAL']`, `EMPRESA_GENERAL`, logo `static/img/logo_general.png`):
  lo antiguo del almacén sin empresa ni precio conocidos. Mismo maestro, lotes PEPS y Kardex. Ingresos SOLO manuales o por Excel
  (`_empresa_bloqueo_ingreso`: nunca con OC; las pantallas de OC solo muestran `EMPRESAS_CON_OC`); proveedor, factura y precio opcionales
  (sin proveedor = `PROVEEDOR_DESCONOCIDO_INSUMOS`). Lo usan los mismos roles que editan Insumos (admin, almacen, logistica).
  Cuando queda en 0 se CIERRA (`insumos_general_cerrar`, `SystemConfig('insumos_general_cerrado')`): ya no acepta ingresos; solo Gerencia
  lo vuelve a abrir. Gasto por área tiene columna General.
- **Nueva salida sin elegir empresa** (`insumos_salida_form.html`): se busca el insumo (catálogo único con el stock de cada bolsa), cada
  línea elige "Sale de" (`empresa_linea[]`), con recomendación: General si tiene; si no, la empresa con más stock. Si no alcanza, botón
  para sacar el resto de otra bolsa (otra línea). `insumos_salida_guardar` crea UNA `InsumoSalida` por bolsa (su correlativo, costo y PDF),
  con la misma firma y el mismo `grupo` (columna nueva); el detalle muestra las "hermanas". Formularios viejos con `empresa=` siguen sirviendo.
- **Herramientas (activos)** (`modulos/insumos/herramientas.py`, tablas `herramienta` y `herramienta_movimiento`, plantillas `herramientas_*.html`,
  pestaña "Herramientas" en `_insumos_nav.html`): cada unidad con código HER-00001, empresa (incl. General), valor, compra, vida útil
  (`herr_vida`), garantía, serie y su OC (docs por `herramientas_doc_oc`, que Almacén puede abrir).
  · Alta a mano (`herramientas_nueva`, N iguales con sus series) o `herramientas_desde_insumos`: saca del stock de insumos (PEPS, Kardex
    concepto `A_HERRAMIENTAS`, no es consumo) y crea una por unidad con el precio de su lote, proveedor, factura y `orden_compra_id` del
    ingreso. En el inventario de insumos, los de categoría HERRAMIENTAS tienen botón 🔨; al ingresar una compra con herramientas sale aviso.
  · Estados `HERR_ESTADOS`: DISPONIBLE → ASIGNADA (prestar con firma, `herramientas_asignar`) → devolver con condición (`herramientas_devolver`,
    opción a reparación) / EN_REPARACION (`herramientas_reparacion`) / BAJA_PEDIDA (`herramientas_baja`, motivo + detalle + foto) → DE_BAJA
    (`herramientas_baja_resolver`: aprueba o rechaza ROLES_HERR_BAJA = admin, logistica; ellos pueden darla de baja directo). Aviso HERR_BAJA.
  · Historial en `HerramientaMovimiento` (firma / foto en S3, `herramientas_archivo`). "Vaciar datos" de Insumos también borra herramientas.
  · v32: `_herr_compra_de_lote(lote)` = ingreso, factura, OC (también la de ingresos antiguos, buscada por `insumo_ingreso_id`) y documentos
    (del ingreso `InsumoDocumento` + de la OC). "Pasar desde insumos" muestra debajo de cada insumo de qué compra(s) sale (PEPS, precio, factura,
    OC, n° de documentos, aviso si va sin precio o si la unidad es CAJA/JGO = 1 herramienta). La ficha muestra el ingreso y sus documentos.
    `_poner_precio_lote` (base.py) también actualiza el movimiento A_HERRAMIENTAS y el `valor` de las herramientas de ese lote (si no tenían
    o seguían con el precio anterior; si se editó a mano no se toca).
- IDEA GUARDADA (no hecha, a pedido del usuario): "unidades de inventario" en el carrito de la OC (no sale en la OC: 3 CAJAS → entran 18 UND,
  precio por unidad convertido; copia la cantidad por defecto; Almacén corrige al ingresar si llega incompleta con nota; recordar la
  equivalencia por insumo). Primero insumos y herramientas. Por ahora Logística pone siempre unidades finales.

## Tableta de almacén (v37, modulos/insumos/tableta.py)

- Usuario con rol **'tableta'** ("Tableta de almacén" en Usuarios): al ingresar va a `/tableta`; `session.permanent` (cookie 400 días,
  `PERMANENT_SESSION_LIFETIME`), NO se cierra por inactividad (`_control_sesion` en app.py lo salta) y `_restringir_tableta` solo le deja
  `RUTAS_TABLETA`. Gerencia lo puede cerrar a distancia como a cualquiera (sesion_version).
- `insumos_tableta.html` (página sola, sin base.html, todo grande): ¿quién eres? (tarjetas con iniciales, buscador y letras) → PIN de 4
  (teclado) → materiales (categorías, buscador, Disponible/Agotado; sin HERRAMIENTAS) → cantidades con +/−, motivo y área → enviar.
  v37.2: la tableta solo dice "Ingresa tu clave" (no menciona el DNI). Atajos arriba de las categorías: ⭐ "Lo que siempre pides"
  (lo que más sacó ese trabajador en 120 días) y 🔥 "Más pedidos" (`_insumos_frecuentes`: salidas + pedidos de 60 días); al buscar se busca en todo.
  v37.4 FIRMA: paso "Firma aquí con tu dedo" (static/js/firma.js) antes de enviar; Insumos → Configuración → pestaña Tableta:
  Obligatoria / Opcional / No pedir (SystemConfig 'insumos_tableta_firma', `_firma_tableta`). Se guarda en S3 (`InsumoPedido.firma_s3_key`)
  y al entregar se COPIA a cada salida (`_pedido_marcar_entregado`) → sale en el PDF. El globito y "Pedidos tableta" dan el PDF de la salida.
  Sin tocar 90 s vuelve al inicio. API: `tableta_datos`, `tableta_entrar` (PIN; 5 fallos = bloqueo 10 min), `tableta_pedido`
  (session['tab_t'] vale 10 min), `tableta_cancelar`, `tableta_salir`.
- PIN (`InsumoTrabajador.pin_hash`, `pin_fallos`, `pin_bloqueo_hasta`): si no tiene uno propio, los 4 primeros dígitos de su DNI/código
  (`_pin_por_defecto`). Se pone/quita en Insumos → Configuración → Trabajadores (columna "PIN tableta").
- `InsumoPedido` / `InsumoPedidoItem` (PENDIENTE / ENTREGADO / RECHAZADO / CANCELADO): NO descuentan stock.
- Almacén / Logística / Gerencia: globito abajo a la izquierda (`_pedidos_tableta_widget.html`, en base.html; consulta cada 30 s, sin
  sonido). "Entregar" (`insumos_pedido_entregar`) arma un MultiDict y llama a `_salida_insumos_crear` (movimientos.py: el núcleo de la
  Nueva salida, sacado de `insumos_salida_guardar`) con el inventario recomendado por línea (`_bolsa_para`: General si alcanza, si no la
  empresa con más stock que alcance). "Revisar" = `insumos_salida_nueva?pedido=` con todo cargado (pedido_id oculto → al guardar queda
  ENTREGADO, `_pedido_marcar_entregado`). "Rechazar" con motivo. Lista: `insumos_pedidos` (chip "Pedidos tableta" en el menú de Insumos).

## Compras: vista previa, Excel y stock al duplicar (v38, modulos/compras/vista_previa.py)
- Formulario de la orden → "Vista previa del PDF" / "Excel": arma la orden EN MEMORIA con lo escrito (`_oc_desde_form` usa
  `_leer_orden_form`, que solo lee) → NO guarda nada y NO gasta número. Ruta POST `oc_vista_previa` (formato_vista = html | pdf | xlsx).
  html = la misma plantilla pdf_orden_compra.html vista en el navegador (`vista_html=True`: se dibuja como hoja A4; en el celular se
  achica para que entre de ancho) dentro de un modal; "Abrir PDF real" = xhtml2pdf igual que oc_pdf. Si faltan datos, igual se arma y
  muestra arriba "Al guardar te pedirá corregir: …".
- NÚMERO: orden nueva sin guardar → N° AAAA-00000 + franja azul "VISTA PREVIA … el N° se asigna al guardar" (`vista_previa` en la
  plantilla). Editando → su número real (si cambia de empresa: 00000, porque al guardar toma el siguiente de la otra). Al guardar
  se toma el correlativo como siempre (`_siguiente_numero_oc`), así la vista previa nunca deja huecos.
- Excel de una orden guardada: GET `oc_excel` (/ordenes/<id>/excel, permiso 'docs' como el PDF), botón "Excel" en el detalle y en
  el menú 📎 de documentos. `_oc_excel_bytes(o, empresa, firma, banner)` = mismo contenido del PDF (logo, RUC/tipo/N°, proveedor,
  ítems, totales/detracción, condiciones, términos, horario, firma si está aprobada), A4 vertical ajustado a 1 hoja de ancho.
  Importación: columnas QUANTITY / KGS/1000PCS / TOTAL KGS / USD/PCS / AMOUNT/USD y condiciones de pago con %.
- DUPLICAR / EDITAR: `_stock_actual_items` (ordenes.py, desde `_orden_a_previo`) pone en cada ítem el stock de HOY
  (insumos: stock/mínimo/costo de la empresa de la orden; productos: stock Anclajes / Import Bolts) y oc_form.html lo pasa a
  `vincular()`. Antes salía 0 (y "por reponer") porque el ítem precargado no traía stock.

## Maestro: códigos y orden (v36, modulos/kardex/maestro_codigos.py)

- Los códigos ordenan todas las listas; dentro de una familia van por medida (ej. P18128I400A 5/8"×4 1/2" → P18128I420A 5/8"×5").
- Botón <i>upc</i> "Cambiar código" en cada fila del Maestro (`_maestro_cambiar_codigo.html`) → `admin_maestro_cambiar_codigo`:
  `_cambiar_codigo_maestro` cambia MaestroProducto, Product, ProductImportBolts, la sombra `IBT-` (+ `shadow_origen_sku`), ítems de OC
  (`codigo` / `sku_ingreso`, solo los que no son insumo), entregas, requerimientos, MaestroCambioLog y MovimientoEliminado; añade un log
  campo='codigo'. Kardex, ventas y fotos van por id: no se tocan. Bloquea si el código ya existe en cualquier lado.
- Vista previa en vivo (`_maestro_codigo_pos.html` + `/api/maestro/codigo/posicion`, `_codigo_posicion`): vecinos de arriba/abajo con la
  medida leída de la descripción (`_medidas_desc`: "5/8\" X 8\"", "#10 X 3/4", "M10 X 50"), avisos (no sigue el formato de la familia
  `_forma_codigo` A/9, queda al final, la medida no encaja) y un código libre sugerido entre los vecinos por medida (`_codigo_entre`).
  También en "Nuevo producto" (y pide confirmar al crear si hay avisos). Placeholder "PER-005" quitado.
- "Revisar orden" (`/admin/maestro/orden?familia=`): la familia por código con su medida; marca en naranja las que tienen medida menor que
  la anterior de su calidad o código con otro formato.

## Kardex: eliminar movimientos (v36)
- El Jefe de Almacén elimina los REGISTRADOS en los últimos 7 días aunque tengan fecha anterior (`_registrado_hace_poco`: id ≥ al primer
  movimiento con fecha de los últimos 7 días). Gerencia, cualquiera. Si solo lo puede Gerencia, sale "🔒 solo Gerencia" con el motivo.

## Buscador de órdenes de compra (v34, modulos/compras/ordenes.py → oc_lista)

- El buscador también busca por **código del ítem** (SKU / código de insumo, `codigo` y `sku_ingreso`), detalle, familia y calidad
  (`_oc_item_busqueda_txt`, `_oc_busqueda_txt`). Coincide aunque se escriba sin guiones ni espacios (`_busqueda_compacta`: PER0001 = PER-0001).
- Con búsqueda sale una franja con en qué pestañas hay órdenes que coinciden (`busq_vistas`) + "Ver todas juntas" / "Buscar en las dos
  empresas"; y en cada orden, debajo del proveedor, el/los ítem(s) que coincidieron (`items_match`).

## Novedades del inventario (v33, modulos/kardex/novedades.py)

- Botón "✨ Nuevos" en Inventario Anclajes, Import Bolts y General (con el numerito de cuántos ya llegaron en 30 días,
  `n_productos_nuevos(inv)` del context processor) → `/inventario/nuevos?inv=&dias=&ver=`: productos de `MaestroProducto` creados en
  los últimos N días (sin los de origen "backfill") y, por inventario, su stock y su 1er ENTRADA (fecha, cantidad, motivo, proveedor,
  referencia) + total ingresado. Filtros: Ya llegaron / Creados sin ingreso / Todos. El visor de inventario también lo puede ver.
- "Últimas salidas" (`_salidas_widget.html`, incluido en base.html junto a la campana) solo para `ROLES_SALIDAS_RECIENTES` = admin y
  vendedor: botoncito con numerito de las salidas no vistas (lo visto se guarda en localStorage por usuario), SIN sonido ni ventanas.
  Consulta `/api/salidas/recientes` cada minuto solo con la pestaña visible. "Ver más" → `/salidas/recientes` (1–30 días, empresa, búsqueda).
  Sin productos "sombra" (IBT-). El cliente y quién registró solo los ve Gerencia (entre vendedores no se muestran los clientes).

## Insumos: revertir movimientos del Kardex (v31)

- Botón "↩ Revertir" en cada fila del Kardex de insumos (Anclajes, Import Bolts y General) para **Gerencia, Logística y el Jefe de Almacén**
  (`ROLES_INSUMOS_REVIERTEN` en base.py). Sirve para errores: inventario o ítem equivocado, carga Excel mal hecha, algo que no era herramienta.
  El botón pregunta primero (`GET /insumos/kardex/movimiento/<id>/revertir`, JSON de `_plan_revertir_mov`) qué va a pasar o **por qué no se
  puede** (`_usos_lote_txt` dice qué salidas / ajustes sacaron del lote, para revertirlos antes); luego POST con motivo (mín. 5 letras).
  · COMPRA → anula el INGRESO completo (`_anular_ingreso` en movimientos.py, exige el lote completo; si vino de OC la orden vuelve a
    "Ingresos pendientes" con evento en la OC). CONSUMO → anula la SALIDA (`_anular_salida`; si fue de varias bolsas solo la de esa bolsa).
  · IMPORTACION entrada → lote ANULADO (si está completo); IMPORTACION salida → vuelve al mismo lote; A_HERRAMIENTAS → borra esas herramientas
    (`_herr_de_mov`: mismo insumo, lote y `fecha_creacion`; solo si siguen DISPONIBLE y sin préstamos) y vuelve al lote.
    Se registra un movimiento ANULACION con `anula_mov_id` (columna nueva) → el original y su reversión no cuentan en los totales.
  · No se revierten: VALORIZACION / AJUSTE_COSTO (el precio se corrige en el lote) ni las anulaciones. General cerrado: no se le devuelve stock.
- Los botones "Anular" del detalle de ingreso y de salida ahora también los ven Logística y Almacén (antes solo Gerencia).

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
- Ingresos pendientes de OC (`/insumos/pendientes-oc`, `_ordenes_pendientes_insumos`, contador global `n_oc_pendientes_insumos()`):
  se ven en el MENÚ LATERAL (badge rojo en "Insumos Internos" aunque esté cerrado + opción "Ingresos pendientes (OC)"), en la pestaña
  del módulo y con un aviso amarillo "N compras de insumos llegaron… Ingresarlas" arriba de todas las pantallas de Insumos.
  v29.2: también hay viñeta "Ingresos pendientes (Insumos)" en la barra de Órdenes de compra (`_oc_nav.html`, `oc_ins_emp` del context
  processor `_contador_ordenes` en vaciar_menu.py; abre la empresa con más pendientes).
- BARRA "POR HACER EN ALMACÉN" (solo rol `almacen`, `ROLES_BARRA_PENDIENTES` en vaciar_menu.py): arriba de TODAS las páginas
  (`templates/_barra_pendientes.html`, incluida en base.html debajo de la cabecera) con "Ingresos pendientes (OC)" (material, servicios,
  uso directo, contables) e "Insumos internos · Pendientes de OC", con el número por empresa (cada uno lleva a su pantalla).
  Datos: `_pendientes_almacen()` (context processor `pend_alm`; también da `oc_por_ingresar`) y `/almacen/pendientes/api` (cada minuto).
  Aviso de NUEVO: compara los ids pendientes (`oc_ids` / `ins_ids`) con los ya vistos (localStorage por usuario): late en rojo con
  "¡NUEVO!" hasta que hace clic o entra a esa pantalla. La primera vez no avisa de lo que ya había.
- La OC de cada ingreso se guarda en `insumo_ingreso.orden_compra_id` (los antiguos se encuentran por `orden_compra.insumo_ingreso_id`).
  Kardex, Ingresos y el detalle muestran la OC (PDF) y todos sus documentos con ver/descargar. Menú reutilizable: `templates/_oc_docs_menu.html`.
- `_oc_docs_menu.html`: `menu_docs_oc(o, docs, texto, icono, clase)` = la orden + sus documentos, cada uno con **Abrir** (pestaña nueva)
  y **Descargar**; `menu_archivo(etiqueta, url_ver, url_bajar, icono, formato, clase, cab)` = menú de UN archivo ("Abrir en una pestaña
  nueva" / "Descargar"; con `{% call %}` se agregan acciones, p. ej. "Quitar documento"). Kardex Anclajes e Import Bolts (columna
  Motivo / Referencia) usan los dos: el chip de la OC ya no descarga el PDF de golpe.
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
- Ingresos pendientes (`oc_ingresos.html`): cada tarjeta (de cualquier tipo) empieza con la FRANJA DE LA EMPRESA (logo + nombre completo +
  "entra al inventario de…" / "uso directo…") y quién CREÓ la orden. Uso directo: fichas iguales (categoría, va a, para qué, solicitó,
  ítems, activo fijo) y el formulario a todo el ancho: `campos_entrega_directo` = a quién / dónde / nota en una fila + TABLA de ítems
  (queda en, N° de serie, garantía con menú +6m/+1/+2/+3 años); con más de 6 ítems la tabla tiene scroll y cabecera fija; en celular
  cada ítem es una tarjeta. Lo entregado: `tabla_entrega_directo`.
  "Entregado a" es una LISTA como "Solicitó" (`_directo_responsables(o)`, uso_directo.py): viene elegido quien lo solicitó (+ área),
  luego las cuentas del sistema y los "Encargados (uso directo)" de Configuración (catálogo `OC_DIRECTO_RESPONSABLE`), y "Otra persona"
  para escribirlo. El botón ⚙ "Agregar encargado" lo guarda en ese catálogo sin salir (POST `/ordenes/uso-directo/encargado`,
  roles que entregan). El formulario manda `entregado_a_sel` (+ `entregado_a_otro`); se acepta aún `entregado_a`.
  Logo de la empresa: `empresa_pill(o)` (global `oc_empresas` = EMPRESAS_OC) en la ventana de entrega y en el Movimiento de Kardex.

## Compras: EN CAMINO en los inventarios (Gerencia, Logística y Almacén)

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

## Compras: DEVOLVER a Logística desde Ingresos pendientes (v25)

- Caso: la orden ya llegó y está conforme, pero al ir a ingresarla Almacén ve que no cuadra (cantidad, precio, producto).
  Botón "↩ Devolver a Logística (hay un error)" (`_oc_permisos` → `devolver`: rol en ROLES_OC_INGRESAN, no devuelta y `_oc_falta_ingresar`)
  en Ingresos pendientes (`oc_ingresos.html`), Insumos · Pendientes de OC (`insumos_pendientes_oc.html`) y el detalle de la orden.
  Modal (`templates/_oc_devolucion.html` → `modal`): qué está mal (MOTIVOS_DEVOLUCION_OC), explicación (mín. 10) y la cantidad REAL por ítem.
- `oc_devolver` (POST /ordenes/<id>/devolver): `devuelta_almacen=True`, `devolucion_motivo`, `devolucion_items` (JSON: oc / llegó / real / nota),
  `devuelta_por`, `fecha_devuelta`, `devoluciones`+1; evento DEVUELTA; aviso OC_DEVUELTA a Logística; se apagan sus avisos ING_PENDIENTE/INSUMO_PENDIENTE.
- Mientras está devuelta queda BLOQUEADA: fuera de `_entregas_por_ingresar`, `_contables_por_confirmar`, `_os_por_seguir`, `_directos_por_entregar`,
  `_oc_pendiente_insumos`, `_ordenes_pendientes_insumos` y de los contadores; `oc_item_ingresar`, `oc_kardex_ingresar` y `oc_os_seguimiento`
  revisan `_oc_bloqueo_devuelta`; permisos ingresar/insumos/confirmar_contable/entregar_directo = False. En Ingresos pendientes se ve con
  banner rojo y sin botones (`.oc-card.devuelta`), y arriba la lista "Devueltas a Logística para corregir" (en qué está cada una).
  La barra de Almacén muestra "N devuelta(s) a Logística" (`_pendientes_almacen()['dev']`).
  En Órdenes de compra: pestaña "↩ Devueltas por Almacén" (vista `devueltas` en VISTAS_OC_ORDEN/VISTAS_OC_EXTRA; `en_vista` usa
  `devuelta_almacen`), late en rojo si hay alguna, más la tarjeta KPI "Devueltas por Almacén" y un recuadro con motivo y en qué está cada una.
- Historial (v27.7): Ingresos pendientes → pestaña "Devueltas (historial)" (vista `devueltas` de `oc_ingresos_pendientes`).
  `_oc_devueltas_historial(emp)` (entregas.py): toda orden con `devoluciones > 0` (máx. DEV_HIST_LIMITE), sus ciclos desde los eventos
  DEVUELTA → DEVOLUCION_RESUELTA (motivo, quién, cuándo, cómo se corrigió, en cuántos días) y el resultado `_dev_hist_resultado`
  (DEV_HIST_ESTADOS: sigue en Logística / regresó · falta ingresar / ingresada en parte / regresó y se sumó / anulada / rechazada).
  Plantilla: macro `historial` de `_oc_devolucion.html` (recuadros-filtro + buscador).
- Logística (banner con acciones en el detalle, `banner` + `modales_logistica`):
  · Error en la ORDEN → "Editar la orden" (`reeditar`, vuelve a Gerencia; `oc_editar` precarga el motivo "Corrección pedida por … (Almacén)").
    Gerencia ve "corrección pedida por Almacén" en la notificación y el banner. `oc_aprobar` llama `_oc_devolucion_cerrar(orden, 'REAPROBADA')`.
    Con la orden devuelta se puede BAJAR la cantidad por debajo de lo registrado como llegado (mínimo: lo ya ingresado al inventario;
    `_leer_orden_form`): al guardar, `_aplicar_datos_orden` ajusta solo las entregas (última primero, sin tocar lo ingresado; borra las que
    quedan vacías) y deja el evento ENTREGA_CORREGIDA. Ej.: OC 3,000 registrada como llegada 3,000, real 1,820 → se edita a 1,820 y listo.
    v28.3: vale para CUALQUIER re-edición (devuelta o no) y también para QUITAR un ítem registrado como llegado: lo que manda es lo
    INGRESADO al inventario (no se quita ni se baja de eso; si se ingresó por error → "Revertir ingreso al Kardex"), no lo registrado como
    llegado (a veces se avanza el flujo sin contar). Al quitarlo, `_aplicar_datos_orden` borra sus entrega-ítems ("se quitó de la orden …").
  · Error en lo que se registró que LLEGÓ → "Corregir lo que llegó" (`oc_entrega_corregir`, POST /ordenes/entrega/<id>/corregir): solo ítems
    sin ingresar, tope = pedido − cancelado − lo de otras entregas; 0 quita el ítem; entrega vacía se borra (sus docs quedan sin entrega);
    recalcula estado con `_oc_etapa_por_entregas`; evento ENTREGA_CORREGIDA. No va a Gerencia.
  · "Listo, devolver a Almacén" (`oc_devolucion_resolver`, nota obligatoria) → `_oc_devolucion_cerrar(orden, 'LISTA', nota)`.
  Cerrar = `devuelta_almacen=False`, evento DEVOLUCION_RESUELTA y aviso OC_DEVOLUCION_LISTA a Almacén. Se conserva todo el historial.

## Compras: PLANILLA POR GASTO DE MOVILIDAD (v26) · `modulos/compras/movilidad.py`

- Tabla `orden_compra_movilidad` (modelo `OrdenCompraMovilidad`, se crea sola con `_asegurar_mov()`): una o varias por orden,
  en CUALQUIER estado. Una planilla = un trabajador + un día (fecha_gasto) + sus desplazamientos `filas` (JSON motivo/destino/monto).
- Empresa: por defecto la de la orden; se puede elegir la otra. Razón social, RUC y logo de `_oc_cfg(empresa)`; N° correlativo
  propio de cada empresa (`_mov_siguiente_numero`, formato `00-00015`). Creada, la empresa ya no se cambia (no deja huecos).
- No se borra: se ANULA con motivo (`oc_movilidad_anular`, admin/logística); el número no se reutiliza.
- Firma del trabajador: en pantalla (canvas `static/js/firma.js`, en el formulario o después `oc_movilidad_firmar`) o subiendo la
  hoja impresa y firmada a mano (`oc_movilidad_hoja`). Firmada = no se edita; para corregir: "Quitar firma" con motivo (`oc_movilidad_quitar_firma`).
  Todo queda en el historial de la orden (evento MOVILIDAD).
- Tope deducible: 4% de la RMV por trabajador y día (RMV en OCConfig `MOV_RMV`, defecto S/ 1,230 = D.S. 015-2026-TR; el admin la cambia
  desde el formulario, `oc_movilidad_rmv`). Solo AVISA (no bloquea); cada planilla guarda la RMV con que se hizo (`rmv`).
- Trabajador: "Elegir trabajador" = cuentas del sistema AGRUPADAS POR ROL (sin auditores: MOV_ROLES_FUERA) + "Otros trabajadores
  (sin cuenta)"; cada opción trae nombre y DNI guardados (✓). Tabla `oc_movilidad_trabajador` (modelo `OCMovilidadTrabajador`:
  nombre, dni, user_id opcional, cargo, activo). Botón "Guardar para la próxima" (`oc_movilidad_trabajador_guardar`) y ⚙ Trabajadores
  (modal: agregar / editar / desactivar, `oc_movilidad_trabajadores`, `oc_movilidad_trabajador_activo`). Al guardar una planilla, si
  su DNI no estaba guardado, se guarda solo. DNI por RENIEC (`oc_movilidad_dni`).
- APROBACIÓN del ENCARGADO (siempre Luis Carlos): campos aprobado_por_id/_nombre, fecha_aprobada, firma_aprob_s3_key (columnas con
  `_agregar_columnas_si_faltan`). Encargado = OCConfig `MOV_ENCARGADO` (el admin lo elige en 🚕 Movilidad; si no, la cuenta "Luis Carlos…",
  `_mov_encargado_id`, cache 60 s). Solo él aprueba (`oc_movilidad_aprobar`, también ve la lista y los PDF aunque su rol no sea de compras:
  `_ruta_mov(encargado=True)`). Se aprueba cuando el trabajador ya firmó; firma dibujada o la guardada (OCConfig `MOV_FIRMA_U<id>`,
  "Guardar mi firma" → luego un clic). Aviso arriba en todas las páginas (`mov_por_aprobar`, context processor) y filtro "Falta aprobación".
  Quitar la firma también quita la aprobación. PDF: "Firma del Trabajador" | "Aprobado por (Encargado)" con firma; "Elaborado por" abajo a la
  derecha, sin firma. Lista con mes=todos.
- Firma en pantalla (`static/js/firma.js` v2): "Borrar" limpia todo el lienzo también con zoom < 100% (antes quedaba la parte derecha/abajo).
- PDF `templates/pdf_movilidad.html` (formato del modelo + logo, referencia de la orden, total en letras, firma, base legal y nota).
- Vistas: panel "🚕 Planillas de movilidad" en el detalle (`_oc_movilidad.html` → `panel`) + botón arriba; en la lista de órdenes
  chip en Docs (`chip`: "🚕 n · S/ x", amarillo si falta firmar, "+ 🚕 Movilidad" si no tiene) y filtro Docs con/sin/sin firmar
  (`_mov_por_orden`); pestaña "🚕 Movilidad" en el menú de Órdenes = lista del mes por empresa (`oc_movilidad_lista`) con KPIs,
  excesos del tope, resumen por trabajador y "Ver todas en un PDF" (para contabilidad).
- Roles: ven/crean/editan/firman admin, logística, administración (`ROLES_MOV_VEN`); anulan y quitan firma admin, logística.
- PRUEBAS: en 🚕 Movilidad (solo admin) "Zona de pruebas: vaciar planillas" (`oc_movilidad_vaciar`, escribir BORRAR MOVILIDAD,
  las dos empresas o una): borra planillas de todas las fechas + firmas/hojas en S3 + sus eventos MOVILIDAD (`_mov_vaciar`); la
  numeración vuelve a 00-00001; no toca órdenes ni la RMV. "Vaciar datos del módulo" (oc_vaciar) también las borra (antes de las órdenes).

## Compras: POSIBLES ÓRDENES DUPLICADAS (v27) · `modulos/compras/duplicados.py`

- Solo se compara con órdenes del MISMO PROVEEDOR (RUC; si no hay, razón social) y no anuladas. Puntaje (`_dup_comparar`):
  misma factura +60 (`_dup_factura` → (serie, número); serie SUNAT completa = letras + número: F001 ≠ E001 ≠ FT01, sin ceros de relleno:
  F001-00003527 = F001-3527 = F0013527 = "Factura F001 N° 3527"; `_dup_misma_factura`: sin serie (FAC-0002555, 2555) o sin letras
  (001-2555 vs F001-2555) = mismo número +45; series distintas = otra factura),
  mismo monto +35 (parecido ±3% +15), mismos productos +30 (parecidos +15; `_dup_sim_items`: código o palabras, "5MT" = "5 MT"),
  misma empresa +5, misma semana +15 (≤30 días +8), +5 si se hizo con "Duplicar". Ventana DUP_VENTANA_DIAS = 90 días
  (más antiguas solo si coincide la factura, −15). Nivel (`DUP_NIVELES`): Alta ≥70, Media ≥45, Baja ≥25.
- En vivo en `oc_form.html` (`_oc_duplicados.html` → caja_form + js_form; API `oc_duplicados_revisar`, los totales los calcula
  `_leer_orden_form`). Para ENVIAR a Gerencia con nivel Alta: "Revisé: no es duplicada" + motivo ≥10 (`_dup_control_envio` en oc_guardar,
  y en el navegador); se guarda en `duplicado_revision` y evento DUPLICADO_REVISADO (Gerencia lo ve en el detalle).
- Detalle (`panel_detalle`, id #duplicados): aviso con las parecidas (Alta/Media), "No es duplicada" (`oc_duplicado_descartar`: el par se
  guarda en `duplicado_descartes` de las dos y deja de avisar) y, para Gerencia, "Anular ESTA por duplicada" / botón "Anular por duplicada".
- `oc_anular_duplicada` (Gerencia y Logística, `ROLES_ANULAN_DUPLICADA`): anula aunque esté aprobada/conforme si NO está pagada y no ingresó nada a Kardex ni Insumos
  (`_dup_bloqueo_anular`); la entrega de uso directo, la confirmación contable o el seguimiento de OS no lo impiden (no mueven inventario).
  anulacion_categoria = 'DUPLICADA', `anulada_duplicada_de_id` = la original; evento en las dos; sale de Por pagar.
- Lista: chip "⚠ ¿Duplicada? Alta/Media" junto al estado (al hacer clic: con cuál se parece, qué coincide, "Comparar lado a lado",
  "Ver ↗" y "No es duplicada" ahí mismo) y pestaña "⚠ Posibles duplicadas" (`_dup_mapa`, mira las dos empresas). Las anuladas por
  duplicada muestran "↪ duplicada de OC …" (mapeo `anulada_duplicada_de_id`); la original muestra en su detalle cuáles se anularon.
- RECHAZADAS y ANULADAS no avisan ni se comparan (`DUP_ESTADOS_FUERA`); si una rechazada se corrige, vuelve a contar.
- Comparar lado a lado: `oc_duplicados_comparar` (?ids=23,19,24 hasta DUP_COMPARAR_MAX = 6, o ?a=&b=; `oc_dup_comparar.html`):
  una columna por orden; se marca cuál es la CORRECTA (radio; rechazadas/anuladas no pueden serlo) y lo que coincide con ella sale en
  verde (datos `_dup_claves`, productos emparejados por código o descripción, razones por par). "Anular" (checkbox) en las que sobran →
  `oc_anular_duplicadas_varias` (todas o ninguna; usa `_dup_anular`, el mismo de `oc_anular_duplicada`). "No es duplicada de …" por columna.
  Desde la lista ("Comparar las N", `comparar_todas` en `_dup_mapa`) y el detalle ("Comparar las N juntas").
  Diseño (v27.5): usa todo el ancho (con 2 órdenes máx. 1400px), letra .9rem; en pantallas ≥1400px la cabecera queda fija al bajar.
  La barra "Motivo + Anular" va debajo de la tabla en una línea y solo se queda fija abajo (`.cmp-acc.fija`) cuando hay algo marcado.
- Por qué NO se puede anular (v27.6): `_dup_bloqueos_lista(orden)` (global `oc_dup_bloqueos`) da TODAS las razones con qué hacer y enlace
  (💰 pagada → la orden; 📦 sumada a Insumos → ingreso #N, que solo Gerencia anula si no se sacó nada; 🏭 ingresada al Kardex → entregas).
  `_dup_bloqueo_anular` sigue dando una frase (para mensajes). En comparar: fila "¿Se puede anular?" y "🔒 No se puede anular" en la cabecera;
  la correcta propuesta es la vigente que ya no se puede anular. En el detalle, el botón "Anular por duplicada — ¿por qué no se puede?" abre la
  ventana con las razones (sin botón de anular).

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
- **Revertir el ingreso de una OC** (v28, `modulos/kardex/revertir_oc.py`, plantilla `_oc_reversion.html`, tabla `oc_reversion_kardex`
  = OCReversionKardex): para una OC mal digitada (6 MT en vez de 1 UN) o DUPLICADA que ya sumó al Kardex.
  · Pide: ROLES_SOLICITAN_REVERSION (admin, almacen) desde Ingresos pendientes → "Ya ingresados" (botón en la tarjeta) o el detalle
    (`oc_reversion_solicitar`). Modo CORREGIR (ítems elegidos; la orden vuelve a Logística como DEVUELTA, entra al historial de devueltas)
    o DUPLICADA (todo; se elige la correcta y se anula con `_dup_anular` → mapeo). Vista previa del stock (`_rev_ingresados`, no deja si no alcanza).
    Mientras está PENDIENTE no cambia nada y `_oc_bloqueo_devuelta` impide ingresar más de esa orden. Aviso OC_REVERSION a Logística.
  · Confirma: ROLES_CONFIRMAN_REVERSION (solo logistica, por ahora) `oc_reversion_confirmar` (todo o nada): `_eliminar_mov_auditado`
    (eliminar.py, el mismo de "Eliminar") de cada movimiento → stock descontado, saldos posteriores corregidos, copia en MovimientoEliminado
    con `orden_compra_id` y `reversion_id`; quita la marca de ingresado (entrega-ítems e ítems, fecha_kardex). DUPLICADA pagada: no deja
    (Gerencia quita el pagado primero). `oc_reversion_rechazar` (Logística rechaza con nota; quien la pidió o Gerencia la cancela: cancelar=1).
  · Se ve: panel en el detalle y en la tarjeta de Ingresos (`rv.panel`), chip en la lista de OC ("Reversión por confirmar" /
    "Kardex revertido −6 SKU", `rv.chip` con `_rev_mapa` cacheado en `g`), eventos REVERSION_PEDIDA / REVERSION / REVERSION_NO, y en
    "Movimientos eliminados" la etiqueta "↩ Reversión de OC" + filtro `tipo=oc`. El Kardex ya no dice "deshacer" para los de OC: apunta aquí.
  · Desde los Kardex (v28.1): en cada ENTRADA de una OC (Anclajes e Import Bolts) `rv.kardex_link` muestra "↩ Revertir ingreso (OC)"
    (admin, almacen) o "Reversión por confirmar". Lleva a la página `oc_reversion_ver` (/ordenes/<id>/reversion, `oc_reversion.html`,
    roles de Ingresos): lo que entró, el pedido pendiente (Logística confirma ahí) o el formulario (se abre solo con ?abrir=1); ?desde= vuelve al Kardex.
    Los avisos OC_REVERSION / OC_REVERSION_LISTA llevan a esa página (Almacén no puede abrir el detalle de la OC).
  · Dónde lo ve Logística (v28.2): aviso amarillo arriba de TODAS las páginas ("N reversión(es) de ingreso al Kardex por confirmar",
    context processor `_rev_ctx` → `rev_por_confirmar`, en base.html) que lleva a la lista `oc_reversiones` (/ordenes/reversiones,
    `oc_reversiones.html`: pendientes con Confirmar/Rechazar + historial); también la campana (OC_REVERSION) y el link en Ingresos pendientes.
  · OJO modelos nuevos: app.py solo importa sus modelos; un módulo con modelo nuevo hace `from models import ...` arriba
    (v28 falló en producción por eso: NameError OCReversionKardex). `_asegurar_rev()` crea tabla/columnas al arrancar y reintenta
    en before_request (oc_reversion*, kardex_eliminar*, kardex_eliminados) si falló.

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
- Mejores precios · CONSULTA RÁPIDA POR ÍTEM (`vista=rapido`): para trabajadores y Gerencia. Buscador grande; por defecto solo lo
  comprado MÁS DE UNA VEZ (`todos=1` = todo). Una tarjeta por producto (moneda + U.M.): MEJOR PRECIO (verde, proveedor, fecha, empresa
  que compró, OC), ÚLTIMA COMPRA (▲ % más caro o ✔ al mejor precio) y "PARA LA PRÓXIMA COMPRA" (a quién pedir precio, cuánto más se pagó,
  ahorro posible). "Ver todas las compras" = ranking + tabla. Cada OC abre `menu_docs_oc(..., detalle_url=...)`: abrir la orden en el
  sistema, PDF (abrir / descargar) y sus documentos. Sin indicadores arriba. Producto: `compras` (más nueva primero) y `empresas`.
  Chips "Qué ver": Todo / Solo OC (sin servicios) / Solo servicios (OS) / Productos del inventario / Insumos / Uso directo (tipo + clase).
- Filtros FAMILIA, CALIDAD y CÓDIGO (inventario general o insumos) en todas las vistas de Mejores precios: select con buscador
  (`select.filtro-s2` + `static/js/filtros.js`, como en los inventarios): se elige o se escribe y busca por coincidencia sin tildes.
  Calidades y códigos según la familia elegida (`opciones_familia/calidad/codigo`).
- Mejores precios (v16): resumen sin donas ni doble eje; moneda global; condición de pago por MONTO sin IGV (antes con IGV)
  y n° de órdenes en el tooltip; clic en un proveedor → vista "Por producto" filtrada por él (`res.prov_graf`).
- Más funciones (v17): `GR.mini` (mini tendencia de los KPIs), `GR.pareto`, `GR.proceso` (línea del proceso: mediana vs meta,
  rojo si pasa la meta), `GR.semaforo` (barra 100% por proveedor), `GR.burbujas` (matriz de riesgo con cuadrantes: `data.grCuadrantes`).
  En barras apiladas el valor va dentro del tramo (`dataset.grDentro`). Montos cortos propios: "850 · 12.5 mil · 1.2 M".
- Plan: Fase 3 (v18) precios finos (pesas, Pareto del ahorro, cascada precio/volumen,
  ahorro vs. compra anterior). Fase 4: dashboards de ventas / admin / insumos con esta base; PPV cuando exista precio estándar.

## Órdenes de compra (lista): botón "🌐 Importaciones" (solo importaciones) y filtro "Importación" (todas / solo importaciones /
   solo nacionales) = parámetro `importacion=si|no`; se mantiene al cambiar de pestaña.

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
