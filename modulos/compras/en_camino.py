# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · EN CAMINO (lo comprado que todavía no está en el inventario)
# Para Gerencia (cuentas admin): en el inventario de Anclajes, de Import Bolts y de Insumos se ve, por producto,
# cuánto viene en órdenes APROBADAS, cuándo llega (o "sin fecha confirmada"), en qué paso está y si ya se sumó al stock.
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================
# Cuándo aparece: desde que Gerencia APRUEBA la orden (antes no es seguro que se compre).
# Pasos: En camino -> Llegó (falta conformidad) -> Conforme (falta sumar al inventario) -> Sumado al inventario.
# Lo ya sumado se sigue mostrando DIAS_INGRESO_RECIENTE días ("+300 sumados hace 2 días") y luego desaparece.

DIAS_INGRESO_RECIENTE = 7
ROLES_EN_CAMINO = ['admin']
ETAPAS_CAMINO = {
    'EN_CAMINO': {'txt': 'En camino', 'corto': 'en camino', 'color': '#b45309', 'fondo': '#fffbeb', 'borde': '#fcd34d', 'icono': 'bi-truck'},
    'POR_CONFORMIDAD': {'txt': 'Llegó · falta la conformidad', 'corto': 'llegó (por revisar)', 'color': '#0e7490', 'fondo': '#ecfeff', 'borde': '#a5f3fc', 'icono': 'bi-clipboard-check'},
    'POR_INGRESAR': {'txt': 'Conforme · falta sumar al inventario', 'corto': 'por sumar al stock', 'color': '#6d28d9', 'fondo': '#f5f3ff', 'borde': '#ddd6fe', 'icono': 'bi-box-arrow-in-down'},
    'INGRESADO': {'txt': 'Sumado al inventario', 'corto': 'sumados', 'color': '#15803d', 'fondo': '#f0fdf4', 'borde': '#bbf7d0', 'icono': 'bi-check2-circle'},
}
ORDEN_ETAPAS = ['EN_CAMINO', 'POR_CONFORMIDAD', 'POR_INGRESAR', 'INGRESADO']


def _fecha_txt(v):
    return v.strftime('%d/%m/%Y') if v else ''


def _dias_txt(fecha, hoy, pasado=False):
    """'hoy', 'ayer', 'hace 3 días' / 'mañana', 'en 5 días' para una fecha (date o datetime). pasado=True: algo que ya ocurrió."""
    if not fecha:
        return ''
    f = fecha.date() if isinstance(fecha, datetime) else fecha
    d = (hoy - f).days
    if pasado and d < 0:
        d = 0
    if d == 0:
        return 'hoy'
    if d == 1:
        return 'ayer'
    if d == -1:
        return 'mañana'
    return f'hace {d} días' if d > 0 else f'en {-d} días'


def _solo_fecha(v):
    return v.date() if isinstance(v, datetime) else v


def _camino_linea_tiempo(o, rec, hoy, ingreso_fecha, ingreso_completo):
    """Pasos de la orden para la mini línea de tiempo: aprobada -> llegada -> conformidad -> en inventario."""
    esperada = _oc_fecha_esperada(o)
    atrasada = bool(esperada and esperada < hoy and rec['pendiente'] > 0)
    llego = bool(rec['entregas']) or bool(o.fecha_llegada)
    pasos = [{'txt': 'Aprobada', 'fecha': _fecha_txt(o.fecha_aprobacion), 'estado': 'hecho'}]
    if llego:
        pasos.append({'txt': 'Llegó' + (' (parcial)' if rec['pendiente'] > 0 else ''), 'fecha': _fecha_txt(o.fecha_llegada), 'estado': 'hecho'})
    else:
        pasos.append({'txt': ('Llega ' + _fecha_txt(esperada)) if esperada else 'Sin fecha confirmada', 'fecha': ('atrasada' if atrasada else _dias_txt(esperada, hoy)) if esperada else '',
                      'estado': 'atrasado' if atrasada else 'actual'})
    conforme = bool(o.fecha_conforme) and not rec['sin_conformar']
    conf_parcial = not conforme and bool(rec['entregas']) and not rec['sin_conformar']     # lo que llegó ya tiene conformidad; falta el resto
    f_conf = o.fecha_conforme or max([e.fecha_conforme for e in rec['entregas'] if e.fecha_conforme] or [None])
    pasos.append({'txt': 'Conforme (parcial)' if conf_parcial else 'Conformidad', 'fecha': _fecha_txt(f_conf) if (conforme or conf_parcial) else '',
                  'estado': 'hecho' if (conforme or conf_parcial) else ('actual' if llego else 'pendiente')})
    ing_parcial = not ingreso_completo and bool(ingreso_fecha)
    pasos.append({'txt': 'En inventario (parcial)' if ing_parcial else 'En inventario', 'fecha': _fecha_txt(ingreso_fecha) if (ingreso_completo or ing_parcial) else '',
                  'estado': 'hecho' if (ingreso_completo or ing_parcial) else ('actual' if (conforme or conf_parcial) else 'pendiente')})
    return pasos, esperada, atrasada


def _en_camino(destino, empresa):
    """Lo que viene para un inventario: destino 'GENERAL' (productos de Anclajes / Import Bolts) o 'INSUMOS' (insumos de esa empresa).
    Devuelve None si el usuario no es de Gerencia. {'items': {clave: [líneas]}, 'ordenes': [...], 'resumen': {...}}"""
    if session.get('role') not in ROLES_EN_CAMINO:
        return None
    cache = g.get('_en_camino_cache')
    if cache is None:
        cache = g._en_camino_cache = {}
    if (destino, empresa) in cache:
        return cache[(destino, empresa)]
    try:
        _asegurar_oc()
        res = _en_camino_calcular(destino, empresa)
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudo calcular lo que viene en camino")
        res = None
    cache[(destino, empresa)] = res
    return res


def _en_camino_calcular(destino, empresa):
    ahora = hora_peru()
    hoy = ahora.date()
    limite = ahora - timedelta(days=DIAS_INGRESO_RECIENTE)
    ordenes = [o for o in OrdenCompra.query.filter(OrdenCompra.estado.in_(['APROBADA', 'RECIBIDA', 'CONFORME']), OrdenCompra.tipo == 'OC',
                                                   OrdenCompra.destino == destino).all() if (o.empresa or 'ANCLAJES') == empresa]
    por_clave, lista_ordenes = {}, []
    ingresos_ins = {}
    if destino == 'INSUMOS':
        ids = [o.insumo_ingreso_id for o in ordenes if o.insumo_ingreso_id]
        ingresos_ins = {i.id: i for i in InsumoIngreso.query.filter(InsumoIngreso.id.in_(ids or [0])).all()}
    for o in ordenes:
        # una orden ya sumada al inventario hace más de N días no se mira
        if destino == 'GENERAL' and o.estado == 'CONFORME' and o.fecha_kardex and o.fecha_kardex < limite:
            continue
        if destino == 'INSUMOS' and o.insumo_ingreso_id:
            ing = ingresos_ins.get(o.insumo_ingreso_id)
            f_ing = (ing.fecha_registro or ing.fecha) if ing else None
            if not f_ing or f_ing < limite:
                continue
        rec = _oc_recepcion(o)
        lineas, ultimo_ingreso = [], None
        ingreso_por_item = {}
        for e in rec['entregas']:
            for ei in e.items:
                if ei.fecha_ingreso:
                    x = ingreso_por_item.setdefault(ei.item_id, {'fecha': None, 'kardex': 0.0})
                    x['fecha'] = max(filter(None, [x['fecha'], ei.fecha_ingreso]))
                    x['kardex'] += ei.cantidad_kardex if ei.cantidad_kardex is not None else (ei.cantidad or 0)
        for it in o.items:
            d = rec['items'].get(it.id, {})
            pedido = round((it.cantidad or 0) - (it.cantidad_cancelada or 0), 4)
            llego, conf, ing = d.get('llego', 0), d.get('conforme', 0), d.get('ingresado', 0)
            info_ing = ingreso_por_item.get(it.id)
            f_ing, cant_kardex = (info_ing['fecha'], info_ing['kardex']) if info_ing else (it.fecha_ingreso, it.cantidad_kardex)
            if destino == 'INSUMOS':
                clave = it.insumo_id
                if not clave:
                    continue
                if o.insumo_ingreso_id:
                    ing_obj = ingresos_ins.get(o.insumo_ingreso_id)
                    partes = {'INGRESADO': pedido}
                    f_ing, cant_kardex = ((ing_obj.fecha_registro or ing_obj.fecha) if ing_obj else None), pedido
                else:
                    partes = {'EN_CAMINO': d.get('pendiente', pedido), 'POR_CONFORMIDAD': max(llego - conf, 0), 'POR_INGRESAR': conf}
            else:
                clave = (it.codigo or '').upper().strip()
                if not clave:
                    continue
                if not ing and it.fecha_ingreso:          # ingreso antiguo (sin entregas): todo lo que llegó
                    ing = llego or pedido
                partes = {'EN_CAMINO': d.get('pendiente', pedido), 'POR_CONFORMIDAD': max(llego - conf, 0), 'POR_INGRESAR': max(conf - ing, 0)}
                if ing and f_ing and f_ing >= limite:
                    partes['INGRESADO'] = cant_kardex or ing
            partes = {k: round(v, 4) for k, v in partes.items() if v and v > 0}
            if 'INGRESADO' in partes and (not f_ing or f_ing < limite):
                partes.pop('INGRESADO')
            if not partes:
                continue
            if f_ing and (not ultimo_ingreso or f_ing > ultimo_ingreso):
                ultimo_ingreso = f_ing
            etapa = next(k for k in ORDEN_ETAPAS if k in partes)
            lineas.append({'clave': clave, 'item': it, 'etapa': etapa, 'partes': partes, 'pedido': pedido, 'llego': llego,
                           'um': it.um or '', 'descripcion': it.descripcion, 'fecha_ingreso': f_ing})
        if not lineas:
            continue
        completo = (bool(o.insumo_ingreso_id) if destino == 'INSUMOS' else _oc_ingreso_estado(o)['completo'])
        pasos, esperada, atrasada = _camino_linea_tiempo(o, rec, hoy, ultimo_ingreso, completo)
        etapa_orden = min((ln['etapa'] for ln in lineas), key=ORDEN_ETAPAS.index)
        resumen_o = {'id': o.id, 'codigo': _oc_codigo(o), 'url': url_for('oc_detalle', orden_id=o.id), 'proveedor': o.razon_social or '',
                     'importacion': bool(o.es_importacion), 'monto': f"{MONEDAS_OC[o.moneda]['simbolo']} {(o.total or 0):,.2f}",
                     'aprobada': _fecha_txt(o.fecha_aprobacion), 'esperada': _fecha_txt(esperada), 'atrasada': atrasada,
                     'sin_fecha': not esperada and not (rec['entregas'] or o.fecha_llegada), 'etapa': etapa_orden, 'pasos': pasos,
                     'ingreso': _fecha_txt(ultimo_ingreso), 'ingreso_hace': _dias_txt(ultimo_ingreso, hoy, True) if ultimo_ingreso else '',
                     'estado_txt': ESTADOS_OC[o.estado]['txt'], 'esperada_d': esperada,
                     'lineas': [{'codigo': (ln['item'].codigo or '') if destino == 'GENERAL' else '', 'descripcion': ln['descripcion'], 'um': ln['um'],
                                 'partes': [{'etapa': k, 'cant': v} for k, v in ln['partes'].items()]} for ln in lineas]}
        lista_ordenes.append(resumen_o)
        for ln in lineas:
            por_clave.setdefault(ln['clave'], []).append({
                'orden_id': o.id, 'codigo': resumen_o['codigo'], 'url': resumen_o['url'], 'proveedor': resumen_o['proveedor'],
                'importacion': resumen_o['importacion'], 'aprobada': resumen_o['aprobada'], 'esperada': resumen_o['esperada'],
                'atrasada': atrasada, 'sin_fecha': resumen_o['sin_fecha'], 'etapa': ln['etapa'], 'um': ln['um'],
                'pedido': ln['pedido'], 'llego': ln['llego'], 'partes': ln['partes'], 'pasos': pasos,
                'ingreso': _fecha_txt(ln['fecha_ingreso']) if 'INGRESADO' in ln['partes'] else '',
                'ingreso_hace': _dias_txt(ln['fecha_ingreso'], hoy, True) if 'INGRESADO' in ln['partes'] and ln['fecha_ingreso'] else ''})
    # orden: primero lo que llega antes; las sin fecha al final
    lista_ordenes.sort(key=lambda r: (ORDEN_ETAPAS.index(r['etapa']) if r['etapa'] != 'EN_CAMINO' else -1, r['esperada_d'] or date.max, r['id']))
    for r in lista_ordenes:
        r.pop('esperada_d', None)
    en_camino = [r for r in lista_ordenes if r['etapa'] == 'EN_CAMINO']
    fechas = sorted(datetime.strptime(r['esperada'], '%d/%m/%Y').date() for r in en_camino if r['esperada'] and not r['atrasada'])
    por_aprobar = sum(1 for o in OrdenCompra.query.filter(OrdenCompra.estado == 'ENVIADA', OrdenCompra.tipo == 'OC',
                                                          OrdenCompra.destino == destino).all() if (o.empresa or 'ANCLAJES') == empresa)
    resumen = {'en_camino': len(en_camino), 'importacion': sum(1 for r in en_camino if r['importacion']),
               'atrasadas': sum(1 for r in en_camino if r['atrasada']), 'sin_fecha': sum(1 for r in en_camino if r['sin_fecha']),
               'por_conformidad': sum(1 for r in lista_ordenes if r['etapa'] == 'POR_CONFORMIDAD'),
               'por_ingresar': sum(1 for r in lista_ordenes if r['etapa'] == 'POR_INGRESAR'),
               'ingresadas': sum(1 for r in lista_ordenes if r['etapa'] == 'INGRESADO'),
               'proxima': _fecha_txt(fechas[0]) if fechas else '', 'proxima_hace': _dias_txt(fechas[0], hoy) if fechas else '',
               'por_aprobar': por_aprobar, 'productos': len(por_clave), 'dias_reciente': DIAS_INGRESO_RECIENTE}
    return {'items': por_clave, 'ordenes': lista_ordenes, 'resumen': resumen, 'etapas': ETAPAS_CAMINO, 'destino': destino, 'empresa': empresa}


def _en_camino_totales(lineas):
    """Para el botón del producto: cuánto hay en cada paso (sumando las órdenes; misma U.M.)."""
    tot = {}
    for ln in lineas or []:
        for k, v in ln['partes'].items():
            x = tot.setdefault(k, {'cant': 0.0, 'um': ln['um'], 'hace': ''})
            x['cant'] = round(x['cant'] + v, 4)
            if k == 'INGRESADO' and ln['ingreso_hace']:
                x['hace'] = ln['ingreso_hace']
            if x['um'] != ln['um']:
                x['um'] = ''
    return [(k, tot[k]) for k in ORDEN_ETAPAS if k in tot]


app.add_template_global(_en_camino, 'en_camino')
app.add_template_global(_en_camino_totales, 'en_camino_totales')
