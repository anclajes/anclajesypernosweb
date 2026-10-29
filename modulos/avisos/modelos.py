"""Modelos (tablas) de AVISOS (campana y avisos de Windows).
Se importan al final de models.py: "from models import X" sigue funcionando igual. Ver MAPA.md."""
from models import db, hora_peru

__all__ = ['Notificacion', 'PushSuscripcion', 'NotificacionConfig']


class Notificacion(db.Model):
    """Aviso para un usuario (campana del sistema): OC/OS por aprobar, aprobada, rechazada, requerimiento nuevo...
    Se marca como leída al abrirla o al pulsar "Marcar todo como leído"."""
    __tablename__ = 'notificacion'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)          # OC_POR_APROBAR / OC_APROBADA / OC_RECHAZADA / REQ_NUEVO
    titulo = db.Column(db.String(150), nullable=False)
    texto = db.Column(db.String(300))
    url = db.Column(db.String(300))
    orden_id = db.Column(db.Integer, nullable=True, index=True)
    req_id = db.Column(db.Integer, nullable=True)
    empresa = db.Column(db.String(15))
    fecha = db.Column(db.DateTime, default=hora_peru)
    leida = db.Column(db.Boolean, default=False, index=True)
    fecha_leida = db.Column(db.DateTime)


class PushSuscripcion(db.Model):
    """Navegador (computadora) donde el usuario activó los avisos de Windows: el servidor le manda el aviso aunque la página esté cerrada."""
    __tablename__ = 'push_suscripcion'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    endpoint = db.Column(db.String(800), nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(100), nullable=False)
    navegador = db.Column(db.String(120))
    fecha = db.Column(db.DateTime, default=hora_peru)
    ultimo_envio = db.Column(db.DateTime)
    fallos = db.Column(db.Integer, default=0)


class NotificacionConfig(db.Model):
    """Cómo quiere cada usuario sus avisos (qué tipos, sonido, ventana emergente, aviso de Windows, cada cuánto recordar)."""
    __tablename__ = 'notificacion_config'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    datos = db.Column(db.Text)                                 # JSON
    fecha = db.Column(db.DateTime, default=hora_peru)
