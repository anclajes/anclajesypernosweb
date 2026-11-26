# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v37 · TABLETA DE ALMACÉN: los trabajadores piden lo que van a sacar (insumos) y Almacén lo entrega.
#   · Usuario del sistema con rol 'tableta' (Usuarios → Rol "Tableta de almacén"): queda conectado siempre (no se cierra por
#     inactividad ni al cerrar el navegador) y SOLO puede abrir la pantalla de la tableta (/tableta).
#   · En la tableta: el trabajador toca su nombre (bloques grandes) → PIN de 4 dígitos (si no tiene uno propio, los 4 primeros
#     dígitos de su DNI / código) → elige los materiales con + / − → para qué y el área → "Enviar". NO descuenta stock.
#   · Almacén / Logística / Gerencia: globito abajo a la izquierda con los pedidos pendientes (sin sonido). "Entregar" crea la
#     salida normal (lotes PEPS, costo, una por inventario, el inventario recomendado: primero General) en un toque;
#     "Revisar" abre la Nueva salida con todo cargado (para cambiar cantidades, inventario o firmar); "Rechazar" con motivo.
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS), después de insumos/revertir.py. Ver MAPA.md.
# =====================================================================================
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash
from models import InsumoPedido, InsumoPedidoItem

ROL_TABLETA = 'tableta'
ROLES_ATIENDEN_PEDIDOS = ['admin', 'almacen', 'logistica']
PIN_MAX_FALLOS = 5
PIN_BLOQUEO_MIN = 10
TABLETA_MINUTOS_PEDIDO = 10            # después de poner el PIN, tiene 10 min para enviar el pedido
TABLETA_MAX_ITEMS = 30
RUTAS_TABLETA = {'tableta', 'tableta_datos', 'tableta_entrar', 'tableta_pedido', 'tableta_salir', 'tableta_cancelar', 'logout', 'login', 'static'}
COLORES_AVATAR = ['#0B3D91', '#0f766e', '#b45309', '#7c3aed', '#be123c', '#0369a1', '#15803d', '#a21caf', '#c2410c', '#334155']
ESTADOS_PEDIDO = {'PENDIENTE': ('Pendiente', '#b45309'), 'ENTREGADO': ('Entregado', '#15803d'), 'RECHAZADO': ('Rechazado', '#b91c1c'),
                  'CANCELADO': ('Cancelado', '#64748b')}

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=400)     # solo cuenta para la sesión "permanente" de la tableta
_ped_ok = False


def _asegurar_pedidos():
    global _ped_ok
    if _ped_ok:
        return
    try:
        InsumoPedido.__table__.create(bind=db.engine, checkfirst=True)
        InsumoPedidoItem.__table__.create(bind=db.engine, checkfirst=True)
        _ped_ok = True
    except Exception as e:
        print(f"Aviso: no se pudo preparar los pedidos de la tableta: {e}")


with app.app_context():
    _asegurar_pedidos()


@app.before_request
def _restringir_tableta():
    """El usuario de la tableta solo ve la pantalla de la tableta (y queda siempre conectado)."""
    if session.get('role') != ROL_TABLETA:
        return
    session.permanent = True
    if request.endpoint is None or request.endpoint in RUTAS_TABLETA:
        return
    return redirect(url_for('tableta'))


# ------------------------------------------------ PIN ------------------------------------------------
def _pin_por_defecto(t):
    """Los 4 primeros dígitos de su DNI / código (si tiene al menos 4)."""
    dig = re.sub(r'\D', '', t.codigo or '')
    return dig[:4] if len(dig) >= 4 else None


def _pin_tipo(t):
    return 'PROPIO' if t.pin_hash else ('DNI' if _pin_por_defecto(t) else None)


def _pin_correcto(t, pin):
    if t.pin_hash:
        return check_password_hash(t.pin_hash, pin)
    por_def = _pin_por_defecto(t)
    return bool(por_def) and pin == por_def


def _poner_pin(t, pin):
    """pin '' / None → vuelve al de su DNI. Devuelve mensaje de error o None."""
    pin = (pin or '').strip()
    if not pin:
        t.pin_hash = None
    elif not re.fullmatch(r'\d{4}', pin):
        return 'El PIN debe tener exactamente 4 números.'
    else:
        t.pin_hash = generate_password_hash(pin)
    t.pin_fallos, t.pin_bloqueo_hasta = 0, None
    return None


def _iniciales(nombre):
    p = [x for x in (nombre or '').split() if x]
    return ((p[0][0] if p else '?') + (p[1][0] if len(p) > 1 else '')).upper()


def _trabajador_de_la_tableta():
    """El trabajador que puso su PIN hace menos de TABLETA_MINUTOS_PEDIDO minutos en esta tableta, o None."""
    d = session.get('tab_t') or {}
    try:
        cuando = datetime.fromisoformat(d.get('h'))
    except (TypeError, ValueError):
        return None
    if hora_peru() - cuando > timedelta(minutes=TABLETA_MINUTOS_PEDIDO):
        session.pop('tab_t', None)
        return None
    t = InsumoTrabajador.query.get(d.get('id'))
    return t if t and t.activo else None


def _stock_total_insumos():
    tot = {}
    for s in InsumoStock.query.all():
        if s.empresa in EMPRESAS_INSUMOS:
            tot[s.insumo_id] = tot.get(s.insumo_id, 0) + float(s.stock_actual or 0)
    return tot


def _pedido_json(p, con_bolsas=False):
    d = {'id': p.id, 'estado': p.estado, 'estado_txt': ESTADOS_PEDIDO.get(p.estado, (p.estado,))[0],
         'fecha': p.fecha.isoformat(timespec='seconds') if p.fecha else None, 'hora': p.fecha.strftime('%d/%m %H:%M') if p.fecha else '',
         'trabajador': p.trabajador.nombre if p.trabajador else '', 'trabajador_id': p.trabajador_id,
         'area': p.area.nombre if p.area else '', 'area_id': p.area_id, 'motivo': p.motivo or '', 'nota': p.nota or '',
         'motivo_rechazo': p.motivo_rechazo or '', 'atendido_por': p.atendido_por or '',
         'items': [{'id': it.id, 'insumo_id': it.insumo_id, 'codigo': it.insumo.codigo if it.insumo else '', 'descripcion': it.insumo.descripcion if it.insumo else '',
                    'unidad': (it.insumo.unidad or '') if it.insumo else '', 'cantidad': it.cantidad, 'entregada': it.cantidad_entregada} for it in p.items]}
    if con_bolsas:
        ok = True
        for it in d['items']:
            emp, stocks = _bolsa_para(it['insumo_id'], it['cantidad'])
            it['bolsa'] = emp
            it['bolsa_txt'] = EMPRESAS_INSUMOS[emp]['corto'] if emp else None
            it['stocks'] = stocks
            ok = ok and bool(emp)
        d['entrega_rapida'] = ok and bool(p.area_id) and bool(p.motivo)
        d['por_que_no'] = None if d['entrega_rapida'] else (
            'Falta el área' if not p.area_id else ('Falta el motivo' if not p.motivo else 'No alcanza el stock en un solo inventario: usa Revisar'))
    return d


def _bolsa_para(insumo_id, cantidad):
    """Inventario recomendado para entregar `cantidad` (como en la Nueva salida): primero General si alcanza; si no, la empresa
    con más stock que alcance. Devuelve (empresa | None, {empresa: stock})."""
    stocks = {}
    for e in EMPRESAS_INSUMOS:
        st = _stock_de(insumo_id, e, crear=False)
        stocks[e] = round(float(st.stock_actual or 0), 3) if st else 0
    if stocks.get(EMPRESA_GENERAL, 0) + 1e-9 >= cantidad:
        return EMPRESA_GENERAL, stocks
    con = sorted([e for e in EMPRESAS_INSUMOS if e != EMPRESA_GENERAL and stocks[e] + 1e-9 >= cantidad], key=lambda e: -stocks[e])
    return (con[0] if con else None), stocks


def _pedido_marcar_entregado(p, hechas, items):
    """Dentro de la transacción de la salida: el pedido queda ENTREGADO con lo despachado de cada insumo."""
    entregado = {}
    for it in items:
        entregado[it['ins'].id] = entregado.get(it['ins'].id, 0) + float(it['cd'])
    for it in p.items:
        it.cantidad_entregada = round(entregado.pop(it.insumo_id, 0), 3)
    p.estado, p.fecha_atencion = 'ENTREGADO', hora_peru()
    p.atendido_por, p.atendido_user_id = session.get('nombre') or session.get('username'), session.get('user_id')
    p.salida_ids = ','.join(str(s.id) for s in hechas)[:120]


# ------------------------------------------------ pantalla de la tableta ------------------------------------------------
def _puede_tableta():
    return session.get('user_id') and session.get('role') in [ROL_TABLETA] + ROLES_ATIENDEN_PEDIDOS


@app.route('/tableta')
def tableta():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if not _puede_tableta():
        return "Acceso denegado", 403
    _asegurar_insumos()
    _asegurar_pedidos()
    return render_template('insumos_tableta.html', es_tableta=session.get('role') == ROL_TABLETA, minutos=TABLETA_MINUTOS_PEDIDO)


@app.route('/tableta/api/datos')
def tableta_datos():
    if not _puede_tableta():
        return {'status': 'error'}, 403
    _asegurar_insumos()
    tot = _stock_total_insumos()
    trab = InsumoTrabajador.query.filter_by(activo=True).order_by(InsumoTrabajador.nombre).all()
    return {'status': 'ok', 'ahora': hora_peru().isoformat(timespec='seconds'),
            'trabajadores': [{'id': t.id, 'nombre': t.nombre, 'area': t.area.nombre if t.area else '', 'area_id': t.area_id, 'cargo': t.cargo or '',
                              'ini': _iniciales(t.nombre), 'color': COLORES_AVATAR[t.id % len(COLORES_AVATAR)], 'pin': bool(_pin_tipo(t))} for t in trab],
            'areas': [{'id': a.id, 'nombre': a.nombre} for a in InsumoArea.query.filter_by(activo=True).order_by(InsumoArea.nombre).all()],
            'motivos': [m.valor for m in _catalogo_insumos('INSUMO_MOTIVO')],
            'insumos': [{'id': i.id, 'codigo': i.codigo, 'descripcion': i.descripcion, 'unidad': i.unidad or '', 'categoria': i.categoria or 'OTROS',
                         'hay': round(tot.get(i.id, 0), 3)} for i in Insumo.query.filter_by(activo=True).order_by(Insumo.descripcion).all()
                        if (i.categoria or '').upper() != 'HERRAMIENTAS']}


@app.route('/tableta/api/entrar', methods=['POST'])
def tableta_entrar():
    if not _puede_tableta():
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    d = request.get_json(silent=True) or {}
    t = InsumoTrabajador.query.get(int(d.get('trabajador_id') or 0))
    if not t or not t.activo:
        return {'status': 'error', 'msg': 'Trabajador no encontrado.'}
    ahora = hora_peru()
    if t.pin_bloqueo_hasta and t.pin_bloqueo_hasta > ahora:
        mins = max(1, int((t.pin_bloqueo_hasta - ahora).total_seconds() // 60) + 1)
        return {'status': 'error', 'msg': f'Demasiados intentos. Espera {mins} min o pide a Almacén que revise tu PIN.', 'bloqueado': True}
    if not _pin_tipo(t):
        return {'status': 'error', 'msg': 'Todavía no tienes PIN: pide a Almacén que registre tu DNI o te ponga un PIN.'}
    if not _pin_correcto(t, str(d.get('pin') or '')):
        t.pin_fallos = (t.pin_fallos or 0) + 1
        quedan = PIN_MAX_FALLOS - t.pin_fallos
        if quedan <= 0:
            t.pin_fallos, t.pin_bloqueo_hasta = 0, ahora + timedelta(minutes=PIN_BLOQUEO_MIN)
            registrar_log(f"Tableta de almacén: PIN de {t.nombre} bloqueado {PIN_BLOQUEO_MIN} min por intentos fallidos", 'bi-shield-lock', 'text-danger')
        db.session.commit()
        return {'status': 'error', 'msg': 'PIN incorrecto.' + (f' Te quedan {quedan} intento(s).' if quedan > 0 else f' Bloqueado {PIN_BLOQUEO_MIN} minutos.')}
    t.pin_fallos, t.pin_bloqueo_hasta = 0, None
    db.session.commit()
    session['tab_t'] = {'id': t.id, 'h': ahora.isoformat()}
    mios = InsumoPedido.query.filter(InsumoPedido.trabajador_id == t.id).order_by(InsumoPedido.id.desc()).limit(5).all()
    return {'status': 'ok', 'trabajador': {'id': t.id, 'nombre': t.nombre, 'area_id': t.area_id, 'area': t.area.nombre if t.area else ''},
            'mis_pedidos': [_pedido_json(p) for p in mios]}


@app.route('/tableta/api/salir', methods=['POST'])
def tableta_salir():
    session.pop('tab_t', None)
    return {'status': 'ok'}


@app.route('/tableta/api/pedido', methods=['POST'])
def tableta_pedido():
    if not _puede_tableta():
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    t = _trabajador_de_la_tableta()
    if not t:
        return {'status': 'error', 'msg': 'Se acabó el tiempo: vuelve a elegir tu nombre y poner tu PIN.', 'reiniciar': True}
    d = request.get_json(silent=True) or {}
    area = InsumoArea.query.get(int(d.get('area_id') or 0)) if d.get('area_id') else t.area
    motivo = (d.get('motivo') or '').strip()
    if not area or not area.activo:
        return {'status': 'error', 'msg': 'Elige el área.'}
    if motivo not in {v.valor for v in _catalogo_insumos('INSUMO_MOTIVO')}:
        return {'status': 'error', 'msg': 'Elige para qué es.'}
    lineas, vistos = [], set()
    for it in (d.get('items') or [])[:TABLETA_MAX_ITEMS]:
        try:
            iid, cant = int(it.get('insumo_id')), float(it.get('cantidad'))
        except (TypeError, ValueError):
            continue
        ins = Insumo.query.get(iid)
        if not ins or not ins.activo or not (0 < cant <= 100000) or iid in vistos:
            continue
        vistos.add(iid)
        lineas.append((ins, round(cant, 3)))
    if not lineas:
        return {'status': 'error', 'msg': 'Elige al menos un material.'}
    ahora = hora_peru()
    p = InsumoPedido(trabajador_id=t.id, area_id=area.id, motivo=motivo[:100], nota=' '.join((d.get('nota') or '').split())[:300] or None,
                     estado='PENDIENTE', fecha=ahora, dispositivo_user_id=session.get('user_id'))
    db.session.add(p)
    db.session.flush()
    for ins, cant in lineas:
        db.session.add(InsumoPedidoItem(pedido_id=p.id, insumo_id=ins.id, cantidad=cant))
    registrar_log(f"Tableta: {t.nombre} pidió {len(lineas)} material(es) (pedido N° {p.id}, {area.nombre})", 'bi-tablet', 'text-primary')
    db.session.commit()
    session.pop('tab_t', None)
    return {'status': 'ok', 'numero': p.id, 'items': len(lineas)}


@app.route('/tableta/api/cancelar/<int:pedido_id>', methods=['POST'])
def tableta_cancelar(pedido_id):
    """El mismo trabajador (con su PIN recién puesto) cancela su pedido mientras siga pendiente."""
    t = _trabajador_de_la_tableta()
    p = InsumoPedido.query.get_or_404(pedido_id)
    if not t or p.trabajador_id != t.id:
        return {'status': 'error', 'msg': 'Vuelve a poner tu PIN.'}
    if p.estado != 'PENDIENTE':
        return {'status': 'error', 'msg': 'Ese pedido ya fue atendido.'}
    p.estado, p.fecha_atencion, p.motivo_rechazo = 'CANCELADO', hora_peru(), 'Lo canceló el trabajador'
    db.session.commit()
    return {'status': 'ok'}


# ------------------------------------------------ Almacén: atender los pedidos ------------------------------------------------
@app.context_processor
def _ctx_pedidos_tableta():
    return {'pedidos_tableta_widget': bool(session.get('user_id')) and session.get('role') in ROLES_ATIENDEN_PEDIDOS,
            'n_pedidos_tableta': _n_pedidos_pendientes}


def _n_pedidos_pendientes():
    if 'n_ped_tab' not in g:
        try:
            g.n_ped_tab = InsumoPedido.query.filter(InsumoPedido.estado == 'PENDIENTE').count() if _ped_ok else 0
        except Exception:
            db.session.rollback()
            g.n_ped_tab = 0
    return g.n_ped_tab


@app.route('/api/insumos/pedidos/pendientes')
def insumos_pedidos_pendientes_api():
    if session.get('role') not in ROLES_ATIENDEN_PEDIDOS:
        return {'status': 'error'}, 403
    try:
        _asegurar_pedidos()
        pend = InsumoPedido.query.filter(InsumoPedido.estado == 'PENDIENTE').order_by(InsumoPedido.fecha.asc()).limit(40).all()
        return {'status': 'ok', 'ahora': hora_peru().isoformat(timespec='seconds'), 'pedidos': [_pedido_json(p, con_bolsas=True) for p in pend]}
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudieron leer los pedidos de la tableta")
        return {'status': 'error'}, 500


@app.route('/insumos/pedidos/<int:pedido_id>/entregar', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_pedido_entregar(pedido_id):
    """Entrega rápida: crea la salida con lo pedido, del inventario recomendado de cada material."""
    p = InsumoPedido.query.get_or_404(pedido_id)
    if session.get('role') not in ROLES_ATIENDEN_PEDIDOS:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    if p.estado != 'PENDIENTE':
        return {'status': 'error', 'msg': f'Ese pedido ya está {ESTADOS_PEDIDO.get(p.estado, (p.estado,))[0].lower()}.'}
    pj = _pedido_json(p, con_bolsas=True)
    if not pj['entrega_rapida']:
        return {'status': 'error', 'msg': pj['por_que_no'], 'revisar': url_for('insumos_salida_nueva', pedido=p.id)}
    f = MultiDict([('solicitado_por_id', str(p.trabajador_id)), ('recibido_por_id', str(p.trabajador_id)), ('area_id', str(p.area_id)),
                   ('motivo', p.motivo), ('motivo_detalle', (f'Pedido N° {p.id} desde la tableta' + (f' · {p.nota}' if p.nota else ''))[:300]), ('fecha', '')])
    for it in pj['items']:
        f.add('insumo_id[]', str(it['insumo_id']))
        f.add('cantidad_solicitada[]', str(it['cantidad']))
        f.add('cantidad_despachada[]', str(it['cantidad']))
        f.add('empresa_linea[]', it['bolsa'])
    hechas, area, err = _salida_insumos_crear(f, antes_de_commit=lambda hs, its: _pedido_marcar_entregado(p, hs, its))
    if err:
        return {'status': 'error', 'msg': err, 'revisar': url_for('insumos_salida_nueva', pedido=p.id)}
    return {'status': 'success', 'msg': 'Entregado: ' + ' · '.join(f"{EMPRESAS_INSUMOS[s.empresa]['corto']} N° {s.numero:06d}" for s in hechas),
            'salidas': [{'url': url_for('insumos_salida_detalle', salida_id=s.id), 'txt': f"{EMPRESAS_INSUMOS[s.empresa]['corto']} N° {s.numero:06d}"} for s in hechas]}


@app.route('/insumos/pedidos/<int:pedido_id>/rechazar', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_pedido_rechazar(pedido_id):
    p = InsumoPedido.query.get_or_404(pedido_id)
    if session.get('role') not in ROLES_ATIENDEN_PEDIDOS:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    if p.estado != 'PENDIENTE':
        return {'status': 'error', 'msg': 'Ese pedido ya fue atendido.'}
    motivo = ' '.join((request.form.get('motivo') or '').split())[:255]
    if len(motivo) < 3:
        return {'status': 'error', 'msg': 'Escribe por qué se rechaza.'}
    p.estado, p.motivo_rechazo, p.fecha_atencion = 'RECHAZADO', motivo, hora_peru()
    p.atendido_por, p.atendido_user_id = session.get('nombre') or session.get('username'), session.get('user_id')
    registrar_log(f"Rechazó el pedido de la tableta N° {p.id} de {p.trabajador.nombre if p.trabajador else '-'}: {motivo}", 'bi-x-circle', 'text-danger')
    db.session.commit()
    return {'status': 'success'}


@app.route('/insumos/pedidos')
@_ruta_insumos()
def insumos_pedidos():
    _asegurar_pedidos()
    estado = request.args.get('estado', 'PENDIENTE')
    estado = estado if estado in ESTADOS_PEDIDO or estado == 'TODOS' else 'PENDIENTE'
    q = InsumoPedido.query
    if estado != 'TODOS':
        q = q.filter(InsumoPedido.estado == estado)
    pedidos = q.order_by(InsumoPedido.id.desc()).limit(200).all()
    conteo = dict(db.session.query(InsumoPedido.estado, db.func.count(InsumoPedido.id)).group_by(InsumoPedido.estado).all())
    salidas = {}
    ids = {int(x) for p in pedidos for x in (p.salida_ids or '').split(',') if x.strip().isdigit()}
    if ids:
        salidas = {s.id: s for s in InsumoSalida.query.filter(InsumoSalida.id.in_(ids)).all()}
    return render_template('insumos_pedidos.html', pedidos=pedidos, estado=estado, estados=ESTADOS_PEDIDO, conteo=conteo, salidas=salidas,
                           empresas=EMPRESAS_INSUMOS, seccion='pedidos', puede_atender=session.get('role') in ROLES_ATIENDEN_PEDIDOS,
                           hay_tableta=User.query.filter_by(role=ROL_TABLETA).count() > 0)
