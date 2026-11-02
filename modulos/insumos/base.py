# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# INSUMOS INTERNOS · base
# empresas, permisos, tablas, catálogos, stock por moneda (soles/dólares) y funciones comunes
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# =====================================================================================
# INSUMOS INTERNOS (material de uso interno de la empresa)
# - Maestro único de insumos; stock, costo y ubicación SEPARADOS por empresa (Anclajes / Import Bolts).
# - Ingresos con factura (proveedor por RUC, igual que el Kardex) y documentos (PDF/foto) en S3.
# - Salidas con el formato "SALIDA DE MATERIALES DE ALMACÉN" (PDF con el logo de cada empresa,
#   correlativo propio por empresa, firma en pantalla o documento firmado subido).
# - Costo: POR LOTES, en orden de llegada (PEPS), con IGV. Cada compra es un LOTE con su precio real
#   (en S/ o en US$, sin convertir). Cada salida saca primero del lote más antiguo y se carga al área con
#   el precio de ese lote (si saca de dos lotes, cada parte a su precio): el gasto es el real, no un promedio.
#   InsumoStock guarda los totales (se recalculan desde los lotes); su "costo promedio" es solo de referencia.
# - PRECIO PENDIENTE (sin factura / inventario de cosas antiguas): el lote entra SIN PRECIO. Sale en su turno
#   (orden de llegada) a costo 0 marcado "sin precio"; cuando se le pone el precio (en el ingreso, en la ficha
#   de precios o con la factura de una reposición) TODAS sus salidas se recalculan con ese precio.
# Las tablas se crean solas al arrancar (no hace falta ninguna ruta /fix_).
# =====================================================================================
from functools import wraps as _wraps_insumos

EMPRESAS_INSUMOS = {
    'ANCLAJES': {'nombre': 'Anclajes y Pernos SAC', 'corto': 'Anclajes', 'logo': 'logo.png', 'color': '#0B3D91'},
    'IMPORTBOLTS': {'nombre': 'Import Bolts SAC', 'corto': 'Import Bolts', 'logo': 'logo_import.png', 'color': '#004b87'},
}
ROLES_INSUMOS_EDITAN = ['admin', 'almacen', 'logistica']
ROLES_INSUMOS_VEN = ['admin', 'almacen', 'logistica', 'administracion']
CATALOGOS_INSUMOS = {'INSUMO_CATEGORIA': 'Categorías', 'INSUMO_UNIDAD': 'Unidades de medida',
                     'INSUMO_MOTIVO': 'Necesario para (motivos)', 'INSUMO_ALMACEN': 'Almacenes / ubicaciones'}
_INSUMOS_INICIALES = {
    'INSUMO_CATEGORIA': ['EPP / SEGURIDAD', 'LIMPIEZA', 'OFICINA', 'HERRAMIENTAS', 'REPUESTOS', 'LUBRICANTES', 'SOLDADURA', 'ELÉCTRICOS'],
    'INSUMO_UNIDAD': ['UND', 'PAR', 'CAJA', 'PAQUETE', 'KG', 'LT', 'GLN', 'MT', 'ROLLO'],
    'INSUMO_MOTIVO': ['PRODUCCIÓN', 'MANTENIMIENTO DE MÁQUINAS', 'MEJORA DE INFRAESTRUCTURA', 'LIMPIEZA',
                      'SEGURIDAD (EPP)', 'OFICINA / ADMINISTRATIVO'],
    'INSUMO_ALMACEN': ['ALMACÉN PRINCIPAL'],
}
_AREAS_INICIALES = ['PRODUCCIÓN', 'ALMACÉN', 'MANTENIMIENTO', 'ADMINISTRACIÓN', 'VENTAS', 'LOGÍSTICA']
FORMATO_SALIDA_DEF = {'codigo': 'LAL-FO-0001', 'version': '01'}
_insumos_ok = False


def _agregar_columnas_si_faltan(tabla, columnas):
    """ALTER TABLE ... ADD COLUMN para las columnas nuevas que todavía no existen (sin rutas /fix_)."""
    from sqlalchemy import inspect as sa_inspect
    existentes = {c['name'] for c in sa_inspect(db.engine).get_columns(tabla)}
    faltan = [(n, t) for n, t in columnas if n not in existentes]
    if not faltan:
        return
    es_pg = db.engine.dialect.name == 'postgresql'
    with db.engine.begin() as conn:
        if es_pg:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        for nombre, tipo in faltan:
            if not es_pg:
                tipo = tipo.replace('DEFAULT FALSE', 'DEFAULT 0').replace('TIMESTAMP', 'DATETIME')
            conn.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {"IF NOT EXISTS " if es_pg else ""}{nombre} {tipo}'))


def _sembrar_catalogos_insumos():
    """Pone los valores iniciales en los catálogos del módulo que estén vacíos."""
    for tipo, valores in _INSUMOS_INICIALES.items():
        if not CatalogoValor.query.filter_by(tipo=tipo).first():
            for v in valores:
                db.session.add(CatalogoValor(tipo=tipo, valor=v, activo=True, es_predeterminado=False))


def _asegurar_insumos():
    """Crea las tablas del módulo si faltan (y columnas nuevas) y siembra UNA vez los catálogos iniciales."""
    global _insumos_ok
    if _insumos_ok:
        return
    for modelo in (InsumoArea, InsumoTrabajador, Insumo, InsumoStock, InsumoProveedor, InsumoIngreso, InsumoIngresoDetalle,
                   InsumoSalida, InsumoSalidaDetalle, InsumoMovimiento, InsumoDocumento, InsumoLote, InsumoSalidaLote):
        modelo.__table__.create(bind=db.engine, checkfirst=True)
    # compras en dólares: se llevan aparte, sin convertir (stock y costo en US$, gasto en US$)
    _agregar_columnas_si_faltan('insumo_stock', [('stock_usd', 'FLOAT DEFAULT 0'), ('costo_usd', 'FLOAT DEFAULT 0'), ('bolsa_antigua', "VARCHAR(3) DEFAULT 'PEN'")])
    _agregar_columnas_si_faltan('insumo_ingreso', [('moneda', "VARCHAR(3) DEFAULT 'PEN'")])
    _agregar_columnas_si_faltan('insumo_movimiento', [('moneda', "VARCHAR(3) DEFAULT 'PEN'"), ('stock_moneda_despues', 'FLOAT')])
    _agregar_columnas_si_faltan('insumo_salida', [('total_costo_usd', 'FLOAT DEFAULT 0')])
    _agregar_columnas_si_faltan('insumo_salida_detalle', [('cantidad_usd', 'FLOAT DEFAULT 0'), ('costo_unitario_usd', 'FLOAT DEFAULT 0'),
                                                          ('costo_total_usd', 'FLOAT DEFAULT 0')])
    # precio pendiente (unidades "sin precio") y la OC de la que vino el ingreso
    _agregar_columnas_si_faltan('insumo_stock', [('stock_sin_costo', 'FLOAT DEFAULT 0')])
    _agregar_columnas_si_faltan('insumo_ingreso', [('orden_compra_id', 'INTEGER')])
    _agregar_columnas_si_faltan('insumo_ingreso_detalle', [('precio_pendiente', 'BOOLEAN DEFAULT FALSE'), ('sin_costo_restante', 'FLOAT DEFAULT 0'),
                                                           ('cantidad_valorizada', 'FLOAT'), ('precio_completado_por', 'VARCHAR(100)'),
                                                           ('fecha_precio', 'TIMESTAMP')])
    _agregar_columnas_si_faltan('insumo_salida_detalle', [('cantidad_sin_costo', 'FLOAT DEFAULT 0'), ('origen_sin_costo', 'VARCHAR(500)')])
    _agregar_columnas_si_faltan('insumo_movimiento', [('lote_id', 'INTEGER')])
    from sqlalchemy import inspect as sa_inspect
    if 'insumo_proveedor_id' not in {c['name'] for c in sa_inspect(db.engine).get_columns('insumo_ingreso')}:
        es_pg = db.engine.dialect.name == 'postgresql'
        with db.engine.begin() as conn:
            if es_pg:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text(f'ALTER TABLE insumo_ingreso ADD COLUMN {"IF NOT EXISTS " if es_pg else ""}insumo_proveedor_id INTEGER'
                              f'{" REFERENCES insumo_proveedor(id)" if es_pg else ""}'))
    if not SystemConfig.query.get('insumos_sembrado'):
        try:
            _sembrar_catalogos_insumos()
            if not InsumoArea.query.first():
                for a in _AREAS_INICIALES:
                    db.session.add(InsumoArea(nombre=a, activo=True))
            db.session.add(SystemConfig(key='insumos_sembrado', value='1', updated_by='Sistema'))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    _migrar_a_lotes()
    _insumos_ok = True




def _ruta_insumos(editar=False, como_json=False, solo_admin=False):
    """Permisos del módulo: Gerencia y Almacén registran; Administración solo consulta."""
    def deco(f):
        @_wraps_insumos(f)
        def envoltura(*args, **kwargs):
            rol = session.get('role')
            permitidos = ['admin'] if solo_admin else (ROLES_INSUMOS_EDITAN if editar else ROLES_INSUMOS_VEN)
            if rol not in permitidos:
                if como_json:
                    return {'status': 'error', 'msg': 'No autorizado'}, 403
                return "Acceso denegado", 403
            _asegurar_insumos()
            return f(*args, **kwargs)
        return envoltura
    return deco


def _num(valor):
    """'12,5' -> 12.5 ; '' o inválido -> None."""
    try:
        v = float(str(valor).replace(',', '.').strip())
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _cant_txt(v):
    """12.0 -> '12' ; 2.5 -> '2.5' ; 1.125 -> '1.125'."""
    if v is None:
        return '-'
    v = round(float(v), 3)
    return f'{int(v):,}' if v == int(v) else f'{v:,.3f}'.rstrip('0').rstrip('.')


app.add_template_filter(_cant_txt, 'cant')
app.add_template_filter(lambda v: f'S/ {float(v or 0):,.2f}', 'soles')


def _empresa_param(nombre='empresa', defecto=None):
    e = (request.values.get(nombre) or defecto or session.get('insumos_empresa') or 'ANCLAJES').upper()
    return e if e in EMPRESAS_INSUMOS else 'ANCLAJES'


def _catalogo_insumos(tipo, incluir_inactivos=False):
    q = CatalogoValor.query.filter_by(tipo=tipo)
    if not incluir_inactivos:
        q = q.filter_by(activo=True)
    return sorted(q.all(), key=lambda v: _clave_alfabetica(v.valor))


def _categorias_insumos():
    """Nombres de categoría para los filtros: las del catálogo + las que ya usan los insumos."""
    nombres = {v.valor for v in _catalogo_insumos('INSUMO_CATEGORIA')}
    nombres |= {c for (c,) in db.session.query(Insumo.categoria).distinct().all() if c}
    return sorted(nombres, key=_clave_alfabetica)


def _stock_de(insumo_id, empresa, crear=True):
    st = InsumoStock.query.filter_by(insumo_id=insumo_id, empresa=empresa).first()
    if not st and crear:
        st = InsumoStock(insumo_id=insumo_id, empresa=empresa, stock_actual=0, stock_minimo=0, costo_promedio=0)
        db.session.add(st)
        db.session.flush()
    return st


MONEDAS_INSUMOS = {'PEN': 'S/', 'USD': 'US$'}


def _montos_txt(pen, usd):
    """'S/ 120.00' · 'US$ 35.00' · 'S/ 120.00 + US$ 35.00' (soles y dólares por separado; nunca se suman)."""
    partes = []
    if (pen or 0) or not (usd or 0):
        partes.append(f"S/ {float(pen or 0):,.2f}")
    if usd or 0:
        partes.append(f"US$ {float(usd):,.2f}")
    return ' + '.join(partes)


app.add_template_global(_montos_txt, 'montos_txt')


def _bolsa(st, moneda):
    """(unidades, costo unitario de referencia) de cada parte del stock, según los TOTALES de InsumoStock (que se recalculan
    desde los lotes). 'PEN' = con precio en soles, 'USD' = con precio en dólares, 'SC' = SIN PRECIO (precio pendiente).
    El costo es el PROMEDIO de los lotes que quedan: solo de referencia; las salidas usan el precio real de cada lote."""
    if not st:
        return 0.0, 0.0
    usd = float(st.stock_usd or 0)
    sc = float(st.stock_sin_costo or 0)
    if moneda == 'USD':
        return usd, float(st.costo_usd or 0)
    if moneda == 'SC':
        return sc, 0.0
    return float(st.stock_actual or 0) - usd - sc, float(st.costo_promedio or 0)


# ---------------------------- LOTES (PEPS: primero en llegar, primero en salir) ----------------------------
def _lotes_activos(insumo_id, empresa, con_saldo=True):
    """Lotes vigentes de un insumo en una empresa, en el ORDEN EN QUE SALEN (el más antiguo primero)."""
    q = InsumoLote.query.filter(InsumoLote.insumo_id == insumo_id, InsumoLote.empresa == empresa, InsumoLote.estado == 'ACTIVO')
    if con_saldo:
        q = q.filter(InsumoLote.cantidad_restante > 1e-9)
    return q.order_by(InsumoLote.fecha, InsumoLote.id).all()


def _resumen_lotes(lotes):
    """Totales de una lista de lotes: unidades y valor con precio en S/ y en US$, y unidades sin precio."""
    r = {'q_pen': 0.0, 'v_pen': 0.0, 'q_usd': 0.0, 'v_usd': 0.0, 'q_sc': 0.0}
    for l in lotes:
        q = float(l.cantidad_restante or 0)
        if q <= 1e-9:
            continue
        if l.costo_unitario is None:
            r['q_sc'] += q
        elif l.moneda == 'USD':
            r['q_usd'] += q
            r['v_usd'] += q * l.costo_unitario
        else:
            r['q_pen'] += q
            r['v_pen'] += q * l.costo_unitario
    return r


def _sincronizar_stock(st, lotes=None):
    """Recalcula los totales de InsumoStock desde sus lotes: stock, unidades en dólares, sin precio y el precio promedio
    de lo que queda (solo de referencia: así el VALOR del inventario es exactamente la suma de los lotes)."""
    if lotes is None:
        db.session.flush()
        lotes = _lotes_activos(st.insumo_id, st.empresa)
    r = _resumen_lotes(lotes)
    st.stock_actual = round(r['q_pen'] + r['q_usd'] + r['q_sc'], 6)
    st.stock_usd = round(r['q_usd'], 6)
    st.stock_sin_costo = round(r['q_sc'], 6)
    st.costo_promedio = round(r['v_pen'] / r['q_pen'], 6) if r['q_pen'] > 1e-9 else 0.0
    st.costo_usd = round(r['v_usd'] / r['q_usd'], 6) if r['q_usd'] > 1e-9 else 0.0
    primero = next((l for l in lotes if (l.cantidad_restante or 0) > 1e-9 and l.costo_unitario is not None), None)
    st.bolsa_antigua = 'USD' if primero and primero.moneda == 'USD' else 'PEN'
    return r


def _nuevo_lote(st, cantidad, precio, moneda, fecha, origen='COMPRA', ingreso=None, detalle=None, proveedor=None, documento=None):
    """Crea el lote de una entrada (con su precio real, o None si el precio está pendiente). Devuelve (lote, stock_antes)."""
    antes = float(st.stock_actual or 0)
    lote = InsumoLote(empresa=st.empresa, insumo_id=st.insumo_id, fecha=fecha, moneda='USD' if moneda == 'USD' else 'PEN',
                      costo_unitario=None if precio is None else round(precio, 6), cantidad_inicial=round(cantidad, 6),
                      cantidad_restante=round(cantidad, 6), origen=origen, ingreso_id=ingreso.id if ingreso else None,
                      ingreso_detalle_id=detalle.id if detalle else None, proveedor=(proveedor or '')[:200] or None,
                      documento=(documento or '')[:120] or None, estado='ACTIVO', creado_en=hora_peru())
    db.session.add(lote)
    db.session.flush()
    _sincronizar_stock(st)
    return lote, antes


def _sacar_de_lotes(st, cantidad):
    """PEPS: saca 'cantidad' de los lotes en orden de llegada (primero el más antiguo), cada parte a SU precio.
    Devuelve (stock_antes, [(lote, cantidad, costo_unitario o None, moneda)]). Lanza ValueError si no alcanza."""
    antes = float(st.stock_actual or 0)
    partes, falta = [], round(cantidad, 6)
    for l in _lotes_activos(st.insumo_id, st.empresa):
        if falta <= 1e-9:
            break
        toma = round(min(float(l.cantidad_restante or 0), falta), 6)
        if toma <= 1e-9:
            continue
        l.cantidad_restante = round(float(l.cantidad_restante) - toma, 6)
        partes.append((l, toma, l.costo_unitario, l.moneda or 'PEN'))
        falta = round(falta - toma, 6)
    if falta > 1e-6:
        raise ValueError(f'No alcanza el stock (faltan {_cant_txt(falta)}).')
    _sincronizar_stock(st)
    return antes, partes


def _totales_partes(partes):
    """De [(lote, cantidad, costo|None, moneda)] -> cantidades y montos en S/, en US$ y sin precio (nunca se suman monedas)."""
    t = {'q_pen': 0.0, 't_pen': 0.0, 'q_usd': 0.0, 't_usd': 0.0, 'q_sc': 0.0}
    for _l, c, u, m in partes:
        if u is None:
            t['q_sc'] += c
        elif m == 'USD':
            t['q_usd'] += c
            t['t_usd'] += c * u
        else:
            t['q_pen'] += c
            t['t_pen'] += c * u
    t['u_pen'] = round(t['t_pen'] / t['q_pen'], 6) if t['q_pen'] > 1e-9 else 0.0
    t['u_usd'] = round(t['t_usd'] / t['q_usd'], 6) if t['q_usd'] > 1e-9 else 0.0
    for k in ('t_pen', 't_usd'):
        t[k] = round(t[k], 2)
    return t


def _aplicar_totales_detalle(d, t):
    """Pone en el detalle de la salida lo que costó (S/, US$) y cuánto salió sin precio."""
    d.costo_unitario, d.costo_total = t['u_pen'], t['t_pen']
    d.cantidad_usd, d.costo_unitario_usd, d.costo_total_usd = round(t['q_usd'], 6), t['u_usd'], t['t_usd']
    d.cantidad_sin_costo = round(t['q_sc'], 6)


def _recalcular_salida(sal):
    """Vuelve a calcular el costo de una salida desde los lotes de los que salió (p. ej. cuando se completa un precio)."""
    filas = InsumoSalidaLote.query.filter_by(salida_id=sal.id).all()
    por_det = {}
    for f in filas:
        por_det.setdefault(f.salida_detalle_id, []).append((f.lote, f.cantidad, f.costo_unitario, f.moneda or 'PEN'))
    for d in sal.detalles:
        if d.id in por_det:
            _aplicar_totales_detalle(d, _totales_partes(por_det[d.id]))
    sal.total_costo = round(sum(d.costo_total or 0 for d in sal.detalles), 2)
    sal.total_costo_usd = round(sum(d.costo_total_usd or 0 for d in sal.detalles), 2)


def _datos_mov_lote(lote, moneda=None):
    """Campos del Kardex de un movimiento de un lote: moneda ('SC' si no tiene precio), precio del lote y lo que queda en él."""
    sin_precio = lote.costo_unitario is None
    return {'moneda': 'SC' if sin_precio else (moneda or lote.moneda or 'PEN'), 'lote_id': lote.id,
            'costo_prom_despues': 0.0 if sin_precio else lote.costo_unitario, 'stock_moneda_despues': round(float(lote.cantidad_restante or 0), 6)}


def _poner_precio_lote(lote, precio, ahora, moneda=None, motivo='', concepto='VALORIZACION'):
    """Pone (o corrige) el precio de un lote. TODO lo que ya salió de ese lote se recalcula con este precio (las salidas y el
    gasto por área quedan con el precio real). Queda en el Kardex (PRECIO COMPLETADO / AJUSTE DE COSTO) con quién y cuándo.
    Devuelve (unidades que ya habían salido, salidas recalculadas)."""
    anterior = lote.costo_unitario
    if moneda in ('PEN', 'USD') and not lote.ingreso_id:     # un saldo inicial / carga Excel puede tomar la moneda de la factura
        lote.moneda = moneda
    mon = lote.moneda or 'PEN'
    lote.costo_unitario = round(precio, 6)
    lote.precio_por = (session.get('nombre', '') or '')[:100] or None
    lote.fecha_precio = ahora
    # lo que ya salió de este lote: salidas (y sus movimientos del Kardex) con el precio real
    salidas, consumido = set(), 0.0
    for f in InsumoSalidaLote.query.filter_by(lote_id=lote.id).all():
        f.costo_unitario, f.moneda = lote.costo_unitario, mon
        salidas.add(f.salida_id)
    for m in InsumoMovimiento.query.filter(InsumoMovimiento.lote_id == lote.id,
                                           InsumoMovimiento.concepto.in_(['COMPRA', 'CONSUMO', 'IMPORTACION', 'ANULACION'])).all():
        m.costo_unitario, m.costo_total, m.moneda = lote.costo_unitario, round((m.cantidad or 0) * lote.costo_unitario, 2), mon
        m.costo_prom_despues = lote.costo_unitario
        if m.tipo == 'SALIDA' and m.concepto in ('CONSUMO', 'IMPORTACION'):
            consumido += m.cantidad or 0
    for sid in salidas:
        sal = InsumoSalida.query.get(sid)
        if sal:
            _recalcular_salida(sal)
    # el ítem del ingreso (si viene de una compra)
    if lote.ingreso_detalle_id:
        det = InsumoIngresoDetalle.query.get(lote.ingreso_detalle_id)
        if det:
            det.precio_unitario, det.precio_total = lote.costo_unitario, round(det.cantidad * lote.costo_unitario, 2)
            det.precio_pendiente, det.sin_costo_restante = False, 0.0
            det.cantidad_valorizada = round(float(lote.cantidad_restante or 0), 6)
            det.precio_completado_por, det.fecha_precio = lote.precio_por, ahora
            det.ingreso.total = round(sum(x.precio_total or 0 for x in det.ingreso.detalles), 2)
    st = _stock_de(lote.insumo_id, lote.empresa)
    _sincronizar_stock(st)
    sim = MONEDAS_INSUMOS.get(mon, 'S/')
    total = float(st.stock_actual or 0)
    txt_ant = f'{sim} {anterior:,.4f}' if anterior is not None else 'sin precio'
    db.session.add(InsumoMovimiento(
        empresa=lote.empresa, insumo_id=lote.insumo_id, fecha=ahora, tipo='AJUSTE', concepto=concepto,
        cantidad=round(float(lote.cantidad_inicial or 0), 6), costo_unitario=lote.costo_unitario,
        costo_total=round(float(lote.cantidad_restante or 0) * lote.costo_unitario, 2), stock_antes=total, stock_despues=total,
        moneda=mon, lote_id=lote.id, costo_prom_despues=lote.costo_unitario, stock_moneda_despues=round(float(lote.cantidad_restante or 0), 6),
        referencia=f'Lote #{lote.id}: {txt_ant} → {sim} {lote.costo_unitario:,.4f}'[:120], ingreso_id=lote.ingreso_id,
        observacion=((motivo + ' · ') if motivo else '') + (f'{len(salidas)} salida(s) recalculadas con este precio' if salidas else 'sin salidas previas'),
        user_id=session.get('user_id'), fecha_registro=ahora))
    return consumido, len(salidas)


def _lotes_sin_precio(insumo_id, empresa, moneda=None, excluir_ingreso=None):
    """Lotes vigentes con PRECIO PENDIENTE (aunque ya se hayan vaciado: al ponerles precio se corrigen sus salidas)."""
    q = InsumoLote.query.filter(InsumoLote.insumo_id == insumo_id, InsumoLote.empresa == empresa, InsumoLote.estado == 'ACTIVO',
                                InsumoLote.costo_unitario.is_(None))
    if excluir_ingreso:
        q = q.filter(db.or_(InsumoLote.ingreso_id.is_(None), InsumoLote.ingreso_id != excluir_ingreso))
    lotes = q.order_by(InsumoLote.fecha, InsumoLote.id).all()
    # los de un ingreso tienen la moneda de su factura; los de saldo inicial / Excel aceptan cualquiera
    return [l for l in lotes if not moneda or not l.ingreso_id or (l.moneda or 'PEN') == moneda]


def _migrar_a_lotes():
    """UNA vez: el stock que había (a costo promedio) se convierte en lotes para empezar a trabajar por PEPS.
    - lo comprado en soles  -> un lote "saldo anterior" a su costo promedio (si era 0, queda SIN PRECIO para completarlo),
    - lo comprado en dólares -> otro lote en US$,
    - lo que estaba con precio pendiente -> un lote por cada ingreso pendiente (y el resto, sin precio).
    El stock total no cambia. Queda marcado en SystemConfig('insumos_lotes')."""
    if SystemConfig.query.get('insumos_lotes'):
        return
    es_pg = db.engine.dialect.name == 'postgresql'
    try:
        if es_pg:     # varios procesos arrancando a la vez: solo uno migra
            db.session.execute(text('SELECT pg_advisory_xact_lock(724501)'))
            if SystemConfig.query.get('insumos_lotes'):
                db.session.rollback()
                return
        creados = 0
        for st in InsumoStock.query.all():
            total = float(st.stock_actual or 0)
            if total <= 1e-9 or InsumoLote.query.filter_by(insumo_id=st.insumo_id, empresa=st.empresa).first():
                continue
            primera = db.session.query(func.min(InsumoMovimiento.fecha)).filter(
                InsumoMovimiento.insumo_id == st.insumo_id, InsumoMovimiento.empresa == st.empresa).scalar() or st.ultimo_ingreso or hora_peru()
            usd, sc = float(st.stock_usd or 0), float(st.stock_sin_costo or 0)
            pen = round(total - usd - sc, 6)
            lotes = []
            orden = ['USD', 'PEN'] if st.bolsa_antigua == 'USD' else ['PEN', 'USD']
            for m in orden:
                q = usd if m == 'USD' else pen
                costo = float(st.costo_usd or 0) if m == 'USD' else float(st.costo_promedio or 0)
                if q > 1e-9:
                    lotes.append((q, costo if costo > 0 else None, m, primera, None, None, 'Saldo anterior (costo promedio)'))
            if sc > 1e-9:
                resto = sc
                pend = (InsumoIngresoDetalle.query.join(InsumoIngreso, InsumoIngreso.id == InsumoIngresoDetalle.ingreso_id)
                        .filter(InsumoIngreso.empresa == st.empresa, InsumoIngreso.estado == 'REGISTRADO',
                                InsumoIngresoDetalle.insumo_id == st.insumo_id, InsumoIngresoDetalle.precio_pendiente.is_(True))
                        .order_by(InsumoIngreso.fecha, InsumoIngreso.id).all())
                for d in pend:
                    q = min(float(d.sin_costo_restante or 0), resto)
                    if q > 1e-9:
                        lotes.append((q, None, d.ingreso.moneda or 'PEN', d.ingreso.fecha, d.ingreso, d, None))
                        resto -= q
                if resto > 1e-9:
                    lotes.append((resto, None, 'PEN', primera, None, None, 'Saldo anterior sin precio'))
            for q, costo, m, fecha, ing, det, doc in lotes:
                l = InsumoLote(empresa=st.empresa, insumo_id=st.insumo_id, fecha=fecha, moneda=m, costo_unitario=costo,
                               cantidad_inicial=round(det.cantidad if det else q, 6), cantidad_restante=round(q, 6),
                               origen='COMPRA' if ing else 'INICIAL', ingreso_id=ing.id if ing else None,
                               ingreso_detalle_id=det.id if det else None, proveedor=ing.razon_social if ing else None,
                               documento=(f'Factura {ing.numero_factura}' if ing and ing.numero_factura else (f'Ingreso #{ing.id}' if ing else doc)),
                               estado='ACTIVO', creado_en=hora_peru())
                db.session.add(l)
                creados += 1
            db.session.flush()
            _sincronizar_stock(st)
        db.session.add(SystemConfig(key='insumos_lotes', value='1', updated_by='Sistema'))
        db.session.commit()
        if creados:
            print(f"Insumos: stock pasado a lotes (PEPS): {creados} lote(s) creados")
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudo pasar el stock de insumos a lotes")


def _subir_doc_insumo(carpeta, archivo, info, tipo, claves, ingreso_id=None, salida_id=None):
    ext, mime, tamano = info
    s3_key = f"insumos/{carpeta}/{tipo.lower()}_{uuid.uuid4().hex}.{ext}"
    archivo.stream.seek(0)
    s3_client.upload_fileobj(archivo.stream, S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': mime})
    claves.append(s3_key)
    db.session.add(InsumoDocumento(ingreso_id=ingreso_id, salida_id=salida_id, tipo=tipo, s3_key=s3_key,
                                   nombre_original=secure_filename(archivo.filename)[:200] or f'documento.{ext}',
                                   content_type=mime, tamano_bytes=tamano, subido_por=session.get('nombre', ''),
                                   fecha=hora_peru()))


def _fecha_movimiento_insumo(texto):
    """Fecha del ingreso/salida: puede ser anterior (nunca futura). Se le pone la hora actual."""
    ahora = hora_peru()
    if not (texto or '').strip():
        return ahora, None
    try:
        dia = datetime.strptime(texto.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None, 'La fecha no es válida.'
    if dia > ahora.date():
        return None, 'La fecha no puede ser futura.'
    return datetime.combine(dia, ahora.time()), None


def _datos_formulario_insumos(empresa):
    """Insumos activos con el stock de la empresa (para los selectores con buscador) y sus lotes en orden de salida."""
    stocks = {s.insumo_id: s for s in InsumoStock.query.filter_by(empresa=empresa).all()}
    lotes = {}
    for l in (InsumoLote.query.filter(InsumoLote.empresa == empresa, InsumoLote.estado == 'ACTIVO', InsumoLote.cantidad_restante > 1e-9)
              .order_by(InsumoLote.fecha, InsumoLote.id).all()):
        lotes.setdefault(l.insumo_id, []).append([round(l.cantidad_restante, 3), l.costo_unitario, l.moneda or 'PEN'])
    lista = []
    for i in Insumo.query.filter_by(activo=True).order_by(Insumo.codigo).all():
        s = stocks.get(i.id)
        lista.append({'id': i.id, 'codigo': i.codigo, 'descripcion': i.descripcion, 'unidad': i.unidad or '',
                      'categoria': i.categoria or '', 'stock': round(float(s.stock_actual or 0), 3) if s else 0,
                      'costo': round(float(s.costo_promedio or 0), 4) if s else 0, 'almacen': (s.almacen or '') if s else '',
                      'minimo': round(float(s.stock_minimo or 0), 3) if s else 0,
                      'stock_usd': round(float(s.stock_usd or 0), 3) if s else 0, 'costo_usd': round(float(s.costo_usd or 0), 4) if s else 0,
                      'stock_sc': round(float(s.stock_sin_costo or 0), 3) if s else 0, 'lotes': lotes.get(i.id, []),
                      'primero': (s.bolsa_antigua if s and s.bolsa_antigua in ('PEN', 'USD') else 'PEN')})
    return lista


# Al arrancar (al final del archivo: _asegurar_insumos usa funciones de lotes definidas más arriba)
try:
    with app.app_context():
        _asegurar_insumos()
except Exception as _e_insumos:
    print(f"Aviso: no se pudo preparar el módulo de Insumos al arrancar: {_e_insumos}")
