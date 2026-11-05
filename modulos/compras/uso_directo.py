# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · USO DIRECTO (bienes que NO van al inventario ni a insumos)
# Equipos de cómputo, celulares, muebles, herramientas, maquinaria... que la empresa compra para USARLOS.
# La orden sigue el flujo normal (aprobación de Gerencia, llegada, conformidad, pago). Al estar CONFORME no se ingresa
# a ningún inventario: se registra la ENTREGA (a quién, en qué ubicación; N° de serie y garantía opcionales por ítem).
# Todo queda en el "Registro de uso directo" para saber siempre qué se compró, dónde está y hasta cuándo tiene garantía.
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================
# La entrega reutiliza los campos de "seguimiento" de la orden: fecha_kardex / kardex_registrado_por_id = cuándo y quién
# registró la entrega, nota_seguimiento = nota de la entrega. directo_entregado_a = a quién se entregó.

DIAS_GARANTIA_POR_VENCER = 30
ESTADOS_DIRECTO = {'EN_CAMINO': {'txt': 'Por llegar', 'color': '#1d4ed8', 'fondo': '#eff6ff', 'icono': 'bi-truck'},
                   'POR_ENTREGAR': {'txt': 'Llegó · por entregar', 'color': '#b45309', 'fondo': '#fffbeb', 'icono': 'bi-hourglass-split'},
                   'ENTREGADO': {'txt': 'Entregado', 'color': '#15803d', 'fondo': '#f0fdf4', 'icono': 'bi-check-circle-fill'}}
GARANTIAS_DIRECTO = {'vigente': 'Vigente', 'por_vencer': f'Vence en {DIAS_GARANTIA_POR_VENCER} días o menos', 'vencida': 'Vencida', 'sin': 'Sin dato'}


def _directos_por_entregar(empresa=None):
    """Órdenes de USO DIRECTO conformes a las que aún no se les registra la entrega del bien."""
    try:
        lista = OrdenCompra.query.filter(OrdenCompra.estado == 'CONFORME', OrdenCompra.destino == 'DIRECTO',
                                         OrdenCompra.fecha_kardex.is_(None)).order_by(OrdenCompra.fecha_conforme).all()
    except Exception:
        db.session.rollback()
        return []
    return [o for o in lista if not o.es_contable and (not empresa or (o.empresa or 'ANCLAJES') == empresa)]


def _directo_estado(orden):
    if orden.fecha_kardex:
        return 'ENTREGADO'
    return 'POR_ENTREGAR' if orden.estado == 'CONFORME' else 'EN_CAMINO'


def _garantia_estado(fecha, hoy=None):
    """vigente / por_vencer / vencida / sin (y los días que faltan)."""
    if not fecha:
        return 'sin', None
    hoy = hoy or hora_peru().date()
    dias = (fecha - hoy).days
    if dias < 0:
        return 'vencida', dias
    return ('por_vencer' if dias <= DIAS_GARANTIA_POR_VENCER else 'vigente'), dias


app.add_template_global(_directo_estado, 'directo_estado')
app.add_template_global(_garantia_estado, 'garantia_estado')
app.add_template_global(ESTADOS_DIRECTO, 'estados_directo')


def _volver_seguro(valor, defecto):
    return valor if valor and valor.startswith('/') and not valor.startswith('//') else defecto


@app.route('/ordenes/<int:orden_id>/directo/entregar', methods=['POST'])
@_ruta_oc('contable')
def oc_directo_entregar(orden_id):
    """Registra (o corrige) la ENTREGA de un bien de uso directo: a quién, en qué ubicación, N° de serie y garantía por ítem."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    f = request.form
    volver = _volver_seguro(f.get('volver'), url_for('oc_detalle', orden_id=orden.id))
    p = _oc_permisos(orden)
    corrige = bool(orden.fecha_kardex)
    if not (p['entregar_directo'] or p['editar_directo']):
        flash('⛔ Solo se registra la entrega de una orden de USO DIRECTO que ya está conforme.')
        return redirect(volver)
    entregado_a = ' '.join((f.get('entregado_a') or '').split()).upper()[:120]
    if len(entregado_a) < 3:
        flash('⛔ Escribe A QUIÉN se entregó el bien (persona o área responsable).')
        return redirect(volver)
    ubis = {(v.valor or '').upper(): v.valor for v in _oc_catalogo('OC_DIRECTO_UBICACION', incluir_inactivos=True)}
    ubi = ' '.join((f.get('ubicacion') or '').split()).upper()[:100]
    if ubi not in ubis and ubi != (orden.directo_ubicacion or '').upper():
        flash('⛔ Elige la UBICACIÓN donde queda el bien.')
        return redirect(volver)
    nota = ' '.join((f.get('nota') or '').split())[:300] or None
    cambios, errores = [], []
    ubi_final = ubis.get(ubi, orden.directo_ubicacion)
    ubi_previa = orden.directo_ubicacion
    for it in orden.items:
        # a dónde va cada ítem: el elegido en ese ítem o, si no, la ubicación de la orden
        u_it = ' '.join((f.get(f'ubicacion_{it.id}') or '').split()).upper()
        nueva_u = ubis.get(u_it) or (it.directo_ubicacion if u_it and u_it == (it.directo_ubicacion or '').upper() else None) or ubi_final
        if corrige and (it.directo_ubicacion or ubi_previa) != nueva_u:
            cambios.append(f"ítem {it.item} va a: {it.directo_ubicacion or ubi_previa or '—'} → {nueva_u}")
        it.directo_ubicacion = nueva_u
        if not it.directo_categoria:
            it.directo_categoria = orden.directo_categoria
        serie = ' '.join((f.get(f'serie_{it.id}') or '').split()).upper()[:300] or None
        gar_txt = (f.get(f'garantia_{it.id}') or '').strip()
        gar = None
        if gar_txt:
            try:
                gar = datetime.strptime(gar_txt, '%Y-%m-%d').date()
            except ValueError:
                errores.append(f'Ítem {it.item}: la fecha de garantía no es válida.')
                continue
            if orden.fecha and gar < orden.fecha:
                errores.append(f'Ítem {it.item}: la garantía no puede vencer antes de la fecha de la orden.')
                continue
        if corrige and (serie != it.serie or gar != it.garantia_hasta):
            cambios.append(f"ítem {it.item}: serie {it.serie or '—'} → {serie or '—'}, garantía "
                           f"{it.garantia_hasta.strftime('%d/%m/%Y') if it.garantia_hasta else '—'} → {gar.strftime('%d/%m/%Y') if gar else '—'}")
        it.serie, it.garantia_hasta = serie, gar
    if errores:
        db.session.rollback()
        flash('⛔ ' + ' · '.join(errores))
        return redirect(volver)
    if corrige:
        if entregado_a != (orden.directo_entregado_a or ''):
            cambios.insert(0, f"entregado a: {orden.directo_entregado_a or '—'} → {entregado_a}")
        if (ubi_final or '') != (orden.directo_ubicacion or ''):
            cambios.insert(0, f"ubicación: {orden.directo_ubicacion or '—'} → {ubi_final}")
        if nota != orden.nota_seguimiento:
            cambios.append('nota de entrega actualizada')
    else:
        orden.kardex_registrado_por_id, orden.fecha_kardex = session.get('user_id'), hora_peru()
    orden.directo_entregado_a, orden.directo_ubicacion, orden.nota_seguimiento = entregado_a, ubi_final, nota
    n_series = sum(1 for it in orden.items if it.serie)
    n_gar = sum(1 for it in orden.items if it.garantia_hasta)
    if corrige:
        if not cambios:
            db.session.rollback()
            flash('No había cambios en los datos de la entrega.')
            return redirect(volver)
        _oc_evento(orden, 'DIRECTO_EDITADO', 'Datos de la entrega corregidos: ' + '; '.join(cambios))
        registrar_log(f"Corrigió la entrega (uso directo) de la {_oc_codigo(orden)}", 'bi-pencil', 'text-warning')
        msg = f'✅ {_oc_codigo(orden)}: datos de la entrega actualizados.'
    else:
        _oc_evento(orden, 'ENTREGA_DIRECTO', f"Bien de USO DIRECTO entregado a {entregado_a} · {ubi_final}"
                   + (f" · {n_series} con N° de serie" if n_series else '') + (f" · {n_gar} con garantía" if n_gar else '')
                   + (f" · {nota}" if nota else ''))
        registrar_log(f"Registró la entrega (uso directo) de la {_oc_codigo(orden)} a {entregado_a}", 'bi-pc-display', 'text-success')
        msg = f'✅ {_oc_codigo(orden)}: entrega registrada ({entregado_a} · {ubi_final}). No se sumó nada al inventario: queda en el Registro de uso directo.'
    db.session.commit()
    flash(msg)
    return redirect(volver)


@app.route('/ordenes/<int:orden_id>/directo/deshacer', methods=['POST'])
@_ruta_oc('admin')
def oc_directo_deshacer(orden_id):
    """Gerencia quita el registro de entrega (vuelve a 'por entregar'). Los N° de serie y garantías se conservan."""
    orden = OrdenCompra.query.get_or_404(orden_id)
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    if orden.destino != 'DIRECTO' or not orden.fecha_kardex or len(motivo) < 5:
        flash('⛔ Escribe por qué se quita el registro de la entrega.')
        return redirect(url_for('oc_detalle', orden_id=orden.id))
    _oc_evento(orden, 'INGRESO_DESHECHO', f"Se quitó el registro de entrega (uso directo, estaba con {orden.directo_entregado_a or '-'}): {motivo}")
    orden.kardex_registrado_por_id, orden.fecha_kardex, orden.nota_seguimiento, orden.directo_entregado_a = None, None, None, None
    db.session.commit()
    flash('Registro de entrega quitado: la orden vuelve a "uso directo · por entregar".')
    return redirect(url_for('oc_detalle', orden_id=orden.id))


def _registro_directo_filas(f):
    """Un renglón por cada ítem de las órdenes de uso directo ya aprobadas (por llegar, por entregar o entregados)."""
    hoy = hora_peru().date()
    q = OrdenCompra.query.filter(OrdenCompra.destino == 'DIRECTO', OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME']))
    filas = []
    for o in q.order_by(OrdenCompra.fecha.desc(), OrdenCompra.id.desc()).all():
        emp = o.empresa or 'ANCLAJES'
        est = _directo_estado(o)
        if f['empresa'] != 'TODAS' and emp != f['empresa']:
            continue
        if f['estado'] and est != f['estado']:
            continue
        if f['activo'] and bool(o.directo_activo_fijo) != (f['activo'] == 'si'):
            continue
        for it in o.items:
            cat = it.directo_categoria or o.directo_categoria or ''      # cada ítem puede tener su categoría y su lugar
            ubi = it.directo_ubicacion or o.directo_ubicacion or ''
            if f['categoria'] and cat != f['categoria']:
                continue
            if f['ubicacion'] and ubi != f['ubicacion']:
                continue
            g, dias = _garantia_estado(it.garantia_hasta, hoy)
            if f['garantia'] and g != f['garantia']:
                continue
            if f['q']:
                texto = ' '.join(x or '' for x in (_oc_codigo(o), it.descripcion, it.detalle, it.serie, o.razon_social, o.ruc, cat,
                                                   ubi, o.directo_detalle, o.directo_entregado_a, o.numero_factura,
                                                   _oc_solicitante_txt(o), o.area_solicitante)).upper()
                if not all(t in texto for t in f['q'].upper().split()):
                    continue
            filas.append({'o': o, 'it': it, 'estado': est, 'garantia': g, 'dias': dias, 'empresa': emp, 'cat': cat, 'ubi': ubi})
    return filas


def _registro_directo_filtros():
    a = request.args
    emp = (a.get('empresa') or 'TODAS').upper()
    est = (a.get('estado') or '').upper()
    gar = (a.get('garantia') or '').lower()
    return {'empresa': emp if emp in EMPRESAS_OC else 'TODAS', 'estado': est if est in ESTADOS_DIRECTO else '',
            'categoria': (a.get('categoria') or '').strip()[:100], 'ubicacion': (a.get('ubicacion') or '').strip()[:100],
            'garantia': gar if gar in GARANTIAS_DIRECTO else '', 'activo': a.get('activo') if a.get('activo') in ('si', 'no') else '',
            'q': ' '.join((a.get('q') or '').split())[:80]}


@app.route('/ordenes/uso-directo')
@_ruta_oc('contable')
def oc_registro_directo():
    """Registro de USO DIRECTO: qué se compró (que no va al inventario), dónde está, quién lo tiene, serie y garantía."""
    f = _registro_directo_filtros()
    filas = _registro_directo_filas(f)
    if request.args.get('exportar') == 'excel':
        return _registro_directo_excel(filas, f)
    resumen = {'bienes': len(filas), 'entregados': sum(1 for x in filas if x['estado'] == 'ENTREGADO'),
               'por_entregar': len({x['o'].id for x in filas if x['estado'] == 'POR_ENTREGAR'}),
               'en_camino': sum(1 for x in filas if x['estado'] == 'EN_CAMINO'),
               'por_vencer': sum(1 for x in filas if x['garantia'] == 'por_vencer'),
               'vencidas': sum(1 for x in filas if x['garantia'] == 'vencida'), 'montos': {}}
    por_cat = {}
    for x in filas:
        mon = x['o'].moneda or 'PEN'
        resumen['montos'][mon] = resumen['montos'].get(mon, 0) + (x['it'].total or 0)
        c = por_cat.setdefault(x['cat'] or 'SIN CATEGORÍA', {'n': 0, 'montos': {}})
        c['n'] += 1
        c['montos'][mon] = c['montos'].get(mon, 0) + (x['it'].total or 0)
    todas = OrdenCompra.query.filter(OrdenCompra.destino == 'DIRECTO').all()
    categorias = sorted({o.directo_categoria for o in todas if o.directo_categoria} | {i.directo_categoria for o in todas for i in o.items if i.directo_categoria}
                        | {v.valor for v in _oc_catalogo('OC_DIRECTO_CATEGORIA')})
    ubicaciones = sorted({o.directo_ubicacion for o in todas if o.directo_ubicacion} | {i.directo_ubicacion for o in todas for i in o.items if i.directo_ubicacion}
                         | {v.valor for v in _oc_catalogo('OC_DIRECTO_UBICACION')})
    return render_template('oc_uso_directo.html', filas=filas[:600], total_filas=len(filas), f=f, resumen=resumen,
                           por_cat=sorted(por_cat.items(), key=lambda kv: -kv[1]['n']), categorias=categorias, ubicaciones=ubicaciones,
                           estados=ESTADOS_DIRECTO, garantias=GARANTIAS_DIRECTO, empresas_oc=EMPRESAS_OC, monedas=MONEDAS_OC,
                           puede_ver_oc=session.get('role') in ROLES_OC_VEN, dias_aviso=DIAS_GARANTIA_POR_VENCER,
                           hoy=hora_peru().date(), seccion='directo')


def _registro_directo_excel(filas, f):
    from openpyxl import Workbook
    wb = Workbook()
    datos = []
    for x in filas:
        o, it = x['o'], x['it']
        datos.append([EMPRESAS_OC.get(x['empresa'], {}).get('corto', x['empresa']), _oc_codigo(o), o.fecha, ESTADOS_DIRECTO[x['estado']]['txt'],
                      (x['cat'] or '').capitalize(), x['ubi'], o.directo_detalle or '',
                      'Sí' if o.directo_activo_fijo else 'No', it.descripcion, it.detalle or '', it.cantidad, it.um, it.precio_unitario, it.total,
                      o.moneda, it.serie or '', it.garantia_hasta, GARANTIAS_DIRECTO[x['garantia']], o.directo_entregado_a or '',
                      o.fecha_kardex, o.kardex_registrado_por.nombre_completo if o.kardex_registrado_por else '', o.nota_seguimiento or '',
                      o.razon_social, o.ruc, o.numero_factura or '', _oc_solicitante_txt(o) or '', (o.area_solicitante or '').title()])
    _xlsx_hoja(wb, 'Uso directo', ['Empresa', 'Orden', 'Fecha OC', 'Estado', 'Categoría', 'Ubicación', 'Para qué / detalle', 'Activo fijo',
                                   'Bien', 'Detalle del ítem', 'Cantidad', 'U.M.', 'P. Unit. (sin IGV)', 'Total (sin IGV)', 'Moneda', 'N° de serie',
                                   'Garantía hasta', 'Garantía', 'Entregado a', 'Fecha de entrega', 'Registró la entrega', 'Nota de entrega',
                                   'Proveedor', 'RUC', 'Factura', 'Solicitó', 'Área'],
               datos, formatos={2: 'dd/mm/yyyy', 10: '#,##0.####', 12: '#,##0.00##', 13: '#,##0.00', 16: 'dd/mm/yyyy', 19: 'dd/mm/yyyy hh:mm'},
               primera=True, nota=f"Registro de uso directo (bienes que no van al inventario) · exportado el {hora_peru().strftime('%d/%m/%Y %H:%M')} "
                                  f"por {session.get('nombre', '')} · {len(datos)} bien(es)")
    registrar_log(f"Exportó el registro de uso directo ({len(datos)} bienes) a Excel", 'bi-file-earmark-excel', 'text-success')
    return _xlsx_respuesta(wb, f"uso_directo_{hora_peru().strftime('%Y%m%d_%H%M')}.xlsx")
