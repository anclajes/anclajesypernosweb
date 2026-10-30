# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · órdenes
# lista, Excel y reportes, precios por proveedor, crear / editar y detalle con el flujo (enviar, aprobar, rechazar, anular)
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- LISTA ----------------------------
@app.route('/ordenes')
@_ruta_oc()
def oc_lista():
    rol = session.get('role')
    hoy = hora_peru().date()
    # Cada empresa por separado (se recuerda la última elegida); "TODAS" junta las dos
    emp_sel = (request.args.get('empresa') or session.get('oc_empresa') or 'ANCLAJES').upper()
    emp_sel = emp_sel if emp_sel in EMPRESAS_OC or emp_sel == 'TODAS' else 'ANCLAJES'
    session['oc_empresa'] = emp_sel
    todas_emp = OrdenCompra.query.order_by(OrdenCompra.fecha.desc(), OrdenCompra.id.desc()).all()
    conteo_emp = {e: sum(1 for o in todas_emp if (o.empresa or 'ANCLAJES') == e) for e in EMPRESAS_OC}
    conteo_emp['TODAS'] = len(todas_emp)
    todas = [o for o in todas_emp if emp_sel == 'TODAS' or (o.empresa or 'ANCLAJES') == emp_sel]
    pagos = {o.id: _oc_pago_info(o, hoy) for o in todas}
    atrasos = {o.id: _oc_atraso(o, hoy) for o in todas}

    def en_vista(o, v):
        if v == 'atrasadas':
            return bool(atrasos[o.id])
        if v == 'por_pagar':
            return pagos[o.id]['habilitado'] and not pagos[o.id]['pagada']
        if v == 'pagadas':
            return pagos[o.id]['pagada']
        return o.estado in VISTAS_OC[v][1]

    conteo = {v: sum(1 for o in todas if en_vista(o, v)) for v in VISTAS_OC_ORDEN}
    defecto = 'aprobar' if rol == 'admin' and conteo['aprobar'] else 'curso'
    vista = request.args.get('vista', defecto)
    vista = vista if vista in VISTAS_OC_ORDEN else 'curso'
    a = request.args
    tipo, destino = a.get('tipo', ''), a.get('destino', '')
    prov_id = a.get('proveedor', type=int)
    solicitante, motivo, pago_f, docs_f = a.get('solicitante', ''), a.get('motivo', ''), a.get('pago', ''), a.get('docs', '')
    desde, hasta = _fecha_param('desde', None), _fecha_param('hasta', None)
    buscar = ' '.join((a.get('q') or '').split())
    docs = {}
    for d in OrdenCompraDocumento.query.all():
        docs.setdefault(d.orden_id, []).append(d)
    ordenes = []
    for o in todas:
        if not en_vista(o, vista):
            continue
        if tipo in TIPOS_OC and o.tipo != tipo:
            continue
        if destino in DESTINOS_OC and o.destino != destino:
            continue
        if prov_id and o.oc_proveedor_id != prov_id:
            continue
        if solicitante and (_oc_solicitante_txt(o) or '').upper() != solicitante.upper():
            continue
        if motivo and (o.motivo_compra or '') != motivo:
            continue
        if pago_f:
            niv = pagos[o.id]['nivel']
            if pago_f == 'pendiente' and niv not in ('contado', 'al_dia', 'por_vencer', 'vencida'):
                continue
            if pago_f != 'pendiente' and niv != pago_f:
                continue
        if docs_f:
            tipos_d = {d.tipo for d in docs.get(o.id, [])}
            if docs_f == 'sin_factura' and 'FACTURA' in tipos_d:
                continue
            if docs_f == 'sin_guia' and 'GUIA' in tipos_d:
                continue
            if docs_f == 'sin_certificado' and (not o.requiere_certificado or 'CERTIFICADO' in tipos_d):
                continue
        if desde and o.fecha < desde:
            continue
        if hasta and o.fecha > hasta:
            continue
        if buscar:
            texto = (f"{o.tipo} {_oc_numero_txt(o)} {o.numero:06d} {o.razon_social} {o.ruc or ''} {o.cotizacion or ''} {o.numero_factura or ''} {o.numero_guia or ''} "
                     f"{_oc_solicitante_txt(o)} {o.cliente_razon or ''} {o.cliente_ruc or ''} {' '.join(i.descripcion for i in o.items)}").upper()
            if not all(t in texto for t in buscar.upper().split()):
                continue
        ordenes.append(o)
    total_filtrado = len(ordenes)
    if a.get('exportar') == 'excel':
        return _oc_excel_lista(ordenes, pagos, atrasos, emp_sel)
    ordenes = ordenes[:500]
    # resumen de lo mostrado (por moneda)
    resumen = {}
    for o in ordenes:
        r = resumen.setdefault(o.moneda, {'total': 0, 'pendiente': 0})
        r['total'] += o.total or 0
        if pagos[o.id]['habilitado'] and not pagos[o.id]['pagada']:
            r['pendiente'] += o.total or 0
    kpi = {'aprobar': conteo['aprobar'], 'atrasadas': conteo['atrasadas'],
           'vencidas': sum(1 for x in pagos.values() if x['nivel'] == 'vencida'),
           'por_vencer': sum(1 for x in pagos.values() if x['nivel'] == 'por_vencer'),
           'ingresar': sum(len(eis) for o_, _, eis in _entregas_por_ingresar() if emp_sel == 'TODAS' or (o_.empresa or 'ANCLAJES') == emp_sel)}
    proveedores = sorted({(o.oc_proveedor_id, o.razon_social) for o in todas if o.oc_proveedor_id}, key=lambda x: _clave_alfabetica(x[1] or ''))
    solicitantes = sorted({_oc_solicitante_txt(o) for o in todas if _oc_solicitante_txt(o)}, key=_clave_alfabetica)
    motivos = sorted({o.motivo_compra for o in todas if o.motivo_compra})
    filtros_activos = sum(1 for x in (tipo, destino, prov_id, solicitante, motivo, pago_f, docs_f, desde, hasta) if x)
    return render_template('oc_lista.html', ordenes=ordenes, vista=vista, vistas_orden=VISTAS_OC_ORDEN,
                           nombres_vista={**{k: v[0] for k, v in VISTAS_OC.items()}, **VISTAS_OC_EXTRA}, conteo=conteo, docs=docs,
                           tipo=tipo, destino=destino, prov_id=prov_id, solicitante=solicitante, motivo=motivo, pago_f=pago_f, docs_f=docs_f,
                           desde=desde, hasta=hasta, buscar=buscar, hoy=hoy, pagos=pagos, atrasos=atrasos, kpi=kpi, resumen=resumen,
                           total_filtrado=total_filtrado, proveedores=proveedores, solicitantes=solicitantes, motivos=motivos,
                           filtros_activos=filtros_activos, estados=ESTADOS_OC, tipos=TIPOS_OC, destinos=DESTINOS_OC, monedas=MONEDAS_OC,
                           puede_editar=rol in ROLES_OC_EDITAN, aprueba=rol in ROLES_OC_APRUEBAN, seccion='lista', emp_sel=emp_sel, conteo_emp=conteo_emp, empresas_oc=EMPRESAS_OC)


# ---------------------------- EXCEL Y REPORTES ----------------------------
MESES_ES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic']


def _xlsx_hoja(wb, titulo, cabeceras, filas, anchos=None, formatos=None, primera=False, nota=None):
    """Hoja con cabecera de color, filtros, primera fila fija y formatos de número/fecha por columna (índice desde 0)."""
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    ws = wb.active if primera else wb.create_sheet()
    ws.title = titulo[:31]
    fila0 = 1
    if nota:
        ws.cell(row=1, column=1, value=nota).font = Font(italic=True, color='475569')
        fila0 = 2
    for j, cab in enumerate(cabeceras, start=1):
        c = ws.cell(row=fila0, column=j, value=cab)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='0B3D91')
        c.alignment = Alignment(vertical='center', wrap_text=True)
    for i, fila in enumerate(filas, start=fila0 + 1):
        for j, v in enumerate(fila, start=1):
            c = ws.cell(row=i, column=j, value=v)
            if formatos and (j - 1) in formatos:
                c.number_format = formatos[j - 1]
    ws.freeze_panes = ws.cell(row=fila0 + 1, column=1)
    if filas:
        ws.auto_filter.ref = f"A{fila0}:{get_column_letter(len(cabeceras))}{fila0 + len(filas)}"
    for j, cab in enumerate(cabeceras, start=1):
        ancho = (anchos or {}).get(j - 1) or min(max(len(str(cab)) + 2, *(len(str(f[j - 1] if f[j - 1] is not None else '')) + 1 for f in filas[:300])) if filas else len(str(cab)) + 2, 45)
        ws.column_dimensions[get_column_letter(j)].width = max(ancho, 8)
    return ws


def _xlsx_respuesta(wb, nombre):
    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    return send_file(salida, as_attachment=True, download_name=nombre,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _fecha_xl(v):
    """Fechas sin hora para Excel (las fechas con hora quedan como fecha y hora)."""
    return v if v is not None else None


def _oc_excel_lista(ordenes, pagos, atrasos, emp_sel):
    """Exporta a Excel las órdenes que se están viendo (con los filtros aplicados): hoja de órdenes y hoja de ítems."""
    from openpyxl import Workbook
    wb = Workbook()
    hoy = hora_peru().date()
    docs = {}
    for d in OrdenCompraDocumento.query.filter(OrdenCompraDocumento.orden_id.in_([o.id for o in ordenes] or [0])).all():
        docs.setdefault(d.orden_id, []).append(d)
    filas, filas_it = [], []
    for o in ordenes:
        rec = _oc_recepcion(o)
        pg = pagos.get(o.id) or _oc_pago_info(o, hoy)
        esp = _oc_fecha_esperada(o)
        reqs = sorted({_req_codigo(r) for r in (_req_de_item_oc(i) for i in o.items) if r})
        ie = _oc_ingreso_estado(o) if o.destino == 'GENERAL' and o.tipo == 'OC' else None
        guias = ', '.join(e.numero_guia for e in rec['entregas'] if e.numero_guia) or (o.numero_guia or '')
        filas.append([EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', o.empresa), o.tipo, _oc_numero_txt(o), o.fecha, ESTADOS_OC[o.estado]['txt'],
                      'Sí' if o.es_importacion else '', o.razon_social, o.ruc, _oc_solicitante_txt(o) or '', (o.area_solicitante or '').title(),
                      (o.motivo_compra or '').capitalize(), o.cliente_razon or '', DESTINOS_OC.get(o.destino, o.destino),
                      o.moneda, o.subtotal or 0, o.igv or 0, o.total or 0, o.condicion_pago or '',
                      'Pagada' if pg['pagada'] else ('—' if not pg['habilitado'] else 'Pendiente'), o.fecha_pago, pg.get('vence'),
                      esp, atrasos.get(o.id) or None, o.fecha_llegada, len(rec['entregas']),
                      (f"{rec['n_completos']} de {rec['n_items']} productos completos" if rec['entregas'] else ''), _oc_faltan_txt(o, rec), o.fecha_conforme,
                      ('Completo' if ie['completo'] else f"{ie['hechos']} de {ie['total']}") if ie else ('Sí' if o.insumo_ingreso_id else ''),
                      o.numero_factura or '', guias, o.aprobado_por.nombre_completo if o.aprobado_por else '', o.fecha_aprobacion,
                      o.creado_por.nombre_completo if o.creado_por else '', ', '.join(reqs), len(docs.get(o.id, []))])
        for i in o.items:
            ri = rec['items'].get(i.id, {})
            r = _req_de_item_oc(i)
            filas_it.append([EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', o.empresa), _oc_codigo(o), o.fecha, ESTADOS_OC[o.estado]['txt'], o.razon_social,
                             i.item, i.codigo or '', i.descripcion, i.familia or '', i.calidad or '', i.cantidad, i.um, i.precio_unitario, i.total, o.moneda,
                             i.kgs_mpcs, i.precio_mil, i.peso_total, ri.get('llego', 0), ri.get('cancelado', 0), ri.get('ingresado', 0),
                             i.sku_ingreso or '', _req_codigo(r) if r else ''])
    f_d, f_dt, f_m, f_n = 'dd/mm/yyyy', 'dd/mm/yyyy hh:mm', '#,##0.00', '#,##0.####'
    _xlsx_hoja(wb, 'Órdenes', ['Empresa', 'Tipo', 'N°', 'Fecha', 'Estado', 'Importación', 'Proveedor', 'RUC / Tax ID', 'Solicitó', 'Área', 'Motivo', 'Cliente',
                               'Destino', 'Moneda', 'Subtotal', 'IGV', 'Total', 'Condición de pago', 'Pago', 'Fecha de pago', 'Vence', 'Debía llegar',
                               'Atraso (días)', '1.ª llegada', 'Entregas', 'Llegada', 'Falta llegar (por producto)', 'Conforme', 'Ingreso al inventario',
                               'Factura', 'Guía(s)', 'Aprobó', 'Fecha aprobación', 'Creó', 'Requerimientos', 'Documentos'],
               filas, formatos={3: f_d, 14: f_m, 15: f_m, 16: f_m, 19: f_d, 20: f_d, 21: f_d, 23: f_dt, 27: f_dt, 32: f_dt},
               primera=True, nota=f"Órdenes de compra y servicio · {'Las dos empresas' if emp_sel == 'TODAS' else EMPRESAS_OC[emp_sel]['nombre']} · "
                                  f"exportado el {hora_peru().strftime('%d/%m/%Y %H:%M')} por {session.get('nombre', '')} · {len(filas)} orden(es)")
    _xlsx_hoja(wb, 'Ítems', ['Empresa', 'Orden', 'Fecha', 'Estado', 'Proveedor', 'Ítem', 'Código', 'Descripción', 'Familia', 'Calidad', 'Cantidad', 'U.M.',
                             'P. Unit.', 'Total', 'Moneda', 'KGS/MPCS', 'USD/1000 PCS', 'Peso total (kg)', 'Llegó', 'No llegará', 'Ingresado',
                             'Código en el inventario', 'Requerimiento'],
               filas_it, formatos={2: f_d, 10: f_n, 12: '#,##0.00####', 13: f_m, 15: f_n, 16: f_m, 17: f_n, 18: f_n, 19: f_n, 20: f_n})
    registrar_log(f"Exportó {len(filas)} orden(es) de compra a Excel", 'bi-file-earmark-excel', 'text-success')
    return _xlsx_respuesta(wb, f"ordenes_{emp_sel.lower()}_{hora_peru().strftime('%Y%m%d_%H%M')}.xlsx")


def _estad_dias(valores):
    v = sorted(x for x in valores if x is not None and x >= 0)
    if not v:
        return {'n': 0, 'prom': None, 'mediana': None, 'max': None, 'min': None}
    n = len(v)
    med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return {'n': n, 'prom': round(sum(v) / n, 1), 'mediana': round(med, 1), 'max': round(v[-1], 1), 'min': round(v[0], 1)}


def _dias_entre(a, b):
    """Días (con decimales) entre dos fechas o fechas con hora; None si falta alguna."""
    if not a or not b:
        return None
    a = a if isinstance(a, datetime) else datetime.combine(a, datetime.min.time())
    b = b if isinstance(b, datetime) else datetime.combine(b, datetime.min.time())
    return (b - a).total_seconds() / 86400


def _oc_reporte(emp_sel='TODAS', desde=None, hasta=None, tipo=''):
    """Gasto (soles y dólares por separado), atrasos de proveedores y tiempos de cada paso, de las órdenes APROBADAS del periodo."""
    hoy = hora_peru().date()
    ordenes = [o for o in OrdenCompra.query.filter(OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME'])).all()
               if (emp_sel == 'TODAS' or (o.empresa or 'ANCLAJES') == emp_sel) and (not tipo or o.tipo == tipo)
               and o.fecha and (not desde or o.fecha >= desde) and (not hasta or o.fecha <= hasta)]
    ordenes.sort(key=lambda o: (o.fecha, o.id))

    def acumular(clave_fn):
        res = {}
        for o in ordenes:
            k = clave_fn(o) or '(sin dato)'
            r = res.setdefault(k, {'clave': k, 'PEN': 0.0, 'USD': 0.0, 'n': 0})
            r[o.moneda if o.moneda in ('PEN', 'USD') else 'PEN'] += o.total or 0
            r['n'] += 1
        lista = list(res.values())
        for r in lista:
            r['PEN'], r['USD'] = round(r['PEN'], 2), round(r['USD'], 2)
        return lista

    por_mes = sorted(acumular(lambda o: o.fecha.strftime('%Y-%m')), key=lambda r: r['clave'])
    for r in por_mes:
        if r['clave'][:4].isdigit():
            r['txt'] = f"{MESES_ES[int(r['clave'][5:7]) - 1]} {r['clave'][:4]}"
    orden_gasto = lambda r: (-(r['PEN'] + r['USD'] * 3.75), r['clave'])     # solo para ordenar (no se suman monedas)
    por_prov = sorted(acumular(lambda o: o.razon_social), key=orden_gasto)
    por_area = sorted(acumular(lambda o: (o.area_solicitante or '').title()), key=orden_gasto)
    por_motivo = sorted(acumular(lambda o: (o.motivo_compra or '').capitalize()), key=orden_gasto)
    por_cliente = sorted([r for r in acumular(lambda o: o.cliente_razon) if r['clave'] != '(sin dato)'], key=orden_gasto)
    por_solic = sorted(acumular(lambda o: _oc_solicitante_txt(o)), key=orden_gasto)
    totales = {'PEN': round(sum(o.total or 0 for o in ordenes if o.moneda != 'USD'), 2), 'USD': round(sum(o.total or 0 for o in ordenes if o.moneda == 'USD'), 2),
               'n': len(ordenes), 'n_pen': sum(1 for o in ordenes if o.moneda != 'USD'), 'n_usd': sum(1 for o in ordenes if o.moneda == 'USD'),
               'importacion': sum(1 for o in ordenes if o.es_importacion)}
    # ---- atrasos por proveedor ----
    prov = {}
    for o in ordenes:
        esp = _oc_fecha_esperada(o)
        if not esp:
            continue
        p = prov.setdefault(o.razon_social, {'clave': o.razon_social, 'con_fecha': 0, 'a_tiempo': 0, 'tarde': 0, 'pend_atrasadas': 0, 'dias': [], 'peor': None})
        p['con_fecha'] += 1
        if o.fecha_llegada:
            d = (o.fecha_llegada.date() - esp).days
            if d > 0:
                p['tarde'] += 1
                p['dias'].append(d)
                if not p['peor'] or d > p['peor'][1]:
                    p['peor'] = (_oc_codigo(o), d)
            else:
                p['a_tiempo'] += 1
        elif hoy > esp:
            d = (hoy - esp).days
            p['pend_atrasadas'] += 1
            p['dias'].append(d)
            if not p['peor'] or d > p['peor'][1]:
                p['peor'] = (_oc_codigo(o) + ' (aún no llega)', d)
    atrasos = []
    for p in prov.values():
        p['prom'] = round(sum(p['dias']) / len(p['dias']), 1) if p['dias'] else 0
        p['pct_tarde'] = round(100 * (p['tarde'] + p['pend_atrasadas']) / p['con_fecha']) if p['con_fecha'] else 0
        atrasos.append(p)
    atrasos.sort(key=lambda p: (-(p['tarde'] + p['pend_atrasadas']), -p['prom'], p['clave']))
    # ---- tiempos de cada paso ----
    t = {k: [] for k in ('rq_oc', 'creada_enviada', 'enviada_aprobada', 'aprobada_llegada', 'llegada_conforme', 'conforme_ingreso', 'aprobada_pago', 'ciclo')}
    vistos_rq = set()
    for o in ordenes:
        for i in o.items:
            r = _req_de_item_oc(i)
            if r and (r.id, o.id) not in vistos_rq:
                vistos_rq.add((r.id, o.id))
                t['rq_oc'].append(_dias_entre(r.fecha_registro, o.fecha_registro))
        t['creada_enviada'].append(_dias_entre(o.fecha_registro, o.fecha_envio))
        t['enviada_aprobada'].append(_dias_entre(o.fecha_envio, o.fecha_aprobacion))
        t['aprobada_llegada'].append(_dias_entre(o.fecha_aprobacion, o.fecha_llegada))
        t['aprobada_pago'].append(_dias_entre(o.fecha_aprobacion.date() if o.fecha_aprobacion else None, o.fecha_pago))
        if o.fecha_kardex and o.tipo == 'OC':
            t['ciclo'].append(_dias_entre(o.fecha_registro, o.fecha_kardex))
        for e in _oc_entregas(o):
            t['llegada_conforme'].append(_dias_entre(e.fecha, e.fecha_conforme))
            for ei in e.items:
                t['conforme_ingreso'].append(_dias_entre(e.fecha_conforme, ei.fecha_ingreso))
    pasos = [('rq_oc', 'Requerimiento → OC creada', 'Desde que Almacén pide hasta que Logística arma la orden'),
             ('creada_enviada', 'OC creada → enviada a Gerencia', 'Logística termina y la envía'),
             ('enviada_aprobada', 'Enviada → aprobada', 'Lo que demora Gerencia en aprobar'),
             ('aprobada_llegada', 'Aprobada → llega el material', 'Lo que demora el proveedor (1.ª entrega)'),
             ('llegada_conforme', 'Llegada → conformidad', 'Logística revisa cada entrega'),
             ('conforme_ingreso', 'Conformidad → ingreso al Kardex', 'Almacén ingresa cada producto'),
             ('aprobada_pago', 'Aprobada → pagada', 'Según la condición de pago'),
             ('ciclo', 'Ciclo completo: OC creada → todo ingresado', 'Solo compras para el inventario ya ingresadas')]
    tiempos = [{'clave': k, 'txt': txt, 'ayuda': ay, **_estad_dias(t[k])} for k, txt, ay in pasos]
    return {'ordenes': ordenes, 'totales': totales, 'por_mes': por_mes, 'por_prov': por_prov, 'por_area': por_area, 'por_motivo': por_motivo,
            'por_cliente': por_cliente, 'por_solic': por_solic, 'atrasos': atrasos, 'tiempos': tiempos}


@app.route('/ordenes/reportes')
@_ruta_oc()
def oc_reportes():
    hoy = hora_peru().date()
    emp_sel = (request.args.get('empresa') or session.get('oc_empresa') or 'TODAS').upper()
    emp_sel = emp_sel if emp_sel in EMPRESAS_OC or emp_sel == 'TODAS' else 'TODAS'
    desde = _fecha_param('desde', date(hoy.year, 1, 1))
    hasta = _fecha_param('hasta', hoy)
    tipo = request.args.get('tipo', '') if request.args.get('tipo') in TIPOS_OC else ''
    rep = _oc_reporte(emp_sel, desde, hasta, tipo)
    if request.args.get('exportar') == 'excel':
        return _oc_excel_reporte(rep, emp_sel, desde, hasta, tipo)
    return render_template('oc_reportes.html', rep=rep, emp_sel=emp_sel, desde=desde, hasta=hasta, tipo=tipo, tipos=TIPOS_OC,
                           empresas_oc=EMPRESAS_OC, seccion='reportes', hoy=hoy)


def _oc_excel_reporte(rep, emp_sel, desde, hasta, tipo):
    from openpyxl import Workbook
    wb = Workbook()
    nota = (f"{'Las dos empresas' if emp_sel == 'TODAS' else EMPRESAS_OC[emp_sel]['nombre']} · órdenes aprobadas del {desde.strftime('%d/%m/%Y')} "
            f"al {hasta.strftime('%d/%m/%Y')}{' · solo ' + tipo if tipo else ''} · soles y dólares por separado (no se suman)")
    m = '#,##0.00'
    _xlsx_hoja(wb, 'Gasto por mes', ['Mes', 'Soles (S/)', 'Dólares (US$)', 'Órdenes'],
               [[r.get('txt', r['clave']), r['PEN'], r['USD'], r['n']] for r in rep['por_mes']], formatos={1: m, 2: m}, primera=True, nota=nota)
    for titulo, clave, cab in (('Por proveedor', 'por_prov', 'Proveedor'), ('Por área', 'por_area', 'Área'), ('Por motivo', 'por_motivo', 'Motivo'),
                               ('Por cliente', 'por_cliente', 'Cliente'), ('Por solicitante', 'por_solic', 'Solicitó')):
        _xlsx_hoja(wb, titulo, [cab, 'Soles (S/)', 'Dólares (US$)', 'Órdenes'], [[r['clave'], r['PEN'], r['USD'], r['n']] for r in rep[clave]],
                   formatos={1: m, 2: m}, nota=nota)
    _xlsx_hoja(wb, 'Atrasos de proveedores', ['Proveedor', 'Órdenes con fecha de entrega', 'A tiempo', 'Llegaron tarde', 'Atrasadas sin llegar',
                                              '% con atraso', 'Atraso promedio (días)', 'Peor caso', 'Días del peor caso'],
               [[p['clave'], p['con_fecha'], p['a_tiempo'], p['tarde'], p['pend_atrasadas'], p['pct_tarde'], p['prom'],
                 p['peor'][0] if p['peor'] else '', p['peor'][1] if p['peor'] else None] for p in rep['atrasos']], nota=nota)
    _xlsx_hoja(wb, 'Tiempos por paso', ['Paso', 'Qué mide', 'Casos', 'Promedio (días)', 'Mediana (días)', 'Mínimo', 'Máximo'],
               [[x['txt'], x['ayuda'], x['n'], x['prom'], x['mediana'], x['min'], x['max']] for x in rep['tiempos']], nota=nota)
    _xlsx_hoja(wb, 'Órdenes del periodo', ['Empresa', 'Orden', 'Fecha', 'Proveedor', 'Área', 'Motivo', 'Cliente', 'Moneda', 'Total', 'Estado'],
               [[EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', ''), _oc_codigo(o), o.fecha, o.razon_social, (o.area_solicitante or '').title(),
                 (o.motivo_compra or '').capitalize(), o.cliente_razon or '', o.moneda, o.total or 0, ESTADOS_OC[o.estado]['txt']] for o in rep['ordenes']],
               formatos={2: 'dd/mm/yyyy', 8: m}, nota=nota)
    registrar_log("Exportó los reportes de compras a Excel", 'bi-file-earmark-excel', 'text-success')
    return _xlsx_respuesta(wb, f"reporte_compras_{desde.isoformat()}_{hasta.isoformat()}.xlsx")


# ---------------------------- CREAR / EDITAR ----------------------------
def _solicitantes_oc(orden=None):
    """Opciones de "Solicitó": cuentas del sistema (Gerencia, Administración, Vendedores, Logística, Almacén) + nombres de Configuración."""
    grupos = []
    usuarios = [u for u in User.query.all() if u.role in ROLES_SOLICITANTES_OC and not getattr(u, 'desactivado', False)]
    if orden and orden.solicitante_user_id and not any(u.id == orden.solicitante_user_id for u in usuarios) and orden.solicitante:
        usuarios.append(orden.solicitante)
    for rol in ROLES_SOLICITANTES_OC:
        lista = sorted([u for u in usuarios if u.role == rol], key=lambda u: _clave_alfabetica(u.nombre_completo or u.username or ''))
        if lista:
            grupos.append((ROLE_LABELS.get(rol, rol) + ('es' if rol == 'vendedor' else ''),
                           [{'valor': f'u:{u.id}', 'txt': u.nombre_completo or u.username, 'area': AREA_POR_ROL_OC.get(u.role, '')} for u in lista]))
    otros = [v.valor for v in _oc_catalogo('OC_SOLICITANTE')]
    if orden and not orden.solicitante_user_id and orden.solicitante_nombre and orden.solicitante_nombre not in otros:
        otros.append(orden.solicitante_nombre)
    if otros:
        grupos.append(('Otros (Configuración)', [{'valor': f'n:{n}', 'txt': n, 'area': ''} for n in otros]))
    return grupos


def _contexto_form_oc(orden=None, datos_previos=None):
    motivos = [m for m in OCMotivoCompra.query.all() if m.activo or (orden and (m.nombre or '').upper() == (orden.motivo_compra or '').upper())]
    motivos.sort(key=lambda m: m.id)
    return dict(orden=orden, previo=datos_previos, bloqueo_empresa=_oc_bloqueo_cambio_empresa(orden) if orden else None, tipos=TIPOS_OC, destinos=DESTINOS_OC, monedas=MONEDAS_OC, empresas_oc=EMPRESAS_OC,
                ums=[v.valor for v in _oc_catalogo('OC_UM')], condiciones=[v.valor for v in _oc_catalogo('OC_CONDICION_PAGO')],
                condiciones_imp=CONDICIONES_PAGO_IMP,
                cfg=_oc_cfg(orden.empresa if orden else 'ANCLAJES'), igv=IGV_OC, hoy=hora_peru().date(), seccion='nueva',
                cfgs={e: _oc_cfg(e) for e in EMPRESAS_OC}, detraccion_def=DETRACCION_DEF,
                siguiente={f'{e}|{t}': _oc_numero_txt(None, _siguiente_numero_oc(t, e), e) for e in EMPRESAS_OC for t in TIPOS_OC},
                servicios=[v.valor for v in _oc_catalogo('OC_SERVICIO')],
                solicitantes=_solicitantes_oc(orden), areas=[v.valor for v in _oc_catalogo('OC_AREA')],
                motivos_compra=[{'nombre': m.nombre, 'pide_cliente': bool(m.pide_cliente)} for m in motivos],
                bancos=BANCOS_OC, tipos_cuenta=TIPOS_CUENTA_OC, puede_cuentas=session.get('role') in ROLES_OC_PAGAN,
                categorias=_catalogo_insumos('INSUMO_CATEGORIA'), unidades=_catalogo_insumos('INSUMO_UNIDAD'),
                puede_insumos=session.get('role') in ROLES_INSUMOS_EDITAN,
                reqs_pendientes=_req_json_para_oc(None) if session.get('role') in ROLES_REQ_ATIENDEN else [],
                req_inicial=request.args.get('req', type=int) if not orden else None,
                pagos_imp=_oc_pagos_lista((datos_previos or {}).get('pagos_importacion')),
                imp_defaults={e: {'condiciones': c.get('imp_condiciones', ''), 'pagos': _oc_pagos_de_texto(c.get('imp_pagos', ''))}
                              for e, c in ((e, _oc_cfg(e)) for e in EMPRESAS_OC)})


def _req_txt_item(item):
    r = _req_de_item_oc(item)
    return f"{_req_codigo(r)} · {r.solicitante_nombre or ''}" if r else ''


def _orden_a_previo(o, items=None):
    """Datos de una orden para precargar el formulario (editar o duplicar)."""
    d = {c: getattr(o, c) for c in ('tipo', 'empresa', 'destino', 'ruc', 'razon_social', 'direccion', 'contacto', 'telefono', 'email', 'cotizacion',
                                    'moneda', 'condicion_pago', 'entrega_modo', 'lugar_recojo', 'entrega_tipo', 'entrega_dias',
                                    'observaciones', 'oc_proveedor_id', 'contacto_id', 'area_solicitante', 'motivo_compra', 'motivo_detalle',
                                    'cliente_ruc', 'cliente_razon', 'detraccion_pct', 'es_importacion', 'condiciones_comerciales', 'pagos_importacion',
                                    'precios_con_igv')}
    d['solicitante'] = (f"u:{o.solicitante_user_id}" if o.solicitante_user_id else (f"n:{o.solicitante_nombre}" if o.solicitante_nombre else ''))
    d['fecha'] = o.fecha.isoformat() if o.fecha else ''
    d['fecha_entrega'] = o.fecha_entrega.isoformat() if o.fecha_entrega else ''
    d['items'] = [{'descripcion': i.descripcion, 'cantidad': i.cantidad, 'um': i.um,
                   'precio_unitario': i.precio_con_igv if o.precios_con_igv and i.precio_con_igv is not None else i.precio_unitario,
                   'origen': i.origen or '', 'codigo': i.codigo or '', 'insumo_id': i.insumo_id or '', 'familia': i.familia or '',
                   'calidad': i.calidad or '', 'estado': i.estado_producto or '', 'peso_modo': i.peso_modo or 'U',
                   'peso_valor': (i.peso_total if i.peso_modo == 'T' else i.peso_unitario) or '', 'servicio': i.tipo_servicio or '',
                   'req_item': getattr(i, 'req_item_id', None) or '', 'req_txt': _req_txt_item(i),
                   'kgs_mpcs': i.kgs_mpcs if i.kgs_mpcs is not None else '', 'precio_mil': i.precio_mil if i.precio_mil is not None else '',
                   'detalle': i.detalle or '', 'piezas': i.piezas if i.piezas is not None else ''}
                  for i in (items or o.items)]
    return d


@app.route('/ordenes/nueva')
@_ruta_oc('editar')
def oc_nueva():
    previo = None
    base = OrdenCompra.query.get(request.args.get('duplicar', type=int)) if request.args.get('duplicar', type=int) else None
    if base:
        previo = _orden_a_previo(base)
        previo['fecha'] = hora_peru().date().isoformat()
        previo['duplicada_de'] = base.id
        previo['duplicada_txt'] = _oc_codigo(base)
        for it in previo['items']:          # la copia no vuelve a atender los requerimientos de la original
            it['req_item'], it['req_txt'] = '', ''
    else:
        previo = {'tipo': request.args.get('tipo', 'OC') if request.args.get('tipo') in TIPOS_OC else 'OC',
                  'empresa': request.args.get('empresa') if request.args.get('empresa') in EMPRESAS_OC else session.get('oc_empresa', 'ANCLAJES')}
        if previo['empresa'] not in EMPRESAS_OC:
            previo['empresa'] = 'ANCLAJES'
    return render_template('oc_form.html', **_contexto_form_oc(None, previo))


@app.route('/ordenes/<int:orden_id>/editar')
@_ruta_oc('editar')
def oc_editar(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    if orden.estado in ESTADOS_REEDITABLES_OC:
        bloqueo = _oc_bloqueo_reedicion(orden)
        if bloqueo:
            flash(f'⛔ Esta orden ya no se puede editar: {bloqueo}. Si hay que cambiarla, anúlala (si corresponde) y crea una nueva con "Duplicar".')
            return redirect(url_for('oc_detalle', orden_id=orden.id))
    elif orden.estado != 'BORRADOR':
        flash('Esta orden no se puede editar en su estado actual. Si está enviada a Gerencia, primero "Retírala para corregir".')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    return render_template('oc_form.html', **_contexto_form_oc(orden, _orden_a_previo(orden)))


@app.route('/ordenes/guardar', methods=['POST'])
@_ruta_oc('editar')
def oc_guardar():
    f = request.form
    orden = OrdenCompra.query.get(f.get('id', type=int)) if f.get('id', type=int) else None
    volver = url_for('oc_editar', orden_id=orden.id) if orden else url_for('oc_nueva', tipo=f.get('tipo'))
    reaprobacion = bool(orden) and orden.estado in ESTADOS_REEDITABLES_OC
    if reaprobacion:
        bloqueo = _oc_bloqueo_reedicion(orden)
        if bloqueo:
            flash(f'⛔ Esta orden ya no se puede editar: {bloqueo}.')
            return redirect(url_for('oc_detalle', orden_id=orden.id))
    elif orden and orden.estado != 'BORRADOR':
        flash('⛔ Esta orden ya no está en borrador: no se puede editar.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    datos, items, errores = _leer_orden_form(f, orden)
    motivo_edicion = ' '.join((f.get('motivo_edicion') or '').split())[:300]
    if reaprobacion and len(motivo_edicion) < 10:
        errores.append('Escribe el MOTIVO DE LA EDICIÓN (mínimo 10 letras): Gerencia lo verá al volver a aprobarla.')
    if errores:
        # se vuelve a mostrar el formulario con lo escrito (no se pierde nada) y la lista de lo que falta
        previo = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in datos.items()}
        previo.update(items=[{'descripcion': ' '.join((d or '').split()).upper(), 'cantidad': c, 'um': u, 'precio_unitario': pu, 'origen': o_,
                              'codigo': cod, 'insumo_id': ii, 'familia': fa, 'calidad': ca, 'estado': es, 'peso_modo': pm, 'peso_valor': pval, 'servicio': sv,
                              'req_item': rq, 'req_txt': rt, 'kgs_mpcs': kg, 'precio_mil': pmil, 'detalle': dt, 'piezas': pz}
                             for d, c, u, pu, o_, cod, ii, fa, ca, es, pm, pval, sv, rq, rt, kg, pmil, dt, pz in zip(
                                 f.getlist('descripcion[]'), f.getlist('cantidad[]'), f.getlist('um[]'), f.getlist('precio_unitario[]'),
                                 f.getlist('origen[]'), f.getlist('codigo[]'), f.getlist('insumo_id[]'), f.getlist('familia[]') + [''] * 99,
                                 f.getlist('calidad[]') + [''] * 99, f.getlist('estado_producto[]') + [''] * 99,
                                 f.getlist('peso_modo[]') + [''] * 99, f.getlist('peso_valor[]') + [''] * 99, f.getlist('servicio[]') + [''] * 99,
                                 f.getlist('req_item[]') + [''] * 99, f.getlist('req_txt[]') + [''] * 99,
                                 f.getlist('kgs_mpcs[]') + [''] * 99, f.getlist('precio_mil[]') + [''] * 99,
                                 f.getlist('detalle[]') + [''] * 99, f.getlist('piezas[]') + [''] * 99) if (d or c or pu)],
                      duplicada_de=f.get('duplicada_de'), entrega_dias=f.get('entrega_dias'), fecha_entrega=f.get('fecha_entrega'),
                      solicitante=f.get('solicitante', ''), cliente_ruc=f.get('cliente_ruc', ''), cliente_razon=f.get('cliente_razon', ''),
                      motivo_edicion=motivo_edicion)
        return render_template('oc_form.html', errores=errores, **_contexto_form_oc(orden, previo))
    enviar = f.get('accion') == 'enviar' or reaprobacion
    ahora = hora_peru()
    reqs_antes = {i.req_item_id for i in orden.items if getattr(i, 'req_item_id', None)} if orden else set()
    es_nueva = orden is None
    for intento in range(3):
        try:
            prov = _guardar_proveedor_oc(datos)
            contacto = _contacto_para_orden(prov, datos)
            if orden:
                antes = {c: getattr(orden, c) for c in ('razon_social', 'total', 'moneda', 'condicion_pago', 'destino', 'entrega_modo',
                                                        'solicitante_nombre', 'motivo_compra', 'fecha_entrega', 'entrega_dias', 'lugar_recojo')}
                items_antes = [(i.descripcion, i.cantidad, i.um, i.precio_unitario) for i in orden.items]
                aprobada_antes = (orden.aprobado_por.nombre_completo if orden.aprobado_por else 'Gerencia', orden.fecha_aprobacion)
                # cambio de empresa: toma el número siguiente de la otra empresa (antes de cambiarla, para no contarse a sí misma)
                cambio_emp = None
                if (orden.empresa or 'ANCLAJES') != datos['empresa']:
                    cambio_emp = (EMPRESAS_OC[orden.empresa or 'ANCLAJES']['corto'], _oc_codigo(orden),
                                  _siguiente_numero_oc(orden.tipo, datos['empresa']))
                _aplicar_datos_orden(orden, datos, items, prov, contacto)
                if cambio_emp:
                    orden.numero = cambio_emp[2]
                    _oc_evento(orden, 'EMPRESA', f"Empresa cambiada: {cambio_emp[0]} → {EMPRESAS_OC[orden.empresa]['corto']} · antes {cambio_emp[1]}, "
                                                 f"ahora {_oc_codigo(orden)} (el número anterior queda sin uso)")
                orden.editado_por_id, orden.fecha_edicion = session.get('user_id'), ahora
                cambios = '; '.join(x for x in (_resumen_cambios_orden(antes, orden), _resumen_cambios_items(items_antes, items)) if x)
                if reaprobacion:
                    orden.revision = (orden.revision or 0) + 1
                    orden.motivo_edicion = motivo_edicion
                    orden.aprobado_por_id, orden.fecha_aprobacion = None, None
                    _oc_evento(orden, 'EDITADA_APROBADA', f"Rev. {orden.revision} · Motivo: {motivo_edicion} · Cambios: {cambios or 'sin cambios en montos ni ítems'}"
                                                          f" · (estaba aprobada por {aprobada_antes[0]}"
                                                          + (f" el {aprobada_antes[1].strftime('%d/%m/%Y %H:%M')})" if aprobada_antes[1] else ')'))
                else:
                    _oc_evento(orden, 'EDITADA', cambios or 'Ítems o datos actualizados')
            else:
                orden = OrdenCompra(tipo=datos['tipo'], empresa=datos['empresa'], numero=_siguiente_numero_oc(datos['tipo'], datos['empresa']),
                                    estado='BORRADOR', fecha=datos['fecha'],
                                    razon_social=datos['razon_social'], contacto=datos['contacto'], telefono=datos['telefono'],
                                    creado_por_id=session.get('user_id'), fecha_registro=ahora,
                                    duplicada_de_id=f.get('duplicada_de', type=int))
                db.session.add(orden)
                db.session.flush()
                _aplicar_datos_orden(orden, datos, items, prov, contacto)
                origen = OrdenCompra.query.get(orden.duplicada_de_id) if orden.duplicada_de_id else None
                _oc_evento(orden, 'CREADA', f"{len(items)} ítem(s) · {MONEDAS_OC[orden.moneda]['simbolo']} {orden.total:,.2f}"
                                           + (f" · copia de {_oc_codigo(origen)}" if origen else ''))
            if enviar:
                orden.estado, orden.enviado_por_id, orden.fecha_envio = 'ENVIADA', session.get('user_id'), ahora
                _oc_evento(orden, 'ENVIADA', f'Editada después de aprobada: vuelve a Gerencia para re-aprobación (Rev. {orden.revision})'
                           if reaprobacion else 'Enviada a Gerencia para aprobación')
                _notif_orden_enviada(orden, reaprobacion)
            _req_avisar_orden(orden, reqs_antes)
            registrar_log(f"{'Envió a Gerencia' if enviar else 'Guardó'} la {TIPOS_OC[orden.tipo]} {_oc_codigo(orden)} "
                          f"({orden.razon_social}, {MONEDAS_OC[orden.moneda]['simbolo']} {orden.total:,.2f})", 'bi-cart-check', 'text-primary')
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            if es_nueva:
                orden = None
            if intento == 2:
                flash('⛔ Otro usuario registró una orden al mismo tiempo. Vuelve a intentarlo.')
                return redirect(volver)
    flash(f"✅ {_oc_codigo(orden)} " + (f"editada (Rev. {orden.revision}) y enviada otra vez a Gerencia: queda POR APROBAR con tu motivo." if reaprobacion
                                        else ('enviada a Gerencia para aprobación' if enviar else 'guardada como borrador') + '.'))
    return redirect(url_for('oc_detalle', orden_id=orden.id))


# ---------------------------- DETALLE Y FLUJO ----------------------------
@app.route('/ordenes/<int:orden_id>')
@_ruta_oc()
def oc_detalle(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    eventos = OrdenCompraEvento.query.filter_by(orden_id=orden.id).order_by(OrdenCompraEvento.fecha.desc(), OrdenCompraEvento.id.desc()).all()
    docs = OrdenCompraDocumento.query.filter_by(orden_id=orden.id).order_by(OrdenCompraDocumento.id).all()
    ingreso = InsumoIngreso.query.get(orden.insumo_ingreso_id) if orden.insumo_ingreso_id else None
    duplicada_de = OrdenCompra.query.get(orden.duplicada_de_id) if orden.duplicada_de_id else None
    motivos = _oc_motivos('RECHAZO', orden.tipo)
    motivos_anul = _oc_motivos('ANULACION', orden.tipo)
    observaciones = [e for e in eventos if e.accion == 'OBSERVACION']
    contacto = OCContacto.query.get(orden.contacto_id) if orden.contacto_id else None
    ahora = hora_peru()
    reqs_orden = []
    for ri in _req_items_de_orden(orden).values():
        if ri.requerimiento not in reqs_orden:
            reqs_orden.append(ri.requerimiento)
    return render_template('oc_detalle.html', orden=orden, eventos=eventos, docs=docs, ingreso=ingreso, duplicada_de=duplicada_de, reqs_orden=reqs_orden,
                           motivos=motivos, motivos_anul=motivos_anul, observaciones=observaciones, contacto=contacto, empresas_oc=EMPRESAS_OC,
                           p=_oc_permisos(orden), estados=ESTADOS_OC, tipos=TIPOS_OC, destinos=DESTINOS_OC, monedas=MONEDAS_OC,
                           cfg=_oc_cfg(orden.empresa or 'ANCLAJES'), igv=IGV_OC, ahora=ahora, hoy=ahora.date(), seccion='lista',
                           cuentas=_cuentas_de(orden.oc_proveedor_id), pago=_oc_pago_info(orden, ahora.date()), atraso=_oc_atraso(orden, ahora.date()),
                           tipos_doc=TIPOS_DOC_OC, bancos=BANCOS_OC, tipos_cuenta=TIPOS_CUENTA_OC, docs_unicos=DOCS_UNICOS_OC, max_docs=MAX_DOCS_OC,
                           fecha_pago_min=orden.fecha - timedelta(days=30), rec=_oc_recepcion(orden),
                           hay_peso=any(i.peso_total for i in orden.items), peso_total=round(sum(i.peso_total or 0 for i in orden.items), 3))


def _accion_oc(orden_id, permiso):
    orden = OrdenCompra.query.get_or_404(orden_id)
    if not _oc_permisos(orden)[permiso]:
        flash(f'⛔ No se puede hacer eso: la orden está "{ESTADOS_OC[orden.estado]["txt"]}" o no tienes permiso.')
        return orden, redirect(url_for('oc_detalle', orden_id=orden.id))
    return orden, None


@app.route('/ordenes/<int:orden_id>/enviar', methods=['POST'])
@_ruta_oc('editar')
def oc_enviar(orden_id):
    orden, no = _accion_oc(orden_id, 'enviar')
    if no:
        return no
    orden.estado, orden.enviado_por_id, orden.fecha_envio = 'ENVIADA', session.get('user_id'), hora_peru()
    _oc_evento(orden, 'ENVIADA', 'Enviada a Gerencia para aprobación')
    _notif_orden_enviada(orden)
    registrar_log(f"Envió a Gerencia la {_oc_codigo(orden)}", 'bi-send', 'text-primary')
    db.session.commit()
    flash(f'✅ {_oc_codigo(orden)} enviada a Gerencia. Queda "Por aprobar".')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/retirar', methods=['POST'])
@_ruta_oc('editar')
def oc_retirar(orden_id):
    orden, no = _accion_oc(orden_id, 'retirar')
    if no:
        return no
    orden.estado = 'BORRADOR'
    _oc_evento(orden, 'RETIRADA', 'Retirada de aprobación para corregir')
    db.session.commit()
    flash('La orden volvió a BORRADOR: ya puedes corregirla y enviarla otra vez.')
    return redirect(url_for('oc_editar', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/aprobar', methods=['POST'])
@_ruta_oc('aprobar')
def oc_aprobar(orden_id):
    orden, no = _accion_oc(orden_id, 'aprobar')
    if no:
        return no
    # Si se re-aprueba una orden cuyo material ya llegó (se editó para cuadrarla), vuelve a la etapa en la que estaba
    etapa = _oc_etapa_por_entregas(orden)
    if etapa == 'CONFORME' and not orden.fecha_conforme:
        orden.conforme_por_id, orden.fecha_conforme = session.get('user_id'), hora_peru()
    orden.estado, orden.aprobado_por_id, orden.fecha_aprobacion = etapa, session.get('user_id'), hora_peru()
    _oc_evento(orden, 'APROBADA', ' '.join((request.form.get('comentario') or '').split())[:300]
               or (f'Re-aprobada (Rev. {orden.revision}) con firma y sello de Gerencia' if orden.revision else 'Aprobada con firma y sello de Gerencia'))
    _req_notificar_orden(orden, 'OC_APROBADA', f"Gerencia aprobó la {_oc_codigo(orden)} ({orden.razon_social})")
    _notif_orden_resuelta(orden, 'OC_APROBADA', ' '.join((request.form.get('comentario') or '').split())[:120])
    registrar_log(f"APROBÓ la {_oc_codigo(orden)} ({orden.razon_social}, {MONEDAS_OC[orden.moneda]['simbolo']} {orden.total:,.2f})",
                  'bi-patch-check-fill', 'text-success')
    db.session.commit()
    flash(f'✅ {_oc_codigo(orden)} APROBADA. El PDF ya lleva la firma y sello de Gerencia.')
    volver = (request.form.get('volver') or '').strip()
    if volver.startswith('/') and not volver.startswith('//') and '\\' not in volver:     # aprobada desde la lista: vuelve a la lista
        return redirect(volver)
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/rechazar', methods=['POST'])
@_ruta_oc('aprobar')
def oc_rechazar(orden_id):
    orden, no = _accion_oc(orden_id, 'rechazar')
    if no:
        return no
    opcion = OCMotivoRechazo.query.get(request.form.get('motivo_id', type=int)) if request.form.get('motivo_id', type=int) else None
    detalle = ' '.join((request.form.get('motivo') or '').split())[:300]
    if not opcion or (opcion.uso or 'RECHAZO') != 'RECHAZO' or (opcion.aplica or 'AMBAS') == 'RQ':
        flash('⛔ Elige el motivo del rechazo.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    orden.estado, orden.rechazado_por_id, orden.fecha_rechazo = 'RECHAZADA', session.get('user_id'), hora_peru()
    orden.rechazo_categoria, orden.rechazo_opcion, orden.motivo_rechazo = opcion.categoria, opcion.motivo, detalle or None
    texto = f"{opcion.categoria} · {opcion.motivo}" + (f" — {detalle}" if detalle else '')
    _oc_evento(orden, 'RECHAZADA', texto)
    _req_notificar_orden(orden, 'OC_RECHAZADA', f"Gerencia rechazó la {_oc_codigo(orden)}: los productos vuelven a esperar OC")
    _notif_orden_resuelta(orden, 'OC_RECHAZADA', texto)
    registrar_log(f"RECHAZÓ la {_oc_codigo(orden)}: {texto}", 'bi-x-octagon-fill', 'text-danger')
    db.session.commit()
    flash(f'{_oc_codigo(orden)} rechazada. Logística puede "Duplicarla" para corregirla con un número nuevo.')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/anular', methods=['POST'])
@_ruta_oc('editar')
def oc_anular(orden_id):
    orden, no = _accion_oc(orden_id, 'anular')
    if no:
        return no
    opcion = OCMotivoRechazo.query.get(request.form.get('motivo_id', type=int)) if request.form.get('motivo_id', type=int) else None
    detalle = ' '.join((request.form.get('motivo') or '').split())[:300]
    if not opcion or opcion.uso != 'ANULACION' or (opcion.aplica or 'AMBAS') == 'RQ':
        flash('⛔ Elige el motivo de la anulación.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    estado_antes = orden.estado
    orden.estado, orden.anulado_por_id, orden.fecha_anulacion = 'ANULADA', session.get('user_id'), hora_peru()
    orden.anulacion_categoria, orden.anulacion_opcion, orden.motivo_anulacion = opcion.categoria, opcion.motivo, detalle or None
    motivo = _oc_anulacion_txt(orden)
    _oc_evento(orden, 'ANULADA', f"{motivo} (estaba: {ESTADOS_OC[estado_antes]['txt']})")
    _req_notificar_orden(orden, 'OC_ANULADA', f"Se anuló la {_oc_codigo(orden)}: los productos vuelven a esperar OC")
    registrar_log(f"ANULÓ la {_oc_codigo(orden)}: {motivo}", 'bi-slash-circle', 'text-danger')
    db.session.commit()
    flash(f'{_oc_codigo(orden)} anulada. Su número no se vuelve a usar.')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


@app.route('/ordenes/<int:orden_id>/duplicar', methods=['POST'])
@_ruta_oc('editar')
def oc_duplicar(orden_id):
    orden, no = _accion_oc(orden_id, 'duplicar')
    if no:
        return no
    return redirect(url_for('oc_nueva', duplicar=orden.id))


def _subir_docs_orden(orden, claves, tipos=tuple(TIPOS_DOC_OC), viejas=None, entrega=None):
    """Sube los archivos doc_<TIPO>. Devuelve (cantidad, errores).
    Guía, factura, cotización y constancia de pago: UN solo archivo; si ya hay uno, el nuevo lo REEMPLAZA (queda en el historial).
    Certificado de calidad y otros: hasta 3 archivos. En `viejas` quedan las claves S3 de los reemplazados: se borran después del commit."""
    archivos, errores = [], []
    for tipo in tipos:
        lista = [a for a in request.files.getlist(f'doc_{tipo}') if a and a.filename]
        if not lista:
            continue
        nombre = TIPOS_DOC_OC.get(tipo, tipo)
        existentes = OrdenCompraDocumento.query.filter_by(orden_id=orden.id, tipo=tipo).all()
        if tipo == 'GUIA':          # la guía es de cada entrega (en llegadas parciales hay una guía por entrega)
            existentes = [d for d in existentes if (d.entrega_id or None) == (entrega.id if entrega else None)]
        if tipo in DOCS_UNICOS_OC and len(lista) > 1:
            errores.append(f'{nombre}: se sube UN solo archivo.')
            continue
        maximo = MAX_DOCS_OC.get(tipo)
        if maximo and len(existentes) + len(lista) > maximo:
            errores.append(f'{nombre}: máximo {maximo} archivos (ya hay {len(existentes)}). Borra uno para subir otro.')
            continue
        for a in lista:
            ok, info = _validar_documento_kardex(a)
            if ok:
                archivos.append((tipo, a, info, existentes if tipo in DOCS_UNICOS_OC else []))
            else:
                errores.append(info)
    if errores:
        return 0, errores
    for tipo, a, (ext, mime, tamano), reemplaza in archivos:
        s3_key = f"ordenes/{(orden.empresa or 'ANCLAJES').lower()}/{orden.tipo.lower()}_{_oc_numero_txt(orden)}/{tipo.lower()}_{uuid.uuid4().hex}.{ext}"
        a.stream.seek(0)
        s3_client.upload_fileobj(a.stream, S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': mime})
        claves.append(s3_key)
        nuevo = secure_filename(a.filename)[:200] or f'documento.{ext}'
        db.session.add(OrdenCompraDocumento(orden_id=orden.id, tipo=tipo, s3_key=s3_key, nombre_original=nuevo,
                                            entrega_id=entrega.id if (entrega is not None and tipo == 'GUIA') else None,
                                            content_type=mime, tamano_bytes=tamano, subido_por=session.get('nombre', ''), fecha=hora_peru()))
        for viejo in reemplaza:
            _oc_evento(orden, 'DOCUMENTO', f"Reemplazó {TIPOS_DOC_OC.get(tipo, tipo)}: {viejo.nombre_original} → {nuevo}")
            if viejas is not None:
                viejas.append(viejo.s3_key)
            db.session.delete(viejo)
    return len(archivos), []


