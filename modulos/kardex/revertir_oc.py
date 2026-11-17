# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v28 · REVERTIR EL INGRESO AL KARDEX DE UNA ORDEN DE COMPRA (con doble control)
# Caso: una OC se digitó mal (ej. 6 MT en vez de 1 UN), Almacén la ingresó y sumó 6; o se creó DOS veces la misma compra y
# las dos se ingresaron (stock de más). El movimiento vino de una OC, así que "Eliminar movimiento" del Kardex no lo deja.
#   1) El Jefe de Almacén (o Gerencia) SOLICITA desde la orden: elige los ítems, el motivo y qué hacer con la orden:
#        · CORREGIR  -> la orden vuelve a Logística (DEVUELTA) para que la editen y Almacén la ingrese bien;
#        · DUPLICADA -> la orden se ANULA por duplicada de la correcta (que se elige: queda el mapeo).
#      No cambia nada todavía (solo se bloquea ingresar más de esa orden). Le llega el aviso a Logística.
#   2) LOGÍSTICA CONFIRMA (todo o nada): se eliminan del Kardex los movimientos de esos ítems con su copia en
#      "Movimientos eliminados" (con la OC y la reversión), se descuenta el stock, se corrigen los saldos posteriores,
#      se quita la marca de ingresado y se devuelve o se anula la orden. O la RECHAZA con un motivo.
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS), después de kardex/eliminar.py. Ver MAPA.md.
# =====================================================================================

ROLES_SOLICITAN_REVERSION = ['admin', 'almacen']      # Jefe de Almacén (y Gerencia)
ROLES_CONFIRMAN_REVERSION = ['logistica']             # por ahora solo Logística (son errores al crear la OC)
MODOS_REVERSION = {
    'CORREGIR': {'txt': 'Corregir la orden', 'ico': 'bi-pencil-square',
                 'ayuda': 'Se ingresó una cantidad o unidad equivocada: se revierte y la orden vuelve a Logística para que la editen; luego Almacén la ingresa bien.'},
    'DUPLICADA': {'txt': 'Anular por duplicada', 'ico': 'bi-files',
                  'ayuda': 'La misma compra se registró dos veces: se revierte y esta orden se ANULA por duplicada de la correcta (que eliges).'},
}
ESTADOS_REVERSION = {'PENDIENTE': {'txt': 'Esperando que Logística confirme', 'color': '#d97706'},
                     'CONFIRMADA': {'txt': 'Revertida', 'color': '#16a34a'},
                     'RECHAZADA': {'txt': 'Rechazada por Logística', 'color': '#dc2626'},
                     'CANCELADA': {'txt': 'Cancelada', 'color': '#64748b'}}

try:
    with app.app_context():
        OCReversionKardex.__table__.create(bind=db.engine, checkfirst=True)
        _agregar_columnas_si_faltan('movimiento_eliminado', [('orden_compra_id', 'INTEGER'), ('reversion_id', 'INTEGER')])
except Exception as _e_rev:
    print(f"Aviso: no se pudo preparar la reversión de ingresos de OC: {_e_rev}")


def _rev_items_json(rev):
    try:
        return json.loads(rev.items) if rev and rev.items else []
    except (TypeError, ValueError):
        return []


def _rev_mapa():
    """{orden_id: última reversión PENDIENTE o CONFIRMADA} (una consulta por pedido: la tabla es chica)."""
    if 'rev_mapa' not in g:
        m = {}
        try:
            for r in OCReversionKardex.query.filter(OCReversionKardex.estado.in_(['PENDIENTE', 'CONFIRMADA'])).order_by(OCReversionKardex.id).all():
                m[r.orden_id] = r
        except Exception:
            db.session.rollback()
        g.rev_mapa = m
    return g.rev_mapa


def _rev_pendiente(orden):
    r = _rev_mapa().get(orden.id) if orden is not None else None
    return r if r is not None and r.estado == 'PENDIENTE' else None


def _rev_de_orden(orden):
    """Todas las reversiones de la orden (la más reciente primero), para el detalle."""
    try:
        return OCReversionKardex.query.filter_by(orden_id=orden.id).order_by(OCReversionKardex.id.desc()).all()
    except Exception:
        db.session.rollback()
        return []


def _rev_ingresados(orden):
    """Ítems de la orden que ya entraron al Kardex: lo que se revertiría de cada uno (cantidad, SKU, movimientos y stock hoy)."""
    if orden.tipo != 'OC' or orden.destino != 'GENERAL' or orden.es_contable:
        return []
    cache = g.setdefault('rev_ingresados', {})
    if orden.id in cache:
        return cache[orden.id]
    Modelo, Movimiento, origen = _modelos_inv_orden(orden)
    items = {i.id: i for i in orden.items}
    por_item = {}
    for e in _oc_entregas(orden):
        for ei in e.items:
            if ei.fecha_ingreso and ei.item_id in items:
                por_item.setdefault(ei.item_id, []).append((e, ei))
    filas = []
    for iid, lista in por_item.items():
        it = items[iid]
        movs, cant, sku, manual = [], 0, None, False
        for e, ei in lista:
            mov = Movimiento.query.get(ei.kardex_mov_id) if ei.kardex_mov_id else None
            if mov is not None and mov.orden_compra_id == orden.id and mov.tipo == 'ENTRADA':
                movs.append(mov.id)
                cant += mov.cantidad or 0
                sku = sku or (mov.product.sku if mov.product else ei.sku_ingreso)
            else:
                manual = True          # marcado a mano, o el movimiento ya no está en el Kardex: solo se quita la marca
                sku = sku or ei.sku_ingreso
        prod = (Modelo.query.filter(func.upper(Modelo.sku) == (sku or '').upper()).first() if sku else None)
        stock = int(prod.stock_actual or 0) if prod else None
        filas.append({'item_id': it.id, 'item': it.item, 'descripcion': it.descripcion or '', 'um': it.um or '', 'cantidad_oc': it.cantidad,
                      'sku': sku or '', 'producto': prod.nombre if prod else '', 'cantidad': cant, 'movs': movs, 'manual': manual,
                      'entregas': [e.numero for e, _ in lista], 'stock_antes': stock,
                      'stock_despues': (stock - cant) if stock is not None else None, 'falta_stock': stock is not None and stock - cant < 0})
    cache[orden.id] = sorted(filas, key=lambda x: x['item'])
    return cache[orden.id]


def _rev_puede_solicitar(orden):
    """None si el usuario actual puede pedir la reversión de esta orden; si no, el motivo."""
    if session.get('role') not in ROLES_SOLICITAN_REVERSION:
        return 'solo el Jefe de Almacén o Gerencia la piden'
    if orden.estado not in ('APROBADA', 'RECIBIDA', 'CONFORME'):
        return 'la orden no está aprobada / conforme'
    if _rev_pendiente(orden):
        return 'ya hay una reversión esperando que Logística la confirme'
    if orden.devuelta_almacen:
        return 'la orden está devuelta a Logística'
    if not _rev_ingresados(orden):
        return 'no tiene nada ingresado al Kardex'
    return None


for _n, _f in (('oc_rev_pendiente', _rev_pendiente), ('oc_rev_de_orden', _rev_de_orden), ('oc_rev_ingresados', _rev_ingresados),
               ('oc_rev_puede_solicitar', _rev_puede_solicitar), ('oc_rev_items', _rev_items_json), ('oc_rev_mapa', _rev_mapa)):
    app.add_template_global(_f, _n)
app.add_template_global(MODOS_REVERSION, 'modos_reversion')
app.add_template_global(ESTADOS_REVERSION, 'estados_reversion')
app.add_template_global(ROLES_CONFIRMAN_REVERSION, 'roles_confirman_reversion')
app.add_template_global(ROLES_SOLICITAN_REVERSION, 'roles_solicitan_reversion')


def _rev_volver(orden):
    """A dónde volver: lo que mandó el formulario; si no, el detalle (quien ve órdenes) o Ingresos pendientes (Almacén)."""
    defecto = (url_for('oc_detalle', orden_id=orden.id) + '#reversion' if session.get('role') in ROLES_OC_VEN
               else url_for('oc_ingresos_pendientes', vista='hechos') + f'#oc{orden.id}')
    return _volver_seguro(request.form.get('volver'), defecto)


def _rev_resumen(items):
    return ', '.join(f"#{x['item']} −{x['cantidad']} {x['sku'] or ''}".strip() for x in items) or '-'


@app.route('/ordenes/<int:orden_id>/reversion/solicitar', methods=['POST'])
@_ruta_oc('ingresar')
def oc_reversion_solicitar(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    f = request.form
    volver = _rev_volver(orden)
    no = _rev_puede_solicitar(orden)
    if no:
        flash(f'⛔ No se puede pedir la reversión: {no}.')
        return redirect(volver)
    modo = f.get('modo')
    motivo = ' '.join((f.get('motivo') or '').split())[:500]
    if modo not in MODOS_REVERSION:
        flash('⛔ Elige qué hacer con la orden: corregirla o anularla por duplicada.')
        return redirect(volver)
    if len(motivo) < 10:
        flash('⛔ Explica qué pasó (mínimo 10 letras): lo lee Logística y queda en la auditoría del Kardex.')
        return redirect(volver)
    disponibles = {x['item_id']: x for x in _rev_ingresados(orden)}
    if modo == 'DUPLICADA':
        elegidos = list(disponibles.values())          # una duplicada se revierte entera
        try:
            original = OrdenCompra.query.get(int(f.get('original_id') or 0))
        except ValueError:
            original = None
        if not original or original.id == orden.id or original.estado in DUP_ESTADOS_FUERA:
            flash('⛔ Elige cuál es la orden CORRECTA (la que se queda): no puede ser esta misma, ni una anulada o rechazada.')
            return redirect(volver)
    else:
        ids = {int(x) for x in f.getlist('item_id') if (x or '').isdigit()}
        elegidos = [x for iid, x in disponibles.items() if iid in ids]
        original = None
        if not elegidos:
            flash('⛔ Marca al menos un ítem a revertir.')
            return redirect(volver)
    sin_stock = [x for x in elegidos if x['falta_stock']]
    if sin_stock:
        flash('⛔ No alcanza el stock para revertir: ' + '; '.join(f"{x['sku']} hay {x['stock_antes']} y habría que descontar {x['cantidad']}" for x in sin_stock)
              + '. Primero corrige las salidas que se hicieron con ese stock.')
        return redirect(volver)
    rev = OCReversionKardex(orden_id=orden.id, empresa=orden.empresa or 'ANCLAJES', modo=modo, original_id=original.id if original else None,
                            motivo=motivo, items=json.dumps(elegidos, ensure_ascii=False, default=str), estado='PENDIENTE',
                            solicitado_por_id=session.get('user_id'), fecha_solicitud=hora_peru())
    db.session.add(rev)
    db.session.flush()
    que = MODOS_REVERSION[modo]['txt'] + (f" de {_oc_codigo(original)}" if original else '')
    _oc_evento(orden, 'REVERSION_PEDIDA', f"{session.get('nombre', '')} pidió revertir el ingreso al Kardex ({_rev_resumen(elegidos)}) y {que.lower()}: {motivo}")
    corto = EMPRESAS_OC.get(orden.empresa or 'ANCLAJES', {}).get('corto', '')
    _notif_crear('OC_REVERSION', f"Confirmar reversión de ingreso · {_oc_codigo(orden)} · {corto}", f"{que} · {_rev_resumen(elegidos)} · {motivo}",
                 volver, orden=orden, excluir=session.get('user_id'))
    registrar_log(f"Pidió revertir el ingreso al Kardex de la {_oc_codigo(orden)} ({_rev_resumen(elegidos)}; {que}): {motivo[:120]}", 'bi-arrow-counterclockwise', 'text-warning')
    db.session.commit()
    flash(f'↩ Reversión pedida para {_oc_codigo(orden)}. Todavía NO cambió el stock: Logística debe confirmarla. Mientras tanto no se ingresa nada más de esta orden.')
    return redirect(volver)


def _rev_cargar(rev_id):
    rev = OCReversionKardex.query.get_or_404(rev_id)
    orden = OrdenCompra.query.get_or_404(rev.orden_id)
    return rev, orden, _rev_volver(orden)


@app.route('/ordenes/reversion/<int:rev_id>/confirmar', methods=['POST'])
@_ruta_oc('ver')
def oc_reversion_confirmar(rev_id):
    rev, orden, volver = _rev_cargar(rev_id)
    if session.get('role') not in ROLES_CONFIRMAN_REVERSION:
        flash('⛔ La reversión la confirma Logística.')
        return redirect(volver)
    if rev.estado != 'PENDIENTE':
        flash('Esta reversión ya se resolvió.')
        return redirect(volver)
    nota = ' '.join((request.form.get('nota') or '').split())[:500]
    pedidos = _rev_items_json(rev)
    original = OrdenCompra.query.get(rev.original_id) if rev.original_id else None
    if rev.modo == 'DUPLICADA':
        if not original or original.estado in DUP_ESTADOS_FUERA:
            flash('⛔ La orden correcta elegida ya no está vigente (se anuló o rechazó). Rechaza esta reversión y que Almacén la pida otra vez.')
            return redirect(volver)
        if (orden.estado_pago or 'PENDIENTE') == 'PAGADO':
            flash(f'⛔ {_oc_codigo(orden)} está PAGADA: una orden pagada no se anula. Que Gerencia quite el pagado en la orden (y lo registre en la correcta) y vuelve a confirmar.')
            return redirect(volver)
    Modelo, Movimiento, origen = _modelos_inv_orden(orden)
    solicito = rev.solicitado_por.nombre_completo if rev.solicitado_por else 'Almacén'
    hechos, ahora = [], hora_peru()
    try:
        actuales = {x['item_id']: x for x in _rev_ingresados(orden)}
        objetivo = list(actuales.values()) if rev.modo == 'DUPLICADA' else [actuales[x['item_id']] for x in pedidos if x['item_id'] in actuales]
        if not objetivo:
            raise ValueError('ya no hay nada ingresado de esos ítems (alguien lo corrigió antes)')
        items = {i.id: i for i in orden.items}
        motivo_kx = (f"REVERSIÓN DE INGRESO de {_oc_codigo(orden)} ({MODOS_REVERSION[rev.modo]['txt'].lower()}"
                     + (f" de {_oc_codigo(original)}" if original else '') + f"). Pidió {solicito}, confirmó {session.get('nombre', '')}: {rev.motivo}")
        for x in objetivo:
            antes = despues = None
            for mid in x['movs']:
                mov = Movimiento.query.get(mid)
                if mov is None:
                    continue
                _, a, d, _, prod = _eliminar_mov_auditado(origen, mov, motivo_kx, orden_compra_id=orden.id, reversion_id=rev.id)
                antes = a if antes is None else antes
                despues = d
            for e in _oc_entregas(orden):
                for ei in e.items:
                    if ei.item_id == x['item_id'] and ei.fecha_ingreso:
                        ei.ingresado_por_id = ei.fecha_ingreso = ei.nota_ingreso = None
                        ei.kardex_mov_id = ei.cantidad_kardex = None
            it = items.get(x['item_id'])
            if it:
                it.ingresado_por_id = it.fecha_ingreso = None
                it.kardex_mov_id = it.cantidad_kardex = None
            x.update(stock_antes=antes if antes is not None else x['stock_antes'], stock_despues=despues if despues is not None else x['stock_antes'])
            hechos.append(x)
        orden.kardex_registrado_por_id, orden.fecha_kardex = None, None
        db.session.flush()
        resumen = _rev_resumen(hechos)
        _oc_evento(orden, 'REVERSION', f"Ingreso al Kardex REVERTIDO ({resumen}) · pidió {solicito}, confirmó {session.get('nombre', '')}"
                                       + (f" · {nota}" if nota else '') + f" · {rev.motivo}")
        if rev.modo == 'DUPLICADA':
            bl = _dup_bloqueo_anular(orden)
            if bl:
                raise ValueError(f'no se puede anular: {bl}')
            _dup_anular(orden, original, f"{rev.motivo} (ingreso al Kardex revertido: {resumen})"[:500])
        else:
            # vuelve a Logística como DEVUELTA (mismo camino de siempre: la editan y Almacén la ingresa bien)
            orden.devuelta_almacen = True
            orden.devolucion_motivo = f"Reversión de ingreso al Kardex ({resumen}): {rev.motivo}"[:600]
            orden.devolucion_items = json.dumps([{'item_id': x['item_id'], 'item': x['item'], 'descripcion': x['descripcion'][:120], 'codigo': x['sku'],
                                                  'um': x['um'], 'oc': x['cantidad_oc'], 'llego': None, 'real': None,
                                                  'nota': f"se revirtió −{x['cantidad']} del Kardex"} for x in hechos], ensure_ascii=False)
            orden.devuelta_por_id, orden.fecha_devuelta = rev.solicitado_por_id, ahora
            orden.devoluciones = (orden.devoluciones or 0) + 1
            _oc_evento(orden, 'DEVUELTA', f"Devuelta a Logística por {solicito} · {orden.devolucion_motivo}")
        rev.items = json.dumps(hechos, ensure_ascii=False, default=str)
        rev.estado, rev.resuelto_por_id, rev.fecha_resuelta, rev.nota_resolucion = 'CONFIRMADA', session.get('user_id'), ahora, nota or None
        corto = EMPRESAS_OC.get(orden.empresa or 'ANCLAJES', {}).get('corto', '')
        _notif_crear('OC_REVERSION_LISTA', f"Revertido el ingreso de {_oc_codigo(orden)} · {corto}",
                     f"{resumen} · " + (f"anulada por duplicada de {_oc_codigo(original)}" if original else 'devuelta a Logística para corregirla'),
                     url_for('oc_detalle', orden_id=orden.id), orden=orden, excluir=session.get('user_id'))
        registrar_log(f"Confirmó la REVERSIÓN del ingreso al Kardex {corto} de la {_oc_codigo(orden)} ({resumen})"
                      + (f"; anulada por duplicada de {_oc_codigo(original)}" if original else '; devuelta a Logística'), 'bi-arrow-counterclockwise', 'text-danger')
        db.session.commit()
    except ValueError as ex:
        db.session.rollback()
        flash(f'⛔ No se revirtió nada: {ex}.')
        return redirect(volver)
    except Exception as ex:
        db.session.rollback()
        app.logger.exception('No se pudo revertir el ingreso de la OC')
        flash(f'⛔ No se pudo revertir (no se cambió nada): {ex}')
        return redirect(volver)
    flash(f"✅ Ingreso revertido: {_rev_resumen(hechos)}. "
          + (f"{_oc_codigo(orden)} quedó ANULADA por duplicada de {_oc_codigo(original)}." if original
             else f"{_oc_codigo(orden)} quedó devuelta a Logística: edítala y Almacén la vuelve a ingresar.")
          + ' Los movimientos quedan en el Kardex → "Movimientos eliminados".')
    return redirect(volver)


@app.route('/ordenes/reversion/<int:rev_id>/rechazar', methods=['POST'])
@_ruta_oc('ver')
def oc_reversion_rechazar(rev_id):
    rev, orden, volver = _rev_cargar(rev_id)
    cancela = request.form.get('cancelar') == '1'
    if rev.estado != 'PENDIENTE':
        flash('Esta reversión ya se resolvió.')
        return redirect(volver)
    if cancela and not (session.get('user_id') == rev.solicitado_por_id or session.get('role') == 'admin'):
        flash('⛔ Solo quien la pidió (o Gerencia) la cancela.')
        return redirect(volver)
    if not cancela and session.get('role') not in ROLES_CONFIRMAN_REVERSION:
        flash('⛔ La reversión la confirma o rechaza Logística.')
        return redirect(volver)
    nota = ' '.join((request.form.get('nota') or '').split())[:500]
    if not cancela and len(nota) < 5:
        flash('⛔ Escribe por qué la rechazas, para que Almacén lo sepa.')
        return redirect(volver)
    rev.estado = 'CANCELADA' if cancela else 'RECHAZADA'
    rev.resuelto_por_id, rev.fecha_resuelta, rev.nota_resolucion = session.get('user_id'), hora_peru(), nota or None
    _oc_evento(orden, 'REVERSION_NO', f"{'Cancelada' if cancela else 'Rechazada'} la reversión de ingreso por {session.get('nombre', '')}" + (f": {nota}" if nota else ''))
    if not cancela:
        _notif_crear('OC_REVERSION_LISTA', f"Logística rechazó revertir {_oc_codigo(orden)}", nota, url_for('oc_detalle', orden_id=orden.id),
                     orden=orden, excluir=session.get('user_id'))
    db.session.commit()
    flash('Reversión ' + ('cancelada.' if cancela else 'rechazada: el stock y la orden siguen igual.'))
    return redirect(volver)
