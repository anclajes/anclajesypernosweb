# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · PDF, proveedores y configuración
# PDF de la orden, proveedores y contactos, buscador de productos y configuración del módulo
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- PDF ----------------------------
_IMG_OC = {}


def _firma_gerencia_oc(empresa='ANCLAJES'):
    """Firma y sello de aprobación de cada empresa (static/img: GerenciaAnclajes.jpeg / firmaImpobolts.png)."""
    emp = EMPRESAS_OC.get(empresa, EMPRESAS_OC['ANCLAJES'])
    clave = f'firma_{empresa}'
    if clave not in _IMG_OC:
        try:
            with open(os.path.join(app.root_path, 'static', 'img', emp['firma']), 'rb') as fh:
                _IMG_OC[clave] = _imagen_pdf(fh.read(), emp['firma_alto'], 230)
        except Exception:
            app.logger.exception("No se encontró la firma/sello de Gerencia (static/img/%s)", emp['firma'])
            return None
    return _IMG_OC[clave]


@app.route('/ordenes/<int:orden_id>/pdf')
@_ruta_oc('docs')
def oc_pdf(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    filas = list(orden.items) + [None] * max(0, 22 - len(orden.items))
    empresa = orden.empresa or 'ANCLAJES'
    html_pdf = render_template('pdf_orden_compra.html', o=orden, cfg=_oc_cfg(empresa), logo=_logo_pdf_insumos(empresa),
                               firma=_firma_gerencia_oc(empresa) if orden.estado in ('APROBADA', 'RECIBIDA', 'CONFORME') else None,
                               filas=filas, mon=MONEDAS_OC[orden.moneda], letras=_monto_en_letras(orden.total, orden.moneda),
                               tipos=TIPOS_OC, igv_pct=int(IGV_OC * 100), tema=TEMAS_PDF_OC.get(empresa, TEMAS_PDF_OC['ANCLAJES']))
    nombre = f"{orden.tipo}_{secure_filename(empresa.title())}_{_oc_numero_txt(orden)}_{secure_filename(orden.razon_social)[:30]}.pdf"
    resp = _generar_respuesta_pdf(html_pdf, nombre, "el PDF de la orden")
    if request.args.get('ver') == '1' and not isinstance(resp, tuple):
        resp.headers['Content-Disposition'] = f'inline; filename="{nombre}"'
    return resp


@app.route('/ordenes/config/pdf_muestra/<empresa>')
@_ruta_oc('editar')
def oc_pdf_muestra(empresa):
    """PDF de muestra (no se guarda nada) para revisar logo, colores, datos y firma de cada empresa."""
    from types import SimpleNamespace as NS
    empresa = empresa.upper() if empresa.upper() in EMPRESAS_OC else 'ANCLAJES'
    tipo = request.args.get('tipo', 'OC') if request.args.get('tipo') in TIPOS_OC else 'OC'
    ahora = hora_peru()
    items = [NS(item=1, descripcion='PERNO HEX GRADO 10.9 UNC M-22 X 70' if tipo == 'OC' else 'VARILLA ROSCADA 5/8 A PEDAZOS DE 30 CM',
                cantidad=150, um='PZA', precio_unitario=1.344, total=201.6, tipo_servicio='CORTE' if tipo == 'OS' else None),
             NS(item=2, descripcion='ARANDELA PLANA AC M-12 GALV. CAL.', cantidad=115, um='PZA', precio_unitario=0.0666, total=7.66,
                tipo_servicio='GALVANIZADO' if tipo == 'OS' else None)]
    sub = round(sum(i.total for i in items), 2)
    o = NS(tipo=tipo, estado='APROBADA', numero=_siguiente_numero_oc(tipo, empresa), empresa=empresa, fecha=ahora.date(), contacto='CONTACTO DE PRUEBA',
           telefono='999 999 999', ruc='20524196205', razon_social='ACEROS IMPORT S.A.C. (MUESTRA)', cotizacion='COT-001', email='ventas@proveedor.pe',
           direccion='CAL. JAVIER HERAUD MZA. M LOTE 5 - LOS OLIVOS', items=items, observaciones=None, subtotal=sub, igv=round(sub * IGV_OC, 2),
           total=round(sub * (1 + IGV_OC), 2), condicion_pago='CONTADO', entrega_tipo='A_TRATAR', entrega_dias=None, fecha_entrega=None,
           entrega_modo='EMPRESA', lugar_recojo=None, moneda='USD', aprobado_por=NS(nombre_completo=session.get('nombre', 'Gerencia')),
           fecha_aprobacion=ahora, creado_por=NS(nombre_completo=session.get('nombre', '')), detraccion_pct=DETRACCION_DEF if tipo == 'OS' else None)
    filas = list(items) + [None] * (22 - len(items))
    html_pdf = render_template('pdf_orden_compra.html', o=o, cfg=_oc_cfg(empresa), logo=_logo_pdf_insumos(empresa), firma=_firma_gerencia_oc(empresa),
                               filas=filas, mon=MONEDAS_OC['USD'], letras=_monto_en_letras(o.total, 'USD'), tipos=TIPOS_OC,
                               igv_pct=int(IGV_OC * 100), tema=TEMAS_PDF_OC[empresa])
    resp = _generar_respuesta_pdf(html_pdf, f'muestra_{tipo}_{empresa.lower()}.pdf', 'el PDF de muestra')
    if not isinstance(resp, tuple):
        resp.headers['Content-Disposition'] = f'inline; filename="muestra_{tipo}_{empresa.lower()}.pdf"'
    return resp


# ---------------------------- PROVEEDORES (lista propia) Y CONTACTOS ----------------------------
def _contacto_json(c):
    guardado = c.fecha_actualizacion or c.fecha_creacion
    return {'id': c.id, 'nombre': c.nombre, 'telefono': c.telefono, 'email': c.email or '', 'cargo': c.cargo or '', 'activo': bool(c.activo),
            'guardado': guardado.strftime('%d/%m/%Y %H:%M') if guardado else '', 'guardado_por': (c.actualizado_por or c.creado_por or ''),
            'editado': bool(c.fecha_actualizacion), 'usos': c.usos or 0,
            'ultimo_uso': c.ultimo_uso.strftime('%d/%m/%Y') if c.ultimo_uso else '', '_orden': (guardado or datetime.min, c.id or 0)}


def _contactos_de(prov, incluir_archivados=False):
    lista = [c for c in OCContacto.query.filter_by(oc_proveedor_id=prov.id).all() if incluir_archivados or c.activo]
    res = [_contacto_json(c) for c in lista]
    res.sort(key=lambda x: (x['activo'], x['_orden']), reverse=True)      # el más reciente primero
    for r in res:
        r.pop('_orden')
    return res


def _proveedor_oc_json(p, con_contactos=True):
    d = {'id': p.id, 'ruc': p.ruc or '', 'razon_social': p.razon_social, 'direccion': p.direccion or '',
         'sunat_estado': p.sunat_estado or '', 'sunat_condicion': p.sunat_condicion or '',
         'sunat_fecha': p.sunat_fecha.strftime('%d/%m/%Y') if p.sunat_fecha else '',
         'ultima': p.ultima_orden.strftime('%d/%m/%Y') if p.ultima_orden else '',
         'extranjero': bool(p.es_extranjero), 'pais': p.pais or ''}
    if con_contactos:
        d['contactos'] = _contactos_de(p)
        d['cuentas'] = _cuentas_de(p.id)
    return d


def _sunat_consulta_externa(numero):
    """Consulta directa a SUNAT/RENIEC (mismo servicio del sistema). Devuelve (datos, error)."""
    url = (f"https://api.decolecta.com/v1/reniec/dni?numero={numero}" if len(numero) == 8
           else f"https://api.decolecta.com/v1/sunat/ruc?numero={numero}")
    try:
        r = requests.get(url, headers={'Authorization': 'Bearer sk_12670.mczJWCBkAFXbV3pYZdD6EoxkwZ7SZSME'}, timeout=6)
        data = r.json()
    except Exception as e:
        return None, f'SUNAT no respondió ({e.__class__.__name__}). Intenta otra vez o escribe los datos a mano.'
    if r.status_code != 200:
        return None, data.get('message', 'No encontrado en SUNAT')
    if len(numero) == 8:
        razon = html.unescape(f"{data.get('nombres', '')} {data.get('apellidoPaterno', '')} {data.get('apellidoMaterno', '')}".strip())
        return ({'razon_social': razon, 'direccion': '', 'estado': '', 'condicion': ''}, None) if razon else (None, 'DNI no encontrado.')
    razon = html.unescape(data.get('razon_social') or data.get('razonSocial') or data.get('nombre') or '')
    if not razon:
        return None, 'No se encontró información para ese RUC.'
    return {'razon_social': razon, 'direccion': html.unescape(data.get('direccion', '') or ''),
            'estado': data.get('estado', '') or '', 'condicion': data.get('condicion', '') or ''}, None


@app.route('/ordenes/api/proveedores')
@_ruta_oc('editar', como_json=True)
def oc_api_proveedores():
    """SOLO la lista propia de proveedores de órdenes (no se mezcla con clientes ni con otros proveedores del sistema)."""
    q = ' '.join((request.args.get('q') or '').split()).upper()
    lista = OCProveedor.query.all()
    # importación: solo proveedores del exterior; compra local: solo los peruanos (RUC / DNI)
    ext = request.args.get('ext') == '1'
    lista = [p for p in lista if bool(p.es_extranjero) == ext]
    if q:
        lista = [p for p in lista if all(t in f"{p.ruc or ''} {p.razon_social} {p.pais or ''}".upper() for t in q.split())]
    lista.sort(key=lambda p: (p.ultima_orden or p.fecha_creacion or datetime.min), reverse=True)
    return {'status': 'success', 'proveedores': [_proveedor_oc_json(p, con_contactos=False) for p in lista[:25]]}


@app.route('/ordenes/api/proveedor_ext', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_api_proveedor_ext():
    """Registra (o corrige) un proveedor del EXTERIOR en la lista propia: Tax ID / N° de registro, razón social, país y dirección.
    No pasa por SUNAT. Luego se le agregan contactos y cuentas (SWIFT) como a cualquier proveedor."""
    f = request.form
    tax = re.sub(r'[^0-9A-Za-z]', '', f.get('tax_id') or '').upper()[:20]
    razon = ' '.join((f.get('razon_social') or '').split()).upper()[:200]
    pais = ' '.join((f.get('pais') or '').split()).upper()[:60]
    direccion = ' '.join((f.get('direccion') or '').split())[:250]
    if len(tax) < 3:
        return {'status': 'error', 'msg': 'Escribe el Tax ID / N° de registro del proveedor (mínimo 3 letras o números).'}
    if len(razon) < 3:
        return {'status': 'error', 'msg': 'Escribe la razón social del proveedor.'}
    if not pais:
        return {'status': 'error', 'msg': 'Escribe el país del proveedor.'}
    p = next((x for x in OCProveedor.query.filter(OCProveedor.ruc == tax).all()), None)
    ahora = hora_peru()
    if p and not p.es_extranjero:
        return {'status': 'error', 'msg': f'Ese número ya está registrado como proveedor peruano ({p.razon_social}).'}
    if p:
        p.razon_social, p.pais, p.direccion = razon, pais, direccion or p.direccion
        p.actualizado_por, p.fecha_actualizacion = session.get('nombre', ''), ahora
        msg = 'Proveedor del exterior actualizado.'
    else:
        p = OCProveedor(ruc=tax, razon_social=razon, direccion=direccion or None, pais=pais, es_extranjero=True,
                        creado_por=session.get('nombre', ''), fecha_creacion=ahora)
        db.session.add(p)
        msg = 'Proveedor del exterior guardado en la lista.'
    db.session.flush()
    registrar_log(f"Guardó el proveedor del exterior {razon} ({pais}, Tax ID {tax})", 'bi-globe-americas', 'text-primary')
    db.session.commit()
    return {'status': 'success', 'msg': msg, 'proveedor': _proveedor_oc_json(p)}


@app.route('/ordenes/api/proveedor/<int:prov_id>')
@_ruta_oc('editar', como_json=True)
def oc_api_proveedor(prov_id):
    return {'status': 'success', 'proveedor': _proveedor_oc_json(OCProveedor.query.get_or_404(prov_id))}


@app.route('/ordenes/api/sunat', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_api_sunat():
    """Busca el RUC en la lista propia; si no está (o se pide actualizar), lo consulta en SUNAT y lo GUARDA en la lista."""
    numero = re.sub(r'\D', '', request.form.get('numero') or '')
    if len(numero) not in (8, 11):
        return {'status': 'error', 'msg': 'Escribe un RUC de 11 dígitos (o DNI de 8).'}
    p = OCProveedor.query.filter(OCProveedor.ruc == numero).first()
    if p and request.form.get('actualizar') != '1':
        return {'status': 'success', 'origen': 'LISTA', 'proveedor': _proveedor_oc_json(p)}
    datos, err = _sunat_consulta_externa(numero)
    if err:
        return {'status': 'error', 'msg': err}
    ahora = hora_peru()
    nuevo = p is None
    if nuevo:
        p = OCProveedor(ruc=numero, razon_social=datos['razon_social'], creado_por=session.get('nombre', ''), fecha_creacion=ahora)
        db.session.add(p)
    else:
        p.actualizado_por, p.fecha_actualizacion = session.get('nombre', ''), ahora
    p.razon_social = datos['razon_social'][:200]
    p.direccion = (datos['direccion'] or p.direccion or '')[:250] or None
    p.sunat_estado, p.sunat_condicion, p.sunat_fecha = datos['estado'][:50] or None, datos['condicion'][:50] or None, ahora
    registrar_log(f"{'Agregó' if nuevo else 'Actualizó desde SUNAT'} el proveedor de órdenes {numero} {p.razon_social}", 'bi-building-add', 'text-info')
    db.session.commit()
    return {'status': 'success', 'origen': 'SUNAT', 'nuevo': nuevo, 'proveedor': _proveedor_oc_json(p)}


@app.route('/ordenes/api/contacto', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_api_contacto():
    """Guardar (nuevo o editar), archivar, restaurar o borrar un contacto. Devuelve la lista actualizada del proveedor."""
    f = request.form
    accion = f.get('accion', 'guardar')
    ahora, quien = hora_peru(), session.get('nombre', '')
    if accion == 'guardar':
        prov = OCProveedor.query.get(f.get('oc_proveedor_id', type=int)) if f.get('oc_proveedor_id', type=int) else None
        c = OCContacto.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
        if c:
            prov = OCProveedor.query.get(c.oc_proveedor_id)
        if not prov:
            return {'status': 'error', 'msg': 'Primero elige o busca el proveedor.'}
        nombre, telefono = _limpio(f.get('nombre'), 120), _limpio(f.get('telefono'), 40)
        email, cargo = _limpio(f.get('email'), 120).lower(), _limpio(f.get('cargo'), 80)
        if len(nombre) < 3:
            return {'status': 'error', 'msg': 'Escribe el nombre del contacto.'}
        if len(re.sub(r'\D', '', telefono)) < 6:
            return {'status': 'error', 'msg': 'Escribe el teléfono (mínimo 6 dígitos).'}
        if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return {'status': 'error', 'msg': 'El correo no es válido.'}
        repetido = next((x for x in OCContacto.query.filter_by(oc_proveedor_id=prov.id).all()
                         if x.id != (c.id if c else 0) and (x.nombre or '').upper() == nombre.upper() and x.telefono == telefono), None)
        if repetido:
            return {'status': 'error', 'msg': f'Ese contacto ya está guardado ({repetido.nombre} · {repetido.telefono}).'}
        if c:
            antes = f"{c.nombre} · {c.telefono} · {c.email or '-'}"
            c.nombre, c.telefono, c.email, c.cargo = nombre, telefono, email or None, cargo or None
            c.actualizado_por, c.fecha_actualizacion = quien, ahora
            registrar_log(f"Editó el contacto de {prov.razon_social}: {antes} → {nombre} · {telefono} · {email or '-'}", 'bi-person-lines-fill', 'text-warning')
        else:
            c = OCContacto(oc_proveedor_id=prov.id, nombre=nombre, telefono=telefono, email=email or None, cargo=cargo or None,
                           activo=True, creado_por=quien, fecha_creacion=ahora, usos=0)
            db.session.add(c)
            registrar_log(f"Guardó el contacto {nombre} ({telefono}) de {prov.razon_social}", 'bi-person-plus', 'text-info')
        db.session.commit()
        return {'status': 'success', 'contacto_id': c.id, 'contactos': _contactos_de(prov, f.get('todos') == '1')}
    c = OCContacto.query.get_or_404(f.get('id', type=int))
    prov = OCProveedor.query.get(c.oc_proveedor_id)
    if accion == 'archivar':
        c.activo, c.archivado_por, c.fecha_archivo = False, quien, ahora
        registrar_log(f"Archivó el contacto {c.nombre} de {prov.razon_social}", 'bi-archive', 'text-secondary')
    elif accion == 'restaurar':
        c.activo, c.archivado_por, c.fecha_archivo = True, None, None
    elif accion == 'borrar':
        if session.get('role') != 'admin':
            return {'status': 'error', 'msg': 'Solo Gerencia puede borrar definitivamente. Archívalo para que no aparezca.'}
        if (c.usos or 0) > 0 or OrdenCompra.query.filter_by(contacto_id=c.id).first():
            return {'status': 'error', 'msg': 'Este contacto ya se usó en órdenes: no se borra (se perdería el historial). Archívalo.'}
        registrar_log(f"Borró el contacto {c.nombre} de {prov.razon_social}", 'bi-trash', 'text-danger')
        db.session.delete(c)
    db.session.commit()
    return {'status': 'success', 'contactos': _contactos_de(prov, f.get('todos') == '1')}


# ---------------------------- BUSCADOR DE PRODUCTOS (con Familia y Calidad, como en los inventarios) ----------------------------
def _catalogo_productos_oc(empresa):
    """Productos activos de los dos inventarios unidos por SKU, con el stock de cada empresa."""
    datos = {}
    for origen, Modelo in (('ANCLAJES', Product), ('IMPORTBOLTS', ProductImportBolts)):
        q = Modelo.query.filter(Modelo.activo.is_(True))
        if Modelo is Product:
            q = q.filter(Product.es_shadow_importbolts.isnot(True))
        for p in q.all():
            d = datos.setdefault((p.sku or '').upper(), {'sku': p.sku, 'descripcion': p.nombre, 'familia': p.categoria or '', 'calidad': p.calidad or '',
                                                       'estado': p.estado or '', 'stock_ANCLAJES': None, 'stock_IMPORTBOLTS': None,
                                                       'peso': getattr(p, 'peso_kg', None) or None})
            d[f'stock_{origen}'] = p.stock_actual or 0
            if origen == empresa:
                d.update(descripcion=p.nombre, familia=p.categoria or '', calidad=p.calidad or '', estado=p.estado or '',
                         peso=getattr(p, 'peso_kg', None) or d.get('peso'))
    return list(datos.values())


@app.route('/ordenes/api/productos')
@_ruta_oc('buscar', como_json=True)
def oc_api_productos():
    """Búsqueda de productos que ya tenemos: texto + Familia + Calidad (filtros flexibles, igual que en los inventarios).
    Devuelve también las familias y calidades disponibles según lo ya elegido, el stock en Anclajes e Import Bolts
    y el último precio pagado en una orden."""
    q = ' '.join((request.args.get('q') or '').split()).upper()
    familia = (request.args.get('familia') or '').strip().upper()
    calidad = (request.args.get('calidad') or '').strip().upper()
    empresa = (request.args.get('empresa') or 'ANCLAJES').upper()
    empresa = empresa if empresa in EMPRESAS_OC else 'ANCLAJES'
    terminos = q.split()
    es_insumos = request.args.get('destino') == 'INSUMOS'
    if es_insumos:
        # Todos los insumos del maestro (también los que no tienen stock: se compra justamente para reponer)
        stocks, stocks_emp = {}, {}
        for st in InsumoStock.query.all():
            stocks_emp.setdefault(st.insumo_id, {})[st.empresa] = st.stock_actual or 0
            if st.empresa == empresa:
                stocks[st.insumo_id] = st
        base = [{'sku': i.codigo, 'descripcion': i.descripcion, 'familia': i.categoria or '', 'calidad': '', 'um': i.unidad or '',
                 'insumo_id': i.id, 'origen': 'INSUMO', 'stock_insumo': (stocks[i.id].stock_actual or 0) if i.id in stocks else 0,
                 'costo_insumo': (stocks[i.id].costo_promedio or 0) if i.id in stocks else 0,
                 'minimo_insumo': (stocks[i.id].stock_minimo or 0) if i.id in stocks else 0,
                 'stocks_ins': {e: stocks_emp.get(i.id, {}).get(e, 0) for e in EMPRESAS_INSUMOS}}
                for i in Insumo.query.all() if i.activo is not False]
    else:
        base = _catalogo_productos_oc(empresa)
        for d in base:
            d['origen'] = empresa if d[f'stock_{empresa}'] is not None else 'IMPORTBOLTS' if empresa == 'ANCLAJES' else 'ANCLAJES'
            d['en_empresa'] = d[f'stock_{empresa}'] is not None
        if request.args.get('solo_empresa') == '1':       # compras: solo lo que existe en el inventario de la empresa
            base = [d for d in base if d['en_empresa']]
    por_texto = [d for d in base if all(t in f"{d['sku']} {d['descripcion']} {d.get('estado', '')}".upper() for t in terminos)]
    con_familia = [d for d in por_texto if not familia or familia in d['familia'].upper()]
    con_calidad = [d for d in por_texto if not calidad or calidad in d['calidad'].upper()]
    res = [d for d in con_familia if not calidad or calidad in d['calidad'].upper()]
    familias = sorted({d['familia'] for d in con_calidad if d['familia']})
    calidades = sorted({d['calidad'] for d in con_familia if d['calidad']})
    total = len(res)
    if not (terminos or familia or calidad or es_insumos):
        res = []
    # por páginas: todo el resultado se puede recorrer (no se corta en 40)
    por_pagina = min(max(request.args.get('por_pagina', 25, type=int), 5), 60)
    paginas = max(1, -(-len(res) // por_pagina))
    pagina = min(max(request.args.get('pagina', 1, type=int), 1), paginas)
    res = sorted(res, key=lambda d: (d['sku'] or '').upper())[(pagina - 1) * por_pagina: pagina * por_pagina]
    if res:
        codigos = {d['sku'] for d in res}
        ultimos = {}
        for it in (OrdenCompraItem.query.join(OrdenCompra, OrdenCompra.id == OrdenCompraItem.orden_id)
                   .filter(OrdenCompraItem.codigo.in_(list(codigos)), OrdenCompra.estado.notin_(['ANULADA', 'RECHAZADA']))
                   .order_by(OrdenCompra.fecha.desc(), OrdenCompra.id.desc()).all()):
            if it.codigo not in ultimos:
                ultimos[it.codigo] = {'precio': it.precio_unitario, 'um': it.um, 'moneda': MONEDAS_OC[it.orden.moneda]['simbolo'],
                                      'orden': _oc_codigo(it.orden), 'proveedor': it.orden.razon_social}
        for d in res:
            if d['sku'] in ultimos and session.get('role') in ROLES_OC_VEN:      # el último precio solo lo ve quien ve las órdenes
                d['ultimo'] = ultimos[d['sku']]
    return {'results': res, 'total': total, 'familias': familias, 'calidades': calidades, 'pagina': pagina, 'paginas': paginas, 'por_pagina': por_pagina,
            'insumos': es_insumos}


# ---------------------------- CONFIGURACIÓN ----------------------------
@app.route('/ordenes/config')
@_ruta_oc('editar')
def oc_config():
    es_admin = session.get('role') == 'admin'
    conteo = None
    if es_admin:
        conteo = {'ordenes': OrdenCompra.query.count(), 'documentos': OrdenCompraDocumento.query.count(),
                  'proveedores': OCProveedor.query.count(), 'contactos': OCContacto.query.count(),
                  'cuentas': OCCuentaBancaria.query.count(), 'requerimientos': RequerimientoCompra.query.count(),
                  'docs_req': RequerimientoDocumento.query.count(), **_oc_vinculos_fuera()}
    uso_um = {}
    for (um, n) in db.session.query(OrdenCompraItem.um, func.count(OrdenCompraItem.id)).group_by(OrdenCompraItem.um).all():
        uso_um[um] = n
    uso_cond = {}
    for (c, n) in db.session.query(OrdenCompra.condicion_pago, func.count(OrdenCompra.id)).group_by(OrdenCompra.condicion_pago).all():
        uso_cond[c] = n
    motivos = {u: _oc_motivos(u, incluir_inactivos=True) for u in USOS_MOTIVO_OC}
    uso_motivo = {}
    for o in OrdenCompra.query.all():
        if o.rechazo_opcion:
            k = ('RECHAZO', o.rechazo_categoria, o.rechazo_opcion)
            uso_motivo[k] = uso_motivo.get(k, 0) + 1
        if o.anulacion_opcion:
            k = ('ANULACION', o.anulacion_categoria, o.anulacion_opcion)
            uso_motivo[k] = uso_motivo.get(k, 0) + 1
    ordenes_prov = {}
    for o in OrdenCompra.query.filter(OrdenCompra.oc_proveedor_id.isnot(None)).all():
        ordenes_prov[o.oc_proveedor_id] = ordenes_prov.get(o.oc_proveedor_id, 0) + 1
    contactos_prov = {}
    for c in OCContacto.query.all():
        contactos_prov.setdefault(c.oc_proveedor_id, []).append(c)
    uso_area, uso_sol, uso_mc = {}, {}, {}
    for o in OrdenCompra.query.all():
        if o.area_solicitante:
            uso_area[o.area_solicitante] = uso_area.get(o.area_solicitante, 0) + 1
        if o.solicitante_nombre and not o.solicitante_user_id:
            uso_sol[o.solicitante_nombre] = uso_sol.get(o.solicitante_nombre, 0) + 1
        if o.motivo_compra:
            uso_mc[o.motivo_compra] = uso_mc.get(o.motivo_compra, 0) + 1
    uso_serv = {}
    for (sv, n) in db.session.query(OrdenCompraItem.tipo_servicio, func.count(OrdenCompraItem.id)).group_by(OrdenCompraItem.tipo_servicio).all():
        if sv:
            uso_serv[sv] = n
    cuentas_prov = {}
    for cu in OCCuentaBancaria.query.all():
        cuentas_prov.setdefault(cu.oc_proveedor_id, []).append(_cuenta_json(cu))
    return render_template('oc_config.html', catalogos={t: _oc_catalogo(t, incluir_inactivos=True) for t in CATALOGOS_OC},
                           motivos=motivos, uso_motivo=uso_motivo, ordenes_prov=ordenes_prov, contactos_prov=contactos_prov,
                           cuentas_prov=cuentas_prov, bancos=BANCOS_OC, usos_motivo=USOS_MOTIVO_OC, aplica_motivo=APLICA_MOTIVO_OC, tipos_cuenta=TIPOS_CUENTA_OC, monedas=MONEDAS_OC,
                           motivos_compra=sorted(OCMotivoCompra.query.all(), key=lambda m: m.id), uso_mc=uso_mc,
                           nombres_catalogo=CATALOGOS_OC, uso={'OC_UM': uso_um, 'OC_CONDICION_PAGO': uso_cond, 'OC_AREA': uso_area, 'OC_SOLICITANTE': uso_sol, 'OC_SERVICIO': uso_serv},
                           cfgs={e: _oc_cfg(e) for e in EMPRESAS_OC}, cfg_defs=OC_CONFIG_DEFS, etiquetas=OC_CONFIG_ETIQUETAS, es_admin=es_admin,
                           conteo=conteo, empresas_oc=EMPRESAS_OC, empresa_cfg=request.args.get('empresa') if request.args.get('empresa') in EMPRESAS_OC else 'ANCLAJES',
                           siguientes={e: {t: _oc_numero_txt(None, _siguiente_numero_oc(t, e), e) for t in TIPOS_OC} for e in EMPRESAS_OC}, tipos=TIPOS_OC,
                           proveedores=sorted(OCProveedor.query.all(), key=lambda p: _clave_alfabetica(p.razon_social or '')),
                           tab=request.args.get('tab', 'OC_UM'), seccion='config')


@app.route('/ordenes/config/catalogo', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_config_catalogo():
    """U.M. y condiciones de pago: agregar, renombrar, activar/desactivar y borrar. Las órdenes ya hechas guardan su texto,
    así que cambiar o borrar una opción no altera órdenes anteriores."""
    f = request.form
    accion = f.get('accion')
    if accion in ('toggle', 'editar', 'borrar'):
        v = CatalogoValor.query.get_or_404(f.get('id', type=int))
        if v.tipo not in CATALOGOS_OC:
            return {'status': 'error', 'msg': 'No autorizado'}, 403
        if accion == 'toggle':
            v.activo = not v.activo
        elif accion == 'borrar':
            registrar_log(f"Borró de {CATALOGOS_OC[v.tipo]} (órdenes): {v.valor}", 'bi-trash', 'text-danger')
            db.session.delete(v)
        else:
            nuevo = ' '.join((f.get('valor') or '').split()).upper()[:100]
            if not nuevo:
                return {'status': 'error', 'msg': 'Escribe el nuevo nombre.'}
            if any(x.id != v.id and (x.valor or '').upper() == nuevo for x in CatalogoValor.query.filter_by(tipo=v.tipo).all()):
                return {'status': 'error', 'msg': f'"{nuevo}" ya existe.'}
            registrar_log(f"Renombró en {CATALOGOS_OC[v.tipo]} (órdenes): {v.valor} → {nuevo}", 'bi-pencil', 'text-warning')
            v.valor = nuevo
        db.session.commit()
        return {'status': 'success'}
    tipo = (f.get('tipo') or '').upper()
    valor = ' '.join((f.get('valor') or '').split()).upper()[:100]
    if tipo not in CATALOGOS_OC or not valor:
        return {'status': 'error', 'msg': 'Escribe un valor.'}
    if any((x.valor or '').upper() == valor for x in CatalogoValor.query.filter_by(tipo=tipo).all()):
        return {'status': 'error', 'msg': f'"{valor}" ya existe.'}
    db.session.add(CatalogoValor(tipo=tipo, valor=valor, activo=True, es_predeterminado=False, creado_por_id=session.get('user_id')))
    db.session.commit()
    return {'status': 'success'}


@app.route('/ordenes/config/proveedor', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_config_proveedor():
    f = request.form
    p = OCProveedor.query.get_or_404(f.get('id', type=int))
    if f.get('accion') == 'borrar':
        if session.get('role') != 'admin':
            return {'status': 'error', 'msg': 'Solo Gerencia puede borrar un proveedor.'}
        n = OrdenCompra.query.filter(OrdenCompra.oc_proveedor_id == p.id).count()
        if n:
            return {'status': 'error', 'msg': f'{p.razon_social} tiene {n} orden(es): no se borra para no perder el historial.'}
        OCContacto.query.filter_by(oc_proveedor_id=p.id).delete(synchronize_session=False)
        OCCuentaBancaria.query.filter_by(oc_proveedor_id=p.id).delete(synchronize_session=False)
        registrar_log(f"Borró el proveedor de órdenes {p.ruc} {p.razon_social}", 'bi-trash', 'text-danger')
        db.session.delete(p)
        db.session.commit()
        return {'status': 'success'}
    if p.sunat_fecha:
        return {'status': 'error', 'msg': 'Sus datos vienen de SUNAT: no se editan a mano. Usa "Actualizar SUNAT".'}
    razon = _limpio(f.get('razon_social'), 200)
    if len(razon) < 3:
        return {'status': 'error', 'msg': 'Escribe la razón social.'}
    p.razon_social, p.direccion = razon, _limpio(f.get('direccion'), 250) or None
    p.actualizado_por, p.fecha_actualizacion = session.get('nombre', ''), hora_peru()
    db.session.commit()
    return {'status': 'success'}


@app.route('/ordenes/config/motivo', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_config_motivo():
    """Motivos de rechazo y de anulación por categoría (para OC, OS o ambas): agregar, editar, activar/desactivar y borrar."""
    f = request.form
    accion = f.get('accion', 'guardar')
    m = OCMotivoRechazo.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    if accion in ('toggle', 'borrar'):
        if not m:
            return {'status': 'error', 'msg': 'No existe.'}
        if accion == 'toggle':
            m.activo = not m.activo
        else:
            registrar_log(f"Borró el motivo de {USOS_MOTIVO_OC.get(m.uso or 'RECHAZO', '').lower()} {m.categoria} · {m.motivo}", 'bi-trash', 'text-danger')
            db.session.delete(m)
        db.session.commit()
        return {'status': 'success'}
    categoria = ' '.join((f.get('categoria') or '').split()).upper()[:60]
    motivo = ' '.join((f.get('motivo') or '').split())[:150]
    if len(categoria) < 2 or len(motivo) < 3:
        return {'status': 'error', 'msg': 'Escribe la categoría y el motivo.'}
    motivo = motivo[0].upper() + motivo[1:]
    uso = (f.get('uso') or (m.uso if m else None) or 'RECHAZO').upper()
    aplica = (f.get('aplica') or (m.aplica if m else None) or 'AMBAS').upper()
    if uso == 'DESCARTE':
        aplica = 'RQ'       # descartar es solo para productos de requerimientos
    if uso not in USOS_MOTIVO_OC or aplica not in APLICA_MOTIVO_OC:
        return {'status': 'error', 'msg': 'Elige para qué es el motivo.'}
    if any(x.id != (m.id if m else 0) and (x.uso or 'RECHAZO') == uso and x.categoria == categoria and x.motivo.upper() == motivo.upper()
           for x in OCMotivoRechazo.query.all()):
        return {'status': 'error', 'msg': 'Ese motivo ya existe en esa categoría.'}
    if not m:
        m = OCMotivoRechazo(activo=True)
        db.session.add(m)
    m.categoria, m.motivo, m.uso, m.aplica = categoria, motivo, uso, aplica
    db.session.commit()
    return {'status': 'success'}


@app.route('/ordenes/config/motivo_compra', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_config_motivo_compra():
    """Motivos de compra (para qué se compra): agregar, renombrar, pedir cliente sí/no, activar/desactivar y borrar."""
    f = request.form
    accion = f.get('accion', 'guardar')
    m = OCMotivoCompra.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    if accion in ('toggle', 'cliente', 'borrar'):
        if not m:
            return {'status': 'error', 'msg': 'No existe.'}
        if accion == 'toggle':
            m.activo = not m.activo
        elif accion == 'cliente':
            m.pide_cliente = not m.pide_cliente
        else:
            registrar_log(f"Borró el motivo de compra {m.nombre}", 'bi-trash', 'text-danger')
            db.session.delete(m)
        db.session.commit()
        return {'status': 'success'}
    nombre = ' '.join((f.get('nombre') or '').split()).upper()[:120]
    if len(nombre) < 3:
        return {'status': 'error', 'msg': 'Escribe el motivo.'}
    if any(x.id != (m.id if m else 0) and (x.nombre or '').upper() == nombre for x in OCMotivoCompra.query.all()):
        return {'status': 'error', 'msg': f'"{nombre}" ya existe.'}
    if not m:
        m = OCMotivoCompra(activo=True, pide_cliente=f.get('pide_cliente') == '1')
        db.session.add(m)
    m.nombre = nombre
    db.session.commit()
    return {'status': 'success'}


@app.route('/ordenes/config/datos', methods=['POST'])
@_ruta_oc('admin')
def oc_config_datos():
    """Datos de la empresa, textos del PDF y numeración (solo Gerencia). Cada empresa tiene los suyos."""
    empresa = (request.form.get('empresa') or 'ANCLAJES').upper()
    empresa = empresa if empresa in EMPRESAS_OC else 'ANCLAJES'
    destino = url_for('oc_config', tab='datos', empresa=empresa)
    defs = OC_CONFIG_DEFS[empresa]
    if request.form.get('accion') == 'restablecer':
        for clave in defs:
            c = OCConfig.query.get(_oc_clave_cfg(empresa, clave))
            if c:
                db.session.delete(c)
        db.session.commit()
        flash(f'✅ Datos del PDF de {EMPRESAS_OC[empresa]["corto"]} restablecidos a los valores iniciales.')
        return redirect(destino)
    for clave in defs:
        valor = (request.form.get(clave) or '').strip()
        valor = '\n'.join(' '.join(l.split()) for l in valor.splitlines() if l.strip()) if clave in ('terminos', 'horario', 'imp_condiciones', 'imp_pagos') else ' '.join(valor.split())
        if clave == 'lugar_entrega' and len(valor) < 5:
            flash('⛔ El lugar de entrega no puede quedar vacío.')
            return redirect(destino)
        c = OCConfig.query.get(_oc_clave_cfg(empresa, clave))
        if valor == defs[clave]:
            if c:
                db.session.delete(c)
            continue
        if not c:
            c = OCConfig(clave=_oc_clave_cfg(empresa, clave))
            db.session.add(c)
        c.valor, c.actualizado_por, c.fecha = valor[:3000], session.get('nombre', ''), hora_peru()
    # Numeración: "el siguiente número será..." (solo sirve para avanzar; nunca repite un número ya usado)
    for t in TIPOS_OC:
        txt = re.sub(r'\D', '', request.form.get(f'num_{t}') or '')
        c = OCConfig.query.get(_oc_clave_cfg(empresa, f'num_{t}'))
        if not txt:
            if c:
                db.session.delete(c)
            continue
        if not 1 <= int(txt) <= 999999:
            flash('⛔ El número debe estar entre 1 y 999999.')
            return redirect(destino)
        if not c:
            c = OCConfig(clave=_oc_clave_cfg(empresa, f'num_{t}'))
            db.session.add(c)
        c.valor, c.actualizado_por, c.fecha = str(int(txt)), session.get('nombre', ''), hora_peru()
    registrar_log(f"Actualizó los datos del PDF de órdenes de {EMPRESAS_OC[empresa]['corto']}", 'bi-gear', 'text-info')
    db.session.commit()
    flash(f'✅ Datos del PDF de {EMPRESAS_OC[empresa]["corto"]} guardados.')
    return redirect(destino)


