"""Modelos (tablas) del KARDEX que viven en modulos/kardex.
Se importan al final de models.py: "from models import X" sigue funcionando igual. Ver MAPA.md."""
from models import db, hora_peru

__all__ = ['MovimientoEliminado']


class MovimientoEliminado(db.Model):
    """AUDITORÍA de los movimientos del Kardex (Anclajes / Import Bolts) que se ELIMINARON por error de registro.
    Guarda una copia completa del movimiento, quién lo eliminó, cuándo y por qué, y cómo quedó el stock.
    Al eliminar, el stock se revierte (una salida vuelve, una entrada se descuenta) y el movimiento deja de contar
    en el Kardex y en las estadísticas (ventas, toneladas, rotación)."""
    __tablename__ = 'movimiento_eliminado'
    id = db.Column(db.Integer, primary_key=True)
    origen = db.Column(db.String(15), nullable=False, index=True)       # ANCLAJES / IMPORTBOLTS
    movimiento_id = db.Column(db.Integer, nullable=False)                # id que tenía el movimiento
    product_id = db.Column(db.Integer, nullable=True)
    sku = db.Column(db.String(50), index=True)
    producto = db.Column(db.String(500))
    tipo = db.Column(db.String(10))                                      # ENTRADA / SALIDA
    cantidad = db.Column(db.Integer)
    fecha_movimiento = db.Column(db.DateTime)
    motivo = db.Column(db.String(200))
    referencia = db.Column(db.String(50))
    proveedor = db.Column(db.String(200))                                # proveedor o cliente (razón social + RUC)
    registrado_por = db.Column(db.String(150))                           # quién había registrado el movimiento
    stock_antes = db.Column(db.Integer)                                  # stock del producto al eliminar...
    stock_despues = db.Column(db.Integer)                                # ...y después (revertido)
    movimientos_ajustados = db.Column(db.Integer, default=0)             # movimientos posteriores cuyo saldo se corrigió
    datos = db.Column(db.Text)                                           # copia completa (JSON) del movimiento y sus documentos
    eliminado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    eliminado_por = db.Column(db.String(150))
    rol = db.Column(db.String(30))
    fecha_eliminacion = db.Column(db.DateTime, default=hora_peru, index=True)
    motivo_eliminacion = db.Column(db.String(300), nullable=False)
