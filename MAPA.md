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
    modelos.py           tablas: Insumo, InsumoStock, ingresos, salidas, movimientos, documentos...
    base.py              empresas, permisos (_ruta_insumos), tablas, stock por moneda (S/ y US$), funciones comunes
    inventario.py        inventario por empresa, importar Excel, maestro de insumos, proveedores de insumos
    movimientos.py       ingresos (factura / desde OC), salidas (PDF y firma), kardex valorizado
    gasto_config.py      gasto por área, configuración, ajuste del costo promedio, vaciar el módulo
  compras/             ÓRDENES DE COMPRA / SERVICIO y REQUERIMIENTOS
    modelos.py           tablas: OrdenCompra, OrdenCompraItem, entregas, eventos, documentos, proveedores,
                         cuentas, motivos, requerimientos, OCConfig
    base.py              roles (ROLES_OC_*), empresas, catálogos, tablas, permisos (_ruta_oc), numeración,
                         _leer_orden_form (validación e IGV), recepción (_oc_recepcion) y pagos
    ordenes.py           lista, Excel y reportes, precios por proveedor, crear/editar, detalle y flujo
                         (enviar, aprobar, rechazar, anular, observación)
    entregas.py          llegadas totales/parciales, conformidad, pago y factura, cuentas bancarias,
                         cliente, ingresos pendientes al inventario e ingreso al Kardex
    pdf_proveedores_config.py   PDF de la orden, proveedores y contactos, buscador de productos, configuración
    requerimientos.py    requerimientos de compra (Inventario General o Insumos internos), seguimiento, novedades
    vaciar_menu.py       vaciar datos de órdenes (pruebas) y los números del menú
  avisos/              CAMPANA Y AVISOS
    modelos.py           Notificacion, NotificacionConfig, PushSuscripcion
    notificaciones.py    tipos de aviso, configuración por usuario, API de la campana, aprobación rápida
    push.py              aviso de Windows con la página cerrada (Web Push, /sw.js)
templates/             plantillas (todas en una carpeta; prefijos: oc_*, insumos_*, notificaciones, _campana...)
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
- Requerimientos: los crean admin, logistica, almacen y almacen_visor; los atienden admin y logistica.
- Insumos: editan admin, almacen y logistica.

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
