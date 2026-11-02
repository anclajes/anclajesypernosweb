"""Modelos (tablas) de AVISOS (campana y avisos de Windows).
Se importan al final de models.py: "from models import X" sigue funcionando igual. Ver MAPA.md."""
from models import db, hora_peru

__all__ = ['Notificacion', 'PushSuscripcion', 'NotificacionConfig', 'AvisoAgente']


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


class AvisoAgente(db.Model):
    """Computadora con el "Programa de avisos" instalado: un programita de Windows (sin navegador) que pregunta al
    sistema cada minuto y muestra el aviso de Windows aunque el navegador esté cerrado del todo.
    Se identifica con una clave propia (solo se guarda su huella SHA-256). Al quitarla aquí, el programa se desinstala solo."""
    __tablename__ = 'aviso_agente'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    nombre_pc = db.Column(db.String(60))                       # nombre de la computadora (lo manda el programa)
    version = db.Column(db.String(20))
    fecha = db.Column(db.DateTime, default=hora_peru)          # cuándo se descargó el instalador
    ultimo_contacto = db.Column(db.DateTime)                   # última vez que preguntó (None = todavía no se instaló)
    prueba = db.Column(db.Boolean, default=False)              # aviso de prueba pendiente para la próxima consulta


class NotificacionConfig(db.Model):
    """Cómo quiere cada usuario sus avisos (qué tipos, sonido, ventana emergente, aviso de Windows, cada cuánto recordar)."""
    __tablename__ = 'notificacion_config'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    datos = db.Column(db.Text)                                 # JSON
    fecha = db.Column(db.DateTime, default=hora_peru)
