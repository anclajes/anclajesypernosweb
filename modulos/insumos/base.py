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
# - Costo: PROMEDIO PONDERADO con IGV. Cada ingreso recalcula el costo promedio del stock:
#       nuevo_promedio = (stock * promedio + cantidad * precio) / (stock + cantidad)
#   y cada salida se valoriza a ese promedio -> así se sabe cuánto gasta cada área aunque la
#   factura sea por 100 unidades y se saquen de a pocas y para áreas distintas.
# - PRECIO PENDIENTE (sin factura / inventario de cosas antiguas): esas unidades entran al stock en una
#   parte aparte, "sin precio" (stock_sin_costo). NO cambian el costo promedio ni suman al gasto. Al sacar,
#   sale primero lo que sí tiene precio; lo "sin precio" sale al final (costo 0, marcado). Cuando llega la
#   factura se completa el precio (en el ingreso o con la factura de una reposición) y recién ahí esas
#   unidades pasan al costo promedio.
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
                   InsumoSalida, InsumoSalidaDetalle, InsumoMovimiento, InsumoDocumento):
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
    _insumos_ok = True


try:
    with app.app_context():
        _asegurar_insumos()
except Exception as _e_insumos:
    print(f"Aviso: no se pudo preparar el módulo de Insumos al arrancar: {_e_insumos}")


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
    """(unidades, costo unitario) de cada parte del stock. Lo comprado en soles y en dólares se lleva por separado
    (sin convertir): cada parte tiene su propio costo promedio. 'SC' = unidades SIN PRECIO (precio pendiente): costo 0 y
    no entran al promedio.   stock_actual = soles + dólares + sin precio."""
    if not st:
        return 0.0, 0.0
    usd = float(st.stock_usd or 0)
    sc = float(st.stock_sin_costo or 0)
    if moneda == 'USD':
        return usd, float(st.costo_usd or 0)
    if moneda == 'SC':
        return sc, 0.0
    return float(st.stock_actual or 0) - usd - sc, float(st.costo_promedio or 0)


def _otra_moneda(m):
    return 'PEN' if m == 'USD' else 'USD'


def _entrada_a_stock(st, cantidad, precio_unitario, moneda='PEN'):
    """Suma al stock en la parte de SU moneda y recalcula el COSTO PROMEDIO PONDERADO de esa parte.
    Devuelve (stock_antes total, costo prom. antes de esa moneda).
    moneda 'SC' (precio pendiente): suma a la parte "sin precio", sin tocar ningún costo promedio."""
    antes = float(st.stock_actual or 0)
    if moneda == 'SC':
        st.stock_sin_costo = round(float(st.stock_sin_costo or 0) + cantidad, 6)
        st.stock_actual = round(antes + cantidad, 6)
        return antes, 0.0
    moneda = 'USD' if moneda == 'USD' else 'PEN'
    q, prom = _bolsa(st, moneda)
    otra_q, _ = _bolsa(st, _otra_moneda(moneda))
    nuevo_q = q + cantidad
    costo = precio_unitario if q <= 1e-9 or nuevo_q <= 0 else (q * prom + cantidad * precio_unitario) / nuevo_q
    if q <= 1e-9:     # esta parte estaba vacía: si la otra tiene unidades, esas son las más antiguas (salen primero)
        st.bolsa_antigua = _otra_moneda(moneda) if otra_q > 1e-9 else moneda
    if moneda == 'USD':
        st.stock_usd, st.costo_usd = round(nuevo_q, 6), round(costo, 6)
    else:
        st.costo_promedio = round(costo, 6)
    st.stock_actual = round(antes + cantidad, 6)
    return antes, prom


def _repartir_fifo(pendientes, cantidad):
    """Descuenta 'cantidad' de las unidades sin precio de cada ingreso pendiente, del más antiguo al más nuevo.
    pendientes: detalles de ingreso con precio pendiente (con .id y .sin_costo_restante). Devuelve [(detalle_id, cantidad)];
    lo que no alcanza a ningún ingreso (p. ej. stock cargado desde Excel sin costo) va con detalle_id 0."""
    origenes, falta = [], cantidad
    for d in pendientes:
        if falta <= 1e-9:
            break
        r = float(d.sin_costo_restante or 0)
        toma = min(r, falta)
        if toma > 1e-9:
            d.sin_costo_restante = round(r - toma, 6)
            origenes.append((d.id, round(toma, 6)))
            falta -= toma
    if falta > 1e-9:
        origenes.append((0, round(falta, 6)))
    return origenes


def _pendientes_sin_costo(st, moneda=None, excluir_ingreso=None):
    """Detalles de ingreso (no anulados) de este insumo y empresa que todavía tienen el PRECIO PENDIENTE, del más antiguo al más nuevo."""
    q = (InsumoIngresoDetalle.query.join(InsumoIngreso, InsumoIngreso.id == InsumoIngresoDetalle.ingreso_id)
         .filter(InsumoIngreso.empresa == st.empresa, InsumoIngreso.estado == 'REGISTRADO',
                 InsumoIngresoDetalle.insumo_id == st.insumo_id, InsumoIngresoDetalle.precio_pendiente.is_(True)))
    if excluir_ingreso:
        q = q.filter(InsumoIngreso.id != excluir_ingreso)
    lista = q.order_by(InsumoIngreso.fecha, InsumoIngreso.id, InsumoIngresoDetalle.id).all()
    return [d for d in lista if not moneda or (d.ingreso.moneda or 'PEN') == moneda]


def _origen_txt(origenes):
    """[(12, 3.0), (0, 1.5)] -> '12:3,0:1.5' (de qué ingresos salieron las unidades sin precio)."""
    return ','.join(f'{d}:{round(c, 6):g}' for d, c in origenes)[:500] or None


def _origen_de_txt(texto):
    res = []
    for parte in (texto or '').split(','):
        try:
            d, c = parte.split(':')
            res.append((int(d), float(c)))
        except ValueError:
            continue
    return res


def _salida_por_monedas(st, cantidad, origenes=None):
    """Resta del stock: primero de las unidades MÁS ANTIGUAS (las compradas en soles o en dólares, según cuál entró antes).
    Cada parte sale a su costo promedio y en su moneda. Lo SIN PRECIO (precio pendiente) sale al FINAL, a costo 0 ('SC'),
    para que no distorsione el gasto; si se pasa una lista en 'origenes', se le agrega de qué ingresos salió.
    Devuelve (stock_antes, [(moneda, cantidad, costo_unitario)])."""
    antes = float(st.stock_actual or 0)
    primera = st.bolsa_antigua if st.bolsa_antigua in ('PEN', 'USD') else 'PEN'
    partes, falta = [], cantidad
    bolsas = {m: _bolsa(st, m) for m in ('PEN', 'USD')}     # se leen ANTES de mover nada (la de soles se calcula con las otras)
    for m in (primera, _otra_moneda(primera)):
        if falta <= 1e-9:
            break
        q, costo = bolsas[m]
        toma = min(max(q, 0), falta)
        if toma > 1e-9:
            partes.append((m, round(toma, 6), costo))
            falta -= toma
            if m == 'USD':
                st.stock_usd = round(q - toma, 6)
    q_sc = float(st.stock_sin_costo or 0)
    toma = min(max(q_sc, 0), falta)
    if toma > 1e-9:
        partes.append(('SC', round(toma, 6), 0.0))
        falta -= toma
        st.stock_sin_costo = round(q_sc - toma, 6)
        try:
            org = _repartir_fifo(_pendientes_sin_costo(st), toma)
        except Exception:
            app.logger.exception("No se pudo ubicar el ingreso de las unidades sin precio")
            org = [(0, round(toma, 6))]
        if origenes is not None:
            origenes.extend(org)
    if falta > 1e-9:          # no debería pasar (se valida el stock antes): sale de lo comprado en soles
        partes.append(('PEN', round(falta, 6), float(st.costo_promedio or 0)))
    st.stock_actual = round(antes - cantidad, 6)
    if float(st.stock_usd or 0) <= 1e-9:
        st.stock_usd, st.bolsa_antigua = 0.0, 'PEN'
    elif _bolsa(st, 'PEN')[0] <= 1e-9:
        st.bolsa_antigua = 'USD'
    return antes, partes


def _datos_mov_moneda(st, moneda):
    """Campos del Kardex que dependen de la moneda: costo prom. y unidades que quedan de esa moneda ('SC' = sin precio)."""
    q, c = _bolsa(st, moneda)
    return {'moneda': moneda, 'costo_prom_despues': c, 'stock_moneda_despues': round(q, 6)}


def _valorizar_sin_costo(st, cantidad, precio, moneda):
    """Pasa 'cantidad' unidades de la parte SIN PRECIO a la parte de su moneda con ese precio (recalcula el costo promedio
    ponderado como si recién entraran). El stock total no cambia. Devuelve (cantidad pasada, costo prom. antes, después)."""
    moneda = 'USD' if moneda == 'USD' else 'PEN'
    cant = round(min(max(float(st.stock_sin_costo or 0), 0), cantidad), 6)
    if cant <= 1e-9:
        q, c = _bolsa(st, moneda)
        return 0.0, c, c
    st.stock_sin_costo = round(float(st.stock_sin_costo or 0) - cant, 6)
    st.stock_actual = round(float(st.stock_actual or 0) - cant, 6)
    _, prom_antes = _entrada_a_stock(st, cant, precio, moneda)
    return cant, prom_antes, _bolsa(st, moneda)[1]


def _completar_precio_detalle(det, precio, ahora, ref_extra=''):
    """Pone el precio a un ítem que entró con PRECIO PENDIENTE: lo que de ese ítem sigue en stock pasa al costo promedio
    (queda en el Kardex como PRECIO COMPLETADO). Lo que ya salió antes de tener precio queda a costo 0 en esas salidas.
    Devuelve las unidades valorizadas."""
    ing = det.ingreso
    mon = 'USD' if ing.moneda == 'USD' else 'PEN'
    st = _stock_de(det.insumo_id, ing.empresa)
    restante = float(det.sin_costo_restante or 0)
    cant, prom_antes, prom_desp = _valorizar_sin_costo(st, restante, precio, mon)
    det.precio_unitario = round(precio, 6)
    det.precio_total = round(det.cantidad * precio, 2)
    det.precio_pendiente = False
    det.sin_costo_restante = 0.0
    det.cantidad_valorizada = cant
    det.precio_completado_por = session.get('nombre', '')[:100] or None
    det.fecha_precio = ahora
    det.costo_prom_despues = prom_desp
    ing.total = round(sum(d.precio_total or 0 for d in ing.detalles), 2)
    sim = MONEDAS_INSUMOS[mon]
    if cant > 1e-9:
        total = float(st.stock_actual or 0)
        db.session.add(InsumoMovimiento(
            empresa=ing.empresa, insumo_id=det.insumo_id, fecha=ahora, tipo='AJUSTE', concepto='VALORIZACION', cantidad=cant,
            costo_unitario=round(precio, 6), costo_total=round(cant * precio, 2), stock_antes=total, stock_despues=total,
            **_datos_mov_moneda(st, mon), referencia=f'Precio completado · Ingreso #{ing.id}'[:120], ingreso_id=ing.id,
            observacion=(f'{_cant_txt(cant)} und sin precio pasan a {sim} {precio:,.4f} (costo prom. {sim} {prom_antes:,.4f} → {sim} {prom_desp:,.4f})'
                         + (f' · {ref_extra}' if ref_extra else ''))[:255],
            user_id=session.get('user_id'), fecha_registro=ahora))
    return cant


def _valorizar_huerfanos(st, precio, moneda, ahora, referencia):
    """Unidades sin precio que no vienen de ningún ingreso (p. ej. carga desde Excel sin costo): pasan al costo promedio."""
    pend = sum(float(d.sin_costo_restante or 0) for d in _pendientes_sin_costo(st))
    huerfanos = round(float(st.stock_sin_costo or 0) - pend, 6)
    if huerfanos <= 1e-9:
        return 0.0
    cant, prom_antes, prom_desp = _valorizar_sin_costo(st, huerfanos, precio, moneda)
    if cant > 1e-9:
        sim = MONEDAS_INSUMOS['USD' if moneda == 'USD' else 'PEN']
        total = float(st.stock_actual or 0)
        db.session.add(InsumoMovimiento(
            empresa=st.empresa, insumo_id=st.insumo_id, fecha=ahora, tipo='AJUSTE', concepto='VALORIZACION', cantidad=cant,
            costo_unitario=round(precio, 6), costo_total=round(cant * precio, 2), stock_antes=total, stock_despues=total,
            **_datos_mov_moneda(st, moneda), referencia=referencia[:120],
            observacion=f'{_cant_txt(cant)} und sin precio pasan a {sim} {precio:,.4f} (costo prom. {sim} {prom_antes:,.4f} → {sim} {prom_desp:,.4f})'[:255],
            user_id=session.get('user_id'), fecha_registro=ahora))
    return cant


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
    """Insumos activos con el stock de la empresa (para los selectores con buscador)."""
    stocks = {s.insumo_id: s for s in InsumoStock.query.filter_by(empresa=empresa).all()}
    lista = []
    for i in Insumo.query.filter_by(activo=True).order_by(Insumo.codigo).all():
        s = stocks.get(i.id)
        lista.append({'id': i.id, 'codigo': i.codigo, 'descripcion': i.descripcion, 'unidad': i.unidad or '',
                      'categoria': i.categoria or '', 'stock': round(float(s.stock_actual or 0), 3) if s else 0,
                      'costo': round(float(s.costo_promedio or 0), 4) if s else 0, 'almacen': (s.almacen or '') if s else '',
                      'minimo': round(float(s.stock_minimo or 0), 3) if s else 0,
                      'stock_usd': round(float(s.stock_usd or 0), 3) if s else 0, 'costo_usd': round(float(s.costo_usd or 0), 4) if s else 0,
                      'stock_sc': round(float(s.stock_sin_costo or 0), 3) if s else 0,
                      'primero': (s.bolsa_antigua if s and s.bolsa_antigua in ('PEN', 'USD') else 'PEN')})
    return lista


