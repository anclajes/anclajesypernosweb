# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · POSIBLES ÓRDENES DUPLICADAS (v27)
# Siempre del MISMO PROVEEDOR. Señales: misma factura (aunque se escriba distinto: FT01-2555 = FT01-00002555 = FAC-0002555),
# mismo monto, mismos productos y cercanía de fechas (solo se compara con las de los últimos DUP_VENTANA_DIAS días, salvo
# que coincida la factura). Puntaje -> nivel Alta / Media / Baja.
#   · En vivo al crear/editar (oc_duplicados_revisar) · para ENVIAR a Gerencia con nivel Alta hay que confirmar "no es duplicada"
#   · En el detalle (antes de aprobar) y en la lista (pestaña "Posibles duplicadas")
#   · "No es duplicada" descarta el par · "Anular por duplicada" (Gerencia y Logística) aunque esté conforme: si no se pagó ni ingresó nada
# Este archivo NO se importa: app.py lo carga (MODULOS_EN_ARCHIVOS), como si su código estuviera escrito ahí.
# =====================================================================================
import unicodedata

DUP_VENTANA_DIAS = 90
ROLES_ANULAN_DUPLICADA = ['admin', 'logistica']   # pueden "Anular por duplicada" (los mismos de editar órdenes)
DUP_ESTADOS_FUERA = ('ANULADA', 'RECHAZADA')      # no avisan ni se comparan (una rechazada no se compra; si la corrigen, vuelve a contar)
DUP_NIVELES = [(70, 'alta', 'Alta', '#dc2626'), (45, 'media', 'Media', '#ea580c'), (25, 'baja', 'Baja', '#64748b')]
DUP_PALABRAS_FUERA = {'DE', 'LA', 'EL', 'LOS', 'LAS', 'X', 'Y', 'CON', 'PARA', 'POR', 'EN', 'UN', 'UNA', 'DEL', 'AL', 'A'}


# ---------------------------- normalizar ----------------------------
def _dup_sin_tildes(t):
    return ''.join(c for c in unicodedata.normalize('NFD', str(t or '')) if unicodedata.category(c) != 'Mn').upper()


def _dup_factura(txt):
    """Factura -> (serie, número). La SERIE de SUNAT son 4 caracteres: letras + números (F001, FT01, E001, FA01...) o solo
    números en las físicas (001, 0001). La serie se compara COMPLETA (F001 ≠ E001 ≠ FT01) y sin ceros de relleno
    (F001-00003527 = F001-3527). Ejemplos:
      'Factura F001-00003527' -> (('F', 1), 3527) · 'E001-1736' -> (('E', 1), 1736) · 'FT01-00002555' -> (('FT', 1), 2555)
      'F0013527' (sin guion) -> (('F', 1), 3527) · '001-2555' -> (('', 1), 2555) · 'FAC-0002555' / '2555' -> (None, 2555)
    serie None = no se escribió. Devuelve None si no hay número."""
    t = _dup_sin_tildes(txt)
    t = re.sub(r'N\s*[°º]|\bNRO\b\.?|\bNUMERO\b|\bNUM\b\.?|\bNO\b\.|#|:', ' ', t)
    t = re.sub(r'\b(FACTURA|FACT|FAC|ELECTRONICA|ELECT)\b\.?', ' ', t)
    t = ' '.join(t.split())
    m = re.search(r'\b([A-Z]{1,3})\s*(\d{1,3})\s*[-–—/_. ]\s*(\d{1,10})\b', t)          # F001-3527 · FT01 00002555 · E001/1736
    if m and len(m.group(1)) + len(m.group(2)) <= 4:
        serie, num = (m.group(1), int(m.group(2))), int(m.group(3))
    else:
        m = re.search(r'\b(\d{3,4})\s*[-–—/_.]\s*(\d{1,10})\b', t)                         # física: 001-2555
        if m:
            serie, num = ('', int(m.group(1))), int(m.group(2))
        else:
            m = re.search(r'\b([A-Z]{1,3})(\d{2,})\b', t)                                   # pegado: F0013527 -> F001 + 3527
            if m and len(m.group(1)) < 4 and len(m.group(2)) > 4 - len(m.group(1)):
                corte = 4 - len(m.group(1))
                serie, num = (m.group(1), int(m.group(2)[:corte])), int(m.group(2)[corte:] or 0)
            else:
                grupos = re.findall(r'\d+', t)
                if not grupos:
                    return None
                serie, num = None, int(grupos[-1])
    return (serie, num) if num else None


def _dup_misma_factura(fa, fb):
    """2 = misma factura (misma serie completa y número) · 1 = mismo número y a una le falta la serie (o sus letras) · 0 = otra."""
    if not fa or not fb or fa[1] != fb[1]:
        return 0
    sa, sb = fa[0], fb[0]
    if sa is None or sb is None:
        return 1
    if sa == sb:
        return 2
    if sa[1] == sb[1] and (not sa[0] or not sb[0]):        # '001-2555' y 'F001-2555': falta la letra en una
        return 1
    return 0                                                # F001 ≠ E001 ≠ FT01: son facturas distintas


def _dup_txt_factura(fa, fb):
    return f"{fa} = {fb}" if fa and fb and fa.strip().upper() != fb.strip().upper() else (fa or fb or '')


def _dup_tokens(t):
    s = _dup_sin_tildes(t)
    s = re.sub(r'(\d)([A-Z])', r'\1 \2', s)
    s = re.sub(r'([A-Z])(\d)', r'\1 \2', s)
    s = re.sub(r'[^A-Z0-9]+', ' ', s)
    return {w for w in s.split() if w not in DUP_PALABRAS_FUERA}


def _dup_sim_items(A, B):
    """Qué parte de los productos coincide (0..1). A, B: [(codigo, descripcion)]."""
    if not A or not B:
        return 0.0, 0
    ta = [(re.sub(r'\W', '', _dup_sin_tildes(c)), _dup_tokens(d)) for c, d in A]
    tb = [(re.sub(r'\W', '', _dup_sin_tildes(c)), _dup_tokens(d)) for c, d in B]
    usados, iguales = set(), 0
    for ca, ka in ta:
        for j, (cb, kb) in enumerate(tb):
            if j in usados:
                continue
            jac = len(ka & kb) / len(ka | kb) if (ka or kb) else 0
            if (ca and cb and ca == cb) or jac >= 0.6:
                usados.add(j)
                iguales += 1
                break
    return iguales / max(len(ta), len(tb)), iguales


def _dup_prov(ruc, razon):
    r = re.sub(r'\D', '', ruc or '')
    return ('R', r) if len(r) >= 8 else (('N', ' '.join(_dup_tokens(razon))) if (razon or '').strip() else None)


def _dup_datos(o):
    """Lo que se compara de una orden guardada."""
    return {'id': o.id, 'empresa': o.empresa or 'ANCLAJES', 'prov': _dup_prov(o.ruc, o.razon_social), 'total': o.total or 0, 'moneda': o.moneda,
            'fecha': o.fecha or (o.fecha_registro.date() if getattr(o, 'fecha_registro', None) else hora_peru().date()),
            'factura': o.numero_factura or '', 'items': None, '_o': o, 'duplicada_de_id': o.duplicada_de_id,
            'descartes': {x.get('id') for x in _dup_descartes(o)}}


def _dup_items_de(d):
    if d['items'] is None:
        d['items'] = [(i.codigo or '', i.descripcion or '') for i in d['_o'].items]
    return d['items']


def _dup_descartes(o):
    try:
        return [x for x in json.loads(o.duplicado_descartes or '[]') if isinstance(x, dict)]
    except (ValueError, TypeError):
        return []


def _dup_nivel(pts):
    for minimo, k, txt, color in DUP_NIVELES:
        if pts >= minimo:
            return {'k': k, 'txt': txt, 'color': color}
    return None


def _dup_dinero(moneda, v):
    return f"{'US$' if moneda == 'USD' else 'S/'} {v:,.2f}"


def _dup_comparar(a, b):
    """(puntos, razones, dias) o None si no hay que compararlas."""
    if not a['prov'] or a['prov'] != b['prov'] or (a['id'] and a['id'] == b['id']):
        return None
    if (b['id'] in a['descartes']) or (a['id'] and a['id'] in b['descartes']):
        return None
    pts, razones, fact = 5, ['Mismo proveedor'], 0
    fa, fb = _dup_factura(a['factura']), _dup_factura(b['factura'])
    nivel_fact = _dup_misma_factura(fa, fb)
    if nivel_fact:
        if nivel_fact == 2:
            pts, fact = pts + 60, 2
            razones.append(f"Misma factura ({_dup_txt_factura(a['factura'], b['factura'])})")
        else:
            pts, fact = pts + 45, 1
            razones.append(f"Mismo N° de factura ({_dup_txt_factura(a['factura'], b['factura'])})")
    dias = abs((a['fecha'] - b['fecha']).days) if a['fecha'] and b['fecha'] else 0
    if dias > DUP_VENTANA_DIAS and not fact:
        return None
    ta, tb = round(a['total'] or 0, 2), round(b['total'] or 0, 2)
    if a['moneda'] == b['moneda'] and ta > 0 and tb > 0:
        dif = abs(ta - tb)
        if dif <= max(0.5, 0.002 * max(ta, tb)):
            pts += 35
            razones.append(f"Mismo monto ({_dup_dinero(a['moneda'], tb)})")
        elif dif / max(ta, tb) <= 0.03:
            pts += 15
            razones.append(f"Monto parecido ({_dup_dinero(a['moneda'], ta)} y {_dup_dinero(b['moneda'], tb)})")
    if pts >= 20 or dias <= 30:              # los productos solo se miran si ya hay alguna señal (o son de fechas cercanas)
        sim, iguales = _dup_sim_items(_dup_items_de(a), _dup_items_de(b))
        n = max(len(a['items'] or []), len(b['items'] or []))
        if sim >= 0.99:
            pts += 30
            razones.append(f"Mismos productos ({iguales} de {n})")
        elif sim >= 0.5:
            pts += 15
            razones.append(f"Productos parecidos ({iguales} de {n})")
    if a['empresa'] == b['empresa']:
        pts += 5
    else:
        razones.append(f"Otra empresa ({EMPRESAS_OC.get(b['empresa'], {}).get('corto', b['empresa'])})")
    if dias <= 7:
        pts += 15
        razones.append('Misma semana' if dias else 'Mismo día')
    elif dias <= 30:
        pts += 8
        razones.append(f'{dias} días de diferencia')
    elif dias > DUP_VENTANA_DIAS:
        pts -= 15
        razones.append(f'Hace {dias // 30} meses')
    if (a.get('duplicada_de_id') and a['duplicada_de_id'] == b['id']) or (a['id'] and b.get('duplicada_de_id') == a['id']):
        pts += 5
        razones.append("Se hizo con el botón 'Duplicar'")
    return pts, razones, dias


def _dup_json(b, pts, razones, dias, a_id=None):
    o = b['_o']
    est = ESTADOS_OC.get(o.estado, {})
    its = _dup_items_de(b)
    return {'id': o.id, 'codigo': _oc_codigo(o), 'url': url_for('oc_detalle', orden_id=o.id), 'comparar': (url_for('oc_duplicados_comparar', a=a_id, b=o.id) if a_id else None), 'empresa': EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', ''),
            'destino': DESTINOS_OC.get(o.destino, o.destino), 'estado': est.get('txt', o.estado), 'estado_color': est.get('color', '#64748b'),
            'fecha': o.fecha.strftime('%d/%m/%Y') if o.fecha else '', 'dias': dias, 'total': _dup_dinero(o.moneda, o.total or 0),
            'factura': o.numero_factura or '', 'proveedor': o.razon_social, 'solicito': _oc_solicitante_txt(o) or '',
            'creo': o.creado_por.nombre_completo if getattr(o, 'creado_por', None) else '',
            'pagada': (o.estado_pago or 'PENDIENTE') == 'PAGADO',
            'prods': [{'d': (i.descripcion or '')[:70], 'c': _cant_txt(i.cantidad), 'um': i.um or ''} for i in o.items[:6]], 'n_items': len(its),
            'puntos': pts, 'nivel': _dup_nivel(pts), 'razones': razones}


def _dup_buscar(a, minimo=25, limite=8):
    """Órdenes parecidas a `a` (dict como _dup_datos). Lista de dicts (_dup_json), la más probable primero."""
    if not a.get('prov'):
        return []
    try:
        q = OrdenCompra.query.filter(OrdenCompra.estado.notin_(DUP_ESTADOS_FUERA))
        if a['prov'][0] == 'R':
            q = q.filter(OrdenCompra.ruc.ilike(f"%{a['prov'][1]}%"))
        else:
            q = q.filter(func.upper(OrdenCompra.razon_social).like(f"%{a['prov'][1].split()[0]}%"))
        if a.get('id'):
            q = q.filter(OrdenCompra.id != a['id'])
        res = []
        for o in q.order_by(OrdenCompra.id.desc()).limit(400).all():
            b = _dup_datos(o)
            r = _dup_comparar(a, b)
            if r and r[0] >= minimo:
                res.append(_dup_json(b, *r, a_id=a.get('id')))
    except Exception:
        db.session.rollback()
        app.logger.exception('No se pudieron buscar órdenes duplicadas')
        return []
    res.sort(key=lambda x: (-x['puntos'], x['dias']))
    return res[:limite]


def _oc_duplicados(orden, minimo=45):
    """Para el detalle: las posibles duplicadas (alta/media) de una orden guardada."""
    if not orden or orden.estado in DUP_ESTADOS_FUERA:
        return []
    return _dup_buscar(_dup_datos(orden), minimo=minimo)


app.add_template_global(_oc_duplicados, 'oc_duplicados')
app.add_template_global(_dup_descartes, 'oc_dup_descartes')


def _dup_mapa(ordenes):
    """Para la lista: {orden_id: {'nivel', 'puntos', 'con': [{id, codigo, url, nivel, razones, estado, total, fecha}]}}
    solo Alta/Media (una pasada por proveedor; sin anuladas ni rechazadas)."""
    grupos = {}
    for o in ordenes:
        if o.estado in DUP_ESTADOS_FUERA:
            continue
        d = _dup_datos(o)
        if d['prov']:
            grupos.setdefault(d['prov'], []).append(d)
    mapa = {}
    for lista in grupos.values():
        if len(lista) < 2:
            continue
        lista.sort(key=lambda d: d['fecha'])
        for i, a in enumerate(lista):
            for b in lista[i + 1:]:
                r = _dup_comparar(a, b)
                if not r or r[0] < 45:
                    continue
                for x, y in ((a, b), (b, a)):
                    m = mapa.setdefault(x['id'], {'puntos': 0, 'con': []})
                    m['puntos'] = max(m['puntos'], r[0])
                    oy = y['_o']
                    m['con'].append({'id': oy.id, 'puntos': r[0], 'codigo': _oc_codigo(oy), 'url': url_for('oc_detalle', orden_id=oy.id), 'nivel': _dup_nivel(r[0]),
                                     'razones': r[1], 'estado': ESTADOS_OC.get(oy.estado, {}).get('txt', oy.estado),
                                     'total': _dup_dinero(oy.moneda, oy.total or 0), 'fecha': oy.fecha.strftime('%d/%m/%Y') if oy.fecha else '',
                                     'comparar': url_for('oc_duplicados_comparar', a=x['id'], b=oy.id)})
    for oid, m in mapa.items():
        m['nivel'] = _dup_nivel(m['puntos'])
        m['con'].sort(key=lambda c: -c['puntos'])
        m['comparar_todas'] = _dup_url_comparar([oid] + [c['id'] for c in m['con']]) if len(m['con']) > 1 else None
    return mapa


# ---------------------------- en vivo, desde el formulario ----------------------------
def _dup_desde_form(f, orden=None):
    """Datos del formulario (los totales los calcula el servidor, igual que al guardar)."""
    datos, items, _err = _leer_orden_form(f, orden)
    try:
        fecha = datos.get('fecha') if hasattr(datos.get('fecha'), 'year') else hora_peru().date()
    except Exception:
        fecha = hora_peru().date()
    return {'id': orden.id if orden else None, 'empresa': datos.get('empresa') or 'ANCLAJES', 'prov': _dup_prov(datos.get('ruc'), datos.get('razon_social')),
            'total': datos.get('total') or 0, 'moneda': datos.get('moneda') or 'PEN', 'fecha': fecha or hora_peru().date(),
            'factura': (orden.numero_factura if orden else '') or '', 'items': [(i.get('codigo') or '', i.get('descripcion') or '') for i in items],
            '_o': orden, 'duplicada_de_id': f.get('duplicada_de', type=int), 'descartes': {x.get('id') for x in _dup_descartes(orden)} if orden else set()}


@app.route('/ordenes/duplicados/revisar', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_duplicados_revisar():
    f = request.form
    orden = OrdenCompra.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    try:
        a = _dup_desde_form(f, orden)
    except Exception:
        db.session.rollback()
        return {'status': 'success', 'lista': []}
    lista = _dup_buscar(a)
    return {'status': 'success', 'lista': lista, 'alta': [x['id'] for x in lista if x['nivel'] and x['nivel']['k'] == 'alta']}


def _dup_control_envio(f, orden, datos, items):
    """Al ENVIAR a Gerencia: si hay una posible duplicada ALTA, hay que confirmar que no lo es (con motivo).
    Devuelve (error, confirmacion): error = texto para el usuario; confirmacion = dict para el historial."""
    a = _dup_desde_form(f, orden)
    altas = [x for x in _dup_buscar(a) if x['nivel'] and x['nivel']['k'] == 'alta']
    if not altas:
        return None, None
    motivo = ' '.join((f.get('dup_motivo') or '').split())[:300]
    if f.get('dup_revisado') != '1' or len(motivo) < 10:
        cods = ', '.join(x['codigo'] for x in altas[:3])
        return (f"Posible ORDEN DUPLICADA (coincidencia alta con {cods}). Revísala y, si NO es duplicada, marca "
                f"\"Revisé: no es duplicada\" y escribe por qué (mínimo 10 letras)."), None
    return None, {'ids': [x['id'] for x in altas], 'codigos': [x['codigo'] for x in altas], 'motivo': motivo,
                  'por': session.get('nombre', ''), 'fecha': hora_peru().strftime('%d/%m/%Y %H:%M')}


def _dup_registrar_confirmacion(orden, conf):
    """Guarda en la orden y en su historial que se revisó y NO es duplicada (lo ve Gerencia al aprobar)."""
    orden.duplicado_revision = json.dumps(conf, ensure_ascii=False)[:2000]
    _oc_evento(orden, 'DUPLICADO_REVISADO', f"Se revisó: NO es duplicada de {', '.join(conf['codigos'])} · {conf['motivo']}"[:500])


app.add_template_global(lambda o: (json.loads(o.duplicado_revision) if getattr(o, 'duplicado_revision', None) else None), 'oc_dup_revision')


# ---------------------------- descartar / anular por duplicada ----------------------------
@app.route('/ordenes/<int:orden_id>/duplicado/descartar', methods=['POST'])
@_ruta_oc('editar')
def oc_duplicado_descartar(orden_id):
    """'No es duplicada': deja de avisar ese par (en las dos órdenes). Queda en el historial."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    otra = OrdenCompra.query.get_or_404(request.form.get('otra_id', type=int) or 0)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    volver = _volver_seguro(request.form.get('volver'), url_for('oc_detalle', orden_id=orden.id))
    if len(motivo) < 5:
        flash('⛔ Escribe por qué no es duplicada (mínimo 5 letras).')
        return redirect(volver)
    ahora = hora_peru().strftime('%d/%m/%Y %H:%M')
    for x, y in ((orden, otra), (otra, orden)):
        lista = [d for d in _dup_descartes(x) if d.get('id') != y.id]
        lista.append({'id': y.id, 'por': session.get('nombre', ''), 'fecha': ahora, 'motivo': motivo})
        x.duplicado_descartes = json.dumps(lista[-40:], ensure_ascii=False)
        _oc_evento(x, 'DUPLICADO_REVISADO', f"NO es duplicada de {_oc_codigo(y)}: {motivo}"[:500])
    db.session.commit()
    flash(f'✅ Listo: {_oc_codigo(orden)} y {_oc_codigo(otra)} ya no se marcan como posibles duplicadas.')
    return redirect(volver)


def _dup_bloqueos_lista(orden):
    """v27.6: TODAS las razones por las que no se puede anular por duplicada, cada una con qué hacer y a dónde ir.
    [] = sí se puede. Cada una: {'ico', 'titulo', 'txt' (frase corta para mensajes), 'hacer', 'url', 'url_txt'}."""
    if orden.estado == 'ANULADA':
        return [{'ico': '🚫', 'titulo': 'Ya está anulada', 'txt': 'ya está anulada', 'hacer': '', 'url': None, 'url_txt': ''}]
    r, url_oc = [], url_for('oc_detalle', orden_id=orden.id)
    if (orden.estado_pago or 'PENDIENTE') == 'PAGADO':
        r.append({'ico': '💰', 'titulo': 'Ya está pagada', 'txt': 'ya está pagada: primero deshaz el pago (o gestiona la devolución / nota de crédito con el proveedor)',
                  'hacer': 'Si el pago se registró por error, Administración/Gerencia lo deshace en la orden. Si de verdad se pagó dos veces, '
                           'hay que pedir la devolución o una nota de crédito al proveedor.', 'url': url_oc, 'url_txt': 'Ver el pago en la orden'})
    if orden.insumo_ingreso_id:
        r.append({'ico': '📦', 'titulo': f'Ya se sumó al inventario de Insumos (ingreso #{orden.insumo_ingreso_id})',
                  'txt': 'ya se ingresó a Insumos internos: primero anula ese ingreso',
                  'hacer': 'Esos productos ya están en el stock de Insumos. Gerencia debe anular primero ese ingreso '
                           '(solo se puede si no se sacó nada de él).',
                  'url': url_for('insumos_ingreso_detalle', ingreso_id=orden.insumo_ingreso_id), 'url_txt': f'Ver ingreso #{orden.insumo_ingreso_id}'})
    if any(i.fecha_ingreso for i in orden.items) or any(ei.fecha_ingreso for e in _oc_entregas(orden) for ei in e.items):
        r.append({'ico': '🏭', 'titulo': 'Almacén ya la ingresó al Kardex', 'txt': 'Almacén ya ingresó productos de esta orden al Kardex: primero revierte ese ingreso',
                  'hacer': 'Esos productos ya suman en el inventario (Kardex). Primero hay que revertir ese ingreso.',
                  'url': url_oc, 'url_txt': 'Ver las entregas en la orden'})
    return r


def _dup_bloqueo_anular(orden):
    """Por qué NO se puede anular por duplicada, en una frase (None = sí se puede). Detalle completo: _dup_bloqueos_lista."""
    r = _dup_bloqueos_lista(orden)
    if not r:
        return None
    return r[0]['txt'] if len(r) == 1 else '; '.join(x['txt'].split(':')[0] for x in r) + ' (resuelve cada punto primero)'


app.add_template_global(_dup_bloqueo_anular, 'oc_dup_bloqueo_anular')
app.add_template_global(_dup_bloqueos_lista, 'oc_dup_bloqueos')
app.add_template_global(ROLES_ANULAN_DUPLICADA, 'roles_anulan_duplicada')


def _dup_opciones_original(orden):
    """Órdenes de las que podría ser duplicada: las parecidas primero; luego las del mismo proveedor (180 días)."""
    parecidas = _dup_buscar(_dup_datos(orden), minimo=0, limite=15)
    vistos = {x['id'] for x in parecidas}
    desde = (orden.fecha or hora_peru().date()) - timedelta(days=180)
    q = OrdenCompra.query.filter(OrdenCompra.estado.notin_(DUP_ESTADOS_FUERA), OrdenCompra.id != orden.id, OrdenCompra.fecha >= desde)
    prov = _dup_prov(orden.ruc, orden.razon_social)
    if prov and prov[0] == 'R':
        q = q.filter(OrdenCompra.ruc.ilike(f'%{prov[1]}%'))
    else:
        q = q.filter(OrdenCompra.razon_social == orden.razon_social)
    otras = [{'id': o.id, 'codigo': _oc_codigo(o), 'fecha': o.fecha.strftime('%d/%m/%Y') if o.fecha else '', 'total': _dup_dinero(o.moneda, o.total or 0),
              'estado': ESTADOS_OC.get(o.estado, {}).get('txt', o.estado), 'nivel': None, 'razones': []}
             for o in q.order_by(OrdenCompra.fecha.desc()).limit(30).all() if o.id not in vistos]
    return [x for x in parecidas] + otras


app.add_template_global(_dup_opciones_original, 'oc_dup_opciones')


@app.route('/ordenes/<int:orden_id>/anular_duplicada', methods=['POST'])
@_ruta_oc('editar')
def oc_anular_duplicada(orden_id):
    """GERENCIA o LOGÍSTICA (ROLES_ANULAN_DUPLICADA): anula una orden que es DUPLICADA de otra, aunque ya esté aprobada o conforme (si no se pagó ni ingresó nada).
    Su número no se vuelve a usar; queda en el historial de las dos órdenes y sale del 'Por pagar'."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    volver = url_for('oc_detalle', orden_id=orden.id)
    if session.get('role') not in ROLES_ANULAN_DUPLICADA:
        flash('⛔ Solo Gerencia o Logística anulan por duplicada.')
        return redirect(volver)
    bloqueo = _dup_bloqueo_anular(orden)
    if bloqueo:
        flash(f'⛔ No se puede anular: {bloqueo}.')
        return redirect(volver)
    original = OrdenCompra.query.get(request.form.get('original_id', type=int) or 0)
    detalle = ' '.join((request.form.get('motivo') or '').split())[:250]
    if not original or original.id == orden.id or original.estado in DUP_ESTADOS_FUERA:
        flash('⛔ Elige la orden ORIGINAL (la que se queda vigente).')
        return redirect(volver)
    if len(detalle) < 5:
        flash('⛔ Escribe el motivo (mínimo 5 letras).')
        return redirect(volver)
    _dup_anular(orden, original, detalle)
    db.session.commit()
    flash(f'{_oc_codigo(orden)} anulada por duplicada de {_oc_codigo(original)}. Ya no aparece por pagar y su número no se vuelve a usar.')
    return redirect(volver)


def _dup_anular(orden, original, detalle):
    """Anula `orden` por duplicada de `original` (sin commit). Ya se revisó _dup_bloqueo_anular y el rol."""
    estado_antes = orden.estado
    extra = []
    if orden.destino == 'DIRECTO' and orden.fecha_kardex:
        extra.append('tenía registrada la entrega de uso directo (no movió inventario)')
    if orden.es_contable and orden.fecha_kardex:
        extra.append('estaba confirmada como tema contable (no movió inventario)')
    if orden.tipo == 'OS' and orden.fecha_kardex:
        extra.append('tenía marcado el seguimiento del servicio')
    orden.estado, orden.anulado_por_id, orden.fecha_anulacion = 'ANULADA', session.get('user_id'), hora_peru()
    orden.anulacion_categoria, orden.anulacion_opcion = 'DUPLICADA', f'Orden duplicada de {_oc_codigo(original)}'[:150]
    orden.motivo_anulacion = detalle
    orden.anulada_duplicada_de_id = original.id
    _oc_evento(orden, 'ANULADA', f"ANULADA POR DUPLICADA de {_oc_codigo(original)}: {detalle} (estaba: {ESTADOS_OC.get(estado_antes, {}).get('txt', estado_antes)}"
                                 + (f"; {'; '.join(extra)}" if extra else '') + ')')
    _oc_evento(original, 'DUPLICADO', f"Se anuló la {_oc_codigo(orden)} por ser DUPLICADA de esta orden: {detalle}"[:500])
    registrar_log(f"ANULÓ POR DUPLICADA la {_oc_codigo(orden)} (original {_oc_codigo(original)}): {detalle}"[:255], 'bi-files', 'text-danger')


@app.route('/ordenes/duplicados/anular_varias', methods=['POST'])
@_ruta_oc('editar')
def oc_anular_duplicadas_varias():
    """Desde 'Comparar': se elige la orden CORRECTA y se anulan de una vez las marcadas (todas o ninguna)."""
    f = request.form
    volver = _volver_seguro(f.get('volver'), url_for('oc_lista'))
    if session.get('role') not in ROLES_ANULAN_DUPLICADA:
        flash('⛔ Solo Gerencia o Logística anulan por duplicada.')
        return redirect(volver)
    original = OrdenCompra.query.get(f.get('original_id', type=int) or 0)
    ids = [int(x) for x in f.getlist('anular_ids') if str(x).isdigit()]
    detalle = ' '.join((f.get('motivo') or '').split())[:250]
    if not original or original.estado in DUP_ESTADOS_FUERA:
        flash('⛔ Elige la orden CORRECTA (la que se queda vigente).')
        return redirect(volver)
    ids = [i for i in dict.fromkeys(ids) if i != original.id]
    if not ids:
        flash('⛔ Marca al menos una orden para anular (no la correcta).')
        return redirect(volver)
    if len(detalle) < 5:
        flash('⛔ Escribe el motivo (mínimo 5 letras).')
        return redirect(volver)
    ordenes, errores = [], []
    for i in ids:
        o = OrdenCompra.query.get(i)
        bl = _dup_bloqueo_anular(o) if o else 'no existe'
        if bl:
            errores.append(f"{_oc_codigo(o) if o else i}: {bl}")
        else:
            ordenes.append(o)
    if errores:
        flash('⛔ No se anuló ninguna. ' + ' · '.join(errores))
        return redirect(volver)
    for o in ordenes:
        _dup_anular(o, original, detalle)
    db.session.commit()
    flash(f"{len(ordenes)} orden(es) anulada(s) por duplicadas de {_oc_codigo(original)}: {', '.join(_oc_codigo(o) for o in ordenes)}. "
          "Ya no aparecen por pagar y sus números no se vuelven a usar.")
    return redirect(url_for('oc_detalle', orden_id=original.id))


# ---------------------------- mapeo y comparar lado a lado ----------------------------
def _dup_anuladas_de(orden):
    """Las órdenes que se anularon por ser DUPLICADAS de esta (para el detalle de la original)."""
    try:
        return OrdenCompra.query.filter(OrdenCompra.anulada_duplicada_de_id == orden.id).order_by(OrdenCompra.id).all()
    except Exception:
        db.session.rollback()
        return []


app.add_template_global(_dup_anuladas_de, 'oc_dup_anuladas_de')


DUP_COMPARAR_MAX = 6


def _dup_url_comparar(ids):
    ids = [i for i in dict.fromkeys(ids) if i][:DUP_COMPARAR_MAX]
    return url_for('oc_duplicados_comparar', ids=','.join(str(i) for i in ids))


app.add_template_global(_dup_url_comparar, 'oc_dup_url_comparar')


def _dup_claves(o):
    """Lo que se pinta de verde si coincide con la orden CORRECTA elegida (texto normalizado)."""
    fa = _dup_factura(o.numero_factura)
    return {'proveedor': '|'.join(_dup_prov(o.ruc, o.razon_social) or ('', '')), 'empresa': o.empresa or 'ANCLAJES',
            'destino': f"{o.tipo}|{o.destino}", 'total': f"{o.moneda}|{round(o.total or 0, 1)}",
            'factura': (f"{fa[0][0] if fa[0] else ''}{fa[0][1] if fa[0] else ''}|{fa[1]}" if fa and fa[0] else ''), 'factura_num': str(fa[1]) if fa else '',
            'fecha': o.fecha.isoformat() if o.fecha else ''}


@app.route('/ordenes/duplicados/comparar')
@_ruta_oc()
def oc_duplicados_comparar():
    """Hasta DUP_COMPARAR_MAX órdenes lado a lado (?ids=23,19,30, o ?a=&b=). Se elige la CORRECTA y lo que coincide con ella
    sale en verde; se pueden anular varias de una vez o marcar 'No es duplicada'."""
    ids = [int(x) for x in (request.args.get('ids') or '').split(',') if x.strip().isdigit()]
    ids += [x for x in (request.args.get('a', type=int), request.args.get('b', type=int)) if x]
    ids = list(dict.fromkeys(ids))[:DUP_COMPARAR_MAX]
    ords = [o for o in (OrdenCompra.query.get(i) for i in ids) if o]
    if len(ords) < 2:
        flash('Elige al menos dos órdenes para comparar.')
        return redirect(url_for('oc_lista'))
    datos = {o.id: _dup_datos(o) for o in ords}
    for d in datos.values():
        d['descartes'] = set()                      # comparar igual aunque el par esté descartado
    pares = {}
    for x in ords:
        for y in ords:
            if x.id != y.id:
                r = _dup_comparar(datos[x.id], datos[y.id])
                pares[f"{x.id}-{y.id}"] = {'nivel': _dup_nivel(r[0]) if r else None, 'razones': r[1] if r else [], 'dias': r[2] if r else None}
    # productos: una fila por producto; en cada columna el de esa orden (mismo código o descripción parecida)
    filas = []                                      # [{'tok': set, 'cod': str, 'items': {orden_id: item}}]
    for o in ords:
        for it in o.items:
            tok, cod = _dup_tokens(it.descripcion), (it.codigo or '').strip().upper()
            fila = None
            for fl in filas:
                if o.id in fl['items']:
                    continue
                jac = len(tok & fl['tok']) / len(tok | fl['tok']) if (tok or fl['tok']) else 0
                if (cod and cod in fl['cods']) or jac >= 0.6:
                    fila = fl
                    break
            if not fila:
                fila = {'tok': tok, 'cods': set(), 'items': {}}
                filas.append(fila)
            fila['items'][o.id] = it
            if cod:
                fila['cods'].add(cod)
    bloqueos_det = {o.id: _dup_bloqueos_lista(o) for o in ords}
    vigentes = [o for o in ords if o.estado not in DUP_ESTADOS_FUERA]
    # la correcta propuesta: la vigente que YA NO se puede anular (pagada / ingresada: esa es la que se queda); si no, la primera vigente
    ref = next((o for o in vigentes if bloqueos_det[o.id]), vigentes[0] if vigentes else ords[0])
    descartes = {o.id: [d.get('id') for d in _dup_descartes(o)] for o in ords}
    return render_template('oc_dup_comparar.html', ords=ords, ref=ref, pares=pares, filas=filas, claves={o.id: _dup_claves(o) for o in ords},
                           bloqueos={o.id: _dup_bloqueo_anular(o) for o in ords}, bloqueos_det=bloqueos_det, descartes=descartes, fuera=DUP_ESTADOS_FUERA,
                           estados=ESTADOS_OC, destinos=DESTINOS_OC, empresas_oc=EMPRESAS_OC, seccion='lista')
