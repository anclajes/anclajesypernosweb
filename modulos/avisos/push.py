# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# AVISOS · aviso de Windows con la página cerrada (Web Push)
# claves VAPID, cifrado RFC 8291, service worker (/sw.js) y registro de navegadores
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------- Avisos de Windows con la página CERRADA (Web Push) ----------------
# El servidor le manda el aviso al navegador (Chrome / Edge) a través del servicio de avisos del propio navegador.
# Llega aunque no haya ninguna pestaña del sistema abierta, mientras el navegador esté funcionando (también en segundo plano).
# Cifrado según RFC 8291 (aes128gcm) y firma VAPID (RFC 8292). Gratis: no hay costo por aviso.
import threading as _threading
import time
from flask import make_response, has_request_context
import struct as _struct
import hmac as _hmac_mod
import hashlib as _hashlib
try:
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.hazmat.primitives import hashes as _hashes, serialization as _serial
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature as _dss_dec
    PUSH_DISPONIBLE = True
except Exception:          # si faltara la librería, el sistema sigue igual (solo sin avisos con la página cerrada)
    PUSH_DISPONIBLE = False
PUSH_EN_HILO = True        # se envía en segundo plano para no demorar la acción (aprobar, enviar...)
_push_claves_cache = {}


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _b64u_dec(s):
    s = (s or '').strip()
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _push_pub_raw(pub):
    return pub.public_bytes(_serial.Encoding.X962, _serial.PublicFormat.UncompressedPoint)


def _push_claves():
    """Par de claves VAPID del servidor (se crea una sola vez y se guarda; o se toma de la variable VAPID_PRIVATE_KEY)."""
    if not PUSH_DISPONIBLE:
        return None, None
    if 'priv' in _push_claves_cache:
        return _push_claves_cache['priv'], _push_claves_cache['pub']
    raw = os.environ.get('VAPID_PRIVATE_KEY')
    if not raw:
        fila = SystemConfig.query.get('push_vapid_privada')
        if not fila:
            nueva = _ec.generate_private_key(_ec.SECP256R1())
            try:
                with db.session.begin_nested():
                    db.session.add(SystemConfig(key='push_vapid_privada', value=_b64u(nueva.private_numbers().private_value.to_bytes(32, 'big')),
                                                updated_by='Sistema'))
                db.session.commit()
            except Exception:
                db.session.rollback()
            fila = SystemConfig.query.get('push_vapid_privada')
        raw = fila.value if fila else None
    if not raw:
        return None, None
    priv = _ec.derive_private_key(int.from_bytes(_b64u_dec(raw), 'big'), _ec.SECP256R1())
    _push_claves_cache.update(priv=priv, pub=_b64u(_push_pub_raw(priv.public_key())))
    return _push_claves_cache['priv'], _push_claves_cache['pub']


def _push_cifrar(p256dh, auth, datos, as_priv=None, salt=None):
    """Cifra el mensaje para ese navegador (RFC 8291, aes128gcm)."""
    _h = lambda k, m: _hmac_mod.new(k, m, _hashlib.sha256).digest()
    ua_pub_raw, secreto = _b64u_dec(p256dh), _b64u_dec(auth)
    ua_pub = _ec.EllipticCurvePublicKey.from_encoded_point(_ec.SECP256R1(), ua_pub_raw)
    as_priv = as_priv or _ec.generate_private_key(_ec.SECP256R1())
    as_pub_raw = _push_pub_raw(as_priv.public_key())
    ikm = _h(_h(secreto, as_priv.exchange(_ec.ECDH(), ua_pub)), b'WebPush: info\x00' + ua_pub_raw + as_pub_raw + b'\x01')
    salt = salt or os.urandom(16)
    prk = _h(salt, ikm)
    cek, nonce = _h(prk, b'Content-Encoding: aes128gcm\x00\x01')[:16], _h(prk, b'Content-Encoding: nonce\x00\x01')[:12]
    return salt + _struct.pack('!I', 4096) + bytes([len(as_pub_raw)]) + as_pub_raw + _AESGCM(cek).encrypt(nonce, datos + b'\x02', None)


def _push_vapid(endpoint, priv, pub_b64, sub):
    from urllib.parse import urlparse
    u = urlparse(endpoint)
    cab = _b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    cuerpo = _b64u(json.dumps({'aud': f'{u.scheme}://{u.netloc}', 'exp': int(time.time()) + 12 * 3600, 'sub': sub}, separators=(',', ':')).encode())
    r, s = _dss_dec(priv.sign(f'{cab}.{cuerpo}'.encode(), _ec.ECDSA(_hashes.SHA256())))
    return f'vapid t={cab}.{cuerpo}.{_b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}, k={pub_b64}'


def _push_enviar_uno(trabajo, priv, pub, sub):
    """Manda un aviso a un navegador. Devuelve el código HTTP (201 = entregado; 404/410 = ese navegador ya no existe)."""
    try:
        cuerpo = _push_cifrar(trabajo['p256dh'], trabajo['auth'], json.dumps(trabajo['datos'], ensure_ascii=False).encode())
        r = requests.post(trabajo['endpoint'], data=cuerpo, timeout=10,
                          headers={'Authorization': _push_vapid(trabajo['endpoint'], priv, pub, sub), 'Content-Encoding': 'aes128gcm',
                                   'Content-Type': 'application/octet-stream', 'TTL': str(trabajo.get('ttl', 86400)), 'Urgency': 'high'})
        return r.status_code
    except Exception as e:
        app.logger.warning("Aviso push no enviado: %s", e)
        return 0


def _push_procesar(trabajos, priv, pub, sub, espera=0):
    if espera:
        time.sleep(espera)
    resultado = [(t['sub_id'], _push_enviar_uno(t, priv, pub, sub)) for t in trabajos]
    try:
        with app.app_context():
            ahora = hora_peru()
            for sid, codigo in resultado:
                fila = PushSuscripcion.query.get(sid)
                if not fila:
                    continue
                if codigo in (404, 410):              # el usuario quitó el permiso o borró el navegador
                    db.session.delete(fila)
                elif 200 <= codigo < 300:
                    fila.ultimo_envio, fila.fallos = ahora, 0
                else:
                    fila.fallos = (fila.fallos or 0) + 1
            db.session.commit()
    except Exception:
        app.logger.exception("No se pudo actualizar los navegadores con aviso")
    return resultado


def _push_a_usuarios(por_usuario, espera=0, en_hilo=None):
    """por_usuario: {user_id: datos del aviso}. Solo a quien tiene el aviso de Windows activado."""
    priv, pub = _push_claves()
    if not priv or not por_usuario:
        return []
    trabajos = []
    for s_ in PushSuscripcion.query.filter(PushSuscripcion.user_id.in_(list(por_usuario))).all():
        trabajos.append({'sub_id': s_.id, 'endpoint': s_.endpoint, 'p256dh': s_.p256dh, 'auth': s_.auth, 'datos': por_usuario[s_.user_id]})
    if not trabajos:
        return []
    # 'sub' de VAPID: la dirección del sistema (en Render siempre es https)
    sub = os.environ.get('VAPID_SUB') or (('https://' + request.host) if has_request_context() else 'mailto:avisos@sistema.local')
    if PUSH_EN_HILO if en_hilo is None else en_hilo:
        _threading.Thread(target=_push_procesar, args=(trabajos, priv, pub, sub, espera), daemon=True).start()
        return [(t['sub_id'], None) for t in trabajos]
    return _push_procesar(trabajos, priv, pub, sub, espera)


@app.after_request
def _push_despachar(resp):
    """Después de guardar: manda por Web Push los avisos creados en esta petición (si se deshizo, no se manda nada)."""
    ids = g.pop('push_cola', None)
    if not ids or not PUSH_DISPONIBLE:
        return resp
    try:
        logo = url_for('static', filename='img/logo.png')
        por_usuario = {}
        avisos = Notificacion.query.filter(Notificacion.id.in_(ids)).all()
        roles = {u.id: u.role for u in User.query.filter(User.id.in_(list({n.user_id for n in avisos}) or [0])).all()}
        for n in avisos:
            if n.leida or not _notif_cfg(n.user_id, roles.get(n.user_id))['windows']:
                continue
            por_usuario[n.user_id] = {'title': n.titulo, 'body': n.texto or '', 'url': url_for('notif_ir', notif_id=n.id), 'tag': f'erp-{n.id}',
                                      'insistente': n.tipo == 'OC_POR_APROBAR', 'icon': logo}
        _push_a_usuarios(por_usuario)
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudo despachar los avisos push")
    return resp


SW_JS = r"""/* Avisos del sistema con la página cerrada (Web Push) */
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { title: 'Aviso del sistema', body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Aviso del sistema', {
    body: d.body || '', icon: d.icon, badge: d.icon, tag: d.tag || 'erp', renotify: true,
    requireInteraction: !!d.insistente, data: { url: d.url || '/' } }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ventanas => {
    for (const w of ventanas) {
      if (w.url.startsWith(self.location.origin) && 'focus' in w) return w.focus().then(v => (v || w).navigate ? (v || w).navigate(url) : null);
    }
    return self.clients.openWindow(url);
  }));
});
"""


@app.route('/sw.js')
def push_sw():
    """Service worker: recibe los avisos aunque la página esté cerrada (tiene que servirse desde la raíz del sitio)."""
    resp = make_response(SW_JS)
    resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


def _navegador_txt(ua):
    ua = ua or ''
    nav = 'Edge' if 'Edg/' in ua else 'Opera' if 'OPR/' in ua else 'Chrome' if 'Chrome/' in ua else 'Firefox' if 'Firefox/' in ua else 'Safari' if 'Safari/' in ua else 'Navegador'
    so = 'Windows' if 'Windows' in ua else 'Android' if 'Android' in ua else 'iPhone' if 'iPhone' in ua or 'iPad' in ua else 'Mac' if 'Mac OS' in ua else 'Linux' if 'Linux' in ua else ''
    return f"{nav}{' · ' + so if so else ''}"[:120]


@app.route('/notificaciones/push/suscribir', methods=['POST'])
def push_suscribir():
    """El navegador avisa a dónde mandarle los avisos (se llama sola al abrir el sistema con el permiso dado)."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid or rol not in ROLES_NOTIF:
        return {'status': 'error'}, 403
    d = request.get_json(silent=True) or {}
    endpoint, claves = (d.get('endpoint') or '').strip(), d.get('keys') or {}
    if not endpoint.startswith('https://') or len(endpoint) > 800 or not claves.get('p256dh') or not claves.get('auth'):
        return {'status': 'error', 'msg': 'Suscripción no válida'}, 400
    try:
        if len(_b64u_dec(claves['p256dh'])) != 65 or len(_b64u_dec(claves['auth'])) != 16:
            raise ValueError
    except Exception:
        return {'status': 'error', 'msg': 'Claves no válidas'}, 400
    _asegurar_oc()
    fila = PushSuscripcion.query.filter_by(endpoint=endpoint).first()
    if not fila:
        fila = PushSuscripcion(endpoint=endpoint, fecha=hora_peru(), fallos=0)
        db.session.add(fila)
    # si en esa computadora entra otro usuario, los avisos pasan a ser de quien está usando el navegador ahora
    fila.user_id, fila.p256dh, fila.auth = uid, claves['p256dh'][:200], claves['auth'][:100]
    fila.navegador = _navegador_txt(request.headers.get('User-Agent'))
    db.session.commit()
    return {'status': 'ok', 'id': fila.id}


@app.route('/notificaciones/push/quitar', methods=['POST'])
def push_quitar():
    uid = session.get('user_id')
    if not uid:
        return {'status': 'error'}, 401
    d = request.get_json(silent=True) or {}
    q = PushSuscripcion.query.filter(PushSuscripcion.user_id == uid)
    if d.get('endpoint'):
        q = q.filter(PushSuscripcion.endpoint == d['endpoint'])
    elif request.form.get('id', type=int):
        q = q.filter(PushSuscripcion.id == request.form.get('id', type=int))
    n = q.delete(synchronize_session=False)
    db.session.commit()
    return {'status': 'ok', 'n': n}


@app.route('/notificaciones/push/prueba', methods=['POST'])
def push_prueba():
    """Aviso de prueba a mis navegadores. Con 'espera' se manda en unos segundos (para probarlo con la página cerrada)."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid or rol not in ROLES_NOTIF:
        return {'status': 'error'}, 403
    _asegurar_oc()
    espera = min(max(request.form.get('espera', 0, type=int), 0), 60)
    n_nav = PushSuscripcion.query.filter_by(user_id=uid).count()
    if not n_nav:
        return {'status': 'error', 'msg': 'Este usuario no tiene ningún navegador con los avisos activados.'}
    datos = {'title': 'Prueba de aviso del sistema', 'body': 'Así te llegarán las órdenes por aprobar aunque la página esté cerrada.',
             'url': url_for('notif_pagina'), 'tag': 'erp-prueba', 'insistente': False, 'icon': url_for('static', filename='img/logo.png')}
    res = _push_a_usuarios({uid: datos}, espera=espera, en_hilo=bool(espera))
    ok = sum(1 for _, c in res if c is None or 200 <= (c or 0) < 300)
    return {'status': 'ok', 'navegadores': n_nav, 'enviados': ok, 'espera': espera}


@app.context_processor
def _ctx_notificaciones():
    """La campana con avisos solo se activa para los roles que reciben alguno."""
    activa = bool(session.get('user_id')) and session.get('role') in ROLES_NOTIF
    clave = None
    if activa and PUSH_DISPONIBLE:
        try:
            clave = _push_claves()[1]
        except Exception:
            db.session.rollback()
    return {'campana_activa': activa, 'push_clave': clave}


