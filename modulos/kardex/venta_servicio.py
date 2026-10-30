# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# KARDEX · SALIDA A SERVICIO QUE SALE COMO VENTA  +  VÍNCULO CON LAS ÓRDENES DE SERVICIO (Compras)
# Cuando el material sale por un motivo que "inicia una OC" (REQUERIMIENTO DE MAESTRANZA, SERVICIO DE
# TRANSFORMACIÓN...), casi siempre ya no vuelve: el taller lo trabaja y se le entrega al cliente.
# Marcando "Sale como VENTA" (viene marcado por defecto):
#   - NO se abre el proceso por OC (no hay reingreso ni salida final);
#   - se guarda el taller que hace el servicio (el proveedor del movimiento), el CLIENTE al que se vende
#     y, si ya se tiene, el N° de OC del cliente (se puede poner o corregir después desde el Kardex);
#   - en el Kardex sale como VENTA y cuenta como venta en los dashboards de toneladas;
#   - se puede vincular con la Orden de Servicio del taller (módulo Compras), desde el movimiento o desde la OS
#     (una OS puede tener varios movimientos: el Kardex es producto por producto).
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================
ROLES_VENTA_SERVICIO = ['admin', 'almacen', 'logistica']        # registran / editan la venta en el Kardex
ESTADOS_OS_NO_VINCULABLES = ('ANULADA', 'RECHAZADA')
DIAS_CANDIDATOS_OS = 365                                         # movimientos que se ofrecen para vincular desde la OS


def _vs_norm_oc(valor):
    return ' '.join((valor or '').upper().split())[:50]


def _vs_digitos(valor):
    return ''.join(c for c in (valor or '') if c.isdigit())


def _vs_modelo(origen):
    return ProductMovementImportBolts if origen == 'IMPORTBOLTS' else ProductMovement


def _vs_os_valida(os_id):
    """(orden, None) si es una Orden de Servicio que se puede vincular; (None, mensaje) si no."""
    try:
        o = OrdenCompra.query.get(int(os_id))
    except (TypeError, ValueError):
        o = None
    if not o or o.tipo != 'OS':
        return None, '⛔ La orden de servicio elegida no existe. Vuelve a buscarla.'
    if o.estado in ESTADOS_OS_NO_VINCULABLES:
        return None, f'⛔ La {_oc_codigo(o)} está {ESTADOS_OC[o.estado]["txt"].lower()}: no se puede vincular.'
    return o, None


def _vs_preparar(f, tipo_kardex, etapa_motivo):
    """Valida la venta tras servicio ANTES de tocar el stock. Solo aplica a una SALIDA cuyo motivo inicia un proceso
    (Catálogos -> Motivos -> Proceso OC = Inicia) y que viene marcada 'venta_servicio'. Devuelve (datos | None, error | None)."""
    if not (tipo_kardex == 'SALIDA' and etapa_motivo == 'INICIO' and f.get('venta_servicio') == '1'):
        return None, None
    ruc = _vs_digitos(f.get('cliente_ruc'))
    razon = ' '.join((f.get('cliente_razon') or '').split()).upper()[:200]
    if len(ruc) not in (8, 11) or len(razon) < 3:
        return None, '⛔ Sale como venta: busca y elige el CLIENTE al que se le vende (RUC o DNI y razón social).'
    orden_os = None
    if (f.get('orden_servicio_id') or '').strip():
        orden_os, error = _vs_os_valida(f.get('orden_servicio_id'))
        if error:
            return None, error
    return {'cliente_ruc': ruc, 'cliente_razon': razon, 'oc_cliente': _vs_norm_oc(f.get('oc_cliente')) or None, 'os': orden_os}, None


def _vs_aplicar(mov, vs):
    mov.venta_servicio = True
    mov.cliente_ruc, mov.cliente_razon, mov.oc_cliente = vs['cliente_ruc'], vs['cliente_razon'], vs['oc_cliente']
    mov.orden_servicio_id = vs['os'].id if vs['os'] else None
    if vs['os']:
        _oc_evento(vs['os'], 'KARDEX_OS', f"Vinculada al Kardex al registrar la salida: {mov.product.sku if mov.product else ''} "
                                       f"-{mov.cantidad} · venta a {mov.cliente_razon}" + (f" (OC {mov.oc_cliente})" if mov.oc_cliente else ''))


def _vs_resumen(mov):
    return (f"Sale como VENTA a {mov.cliente_razon}" + (f" · OC del cliente {mov.oc_cliente}" if mov.oc_cliente else ' · sin OC del cliente (puedes ponerla después)')
            + (f" · vinculada a la {_oc_codigo(OrdenCompra.query.get(mov.orden_servicio_id))}" if mov.orden_servicio_id else ''))


def _vs_cond_motivo(cond, Modelo, texto):
    """Filtro de motivo por texto (links "ventas" de los Dashboards): las salidas a servicio marcadas como venta también son 'venta'."""
    t = _txt_sin_tildes(texto)
    if len(t) >= 3 and t in 'VENTA':
        return or_(cond, Modelo.venta_servicio.is_(True))
    return cond


def _vs_filtro_kardex(query, Modelo):
    """Filtros del Kardex: ?oc_cliente=<N° OC del cliente> · ?os=<id de la Orden de Servicio> · ?venta_srv=1 (solo estas ventas)."""
    a = request.args
    info = {}
    oc = _vs_norm_oc(a.get('oc_cliente'))
    if oc:
        query = query.filter(func.upper(Modelo.oc_cliente) == oc)
        info['oc_cliente'] = oc
    os_id = a.get('os', type=int)
    if os_id:
        query = query.filter(Modelo.orden_servicio_id == os_id)
        info['os'] = OrdenCompra.query.get(os_id)
        info['os_id'] = os_id
    if a.get('venta_srv') == '1':
        query = query.filter(Modelo.venta_servicio.is_(True))
        info['solo'] = True
    return query, (info or None)


def _vs_os_por_movimientos(movimientos):
    """{movimiento_id: OrdenCompra} de los movimientos de la página vinculados a una Orden de Servicio."""
    ids = {getattr(m, 'orden_servicio_id', None) for m in movimientos} - {None}
    if not ids:
        return {}
    try:
        ordenes = {o.id: o for o in OrdenCompra.query.filter(OrdenCompra.id.in_(list(ids))).all()}
    except Exception:
        db.session.rollback()
        return {}
    return {m.id: ordenes[m.orden_servicio_id] for m in movimientos if getattr(m, 'orden_servicio_id', None) in ordenes}


def _vs_mov_dict(origen, m, orden=None):
    p = m.product
    return {'clave': f'{origen}:{m.id}', 'origen': origen, 'origen_txt': 'Import Bolts' if origen == 'IMPORTBOLTS' else 'Anclajes',
            'id': m.id, 'fecha': m.fecha.strftime('%d/%m/%Y') if m.fecha else '', 'fecha_dt': m.fecha,
            'sku': p.sku if p else '', 'nombre': p.nombre if p else '', 'cantidad': m.cantidad, 'motivo': m.motivo or '',
            'taller': m.razon_social_proveedor or '', 'taller_ruc': m.ruc_proveedor or '',
            'cliente': m.cliente_razon or '', 'cliente_ruc': m.cliente_ruc or '', 'oc_cliente': m.oc_cliente or '',
            'peso': round((p.peso_kg or 0) * (m.cantidad or 0), 2) if p else 0,
            'os_id': m.orden_servicio_id, 'os_txt': _oc_codigo(orden) if orden else ''}


def _os_kardex(orden):
    """Movimientos del Kardex (de los dos inventarios) vinculados a esta Orden de Servicio."""
    if not orden or orden.tipo != 'OS':
        return []
    res = []
    try:
        for origen in ('ANCLAJES', 'IMPORTBOLTS'):
            for m in _vs_modelo(origen).query.filter_by(orden_servicio_id=orden.id).all():
                res.append(_vs_mov_dict(origen, m, orden))
    except Exception:
        db.session.rollback()
        return []
    res.sort(key=lambda x: (x['fecha_dt'] or datetime.min, x['id']))
    return res


app.add_template_global(_os_kardex, 'os_kardex')


def _vs_candidatos(orden=None, ruc=None, limite=60):
    """Salidas a servicio vendidas que todavía NO tienen Orden de Servicio (las del mismo taller primero)."""
    ruc = _vs_digitos(ruc if ruc is not None else (orden.ruc if orden else ''))
    desde = hora_peru() - timedelta(days=DIAS_CANDIDATOS_OS)
    res = []
    for origen in ('ANCLAJES', 'IMPORTBOLTS'):
        Modelo = _vs_modelo(origen)
        for m in (Modelo.query.filter(Modelo.venta_servicio.is_(True), Modelo.orden_servicio_id.is_(None), Modelo.fecha >= desde)
                  .order_by(Modelo.fecha.desc()).limit(300).all()):
            d = _vs_mov_dict(origen, m)
            d['mismo_taller'] = bool(ruc) and _vs_digitos(m.ruc_proveedor) == ruc
            res.append(d)
    res.sort(key=lambda x: (not x['mismo_taller'], -(x['fecha_dt'].timestamp() if x['fecha_dt'] else 0)))
    return res[:limite]


app.add_template_global(_vs_candidatos, 'os_kardex_candidatos')


def _vs_vincular(orden, claves):
    """Vincula a la OS los movimientos 'ORIGEN:id' (solo ventas tras servicio sin otra OS). Devuelve (vinculados, avisos)."""
    hechos, avisos = [], []
    for clave in claves:
        origen, _, mid = (clave or '').partition(':')
        if origen not in ('ANCLAJES', 'IMPORTBOLTS') or not mid.isdigit():
            continue
        m = _vs_modelo(origen).query.get(int(mid))
        if not m or not m.venta_servicio:
            avisos.append(f'el movimiento {mid} no es una salida a servicio vendida')
            continue
        if m.orden_servicio_id and m.orden_servicio_id != orden.id:
            otra = OrdenCompra.query.get(m.orden_servicio_id)
            avisos.append(f"{m.product.sku if m.product else mid} ya está en la {_oc_codigo(otra) if otra else 'otra OS'}")
            continue
        if m.orden_servicio_id == orden.id:
            continue
        m.orden_servicio_id = orden.id
        hechos.append(f"{m.product.sku if m.product else mid} -{m.cantidad}")
    if hechos:
        _oc_evento(orden, 'KARDEX_OS', f"Vinculó {len(hechos)} movimiento(s) del Kardex: {', '.join(hechos)}")
    return hechos, avisos


def _vs_vincular_desde_form(orden, f):
    """Al guardar una Orden de Servicio: los movimientos marcados en "Movimientos del Kardex ya registrados"."""
    claves = [c for c in f.getlist('kardex_mov[]') if c]
    if orden.tipo != 'OS' or not claves:
        return []
    hechos, _ = _vs_vincular(orden, claves)
    return hechos


# ---------------------------- RUTAS ----------------------------
@app.route('/kardex/api/os_buscar')
def vs_api_os_buscar():
    """Órdenes de Servicio para vincular a un movimiento (las del mismo taller primero)."""
    if session.get('role') not in ROLES_VENTA_SERVICIO:
        return {'status': 'error', 'msg': 'No autorizado', 'ordenes': []}, 403
    _asegurar_oc()
    q = ' '.join((request.args.get('q') or '').split()).upper()
    ruc = _vs_digitos(request.args.get('ruc'))
    ordenes = (OrdenCompra.query.filter(OrdenCompra.tipo == 'OS').order_by(OrdenCompra.fecha.desc(), OrdenCompra.id.desc()).limit(500).all())
    res = []
    for o in ordenes:
        if o.estado in ESTADOS_OS_NO_VINCULABLES:
            continue
        texto = (f"{_oc_codigo(o)} {o.numero} {_oc_numero_txt(o)} {o.razon_social or ''} {o.ruc or ''} {o.cliente_razon or ''} "
                 f"{' '.join(i.descripcion or '' for i in o.items)}").upper()
        if q and not all(t in texto for t in q.split()):
            continue
        mismo = bool(ruc) and _vs_digitos(o.ruc) == ruc
        res.append({'id': o.id, 'codigo': _oc_codigo(o), 'empresa': (o.empresa or 'ANCLAJES').title(), 'proveedor': o.razon_social or '',
                    'ruc': o.ruc or '', 'estado': ESTADOS_OC.get(o.estado, {}).get('txt', o.estado), 'fecha': o.fecha.strftime('%d/%m/%Y') if o.fecha else '',
                    'cliente': o.cliente_razon or '', 'detalle': ', '.join((i.descripcion or '')[:40] for i in o.items[:2]),
                    'mismo_taller': mismo, 'url': url_for('oc_detalle', orden_id=o.id)
                    if session.get('role') in ROLES_OC_VEN else ''})
    res.sort(key=lambda x: not x['mismo_taller'])
    return {'status': 'success', 'ordenes': res[:15]}


@app.route('/kardex/<origen>/movimiento/<int:mov_id>/venta_servicio', methods=['POST'])
def vs_editar_movimiento(origen, mov_id):
    """Corrige o completa después: N° de OC del cliente, cliente y Orden de Servicio de una venta tras servicio."""
    origen = 'IMPORTBOLTS' if origen.upper() == 'IMPORTBOLTS' else 'ANCLAJES'
    volver = request.form.get('volver') or url_for('ver_kardex_importbolts' if origen == 'IMPORTBOLTS' else 'ver_kardex')
    if not volver.startswith('/'):
        volver = url_for('ver_kardex')
    if session.get('role') not in ROLES_VENTA_SERVICIO:
        flash('⛔ No tienes permiso para editar este movimiento.')
        return redirect(volver)
    m = _vs_modelo(origen).query.get_or_404(mov_id)
    if not m.venta_servicio:
        flash('⛔ Solo se edita así una salida a servicio marcada como venta.')
        return redirect(volver)
    f = request.form
    ruc, razon = _vs_digitos(f.get('cliente_ruc')), ' '.join((f.get('cliente_razon') or '').split()).upper()[:200]
    if len(ruc) not in (8, 11) or len(razon) < 3:
        flash('⛔ El cliente necesita RUC (o DNI) y razón social.')
        return redirect(volver)
    orden_os = None
    if (f.get('orden_servicio_id') or '').strip():
        orden_os, error = _vs_os_valida(f.get('orden_servicio_id'))
        if error:
            flash(error)
            return redirect(volver)
    antes = (m.oc_cliente, m.cliente_ruc, m.orden_servicio_id)
    nuevo_oc = _vs_norm_oc(f.get('oc_cliente')) or None
    cambios = []
    if (m.oc_cliente or None) != nuevo_oc:
        cambios.append(f"OC del cliente: {m.oc_cliente or '—'} → {nuevo_oc or '—'}")
    if m.cliente_ruc != ruc or (m.cliente_razon or '') != razon:
        cambios.append(f"cliente: {m.cliente_razon or '—'} → {razon}")
    nuevo_os = orden_os.id if orden_os else None
    if m.orden_servicio_id != nuevo_os:
        anterior = OrdenCompra.query.get(m.orden_servicio_id) if m.orden_servicio_id else None
        cambios.append(f"OS: {_oc_codigo(anterior) if anterior else '—'} → {_oc_codigo(orden_os) if orden_os else '—'}")
        if anterior:
            _oc_evento(anterior, 'KARDEX_OS', f"Se quitó del Kardex: {m.product.sku if m.product else ''} -{m.cantidad} (por {session.get('nombre', '')})")
        if orden_os:
            _oc_evento(orden_os, 'KARDEX_OS', f"Vinculada desde el Kardex: {m.product.sku if m.product else ''} -{m.cantidad} · venta a {razon}")
    if not cambios:
        flash('No había nada que cambiar.')
        return redirect(volver)
    m.oc_cliente, m.cliente_ruc, m.cliente_razon, m.orden_servicio_id = nuevo_oc, ruc, razon, nuevo_os
    registrar_log(f"Editó la venta tras servicio del Kardex {origen.title()} ({m.product.sku if m.product else mov_id}): " + '; '.join(cambios),
                  'bi-pencil-square', 'text-primary')
    db.session.commit()
    flash('✅ Venta actualizada: ' + '; '.join(cambios) + '.')
    return redirect(volver)


@app.route('/ordenes/<int:orden_id>/kardex_vincular', methods=['POST'])
@_ruta_oc('editar')
def vs_os_vincular(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    destino = url_for('oc_detalle', orden_id=orden.id) + '#panelKardex'
    if orden.tipo != 'OS' or orden.estado in ESTADOS_OS_NO_VINCULABLES:
        flash('⛔ Solo se vinculan movimientos a una orden de servicio vigente.')
        return redirect(destino)
    hechos, avisos = _vs_vincular(orden, request.form.getlist('movs'))
    if not hechos and not avisos:
        flash('Elige al menos un movimiento del Kardex.')
        return redirect(destino)
    if hechos:
        registrar_log(f"Vinculó {len(hechos)} movimiento(s) del Kardex a la {_oc_codigo(orden)}", 'bi-link-45deg', 'text-primary')
    db.session.commit()
    flash((f"✅ {len(hechos)} movimiento(s) vinculados a la {_oc_codigo(orden)}." if hechos else '')
          + (f" ⚠️ No se vinculó: {'; '.join(avisos)}." if avisos else ''))
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/kardex_desvincular', methods=['POST'])
@_ruta_oc('editar')
def vs_os_desvincular(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    destino = url_for('oc_detalle', orden_id=orden.id) + '#panelKardex'
    origen, _, mid = (request.form.get('mov') or '').partition(':')
    m = _vs_modelo(origen).query.get(int(mid)) if origen in ('ANCLAJES', 'IMPORTBOLTS') and mid.isdigit() else None
    if not m or m.orden_servicio_id != orden.id:
        flash('⛔ Ese movimiento no está vinculado a esta orden.')
        return redirect(destino)
    m.orden_servicio_id = None
    _oc_evento(orden, 'KARDEX_OS', f"Quitó del Kardex: {m.product.sku if m.product else mid} -{m.cantidad}")
    registrar_log(f"Quitó un movimiento del Kardex de la {_oc_codigo(orden)}", 'bi-link-45deg', 'text-secondary')
    db.session.commit()
    flash('Movimiento quitado de la orden (el movimiento sigue en el Kardex).')
    return redirect(destino)


@app.route('/ordenes/api/kardex_candidatos')
@_ruta_oc('editar', como_json=True)
def vs_api_candidatos():
    """Para el formulario de una OS: ventas tras servicio del Kardex aún sin Orden de Servicio (mismo taller primero)."""
    orden = OrdenCompra.query.get(request.args.get('orden', type=int)) if request.args.get('orden', type=int) else None
    lista = _vs_candidatos(orden, request.args.get('ruc'))
    for d in lista:
        d.pop('fecha_dt', None)
    vinculados = _os_kardex(orden) if orden else []
    for d in vinculados:
        d.pop('fecha_dt', None)
    return {'status': 'success', 'movimientos': lista, 'vinculados': vinculados}
