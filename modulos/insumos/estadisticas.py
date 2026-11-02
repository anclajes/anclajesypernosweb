# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# INSUMOS INTERNOS · lotes, precios y estadísticas
# - Ficha de precios de un insumo: lotes vigentes (en el orden en que salen, PEPS), lotes ya vacíos / anulados,
#   historial de precios de compra y resumen por proveedor. Poner / corregir el precio de un lote.
# - Estadísticas: qué se compra y se consume más, a quién conviene comprar (mejores precios), proveedores,
#   evolución mensual y alertas (por agotarse, sin movimiento, precio subiendo).
# Soles y dólares SIEMPRE por separado (no se convierte).
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================

def _compras_insumos(empresa=None, desde=None, hasta=None, insumo_id=None):
    """Ítems comprados (ingresos no anulados, con precio) -> lista de dicts con fecha, insumo, proveedor, cantidad, precio y moneda."""
    q = (db.session.query(InsumoIngresoDetalle, InsumoIngreso)
         .join(InsumoIngreso, InsumoIngreso.id == InsumoIngresoDetalle.ingreso_id)
         .filter(InsumoIngreso.estado == 'REGISTRADO'))
    if empresa in EMPRESAS_INSUMOS:
        q = q.filter(InsumoIngreso.empresa == empresa)
    if insumo_id:
        q = q.filter(InsumoIngresoDetalle.insumo_id == insumo_id)
    if desde:
        q = q.filter(InsumoIngreso.fecha >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        q = q.filter(InsumoIngreso.fecha < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
    res = []
    for d, ing in q.order_by(InsumoIngreso.fecha, InsumoIngreso.id).all():
        if d.precio_pendiente or not (d.precio_unitario or 0) > 0:
            continue
        res.append({'fecha': ing.fecha, 'ingreso': ing, 'insumo_id': d.insumo_id, 'insumo': d.insumo, 'cantidad': float(d.cantidad or 0),
                    'precio': float(d.precio_unitario), 'total': float(d.precio_total or 0), 'moneda': 'USD' if ing.moneda == 'USD' else 'PEN',
                    'proveedor': (ing.razon_social or 'Sin proveedor').strip(), 'ruc': ing.ruc or '', 'empresa': ing.empresa,
                    'factura': ing.numero_factura or ''})
    return res


def _resumen_precios(compras):
    """Por insumo y moneda: último, mejor (mínimo), máximo y promedio pagado (ponderado); y por proveedor."""
    grupos = {}
    for c in compras:
        g = grupos.setdefault((c['insumo_id'], c['moneda']), {'insumo': c['insumo'], 'moneda': c['moneda'], 'compras': [], 'prov': {}})
        g['compras'].append(c)
        p = g['prov'].setdefault(c['proveedor'], {'proveedor': c['proveedor'], 'n': 0, 'cant': 0.0, 'total': 0.0, 'min': None, 'ultimo': None})
        p['n'] += 1
        p['cant'] += c['cantidad']
        p['total'] += c['cantidad'] * c['precio']
        p['min'] = c['precio'] if p['min'] is None else min(p['min'], c['precio'])
        p['ultimo'] = c                                  # vienen ordenadas por fecha
    filas = []
    hace_un_anio = hora_peru() - timedelta(days=365)
    for g in grupos.values():
        cs = g['compras']
        ultimo = cs[-1]
        mejor = min(cs, key=lambda c: (c['precio'], -c['fecha'].timestamp()))
        cant = sum(c['cantidad'] for c in cs)
        prom = sum(c['cantidad'] * c['precio'] for c in cs) / cant if cant else 0
        provs = sorted(g['prov'].values(), key=lambda p: p['total'] / p['cant'] if p['cant'] else 0)
        for p in provs:
            p['prom'] = p['total'] / p['cant'] if p['cant'] else 0
        # a quién conviene: el de menor precio promedio entre los que vendieron en el último año (si no, el de menor precio)
        recientes = [p for p in provs if p['ultimo']['fecha'] >= hace_un_anio]
        recomendado = (recientes or provs)[0] if provs else None
        filas.append({'insumo': g['insumo'], 'moneda': g['moneda'], 'n': len(cs), 'cantidad': cant, 'ultimo': ultimo, 'mejor': mejor,
                      'maximo': max(c['precio'] for c in cs), 'promedio': prom, 'provs': provs, 'recomendado': recomendado,
                      'dif_pct': round(100 * (ultimo['precio'] - mejor['precio']) / mejor['precio'], 1) if mejor['precio'] else 0,
                      'sobrecosto': round((ultimo['precio'] - mejor['precio']) * ultimo['cantidad'], 2),
                      'sube': prom > 0 and ultimo['precio'] > prom * 1.10})
    return filas


@app.route('/insumos/ficha/<int:insumo_id>')
@_ruta_insumos()
def insumos_ficha(insumo_id):
    """Lotes y precios de UN insumo en una empresa: lo que hay (en el orden en que sale), lo que ya se vació, y el historial."""
    ins = Insumo.query.get_or_404(insumo_id)
    empresa = _empresa_param()
    st = _stock_de(ins.id, empresa, crear=False)
    todos = (InsumoLote.query.filter(InsumoLote.insumo_id == ins.id, InsumoLote.empresa == empresa)
             .order_by(InsumoLote.fecha, InsumoLote.id).all())
    vigentes = [l for l in todos if l.estado == 'ACTIVO' and (l.cantidad_restante or 0) > 1e-9]
    pend_vacios = [l for l in todos if l.estado == 'ACTIVO' and (l.cantidad_restante or 0) <= 1e-9 and l.costo_unitario is None]
    historicos = sorted([l for l in todos if l not in vigentes and l not in pend_vacios], key=lambda l: (l.fecha, l.id), reverse=True)
    r = _resumen_lotes(vigentes)
    compras = _compras_insumos(empresa, insumo_id=ins.id)
    resumen = _resumen_precios(compras)
    # gráfico: precio pagado en cada compra, una serie por proveedor (los 5 con más compras), por moneda
    graf = {}
    for mon in ('PEN', 'USD'):
        cs = [c for c in compras if c['moneda'] == mon]
        if not cs:
            continue
        por_prov = {}
        for c in cs:
            por_prov.setdefault(c['proveedor'], []).append({'x': c['fecha'].strftime('%Y-%m-%d'), 'y': round(c['precio'], 4),
                                                            'f': c['factura'], 'q': c['cantidad']})
        top = sorted(por_prov.items(), key=lambda kv: -len(kv[1]))
        series = [{'nombre': k, 'puntos': v} for k, v in top[:5]]
        if len(top) > 5:
            series.append({'nombre': 'Otros', 'puntos': sorted([p for _, v in top[5:] for p in v], key=lambda p: p['x'])})
        graf[mon] = series
    # cuánto salió de cada lote (y en cuántas salidas)
    usos = {}
    for lid, n, q in (db.session.query(InsumoSalidaLote.lote_id, func.count(InsumoSalidaLote.id), func.sum(InsumoSalidaLote.cantidad))
                      .join(InsumoSalida, InsumoSalida.id == InsumoSalidaLote.salida_id)
                      .filter(InsumoSalidaLote.lote_id.in_([l.id for l in todos] or [0]), InsumoSalida.estado == 'REGISTRADA')
                      .group_by(InsumoSalidaLote.lote_id).all()):
        usos[lid] = {'n': n, 'q': float(q or 0)}
    return render_template('insumos_ficha.html', ins=ins, empresa=empresa, empresas=EMPRESAS_INSUMOS, st=st, vigentes=vigentes,
                           pend_vacios=pend_vacios, historicos=historicos[:300], r=r, compras=list(reversed(compras))[:300], resumen=resumen,
                           graf=graf, usos=usos, puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN,
                           es_admin=session.get('role') == 'admin', seccion='inventario')


@app.route('/insumos/estadisticas')
@_ruta_insumos()
def insumos_estadisticas():
    """Estadísticas de insumos: qué se compra y se consume más, a quién conviene comprar, proveedores y alertas."""
    ahora = hora_peru()
    empresa = request.args.get('empresa', 'AMBAS')
    empresa = empresa if empresa in EMPRESAS_INSUMOS else 'AMBAS'
    hasta = _fecha_param('hasta', ahora.date())
    desde = _fecha_param('desde', (ahora - timedelta(days=365)).date())
    if desde > hasta:
        desde, hasta = hasta, desde
    categoria = request.args.get('categoria', '')
    en_cat = lambda ins: not categoria or (ins.categoria or '') == categoria
    compras = [c for c in _compras_insumos(empresa, desde, hasta) if en_cat(c['insumo'])]

    # consumo (salidas no anuladas) en el rango
    qs = (db.session.query(InsumoSalidaDetalle, InsumoSalida).join(InsumoSalida, InsumoSalida.id == InsumoSalidaDetalle.salida_id)
          .filter(InsumoSalida.estado == 'REGISTRADA', InsumoSalida.fecha >= datetime.combine(desde, datetime.min.time()),
                  InsumoSalida.fecha < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1)))
    if empresa in EMPRESAS_INSUMOS:
        qs = qs.filter(InsumoSalida.empresa == empresa)
    consumos = [(d, s) for d, s in qs.all() if en_cat(d.insumo)]

    kpi = {'comprado': sum(c['total'] for c in compras if c['moneda'] == 'PEN'), 'comprado_usd': sum(c['total'] for c in compras if c['moneda'] == 'USD'),
           'consumido': sum(d.costo_total or 0 for d, _ in consumos), 'consumido_usd': sum(d.costo_total_usd or 0 for d, _ in consumos),
           'n_compras': len({c['ingreso'].id for c in compras}), 'n_prov': len({c['proveedor'] for c in compras}),
           'n_salidas': len({s.id for _, s in consumos}), 'sc_consumido': sum(d.cantidad_sin_costo or 0 for d, _ in consumos)}

    # lotes vigentes: valor real del inventario y lotes sin precio
    ql = InsumoLote.query.filter(InsumoLote.estado == 'ACTIVO')
    if empresa in EMPRESAS_INSUMOS:
        ql = ql.filter(InsumoLote.empresa == empresa)
    lotes = [l for l in ql.all() if en_cat(l.insumo)]
    rv = _resumen_lotes(lotes)
    kpi['valor'], kpi['valor_usd'] = rv['v_pen'], rv['v_usd']
    sin_precio = [l for l in lotes if l.costo_unitario is None]
    kpi['lotes_sp'] = len(sin_precio)

    # mensual: comprado vs consumido (por moneda)
    meses = []
    y, m = hasta.year, hasta.month
    for _ in range(12):
        meses.insert(0, (y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    mensual = {mon: {'comprado': [0.0] * 12, 'consumido': [0.0] * 12} for mon in ('PEN', 'USD')}
    idx = {mm: n for n, mm in enumerate(meses)}
    for c in compras:
        n = idx.get((c['fecha'].year, c['fecha'].month))
        if n is not None:
            mensual[c['moneda']]['comprado'][n] += c['total']
    for d, s in consumos:
        n = idx.get((s.fecha.year, s.fecha.month))
        if n is not None:
            mensual['PEN']['consumido'][n] += d.costo_total or 0
            mensual['USD']['consumido'][n] += d.costo_total_usd or 0
    hay_usd = any(mensual['USD']['comprado']) or any(mensual['USD']['consumido'])

    # lo que más se compra (por monto, por moneda) y lo que más se consume
    top_compra = {}
    for c in compras:
        t = top_compra.setdefault((c['insumo_id'], c['moneda']), {'insumo': c['insumo'], 'moneda': c['moneda'], 'cant': 0.0, 'total': 0.0, 'n': 0})
        t['cant'] += c['cantidad']
        t['total'] += c['total']
        t['n'] += 1
    top_compra = sorted(top_compra.values(), key=lambda t: (t['moneda'] != 'PEN', -t['total']))
    top_consumo = {}
    for d, s in consumos:
        t = top_consumo.setdefault(d.insumo_id, {'insumo': d.insumo, 'cant': 0.0, 'total': 0.0, 'total_usd': 0.0, 'sc': 0.0, 'n': 0, 'areas': {}})
        t['cant'] += d.cantidad_despachada or 0
        t['total'] += d.costo_total or 0
        t['total_usd'] += d.costo_total_usd or 0
        t['sc'] += d.cantidad_sin_costo or 0
        t['n'] += 1
        a = s.area.nombre if s.area else 'Sin área'
        t['areas'][a] = t['areas'].get(a, 0) + (d.cantidad_despachada or 0)
    for t in top_consumo.values():
        t['area_top'] = max(t['areas'].items(), key=lambda kv: kv[1])[0] if t['areas'] else ''
    top_consumo_monto = sorted(top_consumo.values(), key=lambda t: (-t['total'], -t['total_usd']))[:15]
    top_consumo_cant = sorted(top_consumo.values(), key=lambda t: -t['cant'])[:15]

    # mejores precios por insumo y proveedores
    precios = sorted(_resumen_precios(compras), key=lambda f: (f['moneda'] != 'PEN', -f['sobrecosto'], f['insumo'].codigo))
    mejores = {}
    for f in precios:
        mejores.setdefault((f['mejor']['proveedor'], f['moneda']), 0)
        mejores[(f['mejor']['proveedor'], f['moneda'])] += 1
    provs = {}
    for c in compras:
        p = provs.setdefault((c['proveedor'], c['moneda']), {'proveedor': c['proveedor'], 'ruc': c['ruc'], 'moneda': c['moneda'], 'total': 0.0,
                                                             'ingresos': set(), 'insumos': set(), 'ultima': c['fecha']})
        p['total'] += c['total']
        p['ingresos'].add(c['ingreso'].id)
        p['insumos'].add(c['insumo_id'])
        p['ultima'] = max(p['ultima'], c['fecha'])
    proveedores = sorted(({**p, 'n': len(p['ingresos']), 'n_ins': len(p['insumos']), 'mejor_en': mejores.get((p['proveedor'], p['moneda']), 0)}
                          for p in provs.values()), key=lambda p: (p['moneda'] != 'PEN', -p['total']))

    # alertas: por agotarse (cobertura < 15 días o bajo el mínimo), sin movimiento (180 días), precio subiendo
    alertas = {'agotar': [], 'quieto': [], 'sube': [f for f in precios if f['sube']]}
    q90 = (db.session.query(InsumoSalidaDetalle.insumo_id, InsumoSalida.empresa, func.sum(InsumoSalidaDetalle.cantidad_despachada))
           .join(InsumoSalida, InsumoSalida.id == InsumoSalidaDetalle.salida_id)
           .filter(InsumoSalida.estado == 'REGISTRADA', InsumoSalida.fecha >= ahora - timedelta(days=90))
           .group_by(InsumoSalidaDetalle.insumo_id, InsumoSalida.empresa).all())
    cons90 = {(i, e): float(q or 0) for i, e, q in q90}
    qst = InsumoStock.query
    if empresa in EMPRESAS_INSUMOS:
        qst = qst.filter(InsumoStock.empresa == empresa)
    for s_ in qst.all():
        if not s_.insumo or not s_.insumo.activo or not en_cat(s_.insumo):
            continue
        stock, minimo = float(s_.stock_actual or 0), float(s_.stock_minimo or 0)
        diario = cons90.get((s_.insumo_id, s_.empresa), 0) / 90
        cobertura = round(stock / diario) if diario > 0 else None
        fila = {'insumo': s_.insumo, 'empresa': s_.empresa, 'stock': stock, 'minimo': minimo, 'diario': diario, 'cobertura': cobertura,
                'ultima': s_.ultima_salida}
        if (minimo > 0 and stock <= minimo) or (cobertura is not None and cobertura < 15):
            alertas['agotar'].append(fila)
        elif stock > 0 and (not s_.ultima_salida or s_.ultima_salida < ahora - timedelta(days=180)):
            alertas['quieto'].append(fila)
    alertas['agotar'].sort(key=lambda f: (f['cobertura'] if f['cobertura'] is not None else -1))
    alertas['quieto'].sort(key=lambda f: f['ultima'] or datetime(2000, 1, 1))

    return render_template('insumos_estadisticas.html', empresa=empresa, empresas=EMPRESAS_INSUMOS, desde=desde, hasta=hasta,
                           categoria=categoria, categorias_filtro=_categorias_insumos(), kpi=kpi, precios=precios, proveedores=proveedores,
                           top_compra=top_compra[:20], top_consumo_monto=top_consumo_monto, top_consumo_cant=top_consumo_cant,
                           mensual=mensual, hay_usd=hay_usd, meses=[f"{MESES_CORTOS_INSUMOS[mm - 1]} {str(yy)[2:]}" for yy, mm in meses],
                           alertas=alertas, sin_precio=sin_precio[:50], seccion='estadisticas')
