# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# INSUMOS INTERNOS · ingresos, salidas y kardex
# ingresos (con factura / desde OC), salidas (PDF, firma) y kardex valorizado
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- INGRESOS ----------------------------
def _oc_pendiente_insumos(oc_id):
    """Orden de compra CONFORME, con destino Insumos y todavía sin ingresar. None si no aplica."""
    try:
        o = OrdenCompra.query.get(int(oc_id)) if oc_id else None
    except (TypeError, ValueError):
        return None
    if o and o.estado == 'CONFORME' and o.destino == 'INSUMOS' and not o.insumo_ingreso_id and not o.es_contable and not o.devuelta_almacen:
        return o
    return None


def _ordenes_pendientes_insumos(empresa=None):
    """OC conformes para Insumos internos que todavía no se registran (de una empresa, o de las dos)."""
    try:
        lista = OrdenCompra.query.filter(OrdenCompra.estado == 'CONFORME', OrdenCompra.destino == 'INSUMOS',
                                         OrdenCompra.insumo_ingreso_id.is_(None)).order_by(OrdenCompra.fecha_conforme).all()
    except Exception:
        db.session.rollback()
        return []
    # las de TEMA CONTABLE no se registran en Insumos (no suman): se confirman en "Ingresos pendientes" de Compras
    return [o for o in lista if not o.es_contable and not o.devuelta_almacen and (not empresa or (o.empresa or 'ANCLAJES') == empresa)]


def _n_oc_pendientes_insumos():
    return len(_ordenes_pendientes_insumos()) if _oc_ok else 0


app.add_template_global(_n_oc_pendientes_insumos, 'n_oc_pendientes_insumos')


def _ocs_de_ingresos(ingresos):
    """La Orden de Compra de cada ingreso (para ver y descargar su PDF y sus documentos en todo momento) y los documentos
    de cada orden. Devuelve ({ingreso_id: OrdenCompra}, {orden_id: [OrdenCompraDocumento]})."""
    ingresos = [i for i in ingresos if i]
    if not ingresos:
        return {}, {}
    try:
        _asegurar_oc()
        ids = [i.id for i in ingresos]
        por_id = {o.id: o for o in OrdenCompra.query.filter(
            OrdenCompra.id.in_([i.orden_compra_id for i in ingresos if i.orden_compra_id] or [0])).all()}
        por_ing = {o.insumo_ingreso_id: o for o in OrdenCompra.query.filter(OrdenCompra.insumo_ingreso_id.in_(ids)).all()}
        ocs = {}
        for i in ingresos:
            o = por_id.get(i.orden_compra_id) or por_ing.get(i.id)    # los ingresos antiguos no guardaban la OC: se busca por la orden
            if o:
                ocs[i.id] = o
        docs = {}
        for d in OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id.in_([o.id for o in ocs.values()] or [0])).all():
            docs.setdefault(d.orden_id, []).append(d)
        return ocs, docs
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudieron leer las órdenes de compra de los ingresos de insumos")
        return {}, {}


def _prefill_ingreso_desde_oc(o):
    """Datos de la OC para llenar el ingreso de insumos (proveedor, factura, fecha de llegada, ítems y precios con IGV)."""
    guardado = InsumoProveedor.query.filter(InsumoProveedor.ruc == o.ruc).first() if o.ruc else None
    sunat = Proveedor.query.filter_by(documento=o.ruc).first() if o.ruc and not guardado else None
    if guardado:
        prov = {'modo': 'guardado', 'id': guardado.id, 'ruc': guardado.ruc or '', 'razon_social': guardado.razon_social,
                'direccion': guardado.direccion or '', 'contacto_nombre': o.contacto or guardado.contacto_nombre or '',
                'contacto_telefono': o.telefono or guardado.contacto_telefono or ''}
    elif sunat:
        prov = {'modo': 'sunat', 'proveedor_id': sunat.id, 'ruc': sunat.documento, 'razon_social': sunat.razon_social,
                'direccion': sunat.direccion or '', 'telefono': o.telefono or ''}
    else:
        prov = {'modo': 'manual', 'ruc': o.ruc or '', 'razon_social': o.razon_social, 'direccion': o.direccion or ''}
    prov.setdefault('contacto_nombre', o.contacto or '')
    prov.setdefault('contacto_telefono', o.telefono or '')
    rec = _oc_recepcion(o) if o.fecha_llegada else None
    # lo que de verdad llegó (si llegó por partes o se cerró el saldo, no lo pedido)
    items = [{'insumo_id': it.insumo_id or '', 'descripcion': it.descripcion, 'um': it.um,
              'cantidad': rec['items'][it.id]['llego'] if rec and rec['entregas'] else it.cantidad,
              'precio_oc': it.precio_unitario, 'simbolo': MONEDAS_OC[o.moneda]['simbolo'],
              # en la moneda de la orden (soles o dólares, sin convertir); con IGV, salvo importación
              'precio_unitario': it.precio_unitario if o.es_importacion else (it.precio_con_igv if it.precio_con_igv else round(it.precio_unitario * (1 + IGV_OC), 4))}
             for it in o.items if not (rec and rec['entregas'] and rec['items'][it.id]['llego'] <= 0)]
    docs = [{'id': d.id, 'tipo': d.tipo, 'nombre': d.nombre_original, 'url': url_for('oc_documento_ver', doc_id=d.id),
             'tipo_txt': TIPOS_DOC_OC.get(d.tipo, d.tipo), 'numero': {'GUIA': o.numero_guia, 'FACTURA': o.numero_factura}.get(d.tipo) or ''}
            for d in OrdenCompraDocumento.query.filter_by(orden_id=o.id).all() if d.tipo in ('GUIA', 'FACTURA', 'CERTIFICADO', 'OTRO')]
    return {'oc_id': o.id, 'codigo': _oc_codigo(o), 'fecha': (o.fecha_llegada or o.fecha_conforme or hora_peru()).date().isoformat(),
            'numero_factura': o.numero_factura or '', 'moneda': o.moneda, 'importacion': bool(o.es_importacion), 'proveedor': prov, 'items': items, 'docs': docs,
            'empresa': o.empresa or 'ANCLAJES', 'numero_guia': o.numero_guia or '', 'pdf': url_for('oc_pdf', orden_id=o.id, ver=1)}


@app.route('/insumos/ingreso/nuevo')
@_ruta_insumos(editar=True)
def insumos_ingreso_nuevo():
    empresa = _empresa_param()
    _asegurar_oc()
    oc = _oc_pendiente_insumos(request.args.get('oc'))
    if request.args.get('oc') and not oc:
        flash('Esa orden de compra ya fue ingresada o todavía no está conforme.')
    return render_template('insumos_ingreso_form.html', empresa=(oc.empresa or 'ANCLAJES') if oc else empresa, empresas=EMPRESAS_INSUMOS,
                           oc_prefill=_prefill_ingreso_desde_oc(oc) if oc else None, oc_pendientes=_ordenes_pendientes_insumos(empresa),
                           insumos_json={e: _datos_formulario_insumos(e) for e in EMPRESAS_INSUMOS},
                           categorias=_catalogo_insumos('INSUMO_CATEGORIA'), unidades=_catalogo_insumos('INSUMO_UNIDAD'),
                           categorias_filtro=_categorias_insumos(),
                           almacenes=_catalogo_insumos('INSUMO_ALMACEN'), hoy=hora_peru().date(), seccion='ingreso')


@app.route('/insumos/pendientes-oc')
@_ruta_insumos()
def insumos_pendientes_oc():
    """Compras con Orden de Compra (destino Insumos) que ya llegaron y están conformes, esperando registrarse en el inventario de insumos.
    Separadas por empresa; cada una se ingresa con sus datos ya llenos (proveedor, factura, ítems, precios y documentos)."""
    _asegurar_oc()
    empresa = _empresa_param()
    session['insumos_empresa'] = empresa
    ordenes = _ordenes_pendientes_insumos(empresa)
    por_emp = {e: len(_ordenes_pendientes_insumos(e)) for e in EMPRESAS_INSUMOS}
    try:
        devueltas = [o for o in OrdenCompra.query.filter(OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME', 'ENVIADA']), OrdenCompra.destino == 'INSUMOS',
                                                         OrdenCompra.devuelta_almacen.is_(True), OrdenCompra.insumo_ingreso_id.is_(None)).all()
                     if (o.empresa or 'ANCLAJES') == empresa]
    except Exception:
        db.session.rollback()
        devueltas = []
    stocks = {st.insumo_id: st for st in InsumoStock.query.filter_by(empresa=empresa).all()}
    docs = {}
    for d in OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id.in_([o.id for o in ordenes] or [0])).all():
        docs.setdefault(d.orden_id, []).append(d)
    ahora = hora_peru()
    return render_template('insumos_pendientes_oc.html', ordenes=ordenes, empresa=empresa, empresas=EMPRESAS_INSUMOS, por_emp=por_emp,
                           stocks=stocks, docs=docs, monedas=MONEDAS_OC, igv=IGV_OC, ahora=ahora, insumos={i.id: i for i in Insumo.query.all()},
                           puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN, puede_ver_oc=session.get('role') in ROLES_OC_VEN,
                           tipos_doc=TIPOS_DOC_OC, seccion='oc_pend', devueltas=devueltas)


@app.route('/insumos/ingreso/guardar', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_ingreso_guardar():
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    f = request.form
    volver = url_for('insumos_ingreso_nuevo', empresa=f.get('empresa'), oc=f.get('oc_id') or None)
    orden_oc = None
    if f.get('oc_id'):
        _asegurar_oc()
        orden_oc = _oc_pendiente_insumos(f.get('oc_id'))
        if not orden_oc:
            flash('⛔ Esa orden de compra ya fue ingresada o no está conforme.')
            return redirect(url_for('insumos_ingreso_nuevo'))
    empresa = (f.get('empresa') or '').upper()
    if empresa not in EMPRESAS_INSUMOS:
        flash('⛔ Elige la empresa del ingreso.')
        return redirect(volver)
    fecha, err = _fecha_movimiento_insumo(f.get('fecha'))
    if err:
        flash(f'⛔ {err}')
        return redirect(volver)
    datos_prov, err = _datos_proveedor_ingreso(f)
    if err:
        flash(f'⛔ {err}')
        return redirect(volver)
    # La factura es OPCIONAL (inventario de cosas antiguas, compras sin comprobante): se puede completar después
    numero_factura = ' '.join((f.get('numero_factura') or '').split()).upper()[:50] or None
    repetido = _factura_insumo_repetida(empresa, numero_factura, datos_prov) if numero_factura else None
    if repetido:
        flash(f'⛔ La factura {numero_factura} de {datos_prov["razon_social"]} ya está registrada en el ingreso #{repetido.id} '
              f'({repetido.fecha.strftime("%d/%m/%Y")}). Si era otra compra, revisa el número.')
        return redirect(volver)
    moneda = 'USD' if (f.get('moneda') or '').upper() == 'USD' else 'PEN'
    if orden_oc:      # desde una OC: la moneda es la de la orden (no se convierte)
        moneda = 'USD' if orden_oc.moneda == 'USD' else 'PEN'
    simbolo = MONEDAS_INSUMOS[moneda]
    items, errores = [], []
    ids = f.getlist('insumo_id[]')
    pendientes = f.getlist('precio_pendiente[]')      # '1' = la fila entra SIN PRECIO (no toca el costo promedio)
    valorizar = f.getlist('valorizar_sc[]')           # '1' = con este precio, completar también lo que hay "sin precio" de ese insumo
    for n, (iid, cod_prov, cant, pu, pt, smin) in enumerate(zip(ids, f.getlist('codigo_proveedor[]'), f.getlist('cantidad[]'),
                                                              f.getlist('precio_unitario[]'), f.getlist('precio_total[]'),
                                                              f.getlist('stock_minimo[]')), start=1):
        if not (iid or '').strip():
            continue
        ins = Insumo.query.get(int(iid)) if iid.isdigit() else None
        cantidad, unit, total, minimo = _num(cant), _num(pu), _num(pt), _num(smin)
        sin_precio = (pendientes[n - 1] if n - 1 < len(pendientes) else '') == '1'
        if not ins or not ins.activo:
            errores.append(f'Fila {n}: el insumo no existe o está inactivo.')
            continue
        if cantidad is None or cantidad <= 0:
            errores.append(f'Fila {n} ({ins.codigo}): la cantidad debe ser mayor a 0.')
            continue
        if sin_precio:
            items.append({'ins': ins, 'cod_prov': ' '.join((cod_prov or '').split())[:60], 'cantidad': cantidad,
                          'unit': 0.0, 'total': 0.0, 'minimo': minimo, 'pendiente': True, 'valorizar': False})
            continue
        if unit is None and total is not None:
            unit = total / cantidad
        if unit is None or unit < 0:
            errores.append(f'Fila {n} ({ins.codigo}): falta el precio (unitario o total) con IGV.')
            continue
        total = round(total if total is not None else unit * cantidad, 2)
        items.append({'ins': ins, 'cod_prov': ' '.join((cod_prov or '').split())[:60], 'cantidad': cantidad,
                      'unit': round(unit, 6), 'total': total, 'minimo': minimo, 'pendiente': False,
                      'valorizar': (valorizar[n - 1] if n - 1 < len(valorizar) else '') == '1' and unit > 0})
    if not items and not errores:
        errores.append('Agrega al menos un insumo.')
    archivos = []
    for tipo in ('FACTURA', 'GUIA'):
        a = request.files.get(f'doc_{tipo}')
        if a and a.filename:
            ok, info = _validar_documento_kardex(a)
            if not ok:
                errores.append(f'{tipo.title()}: {info}')
            else:
                archivos.append((tipo, a, info))
    if errores:
        flash('⛔ ' + ' '.join(errores))
        return redirect(volver)

    ahora = hora_peru()
    claves = []
    try:
        prov_ins = _guardar_proveedor_insumo(datos_prov, fecha)
        ing = InsumoIngreso(
            empresa=empresa, fecha=fecha, moneda=moneda, proveedor_id=datos_prov['proveedor_id'], insumo_proveedor_id=prov_ins.id,
            ruc=datos_prov['ruc'] or None, razon_social=datos_prov['razon_social'], direccion=datos_prov['direccion'] or None,
            numero_factura=numero_factura,
            contacto_nombre=datos_prov['contacto_nombre'] or None, contacto_telefono=datos_prov['contacto_telefono'] or None,
            almacen=(f.get('almacen') or '').strip()[:100] or None,
            observacion=' '.join((f.get('observacion') or '').split())[:300] or None,
            total=round(sum(i['total'] for i in items), 2), estado='REGISTRADO', user_id=session.get('user_id'), fecha_registro=ahora,
            orden_compra_id=orden_oc.id if orden_oc else None)
        db.session.add(ing)
        db.session.flush()
        ref = f"Factura {ing.numero_factura}" if ing.numero_factura else f"Ingreso #{ing.id} (sin factura)"
        valorizados = 0
        doc_lote = ref + (f" · {_oc_codigo(orden_oc)}" if orden_oc else '')
        for it in items:
            st = _stock_de(it['ins'].id, empresa)
            if ing.almacen:
                st.almacen = ing.almacen
            if it['minimo'] is not None and it['minimo'] >= 0:
                st.stock_minimo = it['minimo']
            st.ultimo_ingreso = fecha
            prom_antes = _bolsa(st, moneda)[1]
            det = InsumoIngresoDetalle(
                ingreso_id=ing.id, insumo_id=it['ins'].id, codigo_proveedor=it['cod_prov'] or None, cantidad=it['cantidad'],
                precio_unitario=it['unit'], precio_total=it['total'], stock_antes=float(st.stock_actual or 0),
                costo_prom_antes=prom_antes, precio_pendiente=it['pendiente'], sin_costo_restante=it['cantidad'] if it['pendiente'] else 0.0)
            db.session.add(det)
            db.session.flush()
            # cada compra es un LOTE con su precio real (o sin precio, si está pendiente)
            lote, antes = _nuevo_lote(st, it['cantidad'], None if it['pendiente'] else it['unit'], moneda, fecha, 'COMPRA',
                                      ingreso=ing, detalle=det, proveedor=ing.razon_social, documento=doc_lote)
            det.stock_despues, det.costo_prom_despues = st.stock_actual, _bolsa(st, moneda)[1]
            db.session.add(InsumoMovimiento(
                empresa=empresa, insumo_id=it['ins'].id, fecha=fecha, tipo='ENTRADA', concepto='COMPRA', cantidad=it['cantidad'],
                costo_unitario=it['unit'], costo_total=it['total'], stock_antes=antes, stock_despues=st.stock_actual,
                **_datos_mov_lote(lote), referencia=ref[:120], ingreso_id=ing.id, user_id=session.get('user_id'),
                observacion='Precio pendiente: entra sin precio (se completa con la factura)' if it['pendiente'] else None,
                fecha_registro=ahora))
            if it['valorizar']:
                # reposición con factura: los lotes "sin precio" de este insumo toman el precio de esta compra (y sus salidas se recalculan)
                for l in _lotes_sin_precio(it['ins'].id, empresa, moneda=moneda, excluir_ingreso=ing.id):
                    _poner_precio_lote(l, it['unit'], ahora, moneda=moneda, motivo=f'Con el precio de la compra {ref}')
                    valorizados += float(l.cantidad_inicial or 0)
        for tipo, a, info in archivos:
            _subir_doc_insumo(f"{empresa.lower()}/ingresos/{ing.id}", a, info, tipo, claves, ingreso_id=ing.id)
        if orden_oc and f.get('usar_docs_oc') == '1':
            # documentos de la orden (guía, factura...): se COPIAN al ingreso (si se borran aquí, la orden conserva los suyos)
            ya = {t for t, _, _ in archivos}
            for d in OrdenCompraDocumento.query.filter_by(orden_id=orden_oc.id).all():
                if d.tipo not in ('GUIA', 'FACTURA', 'CERTIFICADO', 'OTRO') or d.tipo in ya:
                    continue
                ext = d.s3_key.rsplit('.', 1)[-1].lower()
                nueva = f"insumos/{empresa.lower()}/ingresos/{ing.id}/{d.tipo.lower()}_oc_{uuid.uuid4().hex}.{ext}"
                s3_client.copy_object(Bucket=S3_BUCKET_NAME, Key=nueva, CopySource={'Bucket': S3_BUCKET_NAME, 'Key': d.s3_key})
                claves.append(nueva)
                db.session.add(InsumoDocumento(ingreso_id=ing.id, tipo=d.tipo if d.tipo in ('GUIA', 'FACTURA') else 'OTRO', s3_key=nueva,
                                               nombre_original=d.nombre_original, content_type=d.content_type, tamano_bytes=d.tamano_bytes,
                                               subido_por=session.get('nombre', ''), fecha=ahora))
        if orden_oc:
            orden_oc.insumo_ingreso_id = ing.id
            ing.observacion = (f"{_oc_codigo(orden_oc)}" + (f" · {ing.observacion}" if ing.observacion else ''))[:300]
            _oc_evento(orden_oc, 'INSUMOS', f"Ingresado en Insumos internos (ingreso #{ing.id}, {EMPRESAS_INSUMOS[empresa]['corto']})")
            _req_notificar_orden(orden_oc, 'OC_INGRESADO', f"{_oc_codigo(orden_oc)}: ingresado en Insumos internos {EMPRESAS_INSUMOS[empresa]['corto']} (ingreso #{ing.id})")
        registrar_log(f"Ingreso de insumos {EMPRESAS_INSUMOS[empresa]['corto']} #{ing.id} ({ref}, {len(items)} ítem(s), {simbolo} {ing.total:,.2f})",
                      'bi-box-arrow-in-down', 'text-success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception("No se pudo guardar el ingreso de insumos")
        flash(f'⛔ No se pudo guardar el ingreso (no se registró nada): {e}')
        return redirect(volver)
    n_pend = sum(1 for i in items if i['pendiente'])
    flash(f'✅ Ingreso registrado: {len(items)} insumo(s) por {simbolo} {ing.total:,.2f}'
          + (' (en dólares: se lleva aparte, sin convertir a soles)' if moneda == 'USD' else '')
          + (f'. {n_pend} ítem(s) con PRECIO PENDIENTE: entraron como lote sin precio; complétalo aquí cuando tengas la factura' if n_pend else '')
          + (f'. Con esta compra se puso precio a lotes sin precio ({_cant_txt(valorizados)} und) y se recalcularon sus salidas' if valorizados else '')
          + '.' + (' Sin N° de factura: puedes agregarlo después en el ingreso.' if not numero_factura else ''))
    return redirect(url_for('insumos_ingreso_detalle', ingreso_id=ing.id))


@app.route('/insumos/ingresos')
@_ruta_insumos()
def insumos_ingresos():
    empresa = request.args.get('empresa', 'TODAS')
    q = InsumoIngreso.query
    if empresa in EMPRESAS_INSUMOS:
        q = q.filter(InsumoIngreso.empresa == empresa)
    buscar = ' '.join((request.args.get('q') or '').split())
    ingresos = q.order_by(InsumoIngreso.fecha.desc(), InsumoIngreso.id.desc()).limit(500).all()
    ocs, docs_oc = _ocs_de_ingresos(ingresos)
    if buscar:      # proveedor, RUC, factura o N° de la orden de compra
        b = buscar.upper()
        ingresos = [i for i in ingresos if b in (f'{i.razon_social or ""} {i.ruc or ""} {i.numero_factura or ""} '
                                                 f'{_oc_codigo(ocs[i.id]) + " " + _oc_numero_txt(ocs[i.id]) if i.id in ocs else ""}').upper()]
    pend = request.args.get('pend') == '1'
    if pend:        # solo los que tienen algún ítem con precio pendiente
        ingresos = [i for i in ingresos if i.estado == 'REGISTRADO' and any(d.precio_pendiente for d in i.detalles)]
    categoria = request.args.get('categoria', '')
    if categoria:
        ingresos = [i for i in ingresos if any((d.insumo.categoria or '') == categoria for d in i.detalles)]
    docs = {}
    for d in InsumoDocumento.query.filter(InsumoDocumento.ingreso_id.in_([i.id for i in ingresos] or [0])).all():
        docs.setdefault(d.ingreso_id, []).append(d)
    return render_template('insumos_ingresos.html', ingresos=ingresos, docs=docs, ocs=ocs, docs_oc=docs_oc, pend=pend, empresa=empresa, empresas=EMPRESAS_INSUMOS,
                           buscar=buscar, categoria=categoria, categorias_filtro=_categorias_insumos(), seccion='ingresos')


@app.route('/insumos/ingresos/<int:ingreso_id>')
@_ruta_insumos()
def insumos_ingreso_detalle(ingreso_id):
    ing = InsumoIngreso.query.get_or_404(ingreso_id)
    docs = InsumoDocumento.query.filter_by(ingreso_id=ing.id).order_by(InsumoDocumento.id).all()
    ocs, docs_oc = _ocs_de_ingresos([ing])
    oc = ocs.get(ing.id)
    lotes = {l.ingreso_detalle_id: l for l in InsumoLote.query.filter_by(ingreso_id=ing.id).all() if l.ingreso_detalle_id}
    return render_template('insumos_ingreso_detalle.html', ing=ing, docs=docs, empresas=EMPRESAS_INSUMOS, seccion='ingresos', lotes=lotes,
                           oc=oc, docs_oc=docs_oc.get(oc.id, []) if oc else [], puede_ver_oc=session.get('role') in ROLES_OC_VEN,
                           puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN)


@app.route('/insumos/ingresos/<int:ingreso_id>/documento', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_ingreso_documento(ingreso_id):
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    ing = InsumoIngreso.query.get_or_404(ingreso_id)
    tipo = (request.form.get('tipo') or 'FACTURA').upper()
    tipo = tipo if tipo in ('FACTURA', 'GUIA', 'OTRO') else 'OTRO'
    archivo = request.files.get('archivo')
    ok, info = _validar_documento_kardex(archivo)
    if not ok:
        flash(f'⛔ {info}')
        return redirect(url_for('insumos_ingreso_detalle', ingreso_id=ing.id))
    claves = []
    try:
        _subir_doc_insumo(f"{ing.empresa.lower()}/ingresos/{ing.id}", archivo, info, tipo, claves, ingreso_id=ing.id)
        db.session.commit()
        flash('✅ Documento adjuntado.')
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        flash(f'⛔ No se pudo subir el documento: {e}')
    return redirect(url_for('insumos_ingreso_detalle', ingreso_id=ing.id))


def _guardar_precio_lote(lote, form):
    """Lee el precio (unitario o total) y se lo pone al lote. Devuelve (ok, mensaje)."""
    unit, total = _num(form.get('precio_unitario')), _num(form.get('precio_total'))
    if (unit is None or unit <= 0) and total is not None and total > 0:
        unit = total / float(lote.cantidad_inicial or 1)
    if unit is None or unit <= 0:
        return False, 'Escribe el precio (unitario o total) con IGV.'
    correccion = lote.costo_unitario is not None
    motivo = ' '.join((form.get('motivo') or '').split())[:200]
    if correccion and session.get('role') != 'admin':
        return False, 'Solo Gerencia puede corregir un precio que ya estaba puesto.'
    if correccion and len(motivo) < 5:
        return False, 'Escribe el motivo de la corrección (queda en la auditoría).'
    moneda = 'USD' if (form.get('moneda') or '').upper() == 'USD' else ('PEN' if form.get('moneda') else None)
    ahora = hora_peru()
    try:
        anterior = lote.costo_unitario
        consumido, n_sal = _poner_precio_lote(lote, unit, ahora, moneda=moneda, motivo=motivo,
                                              concepto='AJUSTE_COSTO' if correccion else 'VALORIZACION')
        sim = MONEDAS_INSUMOS.get(lote.moneda or 'PEN', 'S/')
        registrar_log(f"{'Corrigió' if correccion else 'Puso'} el precio del lote #{lote.id} de {lote.insumo.codigo} "
                      f"({EMPRESAS_INSUMOS[lote.empresa]['corto']}): {(sim + ' ' + format(anterior, ',.4f')) if anterior is not None else 'sin precio'} → "
                      f"{sim} {unit:,.4f}{(' · ' + motivo) if motivo else ''}", 'bi-tag', 'text-success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo guardar el precio del lote de insumos")
        return False, f'No se pudo guardar el precio: {e}'
    return True, (f'Precio guardado: {sim} {unit:,.4f} por unidad (lote #{lote.id}).'
                  + (f' Se recalcularon {n_sal} salida(s) que ya habían sacado {_cant_txt(consumido)} und de este lote.' if n_sal else ''))


@app.route('/insumos/ingresos/<int:ingreso_id>/precio', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_ingreso_precio(ingreso_id):
    """Completa el precio de un ítem que entró con PRECIO PENDIENTE (cuando ya se tiene la factura). El lote toma ese precio
    y TODO lo que ya salió de él se recalcula (las salidas y el gasto por área quedan con el precio real)."""
    ing = InsumoIngreso.query.get_or_404(ingreso_id)
    destino = url_for('insumos_ingreso_detalle', ingreso_id=ing.id)
    if ing.estado != 'REGISTRADO':
        flash('⛔ El ingreso está anulado.')
        return redirect(destino)
    det = InsumoIngresoDetalle.query.get(request.form.get('detalle_id', type=int) or 0)
    lote = InsumoLote.query.filter_by(ingreso_detalle_id=det.id, estado='ACTIVO').first() if det and det.ingreso_id == ing.id else None
    if not lote:
        flash('⛔ No se encontró el lote de ese ítem.')
        return redirect(destino)
    ok, msg = _guardar_precio_lote(lote, request.form)
    flash(('✅ ' if ok else '⛔ ') + msg)
    return redirect(destino)


@app.route('/insumos/lote/<int:lote_id>/precio', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_lote_precio(lote_id):
    """Poner el precio a un lote SIN PRECIO (Almacén, Logística, Gerencia) o corregir el de un lote (solo Gerencia, con motivo)."""
    lote = InsumoLote.query.get_or_404(lote_id)
    destino = request.form.get('volver') or url_for('insumos_ficha', insumo_id=lote.insumo_id, empresa=lote.empresa)
    if not destino.startswith('/'):
        destino = url_for('insumos_ficha', insumo_id=lote.insumo_id, empresa=lote.empresa)
    if lote.estado != 'ACTIVO':
        flash('⛔ Ese lote está anulado.')
        return redirect(destino)
    ok, msg = _guardar_precio_lote(lote, request.form)
    flash(('✅ ' if ok else '⛔ ') + msg)
    return redirect(destino)


@app.route('/insumos/ingresos/<int:ingreso_id>/factura', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_ingreso_factura(ingreso_id):
    """Pone (o corrige) el N° de factura de un ingreso que se registró sin factura."""
    ing = InsumoIngreso.query.get_or_404(ingreso_id)
    destino = url_for('insumos_ingreso_detalle', ingreso_id=ing.id)
    numero = ' '.join((request.form.get('numero_factura') or '').split()).upper()[:50]
    if not numero:
        flash('⛔ Escribe el número de factura.')
        return redirect(destino)
    repetido = _factura_insumo_repetida(ing.empresa, numero, {'ruc': ing.ruc or '', 'razon_social': ing.razon_social or ''})
    if repetido and repetido.id != ing.id:
        flash(f'⛔ La factura {numero} ya está registrada en el ingreso #{repetido.id}.')
        return redirect(destino)
    anterior = ing.numero_factura
    ing.numero_factura = numero
    for m in InsumoMovimiento.query.filter_by(ingreso_id=ing.id, concepto='COMPRA').all():
        m.referencia = f'Factura {numero}'[:120]
    registrar_log(f"{'Corrigió' if anterior else 'Agregó'} el N° de factura del ingreso de insumos #{ing.id}: {numero}"
                  + (f' (antes {anterior})' if anterior else ''), 'bi-receipt', 'text-info')
    db.session.commit()
    flash(f'✅ Factura {numero} guardada en el ingreso #{ing.id}.')
    return redirect(destino)


@app.route('/insumos/ingresos/<int:ingreso_id>/anular', methods=['POST'])
@_ruta_insumos(solo_admin=True)
def insumos_ingreso_anular(ingreso_id):
    """Gerencia: anula un ingreso mal registrado. Solo si su cantidad sigue en stock (no se consumió)."""
    ing = InsumoIngreso.query.get_or_404(ingreso_id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:255]
    destino = url_for('insumos_ingreso_detalle', ingreso_id=ing.id)
    if ing.estado != 'REGISTRADO':
        flash('Este ingreso ya estaba anulado.')
        return redirect(destino)
    if len(motivo) < 5:
        flash('⛔ Escribe el motivo de la anulación.')
        return redirect(destino)
    ahora = hora_peru()
    mon = ing.moneda if ing.moneda in ('PEN', 'USD') else 'PEN'
    # qué sale de cada lote: el lote de esa compra tiene que estar COMPLETO (no se sacó nada de él).
    # Los ingresos de antes de pasar a lotes se descuentan del "saldo anterior" en la misma moneda.
    plan = []
    for d in ing.detalles:
        lote = InsumoLote.query.filter_by(ingreso_detalle_id=d.id, estado='ACTIVO').first()
        if lote:
            if float(lote.cantidad_restante or 0) + 1e-9 < float(lote.cantidad_inicial or 0):
                flash(f'⛔ No se puede anular: de {d.insumo.codigo} ya salió parte de este lote '
                      f'(quedan {_cant_txt(lote.cantidad_restante)} de {_cant_txt(lote.cantidad_inicial)}). Anula primero esas salidas.')
                return redirect(destino)
            plan.append((d, [(lote, float(lote.cantidad_restante))]))
            continue
        iniciales = [l for l in _lotes_activos(d.insumo_id, ing.empresa) if l.origen == 'INICIAL' and (l.moneda or 'PEN') == mon]
        falta, partes = d.cantidad, []
        for l in iniciales:
            toma = min(float(l.cantidad_restante), falta)
            if toma > 1e-9:
                partes.append((l, toma))
                falta -= toma
        if falta > 1e-6:
            flash(f'⛔ No se puede anular: de {d.insumo.codigo} ya salió parte de lo ingresado.')
            return redirect(destino)
        plan.append((d, partes))
    for d, partes in plan:
        st = _stock_de(d.insumo_id, ing.empresa)
        for lote, cant in partes:
            antes = float(st.stock_actual or 0)
            lote.cantidad_restante = round(float(lote.cantidad_restante) - cant, 6)
            if lote.ingreso_detalle_id == d.id:
                lote.estado = 'ANULADO'
            _sincronizar_stock(st)
            db.session.add(InsumoMovimiento(
                empresa=ing.empresa, insumo_id=d.insumo_id, fecha=ahora, tipo='SALIDA', concepto='ANULACION', cantidad=cant,
                costo_unitario=lote.costo_unitario or 0, costo_total=round(cant * (lote.costo_unitario or 0), 2), stock_antes=antes,
                stock_despues=st.stock_actual, **_datos_mov_lote(lote), referencia=f'Anulación ingreso #{ing.id}', ingreso_id=ing.id,
                observacion=motivo, user_id=session.get('user_id'), fecha_registro=ahora))
        d.sin_costo_restante = 0.0
    ing.estado, ing.anulado_por, ing.fecha_anulacion, ing.motivo_anulacion = 'ANULADO', session.get('nombre', ''), ahora, motivo
    try:
        for o in OrdenCompra.query.filter(OrdenCompra.insumo_ingreso_id == ing.id).all():
            o.insumo_ingreso_id = None
            _oc_evento(o, 'INSUMOS', f"Se anuló el ingreso #{ing.id} en Insumos: la orden vuelve a quedar pendiente de ingresar")
    except Exception:
        app.logger.exception("No se pudo liberar la OC del ingreso anulado")
    registrar_log(f"Anuló el ingreso de insumos #{ing.id}: {motivo}", 'bi-x-octagon', 'text-danger')
    db.session.commit()
    flash('Ingreso anulado: su lote se quitó del stock y ya no cuenta en los totales.')
    return redirect(destino)


# ---------------------------- SALIDAS ----------------------------
def _siguiente_numero_salida(empresa):
    ultimo = db.session.query(func.max(InsumoSalida.numero)).filter(InsumoSalida.empresa == empresa).scalar()
    return int(ultimo or 0) + 1


@app.route('/insumos/salida/nueva')
@_ruta_insumos(editar=True)
def insumos_salida_nueva():
    empresa = _empresa_param()
    trabajadores = InsumoTrabajador.query.filter_by(activo=True).order_by(InsumoTrabajador.nombre).all()
    return render_template('insumos_salida_form.html', empresa=empresa, empresas=EMPRESAS_INSUMOS,
                           insumos_json={e: _datos_formulario_insumos(e) for e in EMPRESAS_INSUMOS},
                           trabajadores=trabajadores, areas=InsumoArea.query.filter_by(activo=True).order_by(InsumoArea.nombre).all(),
                           motivos=_catalogo_insumos('INSUMO_MOTIVO'), hoy=hora_peru().date(), seccion='salida',
                           categorias_filtro=_categorias_insumos(),
                           siguiente={e: _siguiente_numero_salida(e) for e in EMPRESAS_INSUMOS})


def _guardar_firma_png(data_url, salida, claves):
    """Firma dibujada en pantalla (data:image/png;base64,...) -> S3. Devuelve la clave o lanza ValueError."""
    if not data_url.startswith('data:image/png;base64,'):
        raise ValueError('Firma no válida.')
    datos = base64.b64decode(data_url.split(',', 1)[1], validate=True)
    if not datos.startswith(b'\x89PNG\r\n\x1a\n') or len(datos) > 400 * 1024:
        raise ValueError('Firma no válida o demasiado grande.')
    s3_key = f"insumos/{salida.empresa.lower()}/firmas/salida_{salida.id}_{uuid.uuid4().hex[:8]}.png"
    s3_client.upload_fileobj(io.BytesIO(datos), S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': 'image/png'})
    claves.append(s3_key)
    return s3_key


@app.route('/insumos/salida/guardar', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_salida_guardar():
    f = request.form
    volver = url_for('insumos_salida_nueva', empresa=f.get('empresa'))
    empresa = (f.get('empresa') or '').upper()
    if empresa not in EMPRESAS_INSUMOS:
        flash('⛔ Elige la empresa de la salida.')
        return redirect(volver)
    fecha, err = _fecha_movimiento_insumo(f.get('fecha'))
    if err:
        flash(f'⛔ {err}')
        return redirect(volver)

    def trab(nombre, obligatorio=False, jefe=False):
        t = InsumoTrabajador.query.get(f.get(nombre, type=int)) if f.get(nombre, type=int) else None
        if t and not t.activo:
            t = None
        if jefe and t and not t.es_jefe:
            t = None
        return t
    solicitado, recibido, autorizado, a_cuenta = trab('solicitado_por_id'), trab('recibido_por_id'), trab('autorizado_por_id', jefe=True), trab('a_cuenta_de_id')
    area = InsumoArea.query.get(f.get('area_id', type=int)) if f.get('area_id', type=int) else None
    motivo = (f.get('motivo') or '').strip()
    errores = []
    if not solicitado:
        errores.append('Elige quién solicita.')
    if not area or not area.activo:
        errores.append('Elige el área (sección) a la que se carga el gasto.')
    if motivo not in {v.valor for v in _catalogo_insumos('INSUMO_MOTIVO')}:
        errores.append('Elige para qué es necesario (motivo).')
    if f.get('autorizado_por_id') and not autorizado:
        errores.append('Quien autoriza debe estar marcado como jefe de área.')
    items, pedidos = [], {}
    for n, (iid, sol, desp) in enumerate(zip(f.getlist('insumo_id[]'), f.getlist('cantidad_solicitada[]'),
                                             f.getlist('cantidad_despachada[]')), start=1):
        if not (iid or '').strip():
            continue
        ins = Insumo.query.get(int(iid)) if iid.isdigit() else None
        cs, cd = _num(sol), _num(desp)
        if not ins:
            errores.append(f'Fila {n}: el insumo no existe.')
            continue
        if cs is None or cs <= 0:
            errores.append(f'Fila {n} ({ins.codigo}): la cantidad solicitada debe ser mayor a 0.')
            continue
        cd = cs if cd is None else cd
        if cd <= 0 or cd > cs + 1e-9:
            errores.append(f'Fila {n} ({ins.codigo}): lo despachado debe ser mayor a 0 y no más de lo solicitado.')
            continue
        pedidos[ins.id] = pedidos.get(ins.id, 0) + cd
        items.append({'ins': ins, 'cs': cs, 'cd': cd})
    for iid, total_pedido in pedidos.items():
        st = _stock_de(iid, empresa, crear=False)
        disponible = float(st.stock_actual or 0) if st else 0
        if total_pedido > disponible + 1e-9:
            ins = Insumo.query.get(iid)
            errores.append(f'{ins.codigo}: solo hay {_cant_txt(disponible)} {ins.unidad or ""} en {EMPRESAS_INSUMOS[empresa]["corto"]} '
                           f'(pides {_cant_txt(total_pedido)}).')
    if not items and not errores:
        errores.append('Agrega al menos un insumo.')
    if errores:
        flash('⛔ ' + ' '.join(errores))
        return redirect(volver)

    ahora = hora_peru()
    for intento in range(3):
        claves = []
        try:
            sal = InsumoSalida(
                empresa=empresa, numero=_siguiente_numero_salida(empresa), fecha=fecha, area_id=area.id,
                solicitado_por_id=solicitado.id, recibido_por_id=(recibido or solicitado).id,
                autorizado_por_id=autorizado.id if autorizado else None, a_cuenta_de_id=a_cuenta.id if a_cuenta else None,
                motivo=motivo[:100], motivo_detalle=' '.join((f.get('motivo_detalle') or '').split())[:300] or None,
                estado='REGISTRADA', user_id=session.get('user_id'), fecha_registro=ahora)
            db.session.add(sal)
            db.session.flush()
            total, total_usd = 0, 0
            for it in items:
                st = _stock_de(it['ins'].id, empresa, crear=False)
                # PEPS: sale primero del lote más antiguo; cada parte con el precio REAL de su lote (S/ o US$, sin convertir).
                # Si un lote todavía no tiene precio, esa parte sale "sin precio" y se recalcula al ponerle el precio al lote.
                antes, partes = _sacar_de_lotes(st, it['cd'])
                st.ultima_salida = fecha
                t = _totales_partes(partes)
                total += t['t_pen']
                total_usd += t['t_usd']
                det = InsumoSalidaDetalle(salida_id=sal.id, insumo_id=it['ins'].id, cantidad_solicitada=it['cs'], cantidad_despachada=it['cd'],
                                          unidad=it['ins'].unidad, ubicacion=st.almacen, stock_antes=antes, stock_despues=st.stock_actual)
                _aplicar_totales_detalle(det, t)
                db.session.add(det)
                db.session.flush()
                for lote, c, u, m_ in partes:
                    db.session.add(InsumoSalidaLote(salida_id=sal.id, salida_detalle_id=det.id, lote_id=lote.id, cantidad=c,
                                                    costo_unitario=u, moneda=m_))
                    db.session.add(InsumoMovimiento(
                        empresa=empresa, insumo_id=it['ins'].id, fecha=fecha, tipo='SALIDA', concepto='CONSUMO', cantidad=c,
                        costo_unitario=u or 0, costo_total=round(c * (u or 0), 2), stock_antes=antes, stock_despues=st.stock_actual,
                        **_datos_mov_lote(lote), referencia=f'Consumo N° {sal.numero:06d} · {area.nombre}'[:120],
                        observacion='Sin precio (lote con precio pendiente): se recalcula al ponerle el precio' if u is None else None,
                        salida_id=sal.id, area_id=area.id, user_id=session.get('user_id'), fecha_registro=ahora))
            sal.total_costo = round(total, 2)
            sal.total_costo_usd = round(total_usd, 2)
            firma = f.get('firma_png') or ''
            if firma:
                sal.firma_s3_key = _guardar_firma_png(firma, sal, claves)
                sal.firma_fecha, sal.firma_por = ahora, (recibido or solicitado).nombre
            registrar_log(f"Salida de insumos {EMPRESAS_INSUMOS[empresa]['corto']} N° {sal.numero:06d} para {area.nombre} "
                          f"({_montos_txt(sal.total_costo, sal.total_costo_usd)})", 'bi-box-arrow-up', 'text-danger')
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            _borrar_de_s3(claves)
            if intento == 2:
                flash('⛔ Otro usuario registró una salida al mismo tiempo. Vuelve a intentarlo.')
                return redirect(volver)
        except Exception as e:
            db.session.rollback()
            _borrar_de_s3(claves)
            app.logger.exception("No se pudo guardar la salida de insumos")
            flash(f'⛔ No se pudo guardar la salida (no se registró nada): {e}')
            return redirect(volver)
    flash(f'✅ Salida N° {sal.numero:06d} registrada ({_montos_txt(sal.total_costo, sal.total_costo_usd)} para {area.nombre}).')
    return redirect(url_for('insumos_salida_detalle', salida_id=sal.id))


@app.route('/insumos/salidas')
@_ruta_insumos()
def insumos_salidas():
    empresa = request.args.get('empresa', 'TODAS')
    q = InsumoSalida.query
    if empresa in EMPRESAS_INSUMOS:
        q = q.filter(InsumoSalida.empresa == empresa)
    area_id = request.args.get('area_id', type=int)
    if area_id:
        q = q.filter(InsumoSalida.area_id == area_id)
    trabajador_id = request.args.get('trabajador_id', type=int)
    desde = _fecha_param('desde', None)
    hasta = _fecha_param('hasta', None)
    if desde:
        q = q.filter(InsumoSalida.fecha >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        q = q.filter(InsumoSalida.fecha < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
    salidas = q.order_by(InsumoSalida.fecha.desc(), InsumoSalida.id.desc()).limit(500).all()
    if trabajador_id:
        salidas = [s for s in salidas if trabajador_id in (s.solicitado_por_id, s.recibido_por_id, s.a_cuenta_de_id)]
    categoria = request.args.get('categoria', '')
    total_categoria = total_categoria_usd = None
    if categoria:
        salidas = [s for s in salidas if any((d.insumo.categoria or '') == categoria for d in s.detalles)]
        total_categoria = sum(d.costo_total or 0 for s in salidas if s.estado == 'REGISTRADA'
                              for d in s.detalles if (d.insumo.categoria or '') == categoria)
        total_categoria_usd = sum(d.costo_total_usd or 0 for s in salidas if s.estado == 'REGISTRADA'
                                  for d in s.detalles if (d.insumo.categoria or '') == categoria)
    total = sum(s.total_costo or 0 for s in salidas if s.estado == 'REGISTRADA')
    total_usd = sum(s.total_costo_usd or 0 for s in salidas if s.estado == 'REGISTRADA')
    return render_template('insumos_salidas.html', salidas=salidas, total=total, total_usd=total_usd, total_categoria_usd=total_categoria_usd, empresa=empresa, empresas=EMPRESAS_INSUMOS,
                           areas=InsumoArea.query.order_by(InsumoArea.nombre).all(), area_id=area_id,
                           trabajadores=InsumoTrabajador.query.order_by(InsumoTrabajador.nombre).all(), trabajador_id=trabajador_id,
                           desde=desde, hasta=hasta, categoria=categoria, total_categoria=total_categoria,
                           categorias_filtro=_categorias_insumos(), seccion='salidas')


@app.route('/insumos/salidas/<int:salida_id>')
@_ruta_insumos()
def insumos_salida_detalle(salida_id):
    sal = InsumoSalida.query.get_or_404(salida_id)
    docs = InsumoDocumento.query.filter_by(salida_id=sal.id).order_by(InsumoDocumento.id).all()
    lotes_det = {}      # de qué lote salió cada línea y a qué precio (PEPS)
    for f_ in InsumoSalidaLote.query.filter_by(salida_id=sal.id).order_by(InsumoSalidaLote.id).all():
        lotes_det.setdefault(f_.salida_detalle_id, []).append(f_)
    return render_template('insumos_salida_detalle.html', sal=sal, docs=docs, empresas=EMPRESAS_INSUMOS, seccion='salidas', lotes_det=lotes_det,
                           puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN)


@app.route('/insumos/salidas/<int:salida_id>/firmar', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_salida_firmar(salida_id):
    sal = InsumoSalida.query.get_or_404(salida_id)
    if sal.estado != 'REGISTRADA':
        return {'status': 'error', 'msg': 'La salida está anulada.'}
    claves, anterior = [], sal.firma_s3_key
    try:
        sal.firma_s3_key = _guardar_firma_png(request.form.get('firma_png') or '', sal, claves)
        sal.firma_fecha, sal.firma_por = hora_peru(), (sal.recibido_por.nombre if sal.recibido_por else '')
        registrar_log(f"Firmó la recepción de la salida de insumos N° {sal.numero:06d}", 'bi-pen', 'text-info')
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return {'status': 'error', 'msg': str(e)}
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        return {'status': 'error', 'msg': f'No se pudo guardar la firma: {e}'}
    if anterior:
        _borrar_de_s3([anterior])
    return {'status': 'success'}


@app.route('/insumos/salidas/<int:salida_id>/firma')
@_ruta_insumos()
def insumos_salida_firma(salida_id):
    sal = InsumoSalida.query.get_or_404(salida_id)
    if not sal.firma_s3_key:
        return "Sin firma", 404
    obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=sal.firma_s3_key)
    return send_file(io.BytesIO(obj['Body'].read()), mimetype='image/png')


@app.route('/insumos/salidas/<int:salida_id>/documento', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_salida_documento(salida_id):
    """El formato impreso y firmado a mano (PDF o foto)."""
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    sal = InsumoSalida.query.get_or_404(salida_id)
    archivo = request.files.get('archivo')
    ok, info = _validar_documento_kardex(archivo)
    if not ok:
        flash(f'⛔ {info}')
        return redirect(url_for('insumos_salida_detalle', salida_id=sal.id))
    claves = []
    try:
        _subir_doc_insumo(f"{sal.empresa.lower()}/salidas/{sal.id}", archivo, info, 'SALIDA_FIRMADA', claves, salida_id=sal.id)
        registrar_log(f"Subió el formato firmado de la salida de insumos N° {sal.numero:06d}", 'bi-paperclip', 'text-info')
        db.session.commit()
        flash('✅ Documento firmado adjuntado.')
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        flash(f'⛔ No se pudo subir el documento: {e}')
    return redirect(url_for('insumos_salida_detalle', salida_id=sal.id))


@app.route('/insumos/documento/<int:doc_id>')
@_ruta_insumos()
def insumos_documento(doc_id):
    doc = InsumoDocumento.query.get_or_404(doc_id)
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception as e:
        return f"<h3>No se pudo recuperar el documento</h3><p>{html.escape(str(e))}</p>", 404
    ext = doc.s3_key.rsplit('.', 1)[-1].lower()
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=doc.content_type or 'application/octet-stream',
                     as_attachment=request.args.get('download') == '1',
                     download_name=secure_filename(f"{doc.tipo.lower()}_{doc.ingreso_id or doc.salida_id}_{doc.id}.{ext}"))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@app.route('/insumos/salidas/<int:salida_id>/anular', methods=['POST'])
@_ruta_insumos(solo_admin=True)
def insumos_salida_anular(salida_id):
    """Gerencia: anula una salida mal registrada; lo despachado vuelve a los mismos lotes de los que salió (mismo precio)."""
    sal = InsumoSalida.query.get_or_404(salida_id)
    destino = url_for('insumos_salida_detalle', salida_id=sal.id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:255]
    if sal.estado != 'REGISTRADA':
        flash('Esta salida ya estaba anulada.')
        return redirect(destino)
    if len(motivo) < 5:
        flash('⛔ Escribe el motivo de la anulación.')
        return redirect(destino)
    ahora = hora_peru()
    for d in sal.detalles:
        st = _stock_de(d.insumo_id, sal.empresa)
        filas = InsumoSalidaLote.query.filter_by(salida_detalle_id=d.id).all()
        if filas:
            # lo despachado vuelve a LOS MISMOS LOTES de los que salió (con su precio, o sin precio si todavía no lo tienen)
            for f_ in filas:
                lote = f_.lote
                antes = float(st.stock_actual or 0)
                lote.cantidad_restante = round(float(lote.cantidad_restante or 0) + f_.cantidad, 6)
                _sincronizar_stock(st)
                db.session.add(InsumoMovimiento(
                    empresa=sal.empresa, insumo_id=d.insumo_id, fecha=ahora, tipo='ENTRADA', concepto='ANULACION',
                    cantidad=f_.cantidad, costo_unitario=lote.costo_unitario or 0, costo_total=round(f_.cantidad * (lote.costo_unitario or 0), 2),
                    stock_antes=antes, stock_despues=st.stock_actual, **_datos_mov_lote(lote),
                    referencia=f'Anulación consumo N° {sal.numero:06d}', salida_id=sal.id, area_id=sal.area_id, observacion=motivo,
                    user_id=session.get('user_id'), fecha_registro=ahora))
            continue
        # salida de antes de pasar a lotes: vuelve como un lote "devolución" con el costo con el que salió
        c_usd, c_sc = float(d.cantidad_usd or 0), float(d.cantidad_sin_costo or 0)
        for mon, cant, unit in (('PEN', round((d.cantidad_despachada or 0) - c_usd - c_sc, 6), d.costo_unitario or 0),
                                ('USD', c_usd, d.costo_unitario_usd or 0), ('PEN', c_sc, None)):
            if cant <= 1e-9:
                continue
            lote, antes = _nuevo_lote(st, cant, unit, mon, sal.fecha, 'DEVOLUCION', documento=f'Anulación consumo N° {sal.numero:06d}')
            db.session.add(InsumoMovimiento(
                empresa=sal.empresa, insumo_id=d.insumo_id, fecha=ahora, tipo='ENTRADA', concepto='ANULACION',
                cantidad=cant, costo_unitario=unit or 0, costo_total=round(cant * (unit or 0), 2), stock_antes=antes,
                stock_despues=st.stock_actual, **_datos_mov_lote(lote),
                referencia=f'Anulación consumo N° {sal.numero:06d}', salida_id=sal.id, area_id=sal.area_id, observacion=motivo,
                user_id=session.get('user_id'), fecha_registro=ahora))
    sal.estado, sal.anulado_por, sal.fecha_anulacion, sal.motivo_anulacion = 'ANULADA', session.get('nombre', ''), ahora, motivo
    registrar_log(f"Anuló la salida de insumos N° {sal.numero:06d}: {motivo}", 'bi-x-octagon', 'text-danger')
    db.session.commit()
    flash('Salida anulada: lo despachado volvió al stock y ya no cuenta en el gasto del área.')
    return redirect(destino)


_LOGOS_PDF_INSUMOS = {}


def _recortar_bordes(im):
    """Quita el margen blanco/transparente alrededor de la imagen (los logos suelen traer mucho)."""
    from PIL import Image, ImageChops
    rgba = im.convert('RGBA')
    fondo = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
    plano = Image.alpha_composite(fondo, rgba).convert('RGB')
    caja = ImageChops.difference(plano, Image.new('RGB', plano.size, (255, 255, 255))).convert('L').point(lambda v: 255 if v > 18 else 0).getbbox()
    if not caja:
        return im
    margen = max(2, round(0.02 * max(im.size)))
    caja = (max(0, caja[0] - margen), max(0, caja[1] - margen), min(im.size[0], caja[2] + margen), min(im.size[1], caja[3] + margen))
    return im.crop(caja)


def _imagen_pdf(datos, alto_px, ancho_max_px, recortar=False):
    """Imagen reducida (PNG en data URI) + su ancho/alto para xhtml2pdf, que necesita los dos."""
    from PIL import Image
    im = Image.open(io.BytesIO(datos))
    im.load()
    if recortar:
        im = _recortar_bordes(im)
    w, h = im.size
    ancho = min(ancho_max_px, alto_px * w / h) if h else ancho_max_px
    alto = ancho * h / w if w else alto_px
    if im.mode not in ('RGB', 'RGBA'):
        im = im.convert('RGBA')
    im.thumbnail((int(ancho * 3), int(alto * 3)))       # 3x para que se vea nítido al imprimir
    buf = io.BytesIO()
    im.save(buf, format='PNG', optimize=True)
    return {'uri': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(), 'ancho': round(ancho), 'alto': round(alto)}


def _logo_pdf_insumos(empresa):
    if empresa not in _LOGOS_PDF_INSUMOS:
        ruta = os.path.join(app.root_path, 'static', 'img', EMPRESAS_INSUMOS[empresa]['logo'])
        try:
            with open(ruta, 'rb') as fh:
                _LOGOS_PDF_INSUMOS[empresa] = _imagen_pdf(fh.read(), 92, 215, recortar=True)
        except Exception:
            app.logger.exception("No se pudo preparar el logo de %s para el PDF", empresa)
            return None
    return _LOGOS_PDF_INSUMOS[empresa]


@app.route('/insumos/salidas/<int:salida_id>/pdf')
@_ruta_insumos()
def insumos_salida_pdf(salida_id):
    sal = InsumoSalida.query.get_or_404(salida_id)
    emp = EMPRESAS_INSUMOS[sal.empresa]
    firma = None
    if sal.firma_s3_key:
        try:
            obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=sal.firma_s3_key)
            firma = _imagen_pdf(obj['Body'].read(), 46, 190)
        except Exception:
            app.logger.exception("No se pudo leer la firma de la salida %s", sal.id)
    cfg = {k: (SystemConfig.query.get(f'insumos_formato_{k}_{sal.empresa}').value
               if SystemConfig.query.get(f'insumos_formato_{k}_{sal.empresa}') else v) for k, v in FORMATO_SALIDA_DEF.items()}
    filas = list(sal.detalles) + [None] * max(0, 10 - len(sal.detalles))
    html_renderizado = render_template('pdf_insumo_salida.html', sal=sal, emp=emp, logo=_logo_pdf_insumos(sal.empresa),
                                       firma=firma, formato=cfg, filas=filas)
    return _generar_respuesta_pdf(html_renderizado, f"salida_{emp['corto'].replace(' ', '')}_{sal.numero:06d}.pdf",
                                  "el PDF de la salida de materiales")


# ---------------------------- KARDEX VALORIZADO ----------------------------
@app.route('/insumos/kardex')
@_ruta_insumos()
def insumos_kardex():
    empresa = _empresa_param()
    insumo_id = request.args.get('insumo_id', type=int)
    categoria = request.args.get('categoria', '')
    desde, hasta = _fecha_param('desde', None), _fecha_param('hasta', None)
    todos = Insumo.query.order_by(Insumo.codigo).all()
    lista = [i for i in todos if not categoria or (i.categoria or '') == categoria]
    if insumo_id and categoria and insumo_id not in {i.id for i in lista}:
        insumo_id = None
    q = InsumoMovimiento.query.filter(InsumoMovimiento.empresa == empresa)
    concepto = request.args.get('concepto', '')
    if concepto in ('COMPRA', 'CONSUMO', 'ANULACION', 'AJUSTE_COSTO', 'IMPORTACION', 'VALORIZACION'):
        q = q.filter(InsumoMovimiento.concepto == concepto)
    else:
        concepto = ''
    if insumo_id:
        q = q.filter(InsumoMovimiento.insumo_id == insumo_id)
    elif categoria:
        q = q.filter(InsumoMovimiento.insumo_id.in_([i.id for i in lista] or [0]))
    if desde:
        q = q.filter(InsumoMovimiento.fecha >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        q = q.filter(InsumoMovimiento.fecha < datetime.combine(hasta, datetime.min.time()) + timedelta(days=1))
    todos_movs = q.order_by(InsumoMovimiento.fecha.desc(), InsumoMovimiento.id.desc()).all()
    # ANULADOS: el ingreso o la salida anulada y su movimiento de anulación NO cuentan en los totales (se cancelan entre sí)
    ing_anul = {i for (i,) in db.session.query(InsumoIngreso.id).filter(
        InsumoIngreso.id.in_({m.ingreso_id for m in todos_movs if m.ingreso_id} or {0}), InsumoIngreso.estado == 'ANULADO').all()}
    sal_anul = {i for (i,) in db.session.query(InsumoSalida.id).filter(
        InsumoSalida.id.in_({m.salida_id for m in todos_movs if m.salida_id} or {0}), InsumoSalida.estado == 'ANULADA').all()}
    anulado = {m.id for m in todos_movs if m.concepto == 'ANULACION' or (m.ingreso_id in ing_anul and m.tipo in ('ENTRADA', 'SALIDA'))
               or (m.salida_id in sal_anul and m.tipo in ('ENTRADA', 'SALIDA'))}
    ocultar = request.args.get('ocultar') == '1'
    validos = [m for m in todos_movs if m.id not in anulado]
    movs = (validos if ocultar else todos_movs)[:500]
    total_movs = len(validos) if ocultar else len(todos_movs)
    entradas = sum(m.costo_total or 0 for m in validos if m.tipo == 'ENTRADA' and (m.moneda or 'PEN') not in ('USD', 'SC'))
    salidas = sum(m.costo_total or 0 for m in validos if m.tipo == 'SALIDA' and (m.moneda or 'PEN') not in ('USD', 'SC'))
    entradas_usd = sum(m.costo_total or 0 for m in validos if m.tipo == 'ENTRADA' and m.moneda == 'USD')
    salidas_usd = sum(m.costo_total or 0 for m in validos if m.tipo == 'SALIDA' and m.moneda == 'USD')
    sc_ent = sum(m.cantidad or 0 for m in validos if m.tipo == 'ENTRADA' and m.moneda == 'SC')
    sc_sal = sum(m.cantidad or 0 for m in validos if m.tipo == 'SALIDA' and m.moneda == 'SC')
    lotes_ficha = _lotes_activos(insumo_id, empresa) if insumo_id else []
    insumo = Insumo.query.get(insumo_id) if insumo_id else None
    stock = _stock_de(insumo_id, empresa, crear=False) if insumo_id else None
    ids_ing = {m.ingreso_id for m in movs if m.ingreso_id}
    ingresos = {i.id: i for i in InsumoIngreso.query.filter(InsumoIngreso.id.in_(list(ids_ing) or [0])).all()}
    # la OC de cada compra y los documentos (de la orden y del ingreso): ver y descargar desde el Kardex
    ocs, docs_oc = _ocs_de_ingresos(list(ingresos.values()))
    docs_ing = {}
    for d in InsumoDocumento.query.filter(InsumoDocumento.ingreso_id.in_(list(ids_ing) or [0])).all():
        docs_ing.setdefault(d.ingreso_id, []).append(d)
    # compras con OC que todavía NO entran al Kardex (conformes, por registrar): ya se pueden ver con su OC
    oc_pend, docs_pend = [], {}
    try:
        _asegurar_oc()
        oc_pend = [o for o in _ordenes_pendientes_insumos(empresa)
                   if not insumo_id or any(it.insumo_id == insumo_id for it in o.items)]
        if oc_pend:
            for d in OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id.in_([o.id for o in oc_pend])).all():
                docs_pend.setdefault(d.orden_id, []).append(d)
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudieron leer las OC pendientes para el Kardex de insumos")
        oc_pend, docs_pend = [], {}
    return render_template('insumos_kardex.html', ingresos=ingresos, ocs=ocs, docs_oc=docs_oc, docs_ing=docs_ing,
                           oc_pend=oc_pend, docs_pend=docs_pend, puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN, empresa=empresa,
                           anulado=anulado, n_anulados=len(anulado), ocultar=ocultar, total_movs=total_movs, sc_ent=sc_ent, sc_sal=sc_sal,
                           lotes_ficha=lotes_ficha, empresas=EMPRESAS_INSUMOS, movs=movs, insumo=insumo, stock=stock,
                           insumos=lista, desde=desde, hasta=hasta, categoria=categoria, categorias_filtro=_categorias_insumos(),
                           puede_ajustar=session.get('role') == 'admin', concepto=concepto,
                           tot_entradas=entradas, tot_salidas=salidas, tot_entradas_usd=entradas_usd, tot_salidas_usd=salidas_usd, seccion='kardex')


