# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · v38 VISTA PREVIA Y EXCEL DE LA ORDEN
# - Vista previa ANTES de guardar: con lo que está escrito en el formulario se arma la orden en memoria (NO se guarda
#   nada y NO se gasta ningún número) y se muestra como se vería el PDF (rápida, en la misma página), el PDF real o un Excel.
# - Excel de una orden ya guardada: el mismo contenido del PDF, con su número real.
# NÚMERO CORRELATIVO: una orden nueva que todavía no se guarda sale con N° AAAA-00000 y la franja "VISTA PREVIA"
#   (el número se asigna recién al guardar). Al editar, sale con su número (si se cambia de empresa: 00000, porque
#   al guardar tomará el siguiente de la otra empresa).
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================

AVISO_VISTA_PREVIA_OC = 'VISTA PREVIA — todavía NO está guardada. El N° se asigna al guardar (por eso sale 00000).'
_CAMPOS_ORDEN_PREVIA = ('ruc', 'razon_social', 'direccion', 'contacto', 'telefono', 'email', 'cotizacion', 'moneda', 'condicion_pago',
                        'entrega_modo', 'lugar_recojo', 'entrega_tipo', 'entrega_dias', 'fecha_entrega', 'observaciones', 'subtotal', 'igv',
                        'total', 'detraccion_pct', 'es_importacion', 'condiciones_comerciales', 'pagos_importacion', 'precios_con_igv', 'destino')


def _oc_ctx_pdf(o, empresa, firma=None, **extra):
    """Lo que necesita pdf_orden_compra.html (el mismo PDF de siempre: oc_pdf)."""
    mon = MONEDAS_OC.get(o.moneda) or MONEDAS_OC['PEN']
    items = list(o.items)
    return dict(o=o, cfg=_oc_cfg(empresa), logo=_logo_pdf_insumos(empresa), firma=firma,
                filas=items + [None] * max(0, 22 - len(items)), mon=mon, letras=_monto_en_letras(o.total, o.moneda if o.moneda in MONEDAS_OC else 'PEN'),
                tipos=TIPOS_OC, igv_pct=int(IGV_OC * 100), tema=TEMAS_PDF_OC.get(empresa, TEMAS_PDF_OC['ANCLAJES']), **extra)


def _oc_desde_form(f):
    """La orden armada EN MEMORIA con lo escrito en el formulario (no toca la base de datos ni el correlativo).
    Devuelve (orden, empresa, avisos): avisos = lo que habría que corregir al guardar (la vista previa igual se arma)."""
    from types import SimpleNamespace as NS
    orden = OrdenCompra.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    datos, items, errores = _leer_orden_form(f, orden)
    db.session.rollback()          # por si acaso: la vista previa nunca deja nada pendiente en la sesión
    empresa = datos.get('empresa') if datos.get('empresa') in EMPRESAS_OC else 'ANCLAJES'
    tipo = datos.get('tipo') if datos.get('tipo') in TIPOS_OC else 'OC'
    d = {c: (datos.get(c) if datos.get(c) != '' else None) for c in _CAMPOS_ORDEN_PREVIA}
    d['moneda'] = d['moneda'] if d['moneda'] in MONEDAS_OC else ('USD' if d.get('es_importacion') else 'PEN')
    d['es_importacion'] = bool(d.get('es_importacion'))
    d['razon_social'] = d['razon_social'] or (f.get('razon_social') or '').strip().upper() or '(SIN PROVEEDOR)'
    for c in ('subtotal', 'igv', 'total'):
        d[c] = d[c] or 0
    fecha = datos.get('fecha') if hasattr(datos.get('fecha'), 'strftime') else hora_peru().date()
    misma_emp = orden is not None and (orden.empresa or 'ANCLAJES') == empresa
    if orden is not None and orden.estado in ESTADOS_REEDITABLES_OC:
        revision = (orden.revision or 0) + 1          # al guardar sube la revisión (vuelve a Gerencia)
    else:
        revision = orden.revision if orden is not None else None
    creado = orden.creado_por if orden is not None and orden.creado_por else NS(nombre_completo=session.get('nombre', ''))
    o = NS(id=orden.id if orden is not None else None, tipo=tipo, empresa=empresa, numero=orden.numero if misma_emp else 0,
           estado='BORRADOR', fecha=fecha, revision=revision, creado_por=creado, aprobado_por=None, fecha_aprobacion=None,
           items=[NS(item=n, **it) for n, it in enumerate(items, start=1)], **d)
    avisos = [e for e in errores if e]
    return o, empresa, avisos


def _oc_nombre_archivo(o, empresa, ext, vista_previa=False):
    base = f"{o.tipo}_{secure_filename(empresa.title())}_{_oc_numero_txt(o)}_{secure_filename(o.razon_social or '')[:30]}"
    return f"{'VISTA_PREVIA_' if vista_previa else ''}{base}.{ext}"


def _pdf_bytes_oc(html_pdf):
    """PDF en bytes (o None si xhtml2pdf no pudo): mismo arreglo de celdas vacías que _generar_respuesta_pdf."""
    html_pdf = re.sub(r'(<t[dh]\b[^>]*>)(</t[dh]>)', r'\1&nbsp;\2', html_pdf)
    buf = io.BytesIO()
    try:
        res = pisa.CreatePDF(src=html_pdf, dest=buf, encoding='utf-8')
    except Exception:
        app.logger.exception('Vista previa OC: no se pudo maquetar el PDF')
        return None
    return None if res.err else buf.getvalue()


# ---------------------------- EXCEL (mismo contenido del PDF) ----------------------------
def _oc_excel_bytes(o, empresa, firma=None, banner=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    cfg = _oc_cfg(empresa)
    tema = TEMAS_PDF_OC.get(empresa, TEMAS_PDF_OC['ANCLAJES'])
    mon = MONEDAS_OC.get(o.moneda) or MONEDAS_OC['PEN']
    simb = mon['simbolo']
    imp = bool(o.es_importacion)
    hx = lambda c: (c or '#000000').lstrip('#').upper()
    relleno = lambda c: PatternFill('solid', start_color=hx(c), end_color=hx(c))
    fino, negro = Side(style='thin', color='111111'), Side(style='medium', color=hx(tema['azul']))
    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r'[\\/*?:\[\]]', '-', f"{o.tipo} {_oc_numero_txt(o)}")[:31]
    ws.sheet_view.showGridLines = False
    if imp:
        cols, anchos = ['ITEM', 'DESCRIPCIÓN', 'QUANTITY (PCS)', 'KGS/ 1000PCS', 'TOTAL KGS', 'USD/PCS', 'AMOUNT/USD'], [19, 44, 14, 13, 12, 14, 16]
    else:
        cols, anchos = ['ITEM', 'DESCRIPCIÓN', 'CANTIDAD', 'U.M.', 'P. UNIT.', 'TOTAL'], [19, 56, 13, 8, 14, 16]
    nc = len(cols)
    L = get_column_letter(nc)
    for i, w in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    base_font = 'Arial'
    F = lambda **k: Font(name=base_font, size=k.pop('size', 9), **k)
    fila = [1]

    def celda(col, valor=None, fuente=None, alinear=None, formato=None, fondo=None, borde=None, hasta=None):
        c = ws.cell(row=fila[0], column=col)
        if hasta and hasta > col:
            ws.merge_cells(start_row=fila[0], start_column=col, end_row=fila[0], end_column=hasta)
        if valor is not None:
            c.value = valor
        c.font = fuente or F()
        c.alignment = alinear or Alignment(vertical='top', wrap_text=True)
        if formato:
            c.number_format = formato
        if fondo:
            for k in range(col, (hasta or col) + 1):
                ws.cell(row=fila[0], column=k).fill = relleno(fondo)
        if borde:
            for k in range(col, (hasta or col) + 1):
                ws.cell(row=fila[0], column=k).border = borde
        return c

    def linea():
        for k in range(1, nc + 1):
            ws.cell(row=fila[0], column=k).border = Border(bottom=negro)
        ws.row_dimensions[fila[0]].height = 6
        fila[0] += 1

    centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
    # ---- ENCABEZADO: logo · empresa · caja RUC / tipo / N° ----
    caja_ini = nc - 1
    logo = _logo_pdf_insumos(empresa)
    if logo:
        try:
            from openpyxl.drawing.image import Image as XLImage
            img = XLImage(io.BytesIO(base64.b64decode(logo['uri'].split(',', 1)[1])))
            esc = min(1.0, 72 / float(logo['alto'] or 72), 150 / float(logo['ancho'] or 150))
            img.width, img.height = int(logo['ancho'] * esc), int(logo['alto'] * esc)
            ws.add_image(img, 'A1')
        except Exception:
            app.logger.exception('Excel OC: no se pudo poner el logo')
    textos = [(cfg.get('razon_social', ''), F(size=13, bold=True)), (cfg.get('direccion', ''), F(size=7.5, bold=True, color=hx(tema['azul']))),
              (cfg.get('email', ''), F(size=8, underline='single', color=hx(tema['azul']))), (f"tef  {cfg.get('telefono', '')}", F(size=7.5, bold=True, color=hx(tema['azul'])))]
    caja = [(f"RUC: {cfg.get('ruc') or '-'}", F(size=10.5), None, Border(top=fino, left=fino, right=fino)),
            (TIPOS_OC.get(o.tipo, o.tipo).upper() + ('\nIMPORTACIÓN' if imp else ''), F(size=11 if not imp else 10, bold=True, color='FFFFFF'), tema['caja'], Border(left=fino, right=fino)),
            (f"N° {_oc_numero_txt(o)}" + (f" · Rev. {o.revision}" if getattr(o, 'revision', None) else ''), F(size=11, bold=True), None, Border(bottom=fino, left=fino, right=fino))]
    for i in range(4):
        ws.row_dimensions[fila[0]].height = 30 if (imp and i == 1) else 19
        celda(2, textos[i][0], textos[i][1], centro, hasta=caja_ini - 1)
        if i < 3:
            t, fu, fo, bo = caja[i]
            celda(caja_ini, t, fu, centro, fondo=fo, borde=bo, hasta=nc)
        fila[0] += 1
    # ---- franja: vista previa / estado ----
    estado_txt = {'RECHAZADA': ('ORDEN RECHAZADA por Gerencia — DOCUMENTO SIN VALIDEZ.', 'B91C1C', 'FDECEC'),
                  'ANULADA': ('ORDEN ANULADA — DOCUMENTO SIN VALIDEZ.', '1E293B', 'EEF2F7'),
                  'BORRADOR': ('PENDIENTE DE APROBACIÓN — aún no revisada ni aprobada por Gerencia. No válida sin firma y sello.', 'B45309', 'FFF7E6'),
                  'ENVIADA': ('PENDIENTE DE APROBACIÓN — aún no revisada ni aprobada por Gerencia. No válida sin firma y sello.', 'B45309', 'FFF7E6')}.get(o.estado)
    for txt, color, fondo in ([(banner, '1D4ED8', 'DBEAFE')] if banner else []) + ([estado_txt] if estado_txt else []):
        ws.row_dimensions[fila[0]].height = 18
        celda(1, txt, F(size=9, bold=True, color=color), centro, fondo=fondo, hasta=nc)
        fila[0] += 1
    linea()
    # ---- datos del proveedor ----
    k_f, v_f = F(size=8.5, bold=True), F(size=9)
    sin_corte = Alignment(vertical='top', wrap_text=False)
    ruc_txt = '-' if (o.ruc or '').startswith(TAX_TEMPORAL) else (o.ruc or '-')
    for k1, v1, k2, v2, neg in (('FECHA', o.fecha.strftime('%d/%m/%Y') if o.fecha else '', 'CONTACTO:', o.contacto or '', False),
                                ('TAX ID' if imp else 'RUC', ruc_txt, 'TELÉFONO:', o.telefono or '', False),
                                ('RAZÓN SOCIAL', o.razon_social or '', 'COTIZACIÓN:', o.cotizacion or '', True),
                                ('DIRECCIÓN', o.direccion or '-', 'CORREO:' if o.email else '', o.email or '', False)):
        celda(1, k1, k_f, sin_corte)
        celda(2, v1, F(size=9, bold=neg))
        celda(3, k2, k_f, sin_corte)
        celda(4, v2, v_f, hasta=nc)
        fila[0] += 1
    linea()
    celda(1, 'Estimados señores:\nPor medio de la presente nos es grato solicitarle lo siguiente:', v_f, hasta=nc)
    ws.row_dimensions[fila[0]].height = 26
    fila[0] += 2
    # ---- ítems ----
    for i, t in enumerate(cols, start=1):
        celda(i, t, F(size=8.5, bold=True, color='FFFFFF'), Alignment(horizontal='left' if i <= 2 else ('center' if i <= nc - 2 else 'right'), vertical='center', wrap_text=True),
              fondo=tema['cab'])
    ws.row_dimensions[fila[0]].height = 18
    fila[0] += 1
    der, cen = Alignment(horizontal='right', vertical='top'), Alignment(horizontal='center', vertical='top')
    fmt_cant = '#,##0.####'
    for it in o.items:
        desc = (f"[{it.tipo_servicio}] " if getattr(it, 'tipo_servicio', None) and not imp else '') + (it.descripcion or '')
        extra = ' · '.join(x for x in ((it.detalle or ''), (f"{_cant_txt(it.piezas)} PIEZA(S)" if it.piezas else '')) if x)
        celda(1, it.item, F(size=9), Alignment(horizontal='left', vertical='top'))
        celda(2, desc + (f"\n{extra}" if extra else ''), F(size=9, bold=True))
        if imp:
            celda(3, it.cantidad, F(size=9, bold=True), cen, '#,##0.##')
            celda(4, it.kgs_mpcs if it.kgs_mpcs is not None else '-', F(size=9), cen, '#,##0.00')
            celda(5, it.peso_total if it.peso_total else '-', F(size=9), cen, '#,##0.00')
            celda(6, it.precio_unitario, F(size=9, bold=True), der, '#,##0.00#####')
            celda(7, it.total, F(size=9), der, '"$" #,##0.00')
        else:
            celda(3, it.cantidad, F(size=9, bold=True), cen, fmt_cant)
            celda(4, it.um or '', F(size=9, bold=True), cen)
            celda(5, it.precio_unitario, F(size=9, bold=True), der, '#,##0.00##')
            celda(6, it.total, F(size=9), der, f'"{simb}" #,##0.00')
        if extra:
            ws.row_dimensions[fila[0]].height = 26
        fila[0] += 1
    if not o.items:
        celda(1, '(sin ítems todavía)', F(size=9, italic=True, color='64748B'), hasta=nc)
        fila[0] += 1
    arriba = Border(top=fino)
    letras = _monto_en_letras(o.total, o.moneda if o.moneda in MONEDAS_OC else 'PEN')
    neto_k = F(size=9, bold=True, color='FFFFFF')
    neto_v_borde = Border(top=Side(style='thin', color=hx(tema['neto'])), bottom=Side(style='thin', color=hx(tema['neto'])),
                          left=Side(style='thin', color=hx(tema['neto'])), right=Side(style='thin', color=hx(tema['neto'])))
    if imp:
        tot_pcs = sum((i.cantidad or 0) for i in o.items)
        tot_kg = sum((i.peso_total or 0) for i in o.items)
        for k in range(1, nc + 1):
            ws.cell(row=fila[0], column=k).border = arriba
        celda(2, 'TOTALES', F(size=9, bold=True), der, borde=arriba)
        celda(3, tot_pcs, F(size=9, bold=True), cen, '#,##0.##', borde=arriba)
        celda(5, tot_kg if tot_kg else '-', F(size=9, bold=True), cen, '#,##0.00', borde=arriba)
        celda(6, 'TOTAL NETO', neto_k, der, fondo=tema['neto'])
        celda(7, o.total or 0, F(size=9, bold=True), der, '"$" #,##0.00', borde=neto_v_borde)
        fila[0] += 1
        celda(1, letras, F(size=8, italic=True), hasta=nc - 2)
        celda(nc - 1, 'PRECIOS NO INCLUYEN IGV', F(size=8.5, bold=True), der, hasta=nc)
        fila[0] += 1
    else:
        fila[0] += 1
        ini = fila[0]
        det = _oc_detraccion(o)
        filas_tot = [('VALOR VENTA', o.subtotal), ('DESC.', '-'), ('SUB-TOTAL', o.subtotal), (f'IGV ({int(IGV_OC * 100)}%)', o.igv), ('TOTAL NETO', o.total)]
        if det:
            filas_tot += [(f"DETRACCIÓN ({det['pct_txt']}%)", det['monto']), ('NETO A PAGAR', det['neto'])]
        for etq, val in filas_tot:
            es_neto = etq == 'TOTAL NETO'
            celda(nc - 1, etq, neto_k if es_neto else F(size=8.5, bold=True), fondo=tema['neto'] if es_neto else None)
            celda(nc, val if val is not None else 0, F(size=9, bold=es_neto or etq == 'NETO A PAGAR'), der,
                  None if val == '-' else f'"{simb}" #,##0.00', borde=neto_v_borde if es_neto else None)
            fila[0] += 1
        ws.merge_cells(start_row=ini, start_column=1, end_row=fila[0] - 1, end_column=nc - 2)
        c = ws.cell(row=ini, column=1, value=letras)
        c.font, c.alignment = F(size=8, italic=True), Alignment(vertical='bottom', wrap_text=True)
    if o.observaciones:
        celda(1, f"OBSERVACIONES: {o.observaciones}", F(size=9), hasta=nc)
        ws.row_dimensions[fila[0]].height = 28
        fila[0] += 1
    linea()
    # ---- condiciones ----
    entrega = _oc_entrega_txt(o)
    lugar = o.lugar_recojo if o.entrega_modo == 'RECOJO' else cfg.get('lugar_entrega', '')
    titulo = F(size=8.5, bold=True, underline='single')
    if imp:
        celda(1, 'CONDICIONES COMERCIALES:', titulo, hasta=nc)
        fila[0] += 1
        for l in [x for x in (o.condiciones_comerciales or '').split('\n') if x.strip()] or ['-']:
            celda(1, f"- {l.strip()}", F(size=8.5), hasta=nc)
            fila[0] += 1
        celda(1, 'CONDICIONES DE PAGO:', titulo, hasta=nc)
        fila[0] += 1
        for p in (_oc_pagos_imp(o) or [{'txt': o.condicion_pago or '-'}]):
            celda(1, p['txt'], F(size=8.5, bold=True), hasta=nc)
            fila[0] += 1
        filas_c = [('MONEDA', f"{mon['nombre'].upper()} (USD)"), ('FECHA DE ENTREGA', entrega), ('LUGAR DE ENTREGA', lugar or '')]
    else:
        filas_c = [('CONDICIÓN DE PAGO', o.condicion_pago or ''), ('MONEDA', mon['nombre'].upper()), ('FECHA DE ENTREGA', entrega),
                   ('LUGAR DE RECOJO' if o.entrega_modo == 'RECOJO' else 'LUGAR DE ENTREGA', lugar or '')]
    for k, v in filas_c:
        celda(1, k, k_f, sin_corte, fondo=tema['res'] if k == 'FECHA DE ENTREGA' else None)
        celda(2, v, F(size=9, bold=k == 'MONEDA'), fondo=tema['res'] if k == 'FECHA DE ENTREGA' else None)
        fila[0] += 1
    linea()
    if not imp:
        celda(1, 'TÉRMINOS Y CONDICIONES:', titulo, hasta=nc)
        fila[0] += 1
        for l in (cfg.get('terminos') or '').split('\n'):
            importante = '**' in l
            celda(1, l.replace('**', ''), F(size=8, bold=importante, color=hx(tema['azul']) if importante else '111111'),
                  fondo=tema['resaltado_fondo'] if importante else None, hasta=nc)
            if len(l) > 120:
                ws.row_dimensions[fila[0]].height = 24
            fila[0] += 1
        fila[0] += 1
        celda(1, 'HORARIO DE ATENCIÓN:', F(size=8.5, bold=True, color='FFFFFF'), fondo=tema['cab'], hasta=2)
        fila[0] += 1
        for l in (cfg.get('horario') or '').split('\n'):
            celda(1, l.strip(), F(size=8), hasta=2)
            fila[0] += 1
    fila[0] += 1
    # ---- firmas ----
    celda(1, 'Aprobado por:', F(size=9, bold=True))
    celda(nc - 1, f"Elaborado:   {o.creado_por.nombre_completo if getattr(o, 'creado_por', None) else ''}", F(size=9, bold=True), der, hasta=nc)
    fila[0] += 1
    if firma:
        fila[0] += 1
        try:
            from openpyxl.drawing.image import Image as XLImage
            img = XLImage(io.BytesIO(base64.b64decode(firma['uri'].split(',', 1)[1])))
            img.width, img.height = int(firma['ancho']), int(firma['alto'])
            ws.add_image(img, f'A{fila[0]}')
            for _ in range(max(3, int(firma['alto'] * 0.75 / 18) + 2)):
                ws.row_dimensions[fila[0]].height = 18
                fila[0] += 1
        except Exception:
            app.logger.exception('Excel OC: no se pudo poner la firma')
        quien = o.aprobado_por.nombre_completo if getattr(o, 'aprobado_por', None) else 'Gerencia'
        celda(1, f"{quien} · {o.fecha_aprobacion.strftime('%d/%m/%Y %H:%M') if getattr(o, 'fecha_aprobacion', None) else ''}", F(size=8, color='444444'), hasta=2)
    elif o.estado == 'RECHAZADA':
        celda(1, 'RECHAZADA', F(size=14, bold=True, color='B91C1C'), hasta=2)
    elif o.estado == 'ANULADA':
        celda(1, 'ANULADA', F(size=14, bold=True, color='334155'), hasta=2)
    else:
        celda(1, 'PENDIENTE DE APROBACIÓN — sin revisar por Gerencia', F(size=9, bold=True, color='B45309'), hasta=2)
    # ---- impresión: A4 vertical, todo el ancho en una hoja ----
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.print_area = f"A1:{L}{fila[0]}"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _enviar_excel_oc(datos, nombre):
    return send_file(io.BytesIO(datos), as_attachment=True, download_name=nombre,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/ordenes/<int:orden_id>/excel')
@_ruta_oc('docs')
def oc_excel(orden_id):
    """Excel de una orden ya guardada: mismo contenido que el PDF y su número real."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    empresa = orden.empresa or 'ANCLAJES'
    firma = _firma_gerencia_oc(empresa) if orden.estado in ('APROBADA', 'RECIBIDA', 'CONFORME') else None
    try:
        datos = _oc_excel_bytes(orden, empresa, firma)
    except Exception:
        app.logger.exception('No se pudo armar el Excel de la orden %s', orden_id)
        flash('⚠️ No se pudo armar el Excel de la orden. Descarga el PDF y avisa a soporte.')
        return redirect(url_for('oc_detalle', orden_id=orden_id))
    return _enviar_excel_oc(datos, _oc_nombre_archivo(orden, empresa, 'xlsx'))


@app.route('/ordenes/vista-previa', methods=['POST'])
@_ruta_oc('editar', como_json=True)
def oc_vista_previa():
    """Vista previa de lo que está en el formulario, SIN guardar: formato=html (rápida, en la página), pdf o xlsx."""
    formato = request.form.get('formato_vista') or 'html'
    try:
        o, empresa, avisos = _oc_desde_form(request.form)
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Vista previa OC')
        return {'status': 'error', 'msg': f'No se pudo armar la vista previa ({e.__class__.__name__}). Revisa los datos del formulario.'}
    if formato == 'xlsx':
        return _enviar_excel_oc(_oc_excel_bytes(o, empresa, banner=AVISO_VISTA_PREVIA_OC if not o.numero else 'VISTA PREVIA — cambios todavía NO guardados.'),
                                _oc_nombre_archivo(o, empresa, 'xlsx', vista_previa=True))
    ctx = _oc_ctx_pdf(o, empresa, None, vista_previa=(AVISO_VISTA_PREVIA_OC if not o.numero else 'VISTA PREVIA — cambios todavía NO guardados.'))
    if formato == 'pdf':
        pdf = _pdf_bytes_oc(render_template('pdf_orden_compra.html', **ctx))
        if pdf is None:
            return {'status': 'error', 'msg': 'No se pudo generar el PDF de la vista previa (revisa ítems muy largos o datos raros).'}, 500
        resp = send_file(io.BytesIO(pdf), mimetype='application/pdf', download_name=_oc_nombre_archivo(o, empresa, 'pdf', vista_previa=True))
        resp.headers['Content-Disposition'] = f'inline; filename="{_oc_nombre_archivo(o, empresa, "pdf", vista_previa=True)}"'
        return resp
    return {'status': 'ok', 'html': render_template('pdf_orden_compra.html', vista_html=True, **ctx), 'avisos': avisos,
            'numero': _oc_numero_txt(o), 'nuevo': not o.numero}
