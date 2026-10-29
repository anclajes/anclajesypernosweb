"""Modelos (tablas) de COMPRAS (órdenes de compra / servicio y requerimientos).
Se importan al final de models.py: "from models import X" sigue funcionando igual. Ver MAPA.md."""
from models import db, hora_peru

__all__ = ['OCProveedor', 'OCContacto', 'OCMotivoRechazo', 'OrdenCompra', 'OrdenCompraItem', 'OrdenCompraEntrega', 'OrdenCompraEntregaItem', 'OrdenCompraEvento', 'OrdenCompraDocumento', 'OCCuentaBancaria', 'OCMotivoCompra', 'RequerimientoCompra', 'RequerimientoItem', 'RequerimientoDocumento', 'RequerimientoVisto', 'RequerimientoEvento', 'OCConfig']


# =====================================================================================
# ÓRDENES DE COMPRA / ÓRDENES DE SERVICIO (Logística)
# =====================================================================================
class OCProveedor(db.Model):
    """Proveedores de ÓRDENES DE COMPRA (lista propia, separada de clientes y de otros proveedores del sistema).
    Se llena al consultar un RUC en SUNAT desde una orden."""
    __tablename__ = 'oc_proveedor'
    id = db.Column(db.Integer, primary_key=True)
    ruc = db.Column(db.String(20), index=True)
    razon_social = db.Column(db.String(200), nullable=False)
    direccion = db.Column(db.String(250))
    contacto = db.Column(db.String(120))      # (antiguo) hoy los contactos están en OCContacto
    telefono = db.Column(db.String(40))       # (antiguo)
    email = db.Column(db.String(120))         # (antiguo)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)   # ya no se usa
    sunat_estado = db.Column(db.String(50))
    sunat_condicion = db.Column(db.String(50))
    sunat_fecha = db.Column(db.DateTime, nullable=True)       # última consulta a SUNAT
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    actualizado_por = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, nullable=True)
    ultima_orden = db.Column(db.DateTime, nullable=True)
    es_extranjero = db.Column(db.Boolean, default=False)      # proveedor del exterior (importaciones): ruc = Tax ID
    pais = db.Column(db.String(60))


class OCContacto(db.Model):
    """Contactos de un proveedor de órdenes (nombre + teléfono + correo opcional). No se borran: se ARCHIVAN,
    para no perder el historial; Gerencia puede borrar definitivamente solo los que nunca se usaron."""
    __tablename__ = 'oc_contacto'
    id = db.Column(db.Integer, primary_key=True)
    oc_proveedor_id = db.Column(db.Integer, db.ForeignKey('oc_proveedor.id'), nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    telefono = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(120))
    cargo = db.Column(db.String(80))
    activo = db.Column(db.Boolean, default=True)
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    actualizado_por = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, nullable=True)
    archivado_por = db.Column(db.String(100))
    fecha_archivo = db.Column(db.DateTime, nullable=True)
    usos = db.Column(db.Integer, default=0)
    ultimo_uso = db.Column(db.DateTime, nullable=True)

    proveedor = db.relationship('OCProveedor', backref='contactos')


class OCMotivoRechazo(db.Model):
    """Motivos de rechazo de una orden, organizados por categoría (Configuración)."""
    __tablename__ = 'oc_motivo_rechazo'
    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(60), nullable=False)
    motivo = db.Column(db.String(150), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    uso = db.Column(db.String(10), default='RECHAZO')      # RECHAZO (Gerencia) / ANULACION
    aplica = db.Column(db.String(5), default='AMBAS')      # OC / OS / AMBAS


class OrdenCompra(db.Model):
    """Orden de Compra (OC) u Orden de Servicio (OS). Numeración correlativa propia por tipo.
    Flujo: BORRADOR -> ENVIADA (a Gerencia) -> APROBADA / RECHAZADA -> RECIBIDA (llegó) -> CONFORME.
    Se puede ANULAR (con motivo) mientras el material no haya llegado."""
    __tablename__ = 'orden_compra'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(2), nullable=False, default='OC')          # OC / OS
    numero = db.Column(db.Integer, nullable=False)
    empresa = db.Column(db.String(15), default='ANCLAJES')                # empresa que compra (y cuyo inventario recibe)
    fecha = db.Column(db.Date, nullable=False)
    estado = db.Column(db.String(12), nullable=False, default='BORRADOR', index=True)
    destino = db.Column(db.String(10), nullable=False, default='GENERAL')  # GENERAL / INSUMOS
    # Proveedor (copia de los datos al momento de la orden)
    oc_proveedor_id = db.Column(db.Integer, db.ForeignKey('oc_proveedor.id'), nullable=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    ruc = db.Column(db.String(20))
    razon_social = db.Column(db.String(200), nullable=False)
    direccion = db.Column(db.String(250))
    contacto = db.Column(db.String(120), nullable=False)
    telefono = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(120))
    contacto_id = db.Column(db.Integer, db.ForeignKey('oc_contacto.id'), nullable=True)
    cotizacion = db.Column(db.String(60))
    # Condiciones
    moneda = db.Column(db.String(3), nullable=False, default='PEN')       # PEN / USD
    condicion_pago = db.Column(db.String(120))
    entrega_modo = db.Column(db.String(10), nullable=False, default='EMPRESA')   # EMPRESA (llega) / RECOJO
    lugar_recojo = db.Column(db.String(250))
    entrega_tipo = db.Column(db.String(10), nullable=False, default='A_TRATAR')  # A_TRATAR / DIAS / FECHA
    entrega_dias = db.Column(db.Integer)
    fecha_entrega = db.Column(db.Date)
    observaciones = db.Column(db.String(500))
    subtotal = db.Column(db.Float, default=0)
    igv = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    # Auditoría del flujo
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=hora_peru)
    editado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_edicion = db.Column(db.DateTime, nullable=True)
    enviado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_envio = db.Column(db.DateTime, nullable=True)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_aprobacion = db.Column(db.DateTime, nullable=True)
    rechazado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_rechazo = db.Column(db.DateTime, nullable=True)
    motivo_rechazo = db.Column(db.String(300))          # detalle escrito
    rechazo_categoria = db.Column(db.String(60))
    rechazo_opcion = db.Column(db.String(150))
    anulado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_anulacion = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.String(300))           # descripción escrita
    anulacion_categoria = db.Column(db.String(60))
    anulacion_opcion = db.Column(db.String(150))
    detraccion_pct = db.Column(db.Float)                    # % de detracción SUNAT (vacío = no aplica)
    nota_seguimiento = db.Column(db.String(300))            # OS: nota de Almacén al marcar el seguimiento
    precios_con_igv = db.Column(db.Boolean, default=False)   # los precios se escribieron con IGV (cuadra con la factura)
    es_importacion = db.Column(db.Boolean, default=False)   # OC de importación: ítems por millar, sin IGV, pagos por porcentaje
    condiciones_comerciales = db.Column(db.Text)            # importación: incoterm, embarque, etc.
    pagos_importacion = db.Column(db.Text)                  # importación: JSON [{concepto, pct, detalle}]
    saldo_cerrado_motivo = db.Column(db.String(300))        # "no llegará el resto": por qué se cerró el saldo
    revision = db.Column(db.Integer, default=0)            # cuántas veces se editó DESPUÉS de aprobada (Rev. 1, Rev. 2...)
    motivo_edicion = db.Column(db.String(300))              # por qué se editó la orden ya aprobada (lo ve Gerencia al re-aprobar)
    # Recepción del material
    fecha_llegada = db.Column(db.DateTime, nullable=True)
    recibido_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    numero_guia = db.Column(db.String(60))
    numero_factura = db.Column(db.String(60))
    nota_recepcion = db.Column(db.String(500))
    conforme_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_conforme = db.Column(db.DateTime, nullable=True)
    nota_conforme = db.Column(db.String(500))
    # Seguimiento en inventarios
    insumo_ingreso_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso.id'), nullable=True)
    kardex_registrado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_kardex = db.Column(db.DateTime, nullable=True)
    duplicada_de_id = db.Column(db.Integer, nullable=True)
    # Quién pidió la compra y para qué
    solicitante_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    solicitante_nombre = db.Column(db.String(120))       # copia del nombre (o un nombre de la lista de Configuración)
    area_solicitante = db.Column(db.String(80))
    motivo_compra = db.Column(db.String(120))
    motivo_detalle = db.Column(db.String(300))
    cliente_ruc = db.Column(db.String(20))               # si es pedido de un cliente
    cliente_razon = db.Column(db.String(200))
    # Certificado de calidad obligatorio al dar conformidad (compras para el inventario)
    requiere_certificado = db.Column(db.Boolean, default=False)
    # Factura (para comparar con la orden y contar el crédito)
    fecha_factura = db.Column(db.Date)
    monto_factura = db.Column(db.Float)
    # Control de pago (después de la aprobación de Gerencia)
    estado_pago = db.Column(db.String(12), default='PENDIENTE')   # PENDIENTE / PAGADO
    fecha_pago = db.Column(db.Date)                      # fecha en que se pagó (la que indica quien marca)
    pagado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_marca_pago = db.Column(db.DateTime)            # cuándo se marcó como pagada (auditoría)
    pago_operacion = db.Column(db.String(80))
    pago_cuenta = db.Column(db.String(200))
    pago_nota = db.Column(db.String(300))

    items = db.relationship('OrdenCompraItem', backref='orden', order_by='OrdenCompraItem.item', cascade='all, delete-orphan')
    creado_por = db.relationship('User', foreign_keys=[creado_por_id])
    editado_por = db.relationship('User', foreign_keys=[editado_por_id])
    enviado_por = db.relationship('User', foreign_keys=[enviado_por_id])
    aprobado_por = db.relationship('User', foreign_keys=[aprobado_por_id])
    rechazado_por = db.relationship('User', foreign_keys=[rechazado_por_id])
    anulado_por = db.relationship('User', foreign_keys=[anulado_por_id])
    recibido_por = db.relationship('User', foreign_keys=[recibido_por_id])
    conforme_por = db.relationship('User', foreign_keys=[conforme_por_id])
    kardex_registrado_por = db.relationship('User', foreign_keys=[kardex_registrado_por_id])
    solicitante = db.relationship('User', foreign_keys=[solicitante_user_id])
    pagado_por = db.relationship('User', foreign_keys=[pagado_por_id])
    __table_args__ = (db.UniqueConstraint('empresa', 'tipo', 'numero', name='uq_orden_compra_emp_tipo_num'),)   # numeración propia por empresa


class OrdenCompraItem(db.Model):
    __tablename__ = 'orden_compra_item'
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False, index=True)
    item = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.String(400), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    um = db.Column(db.String(30), nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)      # SIN IGV
    total = db.Column(db.Float, nullable=False)                # SIN IGV
    origen = db.Column(db.String(12))                          # ANCLAJES / IMPORTBOLTS / INSUMO / vacío (escrito a mano)
    codigo = db.Column(db.String(60))                          # SKU o código del insumo
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=True)
    familia = db.Column(db.String(200))
    calidad = db.Column(db.String(200))
    estado_producto = db.Column(db.String(100))                # estado del producto en el inventario (nacional, oxidado...)
    es_nuevo = db.Column(db.Boolean, default=False)            # producto que NO está en el inventario: hay que crearlo
    # Peso (opcional): por unidad o total, como lo dé el proveedor. Se guardan los dos (el otro se calcula).
    tipo_servicio = db.Column(db.String(80))                   # solo en Órdenes de Servicio: CORTE, ROSCADO, GALVANIZADO...
    peso_modo = db.Column(db.String(1))                        # U = por unidad / T = total
    detalle = db.Column(db.String(500))                         # descripción adicional del ítem (sale debajo del producto)
    piezas = db.Column(db.Float)                                # OS: cantidad de piezas (solo informativo)
    precio_con_igv = db.Column(db.Float)                        # precio escrito CON IGV (órdenes con "precios incluyen IGV")
    peso_unitario = db.Column(db.Float)                        # kg por unidad
    peso_total = db.Column(db.Float)                           # kg del ítem
    # Ingreso al inventario (lo marca Almacén cuando hizo el movimiento en el Kardex)
    ingresado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_ingreso = db.Column(db.DateTime, nullable=True)
    sku_ingreso = db.Column(db.String(60))                     # SKU con el que se ingresó (obligatorio si era nuevo)
    nota_ingreso = db.Column(db.String(300))
    req_item_id = db.Column(db.Integer, index=True)            # ítem del requerimiento de Almacén que atiende (si vino de uno)
    cantidad_cancelada = db.Column(db.Float, default=0)        # saldo que ya no llegará (se cerró con motivo)
    kgs_mpcs = db.Column(db.Float)                             # importación: kg por cada 1000 piezas
    precio_mil = db.Column(db.Float)                           # importación: precio por cada 1000 piezas
    kardex_mov_id = db.Column(db.Integer)                      # movimiento del Kardex creado desde Ingresos pendientes
    cantidad_kardex = db.Column(db.Integer)                    # cantidad que entró al Kardex (puede diferir de la OC)

    ingresado_por = db.relationship('User', foreign_keys=[ingresado_por_id])


class OrdenCompraEntrega(db.Model):
    """Una llegada del material (puede haber varias: entregas parciales). Cada una con su fecha, su guía y su conformidad.
    Lo que se aprueba en cada conformidad pasa a "Ingresos pendientes" con la fecha y la guía de esa entrega."""
    __tablename__ = 'orden_compra_entrega'
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)                 # 1, 2, 3... dentro de la orden
    fecha = db.Column(db.DateTime, nullable=False)                 # cuándo llegó
    parcial = db.Column(db.Boolean, default=False)                 # quedó saldo por llegar después de esta entrega
    numero_guia = db.Column(db.String(60))
    nota = db.Column(db.String(500))
    recibido_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=hora_peru)
    conforme_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_conforme = db.Column(db.DateTime, nullable=True)
    nota_conforme = db.Column(db.String(500))

    items = db.relationship('OrdenCompraEntregaItem', backref='entrega', cascade='all, delete-orphan', order_by='OrdenCompraEntregaItem.id')
    recibido_por = db.relationship('User', foreign_keys=[recibido_por_id])
    conforme_por = db.relationship('User', foreign_keys=[conforme_por_id])


class OrdenCompraEntregaItem(db.Model):
    """Cuánto llegó de un ítem en una entrega, y su ingreso al inventario (Kardex)."""
    __tablename__ = 'orden_compra_entrega_item'
    id = db.Column(db.Integer, primary_key=True)
    entrega_id = db.Column(db.Integer, db.ForeignKey('orden_compra_entrega.id'), nullable=False, index=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)   # OrdenCompraItem (sin FK: al re-editar la orden se vuelve a enlazar)
    cantidad = db.Column(db.Float, nullable=False)
    ingresado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_ingreso = db.Column(db.DateTime, nullable=True)
    sku_ingreso = db.Column(db.String(60))
    nota_ingreso = db.Column(db.String(300))
    kardex_mov_id = db.Column(db.Integer)
    cantidad_kardex = db.Column(db.Integer)

    ingresado_por = db.relationship('User', foreign_keys=[ingresado_por_id])


class OrdenCompraEvento(db.Model):
    """Historial (auditoría) de cada orden: quién hizo qué y cuándo."""
    __tablename__ = 'orden_compra_evento'
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False, index=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    accion = db.Column(db.String(20), nullable=False)
    detalle = db.Column(db.String(500))

    usuario = db.relationship('User')


class OrdenCompraDocumento(db.Model):
    """Guía, factura u otros documentos de la orden (PDF o foto en S3)."""
    __tablename__ = 'orden_compra_documento'
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'), nullable=False, index=True)
    tipo = db.Column(db.String(15), nullable=False)           # GUIA / FACTURA / COTIZACION / OTRO
    entrega_id = db.Column(db.Integer, nullable=True, index=True)   # la guía es de UNA entrega (llegadas parciales)
    s3_key = db.Column(db.String(300), nullable=False)
    nombre_original = db.Column(db.String(200))
    content_type = db.Column(db.String(50))
    tamano_bytes = db.Column(db.Integer)
    subido_por = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=hora_peru)


class OCCuentaBancaria(db.Model):
    """Cuentas bancarias de un proveedor de órdenes (cuenta, CCI o cuenta de detracciones). Se archivan, no se borran si se usaron."""
    __tablename__ = 'oc_cuenta_bancaria'
    id = db.Column(db.Integer, primary_key=True)
    oc_proveedor_id = db.Column(db.Integer, db.ForeignKey('oc_proveedor.id'), nullable=False, index=True)
    banco = db.Column(db.String(20), nullable=False)          # BCP / INTERBANK / SCOTIABANK / BBVA / NACION / OTRO
    banco_otro = db.Column(db.String(80))                     # nombre del banco si es OTRO
    tipo = db.Column(db.String(12), nullable=False)           # CUENTA / CCI / DETRACCION
    moneda = db.Column(db.String(3), default='PEN')           # PEN / USD
    numero = db.Column(db.String(40), nullable=False)
    titular = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    actualizado_por = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime)
    archivado_por = db.Column(db.String(100))
    fecha_archivo = db.Column(db.DateTime)


class OCMotivoCompra(db.Model):
    """Para qué se compra (reposición de stock, pedido de cliente, uso interno...). Configurable."""
    __tablename__ = 'oc_motivo_compra'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    pide_cliente = db.Column(db.Boolean, default=False)       # si se elige, se pide RUC y razón social del cliente
    activo = db.Column(db.Boolean, default=True)


class RequerimientoCompra(db.Model):
    """Pedido de productos que faltan (lo hace Almacén u otra área) para que Logística arme la Orden de Compra.
    El avance (en OC, aprobada, llegó, conforme, ingresado) se calcula de las órdenes enlazadas a cada ítem."""
    __tablename__ = 'requerimiento_compra'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False, unique=True)
    empresa = db.Column(db.String(15), nullable=False, default='ANCLAJES')     # inventario al que hacen falta
    destino = db.Column(db.String(10), default='GENERAL')      # GENERAL (productos del inventario) / INSUMOS (insumos internos)
    estado = db.Column(db.String(12), nullable=False, default='PENDIENTE', index=True)   # PENDIENTE / RECHAZADO / ANULADO (el resto se calcula)
    prioridad = db.Column(db.String(10), default='NORMAL')                      # NORMAL / URGENTE
    fecha_registro = db.Column(db.DateTime, default=hora_peru)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)     # quién lo registró (la cuenta)
    solicitante_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   # quién lo pide (vendedor, trabajador...)
    solicitante_nombre = db.Column(db.String(120))
    area = db.Column(db.String(80))
    motivo = db.Column(db.String(120))
    cliente_ruc = db.Column(db.String(20))
    cliente_razon = db.Column(db.String(200))
    oc_cliente = db.Column(db.String(60))              # N° de la orden de compra del CLIENTE
    necesita_para = db.Column(db.Date)
    nota = db.Column(db.String(500))
    rechazado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_rechazo = db.Column(db.DateTime)
    motivo_rechazo = db.Column(db.String(300))                 # descripción escrita
    rechazo_categoria = db.Column(db.String(60))
    rechazo_opcion = db.Column(db.String(150))
    anulado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_anulacion = db.Column(db.DateTime)
    motivo_anulacion = db.Column(db.String(300))
    anulacion_categoria = db.Column(db.String(60))
    anulacion_opcion = db.Column(db.String(150))

    items = db.relationship('RequerimientoItem', backref='requerimiento', order_by='RequerimientoItem.item', cascade='all, delete-orphan')
    creado_por = db.relationship('User', foreign_keys=[creado_por_id])
    solicitante = db.relationship('User', foreign_keys=[solicitante_user_id])
    rechazado_por = db.relationship('User', foreign_keys=[rechazado_por_id])
    anulado_por = db.relationship('User', foreign_keys=[anulado_por_id])


class RequerimientoItem(db.Model):
    __tablename__ = 'requerimiento_item'
    id = db.Column(db.Integer, primary_key=True)
    req_id = db.Column(db.Integer, db.ForeignKey('requerimiento_compra.id'), nullable=False, index=True)
    item = db.Column(db.Integer, nullable=False)
    codigo = db.Column(db.String(60), nullable=False)          # SKU del inventario de la empresa (o código del insumo)
    insumo_id = db.Column(db.Integer, nullable=True)            # si el requerimiento es de INSUMOS internos: el insumo del maestro
    descripcion = db.Column(db.String(400), nullable=False)
    familia = db.Column(db.String(200))
    calidad = db.Column(db.String(200))
    um = db.Column(db.String(30))
    cantidad = db.Column(db.Float, nullable=False)
    nota = db.Column(db.String(200))
    stock_al_pedir = db.Column(db.Integer)                     # stock que había cuando se pidió
    # Logística puede DESCARTAR un producto (no se comprará) con motivo; el requerimiento se cierra cuando todo está comprado o descartado
    descartado = db.Column(db.Boolean, default=False)
    descartado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_descarte = db.Column(db.DateTime)
    descarte_categoria = db.Column(db.String(60))
    descarte_opcion = db.Column(db.String(150))
    descarte_motivo = db.Column(db.String(300))

    descartado_por = db.relationship('User', foreign_keys=[descartado_por_id])


class RequerimientoDocumento(db.Model):
    """OC del cliente u otro sustento (PDF o foto)."""
    __tablename__ = 'requerimiento_documento'
    id = db.Column(db.Integer, primary_key=True)
    req_id = db.Column(db.Integer, db.ForeignKey('requerimiento_compra.id'), nullable=False, index=True)
    s3_key = db.Column(db.String(300), nullable=False)
    nombre_original = db.Column(db.String(200))
    content_type = db.Column(db.String(50))
    tamano_bytes = db.Column(db.Integer)
    subido_por = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=hora_peru)


class RequerimientoVisto(db.Model):
    """Hasta cuándo vio cada usuario un requerimiento (para avisarle de las novedades)."""
    __tablename__ = 'requerimiento_visto'
    id = db.Column(db.Integer, primary_key=True)
    req_id = db.Column(db.Integer, db.ForeignKey('requerimiento_compra.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    __table_args__ = (db.UniqueConstraint('req_id', 'user_id', name='uq_requerimiento_visto'),)


class RequerimientoEvento(db.Model):
    __tablename__ = 'requerimiento_evento'
    id = db.Column(db.Integer, primary_key=True)
    req_id = db.Column(db.Integer, db.ForeignKey('requerimiento_compra.id'), nullable=False, index=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    accion = db.Column(db.String(20), nullable=False)
    detalle = db.Column(db.String(500))

    usuario = db.relationship('User')


class OCConfig(db.Model):
    """Datos de la empresa y textos del PDF de órdenes (términos, horario...), editables en Configuración."""
    __tablename__ = 'oc_config'
    clave = db.Column(db.String(40), primary_key=True)
    valor = db.Column(db.Text)
    actualizado_por = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=hora_peru)
