# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v33 · NOVEDADES DEL INVENTARIO (productos de Anclajes / Import Bolts)
#   1) PRODUCTOS NUEVOS: los que se crearon hace poco en el Maestro (no el "backfill" inicial) y si ya recibieron
#      ingreso en Anclajes, en Import Bolts o en los dos. Botón "Nuevos" en cada inventario (con cuántos llegaron).
#   2) ÚLTIMAS SALIDAS: botoncito arriba (junto a la campana) para Gerencia y Vendedores con lo último que salió del
#      inventario. SIN sonido ni ventanas: solo un numerito con las que no has visto (se guarda en tu navegador).
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================

NUEVOS_DIAS = [(7, '7 días'), (15, '15 días'), (30, '30 días'), (60, '2 meses'), (90, '3 meses')]
NUEVOS_DIAS_DEFECTO = 30
ROLES_SALIDAS_RECIENTES = ['admin', 'vendedor']
SALIDAS_WIDGET_MAX = 15
INV_PRODUCTOS = {
    'ANCLAJES': {'corto': 'Anclajes', 'color': '#0B3D91', 'prod': lambda: Product, 'mov': lambda: ProductMovement, 'kardex': 'ver_kardex'},
    'IMPORTBOLTS': {'corto': 'Import Bolts', 'color': '#0f766e', 'prod': lambda: ProductImportBolts, 'mov': lambda: ProductMovementImportBolts,
                    'kardex': 'ver_kardex_importbolts'},
}


def _maestro_nuevos(dias):
    """Productos creados en el Maestro en los últimos `dias` (sin las filas de migración / backfill)."""
    desde = hora_peru() - timedelta(days=dias)
    return (MaestroProducto.query
            .filter(MaestroProducto.fecha_creacion >= desde,
                    or_(MaestroProducto.origen.is_(None), ~MaestroProducto.origen.ilike('%backfill%')))
            .order_by(MaestroProducto.fecha_creacion.desc()).limit(600).all())


def _ingresos_de(inv, skus):
    """{sku: {'p': producto, 'primero': 1er movimiento de ENTRADA, 'total': unidades ingresadas, 'n': n° de ingresos}} de ese inventario."""
    if not skus:
        return {}
    P, M = INV_PRODUCTOS[inv]['prod'](), INV_PRODUCTOS[inv]['mov']()
    q = P.query.filter(P.sku.in_(skus))
    if inv == 'ANCLAJES':
        q = q.filter(P.es_shadow_importbolts.isnot(True))
    prods = {p.id: p for p in q.all()}
    r = {p.sku: {'p': p, 'primero': None, 'total': 0, 'n': 0} for p in prods.values()}
    if not prods:
        return r
    for m in (M.query.filter(M.product_id.in_(list(prods)), M.tipo == 'ENTRADA').order_by(M.fecha.asc(), M.id.asc()).all()):
        d = r[prods[m.product_id].sku]
        d['n'] += 1
        d['total'] += int(m.cantidad or 0)
        if d['primero'] is None:
            d['primero'] = m
    return r


def _productos_nuevos(inv='TODOS', dias=NUEVOS_DIAS_DEFECTO):
    """Filas de productos nuevos: maestro + por inventario (producto, primer ingreso, total ingresado)."""
    invs = list(INV_PRODUCTOS) if inv not in INV_PRODUCTOS else [inv]
    maes = _maestro_nuevos(dias)
    skus = [m.sku for m in maes]
    datos = {i: _ingresos_de(i, skus) for i in invs}
    filas = []
    for m in maes:
        por_inv = {i: datos[i].get(m.sku) for i in invs}
        fechas = [d['primero'].fecha for d in por_inv.values() if d and d['primero']]
        filas.append({'m': m, 'inv': por_inv, 'con_ingreso': bool(fechas), 'primer_ingreso': min(fechas) if fechas else None})
    return filas


def _n_nuevos_con_ingreso(inv='TODOS', dias=NUEVOS_DIAS_DEFECTO):
    """Para el numerito del botón: cuántos productos nuevos ya recibieron ingreso. Se calcula una vez por página."""
    clave = f'_nuevos_{inv}_{dias}'
    if clave not in g:
        try:
            setattr(g, clave, sum(1 for f in _productos_nuevos(inv, dias) if f['con_ingreso']))
        except Exception:
            db.session.rollback()
            app.logger.exception("No se pudo contar los productos nuevos")
            setattr(g, clave, 0)
    return getattr(g, clave)


@app.context_processor
def _ctx_novedades_inventario():
    rol = session.get('role')
    return {'n_productos_nuevos': _n_nuevos_con_ingreso, 'salidas_widget': bool(session.get('user_id')) and rol in ROLES_SALIDAS_RECIENTES}


@app.route('/inventario/nuevos')
def inventario_nuevos():
    """Productos creados hace poco en el Maestro y si ya llegaron (primer ingreso) a Anclajes / Import Bolts."""
    if session.get('user_id') is None:
        return redirect(url_for('login'))
    inv = request.args.get('inv', 'TODOS')
    inv = inv if inv in INV_PRODUCTOS else 'TODOS'
    dias = request.args.get('dias', NUEVOS_DIAS_DEFECTO, type=int)
    dias = dias if dias in [d for d, _ in NUEVOS_DIAS] else NUEVOS_DIAS_DEFECTO
    ver = request.args.get('ver', 'con_ingreso')
    ver = ver if ver in ('con_ingreso', 'sin_ingreso', 'todos') else 'con_ingreso'
    todas = _productos_nuevos(inv, dias)
    filas = [f for f in todas if ver == 'todos' or (ver == 'con_ingreso') == f['con_ingreso']]
    if ver == 'con_ingreso':
        filas.sort(key=lambda f: f['primer_ingreso'], reverse=True)
    rol = session.get('role')
    volver = {'ANCLAJES': 'inventario', 'IMPORTBOLTS': 'inventario_importbolts'}.get(inv, 'inventario_general')
    return render_template('inventario_nuevos.html', filas=filas, inv=inv, dias=dias, ver=ver, dias_opciones=NUEVOS_DIAS,
                           invs=INV_PRODUCTOS, invs_vista=list(INV_PRODUCTOS) if inv == 'TODOS' else [inv], volver=volver,
                           n_con=sum(1 for f in todas if f['con_ingreso']), n_sin=sum(1 for f in todas if not f['con_ingreso']),
                           ver_kardex=rol in ['admin', 'almacen', 'logistica', 'administracion'],
                           ver_maestro=rol in ['admin', 'almacen', 'logistica'])


# ------------------------------------------- últimas salidas -------------------------------------------
def _salidas_recientes(limite=SALIDAS_WIDGET_MAX, desde=None, empresa='TODAS', q=''):
    """Últimas salidas de Anclajes e Import Bolts (sin los productos 'sombra' del traslado), de la más nueva a la más vieja."""
    filas = []
    for inv, cfg in INV_PRODUCTOS.items():
        if empresa not in ('TODAS', inv):
            continue
        P, M = cfg['prod'](), cfg['mov']()
        qq = db.session.query(M, P).join(P, M.product_id == P.id).filter(M.tipo == 'SALIDA')
        if inv == 'ANCLAJES':
            qq = qq.filter(P.es_shadow_importbolts.isnot(True))
        if desde:
            qq = qq.filter(M.fecha >= desde)
        if q:
            fb = _filtro_busqueda_flexible(q, P.nombre, P.sku)
            if fb is not None:
                qq = qq.filter(fb)
        for m, p in qq.order_by(M.fecha.desc(), M.id.desc()).limit(limite).all():
            filas.append((inv, m, p))
    filas.sort(key=lambda t: (t[1].fecha or datetime.min, t[1].id), reverse=True)
    return filas[:limite]


def _salida_json(inv, m, p, gerencia):
    d = {'k': f'{inv[0]}{m.id}', 'fecha': m.fecha.isoformat(timespec='seconds') if m.fecha else None,
         'hora': m.fecha.strftime('%d/%m %H:%M') if m.fecha else '', 'emp': INV_PRODUCTOS[inv]['corto'], 'color': INV_PRODUCTOS[inv]['color'],
         'sku': p.sku, 'nombre': p.nombre, 'cant': int(m.cantidad or 0), 'queda': m.stock_nuevo, 'motivo': (m.motivo or '').strip(),
         'ref': (m.referencia or '').strip()}
    if gerencia:       # el cliente y quién la registró solo lo ve Gerencia (entre vendedores no se ven los clientes de otros)
        d['cliente'] = (m.cliente_razon or '').strip()
        d['usuario'] = (m.user.nombre_completo if m.user else '') or ''
    return d


@app.route('/api/salidas/recientes')
def salidas_recientes_api():
    """Para el botoncito de "Últimas salidas" (lo consulta cada minuto, en silencio)."""
    if session.get('user_id') is None or session.get('role') not in ROLES_SALIDAS_RECIENTES:
        return {'status': 'error'}, 403
    try:
        filas = _salidas_recientes(SALIDAS_WIDGET_MAX)
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudieron leer las últimas salidas")
        return {'status': 'error'}, 500
    ger = session.get('role') == 'admin'
    return {'status': 'ok', 'ahora': hora_peru().isoformat(timespec='seconds'), 'salidas': [_salida_json(i, m, p, ger) for i, m, p in filas]}


@app.route('/salidas/recientes')
def salidas_recientes():
    """Página con más salidas (últimos días), con filtro por empresa y búsqueda."""
    if session.get('user_id') is None:
        return redirect(url_for('login'))
    if session.get('role') not in ROLES_SALIDAS_RECIENTES:
        flash('⛔ No tienes acceso a esta vista.')
        return redirect(url_for('index'))
    dias = request.args.get('dias', 3, type=int)
    dias = dias if dias in (1, 3, 7, 15, 30) else 3
    empresa = request.args.get('empresa', 'TODAS')
    empresa = empresa if empresa in INV_PRODUCTOS else 'TODAS'
    q = (request.args.get('q') or '').strip()[:80]
    filas = _salidas_recientes(400, desde=hora_peru() - timedelta(days=dias), empresa=empresa, q=q)
    ger = session.get('role') == 'admin'
    return render_template('salidas_recientes.html', filas=[_salida_json(i, m, p, ger) for i, m, p in filas], dias=dias, empresa=empresa, q=q,
                           invs=INV_PRODUCTOS, gerencia=ger, tope=len(filas) >= 400)
