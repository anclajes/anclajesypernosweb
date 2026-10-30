# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · entregas e ingresos
# llegadas totales o parciales, conformidad, pago y factura, cuentas bancarias, cliente, ingresos pendientes e ingreso al Kardex
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- ENTREGAS (llegadas totales o parciales) ----------------------------
def _oc_entregas(orden):
    return OrdenCompraEntrega.query.filter_by(orden_id=orden.id).order_by(OrdenCompraEntrega.numero).all()


def _oc_recepcion(orden):
    """Cuánto llegó de cada ítem (todas las entregas), cuánto tiene conformidad, cuánto entró al inventario y cuánto falta."""
    entregas = _oc_entregas(orden)
    conf = {e.id: bool(e.fecha_conforme) for e in entregas}
    por_item = {}
    if entregas:
        for ei in OrdenCompraEntregaItem.query.filter(OrdenCompraEntregaItem.entrega_id.in_(list(conf))).all():
            d = por_item.setdefault(ei.item_id, {'llego': 0.0, 'conforme': 0.0, 'ingresado': 0.0})
            d['llego'] += ei.cantidad or 0
            if conf.get(ei.entrega_id):
                d['conforme'] += ei.cantidad or 0
            if ei.fecha_ingreso:
                d['ingresado'] += ei.cantidad or 0
    items = {}
    for it in orden.items:
        d = por_item.get(it.id, {'llego': 0.0, 'conforme': 0.0, 'ingresado': 0.0})
        cancelado = it.cantidad_cancelada or 0
        items[it.id] = {**{k: round(v, 4) for k, v in d.items()}, 'pedido': it.cantidad, 'cancelado': cancelado,
                        'pendiente': max(round((it.cantidad or 0) - d['llego'] - cancelado, 4), 0)}
    pendiente = round(sum(x['pendiente'] for x in items.values()), 4)
    # avance POR PRODUCTO (no se suman productos distintos): [{item, llego, pedido, pendiente, cancelado}]
    detalle = [{'item': it, **items[it.id]} for it in orden.items]
    return {'entregas': entregas, 'items': items, 'pendiente': pendiente, 'parcial': bool(entregas) and pendiente > 0,
            'detalle': detalle, 'n_items': len(detalle), 'n_completos': sum(1 for d in detalle if d['pendiente'] <= 0 and d['llego'] > 0),
            'n_faltan': sum(1 for d in detalle if d['pendiente'] > 0),
            'sin_conformar': [e for e in entregas if not e.fecha_conforme],
            'pedido': round(sum(x['pedido'] or 0 for x in items.values()), 4), 'llego': round(sum(x['llego'] for x in items.values()), 4)}


app.add_template_global(_oc_recepcion, 'oc_recepcion')


def _oc_faltan_txt(orden, rec=None):
    """'PER-001: faltan 50 UN · PLA-300: faltan 20 PZA' (cada producto con su propia unidad; nunca se suman productos distintos)."""
    rec = rec or _oc_recepcion(orden)
    partes = []
    for d in rec['detalle']:
        if d['pendiente'] > 0:
            it = d['item']
            partes.append(f"{it.codigo or it.descripcion[:30]}: faltan {_cant_txt(d['pendiente'])} {it.um or ''}".strip())
    return ' · '.join(partes)


app.add_template_global(_oc_faltan_txt, 'oc_faltan_txt')


def _oc_etapa_por_entregas(orden, rec=None):
    """En qué estado debe quedar una orden aprobada según sus entregas: por recibir, en revisión o conforme."""
    rec = rec or _oc_recepcion(orden)
    if rec['sin_conformar']:
        return 'RECIBIDA'
    if rec['entregas'] and rec['pendiente'] <= 0:
        return 'CONFORME'
    return 'APROBADA'


def _oc_revisar_ingreso_completo(orden):
    """Marca cada ítem como ingresado cuando ya entró al inventario todo lo que llegó y no falta nada por llegar,
    y la orden como 'todo ingresado' cuando está conforme y todos sus ítems lo están."""
    if orden.tipo != 'OC' or orden.destino != 'GENERAL':
        return
    rec = _oc_recepcion(orden)
    for it in orden.items:
        d = rec['items'][it.id]
        eis = [ei for e in rec['entregas'] for ei in e.items if ei.item_id == it.id and ei.fecha_ingreso]
        if d['llego'] > 0 and d['pendiente'] <= 0 and d['ingresado'] >= d['llego'] - 1e-9 and eis:
            ultimo = max(eis, key=lambda x: x.fecha_ingreso)
            if not it.fecha_ingreso:
                it.fecha_ingreso, it.ingresado_por_id = ultimo.fecha_ingreso, ultimo.ingresado_por_id
            it.sku_ingreso = ultimo.sku_ingreso or it.sku_ingreso
            it.kardex_mov_id = ultimo.kardex_mov_id or it.kardex_mov_id
            it.cantidad_kardex = sum(x.cantidad_kardex or 0 for x in eis) or it.cantidad_kardex
    completo = orden.estado == 'CONFORME' and all(rec['items'][i.id]['pendiente'] <= 0 and rec['items'][i.id]['ingresado'] >= rec['items'][i.id]['llego'] - 1e-9
                                                  for i in orden.items)
    if completo and not orden.fecha_kardex:
        orden.kardex_registrado_por_id, orden.fecha_kardex = session.get('user_id'), hora_peru()
        _oc_evento(orden, 'KARDEX', 'Todo lo recibido quedó ingresado al inventario')


def _oc_fecha_form_llegada(f, orden, destino):
    ahora = hora_peru()
    if f.get('cuando') != 'otra':
        return ahora, None
    try:
        llegada = datetime.strptime((f.get('fecha_llegada') or '').strip(), '%Y-%m-%dT%H:%M')
    except ValueError:
        return None, '⛔ Escribe la fecha y hora de llegada.'
    if llegada > ahora + timedelta(minutes=5):
        return None, '⛔ La fecha de llegada no puede ser futura.'
    if llegada.date() < orden.fecha:
        return None, '⛔ La llegada no puede ser anterior a la fecha de la orden.'
    return llegada, None


@app.route('/ordenes/<int:orden_id>/llegada', methods=['POST'])
@_ruta_oc('editar')
def oc_llegada(orden_id):
    """Logística registra una ENTREGA: todo lo que faltaba o solo una parte (cantidad por ítem), con su guía.
    Si es parcial, la orden sigue esperando el resto; cada entrega tiene su propia conformidad."""
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    orden, no = _accion_oc(orden_id, 'llegada')
    if no:
        return no
    f = request.form
    destino = url_for('oc_detalle', orden_id=orden.id)
    llegada, error = _oc_fecha_form_llegada(f, orden, destino)
    if error:
        flash(error)
        return redirect(destino)
    rec = _oc_recepcion(orden)
    modo = 'PARCIAL' if f.get('modo') == 'PARCIAL' else 'TOTAL'
    cantidades, errores = {}, []
    for it in orden.items:
        pend = rec['items'][it.id]['pendiente']
        if modo == 'TOTAL':
            q = pend
        else:
            q = _num(f.get(f'llega_{it.id}')) if (f.get(f'llega_{it.id}') or '').strip() else 0
            if q is None or q < 0:
                errores.append(f'Ítem {it.item}: la cantidad que llegó no es válida.')
                continue
            if q > pend + 1e-6:
                errores.append(f'Ítem {it.item}: llegaron {_cant_txt(q)} pero solo faltaban {_cant_txt(pend)} {it.um}. '
                               f'Si llegó de más, primero edita la orden (vuelve a Gerencia).')
                continue
        if q and q > 0:
            cantidades[it.id] = round(q, 4)
    if not errores and not cantidades:
        errores.append('Indica qué llegó: al menos un ítem con cantidad mayor a 0.')
    if errores:
        flash('⛔ No se registró la llegada. ' + ' · '.join(errores))
        return redirect(destino)
    falta = round(rec['pendiente'] - sum(cantidades.values()), 4)
    claves, viejas = [], []
    try:
        numero = (max([e.numero for e in rec['entregas']] or [0])) + 1
        guia = _limpio(f.get('numero_guia'), 60).upper() or None
        e = OrdenCompraEntrega(orden_id=orden.id, numero=numero, fecha=llegada, parcial=falta > 0, numero_guia=guia,
                               nota=' '.join((f.get('nota') or '').split())[:500] or None, recibido_por_id=session.get('user_id'),
                               fecha_registro=hora_peru())
        db.session.add(e)
        db.session.flush()
        for item_id, q in cantidades.items():
            db.session.add(OrdenCompraEntregaItem(entrega_id=e.id, item_id=item_id, cantidad=q))
        n, errores = _subir_docs_orden(orden, claves, ('GUIA', 'FACTURA', 'CERTIFICADO', 'OTRO'), viejas, entrega=e)
        if errores:
            db.session.rollback()
            _borrar_de_s3(claves)
            flash('⛔ ' + ' '.join(errores))
            return redirect(destino)
        orden.estado = 'RECIBIDA'
        orden.fecha_llegada = orden.fecha_llegada or llegada
        orden.recibido_por_id = orden.recibido_por_id or session.get('user_id')
        # los números ya guardados (por ejemplo al pagar) no se borran si aquí quedan vacíos
        orden.numero_guia = guia or orden.numero_guia
        orden.numero_factura = _limpio(f.get('numero_factura'), 60).upper() or orden.numero_factura
        orden.nota_recepcion = e.nota or orden.nota_recepcion
        por_item = {i.id: i for i in orden.items}
        detalle_items = ', '.join(f"{(por_item[i].codigo or por_item[i].descripcion[:25])} {_cant_txt(q)}" for i, q in cantidades.items())
        _oc_evento(orden, 'LLEGADA', f"Entrega {numero} ({'PARCIAL' if falta > 0 else 'completa'}) el {llegada.strftime('%d/%m/%Y %H:%M')}"
                                    + (f" · Guía {guia}" if guia else '') + f" · {detalle_items}"
                                    + (f" · {_oc_faltan_txt(orden)}" if falta > 0 else '')
                                    + (f" · {n} documento(s)" if n else '') + (f" · {e.nota}" if e.nota else ''))
        _req_notificar_orden(orden, 'OC_LLEGO', f"{_oc_codigo(orden)}: llegó la entrega {numero}" + (' (parcial)' if falta > 0 else ''))
        registrar_log(f"Registró la entrega {numero} {'parcial ' if falta > 0 else ''}de la {_oc_codigo(orden)}", 'bi-truck', 'text-info')
        db.session.commit()
        _borrar_de_s3(viejas)
    except Exception as ex:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception("No se pudo registrar la llegada de la orden")
        flash(f'⛔ No se pudo registrar la llegada (no se guardó nada): {ex}')
        return redirect(destino)
    flash(f'✅ Entrega {numero} registrada' + (f' (PARCIAL — {_oc_faltan_txt(orden)})' if falta > 0 else ' (completa)')
          + '. Revisa el material y da la CONFORMIDAD de esta entrega.')
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/conforme', methods=['POST'])
@_ruta_oc('editar')
def oc_conforme(orden_id):
    """Conformidad de UNA entrega: buen estado, cantidad y documentos (su guía o la factura). El certificado de calidad es
    opcional: en importaciones queda como pendiente, sin frenar nada. Lo conforme pasa a Ingresos pendientes.
    La orden queda CONFORME cuando ya llegó todo (o se cerró el saldo)."""
    orden, no = _accion_oc(orden_id, 'conforme')
    if no:
        return no
    f = request.form
    destino = url_for('oc_detalle', orden_id=orden.id)
    rec = _oc_recepcion(orden)
    e = next((x for x in rec['sin_conformar'] if str(x.id) == (f.get('entrega_id') or '')), None) or (rec['sin_conformar'][0] if rec['sin_conformar'] else None)
    if not e:
        flash('⛔ No hay entregas pendientes de conformidad.')
        return redirect(destino)
    faltan = [t for k, t in (('chk_estado', 'el material llegó en buen estado'), ('chk_cantidad', 'la cantidad es la correcta'),
                             ('chk_documentos', 'la guía / factura son correctas')) if f.get(k) != '1']
    if faltan:
        flash('⛔ Para dar conformidad confirma que ' + ', '.join(faltan) + '.')
        return redirect(destino)
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    claves, viejas = [], []
    try:
        n_docs, errores = _subir_docs_orden(orden, claves, ('GUIA', 'FACTURA', 'CERTIFICADO'), viejas, entrega=e)
        if errores:
            db.session.rollback()
            _borrar_de_s3(claves)
            flash('⛔ ' + ' '.join(errores))
            return redirect(destino)
        if (f.get('numero_guia') or '').strip():
            e.numero_guia = _limpio(f.get('numero_guia'), 60).upper()
            orden.numero_guia = e.numero_guia
        if (f.get('numero_factura') or '').strip():
            orden.numero_factura = _limpio(f.get('numero_factura'), 60).upper()
        db.session.flush()
        docs = OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id == orden.id).all()
        guia_ok = any(d.tipo == 'GUIA' and (d.entrega_id == e.id or (d.entrega_id is None and len(rec['entregas']) == 1)) for d in docs)
        falta = []
        if not guia_ok and not any(d.tipo == 'FACTURA' for d in docs):
            falta.append(f'la GUÍA de la entrega {e.numero} o la FACTURA')
        falta_cert = orden.requiere_certificado and not any(d.tipo == 'CERTIFICADO' for d in docs)
        if falta:
            db.session.rollback()
            _borrar_de_s3(claves)
            flash(f"⛔ Falta adjuntar {' y '.join(falta)} (PDF o foto): es obligatorio para dar la conformidad.")
            return redirect(destino)
        if n_docs:
            _oc_evento(orden, 'DOCUMENTO', f"Adjuntó {n_docs} documento(s) al dar la conformidad de la entrega {e.numero}")
    except Exception as ex:
        db.session.rollback()
        _borrar_de_s3(claves)
        flash(f'⛔ No se pudo guardar: {ex}')
        return redirect(destino)
    ahora = hora_peru()
    e.conforme_por_id, e.fecha_conforme = session.get('user_id'), ahora
    e.nota_conforme = ' '.join((f.get('nota') or '').split())[:500] or None
    db.session.flush()
    etapa = _oc_etapa_por_entregas(orden)
    orden.estado = etapa
    if etapa == 'CONFORME':
        orden.conforme_por_id, orden.fecha_conforme = session.get('user_id'), ahora
        orden.nota_conforme = e.nota_conforme or orden.nota_conforme
    _oc_evento(orden, 'CONFORME', f"Entrega {e.numero} conforme: buen estado, cantidad y documentos OK"
               + (f" · {e.nota_conforme}" if e.nota_conforme else '')
               + (' · ORDEN COMPLETA' if etapa == 'CONFORME' else (f" · por llegar: {_oc_faltan_txt(orden)}" if etapa == 'APROBADA' else '')))
    _req_notificar_orden(orden, 'OC_CONFORME', f"{_oc_codigo(orden)}: entrega {e.numero} conforme" + (' (orden completa)' if etapa == 'CONFORME' else ''))
    _oc_revisar_ingreso_completo(orden)
    registrar_log(f"Dio CONFORMIDAD a la entrega {e.numero} de la {_oc_codigo(orden)}", 'bi-check-circle-fill', 'text-success')
    db.session.commit()
    _borrar_de_s3(viejas)
    if falta_cert:
        flash('⚠️ Falta subir el CERTIFICADO DE CALIDAD de esta importación. No frena nada: súbelo apenas llegue '
              '(queda en la lista "Certificados por subir").', 'warning')
    if etapa == 'CONFORME':
        sig = ('Ahora regístralo en Insumos internos (aparece como pendiente).' if orden.destino == 'INSUMOS'
               else 'Servicio terminado: queda pendiente solo el pago.' if orden.tipo == 'OS'
               else 'Almacén lo verá en "Ingresos pendientes" para sumarlo al inventario.')
        flash(f'✅ {_oc_codigo(orden)} CONFORME (llegó todo). {sig}')
    else:
        flash(f'✅ Entrega {e.numero} conforme.' + (' Lo recibido ya está en "Ingresos pendientes" para Almacén.' if orden.tipo == 'OC' and orden.destino == 'GENERAL' else '')
              + (' La orden sigue esperando el resto.' if etapa == 'APROBADA' else ''))
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/cerrar_saldo', methods=['POST'])
@_ruta_oc('editar')
def oc_cerrar_saldo(orden_id):
    """Llegó solo una parte y el resto YA NO llegará: se cierra el saldo con motivo y la orden puede quedar conforme con lo recibido."""
    orden, no = _accion_oc(orden_id, 'cerrar_saldo')
    if no:
        return no
    destino = url_for('oc_detalle', orden_id=orden.id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:300]
    if len(motivo) < 5:
        flash('⛔ Escribe por qué no llegará el resto (queda en el historial).')
        return redirect(destino)
    rec = _oc_recepcion(orden)
    cerrados = []
    for it in orden.items:
        pend = rec['items'][it.id]['pendiente']
        if pend > 0:
            it.cantidad_cancelada = round((it.cantidad_cancelada or 0) + pend, 4)
            cerrados.append(f"{it.codigo or it.descripcion[:25]} {_cant_txt(pend)}")
    orden.saldo_cerrado_motivo = motivo
    db.session.flush()
    etapa = _oc_etapa_por_entregas(orden)
    orden.estado = etapa
    if etapa == 'CONFORME' and not orden.fecha_conforme:
        orden.conforme_por_id, orden.fecha_conforme = session.get('user_id'), hora_peru()
    _oc_evento(orden, 'SALDO_CERRADO', f"No llegará el resto ({', '.join(cerrados)}): {motivo}")
    _req_notificar_orden(orden, 'OC_SALDO', f"{_oc_codigo(orden)}: se cerró lo que faltaba llegar ({motivo})")
    _oc_revisar_ingreso_completo(orden)
    db.session.commit()
    flash('✅ Saldo cerrado: la orden se completa con lo que llegó.' + (' Queda CONFORME.' if etapa == 'CONFORME' else ''))
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/observacion', methods=['POST'])
@_ruta_oc('editar')
def oc_observacion(orden_id):
    orden, no = _accion_oc(orden_id, 'observar')
    if no:
        return no
    texto = ' '.join((request.form.get('texto') or '').split())[:500]
    if len(texto) < 3:
        flash('⛔ Escribe la observación.')
    else:
        _oc_evento(orden, 'OBSERVACION', texto)
        db.session.commit()
        flash('Observación registrada en el historial de la orden.')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/documento', methods=['POST'])
@_ruta_oc('editar')
def oc_documento(orden_id):
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    orden, no = _accion_oc(orden_id, 'documentos')
    if no:
        return no
    # Desde la lista "Certificados por subir" se vuelve a la lista (no al detalle de la orden)
    destino = url_for('oc_certificados') if request.form.get('volver') == 'certificados' else url_for('oc_detalle', orden_id=orden.id)
    tipo = (request.form.get('tipo') or 'OTRO').upper()
    tipo = tipo if tipo in TIPOS_DOC_OC else 'OTRO'
    claves, viejas = [], []
    try:
        ents = _oc_entregas(orden) if tipo == 'GUIA' else []
        n, errores = _subir_docs_orden(orden, claves, (tipo,), viejas, entrega=ents[0] if len(ents) == 1 else None)
        if errores or not n:
            db.session.rollback()
            _borrar_de_s3(claves)
            flash('⛔ ' + (' '.join(errores) or 'Elige un archivo.'))
            return redirect(destino)
        if not viejas:
            _oc_evento(orden, 'DOCUMENTO', f"Adjuntó {n} archivo(s): {TIPOS_DOC_OC[tipo]}")
        db.session.commit()
        _borrar_de_s3(viejas)
        flash(('✅ Documento reemplazado.' if viejas else '✅ Documento adjuntado.')
              + (f' {_oc_codigo(orden)}: certificado de calidad al día.' if tipo == 'CERTIFICADO' else ''))
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        flash(f'⛔ No se pudo subir el documento: {e}')
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/numeros', methods=['POST'])
@_ruta_oc('editar')
def oc_numeros_documento(orden_id):
    """N° de guía y N° de factura (se pueden completar en cualquier momento antes de que la orden se anule)."""
    orden, no = _accion_oc(orden_id, 'documentos')
    if no:
        return no
    cambios = []
    for campo, etq in (('numero_guia', 'Guía'), ('numero_factura', 'Factura')):
        if campo in request.form:
            nuevo = _limpio(request.form.get(campo), 60).upper() or None
            if nuevo != getattr(orden, campo):
                cambios.append(f"{etq}: {getattr(orden, campo) or '-'} → {nuevo or '-'}")
                setattr(orden, campo, nuevo)
    if cambios:
        _oc_evento(orden, 'DOCUMENTO', 'N° de documento: ' + '; '.join(cambios))
        db.session.commit()
        flash('✅ Número guardado.')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/documento/<int:doc_id>/borrar', methods=['POST'])
@_ruta_oc('editar')
def oc_documento_borrar(doc_id):
    doc = OrdenCompraDocumento.query.get_or_404(doc_id)
    orden = OrdenCompra.query.get_or_404(doc.orden_id)
    if not _oc_permisos(orden)['borrar_docs']:
        flash('⛔ Con la orden conforme o anulada, sus documentos ya no se borran.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    clave = doc.s3_key
    _oc_evento(orden, 'DOC_BORRADO', f"Borró {TIPOS_DOC_OC.get(doc.tipo, doc.tipo)}: {doc.nombre_original}")
    db.session.delete(doc)
    db.session.commit()
    _borrar_de_s3([clave])
    flash('Documento borrado.')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/documento/<int:doc_id>')
@_ruta_oc('docs')
def oc_documento_ver(doc_id):
    doc = OrdenCompraDocumento.query.get_or_404(doc_id)
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception as e:
        return f"<h3>No se pudo recuperar el documento</h3><p>{html.escape(str(e))}</p>", 404
    ext = doc.s3_key.rsplit('.', 1)[-1].lower()
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=doc.content_type or 'application/octet-stream',
                     as_attachment=request.args.get('download') == '1',
                     download_name=secure_filename(f"{doc.tipo.lower()}_orden{doc.orden_id}_{doc.id}.{ext}"))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


# ---------------------------- PAGO, FACTURA Y COMPARACIÓN ----------------------------
def _fecha_form(valor):
    try:
        return datetime.strptime((valor or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


@app.route('/ordenes/<int:orden_id>/pagar', methods=['POST'])
@_ruta_oc('pagar')
def oc_pagar(orden_id):
    """Marca la orden como PAGADA (después de la aprobación). Exige la factura: si no está subida, se sube aquí mismo."""
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    orden, no = _accion_oc(orden_id, 'pagar')
    if no:
        return no
    f = request.form
    destino = url_for('oc_detalle', orden_id=orden.id)
    hoy = hora_peru().date()
    fecha_pago = _fecha_form(f.get('fecha_pago')) or hoy
    if fecha_pago > hoy:
        flash('⛔ La fecha de pago no puede ser futura.')
        return redirect(destino)
    if fecha_pago < orden.fecha - timedelta(days=30):
        flash('⛔ La fecha de pago no puede ser más de 30 días anterior a la orden.')
        return redirect(destino)
    fecha_fact = _fecha_form(f.get('fecha_factura'))
    if fecha_fact and (fecha_fact > hoy or fecha_fact < orden.fecha - timedelta(days=60)):
        flash('⛔ Revisa la fecha de emisión de la factura.')
        return redirect(destino)
    claves, viejas = [], []
    try:
        n_docs, errores = _subir_docs_orden(orden, claves, ('FACTURA', 'PAGO'), viejas)
        if errores:
            db.session.rollback()
            _borrar_de_s3(claves)
            flash('⛔ ' + ' '.join(errores))
            return redirect(destino)
        if (f.get('numero_factura') or '').strip():
            orden.numero_factura = _limpio(f.get('numero_factura'), 60).upper()
        if fecha_fact:
            orden.fecha_factura = fecha_fact
        db.session.flush()
        if not OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id == orden.id, OrdenCompraDocumento.tipo == 'FACTURA').first():
            db.session.rollback()
            _borrar_de_s3(claves)
            flash('⛔ Para marcarla como PAGADA adjunta la FACTURA (PDF o foto).')
            return redirect(destino)
        cuenta = OCCuentaBancaria.query.get(f.get('cuenta_id', type=int)) if f.get('cuenta_id', type=int) else None
        if cuenta and cuenta.oc_proveedor_id != orden.oc_proveedor_id:
            cuenta = None
        ahora = hora_peru()
        orden.estado_pago, orden.fecha_pago, orden.pagado_por_id, orden.fecha_marca_pago = 'PAGADO', fecha_pago, session.get('user_id'), ahora
        orden.pago_operacion = _limpio(f.get('operacion'), 80).upper() or None
        orden.pago_cuenta = _cuenta_txt(cuenta)[:200] if cuenta else None
        orden.pago_nota = ' '.join((f.get('nota') or '').split())[:300] or None
        mon = MONEDAS_OC[orden.moneda]['simbolo']
        _oc_evento(orden, 'PAGO', f"Pagada el {fecha_pago.strftime('%d/%m/%Y')} · {mon} {orden.total:,.2f}"
                                  + (f" · Op. {orden.pago_operacion}" if orden.pago_operacion else '')
                                  + (f" · {orden.pago_cuenta}" if orden.pago_cuenta else '')
                                  + (f" · {n_docs} documento(s)" if n_docs else '') + (f" · {orden.pago_nota}" if orden.pago_nota else ''))
        registrar_log(f"Marcó como PAGADA la {_oc_codigo(orden)} ({orden.razon_social}, {mon} {orden.total:,.2f})", 'bi-cash-coin', 'text-success')
        db.session.commit()
        _borrar_de_s3(viejas)
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception("No se pudo marcar el pago de la orden")
        flash(f'⛔ No se pudo guardar el pago (no se guardó nada): {e}')
        return redirect(destino)
    flash(f'✅ {_oc_codigo(orden)} marcada como PAGADA por {session.get("nombre", "")}.')
    return redirect(destino)


@app.route('/ordenes/<int:orden_id>/pago/deshacer', methods=['POST'])
@_ruta_oc('admin')
def oc_pago_deshacer(orden_id):
    orden, no = _accion_oc(orden_id, 'deshacer_pago')
    if no:
        return no
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    if len(motivo) < 5:
        flash('⛔ Escribe por qué se quita la marca de pagada.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    _oc_evento(orden, 'PAGO_DESHECHO', f"Se quitó la marca de pagada (era del {orden.fecha_pago.strftime('%d/%m/%Y') if orden.fecha_pago else '-'}): {motivo}")
    orden.estado_pago, orden.fecha_pago, orden.pagado_por_id, orden.fecha_marca_pago = 'PENDIENTE', None, None, None
    orden.pago_operacion, orden.pago_cuenta, orden.pago_nota = None, None, None
    registrar_log(f"Quitó la marca de PAGADA de la {_oc_codigo(orden)}: {motivo}", 'bi-arrow-counterclockwise', 'text-warning')
    db.session.commit()
    flash('La orden vuelve a "pendiente de pago".')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/factura', methods=['POST'])
@_ruta_oc('pagar')
def oc_factura_datos(orden_id):
    """N°, fecha de emisión y total de la factura (para compararla con la orden y contar el crédito)."""
    orden, no = _accion_oc(orden_id, 'factura')
    volver = request.form.get('volver') or ''
    volver = volver if volver.startswith('/') else url_for('oc_detalle', orden_id=orden_id)
    if no:
        return no
    f = request.form
    hoy = hora_peru().date()
    cambios = []
    if 'numero_factura' in f:
        nuevo = _limpio(f.get('numero_factura'), 60).upper() or None
        if nuevo != orden.numero_factura:
            cambios.append(f"N°: {orden.numero_factura or '-'} → {nuevo or '-'}")
            orden.numero_factura = nuevo
    if 'fecha_factura' in f:
        ff = _fecha_form(f.get('fecha_factura'))
        if f.get('fecha_factura') and (not ff or ff > hoy or ff < orden.fecha - timedelta(days=60)):
            flash('⛔ Revisa la fecha de emisión de la factura.')
            return redirect(volver)
        if ff != orden.fecha_factura:
            cambios.append(f"Emisión: {orden.fecha_factura.strftime('%d/%m/%Y') if orden.fecha_factura else '-'} → {ff.strftime('%d/%m/%Y') if ff else '-'}")
            orden.fecha_factura = ff
    if 'monto_factura' in f:
        monto = _num(f.get('monto_factura')) if (f.get('monto_factura') or '').strip() else None
        if monto is not None and (monto < 0 or monto > 100_000_000):
            flash('⛔ El total de la factura no es válido.')
            return redirect(volver)
        monto = round(monto, 2) if monto is not None else None
        if monto != orden.monto_factura:
            cambios.append(f"Total: {orden.monto_factura if orden.monto_factura is not None else '-'} → {monto if monto is not None else '-'}")
            orden.monto_factura = monto
    if cambios:
        _oc_evento(orden, 'DOCUMENTO', 'Datos de la factura: ' + '; '.join(cambios))
        db.session.commit()
        flash('✅ Datos de la factura guardados.')
    return redirect(volver)


@app.route('/ordenes/<int:orden_id>/comparar')
@_ruta_oc()
def oc_comparar(orden_id):
    """Factura vs. orden lado a lado (cada panel elige su documento y se mueve por su cuenta)."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    docs = OrdenCompraDocumento.query.filter_by(orden_id=orden.id).order_by(OrdenCompraDocumento.id).all()
    fuentes = [{'id': 'oc', 'txt': f'{_oc_codigo(orden)} (PDF del sistema)', 'url': url_for('oc_pdf', orden_id=orden.id, ver=1), 'pdf': True, 'tipo': 'OC'}]
    conteo = {}
    for d in docs:
        conteo[d.tipo] = conteo.get(d.tipo, 0) + 1
        numero = {'GUIA': orden.numero_guia, 'FACTURA': orden.numero_factura, 'COTIZACION': orden.cotizacion}.get(d.tipo)
        fuentes.append({'id': f'd{d.id}', 'tipo': d.tipo, 'url': url_for('oc_documento_ver', doc_id=d.id), 'pdf': d.content_type == 'application/pdf',
                        'txt': f"{TIPOS_DOC_OC.get(d.tipo, d.tipo)} {conteo[d.tipo]}" + (f" · N° {numero}" if numero else '') + f" · {d.nombre_original}"})
    derecha = next((x['id'] for x in fuentes if x['tipo'] == 'FACTURA'), fuentes[1]['id'] if len(fuentes) > 1 else 'oc')
    return render_template('oc_comparar.html', orden=orden, fuentes=fuentes, derecha=derecha, monedas=MONEDAS_OC, igv=IGV_OC,
                           p=_oc_permisos(orden), hay_factura=any(d.tipo == 'FACTURA' for d in docs), seccion='lista')


# ---------------------------- CUENTAS BANCARIAS DEL PROVEEDOR ----------------------------
@app.route('/ordenes/api/cuentas/<int:prov_id>')
@_ruta_oc('ver', como_json=True)
def oc_api_cuentas(prov_id):
    return {'status': 'success', 'cuentas': _cuentas_de(prov_id, request.args.get('todas') == '1')}


@app.route('/ordenes/api/cuenta', methods=['POST'])
@_ruta_oc('pagar', como_json=True)
def oc_api_cuenta():
    """Guardar (nueva o editar), archivar, restaurar o borrar (Gerencia, si nunca se usó) una cuenta bancaria del proveedor."""
    f = request.form
    accion = f.get('accion', 'guardar')
    ahora, quien = hora_peru(), session.get('nombre', '')
    c = OCCuentaBancaria.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    if accion != 'guardar':
        if not c:
            return {'status': 'error', 'msg': 'No existe.'}
        prov = OCProveedor.query.get(c.oc_proveedor_id)
        if accion == 'archivar':
            c.activo, c.archivado_por, c.fecha_archivo = False, quien, ahora
            registrar_log(f"Archivó la cuenta {_cuenta_txt(c)} de {prov.razon_social if prov else ''}", 'bi-archive', 'text-secondary')
        elif accion == 'restaurar':
            c.activo, c.archivado_por, c.fecha_archivo = True, None, None
        elif accion == 'borrar':
            if session.get('role') != 'admin':
                return {'status': 'error', 'msg': 'Solo Gerencia puede borrar una cuenta. Archívala para que no aparezca.'}
            if any((o.pago_cuenta or '').endswith(c.numero) for o in OrdenCompra.query.filter(OrdenCompra.oc_proveedor_id == c.oc_proveedor_id).all()):
                return {'status': 'error', 'msg': 'Esta cuenta ya se usó en un pago: no se borra (se perdería el historial). Archívala.'}
            registrar_log(f"Borró la cuenta {_cuenta_txt(c)} de {prov.razon_social if prov else ''}", 'bi-trash', 'text-danger')
            db.session.delete(c)
        db.session.commit()
        return {'status': 'success', 'cuentas': _cuentas_de(prov.id if prov else 0, f.get('todas') == '1')}
    prov = OCProveedor.query.get(c.oc_proveedor_id if c else f.get('oc_proveedor_id', type=int) or 0)
    if not prov:
        return {'status': 'error', 'msg': 'Primero elige el proveedor.'}
    banco, tipo = (f.get('banco') or '').upper(), (f.get('tipo') or '').upper()
    moneda = (f.get('moneda') or 'PEN').upper()
    numero = ' '.join((f.get('numero') or '').split())[:40]
    digitos = _digitos(numero)
    banco_otro = _limpio(f.get('banco_otro'), 80).upper() or None
    if tipo not in TIPOS_CUENTA_OC:
        return {'status': 'error', 'msg': 'Elige si es cuenta, CCI o cuenta de detracciones.'}
    if tipo == 'DETRACCION':
        banco, moneda = 'NACION', 'PEN'          # las detracciones se depositan en el Banco de la Nación, en soles
    if banco not in BANCOS_OC:
        return {'status': 'error', 'msg': 'Elige el banco.'}
    if banco == 'OTRO' and not banco_otro:
        return {'status': 'error', 'msg': 'Escribe el nombre del banco.'}
    if moneda not in MONEDAS_OC:
        return {'status': 'error', 'msg': 'Moneda no válida.'}
    if re.search(r'[^\d\s-]', numero):
        return {'status': 'error', 'msg': 'El número solo lleva dígitos (y guiones si quieres).'}
    if tipo == 'CCI' and len(digitos) != 20:
        return {'status': 'error', 'msg': f'El CCI tiene 20 dígitos (escribiste {len(digitos)}).'}
    if tipo != 'CCI' and not 6 <= len(digitos) <= 20:
        return {'status': 'error', 'msg': 'El número de cuenta debe tener entre 6 y 20 dígitos.'}
    repetida = next((x for x in OCCuentaBancaria.query.filter_by(oc_proveedor_id=prov.id).all()
                     if x.id != (c.id if c else 0) and _digitos(x.numero) == digitos), None)
    if repetida:
        return {'status': 'error', 'msg': f'Esa cuenta ya está guardada ({_cuenta_txt(repetida)}).'}
    if c:
        antes = _cuenta_txt(c)
        c.actualizado_por, c.fecha_actualizacion = quien, ahora
    else:
        c = OCCuentaBancaria(oc_proveedor_id=prov.id, activo=True, creado_por=quien, fecha_creacion=ahora)
        db.session.add(c)
        antes = None
    c.banco, c.banco_otro, c.tipo, c.moneda, c.numero = banco, banco_otro if banco == 'OTRO' else None, tipo, moneda, numero
    c.titular = _limpio(f.get('titular'), 200).upper() or None
    registrar_log(f"{'Editó' if antes else 'Guardó'} la cuenta de {prov.razon_social}: " + (f"{antes} → " if antes else '') + _cuenta_txt(c),
                  'bi-bank', 'text-info')
    db.session.commit()
    return {'status': 'success', 'cuenta_id': c.id, 'cuentas': _cuentas_de(prov.id, f.get('todas') == '1')}


# ---------------------------- CLIENTE (cuando la compra es para un pedido de cliente) ----------------------------
@app.route('/ordenes/api/cliente')
@_ruta_oc('req_crear', como_json=True)
def oc_api_cliente():
    """Sugerencias de CLIENTES mientras se escribe (nunca proveedores): la cartera de clientes del sistema (la misma de ventas)
    y los clientes ya usados en órdenes anteriores. Sin texto: los últimos clientes usados. Con sunat=1 y un RUC que no está, consulta SUNAT."""
    q = ' '.join((request.args.get('q') or '').split())
    num = _digitos(q)
    solo_numero = bool(num) and len(num) == len(q.replace(' ', ''))
    res, vistos = [], set()

    def agregar(ruc, razon, origen):
        ruc = (ruc or '').strip()
        if ruc and ruc not in vistos and len(res) < 10:
            vistos.add(ruc)
            res.append({'ruc': ruc, 'razon': (razon or '').upper(), 'origen': origen})

    usados = OrdenCompra.query.filter(OrdenCompra.cliente_ruc.isnot(None)).order_by(OrdenCompra.id.desc()).all()
    if len(q) < 2:
        for o in usados:
            agregar(o.cliente_ruc, o.cliente_razon, 'Usado en órdenes')
        return {'status': 'success', 'clientes': res, 'recientes': True}
    if solo_numero:
        cartera = Client.query.filter(Client.documento.like(f'{num}%')).limit(10).all()
    else:
        filtro = _filtro_busqueda_flexible(q, Client.nombre, Client.documento)
        cartera = Client.query.filter(filtro).limit(10).all() if filtro is not None else []
    for x in cartera:
        agregar(x.documento, x.nombre, 'Cartera de clientes')
    terminos = q.upper().split()
    for o in usados:
        if (solo_numero and (o.cliente_ruc or '').startswith(num)) or (not solo_numero and all(t in (o.cliente_razon or '').upper() for t in terminos)):
            agregar(o.cliente_ruc, o.cliente_razon, 'Usado en órdenes')
    if not res and request.args.get('sunat') == '1' and len(num) in (8, 11):
        datos, err = _sunat_consulta_externa(num)
        if err:
            return {'status': 'error', 'msg': err}
        agregar(num, datos['razon_social'], 'SUNAT')
    return {'status': 'success', 'clientes': res}


# ---------------------------- INGRESOS PENDIENTES AL INVENTARIO (Almacén) ----------------------------
def _entregas_por_ingresar(ordenes=None):
    """[(orden, entrega, [ítems de la entrega sin ingresar])] de entregas CONFORMES de compras para el inventario.
    Cada entrega llega a Ingresos pendientes con su fecha y su guía, en el orden en que llegó."""
    if ordenes is None:
        ordenes = OrdenCompra.query.filter(OrdenCompra.tipo == 'OC', OrdenCompra.destino == 'GENERAL',
                                           OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME'])).all()
    res = []
    for o in ordenes:
        if o.tipo != 'OC' or o.destino != 'GENERAL':
            continue
        for e in _oc_entregas(o):
            if e.fecha_conforme:
                pend = [ei for ei in e.items if not ei.fecha_ingreso]
                if pend:
                    res.append((o, e, pend))
    return res


def _items_por_ingresar():
    """Para el contador del menú: cada producto de cada entrega conforme que falta ingresar al inventario."""
    return [ei for _, _, eis in _entregas_por_ingresar() for ei in eis]


def _os_por_seguir():
    """Órdenes de SERVICIO conformes a las que Almacén todavía no les marcó el seguimiento (material de vuelta, movimiento registrado)."""
    return [o for o in OrdenCompra.query.filter(OrdenCompra.estado == 'CONFORME', OrdenCompra.tipo == 'OS').all() if not o.fecha_kardex]


@app.route('/ordenes/ingresos')
@_ruta_oc('ingresar')
def oc_ingresos_pendientes():
    """Lo que llegó con OC y ya tiene conformidad (por entrega, si llegó por partes): Almacén lo ingresa al Kardex."""
    vista = request.args.get('vista', 'pendientes')
    vista = vista if vista in ('pendientes', 'hechos') else 'pendientes'
    emp_sel = (request.args.get('empresa') or session.get('oc_empresa_ing') or 'TODAS').upper()
    emp_sel = emp_sel if emp_sel in EMPRESAS_OC or emp_sel == 'TODAS' else 'TODAS'
    session['oc_empresa_ing'] = emp_sel
    candidatas = (OrdenCompra.query.filter(OrdenCompra.destino == 'GENERAL', OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME']))
                  .order_by(OrdenCompra.id.desc()).all())
    grupos, pend_emp, n_hechos = [], {e: 0 for e in EMPRESAS_OC}, 0
    for o in candidatas:
        emp = o.empresa or 'ANCLAJES'
        items = {i.id: i for i in o.items}
        if o.tipo == 'OS':
            if o.estado != 'CONFORME':
                continue
            pend_emp[emp] += 0 if o.fecha_kardex else 1
            hecho = bool(o.fecha_kardex)
            n_hechos += hecho and (emp_sel in ('TODAS', emp))
            if (emp_sel in ('TODAS', emp)) and ((vista == 'pendientes' and not hecho) or (vista == 'hechos' and hecho)):
                grupos.append({'o': o, 'items': items, 'bloques': [], 'fecha': (o.fecha_kardex if hecho else o.fecha_llegada) or o.fecha_conforme})
            continue
        bloques = []
        for e in _oc_entregas(o):
            if not e.fecha_conforme:
                continue
            pend = [ei for ei in e.items if not ei.fecha_ingreso and ei.item_id in items]
            hechos = [ei for ei in e.items if ei.fecha_ingreso and ei.item_id in items]
            pend_emp[emp] += len(pend)
            if emp_sel in ('TODAS', emp):
                n_hechos += len(hechos)
            lista = pend if vista == 'pendientes' else hechos
            if lista:
                bloques.append({'e': e, 'eis': lista})
        if bloques and emp_sel in ('TODAS', emp):
            # pendientes: por FECHA DE LLEGADA de la entrega más antigua que espera (lo que llegó primero, se ingresa primero)
            fecha = (min(b['e'].fecha or b['e'].fecha_conforme for b in bloques) if vista == 'pendientes'
                     else max(ei.fecha_ingreso for b in bloques for ei in b['eis']))
            grupos.append({'o': o, 'items': items, 'bloques': bloques, 'fecha': fecha})
    # pendientes: lo que llegó primero va arriba (o al revés si se elige "más recientes"); hechos: lo último ingresado arriba
    orden_lista = request.args.get('orden', 'antiguos' if vista == 'pendientes' else 'recientes')
    orden_lista = orden_lista if orden_lista in ('antiguos', 'recientes') else 'antiguos'
    grupos.sort(key=lambda g: (g['fecha'] or datetime.min, g['o'].id), reverse=(orden_lista == 'recientes'))
    if vista == 'hechos':
        grupos = grupos[:80]
    pend_emp['TODAS'] = sum(pend_emp.values())
    stock, peso_inv = {}, {}
    for emp, Modelo in (('ANCLAJES', Product), ('IMPORTBOLTS', ProductImportBolts)):
        skus = {(i.sku_ingreso or i.codigo or '').upper() for g in grupos if (g['o'].empresa or 'ANCLAJES') == emp
                for i in g['items'].values() if (i.sku_ingreso or i.codigo)}
        if skus:
            for pr in Modelo.query.filter(func.upper(Modelo.sku).in_(list(skus))).all():
                stock[(emp, (pr.sku or '').upper())] = pr.stock_actual or 0
                peso_inv[(emp, (pr.sku or '').upper())] = getattr(pr, 'peso_kg', None) or 0
    docs = {}
    for d in OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id.in_([g['o'].id for g in grupos] or [0])).all():
        docs.setdefault(d.orden_id, []).append(d)
    datos_kardex = {}
    if vista == 'pendientes':
        for g in grupos:
            for b in g['bloques']:
                dk = _datos_kardex_entrega(g['o'], b['e'], b['eis'], g['items'])
                dk['pdf'] = url_for('oc_pdf', orden_id=g['o'].id, ver=1)
                dk['docs'] = [{'tipo': TIPOS_DOC_OC.get(d.tipo, d.tipo) + (f" (entrega {b['e'].numero})" if d.entrega_id == b['e'].id else ''),
                               'clave': d.tipo, 'nombre': d.nombre_original or '', 'url': url_for('oc_documento_ver', doc_id=d.id)}
                              for d in docs.get(g['o'].id, []) if d.tipo != 'GUIA' or d.entrega_id in (None, b['e'].id)]
                datos_kardex[b['e'].id] = dk
    presentaciones = [pr.nombre for pr in Presentacion.query.filter_by(activo=True).order_by(Presentacion.nombre).all()]
    return render_template('oc_ingresos.html', grupos=grupos, docs=docs, puede_ver_oc=session.get('role') in ROLES_OC_VEN, vista=vista, stock=stock,
                           datos_kardex=datos_kardex, presentaciones=presentaciones, hoy_iso=hora_peru().date().isoformat(),
                           peso_inv=peso_inv, n_pendientes=pend_emp[emp_sel], n_hechos=n_hechos, monedas=MONEDAS_OC, ahora=hora_peru(),
                           emp_sel=emp_sel, pend_emp=pend_emp, orden_lista=orden_lista,
                           empresas_oc=EMPRESAS_OC, es_admin=session.get('role') == 'admin', seccion='ingresos')


def _ei_y_orden(ei_id):
    ei = OrdenCompraEntregaItem.query.get_or_404(ei_id)
    e = OrdenCompraEntrega.query.get_or_404(ei.entrega_id)
    orden = OrdenCompra.query.get_or_404(e.orden_id)
    item = next((i for i in orden.items if i.id == ei.item_id), None)
    return ei, e, orden, item


@app.route('/ordenes/entrega-item/<int:ei_id>/ingresar', methods=['POST'])
@_ruta_oc('ingresar')
def oc_item_ingresar(ei_id):
    """Solo marcar como ingresado (quien ya hizo el movimiento a mano en el Kardex)."""
    ei, e, orden, item = _ei_y_orden(ei_id)
    volver = url_for('oc_ingresos_pendientes')
    if not item or not e.fecha_conforme or orden.destino != 'GENERAL' or orden.tipo != 'OC':
        flash('⛔ Esa entrega no tiene conformidad o no es para el inventario.')
        return redirect(volver)
    if ei.fecha_ingreso:
        flash('Ese producto ya estaba marcado como ingresado.')
        return redirect(volver)
    # El SKU es OPCIONAL: ayuda a ubicar el producto, pero no impide marcarlo (Almacén pudo crearlo con otro código).
    sku = _limpio(request.form.get('sku'), 60).upper() or (item.codigo or '').upper() or None
    if sku:
        prod = _producto_de_item(orden, item, sku)
        sku = prod.sku if prod else sku
    ahora = hora_peru()
    ei.ingresado_por_id, ei.fecha_ingreso, ei.sku_ingreso = session.get('user_id'), ahora, sku
    ei.nota_ingreso = ' '.join((request.form.get('nota') or '').split())[:300] or None
    _oc_evento(orden, 'INGRESO_ITEM', f"Entrega {e.numero} · ítem {item.item} ({item.descripcion[:60]}): {_cant_txt(ei.cantidad)} marcado(s) como ingresado(s) "
                                     f"al inventario {EMPRESAS_OC[orden.empresa or 'ANCLAJES']['corto']} por {session.get('nombre', '')}"
                                     + (f" · SKU {sku}" if sku else '') + (f" · {ei.nota_ingreso}" if ei.nota_ingreso else ''))
    _oc_revisar_ingreso_completo(orden)
    _req_notificar_orden(orden, 'OC_INGRESADO', f"{_oc_codigo(orden)}: {item.codigo or item.descripcion[:30]} ingresado al inventario")
    registrar_log(f"Marcó como ingresado al inventario: {item.descripcion[:60]}{f' (SKU {sku})' if sku else ''} de la {_oc_codigo(orden)}",
                  'bi-box-arrow-in-down', 'text-success')
    db.session.commit()
    flash(f'✅ Ítem {item.item} (entrega {e.numero}) de la {_oc_codigo(orden)} marcado como ingresado por {session.get("nombre", "")}.')
    return redirect(volver)


@app.route('/ordenes/entrega-item/<int:ei_id>/deshacer', methods=['POST'])
@_ruta_oc('admin')
def oc_item_deshacer(ei_id):
    """Gerencia corrige una marca de ingreso hecha a mano por error (queda en el historial)."""
    ei, e, orden, item = _ei_y_orden(ei_id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    if len(motivo) < 5:
        flash('⛔ Escribe por qué se quita la marca.')
        return redirect(url_for('oc_ingresos_pendientes', vista='hechos'))
    if ei.kardex_mov_id:
        flash(f'⛔ Este producto entró al Kardex con el movimiento #{ei.kardex_mov_id} (stock ya sumado). No se quita la marca: '
              f'si la cantidad estuvo mal, corrígela en el Kardex con un movimiento de ajuste.')
        return redirect(url_for('oc_ingresos_pendientes', vista='hechos'))
    _oc_evento(orden, 'INGRESO_DESHECHO', f"Entrega {e.numero} · ítem {item.item if item else '?'}: se quitó la marca de ingresado ({motivo})")
    ei.ingresado_por_id, ei.fecha_ingreso, ei.sku_ingreso, ei.nota_ingreso = None, None, None, None
    if item:
        item.ingresado_por_id, item.fecha_ingreso = None, None
    orden.kardex_registrado_por_id, orden.fecha_kardex = None, None
    db.session.commit()
    flash('Marca quitada: el producto vuelve a "pendiente de ingresar".')
    return redirect(url_for('oc_ingresos_pendientes'))


# ---------------------------- INGRESO AL KARDEX DESDE LA ORDEN ----------------------------
def _modelos_inv_orden(orden):
    """(Producto, Movimiento, origen del Kardex) del inventario de la empresa de la orden."""
    if (orden.empresa or 'ANCLAJES') == 'IMPORTBOLTS':
        return ProductImportBolts, ProductMovementImportBolts, 'IMPORTBOLTS'
    return Product, ProductMovement, 'ANCLAJES'


def _producto_de_item(orden, item, sku=None):
    """Producto del inventario de la empresa al que entra el ítem: por el SKU indicado o por el código del ítem."""
    Modelo, _, _ = _modelos_inv_orden(orden)
    sku = (sku or item.sku_ingreso or item.codigo or '').strip().upper()
    if not sku:
        return None
    q = Modelo.query.filter(func.upper(Modelo.sku) == sku)
    if Modelo is Product:
        q = q.filter(Product.es_shadow_importbolts.isnot(True))
    return q.first()


def _motivo_compra_kardex():
    """Motivo de ENTRADA 'COMPRA' del Kardex (se crea si alguien lo borró)."""
    m = next((x for x in MotivoMovimiento.query.filter_by(tipo='ENTRADA').all() if _txt_sin_tildes(x.nombre) == 'COMPRA'), None)
    if not m:
        m = MotivoMovimiento(nombre='COMPRA', tipo='ENTRADA', activo=True, es_predeterminado=True)
        db.session.add(m)
        db.session.flush()
    return m


def _proveedor_kardex_de_orden(orden):
    """El proveedor de la orden en la lista de proveedores del Kardex (validado por RUC; se crea con los datos de la orden si no está)."""
    ruc = (orden.ruc or '').strip().upper() if orden.es_importacion else _digitos(orden.ruc)
    p = Proveedor.query.filter_by(documento=ruc).first() if ruc else None
    if not p:
        ocp = OCProveedor.query.get(orden.oc_proveedor_id) if orden.oc_proveedor_id else None
        p = Proveedor(documento=ruc or None, tipo_proveedor='INTERNACIONAL' if orden.es_importacion else 'NACIONAL', razon_social=(orden.razon_social or '')[:200],
                      direccion=(orden.direccion or '')[:200] or None,
                      estado=getattr(ocp, 'sunat_estado', None), condicion=getattr(ocp, 'sunat_condicion', None),
                      last_updated=hora_peru(), updated_by=session.get('username', 'Sistema'), creado_por_id=session.get('user_id'))
        db.session.add(p)
        db.session.flush()
    return p


def _referencia_kardex_orden(orden, entrega=None):
    """En el Kardex, la referencia de una COMPRA es la guía de esa entrega o la factura; si no hay, el número de la orden."""
    return ((entrega.numero_guia if entrega else None) or orden.numero_factura or orden.numero_guia or _oc_codigo(orden))[:50].upper()


def _datos_kardex_entrega(orden, entrega, eis, items):
    """Lo que el modal 'Movimiento de Kardex' necesita precargado para los productos de UNA entrega."""
    filas = []
    for ei in eis:
        i = items.get(ei.item_id)
        if not i or ei.fecha_ingreso:
            continue
        prod = _producto_de_item(orden, i)
        cant = ei.cantidad or 0
        filas.append({'id': ei.id, 'item': i.item, 'descripcion': i.descripcion, 'cantidad': cant, 'um': i.um,
                      'cantidad_int': max(int(cant + 0.5), 1), 'entera': abs(cant - round(cant)) < 1e-9,
                      'precio': round(i.precio_unitario or 0, 4), 'es_nuevo': bool(i.es_nuevo),
                      'sku': prod.sku if prod else '', 'nombre': prod.nombre if prod else '', 'stock': (prod.stock_actual or 0) if prod else None,
                      'familia': i.familia or '', 'calidad': i.calidad or ''})
    llegada = entrega.fecha or orden.fecha_llegada or hora_peru()
    return {'orden_id': orden.id, 'entrega': entrega.numero, 'parcial': bool(entrega.parcial), 'codigo': _oc_codigo(orden),
            'empresa': orden.empresa or 'ANCLAJES', 'empresa_txt': EMPRESAS_OC[orden.empresa or 'ANCLAJES']['corto'],
            'fecha': llegada.date().isoformat(), 'fecha_txt': llegada.strftime('%d/%m/%Y'), 'ruc': orden.ruc or '', 'razon_social': orden.razon_social,
            'referencia': _referencia_kardex_orden(orden, entrega), 'moneda': MONEDAS_OC[orden.moneda or 'PEN']['simbolo'],
            'guia': entrega.numero_guia or '', 'factura': orden.numero_factura or '', 'items': filas,
            'url': url_for('oc_kardex_ingresar', entrega_id=entrega.id)}


@app.route('/ordenes/entrega/<int:entrega_id>/kardex', methods=['POST'])
@_ruta_oc('ingresar')
def oc_kardex_ingresar(entrega_id):
    """Registra en el Kardex (con los datos de la OC y de la ENTREGA) el ingreso de uno o varios productos y los marca como ingresados.
    Motivo COMPRA, proveedor de la orden, precio de la orden, fecha de esa llegada y su guía. Los documentos de la orden NO se
    vuelven a subir: el movimiento queda enlazado a la orden y desde el Kardex se abren sus documentos."""
    e = OrdenCompraEntrega.query.get_or_404(entrega_id)
    orden = OrdenCompra.query.get_or_404(e.orden_id)
    volver = url_for('oc_ingresos_pendientes')
    f = request.form
    if not e.fecha_conforme or orden.destino != 'GENERAL' or orden.tipo != 'OC' or orden.estado not in ('APROBADA', 'RECIBIDA', 'CONFORME'):
        flash('⛔ Esa entrega no tiene conformidad o no es una compra para el inventario.')
        return redirect(volver)
    fecha_mov, error = _resolver_fecha_movimiento(f.get('fecha_movimiento'))
    if error:
        flash(error)
        return redirect(volver)
    if orden.fecha and fecha_mov.date() < orden.fecha:
        flash('⛔ La fecha del ingreso no puede ser anterior a la fecha de la orden.')
        return redirect(volver)
    Modelo, Movimiento, origen = _modelos_inv_orden(orden)
    presentacion = _limpio(f.get('presentacion'), 50) or None
    if presentacion and not Presentacion.query.filter_by(nombre=presentacion).first():
        presentacion = None
    obs_general = ' '.join((f.get('observacion') or '').split())[:200]
    ids = [int(x) for x in f.getlist('item_id') if (x or '').isdigit()]
    eis = {ei.id: ei for ei in e.items}
    items = {i.id: i for i in orden.items}
    filas, errores = [], []
    for eid in dict.fromkeys(ids):
        ei = eis.get(eid)
        it = items.get(ei.item_id) if ei else None
        if not it:
            continue
        if ei.fecha_ingreso:
            errores.append(f'Ítem {it.item}: ya estaba ingresado (lo hizo otra persona).')
            continue
        sku = _limpio(f.get(f'sku_{eid}'), 60).upper()
        prod = _producto_de_item(orden, it, sku or None)
        if not prod:
            errores.append(f'Ítem {it.item} ({it.descripcion[:40]}): elige el producto del inventario {EMPRESAS_OC[orden.empresa or "ANCLAJES"]["corto"]} '
                           f'(si no existe, pide que lo creen en el Maestro).')
            continue
        try:
            cant = int(f.get(f'cantidad_{eid}') or 0)
        except ValueError:
            cant = 0
        if cant < 1 or cant > 10_000_000:
            errores.append(f'Ítem {it.item}: la cantidad que entra al Kardex debe ser un número entero mayor a 0.')
            continue
        precio = _num(f.get(f'precio_{eid}'))
        if precio is None or precio < 0:
            errores.append(f'Ítem {it.item}: el precio unitario no es válido.')
            continue
        difiere = abs(cant - (ei.cantidad or 0)) > 1e-9
        if difiere and len(obs_general) < 5:
            errores.append(f'Ítem {it.item}: la cantidad ({cant}) es distinta a la que llegó en esta entrega ({_cant_txt(ei.cantidad)} {it.um}). '
                           f'Explica por qué en la observación.')
            continue
        filas.append((ei, it, prod, cant, round(precio, 4), difiere))
    if errores or not filas:
        flash('⛔ No se registró nada. ' + (' · '.join(errores) if errores else 'Elige al menos un ítem.'))
        return redirect(volver)
    try:
        motivo = _motivo_compra_kardex()
        prov = _proveedor_kardex_de_orden(orden)
        ahora = hora_peru()
        ref = _referencia_kardex_orden(orden, e)
        codigo = _oc_codigo(orden)
        hechos = []
        for ei, it, prod, cant, precio, difiere in filas:
            antes = prod.stock_actual or 0
            prod.stock_actual = antes + cant
            obs = (f"Ingreso por {codigo} · entrega {e.numero}" + (f" (guía {e.numero_guia})" if e.numero_guia else '') + f" · ítem {it.item}"
                   + (f" · precio {MONEDAS_OC[orden.moneda or 'PEN']['simbolo']} sin IGV" if precio else ''))
            if obs_general:
                obs += f" · {obs_general}"
            mov = Movimiento(product_id=prod.id, user_id=session['user_id'], tipo='ENTRADA', cantidad=cant, stock_anterior=antes,
                             stock_nuevo=prod.stock_actual, motivo=motivo.nombre, motivo_id=motivo.id, proveedor_id=prov.id,
                             tipo_proveedor=prov.tipo_proveedor or 'NACIONAL', ruc_proveedor=prov.documento, razon_social_proveedor=prov.razon_social,
                             precio_unitario=precio, presentacion=presentacion, referencia=ref, fecha=fecha_mov,
                             observacion=obs[:300], orden_compra_id=orden.id, orden_item_id=it.id)
            db.session.add(mov)
            db.session.flush()
            ei.ingresado_por_id, ei.fecha_ingreso, ei.sku_ingreso = session.get('user_id'), ahora, prod.sku
            ei.kardex_mov_id, ei.cantidad_kardex = mov.id, cant
            ei.nota_ingreso = (obs_general or None) if difiere or obs_general else None
            _oc_evento(orden, 'INGRESO_ITEM', f"Entrega {e.numero} · ítem {it.item} ({it.descripcion[:50]}) → Kardex {EMPRESAS_OC[orden.empresa or 'ANCLAJES']['corto']}: "
                                             f"+{cant} {prod.sku} (stock {antes} → {prod.stock_actual}) · mov. #{mov.id} · fecha {fecha_mov.strftime('%d/%m/%Y')}"
                                             f" · por {session.get('nombre', '')}" + (f" · {obs_general}" if obs_general else ''))
            hechos.append(f"+{cant} {prod.sku}")
        db.session.flush()
        _oc_revisar_ingreso_completo(orden)
        _req_notificar_orden(orden, 'OC_INGRESADO', f"{codigo}: entrega {e.numero} ingresada al inventario ({', '.join(hechos)})")
        registrar_log(f"Ingresó al Kardex {'Import Bolts' if origen == 'IMPORTBOLTS' else 'Anclajes'} desde la {codigo} (entrega {e.numero}): {', '.join(hechos)}",
                      'bi-box-arrow-in-down', 'text-success')
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.exception("No se pudo registrar el ingreso al Kardex desde la orden")
        flash(f'⛔ No se pudo registrar el ingreso (no se guardó nada): {ex}')
        return redirect(volver)
    flash(f"✅ {codigo} · entrega {e.numero}: {len(hechos)} producto(s) ingresado(s) al Kardex ({', '.join(hechos)}). Los documentos de la orden quedan enlazados al movimiento.")
    return redirect(volver)


@app.route('/ordenes/<int:orden_id>/seguimiento', methods=['POST'])
@_ruta_oc('ingresar')
def oc_os_seguimiento(orden_id):
    """Orden de SERVICIO conforme: Almacén marca que hizo el seguimiento (el material volvió) y registró el movimiento."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    volver = url_for('oc_ingresos_pendientes')
    if orden.tipo != 'OS' or orden.estado != 'CONFORME':
        flash('⛔ Solo se marca el seguimiento de una orden de servicio conforme.')
        return redirect(volver)
    if orden.fecha_kardex:
        flash('Esa orden de servicio ya tenía el seguimiento marcado.')
        return redirect(volver)
    orden.kardex_registrado_por_id, orden.fecha_kardex = session.get('user_id'), hora_peru()
    orden.nota_seguimiento = ' '.join((request.form.get('nota') or '').split())[:300] or None
    _oc_evento(orden, 'SEGUIMIENTO', f"Seguimiento hecho y movimiento registrado por {session.get('nombre', '')}"
                                     + (f" · {orden.nota_seguimiento}" if orden.nota_seguimiento else ''))
    registrar_log(f"Marcó el seguimiento de la {_oc_codigo(orden)}", 'bi-clipboard-check', 'text-success')
    db.session.commit()
    flash(f'✅ {_oc_codigo(orden)}: seguimiento registrado por {session.get("nombre", "")}.')
    return redirect(volver)


@app.route('/ordenes/<int:orden_id>/seguimiento/deshacer', methods=['POST'])
@_ruta_oc('admin')
def oc_os_seguimiento_deshacer(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    if orden.tipo != 'OS' or len(motivo) < 5:
        flash('⛔ Escribe por qué se quita la marca.')
        return redirect(url_for('oc_ingresos_pendientes', vista='hechos'))
    _oc_evento(orden, 'INGRESO_DESHECHO', f"Se quitó la marca de seguimiento ({motivo})")
    orden.kardex_registrado_por_id, orden.fecha_kardex, orden.nota_seguimiento = None, None, None
    db.session.commit()
    flash('Marca quitada: la orden de servicio vuelve a "pendiente de seguimiento".')
    return redirect(url_for('oc_ingresos_pendientes'))


@app.route('/ordenes/api/sku')
@_ruta_oc('ingresar', como_json=True)
def oc_api_sku():
    """Para confirmar con qué SKU se ingresó un producto nuevo (busca en el inventario de la empresa)."""
    q = ' '.join((request.args.get('q') or '').split())
    if len(q) < 2:
        return {'results': []}
    Modelo = ProductImportBolts if request.args.get('empresa') == 'IMPORTBOLTS' else Product
    filtro = _filtro_busqueda_flexible(q, Modelo.nombre, Modelo.sku)
    res = Modelo.query.filter(filtro).order_by(Modelo.sku).limit(15).all() if filtro is not None else []
    return {'results': [{'sku': p.sku, 'descripcion': p.nombre, 'stock': p.stock_actual or 0} for p in res]}


