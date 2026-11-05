# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · REPORTES DE COMPRAS (tablero /ordenes/reportes)
#   Visión EJECUTIVA: resumen accionable, gasto con comparación vs. el periodo anterior y mini tendencia, gasto por mes,
#                     Pareto de proveedores, por empresa / área / motivo / cliente / solicitante (clic = filtro cruzado).
#   Visión OPERATIVA: órdenes detenidas AHORA en cada paso, línea del proceso (mediana vs. meta), OTIF,
#                     semáforo de atrasos por proveedor y matriz de riesgo (cuánto le compramos vs. % de atraso).
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si su código estuviera
# escrito ahí. Usa directamente los modelos, variables y funciones de app.py y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================
# Montos SIN IGV por defecto (igual que Mejores precios); con ?igv=1 se ven con IGV (lo que se paga). Soles y dólares nunca se suman.
# Cuentan las órdenes APROBADAS (aprobada, llegó o conforme) con FECHA DE LA ORDEN en el periodo.

ESTADOS_REPORTE_OC = ('APROBADA', 'RECIBIDA', 'CONFORME')
# Metas de cada paso (en días). Se pueden cambiar con SystemConfig 'oc_metas_pasos' = JSON, p. ej. {"enviada_aprobada": 2}
METAS_PASOS_OC = {'rq_oc': 2, 'creada_enviada': 1, 'enviada_aprobada': 1, 'aprobada_llegada': 15, 'llegada_conforme': 1, 'conforme_ingreso': 1,
                  'aprobada_pago': 30, 'ciclo': 21}
MIN_ORDENES_RANKING_OC = 3       # un proveedor entra al ranking de atrasos desde 3 órdenes con fecha ya vencida o cumplida
ATRASO_ALERTA_PCT_OC = 25        # matriz de riesgo: desde este % de atraso el proveedor está en zona de alerta
# Filtro cruzado: clic en una barra -> todo el tablero se filtra por ese valor (parámetro de la URL)
FILTROS_CRUZADOS_OC = {
    'prov': ('Proveedor', lambda o: o.razon_social),
    'area': ('Área', lambda o: (o.area_solicitante or '').title()),
    'motivo': ('Motivo', lambda o: (o.motivo_compra or '').capitalize()),
    'cliente': ('Cliente', lambda o: o.cliente_razon),
    'solic': ('Solicitó', lambda o: _oc_solicitante_txt(o)),
    'empresa_c': ('Empresa', lambda o: EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', o.empresa)),
}
# (clave, texto, ayuda, texto corto para el gráfico del proceso)
PASOS_REPORTE_OC = [
    ('rq_oc', 'Requerimiento → OC creada', 'Desde que Almacén pide hasta que Logística arma la orden', 'Arma la OC'),
    ('creada_enviada', 'OC creada → enviada a Gerencia', 'Logística termina y la envía', 'Envía'),
    ('enviada_aprobada', 'Enviada → aprobada', 'Lo que demora Gerencia en aprobar', 'Aprueba'),
    ('aprobada_llegada', 'Aprobada → llega el material', 'Lo que demora el proveedor (1.ª entrega)', 'Proveedor'),
    ('llegada_conforme', 'Llegada → conformidad', 'Logística revisa cada entrega', 'Conformidad'),
    ('conforme_ingreso', 'Conformidad → ingreso al Kardex', 'Almacén ingresa cada producto', 'Ingreso'),
    ('aprobada_pago', 'Aprobada → pagada', 'Según la condición de pago', 'Pago'),
    ('ciclo', 'Ciclo completo: OC creada → todo ingresado', 'Solo compras para el inventario ya ingresadas', 'Ciclo'),
]
PASOS_PROCESO_OC = ['rq_oc', 'creada_enviada', 'enviada_aprobada', 'aprobada_llegada', 'llegada_conforme', 'conforme_ingreso']
# Órdenes detenidas AHORA: (clave, qué espera, quién la tiene, meta (paso), vista de la lista de órdenes)
DETENIDAS_OC = [
    ('borrador', 'Por enviar a Gerencia', 'Logística', 'creada_enviada', 'curso'),
    ('aprobar', 'Esperando la aprobación de Gerencia', 'Gerencia', 'enviada_aprobada', 'aprobar'),
    ('proveedor', 'Esperando que llegue el material', 'Proveedor', 'aprobada_llegada', 'recibir'),
    ('conformidad', 'Llegó: falta dar la conformidad', 'Logística', 'llegada_conforme', 'recibir'),
    ('ingreso', 'Conforme: falta ingresar al inventario', 'Almacén', 'conforme_ingreso', None),
]
FRASES_DETENIDAS_OC = {'borrador': 'por enviar a Gerencia (Logística)', 'aprobar': 'esperando la aprobación de Gerencia',
                       'proveedor': 'esperando que llegue el material del proveedor', 'conformidad': 'que llegaron y falta dar la conformidad (Logística)',
                       'ingreso': 'conformes que falta ingresar al inventario (Almacén)'}


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


def _oc_monto(o, con_igv=False):
    """Monto de la orden: SIN IGV (subtotal) o con IGV (total, lo que se paga). Las importaciones no llevan IGV."""
    if con_igv:
        return o.total or 0
    if o.subtotal:
        return o.subtotal
    return max((o.total or 0) - (o.igv or 0), 0)


def _anio_antes(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                 # 29 de febrero
        return d.replace(year=d.year - 1, day=28)


def _oc_metas_pasos():
    metas = dict(METAS_PASOS_OC)
    try:
        fila = SystemConfig.query.get('oc_metas_pasos')
        if fila and fila.value:
            metas.update({k: float(v) for k, v in json.loads(fila.value).items() if k in metas and v not in (None, '')})
    except Exception:
        pass
    return metas


def _oc_variacion(actual, antes):
    """% de cambio vs. el periodo anterior (None si antes no hubo nada: no se muestra '▲ ∞%')."""
    if not antes:
        return None
    return round(100 * (actual - antes) / antes, 1)


def _oc_entregas_de(ordenes):
    """Entregas y sus ítems de muchas órdenes en 2 consultas: ({orden_id: [entregas]}, {entrega_id: [ítems]})."""
    ids = [o.id for o in ordenes]
    ent, items = {}, {}
    if not ids:
        return ent, items
    lista = OrdenCompraEntrega.query.filter(OrdenCompraEntrega.orden_id.in_(ids)).order_by(OrdenCompraEntrega.orden_id, OrdenCompraEntrega.numero).all()
    for e in lista:
        ent.setdefault(e.orden_id, []).append(e)
    eids = [e.id for e in lista]
    if eids:
        for ei in OrdenCompraEntregaItem.query.filter(OrdenCompraEntregaItem.entrega_id.in_(eids)).all():
            items.setdefault(ei.entrega_id, []).append(ei)
    return ent, items


def _oc_otif_orden(o, ents, items_ent, hoy):
    """OTIF de una orden con fecha de entrega: llegó TODO (sin saldo cerrado) a más tardar en la fecha prometida.
    None si no tiene fecha o todavía está en plazo. motivo: ok / tarde / incompleto / no_llego."""
    esp = _oc_fecha_esperada(o)
    pedido = {it.id: (it.cantidad or 0) for it in o.items}
    if not esp or not pedido:
        return None
    cancelado = any((it.cantidad_cancelada or 0) > 0 for it in o.items)
    llego, completa = {}, None
    for e in sorted(ents, key=lambda e: e.fecha):
        for ei in items_ent.get(e.id, []):
            llego[ei.item_id] = llego.get(ei.item_id, 0) + (ei.cantidad or 0)
        if completa is None and all(llego.get(i, 0) + 1e-9 >= q for i, q in pedido.items()):
            completa = e.fecha.date()
    if not ents and o.fecha_llegada and o.tipo == 'OS':          # servicio sin entregas registradas: cuenta la llegada
        completa = o.fecha_llegada.date()
    if completa is None and not cancelado and hoy <= esp:
        return None                                              # aún en plazo: no se juzga
    if completa is not None and not cancelado:
        motivo = 'ok' if completa <= esp else 'tarde'
    else:
        motivo = 'incompleto' if (llego or o.fecha_llegada) else 'no_llego'
    return {'motivo': motivo, 'esperada': esp, 'completa': completa}


def _oc_otif(ordenes, ents, items_ent, hoy):
    r = {'n': 0, 'ok': 0, 'tarde': 0, 'incompleto': 0, 'no_llego': 0, 'pct': None}
    for o in ordenes:
        x = _oc_otif_orden(o, ents.get(o.id, []), items_ent, hoy)
        if x:
            r['n'] += 1
            r[x['motivo']] += 1
    if r['n']:
        r['pct'] = round(100 * r['ok'] / r['n'])
    return r


def _oc_detenidas(activas, ents, items_ent, metas, hoy):
    """Órdenes que están esperando AHORA en cada paso (sin importar el periodo): cuántas, desde cuándo y cuántas pasaron su meta."""
    ahora = hora_peru()
    grupos = {k: {'clave': k, 'txt': txt, 'quien': quien, 'meta': metas.get(paso), 'vista': vista, 'ordenes': []} for k, txt, quien, paso, vista in DETENIDAS_OC}

    def poner(k, o, desde, fuera=None):
        dias = _dias_entre(desde, ahora) if desde else None
        dias = round(dias, 1) if dias is not None else None
        meta = grupos[k]['meta']
        if fuera is None:
            fuera = bool(dias is not None and meta is not None and dias > meta)
        grupos[k]['ordenes'].append({'id': o.id, 'codigo': _oc_codigo(o), 'proveedor': o.razon_social or '', 'dias': dias, 'fuera': fuera,
                                     'moneda': o.moneda, 'monto': round(o.total or 0, 2)})
    for o in activas:
        e_list = ents.get(o.id, [])
        if o.estado == 'BORRADOR':
            poner('borrador', o, o.fecha_registro)
            continue
        if o.estado == 'ENVIADA':
            poner('aprobar', o, o.fecha_envio or o.fecha_registro)
            continue
        if o.estado not in ('APROBADA', 'RECIBIDA', 'CONFORME'):
            continue
        # material que aún no llega (todo o el saldo de una entrega parcial)
        if o.estado in ('APROBADA', 'RECIBIDA'):
            llego = {}
            for e in e_list:
                for ei in items_ent.get(e.id, []):
                    llego[ei.item_id] = llego.get(ei.item_id, 0) + (ei.cantidad or 0)
            falta = any((it.cantidad or 0) - llego.get(it.id, 0) - (it.cantidad_cancelada or 0) > 1e-9 for it in o.items) if e_list else o.estado == 'APROBADA'
            if falta:
                esp = _oc_fecha_esperada(o)
                # con fecha prometida: fuera de meta si ya pasó esa fecha; sin fecha: si pasó la meta general del paso
                poner('proveedor', o, o.fecha_aprobacion, fuera=(hoy > esp) if esp else None)
        # entregas que llegaron y nadie dio la conformidad
        sin_conf = [e for e in e_list if not e.fecha_conforme]
        if sin_conf:
            poner('conformidad', o, min(e.fecha for e in sin_conf))
        # conformes que faltan ingresar al inventario (solo compras para un inventario; no tema contable)
        if o.tipo == 'OC' and o.destino in ('GENERAL', 'INSUMOS') and not o.es_contable and not o.fecha_kardex \
                and not (o.items and all(it.fecha_ingreso for it in o.items)):
            por_ing = [e for e in e_list if e.fecha_conforme and any(not ei.fecha_ingreso for ei in items_ent.get(e.id, []))]
            if por_ing:
                poner('ingreso', o, min(e.fecha_conforme for e in por_ing))
    salida = []
    for k, *_ in DETENIDAS_OC:
        g = grupos[k]
        g['ordenes'].sort(key=lambda x: -(x['dias'] or 0))
        g['n'] = len(g['ordenes'])
        g['n_fuera'] = sum(1 for x in g['ordenes'] if x['fuera'])
        g['max_dias'] = g['ordenes'][0]['dias'] if g['ordenes'] else None
        salida.append(g)
    return salida


def _oc_reporte(emp_sel='TODAS', desde=None, hasta=None, tipo='', cruz=None, con_igv=False):
    """Todo el tablero: gasto (soles y dólares por separado), comparación con el periodo anterior, atrasos, OTIF,
    tiempos de cada paso con su meta y órdenes detenidas ahora. cruz = {'prov': 'ACEROS SAC', ...} (filtro cruzado)."""
    hoy = hora_peru().date()
    cruz = {k: v for k, v in (cruz or {}).items() if k in FILTROS_CRUZADOS_OC and v}
    metas = _oc_metas_pasos()

    def pasa(o):
        if emp_sel != 'TODAS' and (o.empresa or 'ANCLAJES') != emp_sel:
            return False
        if tipo and o.tipo != tipo:
            return False
        return all((FILTROS_CRUZADOS_OC[k][1](o) or '(sin dato)') == v for k, v in cruz.items())
    todas = [o for o in OrdenCompra.query.all() if pasa(o)]
    en_periodo = lambda o, a, b: o.estado in ESTADOS_REPORTE_OC and o.fecha and (not a or o.fecha >= a) and (not b or o.fecha <= b)
    ordenes = sorted([o for o in todas if en_periodo(o, desde, hasta)], key=lambda o: (o.fecha, o.id))
    # contra qué se compara (▲▼): periodos de 6 a 12 meses (p. ej. "el año a la fecha") contra las MISMAS FECHAS del año anterior;
    # periodos cortos (un mes, un trimestre) contra el periodo inmediatamente anterior del mismo largo
    a_desde = a_hasta = None
    comp_txt = ''
    anteriores = []
    if desde and hasta:
        dias = (hasta - desde).days + 1
        if 180 <= dias <= 366:
            a_desde, a_hasta = _anio_antes(desde), _anio_antes(hasta)
            comp_txt = f'el mismo periodo de {a_desde.year}' if a_desde.year == a_hasta.year else 'el mismo periodo del año anterior'
        else:
            a_desde, a_hasta = desde - timedelta(days=dias), desde - timedelta(days=1)
            comp_txt = 'el periodo anterior'
        anteriores = [o for o in todas if en_periodo(o, a_desde, a_hasta)]
    activas = [o for o in todas if o.estado in ('BORRADOR', 'ENVIADA', 'APROBADA', 'RECIBIDA', 'CONFORME')]
    ents, items_ent = _oc_entregas_de({o.id: o for o in ordenes + anteriores + activas}.values())
    monto = lambda o: _oc_monto(o, con_igv)

    def acumular(clave_fn, lista=None):
        res = {}
        for o in (ordenes if lista is None else lista):
            k = clave_fn(o) or '(sin dato)'
            r = res.setdefault(k, {'clave': k, 'PEN': 0.0, 'USD': 0.0, 'n': 0})
            r[o.moneda if o.moneda in ('PEN', 'USD') else 'PEN'] += monto(o)
            r['n'] += 1
        lista_r = list(res.values())
        for r in lista_r:
            r['PEN'], r['USD'] = round(r['PEN'], 2), round(r['USD'], 2)
        return lista_r

    por_mes = sorted(acumular(lambda o: o.fecha.strftime('%Y-%m')), key=lambda r: r['clave'])
    # meses sin compras también aparecen (la tendencia no salta meses)
    if por_mes and por_mes[0]['clave'][:4].isdigit():
        y, m = int(por_mes[0]['clave'][:4]), int(por_mes[0]['clave'][5:7])
        fin = (int(por_mes[-1]['clave'][:4]), int(por_mes[-1]['clave'][5:7]))
        hay = {r['clave']: r for r in por_mes}
        completo = []
        while (y, m) <= fin:
            k = f'{y:04d}-{m:02d}'
            completo.append(hay.get(k, {'clave': k, 'PEN': 0.0, 'USD': 0.0, 'n': 0}))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        por_mes = completo
    for r in por_mes:
        if r['clave'][:4].isdigit():
            r['txt'] = f"{MESES_ES[int(r['clave'][5:7]) - 1]} {r['clave'][2:4]}"
    orden_gasto = lambda r: (-(r['PEN'] + r['USD'] * 3.75), r['clave'])     # solo para ordenar (no se suman monedas)
    por_prov = sorted(acumular(FILTROS_CRUZADOS_OC['prov'][1]), key=orden_gasto)
    por_area = sorted(acumular(FILTROS_CRUZADOS_OC['area'][1]), key=orden_gasto)
    por_motivo = sorted(acumular(FILTROS_CRUZADOS_OC['motivo'][1]), key=orden_gasto)
    por_cliente = sorted([r for r in acumular(FILTROS_CRUZADOS_OC['cliente'][1]) if r['clave'] != '(sin dato)'], key=orden_gasto)
    por_solic = sorted(acumular(FILTROS_CRUZADOS_OC['solic'][1]), key=orden_gasto)
    por_empresa = sorted(acumular(FILTROS_CRUZADOS_OC['empresa_c'][1]), key=orden_gasto)
    for r in por_empresa:
        info = next((i for i in EMPRESAS_OC.values() if i.get('corto') == r['clave']), {})
        r['color'] = info.get('acento') or info.get('color', '#64748b')

    def totales_de(lista):
        return {'PEN': round(sum(monto(o) for o in lista if o.moneda != 'USD'), 2), 'USD': round(sum(monto(o) for o in lista if o.moneda == 'USD'), 2),
                'n': len(lista), 'n_pen': sum(1 for o in lista if o.moneda != 'USD'), 'n_usd': sum(1 for o in lista if o.moneda == 'USD'),
                'importacion': sum(1 for o in lista if o.es_importacion)}
    totales = totales_de(ordenes)
    anterior = totales_de(anteriores) if a_desde else None
    otif = _oc_otif(ordenes, ents, items_ent, hoy)
    otif_ant = _oc_otif(anteriores, ents, items_ent, hoy) if a_desde else None
    comparacion = {}
    if anterior:
        comparacion = {m: _oc_variacion(totales[m], anterior[m]) for m in ('PEN', 'USD', 'n')}
        comparacion['otif'] = (otif['pct'] - otif_ant['pct']) if otif['pct'] is not None and otif_ant and otif_ant['pct'] is not None else None

    # ---- atrasos por proveedor (fecha prometida vs. PRIMERA llegada) ----
    prov = {}
    for o in ordenes:
        esp = _oc_fecha_esperada(o)
        if not esp:
            continue
        p = prov.setdefault(o.razon_social, {'clave': o.razon_social, 'con_fecha': 0, 'a_tiempo': 0, 'tarde': 0, 'pend_atrasadas': 0, 'en_plazo': 0,
                                             'dias': [], 'peor': None, 'PEN': 0.0, 'USD': 0.0})
        p['con_fecha'] += 1
        p[o.moneda if o.moneda in ('PEN', 'USD') else 'PEN'] += monto(o)
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
        else:
            p['en_plazo'] += 1
    atrasos = []
    for p in prov.values():
        p['juzgadas'] = p['a_tiempo'] + p['tarde'] + p['pend_atrasadas']           # las que aún están en plazo no se juzgan
        p['prom'] = round(sum(p['dias']) / len(p['dias']), 1) if p['dias'] else 0
        p['pct_tarde'] = round(100 * (p['tarde'] + p['pend_atrasadas']) / p['juzgadas']) if p['juzgadas'] else 0
        p['PEN'], p['USD'] = round(p['PEN'], 2), round(p['USD'], 2)
        p['ranking'] = p['juzgadas'] >= MIN_ORDENES_RANKING_OC
        del p['dias']
        atrasos.append(p)
    atrasos.sort(key=lambda p: (not p['ranking'], -p['pct_tarde'], -(p['tarde'] + p['pend_atrasadas']), -p['prom'], p['clave']))

    # ---- tiempos de cada paso ----
    t = {k: [] for k, *_ in PASOS_REPORTE_OC}
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
        for e in ents.get(o.id, []):
            t['llegada_conforme'].append(_dias_entre(e.fecha, e.fecha_conforme))
            for ei in items_ent.get(e.id, []):
                t['conforme_ingreso'].append(_dias_entre(e.fecha_conforme, ei.fecha_ingreso))
    tiempos = []
    for k, txt, ay, corto in PASOS_REPORTE_OC:
        x = {'clave': k, 'txt': txt, 'ayuda': ay, 'corto': corto, 'meta': metas.get(k), **_estad_dias(t[k])}
        x['fuera_meta'] = bool(x['mediana'] is not None and x['meta'] is not None and x['mediana'] > x['meta'])
        tiempos.append(x)
    detenidas = _oc_detenidas(activas, ents, items_ent, metas, hoy)
    unicas = {x['id'] for g in detenidas for x in g['ordenes']}
    unicas_fuera = {x['id'] for g in detenidas for x in g['ordenes'] if x['fuera']}
    rep = {'ordenes': ordenes, 'totales': totales, 'anterior': anterior, 'comparacion': comparacion, 'a_desde': a_desde, 'a_hasta': a_hasta,
           'comp_txt': comp_txt, 'n_detenidas': len(unicas), 'n_detenidas_fuera': len(unicas_fuera),
           'por_mes': por_mes, 'por_prov': por_prov, 'por_area': por_area, 'por_motivo': por_motivo, 'por_cliente': por_cliente,
           'por_solic': por_solic, 'por_empresa': por_empresa, 'atrasos': atrasos, 'tiempos': tiempos, 'detenidas': detenidas,
           'otif': otif, 'otif_ant': otif_ant, 'metas': metas, 'cruz': cruz, 'con_igv': con_igv,
           'min_ranking': MIN_ORDENES_RANKING_OC, 'alerta_pct': ATRASO_ALERTA_PCT_OC}
    rep['insights'] = _oc_insights(rep, emp_sel)
    return rep


def _oc_insights(rep, emp_sel):
    """Resumen en frases cortas y ACCIONABLES (con botón cuando hay algo que hacer)."""
    from markupsafe import Markup, escape
    T, C = rep['totales'], rep['comparacion']
    sufijo = 'con IGV' if rep['con_igv'] else 'sin IGV'
    salida = []
    for m, s in (('PEN', 'S/'), ('USD', 'US$')):
        if not T[m]:
            continue
        txt = Markup('Se compró <b>{} {:,.2f}</b> {} en {} orden(es)').format(s, T[m], sufijo, T['n_' + m.lower()])
        v = C.get(m)
        if v is not None:
            txt += Markup(' · <b>{} {:g}%</b> vs. {} ({} {:,.0f})').format('▲' if v > 0 else ('▼' if v < 0 else '='), abs(v), rep['comp_txt'], s, rep['anterior'][m])
        salida.append({'nivel': 'info', 'icono': 'bi-cash-stack', 'txt': txt})
    # concentración (Pareto) en la moneda principal
    m = 'PEN' if T['PEN'] else 'USD'
    provs = sorted([p for p in rep['por_prov'] if p[m] > 0], key=lambda p: -p[m])
    total = sum(p[m] for p in provs)
    if len(provs) >= 4 and total:
        acum, k = 0, 0
        for p in provs:
            acum += p[m]
            k += 1
            if acum >= 0.8 * total:
                break
        nombres = ', '.join(p['clave'] for p in provs[:min(k, 3)]) + (' y otros' if k > 3 else '')
        salida.append({'nivel': 'info', 'icono': 'bi-pie-chart', 'txt': Markup('<b>{} de {} proveedores</b> concentran el 80% del gasto en {}: {}.').format(
            k, len(provs), 'soles' if m == 'PEN' else 'dólares', nombres)})
    # OTIF
    o = rep['otif']
    if o['n']:
        nivel = 'ok' if o['pct'] >= 90 else ('alerta' if o['pct'] >= 70 else 'mal')
        salida.append({'nivel': nivel, 'icono': 'bi-bullseye', 'tab': 'operativa',
                       'txt': Markup('OTIF <b>{}%</b>: {} de {} órdenes llegaron <b>a tiempo y completas</b>{}.').format(
                           o['pct'], o['ok'], o['n'], Markup(' ({} tarde, {} incompletas, {} sin llegar)').format(o['tarde'], o['incompleto'], o['no_llego']) if o['ok'] < o['n'] else '')})
    # proveedor que más se atrasa (con datos suficientes)
    peor = next((p for p in rep['atrasos'] if p['ranking'] and p['pct_tarde'] > 0), None)
    if peor:
        salida.append({'nivel': 'mal' if peor['pct_tarde'] >= 50 else 'alerta', 'icono': 'bi-alarm', 'tab': 'operativa',
                       'txt': Markup('<b>{}</b> se atrasó en <b>{} de {}</b> órdenes (atraso promedio {} d).').format(
                           peor['clave'], peor['tarde'] + peor['pend_atrasadas'], peor['juzgadas'], peor['prom']),
                       'filtro': ('prov', peor['clave']), 'accion': 'Ver solo este proveedor'})
    # paso que más se pasa de su meta
    fuera = [x for x in rep['tiempos'] if x['fuera_meta'] and x['clave'] in PASOS_PROCESO_OC and x['meta']]
    if fuera:
        x = max(fuera, key=lambda x: x['mediana'] / x['meta'])
        salida.append({'nivel': 'alerta', 'icono': 'bi-stopwatch', 'tab': 'operativa',
                       'txt': Markup('El paso que más se pasa de su meta es <b>{}</b>: lo típico es <b>{} d</b> (meta {:g} d).').format(x['txt'], x['mediana'], x['meta'])})
    elif any(x['mediana'] is not None for x in rep['tiempos'] if x['clave'] in PASOS_PROCESO_OC):
        salida.append({'nivel': 'ok', 'icono': 'bi-stopwatch', 'tab': 'operativa', 'txt': Markup('Todos los pasos del proceso están <b>dentro de su meta</b> (caso típico).')})
    # órdenes detenidas que ya pasaron su meta (las 3 con más órdenes fuera de meta)
    dias_txt = lambda d: '—' if d is None else (f'{d:.0f}' if d >= 10 else f'{d:.1f}'.replace('.0', ''))
    for g in sorted([g for g in rep['detenidas'] if g['n_fuera']], key=lambda g: -g['n_fuera'])[:3]:
        url = url_for('oc_lista', vista=g['vista'], empresa=emp_sel) if g['vista'] else url_for('oc_ingresos_pendientes')
        salida.append({'nivel': 'mal' if g['n_fuera'] >= 3 else 'alerta', 'icono': 'bi-hourglass-split',
                       'txt': Markup('<b>{}</b> {} · <b>{} fuera de meta</b>, la más antigua hace {} d.').format(
                           '1 orden' if g['n'] == 1 else f"{g['n']} órdenes", FRASES_DETENIDAS_OC[g['clave']], g['n_fuera'], dias_txt(g['max_dias'])),
                       'url': url, 'accion': 'Aprobarlas' if g['clave'] == 'aprobar' else 'Verlas', 'detenida': g['clave']})
    return salida


@app.route('/ordenes/reportes')
@_ruta_oc()
def oc_reportes():
    hoy = hora_peru().date()
    emp_sel = (request.args.get('empresa') or session.get('oc_empresa') or 'TODAS').upper()
    emp_sel = emp_sel if emp_sel in EMPRESAS_OC or emp_sel == 'TODAS' else 'TODAS'
    desde = _fecha_param('desde', date(hoy.year, 1, 1))
    hasta = _fecha_param('hasta', hoy)
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde
    tipo = request.args.get('tipo', '') if request.args.get('tipo') in TIPOS_OC else ''
    con_igv = request.args.get('igv') == '1'
    cruz = {k: (request.args.get(k) or '').strip() for k in FILTROS_CRUZADOS_OC if (request.args.get(k) or '').strip()}
    rep = _oc_reporte(emp_sel, desde, hasta, tipo, cruz, con_igv)
    if request.args.get('exportar') == 'excel':
        return _oc_excel_reporte(rep, emp_sel, desde, hasta, tipo)
    base_q = {k: v for k, v in {'empresa': emp_sel, 'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'tipo': tipo,
                                'igv': '1' if con_igv else ''}.items() if v}

    def url_rep(**cambios):
        """URL del tablero con los mismos filtros, cambiando algunos (valor None = quitarlo)."""
        q = {**base_q, **rep['cruz']}
        for k, v in cambios.items():
            if v is None:
                q.pop(k, None)
            else:
                q[k] = v
        return url_for('oc_reportes', **q)
    return render_template('oc_reportes.html', rep=rep, emp_sel=emp_sel, desde=desde, hasta=hasta, tipo=tipo, tipos=TIPOS_OC,
                           empresas_oc=EMPRESAS_OC, seccion='reportes', hoy=hoy, con_igv=con_igv, cruz=rep['cruz'], url_rep=url_rep,
                           filtros_cruzados={k: v[0] for k, v in FILTROS_CRUZADOS_OC.items()}, pasos_proceso=PASOS_PROCESO_OC)


def _oc_excel_reporte(rep, emp_sel, desde, hasta, tipo):
    from openpyxl import Workbook
    wb = Workbook()
    cruz_txt = ''.join(f" · {FILTROS_CRUZADOS_OC[k][0]}: {v}" for k, v in rep['cruz'].items())
    nota = (f"{'Las dos empresas' if emp_sel == 'TODAS' else EMPRESAS_OC[emp_sel]['nombre']} · órdenes aprobadas del {desde.strftime('%d/%m/%Y')} "
            f"al {hasta.strftime('%d/%m/%Y')}{' · solo ' + tipo if tipo else ''}{cruz_txt} · montos {'CON' if rep['con_igv'] else 'SIN'} IGV · "
            f"soles y dólares por separado (no se suman)")
    m = '#,##0.00'
    _xlsx_hoja(wb, 'Gasto por mes', ['Mes', 'Soles (S/)', 'Dólares (US$)', 'Órdenes'],
               [[r.get('txt', r['clave']), r['PEN'], r['USD'], r['n']] for r in rep['por_mes']], formatos={1: m, 2: m}, primera=True, nota=nota)
    for titulo, clave, cab in (('Por proveedor', 'por_prov', 'Proveedor'), ('Por empresa', 'por_empresa', 'Empresa'), ('Por área', 'por_area', 'Área'),
                               ('Por motivo', 'por_motivo', 'Motivo'), ('Por cliente', 'por_cliente', 'Cliente'), ('Por solicitante', 'por_solic', 'Solicitó')):
        _xlsx_hoja(wb, titulo, [cab, 'Soles (S/)', 'Dólares (US$)', 'Órdenes'], [[r['clave'], r['PEN'], r['USD'], r['n']] for r in rep[clave]],
                   formatos={1: m, 2: m}, nota=nota)
    _xlsx_hoja(wb, 'Atrasos de proveedores', ['Proveedor', 'Órdenes con fecha', 'Juzgadas (fecha cumplida o vencida)', 'A tiempo', 'Llegaron tarde',
                                              'Atrasadas sin llegar', 'Aún en plazo', '% con atraso', 'Atraso promedio (días)', 'Peor caso', 'Días del peor caso',
                                              f'En el ranking (desde {MIN_ORDENES_RANKING_OC} juzgadas)'],
               [[p['clave'], p['con_fecha'], p['juzgadas'], p['a_tiempo'], p['tarde'], p['pend_atrasadas'], p['en_plazo'], p['pct_tarde'], p['prom'],
                 p['peor'][0] if p['peor'] else '', p['peor'][1] if p['peor'] else None, 'Sí' if p['ranking'] else 'Pocos datos'] for p in rep['atrasos']], nota=nota)
    o = rep['otif']
    _xlsx_hoja(wb, 'OTIF', ['Indicador', 'Órdenes'], [['Juzgadas (con fecha de entrega cumplida o vencida)', o['n']], ['A tiempo y completas (OTIF)', o['ok']],
                                                     ['Completas pero tarde', o['tarde']], ['Incompletas (falta o se cerró saldo)', o['incompleto']],
                                                     ['No llegó nada', o['no_llego']], ['OTIF %', o['pct']]], nota=nota)
    _xlsx_hoja(wb, 'Tiempos por paso', ['Paso', 'Qué mide', 'Casos', 'Promedio (días)', 'Mediana (días)', 'Meta (días)', '¿Dentro de la meta?', 'Mínimo', 'Máximo'],
               [[x['txt'], x['ayuda'], x['n'], x['prom'], x['mediana'], x['meta'], ('' if x['mediana'] is None or x['meta'] is None else ('No' if x['fuera_meta'] else 'Sí')),
                 x['min'], x['max']] for x in rep['tiempos']], nota=nota)
    _xlsx_hoja(wb, 'Órdenes detenidas ahora', ['Paso', 'Quién la tiene', 'Orden', 'Proveedor', 'Días esperando', 'Meta (días)', '¿Fuera de meta?'],
               [[g['txt'], g['quien'], x['codigo'], x['proveedor'], x['dias'], g['meta'], 'Sí' if x['fuera'] else ''] for g in rep['detenidas'] for x in g['ordenes']],
               nota=f"Situación al {hora_peru().strftime('%d/%m/%Y %H:%M')} (no depende del periodo)")
    _xlsx_hoja(wb, 'Órdenes del periodo', ['Empresa', 'Orden', 'Fecha', 'Proveedor', 'Área', 'Motivo', 'Cliente', 'Moneda', 'Subtotal (sin IGV)', 'Total (con IGV)', 'Estado'],
               [[EMPRESAS_OC.get(o.empresa or 'ANCLAJES', {}).get('corto', ''), _oc_codigo(o), o.fecha, o.razon_social, (o.area_solicitante or '').title(),
                 (o.motivo_compra or '').capitalize(), o.cliente_razon or '', o.moneda, _oc_monto(o, False), o.total or 0, ESTADOS_OC[o.estado]['txt']]
                for o in rep['ordenes']], formatos={2: 'dd/mm/yyyy', 8: m, 9: m}, nota=nota)
    registrar_log("Exportó los reportes de compras a Excel", 'bi-file-earmark-excel', 'text-success')
    return _xlsx_respuesta(wb, f"reporte_compras_{desde.isoformat()}_{hasta.isoformat()}.xlsx")
