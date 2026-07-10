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
    last_updated = db.Column(db.DateTime, default=hora_peru)
    updated_by = db.Column(db.String(50), default='Sistema')

# EN MODELS.PY

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=hora_peru)
    
    # --- CLAVES FORÁNEAS ---
    cliente_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    
    # Aquí están los dos caminos a User:
    vendedor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chofer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Nuevo
    
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
    
    # Datos de Almacén (Nuevos)
    peso_total = db.Column(db.String(50))      
    cantidad_bultos = db.Column(db.String(50)) 
    
    # --- ESTADO DE PAGO ---
    monto_pagado = db.Column(db.Float, default=0.0)
    estado_pago = db.Column(db.String(20), default='Pendiente') 
    
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
    
    # Nuevos campos para manejar tipos
    item_type = db.Column(db.String(20), default='PRODUCTO') # PRODUCTO, FABRICACION, GLB
    
    cantidad = db.Column(db.Integer, nullable=False)
    precio_aplicado = db.Column(db.Float, nullable=False)
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
    
    # Relación con componentes del kit
    kit_components = db.relationship('OrderKitComponent', backref='parent_detail', cascade="all, delete-orphan")

    nombre_personalizado = db.Column(db.String(200)) # Este guardará la descripción NORMAL
    
    # NUEVO CAMPO:
    nombre_personalizado_titulo = db.Column(db.String(200)) # Este guardará la parte en NEGRITA
    check_almacen = db.Column(db.Boolean, default=False)

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

    product = db.relationship('ProductImportBolts', backref='movements')
    user = db.relationship('User', backref='movements_importbolts')