# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# KARDEX · ELIMINAR UN MOVIMIENTO REGISTRADO POR ERROR (con auditoría)
# Gerencia (admin) y el Jefe de Almacén (rol almacen) pueden eliminar un movimiento mal registrado de los Kardex de
# Anclajes e Import Bolts. Al eliminarlo:
#   - el stock se REVIERTE: una SALIDA vuelve al inventario y una ENTRADA se descuenta;
#   - los movimientos POSTERIORES del mismo producto corrigen su saldo (para que la columna "Saldo" cuadre);
#   - deja de contar en el Kardex y en las estadísticas (ventas, toneladas, rotación), porque ya no existe;
#   - queda una copia completa en "Movimientos eliminados" (MovimientoEliminado): quién, cuándo, por qué y cómo quedó el stock.
# NO se pueden eliminar (tienen su propio camino para corregirse): los que vienen de una Orden de Compra (Ingresos
# pendientes → deshacer), de un proceso por OC, de un pedido (NP-), los inter-empresa, el saldo inicial y los de auditorías.
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================

ROLES_ELIMINAN_KARDEX = ['admin', 'almacen']          # Gerencia y Jefe de Almacén
DIAS_ELIMINAR_ALMACEN = 7                             # el Jefe de Almacén: solo movimientos de los últimos 7 días (Gerencia: cualquiera)
_MOTIVOS_AUTOMATICOS = ('NP-', 'INTER-EMPRESA', 'SALDO INICIAL', 'CONTEO FÍSICO', 'CONTEO FISICO', 'AUDITOR', 'RETORNO DE MERCADER')

try:
    with app.app_context():
        MovimientoEliminado.__table__.create(bind=db.engine, checkfirst=True)
except Exception as _e_mov_elim:
    print(f"Aviso: no se pudo preparar la tabla de movimientos eliminados: {_e_mov_elim}")


def _modelos_kardex(origen):
    return (ProductMovementImportBolts, ProductImportBolts) if origen == 'IMPORTBOLTS' else (ProductMovement, Product)


def _bloqueo_eliminar_mov(origen, m, rol=None):
    """Por qué NO se puede eliminar este movimiento (texto) o None si se puede."""
    rol = rol or session.get('role')
    if rol not in ROLES_ELIMINAN_KARDEX:
        return 'Solo Gerencia y el Jefe de Almacén pueden eliminar movimientos.'
    motivo = (m.motivo or '').upper()
    if getattr(m, 'orden_compra_id', None):
        return 'Vino de una Orden de Compra: corrígelo en Compras → Ingresos pendientes (deshacer el ingreso).'
    if m.proceso_oc_id:
        return 'Es parte de un proceso por OC (maestranza / transformación): corrígelo desde el proceso.'
    if getattr(m, 'orden_servicio_id', None):
        return 'Está vinculado a una Orden de Servicio: quita primero el vínculo.'
    if any(x in motivo for x in _MOTIVOS_AUTOMATICOS):
        return 'Es un movimiento automático del sistema (pedido, inter-empresa, saldo inicial o auditoría): no se elimina a mano.'
    if rol != 'admin' and m.fecha and m.fecha < hora_peru() - timedelta(days=DIAS_ELIMINAR_ALMACEN):
        return f'Tiene más de {DIAS_ELIMINAR_ALMACEN} días: solo Gerencia puede eliminarlo.'
    return None


def _puede_eliminar_mov(origen, m):
    return _bloqueo_eliminar_mov(origen, m) is None


app.add_template_global(_puede_eliminar_mov, 'puede_eliminar_mov')
app.add_template_global(ROLES_ELIMINAN_KARDEX, 'roles_eliminan_kardex')


def _plan_eliminar_mov(origen, m):
    """Calcula el efecto de eliminar el movimiento SIN guardar nada: (delta de stock, stock actual, stock nuevo,
    movimientos posteriores, error). delta = lo que vuelve (+) o se descuenta (-) del stock."""
    Modelo, Producto = _modelos_kardex(origen)
    prod = Producto.query.get(m.product_id)
    if not prod:
        return None, None, None, [], 'El producto ya no existe.'
    delta = (m.cantidad or 0) if m.tipo == 'SALIDA' else -(m.cantidad or 0)
    actual = int(prod.stock_actual or 0)
    nuevo = actual + delta
    posteriores = Modelo.query.filter(Modelo.product_id == m.product_id, Modelo.id > m.id).order_by(Modelo.id).all()
    if nuevo < 0:
        return delta, actual, nuevo, posteriores, (f'No se puede: es una ENTRADA de {m.cantidad} y hoy solo hay {actual} en stock '
                                                   f'(quedaría en {nuevo}). Primero corrige las salidas que se hicieron con ese stock.')
    for p in posteriores:
        if p.stock_nuevo is not None and p.stock_nuevo + delta < 0:
            return delta, actual, nuevo, posteriores, (f'No se puede: el saldo del movimiento del {p.fecha.strftime("%d/%m/%Y %H:%M")} '
                                                       f'quedaría negativo ({p.stock_nuevo + delta}). Revisa los movimientos posteriores.')
    return delta, actual, nuevo, posteriores, None


@app.route('/kardex/<origen>/movimiento/<int:mov_id>/eliminar/previa')
def kardex_eliminar_previa(origen, mov_id):
    """Antes de eliminar: qué pasará con el stock (para mostrarlo en la ventana de confirmación)."""
    origen = 'IMPORTBOLTS' if origen.upper() == 'IMPORTBOLTS' else 'ANCLAJES'
    if session.get('role') not in ROLES_ELIMINAN_KARDEX:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    Modelo, _ = _modelos_kardex(origen)
    m = Modelo.query.get_or_404(mov_id)
    bloqueo = _bloqueo_eliminar_mov(origen, m)
    if bloqueo:
        return {'status': 'error', 'msg': bloqueo}
    delta, actual, nuevo, posteriores, err = _plan_eliminar_mov(origen, m)
    if err:
        return {'status': 'error', 'msg': err}
    return {'status': 'success', 'sku': m.product.sku, 'producto': m.product.nombre, 'tipo': m.tipo, 'cantidad': m.cantidad,
            'fecha': m.fecha.strftime('%d/%m/%Y %H:%M') if m.fecha else '', 'motivo': m.motivo or '', 'referencia': m.referencia or '',
            'stock_actual': actual, 'stock_nuevo': nuevo, 'delta': delta, 'posteriores': len(posteriores)}


@app.route('/kardex/<origen>/movimiento/<int:mov_id>/eliminar', methods=['POST'])
def kardex_eliminar_movimiento(origen, mov_id):
    origen = 'IMPORTBOLTS' if origen.upper() == 'IMPORTBOLTS' else 'ANCLAJES'
    destino = request.form.get('volver') or request.referrer or url_for('ver_kardex_importbolts' if origen == 'IMPORTBOLTS' else 'ver_kardex')
    if session.get('role') not in ROLES_ELIMINAN_KARDEX:
        flash('⛔ Solo Gerencia y el Jefe de Almacén pueden eliminar movimientos del Kardex.')
        return redirect(destino)
    Modelo, Producto = _modelos_kardex(origen)
    m = Modelo.query.get_or_404(mov_id)
    motivo_elim = ' '.join((request.form.get('motivo') or '').split())[:300]
    if len(motivo_elim) < 10:
        flash('⛔ Escribe el motivo de la eliminación (mínimo 10 letras): queda en la auditoría.')
        return redirect(destino)
    bloqueo = _bloqueo_eliminar_mov(origen, m)
    if bloqueo:
        flash(f'⛔ {bloqueo}')
        return redirect(destino)
    delta, actual, nuevo, posteriores, err = _plan_eliminar_mov(origen, m)
    if err:
        flash(f'⛔ {err}')
        return redirect(destino)
    col_doc = MovimientoDocumento.movimiento_ib_id if origen == 'IMPORTBOLTS' else MovimientoDocumento.movimiento_id
    docs = MovimientoDocumento.query.filter(col_doc == m.id).all()
    prod = Producto.query.get(m.product_id)
    ahora = hora_peru()
    copia = {c.name: (getattr(m, c.name).isoformat() if hasattr(getattr(m, c.name), 'isoformat') else getattr(m, c.name))
             for c in m.__table__.columns}
    copia['documentos'] = [{'tipo': d.tipo_documento, 'nombre': d.nombre_original, 's3_key': d.s3_key} for d in docs]
    try:
        db.session.add(MovimientoEliminado(
            origen=origen, movimiento_id=m.id, product_id=m.product_id, sku=prod.sku, producto=(prod.nombre or '')[:500], tipo=m.tipo,
            cantidad=m.cantidad, fecha_movimiento=m.fecha, motivo=(m.motivo or '')[:200], referencia=(m.referencia or '')[:50] or None,
            proveedor=(' · '.join(x for x in ((m.razon_social_proveedor or getattr(m, 'cliente_razon', None) or ''), (m.ruc_proveedor or '')) if x))[:200] or None,
            registrado_por=(m.user.nombre_completo or m.user.username) if m.user else None,
            stock_antes=actual, stock_despues=nuevo, movimientos_ajustados=len(posteriores),
            datos=json.dumps(copia, ensure_ascii=False, default=str), eliminado_por_id=session.get('user_id'),
            eliminado_por=session.get('nombre', '') or session.get('username', ''), rol=session.get('role'),
            fecha_eliminacion=ahora, motivo_eliminacion=motivo_elim))
        # el saldo de los movimientos posteriores se corrige (como si este nunca se hubiera registrado)
        for p in posteriores:
            if p.stock_anterior is not None:
                p.stock_anterior += delta
            if p.stock_nuevo is not None:
                p.stock_nuevo += delta
        prod.stock_actual = nuevo
        for d in docs:          # el archivo se conserva en S3 (su referencia queda en la auditoría)
            db.session.delete(d)
        db.session.delete(m)
        registrar_log(f"ELIMINÓ del Kardex {EMPRESAS_OC.get(origen, {}).get('corto', origen)} el movimiento #{mov_id} "
                      f"({m.tipo} {m.cantidad} de {prod.sku}, {m.fecha.strftime('%d/%m/%Y %H:%M') if m.fecha else ''}): stock {actual} → {nuevo}. "
                      f"Motivo: {motivo_elim}", 'bi-trash3-fill', 'text-danger')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo eliminar el movimiento del Kardex")
        flash(f'⛔ No se pudo eliminar (no se cambió nada): {e}')
        return redirect(destino)
    flash(f"✅ Movimiento eliminado: {m.tipo} de {m.cantidad} en {prod.sku}. Stock {actual} → {nuevo}"
          + (f" ({'volvió' if delta > 0 else 'se descontó'} {abs(delta)})" if delta else '')
          + (f"; se corrigió el saldo de {len(posteriores)} movimiento(s) posterior(es)" if posteriores else '')
          + '. Queda en "Movimientos eliminados".')
    return redirect(destino)


@app.route('/kardex/eliminados')
def kardex_eliminados():
    """Auditoría: los movimientos del Kardex que se eliminaron (quién, cuándo, por qué y cómo quedó el stock)."""
    if session.get('role') not in ['admin', 'almacen', 'logistica', 'administracion']:
        return "Acceso denegado", 403
    origen = request.args.get('origen', 'TODOS').upper()
    q = MovimientoEliminado.query
    if origen in ('ANCLAJES', 'IMPORTBOLTS'):
        q = q.filter(MovimientoEliminado.origen == origen)
    buscar = ' '.join((request.args.get('q') or '').split())
    if buscar:
        b = f'%{buscar}%'
        q = q.filter(db.or_(MovimientoEliminado.sku.ilike(b), MovimientoEliminado.producto.ilike(b), MovimientoEliminado.motivo.ilike(b),
                            MovimientoEliminado.motivo_eliminacion.ilike(b), MovimientoEliminado.eliminado_por.ilike(b),
                            MovimientoEliminado.proveedor.ilike(b), MovimientoEliminado.referencia.ilike(b)))
    filas = q.order_by(MovimientoEliminado.fecha_eliminacion.desc(), MovimientoEliminado.id.desc()).limit(500).all()
    return render_template('kardex_eliminados.html', filas=filas, origen=origen, buscar=buscar, empresas_oc=EMPRESAS_OC)
