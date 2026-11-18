# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v30 · HERRAMIENTAS (ACTIVOS) dentro de Insumos internos
# Una herramienta NO se consume: se presta, se devuelve y dura. Por eso no es stock sino un REGISTRO de unidades:
#   · Cada una con su código (HER-00001), empresa (Anclajes / Import Bolts / General), valor, fecha de compra, vida útil,
#     y (si vino de una compra) su ORDEN DE COMPRA con sus documentos.
#   · Alta: a mano (las antiguas) o PASÁNDOLA DESDE EL STOCK DE INSUMOS (categoría HERRAMIENTAS: lo que entró por OC);
#     ahí sale del stock de insumos (Kardex "PASÓ A HERRAMIENTAS", no es gasto) y se crean las unidades con el precio
#     de su lote y la OC de la que vino.
#   · Préstamo (ASIGNADA a un trabajador / área, con firma) y devolución (con su condición), reparación.
#   · BAJA (malograda, fin de vida útil, perdida, robo...): la pide Almacén y la APRUEBA Logística o Gerencia. Solo ahí deja
#     de estar activa; su historial queda para siempre.
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS), después de los de insumos. Ver MAPA.md.
# =====================================================================================
from models import Herramienta, HerramientaMovimiento     # los modelos nuevos se importan aquí (app.py solo importa los suyos)
from flask import abort

ROLES_HERR_BAJA = ['admin', 'logistica']          # aprueban la baja
CATEGORIA_HERRAMIENTAS = 'HERRAMIENTAS'
HERR_ESTADOS = {
    'DISPONIBLE': {'txt': 'En almacén', 'color': '#15803d', 'icono': 'bi-box-seam'},
    'ASIGNADA': {'txt': 'Prestada', 'color': '#1d4ed8', 'icono': 'bi-person-badge'},
    'EN_REPARACION': {'txt': 'En reparación', 'color': '#b45309', 'icono': 'bi-wrench-adjustable'},
    'BAJA_PEDIDA': {'txt': 'Baja por aprobar', 'color': '#dc2626', 'icono': 'bi-hourglass-split'},
    'DE_BAJA': {'txt': 'De baja', 'color': '#64748b', 'icono': 'bi-x-octagon'},
}
HERR_CONDICIONES = {'BUENA': 'Buena', 'CON_DESGASTE': 'Con desgaste', 'MALOGRADA': 'Malograda'}
HERR_MOTIVOS_BAJA = {'MALOGRADA': 'Malograda / sin reparación', 'FIN_VIDA_UTIL': 'Terminó su vida útil', 'PERDIDA': 'Perdida',
                     'ROBO': 'Robada', 'OTRO': 'Otro motivo'}
HERR_TIPOS_MOV = {'ALTA': 'Alta', 'ASIGNACION': 'Prestada', 'DEVOLUCION': 'Devuelta', 'REPARACION': 'A reparación', 'REPARADA': 'Volvió de reparación',
                  'BAJA_PEDIDA': 'Baja pedida', 'BAJA': 'Dada de baja', 'BAJA_RECHAZADA': 'Baja rechazada', 'EDICION': 'Datos corregidos'}
HERR_MAX_ALTA = 50
_herr_ok = False


def _asegurar_herr():
    global _herr_ok
    if _herr_ok:
        return
    try:
        Herramienta.__table__.create(bind=db.engine, checkfirst=True)
        HerramientaMovimiento.__table__.create(bind=db.engine, checkfirst=True)
        _herr_ok = True
    except Exception as e:
        print(f"Aviso: no se pudo preparar Herramientas: {e}")


with app.app_context():
    _asegurar_herr()


def _ruta_herr(editar=False, baja=False):
    def deco(f):
        @_wraps_insumos(f)
        def envoltura(*args, **kwargs):
            rol = session.get('role')
            permitidos = ROLES_HERR_BAJA if baja else (ROLES_INSUMOS_EDITAN if editar else ROLES_INSUMOS_VEN)
            if rol not in permitidos:
                if request.method == 'POST':
                    flash('⛔ No tienes permiso para esto.')
                    return redirect(request.referrer or url_for('herramientas_lista'))
                return "Acceso denegado", 403
            _asegurar_insumos()
            _asegurar_herr()
            return f(*args, **kwargs)
        return envoltura
    return deco


def _herr_siguiente_numero():
    n = 0
    for (c,) in db.session.query(Herramienta.codigo).all():
        m = re.match(r'HER-(\d+)$', c or '')
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def _herr_vida(h, hoy=None):
    """{'fin': fecha en que termina la vida útil, 'cumplida': bool, 'dias': días que faltan (negativo = pasada)} o None."""
    if not h.fecha_compra or not h.vida_util_meses:
        return None
    hoy = hoy or hora_peru().date()
    meses = h.fecha_compra.month - 1 + int(h.vida_util_meses)
    anio, mes = h.fecha_compra.year + meses // 12, meses % 12 + 1
    import calendar
    fin = date(anio, mes, min(h.fecha_compra.day, calendar.monthrange(anio, mes)[1]))
    return {'fin': fin, 'cumplida': fin <= hoy, 'dias': (fin - hoy).days}


app.add_template_global(_herr_vida, 'herr_vida')


def _herr_mov(h, tipo, ahora, trabajador=None, area=None, condicion=None, nota=None, firma=None, foto=None):
    m = HerramientaMovimiento(herramienta_id=h.id, fecha=ahora, tipo=tipo, trabajador_id=trabajador.id if trabajador else None,
                              area_id=area.id if area else None, condicion=condicion, nota=(nota or '')[:500] or None,
                              firma_s3_key=firma, foto_s3_key=foto, usuario=session.get('nombre', '') or session.get('username', ''),
                              user_id=session.get('user_id'))
    db.session.add(m)
    return m


def _herr_subir_firma(data_url, h, claves):
    """Firma dibujada en pantalla -> S3 (None si no firmó). ValueError si no es válida."""
    if not data_url:
        return None
    if not data_url.startswith('data:image/png;base64,'):
        raise ValueError('Firma no válida.')
    datos = base64.b64decode(data_url.split(',', 1)[1], validate=True)
    if not datos.startswith(b'\x89PNG\r\n\x1a\n') or len(datos) > 400 * 1024:
        raise ValueError('Firma no válida o demasiado grande.')
    key = f"herramientas/firmas/{h.codigo}_{uuid.uuid4().hex[:10]}.png"
    s3_client.upload_fileobj(io.BytesIO(datos), S3_BUCKET_NAME, key, ExtraArgs={'ContentType': 'image/png'})
    claves.append(key)
    return key


def _herr_subir_foto(archivo, h, claves):
    """Foto / PDF opcional (evidencia de la baja, foto de la herramienta) -> S3. (key, None) o (None, error)."""
    if not archivo or not archivo.filename:
        return None, None
    ok, info = _validar_documento_kardex(archivo)
    if not ok:
        return None, info
    ext, mime, _t = info
    key = f"herramientas/fotos/{h.codigo}_{uuid.uuid4().hex[:10]}.{ext}"
    archivo.stream.seek(0)
    s3_client.upload_fileobj(archivo.stream, S3_BUCKET_NAME, key, ExtraArgs={'ContentType': mime})
    claves.append(key)
    return key, None


def _herr_trabajador(f, campo='trabajador_id'):
    t = InsumoTrabajador.query.get(f.get(campo, type=int)) if f.get(campo, type=int) else None
    return t if t and t.activo else None


def _herr_area(f, campo='area_id'):
    a = InsumoArea.query.get(f.get(campo, type=int)) if f.get(campo, type=int) else None
    return a if a and a.activo else None


def _herr_pendientes_insumos():
    """Stock de insumos de la categoría HERRAMIENTAS que todavía no se pasó al registro: [(insumo, empresa, cantidad)]."""
    try:
        filas = (db.session.query(Insumo, InsumoStock).join(InsumoStock, InsumoStock.insumo_id == Insumo.id)
                 .filter(func.upper(Insumo.categoria) == CATEGORIA_HERRAMIENTAS, InsumoStock.stock_actual > 1e-9).all())
    except Exception:
        db.session.rollback()
        return []
    return [(i, st.empresa, float(st.stock_actual or 0)) for i, st in sorted(filas, key=lambda x: (x[0].codigo, x[1].empresa))]


def _herr_bajas_por_aprobar():
    try:
        return Herramienta.query.filter_by(estado='BAJA_PEDIDA').count() if _herr_ok else 0
    except Exception:
        db.session.rollback()
        return 0


app.add_template_global(_herr_bajas_por_aprobar, 'herr_bajas_por_aprobar')


def _herr_ctx():
    return dict(estados=HERR_ESTADOS, condiciones=HERR_CONDICIONES, motivos_baja=HERR_MOTIVOS_BAJA, tipos_mov=HERR_TIPOS_MOV,
                empresas=EMPRESAS_INSUMOS, puede_editar=session.get('role') in ROLES_INSUMOS_EDITAN,
                puede_baja=session.get('role') in ROLES_HERR_BAJA, seccion='herramientas')


# ---------------------------- LISTA ----------------------------
@app.route('/insumos/herramientas')
@_ruta_herr()
def herramientas_lista():
    estado = request.args.get('estado', 'activas')
    empresa = request.args.get('empresa', 'TODAS')
    q = ' '.join((request.args.get('q') or '').split())
    trabajador_id = request.args.get('trabajador_id', type=int)
    vida = request.args.get('vida') == '1'
    todas = Herramienta.query.order_by(Herramienta.codigo).all()
    hoy = hora_peru().date()
    filas = []
    for h in todas:
        if estado == 'activas' and h.estado == 'DE_BAJA':
            continue
        if estado not in ('activas', 'todas') and h.estado != estado:
            continue
        if empresa in EMPRESAS_INSUMOS and h.empresa != empresa:
            continue
        if trabajador_id and h.asignado_a_id != trabajador_id:
            continue
        if q and not all(p in f'{h.codigo} {h.nombre} {h.marca or ""} {h.modelo or ""} {h.serie or ""} {h.asignado_a.nombre if h.asignado_a else ""}'.upper()
                         for p in q.upper().split()):
            continue
        v = _herr_vida(h, hoy)
        if vida and not (v and v['cumplida'] and h.estado != 'DE_BAJA'):
            continue
        filas.append({'h': h, 'vida': v})
    activas = [h for h in todas if h.estado != 'DE_BAJA']
    kpi = {'activas': len(activas), 'disponibles': sum(1 for h in activas if h.estado == 'DISPONIBLE'),
           'prestadas': sum(1 for h in activas if h.estado == 'ASIGNADA'), 'reparacion': sum(1 for h in activas if h.estado == 'EN_REPARACION'),
           'bajas_pend': sum(1 for h in activas if h.estado == 'BAJA_PEDIDA'),
           'vida': sum(1 for h in activas if (_herr_vida(h, hoy) or {}).get('cumplida')),
           'valor': sum(h.valor or 0 for h in activas if (h.moneda or 'PEN') == 'PEN'),
           'valor_usd': sum(h.valor or 0 for h in activas if h.moneda == 'USD')}
    return render_template('herramientas_lista.html', filas=filas, kpi=kpi, estado=estado, empresa=empresa, q=q, vida=vida,
                           trabajador_id=trabajador_id, pend_insumos=_herr_pendientes_insumos(),
                           trabajadores=InsumoTrabajador.query.filter_by(activo=True).order_by(InsumoTrabajador.nombre).all(), **_herr_ctx())


# ---------------------------- ALTA MANUAL ----------------------------
def _herr_leer_datos(f, h=None):
    """Campos comunes de alta / edición. Devuelve (dict, error)."""
    d = {'nombre': ' '.join((f.get('nombre') or '').split()).upper()[:200], 'marca': ' '.join((f.get('marca') or '').split()).upper()[:80] or None,
         'modelo': ' '.join((f.get('modelo') or '').split()).upper()[:80] or None, 'categoria': ' '.join((f.get('categoria') or '').split()).upper()[:100] or None,
         'ubicacion': ' '.join((f.get('ubicacion') or '').split())[:100] or None, 'proveedor': ' '.join((f.get('proveedor') or '').split()).upper()[:200] or None,
         'factura': ' '.join((f.get('factura') or '').split()).upper()[:60] or None, 'observacion': ' '.join((f.get('observacion') or '').split())[:500] or None,
         'moneda': 'USD' if f.get('moneda') == 'USD' else 'PEN'}
    if len(d['nombre']) < 3:
        return None, 'Escribe qué herramienta es (mínimo 3 letras).'
    empresa = (f.get('empresa') or '').upper()
    if empresa not in EMPRESAS_INSUMOS:
        return None, 'Elige de qué empresa es (o General si no se sabe).'
    d['empresa'] = empresa
    v = _num(f.get('valor'))
    if v is not None and v < 0:
        return None, 'El valor no puede ser negativo.'
    d['valor'] = round(v, 2) if v is not None else None
    vu = f.get('vida_util_meses', type=int)
    if vu is not None and not (1 <= vu <= 600):
        return None, 'La vida útil va en meses (de 1 a 600).'
    d['vida_util_meses'] = vu
    for campo in ('fecha_compra', 'garantia_hasta'):
        txt = (f.get(campo) or '').strip()
        if not txt:
            d[campo] = None
            continue
        try:
            d[campo] = datetime.strptime(txt, '%Y-%m-%d').date()
        except ValueError:
            return None, 'Revisa las fechas.'
    if d['fecha_compra'] and d['fecha_compra'] > hora_peru().date():
        return None, 'La fecha de compra no puede ser futura.'
    return d, None


@app.route('/insumos/herramientas/nueva', methods=['GET', 'POST'])
@_ruta_herr(editar=True)
def herramientas_nueva():
    if request.method == 'GET':
        return render_template('herramientas_form.html', h=None, hoy=hora_peru().date(), categorias=_herr_categorias(),
                               almacenes=_catalogo_insumos('INSUMO_ALMACEN'), **_herr_ctx())
    f = request.form
    d, err = _herr_leer_datos(f)
    cantidad = f.get('cantidad', type=int) or 1
    if not err and not (1 <= cantidad <= HERR_MAX_ALTA):
        err = f'La cantidad va de 1 a {HERR_MAX_ALTA}.'
    if err:
        flash(f'⛔ {err}')
        return redirect(url_for('herramientas_nueva'))
    series = [x.strip().upper()[:80] for x in (f.get('series') or '').splitlines() if x.strip()]
    ahora, n = hora_peru(), _herr_siguiente_numero()
    creadas = []
    try:
        for k in range(cantidad):
            h = Herramienta(codigo=f'HER-{n + k:05d}', estado='DISPONIBLE', origen='MANUAL', serie=series[k] if k < len(series) else None,
                            creado_por=session.get('nombre', ''), fecha_creacion=ahora, **d)
            db.session.add(h)
            db.session.flush()
            _herr_mov(h, 'ALTA', ahora, nota='Registrada a mano' + (f" · {EMPRESAS_INSUMOS[h.empresa]['corto']}"))
            creadas.append(h)
        registrar_log(f"Registró {cantidad} herramienta(s) {creadas[0].codigo}{(' a ' + creadas[-1].codigo) if cantidad > 1 else ''}: {d['nombre']}",
                      'bi-tools', 'text-success')
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('⛔ Otro usuario registró herramientas al mismo tiempo: vuelve a intentarlo.')
        return redirect(url_for('herramientas_nueva'))
    flash(f"✅ {cantidad} herramienta(s) registrada(s): {creadas[0].codigo}{(' a ' + creadas[-1].codigo) if cantidad > 1 else ''}.")
    return redirect(url_for('herramientas_ficha', herr_id=creadas[0].id) if cantidad == 1 else url_for('herramientas_lista', q=d['nombre']))


def _herr_categorias():
    nombres = {c for (c,) in db.session.query(Herramienta.categoria).distinct().all() if c}
    return sorted(nombres | {CATEGORIA_HERRAMIENTAS}, key=_clave_alfabetica)


# ---------------------------- PASAR DESDE EL STOCK DE INSUMOS ----------------------------
@app.route('/insumos/herramientas/desde-insumos', methods=['GET', 'POST'])
@_ruta_herr(editar=True)
def herramientas_desde_insumos():
    """Lo que está en el stock de insumos (categoría HERRAMIENTAS, normalmente comprado con OC) pasa al registro:
    sale del stock (PEPS, Kardex "PASÓ A HERRAMIENTAS", no es consumo) y se crea UNA herramienta por unidad, con el precio
    de su lote, la empresa, el proveedor, la factura y la orden de compra de la que vino."""
    if request.method == 'GET':
        return render_template('herramientas_desde_insumos.html', pend=_herr_pendientes_insumos(), almacenes=_catalogo_insumos('INSUMO_ALMACEN'),
                               insumo_sel=request.args.get('insumo_id', type=int), empresa_sel=request.args.get('empresa'), **_herr_ctx())
    f = request.form
    volver = url_for('herramientas_desde_insumos')
    ins = Insumo.query.get(f.get('insumo_id', type=int)) if f.get('insumo_id', type=int) else None
    empresa = (f.get('empresa') or '').upper()
    cantidad = _num(f.get('cantidad'))
    if not ins or empresa not in EMPRESAS_INSUMOS:
        flash('⛔ Elige el insumo y el inventario.')
        return redirect(volver)
    if not cantidad or cantidad <= 0 or cantidad != int(cantidad) or cantidad > HERR_MAX_ALTA:
        flash(f'⛔ La cantidad son unidades enteras (de 1 a {HERR_MAX_ALTA}): cada una será una herramienta con su código.')
        return redirect(volver)
    cantidad = int(cantidad)
    st = _stock_de(ins.id, empresa, crear=False)
    if not st or float(st.stock_actual or 0) < cantidad - 1e-9:
        flash(f'⛔ Solo hay {_cant_txt(float(st.stock_actual or 0) if st else 0)} de {ins.codigo} en {EMPRESAS_INSUMOS[empresa]["corto"]}.')
        return redirect(volver)
    nombre = ' '.join((f.get('nombre') or ins.descripcion or '').split()).upper()[:200]
    vu = f.get('vida_util_meses', type=int)
    ahora, n = hora_peru(), _herr_siguiente_numero()
    creadas = []
    try:
        antes, partes = _sacar_de_lotes(st, cantidad)
        unidades = []      # una entrada por unidad: (lote, costo, moneda)
        for lote, c, u, m_ in partes:
            unidades += [(lote, u, m_)] * int(round(c))
            db.session.add(InsumoMovimiento(
                empresa=empresa, insumo_id=ins.id, fecha=ahora, tipo='SALIDA', concepto='A_HERRAMIENTAS', cantidad=c,
                costo_unitario=u or 0, costo_total=round(c * (u or 0), 2), stock_antes=antes, stock_despues=st.stock_actual,
                **_datos_mov_lote(lote), referencia=f'Pasó al registro de herramientas'[:120],
                observacion='No es consumo: queda como herramienta (activo) con su código', user_id=session.get('user_id'), fecha_registro=ahora))
        for k, (lote, u, m_) in enumerate(unidades):
            ing = InsumoIngreso.query.get(lote.ingreso_id) if lote.ingreso_id else None
            h = Herramienta(codigo=f'HER-{n + k:05d}', nombre=nombre, categoria=ins.categoria or CATEGORIA_HERRAMIENTAS, empresa=empresa,
                            estado='DISPONIBLE', ubicacion=st.almacen, valor=round(u, 2) if u is not None else None, moneda=m_ or 'PEN',
                            fecha_compra=(lote.fecha.date() if lote.fecha else None), vida_util_meses=vu,
                            proveedor=(lote.proveedor or (ing.razon_social if ing else None)), factura=(ing.numero_factura if ing else None),
                            origen='INSUMOS', orden_compra_id=(ing.orden_compra_id if ing else None), insumo_id=ins.id, insumo_lote_id=lote.id,
                            creado_por=session.get('nombre', ''), fecha_creacion=ahora)
            db.session.add(h)
            db.session.flush()
            _herr_mov(h, 'ALTA', ahora, nota=f"Pasó desde el stock de insumos {ins.codigo} ({EMPRESAS_INSUMOS[empresa]['corto']}, lote #{lote.id})")
            creadas.append(h)
        registrar_log(f"Pasó {cantidad} {ins.codigo} del stock de insumos {EMPRESAS_INSUMOS[empresa]['corto']} al registro de herramientas "
                      f"({creadas[0].codigo}{(' a ' + creadas[-1].codigo) if cantidad > 1 else ''})", 'bi-tools', 'text-primary')
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        flash(f'⛔ {e}')
        return redirect(volver)
    except IntegrityError:
        db.session.rollback()
        flash('⛔ Otro usuario registró herramientas al mismo tiempo: vuelve a intentarlo.')
        return redirect(volver)
    flash(f"✅ {cantidad} {ins.codigo} pasaron al registro de herramientas ({creadas[0].codigo}{(' a ' + creadas[-1].codigo) if cantidad > 1 else ''}) "
          f"y salieron del stock de insumos de {EMPRESAS_INSUMOS[empresa]['corto']}.")
    return redirect(url_for('herramientas_ficha', herr_id=creadas[0].id) if cantidad == 1 else url_for('herramientas_lista', q=nombre))


# ---------------------------- FICHA ----------------------------
@app.route('/insumos/herramientas/<int:herr_id>')
@_ruta_herr()
def herramientas_ficha(herr_id):
    h = Herramienta.query.get_or_404(herr_id)
    docs_oc = OrdenCompraDocumento.query.filter_by(orden_id=h.orden_compra_id).order_by(OrdenCompraDocumento.id).all() if h.orden_compra_id else []
    return render_template('herramientas_ficha.html', h=h, movs=h.movimientos.all(), docs_oc=docs_oc, vida=_herr_vida(h),
                           trabajadores=InsumoTrabajador.query.filter_by(activo=True).order_by(InsumoTrabajador.nombre).all(),
                           areas=InsumoArea.query.filter_by(activo=True).order_by(InsumoArea.nombre).all(), categorias=_herr_categorias(),
                           almacenes=_catalogo_insumos('INSUMO_ALMACEN'), tipos_doc=TIPOS_DOC_OC, puede_ver_oc=session.get('role') in ROLES_OC_VEN,
                           hoy=hora_peru().date(), **_herr_ctx())


@app.route('/insumos/herramientas/<int:herr_id>/archivo/<int:mov_id>/<cual>')
@_ruta_herr()
def herramientas_archivo(herr_id, mov_id, cual):
    """Firma o foto de un movimiento (o la foto de la herramienta con mov_id=0)."""
    h = Herramienta.query.get_or_404(herr_id)
    if mov_id == 0:
        key = h.foto_s3_key
    else:
        m = HerramientaMovimiento.query.get_or_404(mov_id)
        if m.herramienta_id != h.id:
            abort(404)
        key = m.firma_s3_key if cual == 'firma' else m.foto_s3_key
    if not key:
        abort(404)
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
    except Exception:
        abort(404)
    ext = key.rsplit('.', 1)[-1].lower()
    mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp', 'pdf': 'application/pdf'}.get(ext, 'application/octet-stream')
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=mime, download_name=f'{h.codigo}_{cual}.{ext}')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@app.route('/insumos/herramientas/<int:herr_id>/documento-oc/<int:doc_id>')
@_ruta_herr()
def herramientas_doc_oc(herr_id, doc_id):
    """Documento de la orden de compra de la herramienta (Almacén puede verlo aunque no entre a Compras)."""
    h = Herramienta.query.get_or_404(herr_id)
    doc = OrdenCompraDocumento.query.get_or_404(doc_id)
    if not h.orden_compra_id or doc.orden_id != h.orden_compra_id:
        abort(404)
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception:
        abort(404)
    ext = doc.s3_key.rsplit('.', 1)[-1].lower()
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=doc.content_type or 'application/octet-stream',
                     download_name=secure_filename(f"{doc.tipo.lower()}_{h.codigo}_{doc.id}.{ext}"))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


# ---------------------------- ACCIONES ----------------------------
def _herr_accion(herr_id, permitidos):
    h = Herramienta.query.get_or_404(herr_id)
    if h.estado not in permitidos:
        flash(f'⛔ {h.codigo} está "{HERR_ESTADOS[h.estado]["txt"]}": eso no se puede hacer ahora.')
        return h, redirect(url_for('herramientas_ficha', herr_id=h.id))
    return h, None


def _herr_guardar(h, claves, msg, log=None):
    try:
        h.actualizado_por, h.fecha_actualizacion = session.get('nombre', ''), hora_peru()
        if log:
            registrar_log(log, 'bi-tools', 'text-primary')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        app.logger.exception('Herramientas: no se pudo guardar')
        flash(f'⛔ No se guardó: {e}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    flash(msg)
    return redirect(url_for('herramientas_ficha', herr_id=h.id))


@app.route('/insumos/herramientas/<int:herr_id>/editar', methods=['POST'])
@_ruta_herr(editar=True)
def herramientas_editar(herr_id):
    h = Herramienta.query.get_or_404(herr_id)
    d, err = _herr_leer_datos(request.form, h)
    if err:
        flash(f'⛔ {err}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    d['serie'] = ' '.join((request.form.get('serie') or '').split()).upper()[:80] or None
    cambios = [f"{k}: {getattr(h, k) or '—'} → {v or '—'}" for k, v in d.items() if (getattr(h, k) or None) != (v or None)]
    if not cambios:
        flash('No había nada que cambiar.')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    for k, v in d.items():
        setattr(h, k, v)
    claves = []
    foto, err = _herr_subir_foto(request.files.get('foto'), h, claves)
    if err:
        flash(f'⛔ {err}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    if foto:
        h.foto_s3_key = foto
    _herr_mov(h, 'EDICION', hora_peru(), nota='; '.join(cambios))
    return _herr_guardar(h, claves, '✅ Datos guardados.')


@app.route('/insumos/herramientas/<int:herr_id>/asignar', methods=['POST'])
@_ruta_herr(editar=True)
def herramientas_asignar(herr_id):
    h, no = _herr_accion(herr_id, ('DISPONIBLE',))
    if no:
        return no
    f = request.form
    t, a = _herr_trabajador(f), _herr_area(f)
    if not t:
        flash('⛔ Elige a quién se presta.')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    a = a or t.area
    claves, ahora = [], hora_peru()
    try:
        firma = _herr_subir_firma(f.get('firma_png') or '', h, claves)
    except ValueError as e:
        flash(f'⛔ {e}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    h.estado, h.asignado_a_id, h.area_id, h.fecha_asignacion = 'ASIGNADA', t.id, a.id if a else None, ahora
    _herr_mov(h, 'ASIGNACION', ahora, trabajador=t, area=a, condicion=f.get('condicion') if f.get('condicion') in HERR_CONDICIONES else 'BUENA',
              nota=f.get('nota'), firma=firma)
    return _herr_guardar(h, claves, f'✅ {h.codigo} prestada a {t.nombre}.', f'Prestó la herramienta {h.codigo} ({h.nombre}) a {t.nombre}')


@app.route('/insumos/herramientas/<int:herr_id>/devolver', methods=['POST'])
@_ruta_herr(editar=True)
def herramientas_devolver(herr_id):
    h, no = _herr_accion(herr_id, ('ASIGNADA',))
    if no:
        return no
    f = request.form
    cond = f.get('condicion') if f.get('condicion') in HERR_CONDICIONES else 'BUENA'
    claves, ahora = [], hora_peru()
    try:
        firma = _herr_subir_firma(f.get('firma_png') or '', h, claves)
    except ValueError as e:
        flash(f'⛔ {e}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    quien = h.asignado_a
    _herr_mov(h, 'DEVOLUCION', ahora, trabajador=quien, area=h.area, condicion=cond, nota=f.get('nota'), firma=firma)
    h.asignado_a_id, h.area_id, h.fecha_asignacion = None, None, None
    h.estado = 'EN_REPARACION' if f.get('a_reparacion') == '1' else 'DISPONIBLE'
    if h.estado == 'EN_REPARACION':
        _herr_mov(h, 'REPARACION', ahora, nota='Al devolverla ' + HERR_CONDICIONES[cond].lower())
    extra = ' Pasó a reparación.' if h.estado == 'EN_REPARACION' else (' Si ya no sirve, pide su baja.' if cond == 'MALOGRADA' else '')
    return _herr_guardar(h, claves, f'✅ {h.codigo} devuelta ({HERR_CONDICIONES[cond].lower()}).{extra}',
                         f'Recibió la devolución de la herramienta {h.codigo} de {quien.nombre if quien else "-"} ({HERR_CONDICIONES[cond].lower()})')


@app.route('/insumos/herramientas/<int:herr_id>/reparacion', methods=['POST'])
@_ruta_herr(editar=True)
def herramientas_reparacion(herr_id):
    vuelve = request.form.get('vuelve') == '1'
    h, no = _herr_accion(herr_id, ('EN_REPARACION',) if vuelve else ('DISPONIBLE',))
    if no:
        return no
    h.estado = 'DISPONIBLE' if vuelve else 'EN_REPARACION'
    _herr_mov(h, 'REPARADA' if vuelve else 'REPARACION', hora_peru(), nota=request.form.get('nota'))
    return _herr_guardar(h, [], f"✅ {h.codigo} {'volvió de reparación: está en almacén' if vuelve else 'enviada a reparación'}.")


@app.route('/insumos/herramientas/<int:herr_id>/baja', methods=['POST'])
@_ruta_herr(editar=True)
def herramientas_baja(herr_id):
    """Pedir la baja (Almacén) o darla de una vez si quien la pide es Logística / Gerencia y marca "aprobar ya"."""
    h, no = _herr_accion(herr_id, ('DISPONIBLE', 'ASIGNADA', 'EN_REPARACION'))
    if no:
        return no
    f = request.form
    motivo = f.get('motivo')
    detalle = ' '.join((f.get('detalle') or '').split())[:500]
    if motivo not in HERR_MOTIVOS_BAJA:
        flash('⛔ Elige el motivo de la baja.')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    if len(detalle) < 5:
        flash('⛔ Explica qué pasó (mínimo 5 letras).')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    claves, ahora = [], hora_peru()
    foto, err = _herr_subir_foto(request.files.get('foto'), h, claves)
    if err:
        flash(f'⛔ {err}')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    h.estado_antes_baja = h.estado
    h.baja_motivo, h.baja_detalle = motivo, detalle
    h.baja_pedida_por, h.fecha_baja_pedida = session.get('nombre', ''), ahora
    _herr_mov(h, 'BAJA_PEDIDA', ahora, nota=f"{HERR_MOTIVOS_BAJA[motivo]}: {detalle}", foto=foto)
    directo = f.get('aprobar_ya') == '1' and session.get('role') in ROLES_HERR_BAJA
    if directo:
        _herr_dar_baja(h, ahora, 'Aprobada al pedirla')
        return _herr_guardar(h, claves, f'✅ {h.codigo} dada de BAJA ({HERR_MOTIVOS_BAJA[motivo].lower()}).',
                             f'Dio de baja la herramienta {h.codigo} ({h.nombre}): {HERR_MOTIVOS_BAJA[motivo]} · {detalle}')
    h.estado = 'BAJA_PEDIDA'
    try:
        _notif_crear('HERR_BAJA', f'Baja de herramienta por aprobar · {h.codigo}', f'{h.nombre} · {HERR_MOTIVOS_BAJA[motivo]}: {detalle}',
                     url_for('herramientas_ficha', herr_id=h.id), excluir=session.get('user_id'))
    except Exception:
        app.logger.exception('Herramientas: no se pudo avisar la baja')
    return _herr_guardar(h, claves, f'✅ Baja de {h.codigo} pedida: la aprueba Logística o Gerencia.',
                         f'Pidió la baja de la herramienta {h.codigo} ({h.nombre}): {HERR_MOTIVOS_BAJA[motivo]} · {detalle}')


def _herr_dar_baja(h, ahora, nota):
    if h.asignado_a_id:
        h.asignado_a_id, h.area_id, h.fecha_asignacion = None, None, None
    h.estado, h.baja_aprobada_por, h.fecha_baja = 'DE_BAJA', session.get('nombre', ''), ahora
    _herr_mov(h, 'BAJA', ahora, nota=nota)


@app.route('/insumos/herramientas/<int:herr_id>/baja/resolver', methods=['POST'])
@_ruta_herr(baja=True)
def herramientas_baja_resolver(herr_id):
    h, no = _herr_accion(herr_id, ('BAJA_PEDIDA',))
    if no:
        return no
    ahora, nota = hora_peru(), ' '.join((request.form.get('nota') or '').split())[:300]
    if request.form.get('aprobar') == '1':
        _herr_dar_baja(h, ahora, ('Aprobada' + (f': {nota}' if nota else '')))
        return _herr_guardar(h, [], f'✅ {h.codigo} dada de BAJA. Ya no figura entre las activas (su historial queda).',
                             f'Aprobó la baja de la herramienta {h.codigo} ({h.nombre})')
    if len(nota) < 5:
        flash('⛔ Escribe por qué no se da de baja (mínimo 5 letras).')
        return redirect(url_for('herramientas_ficha', herr_id=h.id))
    h.estado = h.estado_antes_baja if h.estado_antes_baja in ('DISPONIBLE', 'ASIGNADA', 'EN_REPARACION') else 'DISPONIBLE'
    if h.estado == 'ASIGNADA' and not h.asignado_a_id:
        h.estado = 'DISPONIBLE'
    _herr_mov(h, 'BAJA_RECHAZADA', ahora, nota=nota)
    h.baja_motivo = h.baja_detalle = None
    return _herr_guardar(h, [], f'Baja rechazada: {h.codigo} vuelve a "{HERR_ESTADOS[h.estado]["txt"]}".')
