# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# AVISOS · campana de notificaciones
# tipos de aviso, configuración por usuario, API de la campana, aprobación rápida y página de avisos
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ============================ NOTIFICACIONES (campana del sistema) ============================
# Avisos para que Gerencia no se olvide de aprobar las OC/OS y Logística se entere de lo aprobado/rechazado y de los
# requerimientos nuevos. Salen en la campana (arriba a la derecha), con ventana emergente, sonido y aviso de Windows.
# Cada usuario elige en "Configurar avisos" qué recibe y cada cuánto se le recuerda lo pendiente.
TIPOS_NOTIF = {
    'OC_POR_APROBAR': {'txt': 'OC / OS por aprobar', 'ayuda': 'Cuando Logística envía una orden de compra o de servicio a Gerencia. Se recuerda mientras siga pendiente.',
                       'roles': ['admin', 'administracion'], 'defecto': ['admin'], 'icono': 'bi-hourglass-split', 'color': '#d97706'},
    'OC_APROBADA': {'txt': 'OC / OS aprobadas por Gerencia', 'ayuda': 'Para avisar al proveedor y coordinar la entrega.',
                    'roles': ['admin', 'logistica', 'administracion'], 'defecto': ['logistica'], 'icono': 'bi-patch-check-fill', 'color': '#16a34a'},
    'OC_RECHAZADA': {'txt': 'OC / OS rechazadas por Gerencia', 'ayuda': 'Con el motivo del rechazo, para corregirla.',
                     'roles': ['admin', 'logistica'], 'defecto': ['logistica'], 'icono': 'bi-x-octagon-fill', 'color': '#dc2626'},
    'REQ_NUEVO': {'txt': 'Requerimientos de compra nuevos', 'ayuda': 'Cuando Almacén u otra área pide productos o insumos que faltan.',
                  'roles': ['admin', 'logistica'], 'defecto': ['logistica'], 'icono': 'bi-clipboard-plus', 'color': '#7c3aed'},
}
RECORDAR_NOTIF = [(0, 'Solo cuando llega una nueva'), (15, 'Cada 15 minutos'), (30, 'Cada 30 minutos'), (60, 'Cada hora'),
                  (120, 'Cada 2 horas'), (240, 'Cada 4 horas')]
SONIDOS_NOTIF = {'campana': 'Campana (ding-dong)', 'alerta': 'Alerta (más fuerte, 3 tonos)', 'suave': 'Suave (un tono)'}
ROLES_NOTIF = sorted({r for t in TIPOS_NOTIF.values() for r in t['roles']})
CONSULTA_NOTIF_SEG = 30          # cada cuántos segundos la campana pregunta si hay algo nuevo


def _notif_cfg(user_id, rol):
    """Configuración del usuario (lo no guardado toma el valor recomendado)."""
    cfg = {'tipos': {k: rol in t['defecto'] for k, t in TIPOS_NOTIF.items() if rol in t['roles']},
           'popup': True, 'sonido': True, 'sonido_tipo': 'campana', 'volumen': 80, 'windows': True, 'recordar_min': 30}
    fila = NotificacionConfig.query.filter_by(user_id=user_id).first() if user_id else None
    if fila and fila.datos:
        try:
            guardado = json.loads(fila.datos)
        except (TypeError, ValueError):
            guardado = {}
        for k in ('popup', 'sonido', 'windows'):
            if isinstance(guardado.get(k), bool):
                cfg[k] = guardado[k]
        if guardado.get('sonido_tipo') in SONIDOS_NOTIF:
            cfg['sonido_tipo'] = guardado['sonido_tipo']
        if isinstance(guardado.get('volumen'), int) and 10 <= guardado['volumen'] <= 100:
            cfg['volumen'] = guardado['volumen']
        if guardado.get('recordar_min') in [m for m, _ in RECORDAR_NOTIF]:
            cfg['recordar_min'] = guardado['recordar_min']
        for k, v in (guardado.get('tipos') or {}).items():
            if k in cfg['tipos'] and isinstance(v, bool):
                cfg['tipos'][k] = v
    return cfg


def _notif_crear(tipo, titulo, texto='', url='', orden=None, req=None, empresa=None, excluir=None):
    """Deja el aviso a cada usuario que lo tiene activado. Nunca rompe la acción principal (va en un punto de guardado)."""
    try:
        with db.session.begin_nested():
            info = TIPOS_NOTIF[tipo]
            n, creados = 0, []
            for u in User.query.filter(User.role.in_(info['roles'])).all():
                if u.id == excluir or getattr(u, 'desactivado', False) or getattr(u, 'bloqueado', False):
                    continue
                if not _notif_cfg(u.id, u.role)['tipos'].get(tipo):
                    continue
                aviso = Notificacion(user_id=u.id, tipo=tipo, titulo=titulo[:150], texto=(texto or '')[:300], url=(url or '')[:300],
                                     orden_id=orden.id if orden else None, req_id=req.id if req else None,
                                     empresa=empresa or (orden.empresa if orden else None), fecha=hora_peru(), leida=False)
                db.session.add(aviso)
                creados.append(aviso)
                n += 1
            db.session.flush()
        # se mandan por Web Push al terminar la petición (ya guardados)
        g.push_cola = (g.get('push_cola') or []) + [a.id for a in creados if a.id]
        return n
    except Exception:
        app.logger.exception("No se pudo crear el aviso %s", tipo)
        return 0


def _notif_monto(orden):
    return f"{MONEDAS_OC[orden.moneda]['simbolo']} {orden.total or 0:,.2f}"


def _notif_orden_enviada(orden, reaprobacion=False):
    corto = EMPRESAS_OC.get(orden.empresa or 'ANCLAJES', {}).get('corto', '')
    titulo = (f"Re-aprobar {_oc_codigo(orden)} · {corto}" if reaprobacion else f"{_oc_codigo(orden)} por aprobar · {corto}")
    texto = f"{orden.razon_social} · {_notif_monto(orden)}" + (f" · pide {orden.solicitante_nombre}" if orden.solicitante_nombre else '')
    _notif_crear('OC_POR_APROBAR', titulo, texto, url_for('oc_detalle', orden_id=orden.id), orden=orden, excluir=session.get('user_id'))


def _notif_orden_resuelta(orden, tipo, detalle=''):
    """Gerencia aprobó o rechazó: avisa a Logística y quita el pendiente de quienes aprueban."""
    Notificacion.query.filter(Notificacion.orden_id == orden.id, Notificacion.tipo == 'OC_POR_APROBAR',
                              Notificacion.leida.is_(False)).update({'leida': True, 'fecha_leida': hora_peru()}, synchronize_session=False)
    corto = EMPRESAS_OC.get(orden.empresa or 'ANCLAJES', {}).get('corto', '')
    if tipo == 'OC_APROBADA':
        titulo = f"Gerencia APROBÓ la {_oc_codigo(orden)} · {corto}"
        texto = f"{orden.razon_social} · {_notif_monto(orden)}" + (f" · {detalle}" if detalle else '')
    else:
        titulo = f"Gerencia RECHAZÓ la {_oc_codigo(orden)} · {corto}"
        texto = f"{orden.razon_social} · Motivo: {detalle}"
    _notif_crear(tipo, titulo, texto, url_for('oc_detalle', orden_id=orden.id), orden=orden, excluir=session.get('user_id'))


def _notif_req_nuevo(r, n_items):
    texto = (f"{n_items} {'insumo(s) interno(s)' if (r.destino or 'GENERAL') == 'INSUMOS' else 'producto(s)'} · pide {r.solicitante_nombre or '-'}"
             + (f" · {(r.motivo or '').capitalize()}" if r.motivo else '') + (' · URGENTE' if r.prioridad == 'URGENTE' else ''))
    _notif_crear('REQ_NUEVO', f"Nuevo requerimiento {_req_codigo(r)}" + (' (URGENTE)' if r.prioridad == 'URGENTE' else ''), texto,
                 url_for('oc_req_detalle', req_id=r.id), req=r, empresa=None, excluir=session.get('user_id'))


def _hace_txt(fecha, ahora):
    if not fecha:
        return ''
    s = max(0, int((ahora - fecha).total_seconds()))
    if s < 60:
        return 'hace un momento'
    if s < 3600:
        return f'hace {s // 60} min'
    if s < 86400:
        return f"hace {s // 3600} h"
    d = s // 86400
    return f"hace {d} día{'s' if d != 1 else ''}"


def _notif_por_aprobar_json(ahora, puede_aprobar):
    salida = []
    for o in OrdenCompra.query.filter(OrdenCompra.estado == 'ENVIADA').order_by(OrdenCompra.fecha_envio, OrdenCompra.id).all():
        emp = EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {})
        desde = o.fecha_envio or o.fecha_registro
        horas = round((ahora - desde).total_seconds() / 3600, 1) if desde else 0
        salida.append({'id': o.id, 'codigo': _oc_codigo(o), 'tipo': o.tipo, 'tipo_txt': TIPOS_OC.get(o.tipo, ''), 'empresa': o.empresa or 'ANCLAJES',
                       'empresa_txt': emp.get('corto', ''), 'color': emp.get('color', '#0B3D91'), 'proveedor': o.razon_social or '',
                       'monto': _notif_monto(o), 'solicitante': o.solicitante_nombre or '', 'motivo': (o.motivo_compra or '').capitalize(),
                       'revision': o.revision or 0, 'hace': _hace_txt(desde, ahora), 'horas': horas, 'atrasada': horas >= 24,
                       'n_items': len(o.items), 'url': url_for('oc_detalle', orden_id=o.id), 'aprobar': puede_aprobar,
                       'resumen': url_for('notif_orden', orden_id=o.id)})
    return salida


@app.route('/notificaciones/api')
def notif_api():
    """Lo que muestra la campana. La página lo consulta sola cada 30 segundos."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid:
        return {'status': 'error', 'sesion_terminada': True}, 401
    if rol not in ROLES_NOTIF:
        return {'status': 'ok', 'activo': False}
    try:
        _asegurar_oc()
        cfg = _notif_cfg(uid, rol)
        ahora = hora_peru()
        # las de "por aprobar" ya resueltas (aprobada, rechazada, retirada, anulada) se dan por leídas solas
        pend = Notificacion.query.filter(Notificacion.user_id == uid, Notificacion.tipo == 'OC_POR_APROBAR', Notificacion.leida.is_(False)).all()
        if pend:
            vivas = {o.id for o in OrdenCompra.query.filter(OrdenCompra.id.in_([n.orden_id for n in pend if n.orden_id] or [0]),
                                                            OrdenCompra.estado == 'ENVIADA').all()}
            cambio = False
            for n in pend:
                if n.orden_id not in vivas:
                    n.leida, n.fecha_leida, cambio = True, ahora, True
            if cambio:
                db.session.commit()
        por_aprobar = []
        if cfg['tipos'].get('OC_POR_APROBAR'):
            por_aprobar = _notif_por_aprobar_json(ahora, rol in ROLES_OC_APRUEBAN)
        lista = (Notificacion.query.filter(Notificacion.user_id == uid).order_by(Notificacion.id.desc()).limit(40).all())
        ult = max([n.id for n in lista] or [0])
        novedades = []
        for n in lista:
            if n.tipo == 'OC_POR_APROBAR':
                continue                     # están en la sección "Por aprobar" (las resueltas ya no interesan)
            if len(novedades) >= 15:
                break
            info = TIPOS_NOTIF.get(n.tipo, {})
            novedades.append({'id': n.id, 'tipo': n.tipo, 'titulo': n.titulo, 'texto': n.texto or '', 'leida': bool(n.leida),
                              'hace': _hace_txt(n.fecha, ahora), 'icono': info.get('icono', 'bi-bell'), 'color': info.get('color', '#0B3D91'),
                              'ir': url_for('notif_ir', notif_id=n.id)})
        # las nuevas (para la ventana emergente, el sonido y el aviso de Windows)
        desde = request.args.get('desde', type=int)
        nuevas = []
        if desde is not None:
            for n in sorted([x for x in lista if x.id > desde and not x.leida], key=lambda x: x.id)[-5:]:
                info = TIPOS_NOTIF.get(n.tipo, {})
                nuevas.append({'id': n.id, 'tipo': n.tipo, 'titulo': n.titulo, 'texto': n.texto or '', 'icono': info.get('icono', 'bi-bell'),
                               'color': info.get('color', '#0B3D91'), 'ir': url_for('notif_ir', notif_id=n.id),
                               'resumen': url_for('notif_orden', orden_id=n.orden_id) if n.tipo == 'OC_POR_APROBAR' and n.orden_id else '',
                               'aprobar': n.tipo == 'OC_POR_APROBAR' and rol in ROLES_OC_APRUEBAN})
        no_leidas = sum(1 for n in novedades if not n['leida'])
        return {'status': 'ok', 'activo': True, 'cfg': cfg, 'por_aprobar': por_aprobar, 'novedades': novedades, 'nuevas': nuevas,
                'no_leidas': no_leidas, 'total': len(por_aprobar) + no_leidas, 'ultimo_id': ult, 'consulta_seg': CONSULTA_NOTIF_SEG}
    except Exception:
        db.session.rollback()
        app.logger.exception("Campana: no se pudo leer los avisos")
        return {'status': 'error'}, 500


@app.route('/notificaciones/<int:notif_id>/ir')
def notif_ir(notif_id):
    """Abre el aviso: lo marca como leído y lleva a la orden o requerimiento."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    n = Notificacion.query.get_or_404(notif_id)
    if n.user_id != session.get('user_id'):
        return "Acceso denegado", 403
    if not n.leida:
        n.leida, n.fecha_leida = True, hora_peru()
        db.session.commit()
    return redirect(n.url or url_for('notif_pagina'))


@app.route('/notificaciones/leer', methods=['POST'])
def notif_leer():
    """Marcar como leídas (todas o una)."""
    uid = session.get('user_id')
    if not uid:
        return {'status': 'error'}, 401
    q = Notificacion.query.filter(Notificacion.user_id == uid, Notificacion.leida.is_(False), Notificacion.tipo != 'OC_POR_APROBAR')
    nid = request.form.get('id', type=int)
    if nid:
        q = q.filter(Notificacion.id == nid)
    n = q.update({'leida': True, 'fecha_leida': hora_peru()}, synchronize_session=False)
    db.session.commit()
    return {'status': 'ok', 'n': n}


@app.route('/notificaciones/orden/<int:orden_id>')
@_ruta_oc('ver', como_json=True)
def notif_orden(orden_id):
    """Datos para aprobar rápido desde la campana (sin abrir toda la orden)."""
    o = OrdenCompra.query.get_or_404(orden_id)
    s = MONEDAS_OC[o.moneda]['simbolo']
    emp = EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {})
    ahora = hora_peru()
    docs = OrdenCompraDocumento.query.filter_by(orden_id=o.id).order_by(OrdenCompraDocumento.id).all()
    return {'id': o.id, 'codigo': _oc_codigo(o), 'tipo_txt': TIPOS_OC.get(o.tipo, ''), 'empresa_txt': emp.get('nombre', ''), 'color': emp.get('color', '#0B3D91'),
            'estado': o.estado, 'estado_txt': ESTADOS_OC.get(o.estado, {}).get('txt', o.estado), 'pendiente': o.estado == 'ENVIADA',
            'proveedor': o.razon_social or '', 'ruc': o.ruc or '', 'contacto': ' · '.join(x for x in (o.contacto, o.telefono) if x),
            'destino': DESTINOS_OC.get(o.destino, ''), 'importacion': bool(o.es_importacion),
            'solicitante': o.solicitante_nombre or '', 'area': (o.area_solicitante or '').title(), 'motivo': (o.motivo_compra or '').capitalize(),
            'motivo_detalle': o.motivo_detalle or '', 'cliente': o.cliente_razon or '', 'cotizacion': o.cotizacion or '',
            'condicion': o.condicion_pago or '', 'entrega': _oc_entrega_txt(o), 'observaciones': o.observaciones or '',
            'revision': o.revision or 0, 'motivo_edicion': o.motivo_edicion or '',
            'enviado': ((o.enviado_por.nombre_completo if o.enviado_por else '') + (' · ' + _hace_txt(o.fecha_envio, ahora) if o.fecha_envio else '')),
            'items': [{'descripcion': i.descripcion, 'codigo': i.codigo or '', 'detalle': i.detalle or '', 'cantidad': _cant_txt(i.cantidad), 'um': i.um or '',
                       'pu': f"{s} {(i.precio_unitario or 0):,.4f}".rstrip('0').rstrip('.') if round((i.precio_unitario or 0) * 100) != (i.precio_unitario or 0) * 100 else f"{s} {(i.precio_unitario or 0):,.2f}",
                       'total': f"{s} {(i.total or 0):,.2f}"} for i in o.items],
            'subtotal': f"{s} {(o.subtotal or 0):,.2f}", 'igv': f"{s} {(o.igv or 0):,.2f}", 'total': f"{s} {(o.total or 0):,.2f}",
            'sin_igv': bool(o.es_importacion),
            'docs': [{'nombre': d.nombre_original or d.tipo, 'tipo': d.tipo, 'url': url_for('oc_documento_ver', doc_id=d.id)} for d in docs],
            'url': url_for('oc_detalle', orden_id=o.id), 'pdf': url_for('oc_pdf', orden_id=o.id),
            'aprobar_url': url_for('oc_aprobar', orden_id=o.id), 'puede_aprobar': session.get('role') in ROLES_OC_APRUEBAN and o.estado == 'ENVIADA'}


@app.route('/notificaciones', methods=['GET', 'POST'])
def notif_pagina():
    """Historial de avisos y configuración (qué recibir, sonido, Windows, cada cuánto recordar)."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid:
        return redirect(url_for('login'))
    if rol not in ROLES_NOTIF:
        return "Acceso denegado", 403
    _asegurar_oc()
    if request.method == 'POST':
        f = request.form
        cfg = _notif_cfg(uid, rol)
        datos = {'tipos': {k: f.get(f'tipo_{k}') == '1' for k in cfg['tipos']}, 'popup': f.get('popup') == '1', 'sonido': f.get('sonido') == '1',
                 'windows': f.get('windows') == '1', 'sonido_tipo': f.get('sonido_tipo') if f.get('sonido_tipo') in SONIDOS_NOTIF else 'campana',
                 'volumen': min(max(f.get('volumen', 80, type=int), 10), 100),
                 'recordar_min': f.get('recordar_min', 30, type=int) if f.get('recordar_min', 30, type=int) in [m for m, _ in RECORDAR_NOTIF] else 30}
        fila = NotificacionConfig.query.filter_by(user_id=uid).first()
        if not fila:
            fila = NotificacionConfig(user_id=uid)
            db.session.add(fila)
        fila.datos, fila.fecha = json.dumps(datos), hora_peru()
        db.session.commit()
        flash('✅ Avisos guardados.')
        return redirect(url_for('notif_pagina'))
    ahora = hora_peru()
    historial = Notificacion.query.filter(Notificacion.user_id == uid).order_by(Notificacion.id.desc()).limit(60).all()
    return render_template('notificaciones.html', cfg=_notif_cfg(uid, rol), tipos=TIPOS_NOTIF, recordar=RECORDAR_NOTIF, sonidos=SONIDOS_NOTIF,
                           historial=historial, ahora=ahora, hace=_hace_txt, consulta_seg=CONSULTA_NOTIF_SEG,
                           navegadores=PushSuscripcion.query.filter_by(user_id=uid).order_by(PushSuscripcion.id).all(), push_disponible=PUSH_DISPONIBLE)


