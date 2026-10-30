# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · base
# roles, empresas, catálogos, tablas, permisos, numeración, lectura y validación del formulario de la orden, recepción y pagos
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# =====================================================================================
# ÓRDENES DE COMPRA (OC) Y ÓRDENES DE SERVICIO (OS) — módulo de Logística
# Flujo:  BORRADOR (Logística la arma; PDF con "PENDIENTE DE APROBACIÓN")
#         -> ENVIADA a Gerencia -> APROBADA (el PDF lleva firma y sello) / RECHAZADA (el PDF dice RECHAZADA)
#         -> RECIBIDA (Logística registra la llegada + guía/factura) -> CONFORME (check verde: estado,
#            cantidad y documentos OK) -> queda en "Conformes / en almacén".
#         Se puede ANULAR (con motivo) mientras el material no haya llegado. La numeración es correlativa
#         por tipo (OC N° 2026-00001, OS N° 2026-00001) y un número anulado no se reutiliza.
# Precios: se ingresan SIN IGV; el sistema calcula IGV 18% y el total.
# Las tablas se crean solas al arrancar (no hace falta ninguna ruta /fix_).
# =====================================================================================
ROLES_OC_EDITAN = ['admin', 'logistica']
ROLES_OC_VEN = ['admin', 'logistica', 'administracion']
ROLES_OC_APRUEBAN = ['admin']
ROLES_OC_INGRESAN = ['admin', 'logistica', 'almacen']      # marcan el ingreso del material al inventario
ROLES_REQ_CREAN = ['admin', 'logistica', 'almacen', 'almacen_visor']   # piden productos que faltan (requerimientos de compra)
ROLES_REQ_VEN = ['admin', 'logistica', 'almacen', 'administracion', 'almacen_visor']
ROLES_REQ_ATIENDEN = ['admin', 'logistica']                # arman la OC con lo pedido o rechazan el requerimiento
ROLES_OC_PAGAN = ['admin', 'logistica', 'administracion']  # marcan la orden como pagada y guardan cuentas bancarias
ROLES_SOLICITANTES_OC = ['admin', 'administracion', 'vendedor', 'logistica', 'almacen', 'almacen_visor']   # cuentas que pueden figurar como "solicitó"
AREA_POR_ROL_OC = {'admin': 'GERENCIA', 'administracion': 'ADMINISTRACIÓN', 'vendedor': 'VENTAS', 'logistica': 'LOGÍSTICA', 'almacen': 'ALMACÉN', 'almacen_visor': 'ALMACÉN'}
DIAS_AVISO_PAGO = 5            # "por vencer": faltan 5 días o menos
BANCOS_OC = {'BCP': {'nombre': 'BCP', 'logo': 'bcp.png', 'color': '#002a8d'},
             'INTERBANK': {'nombre': 'Interbank', 'logo': 'interbank.png', 'color': '#05be50'},
             'SCOTIABANK': {'nombre': 'Scotiabank', 'logo': 'scotiabanck.png', 'color': '#ec111a'},
             'BBVA': {'nombre': 'BBVA', 'logo': 'bbva.png', 'color': '#004481'},
             'NACION': {'nombre': 'Banco de la Nación', 'logo': None, 'color': '#b91c1c'},
             'OTRO': {'nombre': 'Otro banco', 'logo': None, 'color': '#475569'}}
TIPOS_CUENTA_OC = {'CUENTA': 'Cuenta', 'CCI': 'CCI (interbancaria)', 'DETRACCION': 'Detracciones'}
TIPOS_DOC_OC = {'GUIA': 'Guía de remisión', 'FACTURA': 'Factura', 'CERTIFICADO': 'Certificado de calidad', 'COTIZACION': 'Cotización',
                'PAGO': 'Constancia de pago', 'OTRO': 'Otros'}
# Cada empresa emite sus propias órdenes: numeración, datos del PDF, logo, colores y firma de aprobación separados.
EMPRESAS_OC = {'ANCLAJES': {'nombre': 'Anclajes y Pernos Perú SAC', 'corto': 'Anclajes', 'habilitada': True, 'color': '#0B3D91', 'fondo': '#eff6ff',
                            'logo': 'logo.png', 'firma': 'GerenciaAnclajes.jpeg', 'firma_alto': 78},
               'IMPORTBOLTS': {'nombre': 'Import Bolts & Estructure SAC', 'corto': 'Import Bolts', 'habilitada': True, 'color': '#024aa8', 'fondo': '#ecfdf3',
                               'acento': '#5fb236', 'logo': 'logo_import.png', 'firma': 'firmaImpobolts.png', 'firma_alto': 70}}
# Colores del PDF de cada empresa (mismo formato, distinta identidad)
TEMAS_PDF_OC = {'ANCLAJES': {'azul': '#1f4e9c', 'caja': '#7f7f7f', 'cab': '#7f7f7f', 'neto': '#404040', 'res': '#bdd7ee', 'resaltado_fondo': '#e8f0fe'},
                'IMPORTBOLTS': {'azul': '#024aa8', 'caja': '#024aa8', 'cab': '#024aa8', 'neto': '#024aa8', 'res': '#d6e4f7', 'resaltado_fondo': '#e6f4dd'}}
IGV_OC = 0.18
TIPOS_OC = {'OC': 'Orden de Compra', 'OS': 'Orden de Servicio'}
DESTINOS_OC = {'GENERAL': 'Inventario de la empresa', 'INSUMOS': 'Insumos internos'}
DOCS_UNICOS_OC = ('GUIA', 'FACTURA', 'COTIZACION', 'PAGO')     # un solo archivo (se reemplaza)
MAX_DOCS_OC = {'CERTIFICADO': 3, 'OTRO': 3}                     # hasta 3 archivos
MONEDAS_OC = {'PEN': {'simbolo': 'S/', 'nombre': 'Soles', 'letras': ('SOL', 'SOLES')},
              'USD': {'simbolo': 'US$', 'nombre': 'Dólares', 'letras': ('DÓLAR AMERICANO', 'DÓLARES AMERICANOS')}}
ESTADOS_OC = {
    'BORRADOR': {'txt': 'Borrador', 'color': '#64748b', 'fondo': '#f1f5f9', 'icono': 'bi-pencil-square'},
    'ENVIADA': {'txt': 'Por aprobar', 'color': '#b45309', 'fondo': '#fffbeb', 'icono': 'bi-hourglass-split'},
    'APROBADA': {'txt': 'Aprobada · por recibir', 'color': '#1d4ed8', 'fondo': '#eff6ff', 'icono': 'bi-patch-check'},
    'RECHAZADA': {'txt': 'Rechazada', 'color': '#b91c1c', 'fondo': '#fef2f2', 'icono': 'bi-x-octagon'},
    'ANULADA': {'txt': 'Anulada', 'color': '#334155', 'fondo': '#e2e8f0', 'icono': 'bi-slash-circle'},
    'RECIBIDA': {'txt': 'Recibida · en revisión', 'color': '#0e7490', 'fondo': '#ecfeff', 'icono': 'bi-box-seam'},
    'CONFORME': {'txt': 'Conforme · en almacén', 'color': '#15803d', 'fondo': '#f0fdf4', 'icono': 'bi-check-circle-fill'},
}
VISTAS_OC = {
    'curso': ('En curso', ['BORRADOR', 'ENVIADA', 'APROBADA', 'RECIBIDA']),
    'aprobar': ('Por aprobar', ['ENVIADA']),
    'recibir': ('Por recibir', ['APROBADA', 'RECIBIDA']),
    'conformes': ('Conformes / en almacén', ['CONFORME']),
    'cerradas': ('Rechazadas y anuladas', ['RECHAZADA', 'ANULADA']),
    'todas': ('Todas', list(ESTADOS_OC)),
}
# Vistas que no dependen solo del estado (se calculan): atrasadas y por pagar
VISTAS_OC_ORDEN = ['curso', 'aprobar', 'recibir', 'atrasadas', 'conformes', 'por_pagar', 'pagadas', 'cerradas', 'todas']
VISTAS_OC_EXTRA = {'atrasadas': 'Atrasadas', 'por_pagar': 'Por pagar', 'pagadas': 'Pagadas'}
CATALOGOS_OC = {'OC_UM': 'Unidades de medida (U.M.)', 'OC_CONDICION_PAGO': 'Condiciones de pago', 'OC_SERVICIO': 'Tipos de servicio (OS)',
                'OC_AREA': 'Áreas que solicitan', 'OC_SOLICITANTE': 'Otros solicitantes'}
_OC_INICIALES = {
    'OC_UM': ['UN', 'PZA', 'PAR', 'JGO', 'CJA-10', 'CJA-25', 'CJA-50', 'CJA-100', 'KG', 'MT', 'ROLLO', 'GLN', 'LT', 'SERV'],
    'OC_CONDICION_PAGO': ['CONTADO', 'CONTRA ENTREGA', 'ADELANTO 50% - SALDO CONTRA ENTREGA', 'CRÉDITO 15 DÍAS',
                          'CRÉDITO 30 DÍAS', 'CRÉDITO 45 DÍAS', 'CRÉDITO 60 DÍAS'],
    'OC_AREA': ['GERENCIA', 'ADMINISTRACIÓN', 'VENTAS', 'LOGÍSTICA', 'ALMACÉN', 'PRODUCCIÓN'],
    'OC_SOLICITANTE': [],
    'OC_SERVICIO': ['CORTE', 'ROSCADO', 'DOBLADO', 'GALVANIZADO', 'ZINCADO / PAVONADO', 'MAQUINADO / TORNEADO', 'SOLDADURA', 'PINTURA',
                    'TRATAMIENTO TÉRMICO', 'TRANSPORTE / FLETE', 'MANTENIMIENTO', 'OTRO SERVICIO'],
}
_OC_MOTIVOS_COMPRA_INICIALES = [('REPOSICIÓN DE STOCK', False), ('PEDIDO DE CLIENTE', True), ('USO INTERNO', False),
                                ('PROYECTO / OBRA DE CLIENTE', True), ('MUESTRA PARA CLIENTE', True), ('MANTENIMIENTO', False)]
OC_CONFIG_DEF = {
    'razon_social': 'ANCLAJES Y PERNOS PERÚ SAC',
    'ruc': '20611624671',
    'direccion': 'JE E CORRE 407 SANTA LUZMILA COMAS',
    'email': 'victorm@anclajesperu.com',
    'telefono': '940479303',
    'lugar_entrega': 'AV. SANTA ANA NRO. 386 OTR. CHACRA CERRO LIMA - LIMA - COMAS',
    'terminos': ("1. La entrega de materiales se realizará junto al **CERTIFICADO DE CALIDAD**.\n"
                 "2. Los **MATERIALES QUE NO COINCIDAN** con las especificaciones de la presente O/C **SERÁN DEVUELTOS**.\n"
                 "3. Las facturas se enviarán por correo **logistica@anclajesperu.com**\n"
                 "4. Adjuntar **GUÍA, FACTURA y ORDEN DE COMPRA**\n"
                 "5. Todo personal está obligado a **INGRESAR CON SU RESPECTIVA EPP y su SCTR**, de lo contrario no ingresará."),
    'horario': "LUNES A VIERNES 8:00 AM - 5:00 PM\nSÁBADOS 8:00 AM - 4:00 PM\nREFRIGERIO 1:00 PM - 2:00 PM",
    'imp_condiciones': ("Precios en dólares americanos (USD). No incluyen IGV.\n"
                        "Incoterm y puerto: según la cotización del proveedor (destino: Callao - Perú).\n"
                        "Enviar con cada embarque: factura comercial, packing list, B/L y certificado de calidad.\n"
                        "Marcar cada caja con la medida, la calidad y la cantidad de piezas."),
    'imp_pagos': "Depósito | 15\nEl saldo debe pagarse en 60 días una vez recibido el B/L",
}
OC_CONFIG_DEF_IB = {
    'razon_social': 'IMPORT BOLTS & ESTRUCTURE SAC',
    'ruc': '20601850509',
    'direccion': 'AV. SANTA ANA Nº 386 COMAS-LIMA',
    'email': 'logistica@importbolts.com; lcachay@importbolts.com',
    'telefono': '908801646 / 992519846 / 940479301',
    'lugar_entrega': 'EN NUESTROS ALMACENES: AV. SANTA ANA NRO. 386 OTR. CHACRA CERRO - LIMA - COMAS',
    'terminos': ("1. La entrega de materiales se realizará junto al **CERTIFICADO DE CALIDAD**.\n"
                 "2. Los **MATERIALES QUE NO COINCIDAN** con las especificaciones de la presente O/C **SERÁN DEVUELTOS**.\n"
                 "3. Las facturas se enviarán por correo a **LOGISTICA@IMPORTBOLTS.COM** después de que el envío de bienes o servicio se haya completado.\n"
                 "4. Todo personal está obligado a **INGRESAR CON SU RESPECTIVA EPP** y su SCTR de lo contrario no ingresará."),
    'horario': "LUNES A VIERNES 8:00 AM - 5:00 PM\nSÁBADOS 8:00 AM - 4:00 PM\nREFRIGERIO 1:00 PM - 2:00 PM",
    'imp_condiciones': ("Precios en dólares americanos (USD). No incluyen IGV.\n"
                        "Incoterm y puerto: según la cotización del proveedor (destino: Callao - Perú).\n"
                        "Enviar con cada embarque: factura comercial, packing list, B/L y certificado de calidad.\n"
                        "Marcar cada caja con la medida, la calidad y la cantidad de piezas."),
    'imp_pagos': "Depósito | 15\nEl saldo debe pagarse en 60 días una vez recibido el B/L",
}
OC_CONFIG_DEFS = {'ANCLAJES': OC_CONFIG_DEF, 'IMPORTBOLTS': OC_CONFIG_DEF_IB}
OC_CONFIG_ETIQUETAS = {'razon_social': 'Razón social (título del PDF)', 'ruc': 'RUC de la empresa', 'direccion': 'Dirección',
                       'email': 'Correo', 'telefono': 'Teléfono', 'lugar_entrega': 'Lugar de entrega (fijo)',
                       'terminos': 'Términos y condiciones', 'horario': 'Horario de atención',
                       'imp_condiciones': 'Importación · Condiciones comerciales (sugeridas)',
                       'imp_pagos': 'Importación · Condiciones de pago (sugeridas): una por línea; "texto | %" calcula el monto'}
FIRMA_GERENCIA_OC = 'GerenciaAnclajes.jpeg'
_OC_MOTIVOS_INICIALES = [
    ('PRECIO', 'Precio elevado frente a otras cotizaciones'), ('PRECIO', 'Fuera del presupuesto'),
    ('PROVEEDOR', 'Proveedor no homologado / no confiable'), ('PROVEEDOR', 'Datos del proveedor incorrectos'),
    ('PRODUCTO', 'Especificación o calidad incorrecta'), ('PRODUCTO', 'Cantidad incorrecta'), ('PRODUCTO', 'No se necesita / ya hay stock'),
    ('CONDICIONES', 'Condición de pago no aceptada'), ('CONDICIONES', 'Plazo de entrega muy largo'),
    ('DOCUMENTO', 'Falta la cotización'), ('DOCUMENTO', 'Error en la orden (corregir y volver a enviar)'),
]
# (uso, aplica, categoría, motivo): motivos agregados después (anulación y propios de las Órdenes de Servicio)
_OC_MOTIVOS_V2 = [
    ('RECHAZO', 'OS', 'CALIDAD', 'El taller / proveedor no garantiza la calidad del servicio'),
    ('RECHAZO', 'OS', 'TÉCNICO', 'Especificación incompleta (medidas, acabado, norma)'),
    ('RECHAZO', 'OS', 'INTERNO', 'Se puede hacer en nuestro taller'),
    ('ANULACION', 'AMBAS', 'PROVEEDOR', 'El proveedor no tiene stock o no puede atender'),
    ('ANULACION', 'AMBAS', 'PROVEEDOR', 'El proveedor no confirmó / no respondió'),
    ('ANULACION', 'AMBAS', 'PROVEEDOR', 'El proveedor no puede cumplir el plazo'),
    ('ANULACION', 'AMBAS', 'PRECIO', 'El proveedor cambió el precio'),
    ('ANULACION', 'AMBAS', 'PEDIDO', 'Ya no se necesita'),
    ('ANULACION', 'AMBAS', 'PEDIDO', 'Se compró / contrató con otro proveedor'),
    ('ANULACION', 'AMBAS', 'PEDIDO', 'El cliente canceló su pedido'),
    ('ANULACION', 'AMBAS', 'DOCUMENTO', 'Error en la orden (se emitirá otra)'),
    ('ANULACION', 'OC', 'CALIDAD', 'El material ofrecido no cumple la calidad pedida'),
    ('ANULACION', 'OS', 'CALIDAD', 'El servicio no se puede hacer con la calidad pedida'),
]
_OC_MOTIVOS_RQ = [      # motivos para rechazar (Logística) o anular (quien lo pidió) un REQUERIMIENTO de compra
    ('RECHAZO', 'RQ', 'STOCK', 'Hay stock suficiente en el inventario'),
    ('RECHAZO', 'RQ', 'STOCK', 'Se puede atender con un producto equivalente'),
    ('RECHAZO', 'RQ', 'PEDIDO', 'Pedido duplicado (ya está en otro requerimiento)'),
    ('RECHAZO', 'RQ', 'PEDIDO', 'Cantidad no justificada'),
    ('RECHAZO', 'RQ', 'DATOS', 'Falta información (cliente, OC, cantidades o producto)'),
    ('RECHAZO', 'RQ', 'PRESUPUESTO', 'No hay presupuesto por ahora'),
    ('RECHAZO', 'RQ', 'PROVEEDOR', 'Ningún proveedor lo tiene disponible'),
    ('ANULACION', 'RQ', 'PEDIDO', 'Ya no se necesita'),
    ('ANULACION', 'RQ', 'PEDIDO', 'El cliente canceló su pedido'),
    ('ANULACION', 'RQ', 'PEDIDO', 'Se pidió por error'),
    ('ANULACION', 'RQ', 'STOCK', 'Se consiguió en stock o llegó por otro lado'),
    ('ANULACION', 'RQ', 'DATOS', 'Se volverá a pedir con otros datos'),
]
_OC_MOTIVOS_DESCARTE = [      # para DESCARTAR un producto de un requerimiento (no se comprará)
    ('DESCARTE', 'RQ', 'PROVEEDOR', 'Ningún proveedor lo tiene disponible'),
    ('DESCARTE', 'RQ', 'PROVEEDOR', 'El plazo de entrega no sirve'),
    ('DESCARTE', 'RQ', 'PRECIO', 'Precio fuera del presupuesto'),
    ('DESCARTE', 'RQ', 'STOCK', 'Hay stock suficiente en el inventario'),
    ('DESCARTE', 'RQ', 'PEDIDO', 'Ya no se necesita'),
    ('DESCARTE', 'RQ', 'PEDIDO', 'El cliente canceló o cambió su pedido'),
    ('DESCARTE', 'RQ', 'PRODUCTO', 'Se reemplazó por otro producto equivalente'),
    ('DESCARTE', 'RQ', 'PRODUCTO', 'Se pidió por error'),
]
USOS_MOTIVO_OC = {'RECHAZO': 'Rechazo (Gerencia)', 'ANULACION': 'Anulación', 'DESCARTE': 'Descartar producto (requerimientos)'}
APLICA_MOTIVO_OC = {'AMBAS': 'OC y OS', 'OC': 'Solo OC', 'OS': 'Solo OS', 'RQ': 'Requerimientos'}
DETRACCION_DEF = 12.0       # % de detracción sugerido (se cambia en cada orden)
_oc_ok = False


def _sembrar_catalogos_oc():
    for tipo, valores in _OC_INICIALES.items():
        if not CatalogoValor.query.filter_by(tipo=tipo).first():
            for v in valores:
                db.session.add(CatalogoValor(tipo=tipo, valor=v, activo=True, es_predeterminado=False))


def _sembrar_motivos_compra_oc():
    if not OCMotivoCompra.query.first():
        for nombre, pide in _OC_MOTIVOS_COMPRA_INICIALES:
            db.session.add(OCMotivoCompra(nombre=nombre, pide_cliente=pide, activo=True))


def _migrar_llegadas_a_entregas():
    """Una sola vez: las órdenes que ya tenían llegada registrada pasan a tener su 'Entrega 1' con todo lo pedido
    (y lo que ya se ingresó al inventario queda en esa entrega)."""
    for o in OrdenCompra.query.filter(OrdenCompra.fecha_llegada.isnot(None)).all():
        if OrdenCompraEntrega.query.filter_by(orden_id=o.id).first():
            continue
        e = OrdenCompraEntrega(orden_id=o.id, numero=1, fecha=o.fecha_llegada, parcial=False, numero_guia=o.numero_guia, nota=o.nota_recepcion,
                               recibido_por_id=o.recibido_por_id, fecha_registro=o.fecha_llegada,
                               conforme_por_id=o.conforme_por_id if o.fecha_conforme else None, fecha_conforme=o.fecha_conforme,
                               nota_conforme=o.nota_conforme if o.fecha_conforme else None)
        db.session.add(e)
        db.session.flush()
        for it in o.items:
            db.session.add(OrdenCompraEntregaItem(entrega_id=e.id, item_id=it.id, cantidad=it.cantidad, ingresado_por_id=it.ingresado_por_id,
                                                  fecha_ingreso=it.fecha_ingreso, sku_ingreso=it.sku_ingreso, nota_ingreso=it.nota_ingreso,
                                                  kardex_mov_id=it.kardex_mov_id, cantidad_kardex=it.cantidad_kardex))
        for d in OrdenCompraDocumento.query.filter_by(orden_id=o.id, tipo='GUIA').all():
            d.entrega_id = e.id


def _asegurar_oc():
    """Crea las tablas del módulo si faltan y siembra UNA vez los catálogos (U.M. y condiciones de pago)."""
    global _oc_ok
    if _oc_ok:
        return
    for modelo in (OCProveedor, OCContacto, OCMotivoRechazo, OrdenCompra, OrdenCompraItem, OrdenCompraEvento, OrdenCompraDocumento, OCConfig,
                   OCCuentaBancaria, OCMotivoCompra, RequerimientoCompra, RequerimientoItem, RequerimientoDocumento, RequerimientoEvento,
                   RequerimientoVisto, OrdenCompraEntrega, OrdenCompraEntregaItem, Notificacion, NotificacionConfig, PushSuscripcion):
        modelo.__table__.create(bind=db.engine, checkfirst=True)
    _agregar_columnas_si_faltan('oc_proveedor', [('sunat_estado', 'VARCHAR(50)'), ('sunat_condicion', 'VARCHAR(50)'), ('sunat_fecha', 'TIMESTAMP'),
                                                 ('actualizado_por', 'VARCHAR(100)'), ('fecha_actualizacion', 'TIMESTAMP')])
    _agregar_columnas_si_faltan('orden_compra', [('empresa', "VARCHAR(15) DEFAULT 'ANCLAJES'"), ('contacto_id', 'INTEGER'),
                                                 ('rechazo_categoria', 'VARCHAR(60)'), ('rechazo_opcion', 'VARCHAR(150)'),
                                                 ('solicitante_user_id', 'INTEGER'), ('solicitante_nombre', 'VARCHAR(120)'),
                                                 ('area_solicitante', 'VARCHAR(80)'), ('motivo_compra', 'VARCHAR(120)'), ('motivo_detalle', 'VARCHAR(300)'),
                                                 ('cliente_ruc', 'VARCHAR(20)'), ('cliente_razon', 'VARCHAR(200)'),
                                                 ('requiere_certificado', 'BOOLEAN DEFAULT FALSE'), ('fecha_factura', 'DATE'), ('monto_factura', 'FLOAT'),
                                                 ('estado_pago', "VARCHAR(12) DEFAULT 'PENDIENTE'"), ('fecha_pago', 'DATE'), ('pagado_por_id', 'INTEGER'),
                                                 ('fecha_marca_pago', 'TIMESTAMP'), ('pago_operacion', 'VARCHAR(80)'), ('pago_cuenta', 'VARCHAR(200)'),
                                                 ('pago_nota', 'VARCHAR(300)')])
    _agregar_columnas_si_faltan('oc_motivo_rechazo', [('uso', "VARCHAR(10) DEFAULT 'RECHAZO'"), ('aplica', "VARCHAR(5) DEFAULT 'AMBAS'")])
    _agregar_columnas_si_faltan('orden_compra', [('anulacion_categoria', 'VARCHAR(60)'), ('anulacion_opcion', 'VARCHAR(150)'), ('detraccion_pct', 'FLOAT'),
                                                 ('nota_seguimiento', 'VARCHAR(300)'), ('revision', 'INTEGER DEFAULT 0'),
                                                 ('motivo_edicion', 'VARCHAR(300)')])
    _agregar_columnas_si_faltan('orden_compra_item', [('familia', 'VARCHAR(200)'), ('calidad', 'VARCHAR(200)'), ('estado_producto', 'VARCHAR(100)'),
                                                      ('es_nuevo', 'BOOLEAN DEFAULT FALSE'),
                                                      ('ingresado_por_id', 'INTEGER'), ('fecha_ingreso', 'TIMESTAMP'),
                                                      ('sku_ingreso', 'VARCHAR(60)'), ('nota_ingreso', 'VARCHAR(300)'),
                                                      ('peso_modo', 'VARCHAR(1)'), ('peso_unitario', 'FLOAT'), ('peso_total', 'FLOAT'),
                                                      ('tipo_servicio', 'VARCHAR(80)'), ('kardex_mov_id', 'INTEGER'), ('cantidad_kardex', 'INTEGER'),
                                                      ('req_item_id', 'INTEGER')])
    _agregar_columnas_si_faltan('orden_compra_documento', [('entrega_id', 'INTEGER')])
    _agregar_columnas_si_faltan('orden_compra', [('precios_con_igv', 'BOOLEAN DEFAULT FALSE')])
    _agregar_columnas_si_faltan('oc_proveedor', [('es_extranjero', 'BOOLEAN DEFAULT FALSE'), ('pais', 'VARCHAR(60)')])
    _agregar_columnas_si_faltan('orden_compra_item', [('cantidad_cancelada', 'FLOAT DEFAULT 0'), ('kgs_mpcs', 'FLOAT'), ('precio_mil', 'FLOAT'),
                                                      ('detalle', 'VARCHAR(500)'), ('piezas', 'FLOAT'), ('precio_con_igv', 'FLOAT')])
    _agregar_columnas_si_faltan('orden_compra', [('es_importacion', 'BOOLEAN DEFAULT FALSE'), ('condiciones_comerciales', 'TEXT'),
                                                 ('pagos_importacion', 'TEXT'), ('saldo_cerrado_motivo', 'VARCHAR(300)')])
    _agregar_columnas_si_faltan('requerimiento_item', [('descartado', 'BOOLEAN DEFAULT FALSE'), ('descartado_por_id', 'INTEGER'),
                                                       ('fecha_descarte', 'TIMESTAMP'), ('descarte_categoria', 'VARCHAR(60)'),
                                                       ('descarte_opcion', 'VARCHAR(150)'), ('descarte_motivo', 'VARCHAR(300)')])
    _agregar_columnas_si_faltan('requerimiento_compra', [('solicitante_user_id', 'INTEGER'), ('rechazo_categoria', 'VARCHAR(60)'),
                                                         ('rechazo_opcion', 'VARCHAR(150)'), ('motivo_anulacion', 'VARCHAR(300)'),
                                                         ('anulacion_categoria', 'VARCHAR(60)'), ('anulacion_opcion', 'VARCHAR(150)')])
    _agregar_columnas_si_faltan('requerimiento_compra', [('destino', "VARCHAR(10) DEFAULT 'GENERAL'")])
    _agregar_columnas_si_faltan('requerimiento_item', [('insumo_id', 'INTEGER')])
    if not SystemConfig.query.get('oc_numeracion_empresa'):
        # Numeración propia por empresa: la restricción única pasa de (tipo, número) a (empresa, tipo, número)
        try:
            with db.engine.begin() as conn:
                if db.engine.dialect.name == 'postgresql':
                    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("UPDATE orden_compra SET empresa = 'ANCLAJES' WHERE empresa IS NULL"))
                if db.engine.dialect.name == 'postgresql':
                    conn.execute(text('ALTER TABLE orden_compra DROP CONSTRAINT IF EXISTS uq_orden_compra_tipo_numero'))
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_orden_compra_emp_tipo_num ON orden_compra (empresa, tipo, numero)'))
            db.session.add(SystemConfig(key='oc_numeracion_empresa', value='1', updated_by='Sistema'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Aviso: no se pudo cambiar la numeración por empresa de órdenes: {e}")
    if not SystemConfig.query.get('oc_motivos_sembrado'):
        try:
            if not OCMotivoRechazo.query.first():
                for cat, mot in _OC_MOTIVOS_INICIALES:
                    db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True))
            # contactos que estaban guardados en el proveedor (versión anterior) -> lista de contactos
            for p in OCProveedor.query.all():
                if p.contacto and p.telefono and not OCContacto.query.filter_by(oc_proveedor_id=p.id).first():
                    db.session.add(OCContacto(oc_proveedor_id=p.id, nombre=p.contacto, telefono=p.telefono, email=p.email, activo=True,
                                              creado_por=p.creado_por, fecha_creacion=p.ultima_orden or p.fecha_creacion or hora_peru()))
            db.session.add(SystemConfig(key='oc_motivos_sembrado', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_sembrado'):
        try:
            _sembrar_catalogos_oc()
            db.session.add(SystemConfig(key='oc_sembrado', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_motivos_v2'):      # motivos de anulación y de las Órdenes de Servicio
        try:
            for uso, aplica, cat, mot in _OC_MOTIVOS_V2:
                db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True, uso=uso, aplica=aplica))
            db.session.add(SystemConfig(key='oc_motivos_v2', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_motivos_rq'):      # motivos de rechazo / anulación de los requerimientos
        try:
            for uso, aplica, cat, mot in _OC_MOTIVOS_RQ:
                db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True, uso=uso, aplica=aplica))
            db.session.add(SystemConfig(key='oc_motivos_rq', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_motivos_desc'):    # motivos para descartar productos de un requerimiento
        try:
            for uso, aplica, cat, mot in _OC_MOTIVOS_DESCARTE:
                db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True, uso=uso, aplica=aplica))
            db.session.add(SystemConfig(key='oc_motivos_desc', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_entregas_v1'):     # las llegadas que ya existían pasan a ser la "Entrega 1" de su orden
        try:
            _migrar_llegadas_a_entregas()
            db.session.add(SystemConfig(key='oc_entregas_v1', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_sembrado_v3'):      # tipos de servicio (Órdenes de Servicio)
        try:
            _sembrar_catalogos_oc()
            db.session.add(SystemConfig(key='oc_sembrado_v3', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    if not SystemConfig.query.get('oc_sembrado_v2'):      # áreas y motivos de compra (versión con solicitante)
        try:
            _sembrar_catalogos_oc()
            _sembrar_motivos_compra_oc()
            db.session.add(SystemConfig(key='oc_sembrado_v2', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    _oc_ok = True


try:
    with app.app_context():
        _asegurar_insumos()
        _asegurar_oc()
except Exception as _e_oc:
    print(f"Aviso: no se pudo preparar el módulo de Órdenes de Compra al arrancar: {_e_oc}")


def _ruta_oc(nivel='ver', como_json=False):
    """Permisos: ver (Gerencia, Logística, Administración, Almacén) / editar (Gerencia y Logística) / aprobar (Gerencia)."""
    def deco(f):
        @_wraps_insumos(f)
        def envoltura(*args, **kwargs):
            permitidos = {'ver': ROLES_OC_VEN, 'editar': ROLES_OC_EDITAN, 'aprobar': ROLES_OC_APRUEBAN, 'admin': ['admin'],
                  'ingresar': ROLES_OC_INGRESAN, 'docs': list(set(ROLES_OC_VEN + ROLES_OC_INGRESAN)), 'pagar': ROLES_OC_PAGAN,
                  'req_ver': ROLES_REQ_VEN, 'req_crear': ROLES_REQ_CREAN, 'buscar': list(set(ROLES_OC_INGRESAN + ROLES_REQ_CREAN))}[nivel]
            if session.get('role') not in permitidos:
                if como_json:
                    return {'status': 'error', 'msg': 'No autorizado'}, 403
                return "Acceso denegado", 403
            _asegurar_insumos()
            _asegurar_oc()
            return f(*args, **kwargs)
        return envoltura
    return deco


def _oc_clave_cfg(empresa, clave):
    """Las claves de Anclajes se guardan tal cual (como siempre); las de las otras empresas con prefijo 'EMPRESA:'."""
    return clave if empresa == 'ANCLAJES' else f'{empresa}:{clave}'


def _oc_cfg(empresa='ANCLAJES'):
    empresa = empresa if empresa in EMPRESAS_OC else 'ANCLAJES'
    cfg = dict(OC_CONFIG_DEFS[empresa])
    guardado = {c.clave: c.valor for c in OCConfig.query.all()}
    for clave in list(cfg):
        v = guardado.get(_oc_clave_cfg(empresa, clave))
        if v is not None:
            cfg[clave] = v
    for t in TIPOS_OC:
        cfg[f'num_{t}'] = guardado.get(_oc_clave_cfg(empresa, f'num_{t}')) or ''
    return cfg


def _oc_pagos_de_texto(texto):
    """'Depósito | 15' -> {'texto': 'Depósito', 'pct': 15.0}; una línea sin % queda solo como texto."""
    lineas = []
    for l in (texto or '').splitlines():
        if not l.strip():
            continue
        t, _, pct = l.partition('|')
        pct = _num(pct) if pct.strip() else None
        lineas.append({'texto': ' '.join(t.split())[:200], 'pct': pct if pct and 0 < pct <= 100 else None})
    return lineas


def _oc_pagos_lista(valor):
    """Las líneas de pago guardadas en la orden (JSON) como lista."""
    try:
        lista = json.loads(valor) if isinstance(valor, str) and valor else (valor or [])
    except ValueError:
        lista = []
    return [{'texto': str(x.get('texto') or ''), 'pct': x.get('pct')} for x in lista if isinstance(x, dict)]


def _oc_pagos_imp(orden):
    """Condiciones de pago de una importación con el monto calculado: 'Depósito del 15.0% $13,934.28'."""
    total = orden.total or 0
    filas = []
    for x in _oc_pagos_lista(orden.pagos_importacion):
        monto = round(total * x['pct'] / 100, 2) if x['pct'] else None
        filas.append({**x, 'monto': monto,
                      'txt': f"{x['texto']} del {x['pct']:.1f}% ${monto:,.2f}" if x['pct'] else x['texto']})
    return filas


app.add_template_global(_oc_pagos_imp, 'oc_pagos_imp')


def _oc_evento(orden, accion, detalle=''):
    db.session.add(OrdenCompraEvento(orden_id=orden.id, fecha=hora_peru(), user_id=session.get('user_id'), accion=accion,
                                     detalle=(detalle or '')[:500]))


def _oc_numero_txt(orden, numero=None, empresa=None, fecha=None):
    """Mismo formato en las dos empresas (OC y OS): año de la orden - correlativo de 5 dígitos, ej. 2026-00248.
    Cada empresa y cada tipo llevan su propio correlativo."""
    numero = orden.numero if orden is not None else numero
    anio = (orden.fecha if orden is not None and orden.fecha else (fecha or hora_peru().date())).year
    return f"{anio}-{int(numero or 0):05d}"


def _oc_codigo(orden):
    return f"{orden.tipo} N° {_oc_numero_txt(orden)}"


def _siguiente_numero_oc(tipo, empresa='ANCLAJES'):
    """Numeración correlativa propia de cada empresa y tipo. En Configuración se puede fijar el número desde el que sigue."""
    ultimo = db.session.query(func.max(OrdenCompra.numero)).filter(OrdenCompra.tipo == tipo,
                                                                   OrdenCompra.empresa == empresa).scalar()
    inicio = OCConfig.query.get(_oc_clave_cfg(empresa, f'num_{tipo}'))
    minimo = int(inicio.valor) if inicio and (inicio.valor or '').isdigit() else 1
    return max(int(ultimo or 0) + 1, minimo)


from markupsafe import Markup


def _oc_resaltado(texto):
    """'texto **importante**' -> HTML seguro con lo importante sombreado (para el PDF y la vista previa)."""
    partes = re.split(r'\*\*(.+?)\*\*', html.escape(texto or ''))
    return Markup(''.join(f'<span class="resaltado">{p}</span>' if i % 2 else p for i, p in enumerate(partes)))


_UNIDADES_L = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE', 'DIEZ', 'ONCE', 'DOCE', 'TRECE',
               'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE', 'VEINTE', 'VEINTIUNO', 'VEINTIDÓS',
               'VEINTITRÉS', 'VEINTICUATRO', 'VEINTICINCO', 'VEINTISÉIS', 'VEINTISIETE', 'VEINTIOCHO', 'VEINTINUEVE']
_DECENAS_L = ['', '', '', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
_CENTENAS_L = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS', 'SEISCIENTOS', 'SETECIENTOS',
               'OCHOCIENTOS', 'NOVECIENTOS']


def _letras_999(n):
    if n == 0:
        return ''
    if n == 100:
        return 'CIEN'
    c, r = divmod(n, 100)
    if r < 30:
        resto = _UNIDADES_L[r]
    else:
        d, u = divmod(r, 10)
        resto = _DECENAS_L[d] + (f' Y {_UNIDADES_L[u]}' if u else '')
    return ' '.join(x for x in (_CENTENAS_L[c], resto) if x)


def _numero_a_letras(n):
    """Entero -> texto en español (hasta 999 millones). 1 -> UNO, 21000 -> VEINTIÚN MIL."""
    n = int(n)
    if n == 0:
        return 'CERO'
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append('UN MILLÓN' if millones == 1 else f'{_letras_999(millones)} MILLONES'.replace('UNO MILLONES', 'UN MILLONES'))
    if miles:
        partes.append('MIL' if miles == 1 else f'{_letras_999(miles)} MIL')
    if unidades:
        partes.append(_letras_999(unidades))
    texto = ' '.join(partes)
    texto = re.sub(r'\bUNO (MIL|MILLONES)\b', r'UN \1', texto).replace('VEINTIUNO MIL', 'VEINTIÚN MIL')
    return texto


def _monto_en_letras(monto, moneda):
    centimos = int(round(float(monto or 0) * 100))
    entero, cent = divmod(centimos, 100)
    sing, plur = MONEDAS_OC.get(moneda, MONEDAS_OC['PEN'])['letras']
    return f"SON: {_numero_a_letras(entero)} CON {cent:02d}/100 {sing if entero == 1 else plur}"


def _oc_entrega_txt(orden):
    if orden.entrega_tipo == 'DIAS' and orden.entrega_dias:
        return f"{orden.entrega_dias} DÍA{'S' if orden.entrega_dias != 1 else ''} (luego de aprobada la O/C)"
    if orden.entrega_tipo == 'FECHA' and orden.fecha_entrega:
        return orden.fecha_entrega.strftime('%d/%m/%Y')
    return 'A TRATAR'


def _oc_fecha_esperada(orden):
    """Fecha estimada de llegada (para la lista): fecha fija, o días contados desde la aprobación (o la emisión)."""
    if orden.entrega_tipo == 'FECHA' and orden.fecha_entrega:
        return orden.fecha_entrega
    if orden.entrega_tipo == 'DIAS' and orden.entrega_dias:
        base = (orden.fecha_aprobacion.date() if orden.fecha_aprobacion else orden.fecha)
        return base + timedelta(days=orden.entrega_dias)
    return None


def _oc_motivos(uso, tipo=None, incluir_inactivos=False):
    """{categoría: [motivos]} de rechazo o de anulación que aplican al tipo de orden (OC / OS)."""
    res = {}
    for m in sorted(OCMotivoRechazo.query.all(), key=lambda m: (_clave_alfabetica(m.categoria), _clave_alfabetica(m.motivo))):
        if (m.uso or 'RECHAZO') != uso or (not incluir_inactivos and not m.activo):
            continue
        if tipo == 'RQ' and (m.aplica or 'AMBAS') != 'RQ':
            continue
        if tipo and tipo != 'RQ' and (m.aplica or 'AMBAS') not in ('AMBAS', tipo):
            continue
        res.setdefault(m.categoria, []).append(m)
    return res


def _oc_anulacion_txt(orden):
    partes = [x for x in (orden.anulacion_categoria, orden.anulacion_opcion) if x]
    txt = ' · '.join(partes)
    if orden.motivo_anulacion:
        txt = f"{txt} — {orden.motivo_anulacion}" if txt else orden.motivo_anulacion
    return txt


app.add_template_global(_oc_anulacion_txt, 'oc_anulacion_txt')


def _oc_rechazo_txt(orden):
    partes = [x for x in (orden.rechazo_categoria, orden.rechazo_opcion) if x]
    txt = ' · '.join(partes)
    if orden.motivo_rechazo:
        txt = f"{txt} — {orden.motivo_rechazo}" if txt else orden.motivo_rechazo
    return txt


app.add_template_global(_oc_rechazo_txt, 'oc_rechazo_txt')


def _oc_destino_txt(orden):
    if orden.destino == 'INSUMOS':
        return 'Insumos internos'
    corto = EMPRESAS_OC.get(orden.empresa or 'ANCLAJES', EMPRESAS_OC['ANCLAJES'])['corto']
    return f"Servicio · {corto}" if orden.tipo == 'OS' else f"Inventario {corto}"


def _oc_ingreso_estado(orden):
    """Avance del ingreso al inventario de una orden con destino inventario: ítems completos, total y si ya entró todo."""
    items = list(orden.items)
    hechos = [i for i in items if i.fecha_ingreso]
    # el último ingreso puede ser de una entrega parcial (el ítem aún no se completa)
    marcas = [ei for e in _oc_entregas(orden) for ei in e.items if ei.fecha_ingreso] or hechos
    ultimo = max(marcas, key=lambda i: i.fecha_ingreso) if marcas else None
    return {'hechos': len(hechos), 'total': len(items), 'ultimo': ultimo, 'entregas_ing': len(marcas),
            'completo': bool(orden.fecha_kardex) or (bool(items) and len(hechos) == len(items))}


def _oc_dias_credito(condicion):
    """'CRÉDITO 30 DÍAS' -> 30. Contado, contra entrega o adelanto -> None (se paga al momento: no hay vencimiento ni alertas)."""
    m = re.search(r'(\d+)\s*D[IÍ]A', (condicion or '').upper())
    return int(m.group(1)) if m else None


def _oc_pago_info(orden, hoy=None):
    """Situación del pago. El control se habilita cuando Gerencia aprueba (APROBADA, RECIBIDA o CONFORME).
    Crédito X días: vence X días después de la emisión de la factura; si aún no se registra, desde la llegada del material
    (o la aprobación, como estimado). nivel: na / pagada / contado / al_dia / por_vencer / vencida."""
    hoy = hoy or hora_peru().date()
    habilitado = orden.estado in ('APROBADA', 'RECIBIDA', 'CONFORME')
    pagada = (orden.estado_pago or 'PENDIENTE') == 'PAGADO'
    dias = _oc_dias_credito(orden.condicion_pago)
    info = {'habilitado': habilitado, 'pagada': pagada, 'dias_credito': dias, 'credito': dias is not None,
            'vence': None, 'base': None, 'base_txt': '', 'faltan': None, 'estimado': False}
    if dias is not None:
        if orden.fecha_factura:
            base, txt = orden.fecha_factura, 'la emisión de la factura'
        elif orden.fecha_llegada:
            base, txt = orden.fecha_llegada.date(), 'la llegada del material (falta la fecha de la factura)'
        else:
            base = orden.fecha_aprobacion.date() if orden.fecha_aprobacion else orden.fecha
            txt = 'la aprobación (estimado: aún no llega)'
        info.update(base=base, base_txt=txt, vence=base + timedelta(days=dias), estimado=not orden.fecha_factura)
        info['faltan'] = (info['vence'] - hoy).days
    if pagada:
        nivel = 'pagada'
    elif not habilitado:
        nivel = 'na'
    elif dias is None:
        nivel = 'contado'
    elif info['faltan'] < 0:
        nivel = 'vencida'
    elif info['faltan'] <= DIAS_AVISO_PAGO:
        nivel = 'por_vencer'
    else:
        nivel = 'al_dia'
    info['nivel'] = nivel
    if nivel == 'pagada':
        info['txt'] = f"Pagada{(' el ' + orden.fecha_pago.strftime('%d/%m/%Y')) if orden.fecha_pago else ''}"
    elif nivel == 'na':
        info['txt'] = 'Se habilita al aprobarse' if orden.estado in ('BORRADOR', 'ENVIADA') else '—'
    elif nivel == 'contado':
        info['txt'] = 'sin plazo (se paga al momento)'
    elif nivel == 'vencida':
        info['txt'] = f"VENCIDA hace {-info['faltan']} día{'s' if info['faltan'] != -1 else ''}"
    elif info['faltan'] == 0:
        info['txt'] = 'Vence HOY'
    else:
        info['txt'] = f"Vence en {info['faltan']} día{'s' if info['faltan'] != 1 else ''}"
    return info


def _oc_detraccion(orden):
    """Detracción de la orden: % sobre el total con IGV, monto a depositar en el Banco de la Nación y neto a pagar al proveedor."""
    if not getattr(orden, 'detraccion_pct', None):
        return None
    monto = round((orden.total or 0) * orden.detraccion_pct / 100, 2)
    return {'pct': orden.detraccion_pct, 'pct_txt': ('%g' % orden.detraccion_pct), 'monto': monto, 'neto': round((orden.total or 0) - monto, 2)}


app.add_template_global(_oc_detraccion, 'oc_detraccion')


def _oc_atraso(orden, hoy=None):
    """Días de atraso de una orden aprobada cuyo material no llega (None si no está atrasada)."""
    if orden.estado != 'APROBADA':
        return None
    esp = _oc_fecha_esperada(orden)
    if not esp:
        return None
    dias = ((hoy or hora_peru().date()) - esp).days
    return dias if dias > 0 else None


def _oc_solicitante_txt(orden):
    if orden.solicitante_user_id and orden.solicitante:
        return orden.solicitante.nombre_completo
    return orden.solicitante_nombre or ''


def _digitos(txt):
    return re.sub(r'\D', '', txt or '')


def _cuenta_json(c):
    b = BANCOS_OC.get(c.banco, BANCOS_OC['OTRO'])
    guardado = c.fecha_actualizacion or c.fecha_creacion
    return {'id': c.id, 'oc_proveedor_id': c.oc_proveedor_id, 'banco': c.banco,
            'banco_nombre': (c.banco_otro or b['nombre']) if c.banco == 'OTRO' else b['nombre'], 'banco_otro': c.banco_otro or '',
            'logo': url_for('static', filename='img/' + b['logo']) if b['logo'] else '', 'color': b['color'],
            'tipo': c.tipo, 'tipo_txt': TIPOS_CUENTA_OC.get(c.tipo, c.tipo), 'moneda': c.moneda or 'PEN',
            'moneda_txt': MONEDAS_OC.get(c.moneda or 'PEN', MONEDAS_OC['PEN'])['nombre'], 'numero': c.numero, 'copiar': _digitos(c.numero),
            'titular': c.titular or '', 'activo': bool(c.activo),
            'guardado': f"{'Editada' if c.fecha_actualizacion else 'Guardada'} {guardado.strftime('%d/%m/%Y %H:%M') if guardado else ''} por {c.actualizado_por or c.creado_por or '-'}"}


def _cuentas_de(prov_id, incluir_archivadas=False):
    orden_tipo = {'CUENTA': 0, 'CCI': 1, 'DETRACCION': 2}
    lista = [c for c in OCCuentaBancaria.query.filter_by(oc_proveedor_id=prov_id).all() if incluir_archivadas or c.activo] if prov_id else []
    lista.sort(key=lambda c: (not c.activo, orden_tipo.get(c.tipo, 9), c.banco, c.id))
    return [_cuenta_json(c) for c in lista]


def _cuenta_txt(c):
    return f"{_cuenta_json(c)['banco_nombre']} · {TIPOS_CUENTA_OC.get(c.tipo, c.tipo)} {MONEDAS_OC.get(c.moneda or 'PEN', MONEDAS_OC['PEN'])['simbolo']} · {c.numero}"


app.add_template_global(_oc_pago_info, 'oc_pago_info')
app.add_template_global(_oc_atraso, 'oc_atraso')
app.add_template_global(_oc_solicitante_txt, 'oc_solicitante_txt')
app.add_template_global(_oc_destino_txt, 'oc_destino_txt')
app.add_template_global(_oc_ingreso_estado, 'oc_ingreso_estado')
app.add_template_global(_oc_entrega_txt, 'oc_entrega_txt')
app.add_template_global(_oc_fecha_esperada, 'oc_fecha_esperada')
app.add_template_global(_oc_codigo, 'oc_codigo')
app.add_template_global(_oc_numero_txt, 'oc_numero_txt')
app.add_template_filter(_oc_resaltado, 'resaltado')


ESTADOS_REEDITABLES_OC = ('APROBADA', 'RECIBIDA', 'CONFORME')
TAX_TEMPORAL = 'SINTAXID'     # proveedor del exterior registrado sin Tax ID todavía (se completa después)
# Condiciones de pago que se suelen usar en importaciones (se agregan con un clic; se pueden escribir otras)
CONDICIONES_PAGO_IMP = ['PAGO A 90 DÍAS DE RECIBIDA LA COPIA DEL B/L (PAID IN 90 DAYS ONCE RECEIVED THE COPY OF B/L)',
                        'PAGO A 60 DÍAS DE RECIBIDA LA COPIA DEL B/L (PAID IN 60 DAYS ONCE RECEIVED THE COPY OF B/L)',
                        'DEPÓSITO ANTES DE LA PRODUCCIÓN (DEPOSIT BEFORE PRODUCTION)',
                        'SALDO CONTRA COPIA DEL B/L (BALANCE AGAINST COPY OF B/L)',
                        'SALDO ANTES DEL EMBARQUE (BALANCE BEFORE SHIPMENT)',
                        'T/T 100% ANTES DEL EMBARQUE (100% T/T BEFORE SHIPMENT)',
                        'CARTA DE CRÉDITO A LA VISTA (L/C AT SIGHT)',
                        'PAGO CONTRA DOCUMENTOS (CAD - CASH AGAINST DOCUMENTS)']
app.add_template_global(TAX_TEMPORAL, 'tax_temporal')


def _usd_pcs_txt(v):
    """Precio por pieza de importación: hasta 7 decimales sin ceros de más (0.8038509 · 0.0271499 · 0.16)."""
    if v is None:
        return '-'
    t = f"{v:,.7f}".rstrip('0')
    return t if len(t.split('.')[1]) >= 2 else f"{v:,.2f}"


app.add_template_filter(_usd_pcs_txt, 'usd_pcs')


def _oc_bloqueo_reedicion(orden):
    """Una orden YA APROBADA se puede editar (vuelve a Gerencia) para cuadrarla con lo que de verdad pasó (llegó menos,
    cambió el precio...) mientras NO esté pagada y NO se haya ingresado nada al inventario o a Insumos.
    Devuelve None si se puede, o el motivo por el que ya no."""
    if orden.estado not in ESTADOS_REEDITABLES_OC:
        return 'solo se edita una orden en borrador, aprobada, con material llegado o conforme'
    if (orden.estado_pago or 'PENDIENTE') == 'PAGADO':
        return 'ya está pagada'
    if orden.insumo_ingreso_id:
        return 'ya se ingresó a Insumos internos'
    if orden.tipo == 'OS' and orden.fecha_kardex:
        return 'Almacén ya marcó el seguimiento del servicio'
    if any(i.fecha_ingreso for i in orden.items) or any(ei.fecha_ingreso for e in _oc_entregas(orden) for ei in e.items):
        return 'Almacén ya ingresó productos de esta orden al Kardex'
    return None


def _oc_bloqueo_cambio_empresa(orden):
    """¿Se puede pasar la orden a la otra empresa (Anclajes <-> Import Bolts) al editarla? Solo antes de que haya llegado
    material (la guía y la factura ya salen a nombre de una empresa), de pagarla o de ingresar algo. None = sí se puede."""
    if orden.estado not in ('BORRADOR',) + ESTADOS_REEDITABLES_OC:
        return 'solo al editar una orden en borrador o ya aprobada'
    bloqueo = _oc_bloqueo_reedicion(orden) if orden.estado != 'BORRADOR' else None
    if bloqueo:
        return bloqueo
    if orden.fecha_llegada or _oc_entregas(orden):
        return 'ya llegó material (la guía y la factura son de esa empresa): anúlala y crea otra'
    return None


def _oc_permisos(orden):
    """Qué puede hacer el usuario actual con esta orden (para mostrar solo los botones que corresponden)."""
    rol = session.get('role')
    edita, aprueba = rol in ROLES_OC_EDITAN, rol in ROLES_OC_APRUEBAN
    e = orden.estado
    reeditar = edita and e in ESTADOS_REEDITABLES_OC and _oc_bloqueo_reedicion(orden) is None
    return {
        'editar': edita and e == 'BORRADOR',
        'reeditar': reeditar,
        'reeditar_bloqueo': (_oc_bloqueo_reedicion(orden) if edita and e in ESTADOS_REEDITABLES_OC and not reeditar else None),
        'enviar': edita and e == 'BORRADOR',
        'retirar': edita and e == 'ENVIADA',
        'aprobar': aprueba and e == 'ENVIADA',
        'rechazar': aprueba and e == 'ENVIADA',
        'anular': edita and e in ('BORRADOR', 'ENVIADA', 'APROBADA') and not orden.fecha_llegada,
        'llegada': edita and e in ('APROBADA', 'RECIBIDA') and _oc_recepcion(orden)['pendiente'] > 0,
        'conforme': edita and e == 'RECIBIDA' and bool(_oc_recepcion(orden)['sin_conformar']),
        'cerrar_saldo': edita and e in ('APROBADA', 'RECIBIDA') and _oc_recepcion(orden)['parcial'],
        'observar': edita and e in ('APROBADA', 'RECIBIDA'),
        'documentos': edita and e not in ('ANULADA',),
        'borrar_docs': edita and e not in ('CONFORME', 'ANULADA'),
        'ingresar': rol in ROLES_OC_INGRESAN and orden.destino == 'GENERAL' and not orden.fecha_kardex
                    and ((orden.tipo == 'OS' and e == 'CONFORME') or (orden.tipo == 'OC' and bool(_entregas_por_ingresar([orden])))),
        'insumos': edita and e == 'CONFORME' and orden.destino == 'INSUMOS' and not orden.insumo_ingreso_id,
        'duplicar': edita and e != 'BORRADOR',
        'pagar': rol in ROLES_OC_PAGAN and e in ('APROBADA', 'RECIBIDA', 'CONFORME') and (orden.estado_pago or 'PENDIENTE') != 'PAGADO',
        'deshacer_pago': rol == 'admin' and (orden.estado_pago or 'PENDIENTE') == 'PAGADO',
        'cuentas': rol in ROLES_OC_PAGAN and bool(orden.oc_proveedor_id),
        'factura': rol in ROLES_OC_PAGAN and e not in ('ANULADA', 'RECHAZADA'),
    }


def _clave_natural(texto):
    """Orden alfabético que respeta los números: CRÉDITO 7 < CRÉDITO 15 < CRÉDITO 30 < CRÉDITO 120."""
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', _clave_alfabetica(texto))]


def _oc_catalogo(tipo, incluir_inactivos=False):
    q = CatalogoValor.query.filter_by(tipo=tipo)
    if not incluir_inactivos:
        q = q.filter_by(activo=True)
    return sorted(q.all(), key=lambda v: _clave_natural(v.valor)) if tipo != 'OC_UM' else sorted(q.all(), key=lambda v: v.id)


def _leer_orden_form(f, orden=None):
    """Valida el formulario de la orden. Devuelve (datos, items, errores). Los totales se calculan aquí (no se confía en el navegador)."""
    errores = []
    datos = {}
    tipo = (orden.tipo if orden else (f.get('tipo') or 'OC')).upper()
    if tipo not in TIPOS_OC:
        errores.append('Elige si es Orden de Compra u Orden de Servicio.')
    datos['tipo'] = tipo
    # Orden de IMPORTACIÓN: proveedor del exterior, en dólares, sin IGV, precio por cada 1000 piezas y pagos por porcentaje
    es_imp = tipo == 'OC' and f.get('es_importacion') == '1'
    datos['es_importacion'] = es_imp
    # "Los precios incluyen IGV": se escribe el precio de la factura/cotización CON IGV y el sistema saca el valor sin IGV
    # a partir del TOTAL (así cuadra al céntimo con la factura: 600.00 = 508.47 + 91.53)
    con_igv = f.get('precios_con_igv') == '1' and not es_imp
    datos['precios_con_igv'] = con_igv
    totales_con_igv = []
    empresa = (orden.empresa if orden and orden.empresa else (f.get('empresa') or 'ANCLAJES')).upper()
    pedida = (f.get('empresa') or '').upper()
    if orden and pedida and pedida != empresa:
        # al editar se puede pasar la orden a la otra empresa (toma el número siguiente de esa empresa al guardar)
        bloqueo = _oc_bloqueo_cambio_empresa(orden)
        if bloqueo:
            errores.append(f'No se puede cambiar la empresa: {bloqueo}.')
        else:
            empresa = pedida
    if empresa not in EMPRESAS_OC or not EMPRESAS_OC[empresa]['habilitada']:
        errores.append('Elige la empresa que emite la orden.')
    datos['empresa'] = empresa
    try:
        fecha = datetime.strptime((f.get('fecha') or '').strip(), '%Y-%m-%d').date()
        if fecha > hora_peru().date():
            errores.append('La fecha de la orden no puede ser futura.')
    except ValueError:
        fecha = None
        errores.append('La fecha de la orden no es válida.')
    datos['fecha'] = fecha
    destino = (f.get('destino') or '').upper()
    if tipo == 'OS':
        if destino == 'INSUMOS':
            errores.append('Las órdenes de SERVICIO no van a Insumos internos.')
        destino = 'GENERAL'
    if destino not in DESTINOS_OC:
        errores.append('Elige el destino: Inventario General o Insumos internos.')
    datos['destino'] = destino
    ruc = re.sub(r'\D', '', f.get('ruc') or '')
    if es_imp:
        # proveedor del exterior: no tiene RUC peruano; se usa su código de registro / tax ID (solo letras y números)
        ruc = re.sub(r'[^0-9A-Za-z]', '', f.get('ruc') or '').upper()
        if len(ruc) < 3:
            errores.append('Escribe el N° de identificación del proveedor del exterior (Tax ID / registro).')
    elif len(ruc) not in (8, 11):
        errores.append('El RUC del proveedor debe tener 11 dígitos (o DNI de 8).')
    datos['ruc'] = ruc[:20]
    datos['razon_social'] = _limpio(f.get('razon_social'), 200)
    if len(datos['razon_social']) < 3:
        errores.append('Falta la razón social del proveedor (búscalo por RUC).')
    datos['direccion'] = _limpio(f.get('direccion'), 250)
    datos['contacto'] = _limpio(f.get('contacto'), 120)
    datos['telefono'] = _limpio(f.get('telefono'), 40)
    datos['email'] = _limpio(f.get('email'), 120).lower()
    if len(datos['contacto']) < 3:
        errores.append('El CONTACTO del proveedor es obligatorio.')
    if len(re.sub(r'\D', '', datos['telefono'])) < 6:
        errores.append('El TELÉFONO del proveedor es obligatorio (mínimo 6 dígitos).')
    if datos['email'] and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', datos['email']):
        errores.append('El correo del proveedor no es válido.')
    datos['oc_proveedor_id'] = f.get('oc_proveedor_id', type=int)
    datos['contacto_id'] = f.get('contacto_id', type=int)
    datos['cotizacion'] = _limpio(f.get('cotizacion'), 60).upper()
    moneda = 'USD' if es_imp else (f.get('moneda') or 'PEN').upper()
    if moneda not in MONEDAS_OC:
        errores.append('Moneda no válida.')
    datos['moneda'] = moneda
    datos['condiciones_comerciales'], datos['pagos_importacion'] = None, None
    if es_imp:
        cc = '\n'.join(' '.join(l.split()) for l in (f.get('condiciones_comerciales') or '').splitlines() if l.strip())
        datos['condiciones_comerciales'] = cc[:2000] or None
        pagos = []
        for t, pct in zip(f.getlist('pago_texto[]'), f.getlist('pago_pct[]') + [''] * 50):
            t = ' '.join((t or '').split())[:200]
            if not t:
                continue
            v = _num(pct) if (pct or '').strip() else None
            if (pct or '').strip() and (v is None or not 0 < v <= 100):
                errores.append(f'Condición de pago "{t[:40]}": el porcentaje debe estar entre 0.01 y 100.')
                v = None
            pagos.append({'texto': t, 'pct': round(v, 2) if v else None})
        if not pagos:
            errores.append('Escribe las CONDICIONES DE PAGO de la importación (ej. "Depósito" con 15%, y el saldo).')
        if sum(x['pct'] or 0 for x in pagos) > 100.0001:
            errores.append('Los porcentajes de pago suman más de 100%.')
        datos['pagos_importacion'] = json.dumps(pagos, ensure_ascii=False) if pagos else None
        datos['condicion_pago'] = ' · '.join(f"{x['texto']} {x['pct']:g}%" if x['pct'] else x['texto'] for x in pagos)[:120] or 'IMPORTACIÓN'
    else:
        condiciones = {v.valor for v in _oc_catalogo('OC_CONDICION_PAGO', incluir_inactivos=True)}
        cond = (f.get('condicion_pago') or '').strip()
        if cond not in condiciones and not (orden and cond == orden.condicion_pago):
            errores.append('Elige la condición de pago.')
        datos['condicion_pago'] = cond[:120]
    modo = (f.get('entrega_modo') or 'EMPRESA').upper()
    datos['entrega_modo'] = modo if modo in ('EMPRESA', 'RECOJO') else 'EMPRESA'
    datos['lugar_recojo'] = _limpio(f.get('lugar_recojo'), 250) if datos['entrega_modo'] == 'RECOJO' else None
    if datos['entrega_modo'] == 'RECOJO' and len(datos['lugar_recojo'] or '') < 5:
        errores.append('Si el material se recoge, escribe DÓNDE se recoge.')
    et = (f.get('entrega_tipo') or 'A_TRATAR').upper()
    datos['entrega_tipo'] = et if et in ('A_TRATAR', 'DIAS', 'FECHA') else 'A_TRATAR'
    datos['entrega_dias'], datos['fecha_entrega'] = None, None
    if datos['entrega_tipo'] == 'DIAS':
        dias = f.get('entrega_dias', type=int)
        if not dias or not 1 <= dias <= 365:
            errores.append('Los días de entrega deben estar entre 1 y 365.')
        datos['entrega_dias'] = dias
    elif datos['entrega_tipo'] == 'FECHA':
        try:
            datos['fecha_entrega'] = datetime.strptime((f.get('fecha_entrega') or '').strip(), '%Y-%m-%d').date()
            if fecha and datos['fecha_entrega'] < fecha:
                errores.append('La fecha de entrega no puede ser anterior a la fecha de la orden.')
        except ValueError:
            errores.append('Escribe la fecha de entrega.')
    datos['observaciones'] = ' '.join((f.get('observaciones') or '').split())[:500] or None
    # Quién lo pide y para qué
    datos.update(solicitante_user_id=None, solicitante_nombre=None)
    sol = (f.get('solicitante') or '').strip()
    if sol.startswith('u:') and sol[2:].isdigit():
        u = User.query.get(int(sol[2:]))
        if u and ((u.role in ROLES_SOLICITANTES_OC and not getattr(u, 'desactivado', False)) or (orden and orden.solicitante_user_id == u.id)):
            datos['solicitante_user_id'], datos['solicitante_nombre'] = u.id, (u.nombre_completo or u.username or '')[:120]
    elif sol.startswith('n:'):
        nombre = ' '.join(sol[2:].split()).upper()[:120]
        otros = {(v.valor or '').upper() for v in _oc_catalogo('OC_SOLICITANTE', incluir_inactivos=True)}
        if nombre and (nombre in otros or (orden and not orden.solicitante_user_id and (orden.solicitante_nombre or '').upper() == nombre)):
            datos['solicitante_nombre'] = nombre
    if not datos['solicitante_nombre']:
        errores.append('Elige QUIÉN SOLICITÓ la compra.')
    areas = {(v.valor or '').upper() for v in _oc_catalogo('OC_AREA', incluir_inactivos=True)}
    area = ' '.join((f.get('area_solicitante') or '').split()).upper()[:80]
    if area not in areas and not (orden and area and area == (orden.area_solicitante or '').upper()):
        errores.append('Elige el ÁREA que solicita.')
    datos['area_solicitante'] = area or None
    motivo = ' '.join((f.get('motivo_compra') or '').split()).upper()[:120]
    mot_obj = next((m for m in OCMotivoCompra.query.all() if (m.nombre or '').upper() == motivo), None)
    if not motivo or not ((mot_obj and mot_obj.activo) or (orden and motivo == (orden.motivo_compra or '').upper())):
        errores.append('Elige el MOTIVO de la compra (para qué es).')
    datos['motivo_compra'] = motivo or None
    datos['motivo_detalle'] = ' '.join((f.get('motivo_detalle') or '').split())[:300] or None
    pide_cliente = bool(mot_obj.pide_cliente) if mot_obj else bool((f.get('cliente_ruc') or '').strip())
    datos['cliente_ruc'], datos['cliente_razon'] = None, None
    if pide_cliente:
        cruc = _digitos(f.get('cliente_ruc'))
        crazon = _limpio(f.get('cliente_razon'), 200).upper()
        if len(cruc) not in (8, 11) or len(crazon) < 3:
            errores.append(f'Es "{motivo.title()}": escribe el RUC (o DNI) y la razón social del CLIENTE.')
        datos['cliente_ruc'], datos['cliente_razon'] = cruc[:20] or None, crazon or None
    # Compras para el inventario: el certificado de calidad es obligatorio al dar la conformidad
    datos['requiere_certificado'] = tipo == 'OC' and destino == 'GENERAL'
    # Detracción SUNAT (sugerida en servicios: 12%; se puede cambiar o quitar)
    datos['detraccion_pct'] = None
    if f.get('aplica_detraccion') == '1' and not es_imp:
        pct = _num(f.get('detraccion_pct'))
        if pct is None or not 0 < pct <= 100:
            errores.append('El porcentaje de detracción debe estar entre 0.01 y 100.')
        else:
            datos['detraccion_pct'] = round(pct, 2)
    # Ítems
    ums = {v.valor for v in _oc_catalogo('OC_UM', incluir_inactivos=True)}
    ums_previas = {i.um for i in orden.items} if orden else set()
    items = []
    n_filas = len(f.getlist('descripcion[]'))
    familias = f.getlist('familia[]') + [''] * n_filas
    calidades = f.getlist('calidad[]') + [''] * n_filas
    estados = f.getlist('estado_producto[]') + [''] * n_filas
    pesos_modo = f.getlist('peso_modo[]') + [''] * n_filas
    pesos_valor = f.getlist('peso_valor[]') + [''] * n_filas
    servicios = f.getlist('servicio[]') + [''] * n_filas
    req_items = f.getlist('req_item[]') + [''] * n_filas
    kgs_l = f.getlist('kgs_mpcs[]') + [''] * n_filas
    detalle_l = f.getlist('detalle[]') + [''] * n_filas
    piezas_l = f.getlist('piezas[]') + [''] * n_filas
    pmil_l = f.getlist('precio_mil[]') + [''] * n_filas
    por_pcs = (f.get('imp_precio_por') or '').upper() == 'PCS'     # formulario nuevo: precio de importación por pieza
    servicios_ok = {(v.valor or '').upper() for v in _oc_catalogo('OC_SERVICIO', incluir_inactivos=True)}
    servicios_ok |= {(i.tipo_servicio or '').upper() for i in orden.items} if orden else set()
    filas = zip(f.getlist('descripcion[]'), f.getlist('cantidad[]'), f.getlist('um[]'), f.getlist('precio_unitario[]'),
                f.getlist('origen[]'), f.getlist('codigo[]'), f.getlist('insumo_id[]'), familias, calidades, estados, pesos_modo, pesos_valor, servicios, req_items)
    req_usados = set()
    for n, (desc, cant, um, pu, origen, codigo, insumo_id, familia, calidad, estado_p, p_modo, p_valor, servicio, req_item) in enumerate(filas, start=1):
        desc = ' '.join((desc or '').split()).upper()[:400]
        if not desc and not (cant or '').strip() and not (pu or '').strip():
            continue
        cantidad, precio = _num(cant), _num(pu)
        kgs_mpcs, precio_mil = None, None
        if es_imp:
            # Importación: el precio se escribe en USD POR PIEZA (USD/PCS, como la factura comercial, hasta 7 decimales).
            # Órdenes antiguas: venía en USD por cada 1000 piezas (precio_mil); se sigue aceptando.
            kgs_mpcs = _num(kgs_l[n - 1]) if (kgs_l[n - 1] or '').strip() else None
            if por_pcs:
                if precio is None or precio < 0:
                    errores.append(f'Ítem {n}: escribe el precio en USD por pieza (USD/PCS).')
                    continue
            else:
                precio_mil = _num(pmil_l[n - 1]) if (pmil_l[n - 1] or '').strip() else None
                if precio_mil is None or precio_mil < 0:
                    errores.append(f'Ítem {n}: escribe el precio en USD por cada 1000 piezas.')
                    continue
                precio = precio_mil / 1000
            if kgs_mpcs is not None and not 0 <= kgs_mpcs <= 1_000_000:
                errores.append(f'Ítem {n}: los KGS por 1000 piezas no son válidos.')
                continue
            precio = round(precio, 7)
            precio_mil = round(precio * 1000, 4)
        precio_con = None
        if con_igv and precio is not None:
            precio_con, precio = precio, precio / (1 + IGV_OC)
        if len(desc) < 2:
            errores.append(f'Ítem {n}: escribe la descripción.')
            continue
        if cantidad is None or cantidad <= 0:
            errores.append(f'Ítem {n}: la cantidad debe ser mayor a 0.')
            continue
        if um not in ums and um not in ums_previas:
            errores.append(f'Ítem {n}: elige la unidad de medida.')
            continue
        if precio is None or precio < 0:
            errores.append(f'Ítem {n}: escribe el precio unitario (sin IGV).')
            continue
        servicio = ' '.join((servicio or '').split()).upper()[:80] if tipo == 'OS' else ''
        if tipo == 'OS' and servicio not in servicios_ok:
            errores.append(f'Ítem {n}: elige el TIPO DE SERVICIO (corte, roscado, galvanizado...).')
            continue
        ins_id = int(insumo_id) if (insumo_id or '').isdigit() and Insumo.query.get(int(insumo_id)) else None
        origen = (origen or '').upper()
        origen = origen if origen in ('ANCLAJES', 'IMPORTBOLTS', 'INSUMO') else None
        codigo = _limpio(codigo, 60) or None
        if origen == 'INSUMO' and not ins_id:
            origen, codigo = None, None
        # Compras: SOLO productos que ya existen (inventario de la empresa o maestro de insumos). Nada escrito a mano,
        # para que al llegar el ingreso quede enlazado. Se respetan los ítems antiguos que ya estaban así en la orden.
        if tipo == 'OC' and datos.get('destino') == 'GENERAL' and codigo and origen in ('ANCLAJES', 'IMPORTBOLTS') and origen != empresa:
            # se cambió de empresa: si el mismo código existe en el inventario de la otra, el producto se enlaza ahí
            ModeloOtra = ProductImportBolts if empresa == 'IMPORTBOLTS' else Product
            if ModeloOtra.query.filter(func.upper(ModeloOtra.sku) == codigo.upper()).first():
                origen = empresa
        if tipo == 'OC':
            legado = bool(orden) and any((x.descripcion or '').upper() == desc and (x.codigo or '') == (codigo or '') for x in orden.items)
            if datos.get('destino') == 'INSUMOS':
                if not ins_id and not legado:
                    errores.append(f'Ítem {n}: elige el insumo del maestro (botón Insumos). Si no existe, créalo con "Nuevo insumo (maestro)".')
                    continue
            elif datos.get('destino') == 'GENERAL' and not (legado and (orden.empresa or 'ANCLAJES') == empresa):   # si cambió de empresa se revisa todo
                ModeloInv = ProductImportBolts if empresa == 'IMPORTBOLTS' else Product
                existe = bool(codigo) and origen == empresa and ModeloInv.query.filter(func.upper(ModeloInv.sku) == codigo.upper()).first()
                if not existe:
                    errores.append(f'Ítem {n} ({desc[:40]}): elige el producto del inventario {EMPRESAS_OC[empresa]["corto"]} de la lista. '
                                   f'Si no existe, pide al encargado que lo cree en el Maestro (descripción, familia y calidad).')
                    continue
        # Producto NUEVO: una compra para el inventario de la empresa con un producto que ese inventario no tiene
        es_nuevo = tipo == 'OC' and datos.get('destino') == 'GENERAL' and origen != empresa
        # Peso (opcional): por unidad o total; se guarda también el otro calculado
        peso = _num(p_valor)
        p_modo = (p_modo or 'U').upper()[:1]
        peso_modo, peso_u, peso_t = None, None, None
        if peso is not None and (peso < 0 or peso > 1_000_000):
            errores.append(f'Ítem {n}: el peso no es válido.')
            continue
        if peso:
            peso_modo = 'T' if p_modo == 'T' else 'U'
            peso_u, peso_t = (round(peso / cantidad, 4), round(peso, 3)) if peso_modo == 'T' else (round(peso, 4), round(peso * cantidad, 3))
        if (um or '').upper() == 'KG':      # se compra (o se cobra el servicio) por kilo: el peso ES la cantidad
            peso_modo, peso_u, peso_t = 'U', 1.0, round(cantidad, 3)
        detalle_it = ' '.join((detalle_l[n - 1] or '').split())[:500] or None
        piezas_it = _num(piezas_l[n - 1]) if tipo == 'OS' and (piezas_l[n - 1] or '').strip() else None
        if piezas_it is not None and not 0 < piezas_it <= 100_000_000:
            errores.append(f'Ítem {n}: la cantidad de piezas no es válida.')
            continue
        if es_imp:      # importación: el peso sale de los KGS por millar (1000 piezas)
            peso_modo, peso_u, peso_t = ('U', round(kgs_mpcs / 1000, 6), round(cantidad * kgs_mpcs / 1000, 3)) if kgs_mpcs else (None, None, None)
        # Producto que vino de un requerimiento de Almacén: se valida que siga libre y que sea el mismo producto
        req_item_id = None
        if (req_item or '').isdigit():
            ri = RequerimientoItem.query.get(int(req_item))
            otro = None
            if ri:
                otro = next((oi for oi in OrdenCompraItem.query.filter(OrdenCompraItem.req_item_id == ri.id).all()
                             if oi.orden and oi.orden.estado not in ('ANULADA', 'RECHAZADA') and (not orden or oi.orden_id != orden.id)), None)
            if not ri or ri.requerimiento.estado != 'PENDIENTE' or (ri.requerimiento.empresa or 'ANCLAJES') not in (empresa, REQ_EMPRESA_LIBRE) \
                    or (ri.codigo or '').upper() != (codigo or '').upper() or tipo != 'OC':
                errores.append(f'Ítem {n}: ya no corresponde al requerimiento (cambió el producto, la empresa o el requerimiento se cerró). Quítalo y vuelve a jalarlo.')
                continue
            req_dest = ri.requerimiento.destino or 'GENERAL'
            if req_dest != datos.get('destino') or (req_dest == 'INSUMOS' and ri.insumo_id and ri.insumo_id != ins_id):
                errores.append(f'Ítem {n}: el {_req_codigo(ri.requerimiento)} es de '
                               + ('INSUMOS INTERNOS: la orden debe tener destino "Insumos internos".' if req_dest == 'INSUMOS'
                                  else 'productos del INVENTARIO GENERAL: la orden debe tener destino "Inventario General".'))
                continue
            if otro:
                errores.append(f'Ítem {n}: ese producto del {_req_codigo(ri.requerimiento)} ya está en la {_oc_codigo(otro.orden)}.')
                continue
            if ri.id in req_usados:
                errores.append(f'Ítem {n}: el mismo producto del requerimiento está dos veces.')
                continue
            req_usados.add(ri.id)
            req_item_id = ri.id
        total_con = round(cantidad * precio_con, 2) if con_igv else None
        if con_igv:
            totales_con_igv.append(total_con)
        items.append({'descripcion': desc, 'cantidad': round(cantidad, 4), 'um': um, 'precio_unitario': round(precio, 7 if es_imp else (6 if con_igv else 4)), 'req_item_id': req_item_id,
                      'precio_con_igv': round(precio_con, 4) if con_igv else None,
                      'total': round(total_con / (1 + IGV_OC), 2) if con_igv else round(cantidad * precio, 2), 'origen': origen, 'codigo': codigo, 'insumo_id': ins_id,
                      'kgs_mpcs': round(kgs_mpcs, 4) if kgs_mpcs is not None else None, 'precio_mil': round(precio_mil, 4) if es_imp else None,
                      'detalle': detalle_it, 'piezas': piezas_it,
                      'familia': _limpio(familia, 200) or None, 'calidad': _limpio(calidad, 200) or None,
                      'estado_producto': (_limpio(estado_p, 100) or None) if codigo else None, 'es_nuevo': es_nuevo,
                      'peso_modo': peso_modo, 'peso_unitario': peso_u, 'peso_total': peso_t, 'tipo_servicio': servicio or None})
    if not items:
        errores.append('Agrega al menos un ítem.')
    if len(items) > 60:
        errores.append('Máximo 60 ítems por orden.')
    if orden and orden.fecha_llegada:
        # lo que ya llegó no se puede quitar ni bajar de lo recibido
        rec = _oc_recepcion(orden)
        usados = set()
        for it in orden.items:
            llego = rec['items'][it.id]['llego']
            if llego <= 0:
                continue
            k = _oc_item_equivalente(it, items, usados)
            if k is None:
                errores.append(f'"{it.descripcion[:45]}" ya llegó ({_cant_txt(llego)} {it.um}): no se puede quitar de la orden ni cambiar de producto.')
                continue
            usados.add(k)
            if items[k]['cantidad'] < llego - 1e-9:
                errores.append(f'"{it.descripcion[:45]}": ya llegaron {_cant_txt(llego)} {it.um}; la cantidad no puede ser menor.')
    subtotal = round(sum(i['total'] for i in items), 2)
    datos['subtotal'] = subtotal
    datos['igv'] = 0.0 if es_imp else round(subtotal * IGV_OC, 2)
    datos['total'] = round(subtotal + datos['igv'], 2)
    if con_igv and items:
        # se parte del total CON IGV (como la factura) y el IGV es la diferencia: no se pierde ni se gana un céntimo
        datos['total'] = round(sum(totales_con_igv), 2)
        datos['igv'] = round(datos['total'] - subtotal, 2)
    return datos, items, errores


def _guardar_proveedor_oc(d):
    """Proveedor de la lista PROPIA de órdenes (se crea si se escribió a mano porque SUNAT no respondió)."""
    p = OCProveedor.query.get(d['oc_proveedor_id']) if d.get('oc_proveedor_id') else None
    if not p or (p.ruc or '') != d['ruc']:
        p = OCProveedor.query.filter(OCProveedor.ruc == d['ruc']).first()
    ahora = hora_peru()
    if not p:
        p = OCProveedor(ruc=d['ruc'], razon_social=d['razon_social'], direccion=d['direccion'] or None,
                        es_extranjero=bool(d.get('es_importacion')), creado_por=session.get('nombre', ''), fecha_creacion=ahora)
        db.session.add(p)
    elif not p.sunat_fecha:          # datos escritos a mano: se pueden corregir desde la orden
        p.razon_social = d['razon_social']
        p.direccion = d['direccion'] or p.direccion
    p.ultima_orden = ahora
    db.session.flush()
    return p


def _contacto_para_orden(prov, d):
    """El contacto elegido (o escrito) en la orden. Si no está en la lista del proveedor, se guarda solo."""
    ahora = hora_peru()
    c = OCContacto.query.get(d['contacto_id']) if d.get('contacto_id') else None
    if c and (c.oc_proveedor_id != prov.id or (c.nombre or '').upper() != d['contacto'].upper() or (c.telefono or '') != d['telefono']):
        c = None
    if not c:
        c = next((x for x in OCContacto.query.filter_by(oc_proveedor_id=prov.id).all()
                  if (x.nombre or '').upper() == d['contacto'].upper() and (x.telefono or '') == d['telefono']), None)
    if not c:
        c = OCContacto(oc_proveedor_id=prov.id, nombre=d['contacto'], telefono=d['telefono'], email=d['email'] or None, activo=True,
                       creado_por=session.get('nombre', ''), fecha_creacion=ahora, usos=0)
        db.session.add(c)
    if d['email'] and not c.email:
        c.email = d['email']
    c.activo = True
    c.usos = (c.usos or 0) + 1
    c.ultimo_uso = ahora
    db.session.flush()
    return c


def _oc_item_equivalente(viejo, nuevos, usados=()):
    """El ítem nuevo (al re-editar) que corresponde a uno viejo: mismo código, o misma descripción si no tenía código."""
    get = (lambda x, k: x.get(k)) if nuevos and isinstance(nuevos[0], dict) else (lambda x, k: getattr(x, k))
    for i, n in enumerate(nuevos):
        if i in usados:
            continue
        if (viejo.codigo and (get(n, 'codigo') or '').upper() == viejo.codigo.upper()) or \
                (not viejo.codigo and (get(n, 'descripcion') or '').upper() == (viejo.descripcion or '').upper()):
            return i
    return None


def _aplicar_datos_orden(orden, datos, items, prov, contacto=None):
    for campo in ('fecha', 'empresa', 'destino', 'ruc', 'razon_social', 'direccion', 'contacto', 'telefono', 'email', 'cotizacion', 'moneda',
                  'condicion_pago', 'entrega_modo', 'lugar_recojo', 'entrega_tipo', 'entrega_dias', 'fecha_entrega', 'observaciones',
                  'subtotal', 'igv', 'total', 'solicitante_user_id', 'solicitante_nombre', 'area_solicitante', 'motivo_compra', 'motivo_detalle',
                  'cliente_ruc', 'cliente_razon', 'requiere_certificado', 'detraccion_pct',
                  'es_importacion', 'condiciones_comerciales', 'pagos_importacion', 'precios_con_igv'):
        setattr(orden, campo, datos[campo] if datos[campo] != '' else None)
    orden.es_importacion = bool(datos.get('es_importacion'))
    orden.precios_con_igv = bool(datos.get('precios_con_igv'))
    orden.razon_social = datos['razon_social']
    orden.contacto, orden.telefono = datos['contacto'], datos['telefono']
    orden.oc_proveedor_id = prov.id
    orden.proveedor_id = None
    orden.contacto_id = contacto.id if contacto else None
    viejos = list(orden.items)
    entregas_items = [ei for e in _oc_entregas(orden) for ei in e.items] if orden.id else []
    for viejo in viejos:
        db.session.delete(viejo)
    db.session.flush()
    nuevos = []
    for n, it in enumerate(items, start=1):
        obj = OrdenCompraItem(orden_id=orden.id, item=n, **it)
        db.session.add(obj)
        nuevos.append(obj)
    if entregas_items:
        # re-edición con material ya recibido: lo que llegó sigue enlazado al ítem equivalente de la orden nueva
        db.session.flush()
        usados = set()
        for v in viejos:
            eis = [ei for ei in entregas_items if ei.item_id == v.id]
            if not eis and not v.cantidad_cancelada:
                continue
            k = _oc_item_equivalente(v, nuevos, usados)
            if k is None:
                continue
            usados.add(k)
            for ei in eis:
                ei.item_id = nuevos[k].id
            llego = sum(ei.cantidad or 0 for ei in eis)
            nuevos[k].cantidad_cancelada = min(v.cantidad_cancelada or 0, max((nuevos[k].cantidad or 0) - llego, 0))


def _req_avisar_orden(orden, antes):
    """Deja en el historial de cada requerimiento que Logística jaló sus productos a esta orden (o los quitó)."""
    db.session.flush()
    ahora_ids = {i.req_item_id for i in OrdenCompraItem.query.filter(OrdenCompraItem.orden_id == orden.id).all() if getattr(i, 'req_item_id', None)}
    for accion, ids in (('EN_OC', ahora_ids - antes), ('QUITADO_OC', antes - ahora_ids)):
        por_req = {}
        for ri in (RequerimientoItem.query.filter(RequerimientoItem.id.in_(list(ids))).all() if ids else []):
            por_req.setdefault(ri.requerimiento, []).append(ri)
        for r, lista in por_req.items():
            _req_evento(r, accion, (f"Logística los puso en la {_oc_codigo(orden)} ({orden.razon_social}): " if accion == 'EN_OC'
                                    else f"Se quitaron de la {_oc_codigo(orden)}: ") + ', '.join(x.codigo for x in lista))


def _resumen_cambios_orden(antes, orden):
    cambios = []
    for campo, etq in (('razon_social', 'Proveedor'), ('total', 'Total'), ('moneda', 'Moneda'), ('condicion_pago', 'Pago'),
                       ('destino', 'Destino'), ('entrega_modo', 'Entrega'), ('solicitante_nombre', 'Solicitó'), ('motivo_compra', 'Motivo'),
                       ('fecha_entrega', 'Fecha de entrega'), ('entrega_dias', 'Días de entrega'), ('lugar_recojo', 'Recojo')):
        if campo not in antes:
            continue
        a, d = antes.get(campo), getattr(orden, campo)
        if a != d and not (a in (None, '') and d in (None, '')):
            a_txt = f'{a:,.2f}' if isinstance(a, float) else (a.strftime('%d/%m/%Y') if hasattr(a, 'strftime') else a)
            d_txt = f'{d:,.2f}' if isinstance(d, float) else (d.strftime('%d/%m/%Y') if hasattr(d, 'strftime') else d)
            cambios.append(f"{etq}: {a_txt or '—'} → {d_txt or '—'}")
    return '; '.join(cambios)


def _resumen_cambios_items(antes, items):
    """Qué cambió en los ítems: 'antes' = [(descripción, cantidad, um, precio)], items = los nuevos (dicts)."""
    previos = {}
    for d, c, u, p in antes:
        previos.setdefault(d, (c, u, p))
    nuevos = {}
    for it in items:
        nuevos.setdefault(it['descripcion'], (it['cantidad'], it['um'], it['precio_unitario']))
    cambios = []
    for d, (c, u, p) in nuevos.items():
        if d not in previos:
            cambios.append(f"+ {d[:45]} ({_cant_txt(c)} {u} × {p:,.2f})")
        else:
            c0, u0, p0 = previos[d]
            partes = []
            if abs((c0 or 0) - (c or 0)) > 1e-9 or u0 != u:
                partes.append(f"cant. {_cant_txt(c0)} {u0} → {_cant_txt(c)} {u}")
            if abs((p0 or 0) - (p or 0)) > 1e-9:
                partes.append(f"precio {p0:,.2f} → {p:,.2f}")
            if partes:
                cambios.append(f"{d[:45]}: " + ', '.join(partes))
    for d in previos:
        if d not in nuevos:
            cambios.append(f"− quitó {d[:45]}")
    return '; '.join(cambios)


