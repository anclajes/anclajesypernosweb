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
    ordenes.py           lista (con aprobación rápida), Excel y reportes, crear/editar (incluye cambiar de empresa),
                         detalle y flujo (enviar, aprobar, rechazar, anular, observación)
    mejores_precios.py   MEJORES PRECIOS (/ordenes/precios, también el menú "Mejores Precios"): por producto, por proveedor,
                         detalle, gráficos, ahorro potencial y Excel con gráficos (productos, insumos y servicios)
    en_camino.py         EN CAMINO (solo Gerencia): en los inventarios de Anclajes, Import Bolts e Insumos, por producto,
                         lo que viene en OC aprobadas (en camino / llegó / por sumar / sumado hace X días) y la línea de tiempo
    entregas.py          llegadas totales/parciales, conformidad, pago y factura, cuentas bancarias,
                         cliente, ingresos pendientes al inventario e ingreso al Kardex
    certificados.py      CERTIFICADOS POR SUBIR (/ordenes/certificados): importaciones sin certificado de calidad
                         (el certificado es opcional: nunca frena la conformidad ni el ingreso)
    pdf_proveedores_config.py   PDF de la orden, proveedores y contactos, buscador de productos, configuración
    requerimientos.py    requerimientos de compra (Inventario General o Insumos internos), seguimiento, novedades
    vaciar_menu.py       vaciar datos de órdenes (pruebas) y los números del menú
  kardex/              KARDEX (lo nuevo; el resto del Kardex sigue en app.py)
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
                       _en_camino.html: panel, botones por producto y ventana de "En camino" (se usa en los 3 inventarios)
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

## Kardex

- Salida con motivo que "Inicia una OC" (Catálogos → Motivos, ej. REQUERIMIENTO DE MAESTRANZA): por defecto **sale como VENTA**
  (no se abre proceso por OC). Pide el cliente; la OC del cliente y la Orden de Servicio son opcionales y se completan después
  desde el Kardex (lápiz). En el Kardex sale como VENTA y cuenta en los dashboards de ventas (toneladas).
  Filtros: `?oc_cliente=`, `?os=`, `?venta_srv=1`. Desmarcada, sigue el proceso por OC de siempre (salida → reingreso → venta final).
- Borrar un código del Maestro: el "Saldo Inicial" (carga del Excel) no cuenta como movimiento; si es el único, se borra con el código.

## Avisos de Windows

- Página abierta: la campana (cada 30 s). Pestaña cerrada pero navegador abierto: Web Push (`push.py`).
- Navegador cerrado del todo / PC recién prendida: Programa de avisos (`agente.py`). Se instala en
  `%LOCALAPPDATA%\AvisosImportBolts` y arranca con Windows (acceso directo en la carpeta Inicio del usuario).
  No necesita administrador. Usa la misma configuración del usuario (tipos, recordar cada X min).

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
