# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · requerimientos de compra
# Almacén / áreas piden productos o insumos que faltan; Logística arma la OC; seguimiento y novedades
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- REQUERIMIENTOS DE COMPRA (Almacén pide -> Logística arma la OC) ----------------------------
MAX_DOCS_REQ = 3
REQ_EMPRESA_LIBRE = 'AMBAS'      # requerimiento sin empresa: Logística decide para cuál compra al armar la OC
PRIORIDADES_REQ = {'NORMAL': 'Normal', 'URGENTE': 'Urgente'}
# Avance de cada producto pedido (se calcula con las órdenes enlazadas; no se guarda)
PASOS_REQ = [('PENDIENTE', 'Esperando OC', 'bi-hourglass-split', '#b45309'),
             ('EN_OC', 'OC en preparación', 'bi-pencil-square', '#475569'),
             ('POR_APROBAR', 'OC por aprobar', 'bi-send', '#d97706'),
             ('APROBADA', 'OC aprobada · esperando llegada', 'bi-patch-check-fill', '#0B3D91'),
             ('LLEGO', 'Llegó · revisando conformidad', 'bi-truck', '#0891b2'),
             ('CONFORME', 'Conforme · por ingresar', 'bi-check-circle-fill', '#16a34a'),
             ('INGRESADO', 'Ingresado al inventario', 'bi-box-arrow-in-down', '#15803d')]
_PASO_DE_ESTADO_OC = {'BORRADOR': 1, 'ENVIADA': 2, 'APROBADA': 3, 'RECIBIDA': 4, 'CONFORME': 5}


def _req_codigo(r):
    return f"RQ-{int(r.numero or 0):05d}"


app.add_template_global(_req_codigo, 'req_codigo')
app.add_template_global(PASOS_REQ, 'pasos_req')


def _req_evento(r, accion, detalle=''):
    db.session.add(RequerimientoEvento(req_id=r.id, fecha=hora_peru(), user_id=session.get('user_id'), accion=accion, detalle=(detalle or '')[:500]))


def _req_seguimiento(items):
    """{req_item_id: {'paso', 'activos', 'caidos', 'ordenado', 'recibido', 'descartado'}} según las órdenes enlazadas.
    Si la orden se anula o se rechaza, el producto vuelve a 'Esperando OC' (y se recuerda en 'caidos').
    'recibido' = lo que ya llegó (también las entregas parciales)."""
    ids = [i.id for i in items]
    por = {}
    if ids:
        for oi in OrdenCompraItem.query.filter(OrdenCompraItem.req_item_id.in_(ids)).all():
            por.setdefault(oi.req_item_id, []).append(oi)
    recs = {}
    res = {}
    for i in items:
        lista = sorted(por.get(i.id, []), key=lambda x: x.orden_id)
        activos = [oi for oi in lista if oi.orden and oi.orden.estado not in ('ANULADA', 'RECHAZADA')]
        caidos = [oi for oi in lista if oi.orden and oi.orden.estado in ('ANULADA', 'RECHAZADA')]
        pasos = [6 if (oi.orden.estado == 'CONFORME' and (oi.fecha_ingreso or (oi.orden.destino == 'INSUMOS' and oi.orden.insumo_ingreso_id)))
                 else _PASO_DE_ESTADO_OC.get(oi.orden.estado, 1) for oi in activos]
        recibido = 0.0
        for oi in activos:
            if oi.orden.fecha_llegada:
                if oi.orden_id not in recs:
                    recs[oi.orden_id] = _oc_recepcion(oi.orden)
                recibido += recs[oi.orden_id]['items'].get(oi.id, {}).get('llego', 0)
        res[i.id] = {'paso': min(pasos) if pasos else 0, 'activos': activos, 'caidos': caidos,
                     'ordenado': round(sum(oi.cantidad or 0 for oi in activos), 4), 'recibido': round(recibido, 4),
                     'descartado': bool(getattr(i, 'descartado', False)) and not activos}
    return res


def _req_resumen(r, seg=None):
    """Estado general del requerimiento para listas y detalle. Los productos DESCARTADOS no cuentan para el avance:
    el requerimiento se cierra cuando todo lo demás quedó ingresado (o todo fue descartado)."""
    if r.estado in ('RECHAZADO', 'ANULADO'):
        return {'clave': r.estado, 'txt': 'Rechazado' if r.estado == 'RECHAZADO' else 'Anulado', 'color': '#dc2626' if r.estado == 'RECHAZADO' else '#64748b',
                'icono': 'bi-x-octagon-fill' if r.estado == 'RECHAZADO' else 'bi-slash-circle', 'con_oc': 0, 'total': len(r.items), 'paso': -1, 'descartados': 0}
    seg = seg if seg is not None else _req_seguimiento(r.items)
    vivos = [i for i in r.items if not seg[i.id]['descartado']]
    n_desc = len(r.items) - len(vivos)
    if not vivos:
        return {'clave': 'DESCARTADO', 'txt': 'Cerrado: todos los productos fueron descartados', 'color': '#64748b', 'icono': 'bi-x-circle',
                'con_oc': 0, 'total': len(r.items), 'paso': -1, 'descartados': n_desc}
    pasos = [seg[i.id]['paso'] for i in vivos]
    con_oc = sum(1 for i in vivos if seg[i.id]['activos'])
    minimo = min(pasos)
    extra = f' · {n_desc} descartado(s)' if n_desc else ''
    if minimo == 6:
        txt, color, icono = 'Completado: todo ingresado' + extra, '#15803d', 'bi-check2-all'
    elif con_oc == 0:
        txt, color, icono = 'Esperando que Logística arme la OC' + extra, '#b45309', 'bi-hourglass-split'
    elif con_oc < len(vivos):
        txt, color, icono = f'En proceso: {con_oc} de {len(vivos)} producto(s) con OC' + extra, '#0B3D91', 'bi-arrow-repeat'
    else:
        txt, color, icono = PASOS_REQ[minimo][1] + extra, PASOS_REQ[minimo][3], PASOS_REQ[minimo][2]
    return {'clave': 'COMPLETADO' if minimo == 6 else ('PENDIENTE' if con_oc == 0 else 'EN_PROCESO'), 'txt': txt, 'color': color, 'icono': icono,
            'con_oc': con_oc, 'total': len(r.items), 'paso': minimo, 'descartados': n_desc}


def _req_notificar_orden(orden, accion, texto):
    """Deja en el historial de cada requerimiento atendido por esta orden lo que pasó con ella (aprobada, llegó, conforme,
    ingresada, anulada...). Así quien lo pidió ve las novedades sin entrar a la orden."""
    ids = [i.req_item_id for i in orden.items if getattr(i, 'req_item_id', None)]
    if not ids:
        return
    for rid in sorted({ri.req_id for ri in RequerimientoItem.query.filter(RequerimientoItem.id.in_(ids)).all()}):
        db.session.add(RequerimientoEvento(req_id=rid, fecha=hora_peru(), user_id=session.get('user_id'), accion=accion, detalle=(texto or '')[:500]))


def _req_mios(user_id):
    """Requerimientos que registró o que pidió el usuario."""
    if not user_id:
        return []
    return [r for r in RequerimientoCompra.query.all() if user_id in (r.creado_por_id, r.solicitante_user_id)]


def _req_novedades(user_id, limite=30):
    """Lo que pasó en MIS requerimientos desde la última vez que los abrí (lo hecho por otros): [(req, evento)]."""
    reqs = {r.id: r for r in _req_mios(user_id)}
    if not reqs:
        return []
    vistos = {v.req_id: v.fecha for v in RequerimientoVisto.query.filter(RequerimientoVisto.user_id == user_id).all()}
    salida = []
    for ev in RequerimientoEvento.query.filter(RequerimientoEvento.req_id.in_(list(reqs))).all():
        if ev.user_id == user_id or ev.accion == 'CREADO':
            continue
        visto = vistos.get(ev.req_id)
        if visto is None or (ev.fecha and ev.fecha > visto):
            salida.append((reqs[ev.req_id], ev))
    salida.sort(key=lambda x: (x[1].fecha or datetime.min, x[1].id), reverse=True)
    return salida[:limite] if limite else salida


def _req_marcar_visto(r, user_id):
    if not user_id:
        return
    v = RequerimientoVisto.query.filter_by(req_id=r.id, user_id=user_id).first()
    if not v:
        v = RequerimientoVisto(req_id=r.id, user_id=user_id)
        db.session.add(v)
    v.fecha = hora_peru()


ACCIONES_REQ = {'CREADO': 'Requerimiento enviado', 'EDITADO': 'Requerimiento editado', 'EN_OC': 'Puesto en una orden', 'QUITADO_OC': 'Quitado de una orden',
                'RECHAZADO': 'Rechazado', 'ANULADO': 'Anulado', 'DESCARTADO': 'Producto descartado', 'REACTIVADO': 'Producto vuelve a pendiente',
                'OC_APROBADA': 'OC aprobada por Gerencia', 'OC_RECHAZADA': 'OC rechazada', 'OC_ANULADA': 'OC anulada', 'OC_LLEGO': 'Llegó material',
                'OC_CONFORME': 'Conformidad del material', 'OC_SALDO': 'No llegará el resto', 'OC_INGRESADO': 'Ingresado al inventario'}
app.add_template_global(ACCIONES_REQ, 'acciones_req')


def _req_pendientes_de_oc(empresa=None):
    """Requerimientos con productos que todavía no están en una orden activa (lo que Logística tiene por atender)."""
    q = RequerimientoCompra.query.filter(RequerimientoCompra.estado == 'PENDIENTE')
    if empresa:
        q = q.filter(RequerimientoCompra.empresa.in_([empresa, REQ_EMPRESA_LIBRE]))
    salida = []
    for r in q.order_by(RequerimientoCompra.id).all():
        seg = _req_seguimiento(r.items)
        libres = [i for i in r.items if not seg[i.id]['activos'] and not seg[i.id]['descartado']]
        if libres:
            salida.append((r, libres, seg))
    return salida


def _req_json_para_oc(empresa):
    """Requerimientos pendientes para el panel de la Nueva orden (Logística jala los productos)."""
    datos = []
    for r, libres, seg in _req_pendientes_de_oc(empresa):
        datos.append({'id': r.id, 'codigo': _req_codigo(r), 'empresa': r.empresa, 'destino': r.destino or 'GENERAL', 'solicitante': r.solicitante_nombre or '',
                      'sol_valor': f'u:{r.solicitante_user_id}' if r.solicitante_user_id else (f'n:{r.solicitante_nombre}' if r.solicitante_nombre else ''),
                      'registro': (r.creado_por.nombre_completo or r.creado_por.username) if r.creado_por else '', 'area': r.area or '', 'motivo': r.motivo or '', 'cliente_ruc': r.cliente_ruc or '',
                      'cliente_razon': r.cliente_razon or '', 'oc_cliente': r.oc_cliente or '', 'prioridad': r.prioridad or 'NORMAL',
                      'necesita': r.necesita_para.strftime('%d/%m/%Y') if r.necesita_para else '', 'nota': r.nota or '',
                      'fecha': r.fecha_registro.strftime('%d/%m/%Y') if r.fecha_registro else '',
                      'url': url_for('oc_req_detalle', req_id=r.id),
                      'docs': [{'nombre': d.nombre_original or 'documento', 'url': url_for('oc_req_documento', doc_id=d.id)}
                               for d in RequerimientoDocumento.query.filter_by(req_id=r.id).order_by(RequerimientoDocumento.id).all()],
                      'items': [{'id': i.id, 'codigo': i.codigo, 'insumo_id': i.insumo_id or '', 'descripcion': i.descripcion, 'familia': i.familia or '', 'calidad': i.calidad or '',
                                 'um': i.um or '', 'cantidad': i.cantidad, 'nota': i.nota or '',
                                 'caida': ', '.join(_oc_codigo(oi.orden) + ' ' + oi.orden.estado.lower() for oi in seg[i.id]['caidos'])}
                                for i in libres]})
    return datos


def _req_items_de_orden(orden):
    """{orden_item_id: RequerimientoItem} de los ítems de una orden que vinieron de un requerimiento."""
    ids = [i.req_item_id for i in orden.items if getattr(i, 'req_item_id', None)]
    if not ids:
        return {}
    ri = {x.id: x for x in RequerimientoItem.query.filter(RequerimientoItem.id.in_(ids)).all()}
    return {i.id: ri[i.req_item_id] for i in orden.items if getattr(i, 'req_item_id', None) in ri}


def _req_de_item_oc(item):
    """Para mostrar en Ingresos pendientes / detalle: 'RQ-00003 · Pedro' del ítem de la orden (o None)."""
    if not getattr(item, 'req_item_id', None):
        return None
    ri = RequerimientoItem.query.get(item.req_item_id)
    return ri.requerimiento if ri else None


app.add_template_global(_req_de_item_oc, 'req_de_item_oc')


@app.route('/ordenes/requerimientos')
@_ruta_oc('req_ver')
def oc_req_lista():
    defecto = 'mios' if session.get('role') == 'almacen_visor' else 'abiertos'
    vista = request.args.get('vista', defecto)
    vista = vista if vista in ('abiertos', 'mios', 'completados', 'cerrados', 'todos') else defecto
    yo = session.get('user_id')
    emp_sel = (request.args.get('empresa') or 'TODAS').upper()
    emp_sel = emp_sel if emp_sel in EMPRESAS_OC or emp_sel == 'TODAS' else 'TODAS'
    q = RequerimientoCompra.query
    if emp_sel != 'TODAS':
        q = q.filter(RequerimientoCompra.empresa == emp_sel)
    todos = q.order_by(RequerimientoCompra.id.desc()).limit(400).all()
    filas, cuenta = [], {'abiertos': 0, 'mios': 0, 'completados': 0, 'cerrados': 0, 'todos': len(todos), 'esperando': 0, 'en_proceso': 0, 'urgentes': 0}
    for r in todos:
        seg = _req_seguimiento(r.items)
        res = _req_resumen(r, seg)
        abierto = res['clave'] in ('PENDIENTE', 'EN_PROCESO')
        mio = yo in (r.creado_por_id, r.solicitante_user_id)
        cuenta['abiertos'] += abierto
        cuenta['mios'] += mio
        if vista != 'mios' or mio:          # los indicadores siguen a "Pedidos por mí" cuando se mira solo lo propio
            cuenta['esperando'] += res['clave'] == 'PENDIENTE'
            cuenta['en_proceso'] += res['clave'] == 'EN_PROCESO'
            cuenta['urgentes'] += abierto and r.prioridad == 'URGENTE'
            cuenta['completados_k'] = cuenta.get('completados_k', 0) + (res['clave'] == 'COMPLETADO')
        cuenta['completados'] += res['clave'] == 'COMPLETADO'
        cuenta['cerrados'] += res['clave'] in ('RECHAZADO', 'ANULADO', 'DESCARTADO')
        if (vista == 'todos' or (vista == 'abiertos' and abierto) or (vista == 'mios' and mio)
                or (vista == 'completados' and res['clave'] == 'COMPLETADO') or (vista == 'cerrados' and res['clave'] in ('RECHAZADO', 'ANULADO', 'DESCARTADO'))):
            filas.append((r, seg, res))
    novedades = _req_novedades(yo, limite=0)
    return render_template('oc_req_lista.html', filas=filas, vista=vista, cuenta=cuenta, emp_sel=emp_sel, empresas_oc=EMPRESAS_OC,
                           novedades=novedades[:12], con_novedad={r.id for r, _ in novedades},
                           puede_crear=session.get('role') in ROLES_REQ_CREAN, atiende=session.get('role') in ROLES_REQ_ATIENDEN,
                           puede_ver_oc=session.get('role') in ROLES_OC_VEN, prioridades=PRIORIDADES_REQ, seccion='req', hoy=hora_peru().date(),
                           estados=ESTADOS_OC)


def _contexto_form_req(previo=None, errores=None, req=None):
    motivos = sorted([m for m in OCMotivoCompra.query.all() if m.activo], key=lambda m: m.id)
    yo = User.query.get(session.get('user_id')) if session.get('user_id') else None
    return dict(previo=previo or {}, errores=errores or [], empresas_oc=EMPRESAS_OC, ums=[v.valor for v in _oc_catalogo('OC_UM')],
                solicitantes=_solicitantes_oc(), yo_valor=f"u:{session.get('user_id')}", req=req,
                docs_req=RequerimientoDocumento.query.filter_by(req_id=req.id).order_by(RequerimientoDocumento.id).all() if req else [],
                areas=[v.valor for v in _oc_catalogo('OC_AREA')], motivos_compra=[{'nombre': m.nombre, 'pide_cliente': bool(m.pide_cliente)} for m in motivos],
                prioridades=PRIORIDADES_REQ, max_docs=MAX_DOCS_REQ, seccion='req_nuevo', hoy=hora_peru().date(),
                mi_nombre=(yo.nombre_completo or yo.username) if yo else session.get('nombre', ''))


@app.route('/ordenes/requerimientos/nuevo', methods=['GET', 'POST'])
@_ruta_oc('req_crear')
def oc_req_nuevo():
    if request.method == 'GET':
        return render_template('oc_req_form.html', **_contexto_form_req({'prioridad': 'NORMAL'}))
    return _req_guardar(None)


def _req_a_previo(r):
    return {'solicitante': f'u:{r.solicitante_user_id}' if r.solicitante_user_id else f'n:{r.solicitante_nombre or ""}', 'area': r.area,
            'motivo': r.motivo, 'cliente_ruc': r.cliente_ruc, 'cliente_razon': r.cliente_razon, 'oc_cliente': r.oc_cliente,
            'prioridad': r.prioridad, 'necesita_para': r.necesita_para.isoformat() if r.necesita_para else '', 'nota': r.nota,
            'destino': r.destino or 'GENERAL',
            'items': [{'codigo': i.codigo, 'cantidad': i.cantidad, 'um': i.um, 'nota': i.nota or ''} for i in r.items if not i.descartado]}


@app.route('/ordenes/requerimientos/<int:req_id>/editar', methods=['GET', 'POST'])
@_ruta_oc('req_crear')
def oc_req_editar(req_id):
    """Corregir un requerimiento (cantidades, productos, datos) mientras Logística no haya armado ninguna orden con él."""
    r = RequerimientoCompra.query.get_or_404(req_id)
    if not _req_permisos(r, _req_seguimiento(r.items))['editar']:
        flash('⛔ Ya no se puede editar: Logística ya armó una orden con este requerimiento, o está cerrado. '
              'Si hace falta otro producto, crea un requerimiento nuevo.')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    if request.method == 'GET':
        return render_template('oc_req_form.html', **_contexto_form_req(_req_a_previo(r), req=r))
    return _req_guardar(r)


def _req_guardar(r_edit):
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    f = request.form
    errores, d = [], {}
    # El requerimiento es solo "qué productos faltan": para qué empresa se compra lo decide Logística al armar la OC
    d['empresa'] = REQ_EMPRESA_LIBRE
    d['solicitante_user_id'], d['solicitante_nombre'] = None, None
    sol = (f.get('solicitante') or '').strip()
    if sol.startswith('u:') and sol[2:].isdigit():
        u = User.query.get(int(sol[2:]))
        if u and u.role in ROLES_SOLICITANTES_OC and not getattr(u, 'desactivado', False):
            d['solicitante_user_id'], d['solicitante_nombre'] = u.id, (u.nombre_completo or u.username or '')[:120]
    elif sol.startswith('n:'):
        nombre = ' '.join(sol[2:].split()).upper()[:120]
        if nombre and nombre in {(v.valor or '').upper() for v in _oc_catalogo('OC_SOLICITANTE')}:
            d['solicitante_nombre'] = nombre
    if not d['solicitante_nombre']:
        errores.append('Elige QUIÉN LO PIDE (el vendedor, trabajador o persona que te informó).')
    areas = {(v.valor or '').upper() for v in _oc_catalogo('OC_AREA')}
    d['area'] = ' '.join((f.get('area') or '').split()).upper()[:80]
    if d['area'] not in areas:
        errores.append('Elige el ÁREA que solicita.')
    motivo = ' '.join((f.get('motivo') or '').split()).upper()[:120]
    mot = next((m for m in OCMotivoCompra.query.all() if m.activo and (m.nombre or '').upper() == motivo), None)
    if not mot:
        errores.append('Elige el MOTIVO (para qué se necesitan).')
    d['motivo'] = mot.nombre if mot else motivo
    d['cliente_ruc'] = _digitos(f.get('cliente_ruc'))[:20] or None
    d['cliente_razon'] = _limpio(f.get('cliente_razon'), 200).upper() or None
    d['oc_cliente'] = _limpio(f.get('oc_cliente'), 60).upper() or None
    if mot and mot.pide_cliente:
        if not d['cliente_ruc'] or len(d['cliente_ruc']) not in (8, 11) or len(d['cliente_razon'] or '') < 3:
            errores.append(f'Es "{mot.nombre.title()}": escribe el RUC (o DNI) y la razón social del CLIENTE.')
    d['prioridad'] = f.get('prioridad') if f.get('prioridad') in PRIORIDADES_REQ else 'NORMAL'
    d['necesita_para'] = _fecha_form(f.get('necesita_para'))
    if f.get('necesita_para') and not d['necesita_para']:
        errores.append('La fecha "para cuándo" no es válida.')
    elif d['necesita_para'] and d['necesita_para'] < hora_peru().date():
        errores.append('La fecha "para cuándo" no puede ser pasada.')
    d['nota'] = ' '.join((f.get('nota') or '').split())[:500] or None
    # De qué inventario: productos del Inventario General (para vender) o Insumos internos (uso de la empresa)
    d['destino'] = 'INSUMOS' if (f.get('destino') or '').upper() == 'INSUMOS' else 'GENERAL'
    es_ins = d['destino'] == 'INSUMOS'
    # productos: los que existen en los inventarios (Anclajes o Import Bolts; el maestro los reparte a los dos) o en el maestro de insumos
    ums = {v.valor for v in _oc_catalogo('OC_UM')}
    items, vistos = [], set()
    filas = list(zip(f.getlist('codigo[]'), f.getlist('cantidad[]'), f.getlist('um[]') + [''] * 99, f.getlist('nota_item[]') + [''] * 99))
    for n, (cod, cant, um, nota) in enumerate(filas, start=1):
        cod = (cod or '').strip().upper()
        if not cod and not (cant or '').strip():
            continue
        prod_a = prod_b = ins = None
        if es_ins:
            ins = Insumo.query.filter(func.upper(Insumo.codigo) == cod).first() if cod else None
            if not ins or ins.activo is False:
                errores.append(f'Insumo {n}: elígelo de la lista de Insumos internos.')
                continue
        else:
            prod_a = Product.query.filter(func.upper(Product.sku) == cod, Product.es_shadow_importbolts.isnot(True)).first() if cod else None
            prod_b = ProductImportBolts.query.filter(func.upper(ProductImportBolts.sku) == cod).first() if cod else None
            if not (prod_a or prod_b):
                errores.append(f'Producto {n}: elígelo de la lista del inventario.')
                continue
        prod = prod_a or prod_b
        if cod in vistos:
            errores.append(f'Producto {n} ({cod}): está repetido; súmalo en una sola línea.')
            continue
        cantidad = _num(cant)
        if cantidad is None or cantidad <= 0:
            errores.append(f'Producto {n} ({cod}): la cantidad debe ser mayor a 0.')
            continue
        if um not in ums:
            errores.append(f'Producto {n} ({cod}): elige la unidad de medida.')
            continue
        vistos.add(cod)
        nota_it = ' '.join((nota or '').split())[:200] or None
        if es_ins:
            stock_ins = sum((st.stock_actual or 0) for st in InsumoStock.query.filter_by(insumo_id=ins.id).all())
            items.append({'codigo': ins.codigo, 'insumo_id': ins.id, 'descripcion': (ins.descripcion or '')[:400], 'familia': ins.categoria or None,
                          'calidad': None, 'um': um, 'cantidad': round(cantidad, 4), 'nota': nota_it, 'stock_al_pedir': int(stock_ins)})
            continue
        items.append({'codigo': prod.sku, 'insumo_id': None, 'descripcion': (prod.nombre or '')[:400], 'familia': prod.categoria or None, 'calidad': prod.calidad or None,
                      'um': um, 'cantidad': round(cantidad, 4), 'nota': nota_it,
                      'stock_al_pedir': int((prod_a.stock_actual or 0) if prod_a else 0) + int((prod_b.stock_actual or 0) if prod_b else 0)})
    if not items:
        errores.append('Agrega al menos un insumo.' if es_ins else 'Agrega al menos un producto.')
    if len(items) > 60:
        errores.append('Máximo 60 productos por requerimiento.')
    archivos = [a for a in request.files.getlist('docs') + request.files.getlist('foto') if a and a.filename]
    docs_previos = RequerimientoDocumento.query.filter_by(req_id=r_edit.id).all() if r_edit else []
    quitar_docs = [d for d in docs_previos if str(d.id) in f.getlist('quitar_doc')]
    if len(archivos) + len(docs_previos) - len(quitar_docs) > MAX_DOCS_REQ:
        errores.append(f'Máximo {MAX_DOCS_REQ} archivos en total (OC del cliente, fotos...).')
    validos = []
    for a in archivos[:MAX_DOCS_REQ]:
        ok, info = _validar_documento_kardex(a)
        if not ok:
            errores.append(info)
        else:
            validos.append((a, info))
    if errores:
        previo = {**{k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in d.items()}, 'solicitante': sol,
                  'items': [{'codigo': c, 'cantidad': ca, 'um': u, 'nota': no} for c, ca, u, no in filas if c or ca]}
        return render_template('oc_req_form.html', **_contexto_form_req(previo, errores, req=r_edit))
    claves, borrar = [], []
    if r_edit:
        return _req_guardar_edicion(r_edit, d, items, validos, quitar_docs)
    try:
        for intento in range(3):
            try:
                numero = int(db.session.query(func.max(RequerimientoCompra.numero)).scalar() or 0) + 1
                r = RequerimientoCompra(numero=numero, estado='PENDIENTE', fecha_registro=hora_peru(), creado_por_id=session.get('user_id'), **d)
                db.session.add(r)
                db.session.flush()
                break
            except IntegrityError:
                db.session.rollback()
                if intento == 2:
                    raise
        for n, it in enumerate(items, start=1):
            db.session.add(RequerimientoItem(req_id=r.id, item=n, **it))
        _req_subir_docs(r, validos, claves)
        _req_evento(r, 'CREADO', f"{len(items)} {'insumo(s) interno(s)' if es_ins else 'producto(s)'}"
                                 + (f" · {len(validos)} archivo(s)" if validos else '') + (' · URGENTE' if d['prioridad'] == 'URGENTE' else ''))
        registrar_log(f"Pidió a Logística {_req_codigo(r)}: {len(items)} producto(s)", 'bi-clipboard-plus', 'text-primary')
        _notif_req_nuevo(r, len(items))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception("No se pudo guardar el requerimiento")
        flash(f'⛔ No se pudo guardar el requerimiento (no se guardó nada): {e}')
        return render_template('oc_req_form.html', **_contexto_form_req({**d, 'solicitante': sol}, []))
    flash(f'✅ {_req_codigo(r)} enviado a Logística. Aquí verás cuándo arman la OC, si la aprueban, si llegó y si quedó conforme.')
    return redirect(url_for('oc_req_detalle', req_id=r.id))


def _req_guardar_edicion(r, d, items, validos, quitar_docs):
    """Guarda la edición: datos, productos (se reemplazan) y archivos (se agregan / se quitan). Queda en el historial qué cambió."""
    antes = {i.codigo: (i.cantidad, i.um) for i in r.items if not i.descartado}
    claves, borrar = [], []
    try:
        cambios = []
        if (r.destino or 'GENERAL') != d['destino']:
            cambios.append('Ahora es de ' + ('Insumos internos' if d['destino'] == 'INSUMOS' else 'Inventario General'))
            r.destino = d['destino']
        for campo, etq in (('solicitante_nombre', 'Lo pide'), ('area', 'Área'), ('motivo', 'Motivo'), ('cliente_razon', 'Cliente'),
                           ('oc_cliente', 'OC cliente'), ('prioridad', 'Prioridad'), ('necesita_para', 'Para cuándo'), ('nota', 'Nota')):
            if (getattr(r, campo) or None) != (d.get(campo) or None):
                cambios.append(etq)
            setattr(r, campo, d.get(campo))
        r.solicitante_user_id = d.get('solicitante_user_id')
        r.cliente_ruc = d.get('cliente_ruc')
        despues = {it['codigo']: (it['cantidad'], it['um']) for it in items}
        for cod in despues:
            if cod not in antes:
                cambios.append(f"+ {cod} {_cant_txt(despues[cod][0])} {despues[cod][1]}")
            elif antes[cod] != despues[cod]:
                cambios.append(f"{cod}: {_cant_txt(antes[cod][0])} → {_cant_txt(despues[cod][0])} {despues[cod][1]}")
        cambios += [f"− {cod}" for cod in antes if cod not in despues]
        for viejo in list(r.items):
            if not viejo.descartado:
                db.session.delete(viejo)
        db.session.flush()
        base = max([i.item for i in r.items] or [0])
        for n, it in enumerate(items, start=1):
            db.session.add(RequerimientoItem(req_id=r.id, item=base + n, **it))
        for doc in quitar_docs:
            borrar.append(doc.s3_key)
            cambios.append(f"quitó {doc.nombre_original}")
            db.session.delete(doc)
        _req_subir_docs(r, validos, claves)
        if validos:
            cambios.append(f"{len(validos)} archivo(s) nuevo(s)")
        _req_evento(r, 'EDITADO', '; '.join(cambios) or 'Sin cambios')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception("No se pudo editar el requerimiento")
        flash(f'⛔ No se pudo guardar (no se cambió nada): {e}')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    _borrar_de_s3(borrar)
    flash(f'✅ {_req_codigo(r)} actualizado.')
    return redirect(url_for('oc_req_detalle', req_id=r.id))


def _req_subir_docs(r, validos, claves):
    for a, (ext, mime, tamano) in validos:
        clave = f"requerimientos/{r.id}/{uuid.uuid4().hex}.{ext}"
        a.stream.seek(0)
        s3_client.upload_fileobj(a.stream, S3_BUCKET_NAME, clave, ExtraArgs={'ContentType': mime})
        claves.append(clave)
        db.session.add(RequerimientoDocumento(req_id=r.id, s3_key=clave, nombre_original=secure_filename(a.filename)[:200] or f'documento.{ext}',
                                              content_type=mime, tamano_bytes=tamano, subido_por=session.get('nombre', ''), fecha=hora_peru()))


def _req_permisos(r, seg):
    rol = session.get('role')
    con_oc = any(seg[i.id]['activos'] for i in r.items)
    abierto = r.estado == 'PENDIENTE' and not all(seg[i.id]['descartado'] for i in r.items)    # todo descartado = cerrado
    duenio = rol == 'admin' or session.get('user_id') in (r.creado_por_id, r.solicitante_user_id)
    return {'armar': rol in ROLES_REQ_ATIENDEN and abierto and any(not seg[i.id]['activos'] and not seg[i.id]['descartado'] for i in r.items),
            'rechazar': rol in ROLES_REQ_ATIENDEN and abierto and not con_oc,
            'anular': abierto and not con_oc and duenio,
            'editar': abierto and not con_oc and (duenio or rol in ROLES_REQ_ATIENDEN),
            'descartar': rol in ROLES_REQ_ATIENDEN and r.estado == 'PENDIENTE',
            'ver_oc': rol in ROLES_OC_VEN}


@app.route('/ordenes/requerimientos/item/<int:item_id>/descartar', methods=['POST'])
@_ruta_oc('editar')
def oc_req_descartar(item_id):
    """Logística descarta UN producto del requerimiento (no se comprará), con motivo de la lista + descripción.
    El requerimiento se cierra cuando todo lo demás quedó comprado e ingresado (o todo fue descartado)."""
    ri = RequerimientoItem.query.get_or_404(item_id)
    r = ri.requerimiento
    destino = url_for('oc_req_detalle', req_id=r.id)
    seg = _req_seguimiento(r.items)
    if r.estado != 'PENDIENTE' or ri.descartado:
        flash('⛔ Ese producto ya está descartado o el requerimiento está cerrado.')
        return redirect(destino)
    if seg[ri.id]['activos']:
        flash(f"⛔ {ri.codigo} ya está en la {_oc_codigo(seg[ri.id]['activos'][0].orden)}: quítalo de esa orden (o anúlala) antes de descartarlo.")
        return redirect(destino)
    opcion = OCMotivoRechazo.query.get(request.form.get('motivo_id', type=int)) if request.form.get('motivo_id', type=int) else None
    if not opcion or opcion.uso != 'DESCARTE':
        flash('⛔ Elige el motivo por el que no se comprará.')
        return redirect(destino)
    detalle = ' '.join((request.form.get('motivo') or '').split())[:300]
    ri.descartado, ri.descartado_por_id, ri.fecha_descarte = True, session.get('user_id'), hora_peru()
    ri.descarte_categoria, ri.descarte_opcion, ri.descarte_motivo = opcion.categoria, opcion.motivo, detalle or None
    _req_evento(r, 'DESCARTADO', f"{ri.codigo} {_cant_txt(ri.cantidad)} {ri.um or ''}: {_req_motivo_txt(opcion.categoria, opcion.motivo, detalle)}")
    registrar_log(f"Descartó {ri.codigo} del {_req_codigo(r)}: {opcion.motivo}", 'bi-x-circle', 'text-danger')
    db.session.commit()
    flash(f'{ri.codigo} descartado: no se comprará. Queda registrado con el motivo.')
    return redirect(destino)


@app.route('/ordenes/requerimientos/item/<int:item_id>/reactivar', methods=['POST'])
@_ruta_oc('editar')
def oc_req_reactivar(item_id):
    ri = RequerimientoItem.query.get_or_404(item_id)
    r = ri.requerimiento
    if r.estado == 'PENDIENTE' and ri.descartado:
        ri.descartado, ri.descartado_por_id, ri.fecha_descarte = False, None, None
        ri.descarte_categoria, ri.descarte_opcion, ri.descarte_motivo = None, None, None
        _req_evento(r, 'REACTIVADO', f"{ri.codigo} vuelve a esperar OC")
        db.session.commit()
        flash(f'{ri.codigo} vuelve a "Esperando OC".')
    return redirect(url_for('oc_req_detalle', req_id=r.id))


@app.route('/ordenes/requerimientos/<int:req_id>')
@_ruta_oc('req_ver')
def oc_req_detalle(req_id):
    r = RequerimientoCompra.query.get_or_404(req_id)
    seg = _req_seguimiento(r.items)
    docs = RequerimientoDocumento.query.filter_by(req_id=r.id).order_by(RequerimientoDocumento.id).all()
    eventos = RequerimientoEvento.query.filter_by(req_id=r.id).order_by(RequerimientoEvento.fecha.desc(), RequerimientoEvento.id.desc()).all()
    ordenes = {}
    for i in r.items:
        for oi in seg[i.id]['activos'] + seg[i.id]['caidos']:
            ordenes[oi.orden.id] = oi.orden
    nuevos_ids = {ev.id for _, ev in _req_novedades(session.get('user_id'), limite=0) if ev.req_id == r.id}
    _req_marcar_visto(r, session.get('user_id'))
    db.session.commit()
    return render_template('oc_req_detalle.html', r=r, seg=seg, res=_req_resumen(r, seg), docs=docs, eventos=eventos, p=_req_permisos(r, seg),
                           motivos_rech=_oc_motivos('RECHAZO', 'RQ'), motivos_anul=_oc_motivos('ANULACION', 'RQ'),
                           motivos_desc=_oc_motivos('DESCARTE', 'RQ'), nuevos_ids=nuevos_ids,
                           ordenes=sorted(ordenes.values(), key=lambda o: o.id), estados=ESTADOS_OC, empresas_oc=EMPRESAS_OC,
                           prioridades=PRIORIDADES_REQ, seccion='req', hoy=hora_peru().date())


def _req_opcion_motivo(uso):
    """(opción elegida, detalle) del formulario de rechazo/anulación de un requerimiento; opción None si no es válida."""
    opcion = OCMotivoRechazo.query.get(request.form.get('motivo_id', type=int)) if request.form.get('motivo_id', type=int) else None
    if not opcion or (opcion.uso or 'RECHAZO') != uso or (opcion.aplica or 'AMBAS') != 'RQ':
        opcion = None
    return opcion, ' '.join((request.form.get('motivo') or '').split())[:300]


def _req_motivo_txt(categoria, opcion, detalle):
    txt = ' · '.join(x for x in (categoria, opcion) if x)
    return f"{txt} — {detalle}" if txt and detalle else (txt or detalle or '')


app.add_template_global(_req_motivo_txt, 'req_motivo_txt')


@app.route('/ordenes/requerimientos/<int:req_id>/rechazar', methods=['POST'])
@_ruta_oc('editar')
def oc_req_rechazar(req_id):
    r = RequerimientoCompra.query.get_or_404(req_id)
    if not _req_permisos(r, _req_seguimiento(r.items))['rechazar']:
        flash('⛔ No se puede rechazar: ya tiene productos en una orden o no está pendiente.')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    opcion, detalle = _req_opcion_motivo('RECHAZO')
    if not opcion:
        flash('⛔ Elige el motivo del rechazo (lo verá quien lo pidió).')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    r.estado, r.rechazado_por_id, r.fecha_rechazo = 'RECHAZADO', session.get('user_id'), hora_peru()
    r.rechazo_categoria, r.rechazo_opcion, r.motivo_rechazo = opcion.categoria, opcion.motivo, detalle or None
    texto = _req_motivo_txt(opcion.categoria, opcion.motivo, detalle)
    _req_evento(r, 'RECHAZADO', texto)
    registrar_log(f"Rechazó el requerimiento {_req_codigo(r)}: {texto}", 'bi-x-octagon', 'text-danger')
    db.session.commit()
    flash(f'{_req_codigo(r)} rechazado.')
    return redirect(url_for('oc_req_detalle', req_id=r.id))


@app.route('/ordenes/requerimientos/<int:req_id>/anular', methods=['POST'])
@_ruta_oc('req_crear')
def oc_req_anular(req_id):
    r = RequerimientoCompra.query.get_or_404(req_id)
    if not _req_permisos(r, _req_seguimiento(r.items))['anular']:
        flash('⛔ Solo quien lo pidió (o Gerencia) lo anula, y solo si Logística todavía no armó una orden con él.')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    opcion, detalle = _req_opcion_motivo('ANULACION')
    if not opcion:
        flash('⛔ Elige el motivo de la anulación.')
        return redirect(url_for('oc_req_detalle', req_id=r.id))
    r.estado, r.anulado_por_id, r.fecha_anulacion = 'ANULADO', session.get('user_id'), hora_peru()
    r.anulacion_categoria, r.anulacion_opcion, r.motivo_anulacion = opcion.categoria, opcion.motivo, detalle or None
    _req_evento(r, 'ANULADO', _req_motivo_txt(opcion.categoria, opcion.motivo, detalle))
    db.session.commit()
    flash(f'{_req_codigo(r)} anulado.')
    return redirect(url_for('oc_req_detalle', req_id=r.id))


@app.route('/ordenes/requerimientos/documento/<int:doc_id>')
@_ruta_oc('req_ver')
def oc_req_documento(doc_id):
    doc = RequerimientoDocumento.query.get_or_404(doc_id)
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception as e:
        return f"<h3>No se pudo recuperar el documento</h3><p>{html.escape(str(e))}</p>", 404
    ext = doc.s3_key.rsplit('.', 1)[-1].lower()
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=doc.content_type or 'application/octet-stream',
                     as_attachment=request.args.get('download') == '1', download_name=secure_filename(f"requerimiento{doc.req_id}_{doc.id}.{ext}"))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


