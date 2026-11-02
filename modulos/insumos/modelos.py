"""Modelos (tablas) de INSUMOS INTERNOS.
Se importan al final de models.py: "from models import X" sigue funcionando igual. Ver MAPA.md."""
from models import db, hora_peru

__all__ = ['InsumoArea', 'InsumoTrabajador', 'Insumo', 'InsumoStock', 'InsumoProveedor', 'InsumoIngreso', 'InsumoIngresoDetalle', 'InsumoSalida', 'InsumoSalidaDetalle', 'InsumoMovimiento', 'InsumoDocumento', 'InsumoLote', 'InsumoSalidaLote']


# =====================================================================================
# INSUMOS INTERNOS: material de uso interno (EPP, limpieza, oficina, repuestos...) con
# un MAESTRO único y STOCK separado por empresa (Anclajes / Import Bolts).
# Valorizado POR LOTES en orden de llegada (PEPS, precios con IGV): cada compra es un lote con su precio
# real; las salidas sacan primero del lote más antiguo y se cargan al área con el precio de ese lote.
# InsumoStock guarda los TOTALES (se recalculan desde los lotes); el "costo promedio" queda solo como referencia.
# =====================================================================================
class InsumoArea(db.Model):
    """Áreas / secciones a las que se carga el gasto (Producción, Almacén, Mantenimiento...)."""
    __tablename__ = 'insumo_area'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    creado_en = db.Column(db.DateTime, default=hora_peru)


class InsumoTrabajador(db.Model):
    """Personal que pide / recibe / autoriza (no necesita tener usuario en el sistema)."""
    __tablename__ = 'insumo_trabajador'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    codigo = db.Column(db.String(30))                 # DNI o código interno
    cargo = db.Column(db.String(100))
    area_id = db.Column(db.Integer, db.ForeignKey('insumo_area.id'), nullable=True)
    empresa = db.Column(db.String(15), default='AMBAS')   # ANCLAJES / IMPORTBOLTS / AMBAS
    es_jefe = db.Column(db.Boolean, default=False)    # puede autorizar salidas
    activo = db.Column(db.Boolean, default=True)
    creado_en = db.Column(db.DateTime, default=hora_peru)

    area = db.relationship('InsumoArea')


class Insumo(db.Model):
    """Maestro de insumos (único para las dos empresas)."""
    __tablename__ = 'insumo'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), nullable=False, unique=True, index=True)
    descripcion = db.Column(db.String(300), nullable=False)
    categoria = db.Column(db.String(100))
    unidad = db.Column(db.String(30), default='UND')
    activo = db.Column(db.Boolean, default=True)
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    actualizado_por = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, nullable=True)


class InsumoStock(db.Model):
    """Stock y costo promedio de un insumo EN UNA EMPRESA."""
    __tablename__ = 'insumo_stock'
    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    empresa = db.Column(db.String(15), nullable=False)        # ANCLAJES / IMPORTBOLTS
    stock_actual = db.Column(db.Float, default=0)
    stock_minimo = db.Column(db.Float, default=0)
    costo_promedio = db.Column(db.Float, default=0)          # S/ por unidad, con IGV (de lo comprado en SOLES)
    # Lo comprado en DÓLARES se lleva aparte (sin convertir): cuántas unidades del stock son "en dólares" y su costo en US$.
    # stock_actual = unidades en soles + stock_usd + stock_sin_costo
    stock_usd = db.Column(db.Float, default=0)
    costo_usd = db.Column(db.Float, default=0)               # US$ por unidad (con IGV si la factura lo lleva)
    # unidades con PRECIO PENDIENTE (sin factura / inventario de cosas antiguas): no entran al costo promedio ni al gasto
    stock_sin_costo = db.Column(db.Float, default=0)
    bolsa_antigua = db.Column(db.String(3), default='PEN')    # de qué moneda son las unidades más antiguas (salen primero)
    almacen = db.Column(db.String(100))                     # almacén / ubicación
    ultimo_ingreso = db.Column(db.DateTime, nullable=True)
    ultima_salida = db.Column(db.DateTime, nullable=True)

    insumo = db.relationship('Insumo', backref='stocks')
    __table_args__ = (db.UniqueConstraint('insumo_id', 'empresa', name='uq_insumo_stock_empresa'),)


class InsumoLote(db.Model):
    """Un LOTE = lo que entró en una compra (o el saldo que había al pasar a lotes), con su precio real.
    Salen en orden de llegada (fecha, id): primero el más antiguo. costo_unitario None = PRECIO PENDIENTE."""
    __tablename__ = 'insumo_lote'
    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.String(15), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, index=True)        # fecha de llegada (define el orden de salida)
    moneda = db.Column(db.String(3), default='PEN')                  # PEN / USD (sin convertir)
    costo_unitario = db.Column(db.Float, nullable=True)              # con IGV; None = precio pendiente
    cantidad_inicial = db.Column(db.Float, nullable=False)
    cantidad_restante = db.Column(db.Float, nullable=False)
    origen = db.Column(db.String(12), default='COMPRA')              # COMPRA / INICIAL (saldo al pasar a lotes) / EXCEL / DEVOLUCION
    ingreso_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso.id'), nullable=True, index=True)
    ingreso_detalle_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso_detalle.id'), nullable=True, index=True)
    proveedor = db.Column(db.String(200))
    documento = db.Column(db.String(120))                            # "Factura F001-123 · OC N° 000045"
    estado = db.Column(db.String(10), default='ACTIVO')              # ACTIVO / ANULADO (se anuló su ingreso)
    precio_por = db.Column(db.String(100))                           # quién puso / corrigió el precio después
    fecha_precio = db.Column(db.DateTime, nullable=True)
    creado_en = db.Column(db.DateTime, default=hora_peru)

    insumo = db.relationship('Insumo')


class InsumoSalidaLote(db.Model):
    """De qué lote salió cada parte de una salida (y a qué precio): así el gasto es el real de cada compra."""
    __tablename__ = 'insumo_salida_lote'
    id = db.Column(db.Integer, primary_key=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('insumo_salida.id'), nullable=False, index=True)
    salida_detalle_id = db.Column(db.Integer, db.ForeignKey('insumo_salida_detalle.id'), nullable=False, index=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('insumo_lote.id'), nullable=False, index=True)
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=True)              # None = salió sin precio (se completa al ponerle precio al lote)
    moneda = db.Column(db.String(3), default='PEN')

    lote = db.relationship('InsumoLote')


class InsumoProveedor(db.Model):
    """Proveedores de insumos guardados (con RUC/DNI o sin RUC) para elegirlos rápido en cada ingreso."""
    __tablename__ = 'insumo_proveedor'
    id = db.Column(db.Integer, primary_key=True)
    ruc = db.Column(db.String(20), index=True)                 # vacío = compra sin RUC / informal
    razon_social = db.Column(db.String(200), nullable=False)
    direccion = db.Column(db.String(250))
    contacto_nombre = db.Column(db.String(120))
    contacto_telefono = db.Column(db.String(40))
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)   # el validado en SUNAT
    creado_por = db.Column(db.String(100))
    fecha_creacion = db.Column(db.DateTime, default=hora_peru)
    actualizado_por = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, nullable=True)
    ultima_compra = db.Column(db.DateTime, nullable=True)


class InsumoIngreso(db.Model):
    """Ingreso (compra) con su factura: cabecera."""
    __tablename__ = 'insumo_ingreso'
    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.String(15), nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, index=True)       # puede ser anterior a hoy
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    ruc = db.Column(db.String(20))
    razon_social = db.Column(db.String(200))
    direccion = db.Column(db.String(250))
    moneda = db.Column(db.String(3), default='PEN')                  # PEN / USD (precios del ingreso en esa moneda)
    numero_factura = db.Column(db.String(50))
    contacto_nombre = db.Column(db.String(120))
    contacto_telefono = db.Column(db.String(40))
    almacen = db.Column(db.String(100))
    observacion = db.Column(db.String(300))
    total = db.Column(db.Float, default=0)
    insumo_proveedor_id = db.Column(db.Integer, db.ForeignKey('insumo_proveedor.id'), nullable=True)
    orden_compra_id = db.Column(db.Integer, nullable=True, index=True)   # la OC de la que vino (se conserva aunque se anule el ingreso)
    estado = db.Column(db.String(10), default='REGISTRADO')       # REGISTRADO / ANULADO
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=hora_peru)
    anulado_por = db.Column(db.String(100))
    fecha_anulacion = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.String(255))

    usuario = db.relationship('User')
    detalles = db.relationship('InsumoIngresoDetalle', backref='ingreso', order_by='InsumoIngresoDetalle.id')


class InsumoIngresoDetalle(db.Model):
    __tablename__ = 'insumo_ingreso_detalle'
    id = db.Column(db.Integer, primary_key=True)
    ingreso_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso.id'), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    codigo_proveedor = db.Column(db.String(60))
    cantidad = db.Column(db.Float, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)    # con IGV (0 mientras el precio está pendiente)
    precio_total = db.Column(db.Float, nullable=False)       # con IGV
    stock_antes = db.Column(db.Float)
    stock_despues = db.Column(db.Float)
    costo_prom_antes = db.Column(db.Float)
    costo_prom_despues = db.Column(db.Float)
    # PRECIO PENDIENTE: entró sin precio (no toca el costo promedio). sin_costo_restante = cuánto de este ítem sigue en stock "sin precio".
    precio_pendiente = db.Column(db.Boolean, default=False)
    sin_costo_restante = db.Column(db.Float, default=0)
    cantidad_valorizada = db.Column(db.Float, nullable=True)      # al completar el precio: cuántas unidades pasaron al costo promedio
    precio_completado_por = db.Column(db.String(100))
    fecha_precio = db.Column(db.DateTime, nullable=True)

    insumo = db.relationship('Insumo')


class InsumoSalida(db.Model):
    """Salida de materiales de almacén (formato LAL-FO-0001): cabecera. Correlativo propio por empresa."""
    __tablename__ = 'insumo_salida'
    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.String(15), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, index=True)       # puede ser anterior a hoy
    area_id = db.Column(db.Integer, db.ForeignKey('insumo_area.id'), nullable=True, index=True)
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey('insumo_trabajador.id'), nullable=True)
    recibido_por_id = db.Column(db.Integer, db.ForeignKey('insumo_trabajador.id'), nullable=True)
    autorizado_por_id = db.Column(db.Integer, db.ForeignKey('insumo_trabajador.id'), nullable=True)
    a_cuenta_de_id = db.Column(db.Integer, db.ForeignKey('insumo_trabajador.id'), nullable=True)
    motivo = db.Column(db.String(100))            # "Necesario para" (catálogo)
    motivo_detalle = db.Column(db.String(300))    # explicación libre
    total_costo = db.Column(db.Float, default=0)
    total_costo_usd = db.Column(db.Float, default=0)   # gasto en dólares (lo que salió de compras en US$, sin convertir)
    estado = db.Column(db.String(10), default='REGISTRADA')        # REGISTRADA / ANULADA
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   # grabado / entregado por
    fecha_registro = db.Column(db.DateTime, default=hora_peru)
    firma_s3_key = db.Column(db.String(300))      # firma en pantalla de quien recibe (PNG)
    firma_fecha = db.Column(db.DateTime, nullable=True)
    firma_por = db.Column(db.String(150))
    anulado_por = db.Column(db.String(100))
    fecha_anulacion = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.String(255))

    area = db.relationship('InsumoArea')
    solicitado_por = db.relationship('InsumoTrabajador', foreign_keys=[solicitado_por_id])
    recibido_por = db.relationship('InsumoTrabajador', foreign_keys=[recibido_por_id])
    autorizado_por = db.relationship('InsumoTrabajador', foreign_keys=[autorizado_por_id])
    a_cuenta_de = db.relationship('InsumoTrabajador', foreign_keys=[a_cuenta_de_id])
    usuario = db.relationship('User')
    detalles = db.relationship('InsumoSalidaDetalle', backref='salida', order_by='InsumoSalidaDetalle.id')
    __table_args__ = (db.UniqueConstraint('empresa', 'numero', name='uq_insumo_salida_numero'),)


class InsumoSalidaDetalle(db.Model):
    __tablename__ = 'insumo_salida_detalle'
    id = db.Column(db.Integer, primary_key=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('insumo_salida.id'), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    cantidad_solicitada = db.Column(db.Float, nullable=False)
    cantidad_despachada = db.Column(db.Float, nullable=False)
    unidad = db.Column(db.String(30))
    ubicacion = db.Column(db.String(100))
    costo_unitario = db.Column(db.Float, default=0)   # costo promedio (S/) de la parte que salió de lo comprado en soles
    costo_total = db.Column(db.Float, default=0)      # S/
    cantidad_usd = db.Column(db.Float, default=0)     # de lo despachado, cuánto salió de lo comprado en dólares
    costo_unitario_usd = db.Column(db.Float, default=0)
    costo_total_usd = db.Column(db.Float, default=0)  # US$
    cantidad_sin_costo = db.Column(db.Float, default=0)   # de lo despachado, cuánto era SIN PRECIO (precio pendiente): costo 0
    origen_sin_costo = db.Column(db.String(500))          # de qué ingresos salió: "detalle_id:cantidad,..." (0 = sin ingreso)
    stock_antes = db.Column(db.Float)
    stock_despues = db.Column(db.Float)

    insumo = db.relationship('Insumo')


class InsumoMovimiento(db.Model):
    """Kardex valorizado de insumos (por empresa)."""
    __tablename__ = 'insumo_movimiento'
    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.String(15), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)          # ENTRADA / SALIDA
    concepto = db.Column(db.String(30))                    # COMPRA / CONSUMO / AJUSTE_COSTO / ANULACION / IMPORTACION / VALORIZACION
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, default=0)
    costo_total = db.Column(db.Float, default=0)
    stock_antes = db.Column(db.Float)
    stock_despues = db.Column(db.Float)
    costo_prom_despues = db.Column(db.Float)
    moneda = db.Column(db.String(3), default='PEN')         # moneda del costo de este movimiento (PEN / USD / SC = sin precio)
    stock_moneda_despues = db.Column(db.Float)              # unidades que quedan compradas en ESA moneda (para el valor del saldo)
    referencia = db.Column(db.String(120))                 # "Factura F001-123" / "Consumo N° 000015"
    ingreso_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso.id'), nullable=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('insumo_salida.id'), nullable=True)
    area_id = db.Column(db.Integer, db.ForeignKey('insumo_area.id'), nullable=True)
    lote_id = db.Column(db.Integer, nullable=True, index=True)          # lote del que entra / sale (PEPS)
    observacion = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=hora_peru)

    insumo = db.relationship('Insumo')
    area = db.relationship('InsumoArea')
    usuario = db.relationship('User')


class InsumoDocumento(db.Model):
    """Factura / guía del ingreso, o la salida firmada (PDF o foto en S3)."""
    __tablename__ = 'insumo_documento'
    id = db.Column(db.Integer, primary_key=True)
    ingreso_id = db.Column(db.Integer, db.ForeignKey('insumo_ingreso.id'), nullable=True, index=True)
    salida_id = db.Column(db.Integer, db.ForeignKey('insumo_salida.id'), nullable=True, index=True)
    tipo = db.Column(db.String(20), nullable=False)        # FACTURA / GUIA / OTRO / SALIDA_FIRMADA
    s3_key = db.Column(db.String(300), nullable=False)
    nombre_original = db.Column(db.String(200))
    content_type = db.Column(db.String(50))
    tamano_bytes = db.Column(db.Integer)
    subido_por = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=hora_peru)


