from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz


def hora_peru():
    # Obtiene la hora exacta de Lima, pero le quita la 'etiqueta' de zona horaria (.replace)
    # para que sea 100% compatible con la base de datos (offset-naive)
    return datetime.now(pytz.timezone('America/Lima')).replace(tzinfo=None)

db = SQLAlchemy()   

# --- 1. CATEGORÍAS ---
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    prefijo = db.Column(db.String(5), unique=True, nullable=False) 
    contador = db.Column(db.Integer, default=0) 

# --- 2. USUARIOS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(100), nullable=False) 
    role = db.Column(db.String(20), nullable=False) 
    celular = db.Column(db.String(20))
    cargo_formal = db.Column(db.String(100)) # NUEVO
    email_empresa = db.Column(db.String(100)) # NUEVO

# --- 3. PRODUCTOS ---
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False) 
    nombre = db.Column(db.String(500), nullable=False) 
    categoria = db.Column(db.String(200), nullable=False) 
    calidad = db.Column(db.String(200)) 
    ubicacion = db.Column(db.String(200))
    stock_actual = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=10)
    
    unidades_por_caja = db.Column(db.Integer, default=100)
    precio_unidad = db.Column(db.Float, default=0.0)
    precio_docena = db.Column(db.Float, default=0.0)
    precio_caja = db.Column(db.Float, default=0.0)
    costo_referencial = db.Column(db.Float, default=0.0)

    estado = db.Column(db.String(100), nullable=True) # Para: oxidado, abierto, etc.
    fecha_actualizacion = db.Column(db.DateTime, nullable=True) # Cuándo se subió
    actualizado_por = db.Column(db.String(100), nullable=True) # Quién subió el Excel

    es_shadow_importbolts = db.Column(db.Boolean, default=False)
    shadow_origen_sku = db.Column(db.String(50), nullable=True)
    peso_kg = db.Column(db.Float, default=0.0)  # Peso unitario en Kilogramos
    activo = db.Column(db.Boolean, default=True, nullable=False)  # Desactivar en vez de eliminar
    ultimo_ajuste_auditoria_fecha = db.Column(db.DateTime, nullable=True)
    ultimo_ajuste_auditoria_por = db.Column(db.String(100), nullable=True)
    ultimo_ajuste_auditoria_conteo_por = db.Column(db.String(100), nullable=True)  # quién hizo el CONTEO físico


# --- 4. KARDEX ---
class ProductMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tipo = db.Column(db.String(10)) 
    cantidad = db.Column(db.Integer, nullable=False)
    stock_anterior = db.Column(db.Integer)
    stock_nuevo = db.Column(db.Integer)
    motivo = db.Column(db.String(200))

        # --- NUEVO: datos del proveedor/destino, guardados como snapshot histórico ---
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    ruc_proveedor = db.Column(db.String(20), nullable=True)
    razon_social_proveedor = db.Column(db.String(200), nullable=True)
    tipo_proveedor = db.Column(db.String(15), nullable=True)  # NACIONAL / INTERNACIONAL
    precio_unitario = db.Column(db.Float, nullable=True)  # solo Ingresos
    presentacion = db.Column(db.String(50), nullable=True)  # Metros, Kg, Unidades...
    motivo_id = db.Column(db.Integer, db.ForeignKey('motivo_movimiento.id'), nullable=True)

    proveedor = db.relationship('Proveedor')

    product = db.relationship('Product', backref='movements')
    user = db.relationship('User', backref='movements')

# --- 5. CLIENTES ---
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    documento = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    estado = db.Column(db.String(50), default='ACTIVO')      
    condicion = db.Column(db.String(50), default='HABIDO')

# ---> NUEVOS CAMPOS GEOGRÁFICOS <---
    ubigeo = db.Column(db.String(10), nullable=True)
    distrito = db.Column(db.String(100), nullable=True)
    provincia = db.Column(db.String(100), nullable=True)
    departamento = db.Column(db.String(100), nullable=True)

        # ---> NUEVOS CAMPOS MANUALES (billetera de cliente) <---
    area = db.Column(db.String(150), nullable=True)      # Ej: Logística, Compras, Obras
    correo = db.Column(db.String(150), nullable=True)     # Email de contacto
    rubro = db.Column(db.String(150), nullable=True) 
    contacto_nombre = db.Column(db.String(150), nullable=True)  

        # --- NUEVO: DUEÑO DEL REGISTRO (para separar la Billetera por vendedor) ---
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creado_por = db.relationship('User', foreign_keys=[creado_por_id], backref='clientes_creados')

    last_updated = db.Column(db.DateTime, default=hora_peru)
    updated_by = db.Column(db.String(50), default='Sistema')

# --- NUEVO: CONTACTOS ADICIONALES POR CLIENTE ---
class ClientContact(db.Model):
    __tablename__ = 'client_contact'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(20))
    area = db.Column(db.String(150))
    correo = db.Column(db.String(150))
        # --- NUEVO: dueño del contacto (separación por vendedor) ---
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creado_por = db.relationship('User', foreign_keys=[creado_por_id])

    created_at = db.Column(db.DateTime, default=hora_peru)
    created_by = db.Column(db.String(50), default='Sistema')

    client = db.relationship('Client', backref=db.backref('contactos_adicionales', cascade="all, delete-orphan"))

# --- NUEVO: AUDITORÍA DE CONTACTOS (sobrevive aunque se borre el contacto) ---
class ClientContactLog(db.Model):
    __tablename__ = 'client_contact_log'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    contact_id = db.Column(db.Integer, nullable=True)  # referencia informativa, no FK (puede ya no existir)
    
    accion = db.Column(db.String(20), nullable=False)  # CREADO, EDITADO, ELIMINADO
    
    # Snapshot de los datos en el momento de la acción
    nombre = db.Column(db.String(150))
    telefono = db.Column(db.String(20))
    area = db.Column(db.String(150))
    correo = db.Column(db.String(150))
    
    # Para EDITADO: qué tenía antes (útil para ver el cambio exacto)
    nombre_anterior = db.Column(db.String(150), nullable=True)
    telefono_anterior = db.Column(db.String(20), nullable=True)
    area_anterior = db.Column(db.String(150), nullable=True)
    correo_anterior = db.Column(db.String(150), nullable=True)
    
    realizado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    realizado_por = db.relationship('User', foreign_keys=[realizado_por_id])
    fecha = db.Column(db.DateTime, default=hora_peru)
    
    client = db.relationship('Client', backref='contact_logs')

# --- NUEVO: RUBRO POR VENDEDOR (cada vendedor tiene su propia clasificación del cliente) ---
class ClientRubroVendedor(db.Model):
    __tablename__ = 'client_rubro_vendedor'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rubro = db.Column(db.String(150), nullable=True)
    updated_at = db.Column(db.DateTime, default=hora_peru)
    
    client = db.relationship('Client', backref='rubros_por_vendedor')
    vendedor = db.relationship('User', foreign_keys=[vendedor_id])
    
    __table_args__ = (db.UniqueConstraint('client_id', 'vendedor_id', name='uq_client_vendedor_rubro'),)

# EN MODELS.PY

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    
    # --- CLAVES FORÁNEAS ---
    cliente_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    
    # Aquí están los dos caminos a User:
    vendedor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chofer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Nuevo

    origen_inventario = db.Column(db.String(20), default='ANCLAJES')  # 'ANCLAJES' o 'IMPORTBOLTS'
    
    # --- ESTADOS Y DATOS GENERALES ---
    estado = db.Column(db.String(50), default='Pendiente')
    atencion = db.Column(db.String(100)) 
    orden_compra = db.Column(db.String(50)) # O/C del Cliente (Texto manual)
    archivo_oc = db.Column(db.String(255))  # Nombre del archivo PDF (OC_xxx.pdf)
    

    # --- DATOS DE COTIZACIÓN ---
    condicion_pago = db.Column(db.String(50))
    validez_oferta = db.Column(db.String(50))
    plazo_entrega_texto = db.Column(db.String(100))
    observacion = db.Column(db.Text) # Nota del Vendedor (Logística)
    motivo_rechazo = db.Column(db.Text) # Nota del Gerente (Rechazo)

# --- RASTREO Y LÍNEA DE TIEMPO (NUEVOS CAMPOS) ---
    cliente_confirmado = db.Column(db.Boolean, default=False)
    fecha_confirmacion_cliente = db.Column(db.DateTime, nullable=True)
    
    fecha_verificacion_almacen = db.Column(db.DateTime, nullable=True)
    almacenero_nombre = db.Column(db.String(100), nullable=True)
    
    # 2. NUEVO CAMPO: REVISIÓN INICIAL DE GERENCIA
    fecha_revision_inicial = db.Column(db.DateTime, nullable=True)
    revisor_inicial_nombre = db.Column(db.String(100), nullable=True)
    
    # 3. APROBACIÓN FINAL DE GERENCIA (Con Orden de Compra)
    fecha_aprobacion = db.Column(db.DateTime, nullable=True) 
    gerente_nombre = db.Column(db.String(100), nullable=True)

    agencia = db.Column(db.String(150), nullable=True)
    control_calidad = db.Column(db.String(2), default='NO') # Guardará 'SI' o 'NO'
    penalidad = db.Column(db.String(2), default='NO')       # Guardará 'SI' o 'NO'

    # --- DATOS MONETARIOS ---
    moneda = db.Column(db.String(5), default='PEN') 
    tipo_cambio = db.Column(db.Float, default=1.0)  
    subtotal = db.Column(db.Float, default=0.0)
    igv = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    
    # --- DESCUENTOS ---
    descuento_tipo = db.Column(db.String(10), default='MONTO') 
    descuento_valor = db.Column(db.Float, default=0.0)         
    descuento_total = db.Column(db.Float, default=0.0)         

    # --- DATOS DE ENTREGA / LOGÍSTICA ---
    tipo_entrega = db.Column(db.String(20)) 
    direccion_envio = db.Column(db.String(200))
    fecha_entrega = db.Column(db.Date)

    fecha_devolucion = db.Column(db.DateTime, nullable=True)

    # NUEVO CAMPO: Días hábiles de entrega
    dias_habiles_entrega = db.Column(db.Integer, nullable=True)
    
    # Datos de Almacén (Nuevos)
    peso_total = db.Column(db.String(50))      
    cantidad_bultos = db.Column(db.String(50)) 
    
    # --- ESTADO DE PAGO ---
    monto_pagado = db.Column(db.Float, default=0.0)
    estado_pago = db.Column(db.String(20), default='Pendiente') 

    categoria_cancelacion = db.Column(db.String(100), nullable=True) # Ej: 'Precio muy alto'
    detalle_cancelacion = db.Column(db.Text, nullable=True) # Para cuando eligen "Otro"
    fecha_cancelacion = db.Column(db.DateTime, nullable=True)
    usuario_cancela_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    motivo_anulacion = db.Column(db.String(255), nullable=True)
    motivo_devolucion = db.Column(db.String(255), nullable=True)
    
    # --- RELACIONES (AQUÍ ESTÁ LA CORRECCIÓN DEL ERROR) ---
    
    cliente = db.relationship('Client', backref='orders')
    
    # 1. Relación VENDEDOR: Especificamos explícitamente que use 'vendedor_id'
    vendedor = db.relationship('User', 
                               foreign_keys=[vendedor_id], 
                               backref='ventas_realizadas') # Cambié el backref para ser más claro

    # 2. Relación CHOFER: Especificamos explícitamente que use 'chofer_id'
    chofer = db.relationship('User', 
                             foreign_keys=[chofer_id], 
                             backref='envios_asignados')
    
    # Relación con detalles (Items)
    # details = db.relationship('OrderDetail', backref='order', cascade="all, delete-orphan") 
    # (Asumo que esta línea la tienes en tu código original o en OrderDetail, si no, agrégala)

# --- 7. DETALLE DE ORDEN (Aquí estaba el problema) ---
class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    
    # Puede ser NULL si es Fabricación o GLB puro
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)

    origen_inventario = db.Column(db.String(20), default='ANCLAJES')  # 'ANCLAJES' o 'IMPORTBOLTS'
    product_id_importbolts = db.Column(db.Integer, db.ForeignKey('product_importbolts.id'), nullable=True)
    product_importbolts = db.relationship('ProductImportBolts')
    
    # Nuevos campos para manejar tipos
    item_type = db.Column(db.String(20), default='PRODUCTO') # PRODUCTO, FABRICACION, GLB
    
    cantidad = db.Column(db.Integer, nullable=False)
    precio_aplicado = db.Column(db.Float, nullable=False)

    precio_catalogo_sistema = db.Column(db.Float, nullable=True, default=0.0)

    tipo_precio_usado = db.Column(db.String(50))
    subtotal = db.Column(db.Float, nullable=False)

    # --- NUEVOS CAMPOS (MEMORIA DE DESCUENTOS INDIVIDUALES) ---
    precio_base = db.Column(db.Float, nullable=True)
    desc_tipo = db.Column(db.String(10), default='')
    desc_valor = db.Column(db.Float, default=0.0)
    desc_label = db.Column(db.String(100), default='')
    # ----------------------------------------------------------
    
    product = db.relationship('Product')
    
    # ¡ESTA LÍNEA FALTABA! Sin ella, orden.details da error
    order = db.relationship('Order', backref='details')

    @property
    def producto(self):
        """Devuelve el producto real sin importar el inventario de origen (Anclajes o ImportBolts)."""
        if self.origen_inventario == 'IMPORTBOLTS':
            return self.product_importbolts
        return self.product     
    
    # Relación con componentes del kit
    kit_components = db.relationship('OrderKitComponent', backref='parent_detail', cascade="all, delete-orphan")

    nombre_personalizado = db.Column(db.String(200)) # Este guardará la descripción NORMAL
    
    # NUEVO CAMPO:
    nombre_personalizado_titulo = db.Column(db.String(200)) # Este guardará la parte en NEGRITA
    check_almacen = db.Column(db.Boolean, default=False)

class IntercompanyTransfer(db.Model):
    __tablename__ = 'intercompany_transfer'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    order_detail_id = db.Column(db.Integer, db.ForeignKey('order_detail.id'), nullable=False)
    product_importbolts_id = db.Column(db.Integer, db.ForeignKey('product_importbolts.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    fecha_despacho = db.Column(db.DateTime, default=hora_peru)
    despachado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    estado_facturacion = db.Column(db.String(30), default='PENDIENTE')
    fecha_facturacion = db.Column(db.DateTime, nullable=True)
    facturado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    numero_documento_externo = db.Column(db.String(100), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    
    order = db.relationship('Order', backref='traslados_intercompany')
    order_detail = db.relationship('OrderDetail')
    product_importbolts = db.relationship('ProductImportBolts')
    despachado_por = db.relationship('User', foreign_keys=[despachado_por_id])
    facturado_por = db.relationship('User', foreign_keys=[facturado_por_id])

# --- 8. COMPONENTES DE KIT (GLB) ---
class OrderKitComponent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_detail_id = db.Column(db.Integer, db.ForeignKey('order_detail.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False) 
    cantidad_requerida = db.Column(db.Integer, nullable=False)

    product = db.relationship('Product')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    metodo = db.Column(db.String(50))
    nota = db.Column(db.String(200))
    
    order = db.relationship('Order', backref='payments')

class SystemConfig(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255))               
    updated_at = db.Column(db.DateTime, default=hora_peru)
    updated_by = db.Column(db.String(50), default='Sistema')

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    accion = db.Column(db.String(255), nullable=False)
    fecha = db.Column(db.DateTime, default=hora_peru)
    icono = db.Column(db.String(50), default='bi-info-circle')
    color = db.Column(db.String(20), default='text-primary')
    
    usuario = db.relationship('User', backref=db.backref('logs', lazy=True))

# --- TABLAS EXCLUSIVAS PARA IMPORTBOLTS ---

class CategoryImportBolts(db.Model):
    __tablename__ = 'category_importbolts'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    prefijo = db.Column(db.String(5), unique=True, nullable=False) 
    contador = db.Column(db.Integer, default=0) 

class ProductImportBolts(db.Model):
    __tablename__ = 'product_importbolts'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False) 
    nombre = db.Column(db.String(500), nullable=False) 
    categoria = db.Column(db.String(200), nullable=False) 
    calidad = db.Column(db.String(200)) 
    ubicacion = db.Column(db.String(200))
    stock_actual = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=10)
    
    unidades_por_caja = db.Column(db.Integer, default=100)
    precio_unidad = db.Column(db.Float, default=0.0)
    precio_docena = db.Column(db.Float, default=0.0)
    precio_caja = db.Column(db.Float, default=0.0)
    costo_referencial = db.Column(db.Float, default=0.0)

    estado = db.Column(db.String(100), nullable=True) 
    fecha_actualizacion = db.Column(db.DateTime, nullable=True) 
    actualizado_por = db.Column(db.String(100), nullable=True) 
    peso_kg = db.Column(db.Float, default=0.0)  # Peso unitario en Kilogramos
    activo = db.Column(db.Boolean, default=True, nullable=False)  # Desactivar en vez de eliminar
    ultimo_ajuste_auditoria_fecha = db.Column(db.DateTime, nullable=True)
    ultimo_ajuste_auditoria_por = db.Column(db.String(100), nullable=True)
    ultimo_ajuste_auditoria_conteo_por = db.Column(db.String(100), nullable=True)  # quién hizo el CONTEO físico

class ProductMovementImportBolts(db.Model):
    __tablename__ = 'product_movement_importbolts'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    product_id = db.Column(db.Integer, db.ForeignKey('product_importbolts.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Usa el mismo User general
    tipo = db.Column(db.String(10)) 
    cantidad = db.Column(db.Integer, nullable=False)
    stock_anterior = db.Column(db.Integer)
    stock_nuevo = db.Column(db.Integer)
    motivo = db.Column(db.String(200))

        # --- NUEVO: datos del proveedor/destino, guardados como snapshot histórico ---
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    ruc_proveedor = db.Column(db.String(20), nullable=True)
    razon_social_proveedor = db.Column(db.String(200), nullable=True)
    tipo_proveedor = db.Column(db.String(15), nullable=True)  # NACIONAL / INTERNACIONAL
    precio_unitario = db.Column(db.Float, nullable=True)  # solo Ingresos
    presentacion = db.Column(db.String(50), nullable=True)  # Metros, Kg, Unidades...
    motivo_id = db.Column(db.Integer, db.ForeignKey('motivo_movimiento.id'), nullable=True)

    proveedor = db.relationship('Proveedor')

    product = db.relationship('ProductImportBolts', backref='movements')
    user = db.relationship('User', backref='movements_importbolts')

class MetaVendedor(db.Model):
    """Meta de venta mensual por vendedor. Si no se define una meta para un mes específico,
    el sistema usa automáticamente la última meta definida (queda 'guardada por defecto')."""
    __tablename__ = 'meta_vendedor'
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    monto_meta = db.Column(db.Float, nullable=False, default=0.0)
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    actualizado_en = db.Column(db.DateTime, default=hora_peru)

    vendedor = db.relationship('User', foreign_keys=[vendedor_id])
    actualizado_por = db.relationship('User', foreign_keys=[actualizado_por_id])

    __table_args__ = (db.UniqueConstraint('vendedor_id', 'anio', 'mes', name='uq_meta_vendedor_periodo'),)

class ProductImage(db.Model):
    __tablename__ = 'product_image'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    product_importbolts_id = db.Column(db.Integer, db.ForeignKey('product_importbolts.id'), nullable=True)
    origen_inventario = db.Column(db.String(20), nullable=False, default='ANCLAJES')
    url_s3 = db.Column(db.String(500), nullable=False)
    s3_key = db.Column(db.String(500), nullable=False)  # para poder borrarla de S3 después
    subido_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_subida = db.Column(db.DateTime, default=hora_peru)

    subido_por = db.relationship('User')

# --- MOTIVOS DE MOVIMIENTO (predeterminados + agregados por admin) ---
class MotivoMovimiento(db.Model):
    __tablename__ = 'motivo_movimiento'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'ENTRADA' o 'SALIDA'
    activo = db.Column(db.Boolean, default=True)
    es_predeterminado = db.Column(db.Boolean, default=False)  # protege los de fábrica de borrado accidental
    creado_en = db.Column(db.DateTime, default=hora_peru)

    __table_args__ = (db.UniqueConstraint('nombre', 'tipo', name='uq_motivo_nombre_tipo'),)


# --- PROVEEDORES (caché de RUC/datos, independiente de Client) ---
class Proveedor(db.Model):
    __tablename__ = 'proveedor'
    id = db.Column(db.Integer, primary_key=True)
    tipo_proveedor = db.Column(db.String(15), default='NACIONAL')  # NACIONAL o INTERNACIONAL

    documento = db.Column(db.String(20), unique=True, nullable=True)  # RUC/DNI (solo nacional)
    razon_social = db.Column(db.String(200), nullable=False)
    direccion = db.Column(db.String(200), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)

    # Solo aplican a proveedores nacionales (vienen de SUNAT)
    estado = db.Column(db.String(50), nullable=True)
    condicion = db.Column(db.String(50), nullable=True)
    ubigeo = db.Column(db.String(10), nullable=True)
    distrito = db.Column(db.String(100), nullable=True)
    provincia = db.Column(db.String(100), nullable=True)
    departamento = db.Column(db.String(100), nullable=True)

    # Solo aplica a proveedores internacionales
    pais = db.Column(db.String(100), nullable=True)
    identificador_fiscal = db.Column(db.String(50), nullable=True)  # Tax ID / VAT / etc.

    last_updated = db.Column(db.DateTime, default=hora_peru)
    updated_by = db.Column(db.String(50), default='Sistema')

    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    editado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    editado_en = db.Column(db.DateTime, nullable=True)

    creado_por = db.relationship('User', foreign_keys=[creado_por_id])
    editado_por = db.relationship('User', foreign_keys=[editado_por_id])

class Presentacion(db.Model):
    __tablename__ = 'presentacion'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    activo = db.Column(db.Boolean, default=True)
    es_predeterminado = db.Column(db.Boolean, default=False)

# --- MÓDULO DE AUDITORÍA / CONTEO FÍSICO ---

class PeriodoAuditoria(db.Model):
    """Agrupa los conteos físicos en campañas/periodos (mensual, anual, etc.) para no mezclar
    auditorías distintas entre sí. Es GLOBAL: cubre tanto ANCLAJES como IMPORTBOLTS a la vez, ya
    que el auditor primero elige el período y luego, dentro de él, la empresa a contar.
    Recomendación: mantener como máximo UN período en estado ABIERTO a la vez, para evitar que
    los auditores mezclen conteos de campañas distintas."""
    __tablename__ = 'periodo_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(500), nullable=True)

    estado = db.Column(db.String(20), nullable=False, default='ABIERTO')  # ABIERTO / CERRADO

    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)

    # Cierre automático opcional: si se define, al llegar esta fecha el período se cierra solo
    # (evaluado de forma perezosa, la primera vez que alguien lo consulta después de esa fecha).
    fecha_cierre_programada = db.Column(db.DateTime, nullable=True)

    # Cuándo y quién lo cerró realmente. cerrado_por_id = NULL significa cierre automático.
    fecha_cierre = db.Column(db.DateTime, nullable=True)
    cerrado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    creado_por = db.relationship('User', foreign_keys=[creado_por_id])
    cerrado_por = db.relationship('User', foreign_keys=[cerrado_por_id])

    @property
    def esta_abierto(self):
        return self.estado == 'ABIERTO'


class CatalogoValor(db.Model):
    """Catálogo genérico y administrable: ESTADO_FISICO, UNIDAD_MEDIDA, ANAQUEL, NICHO.
    Solo el admin puede agregar/desactivar valores."""
    __tablename__ = 'catalogo_valor'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(30), nullable=False)   # ESTADO_FISICO / UNIDAD_MEDIDA / ANAQUEL / NICHO
    valor = db.Column(db.String(100), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    es_predeterminado = db.Column(db.Boolean, default=False)  # protege los valores sembrados de borrado accidental
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creado_en = db.Column(db.DateTime, default=hora_peru)

    creado_por = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('tipo', 'valor', name='uq_catalogo_tipo_valor'),)


class CampoPersonalizado(db.Model):
    """Campos extra que el admin puede crear para el formulario de conteo:
    tipo_campo = 'SELECT' (lista de alternativas) o 'TEXTO' (texto libre)."""
    __tablename__ = 'campo_personalizado'
    id = db.Column(db.Integer, primary_key=True)
    etiqueta = db.Column(db.String(150), nullable=False)
    tipo_campo = db.Column(db.String(10), nullable=False, default='TEXTO')
    activo = db.Column(db.Boolean, default=True)
    orden = db.Column(db.Integer, default=0)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creado_en = db.Column(db.DateTime, default=hora_peru)
    obligatorio = db.Column(db.Boolean, default=False)

    creado_por = db.relationship('User')
    opciones = db.relationship('CampoPersonalizadoOpcion', backref='campo', cascade="all, delete-orphan")


class CampoPersonalizadoOpcion(db.Model):
    __tablename__ = 'campo_personalizado_opcion'
    id = db.Column(db.Integer, primary_key=True)
    campo_id = db.Column(db.Integer, db.ForeignKey('campo_personalizado.id'), nullable=False)
    valor = db.Column(db.String(150), nullable=False)
    activo = db.Column(db.Boolean, default=True)




class RegistroAuditoria(db.Model):
    """Un conteo físico enviado por un auditor para un producto específico."""
    __tablename__ = 'registro_auditoria'
    id = db.Column(db.Integer, primary_key=True)

    origen_inventario = db.Column(db.String(20), nullable=False)  # ANCLAJES / IMPORTBOLTS
    trabajador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=hora_peru)

    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    product_importbolts_id = db.Column(db.Integer, db.ForeignKey('product_importbolts.id'), nullable=True)

    sku_snapshot = db.Column(db.String(50))
    nombre_snapshot = db.Column(db.String(500))
    familia = db.Column(db.String(200))
    calidad = db.Column(db.String(200))

    # Anaquel y Nicho son INDEPENDIENTES: se puede llenar uno, ambos o ninguno
    anaquel = db.Column(db.String(20), nullable=True)
    nicho = db.Column(db.String(20), nullable=True)

    num_cajas = db.Column(db.Integer, default=0)
    peso_promedio_20u = db.Column(db.Float, default=0.0)
    num_bolsas = db.Column(db.Integer, default=0)
    cantidad_total = db.Column(db.Integer, nullable=False)
    unidad_medida = db.Column(db.String(20), default='UN')
    estado_fisico = db.Column(db.String(100))
    observaciones = db.Column(db.Text)

    stock_sistema_snapshot = db.Column(db.Integer)  # oculto al auditor (conteo ciego)

    # Período de auditoría al que pertenece este conteo (nullable: los registros anteriores a
    # esta funcionalidad quedan sin período asignado).
    periodo_id = db.Column(db.Integer, db.ForeignKey('periodo_auditoria.id'), nullable=True)

    estado_registro = db.Column(db.String(20), default='PENDIENTE')  # PENDIENTE, APROBADO, RECHAZADO, APLICADO
    bloqueado = db.Column(db.Boolean, default=True)
    motivo_rechazo = db.Column(db.Text)

    revisado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_revision = db.Column(db.DateTime, nullable=True)

    aplicado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_aplicacion = db.Column(db.DateTime, nullable=True)

    # Snapshot del producto justo ANTES de aplicar los cambios (para historial inmutable)
    snapshot_antes_ubicacion = db.Column(db.String(200), nullable=True)
    snapshot_antes_stock = db.Column(db.Integer, nullable=True)
    snapshot_antes_stock_minimo = db.Column(db.Integer, nullable=True)
    snapshot_antes_peso_kg = db.Column(db.Float, nullable=True)
    snapshot_antes_precio_unidad = db.Column(db.Float, nullable=True)
    snapshot_antes_precio_caja = db.Column(db.Float, nullable=True)
    snapshot_antes_estado = db.Column(db.String(100), nullable=True)
    snapshot_antes_activo = db.Column(db.Boolean, nullable=True)
    snapshot_antes_fecha = db.Column(db.DateTime, nullable=True)  # cuándo se tomó esta foto

    trabajador = db.relationship('User', foreign_keys=[trabajador_id])
    revisado_por = db.relationship('User', foreign_keys=[revisado_por_id])
    aplicado_por = db.relationship('User', foreign_keys=[aplicado_por_id])
    product = db.relationship('Product')
    product_importbolts = db.relationship('ProductImportBolts')
    periodo = db.relationship('PeriodoAuditoria')

    @property
    def producto(self):
        return self.product_importbolts if self.origen_inventario == 'IMPORTBOLTS' else self.product


class RegistroAuditoriaFoto(db.Model):
    """Fotos adjuntadas a un conteo físico (mismas reglas que las fotos de producto:
    máx. 5 fotos, máx. 5MB cada una, solo formatos de imagen)."""
    __tablename__ = 'registro_auditoria_foto'
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey('registro_auditoria.id'), nullable=False)
    url_s3 = db.Column(db.String(500), nullable=False)
    s3_key = db.Column(db.String(500), nullable=False)
    subido_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_subida = db.Column(db.DateTime, default=hora_peru)

    registro = db.relationship('RegistroAuditoria', backref=db.backref('fotos', cascade="all, delete-orphan"))
    subido_por = db.relationship('User')


class RegistroAuditoriaValorExtra(db.Model):
    """Valores capturados para los campos personalizados que el admin haya creado."""
    __tablename__ = 'registro_auditoria_valor_extra'
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey('registro_auditoria.id'), nullable=False)
    campo_id = db.Column(db.Integer, db.ForeignKey('campo_personalizado.id'), nullable=True)
    etiqueta_snapshot = db.Column(db.String(150))
    valor = db.Column(db.String(300))

    registro = db.relationship('RegistroAuditoria', backref=db.backref('valores_extra', cascade="all, delete-orphan"))
    campo = db.relationship('CampoPersonalizado')


class RegistroAuditoriaLog(db.Model):
    """Bitácora de todo lo que pasa con un registro: creado, editado, aprobado, rechazado, aplicado."""
    __tablename__ = 'registro_auditoria_log'
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey('registro_auditoria.id'), nullable=False)
    accion = db.Column(db.String(30), nullable=False)
    detalle = db.Column(db.Text)
    realizado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=hora_peru)

    realizado_por = db.relationship('User')
    registro = db.relationship('RegistroAuditoria', backref=db.backref('logs', order_by='RegistroAuditoriaLog.fecha.desc()'))