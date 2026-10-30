# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · vaciar datos (pruebas) y contadores del menú
# borrar los datos del módulo de órdenes y los números del menú (por aprobar, por recibir...)
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

def _oc_vinculos_fuera():
    """Lo que las órdenes ya movieron en OTROS módulos (no se borra al vaciar): movimientos del Kardex hechos desde una orden,
    ingresos a Insumos y el número inicial configurado de cada empresa."""
    movs = []
    for origen, Mov, Prod in (('Anclajes', ProductMovement, Product), ('Import Bolts', ProductMovementImportBolts, ProductImportBolts)):
        try:
            for m in Mov.query.filter(Mov.orden_compra_id.isnot(None)).order_by(Mov.id).all():
                prod = Prod.query.get(m.product_id)
                movs.append({'kardex': origen, 'id': m.id, 'sku': prod.sku if prod else '?', 'cantidad': m.cantidad,
                             'fecha': m.fecha, 'tipo': m.tipo})
        except Exception:
            db.session.rollback()
    ingresos_ins = OrdenCompra.query.filter(OrdenCompra.insumo_ingreso_id.isnot(None)).count()
    inicio = {}
    for e in EMPRESAS_OC:
        for t in TIPOS_OC:
            v = OCConfig.query.get(_oc_clave_cfg(e, f'num_{t}'))
            if v and (v.valor or '').isdigit() and int(v.valor) > 1:
                inicio[f"{t} {EMPRESAS_OC[e]['corto']}"] = _oc_numero_txt(None, int(v.valor), e)
    return {'movs_kardex': movs, 'ingresos_insumos': ingresos_ins, 'inicio': inicio}


@app.route('/ordenes/config/vaciar', methods=['POST'])
@_ruta_oc('admin')
def oc_vaciar():
    """Borra SOLO los datos de Órdenes de Compra/Servicio (y sus archivos en S3). No toca ningún otro módulo."""
    f = request.form
    destino = url_for('oc_config', tab='vaciar')
    if (f.get('confirmacion') or '').strip().upper() != 'BORRAR ORDENES':
        flash('⛔ Escribe BORRAR ORDENES para confirmar.')
        return redirect(destino)
    claves = [d.s3_key for d in OrdenCompraDocumento.query.all() if d.s3_key]
    n = OrdenCompra.query.count()
    extra = []
    try:
        # Los movimientos del Kardex hechos desde una orden NO se borran (el stock ya se movió): solo se les quita el enlace
        n_movs = 0
        for Mov in (ProductMovement, ProductMovementImportBolts):
            n_movs += Mov.query.filter(Mov.orden_compra_id.isnot(None)).update(
                {'orden_compra_id': None, 'orden_item_id': None}, synchronize_session=False) or 0
        if n_movs:
            extra.append(f'{n_movs} movimiento(s) del Kardex quedaron sin enlace a la orden (no se borran)')
        claves += [d.s3_key for d in RequerimientoDocumento.query.all() if d.s3_key]
        n_req = RequerimientoCompra.query.count()
        for modelo in (OrdenCompraEntregaItem, OrdenCompraEntrega, OrdenCompraDocumento, OrdenCompraEvento, OrdenCompraItem, OrdenCompra,
                       RequerimientoDocumento, RequerimientoEvento, RequerimientoVisto, RequerimientoItem, RequerimientoCompra, Notificacion):
            modelo.query.delete(synchronize_session=False)
        if n_req:
            extra.append(f'{n_req} requerimiento(s) de Almacén')
        if f.get('proveedores') == '1':
            OCContacto.query.delete(synchronize_session=False)
            OCCuentaBancaria.query.delete(synchronize_session=False)
            OCProveedor.query.delete(synchronize_session=False)
            extra.append('proveedores, contactos y cuentas bancarias guardados')
        if f.get('catalogos') == '1':
            CatalogoValor.query.filter(CatalogoValor.tipo.in_(list(CATALOGOS_OC))).delete(synchronize_session=False)
            OCConfig.query.delete(synchronize_session=False)
            OCMotivoRechazo.query.delete(synchronize_session=False)
            OCMotivoCompra.query.delete(synchronize_session=False)
            db.session.flush()
            _sembrar_catalogos_oc()
            _sembrar_motivos_compra_oc()
            for cat, mot in _OC_MOTIVOS_INICIALES:
                db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True, uso='RECHAZO', aplica='AMBAS'))
            for uso, aplica, cat, mot in _OC_MOTIVOS_V2 + _OC_MOTIVOS_RQ + _OC_MOTIVOS_DESCARTE:
                db.session.add(OCMotivoRechazo(categoria=cat, motivo=mot, activo=True, uso=uso, aplica=aplica))
            extra.append('U.M., condiciones de pago, tipos de servicio, áreas, solicitantes, motivos de compra, rechazo y anulación, '
                         'datos del PDF y número inicial de cada empresa')
        registrar_log(f"VACIÓ los datos de Órdenes de Compra: {n} orden(es), {len(claves)} archivo(s)"
                      + (f" + {', '.join(extra)}" if extra else ''), 'bi-trash3-fill', 'text-danger')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo vaciar el módulo de órdenes")
        flash(f'⛔ No se pudo vaciar (no se borró nada): {e}')
        return redirect(destino)
    _borrar_de_s3(claves)
    flash(f"✅ Órdenes vaciadas: {n} orden(es) y {len(claves)} archivo(s) borrados. La numeración vuelve a empezar"
          + (' desde el N° 00001' if f.get('catalogos') == '1' else ' (desde el número inicial configurado de cada empresa, si hay uno)')
          + (f"; además: {', '.join(extra)}" if extra else '') + '.')
    return redirect(destino)


@app.context_processor
def _contador_ordenes():
    """Números para el menú: órdenes por aprobar (Gerencia) y aprobadas por recibir (Logística)."""
    rol = session.get('role')
    if (rol not in ROLES_OC_VEN and rol not in ROLES_OC_INGRESAN and rol not in ROLES_REQ_CREAN) or not _oc_ok:
        return {}
    try:
        alertas = 0
        if rol in ROLES_OC_VEN:
            hoy = hora_peru().date()
            activas = OrdenCompra.query.filter(OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME'])).all()
            alertas = sum(1 for o in activas if _oc_atraso(o, hoy) or _oc_pago_info(o, hoy)['nivel'] in ('vencida', 'por_vencer'))
        return {'oc_por_aprobar': OrdenCompra.query.filter_by(estado='ENVIADA').count() if rol == 'admin' else 0,
                'oc_por_recibir': OrdenCompra.query.filter(OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA'])).count()
                if rol in ROLES_OC_EDITAN else 0,
                'oc_por_ingresar': (len(_items_por_ingresar()) + len(_os_por_seguir())) if rol in ROLES_OC_INGRESAN else 0,
                'oc_req_pendientes': len(_req_pendientes_de_oc()) if rol in ROLES_REQ_ATIENDEN else 0,
                'oc_req_novedades': len(_req_novedades(session.get('user_id'), limite=0)) if rol in ROLES_REQ_CREAN else 0,
                'oc_alertas': alertas,
                'oc_cert_pend': len(_certificados_pendientes()) if rol in ROLES_OC_VEN else 0}
    except Exception:
        db.session.rollback()
        return {}


