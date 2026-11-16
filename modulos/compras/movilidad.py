# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS (OC / OS) · PLANILLA POR GASTO DE MOVILIDAD (v26)
# Una o varias planillas por orden (en CUALQUIER estado del flujo): un trabajador, un día, sus desplazamientos
# (motivo, destino, monto). Cada empresa con su razón social, RUC, logo y numeración correlativa propia.
# PDF con el formato de la empresa + base legal; firma del trabajador en pantalla o subiendo la hoja firmada a mano.
# Firmada ya no se edita (hay que quitar la firma, queda en el historial). No se borra: se ANULA (el número no se reutiliza).
# Tope deducible por trabajador y día: 4% de la RMV (se avisa, no se bloquea). Ver MAPA.md.
# Este archivo NO se importa: app.py lo carga (MODULOS_EN_ARCHIVOS), como si su código estuviera escrito ahí.
# =====================================================================================
from models import OrdenCompraMovilidad, OCMovilidadTrabajador

ROLES_MOV_VEN = ['admin', 'logistica', 'administracion']          # ven, crean, editan y firman (los mismos que ven la orden)
ROLES_MOV_ANULAN = ['admin', 'logistica']                         # anulan y quitan la firma
MOV_RMV_DEF = 1230.0              # Remuneración Mínima Vital vigente desde el 01/10/2026 (D.S. 015-2026-TR). Se cambia desde la planilla (admin)
MOV_TOPE_PCT = 0.04               # tope deducible por trabajador y por día: 4% de la RMV
MOV_FILAS_MAX = 12
MOV_MONTO_MAX = 9999.99
MOV_MOTIVOS = ['RECOJO DE MATERIAL', 'ENCOMIENDA DE MATERIAL', 'ENVÍO DE MATERIAL POR AGENCIA', 'ENTREGA DE MATERIAL AL CLIENTE',
               'LLEVAR MATERIAL AL SERVICIO', 'RECOGER MATERIAL DEL SERVICIO', 'COMPRA DE MATERIAL', 'ENTREGA / RECOJO DE DOCUMENTOS',
               'PAGO / DEPÓSITO AL PROVEEDOR', 'VISITA AL PROVEEDOR']
# "Elegir del sistema": las cuentas agrupadas por rol (en este orden). Los auditores no aparecen.
MOV_ROLES_ORDEN = ['logistica', 'almacen', 'chofer', 'vendedor', 'administracion', 'admin', 'almacen_visor']
MOV_ROLES_FUERA = ('auditor_stock',)
MOV_MESES = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SETIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']
MOV_BASE_LEGAL = ('Base Legal: Inciso a1) del artículo 37º del TUO de la Ley del Impuesto a la Renta e inciso v) del artículo 21º del '
                  'Reglamento de la Ley del Impuesto a la Renta.')
MOV_NOTA = ('Nota: La falta de consignación de la fecha en que se incurrió en el gasto, nombres y apellidos de cada trabajador, número de DNI, '
            'motivo y destino del desplazamiento y monto gastado, respecto a cada desplazamiento sólo inhabilita la planilla para la '
            'sustentación del gasto que corresponda a tal desplazamiento.')
_mov_ok = False


def _asegurar_mov():
    global _mov_ok
    if not _mov_ok:
        OrdenCompraMovilidad.__table__.create(bind=db.engine, checkfirst=True)
        OCMovilidadTrabajador.__table__.create(bind=db.engine, checkfirst=True)
        _mov_ok = True


def _ruta_mov(roles=None, como_json=False):
    def deco(f):
        @_wraps_insumos(f)
        def envoltura(*args, **kwargs):
            if session.get('role') not in (roles or ROLES_MOV_VEN):
                return ({'status': 'error', 'msg': 'No autorizado'}, 403) if como_json else ("Acceso denegado", 403)
            _asegurar_insumos()
            _asegurar_oc()
            _asegurar_mov()
            return f(*args, **kwargs)
        return envoltura
    return deco


# ---------------------------- utilidades ----------------------------
def _mov_rmv():
    try:
        c = OCConfig.query.get('MOV_RMV')
        v = float(c.valor) if c and c.valor else MOV_RMV_DEF
        return v if v > 0 else MOV_RMV_DEF
    except Exception:
        db.session.rollback()
        return MOV_RMV_DEF


def _mov_tope(rmv=None):
    return round((rmv or _mov_rmv()) * MOV_TOPE_PCT, 2)


def _mov_numero_txt(m):
    return f"00-{int(m.numero or 0):05d}"


def _mov_codigo(m):
    return f"Planilla de movilidad N° {_mov_numero_txt(m)}"


def _mov_filas(m):
    try:
        return [f for f in json.loads(m.filas or '[]') if isinstance(f, dict)]
    except (ValueError, TypeError):
        return []


def _mov_periodo(fecha):
    return f"MES DE {MOV_MESES[fecha.month - 1]} {fecha.year}"


def _mov_siguiente_numero(empresa):
    ultimo = db.session.query(func.max(OrdenCompraMovilidad.numero)).filter(OrdenCompraMovilidad.empresa == empresa).scalar()
    return (ultimo or 0) + 1


def _mov_firmada(m):
    return bool(m.firma_s3_key or m.escaneo_s3_key)


def _mov_de_orden(orden):
    """Planillas de la orden (las anuladas al final)."""
    try:
        _asegurar_mov()
        lista = OrdenCompraMovilidad.query.filter_by(orden_id=orden.id).order_by(OrdenCompraMovilidad.fecha_gasto, OrdenCompraMovilidad.id).all()
    except Exception:
        db.session.rollback()
        return []
    return sorted(lista, key=lambda m: bool(m.anulada))


def _mov_por_orden(ids):
    """{orden_id: [planillas vigentes]} para la lista de órdenes (una sola consulta)."""
    if not ids:
        return {}
    try:
        _asegurar_mov()
        res = {}
        for m in OrdenCompraMovilidad.query.filter(OrdenCompraMovilidad.orden_id.in_(list(ids)), OrdenCompraMovilidad.anulada.isnot(True)).all():
            res.setdefault(m.orden_id, []).append(m)
        return res
    except Exception:
        db.session.rollback()
        return {}


def _mov_dia_trabajador(dni, fecha, empresa, excluir_id=None):
    """Lo que el trabajador ya suma ese día en esa empresa (otras planillas vigentes)."""
    q = OrdenCompraMovilidad.query.filter(OrdenCompraMovilidad.trabajador_dni == dni, OrdenCompraMovilidad.fecha_gasto == fecha,
                                          OrdenCompraMovilidad.empresa == empresa, OrdenCompraMovilidad.anulada.isnot(True))
    if excluir_id:
        q = q.filter(OrdenCompraMovilidad.id != excluir_id)
    otras = q.all()
    return round(sum(o.total or 0 for o in otras), 2), otras


def _mov_tope_info(m):
    """Si el trabajador pasa el tope diario (4% RMV) ese día: {'dia', 'tope', 'exceso', 'otras'} o None."""
    dia, otras = _mov_dia_trabajador(m.trabajador_dni, m.fecha_gasto, m.empresa, m.id)
    tope = _mov_tope(m.rmv)
    total = round(dia + (m.total or 0), 2)
    if total > tope + 1e-9:
        return {'dia': total, 'tope': tope, 'exceso': round(total - tope, 2), 'otras': otras}
    return None


def _mov_monto(txt):
    t = (txt or '').strip().replace(',', '.').replace('S/', '').strip()
    if not t:
        return None
    v = round(float(t), 2)
    if v != v or v < 0:
        raise ValueError
    return v


def _mov_trabajadores_previos():
    """[{nombre, dni}] de planillas anteriores (el más reciente primero) para autocompletar."""
    vistos, res = set(), []
    for nombre, dni in (db.session.query(OrdenCompraMovilidad.trabajador_nombre, OrdenCompraMovilidad.trabajador_dni)
                        .order_by(OrdenCompraMovilidad.id.desc()).limit(400).all()):
        if dni and dni not in vistos:
            vistos.add(dni)
            res.append({'nombre': nombre, 'dni': dni})
    return res[:80]


def _mov_motivos_previos():
    usados = []
    for (filas,) in db.session.query(OrdenCompraMovilidad.filas).order_by(OrdenCompraMovilidad.id.desc()).limit(150).all():
        try:
            for f in json.loads(filas or '[]'):
                mot = (f.get('motivo') or '').strip().upper()
                if mot and mot not in usados and mot not in MOV_MOTIVOS:
                    usados.append(mot)
        except (ValueError, TypeError, AttributeError):
            continue
    return MOV_MOTIVOS + usados[:30]


def _mov_fila_sugerida(orden):
    """Primera fila propuesta según la orden: a dónde se va y para qué."""
    motivo = 'LLEVAR MATERIAL AL SERVICIO' if orden.tipo == 'OS' else 'RECOJO DE MATERIAL'
    destino = (orden.razon_social or '').strip()
    lugar = (orden.lugar_recojo or orden.direccion or '').strip()
    if lugar:
        destino = f"{destino} - {lugar}" if destino else lugar
    return {'motivo': f"{motivo} ({_oc_codigo(orden)})"[:120], 'destino': destino[:200], 'monto': None}


app.add_template_global(_mov_de_orden, 'oc_movilidades')
app.add_template_global(_mov_numero_txt, 'mov_numero_txt')
app.add_template_global(_mov_firmada, 'mov_firmada')
app.add_template_global(_mov_filas, 'mov_filas')
app.add_template_global(ROLES_MOV_VEN, 'roles_mov')
app.add_template_global(ROLES_MOV_ANULAN, 'roles_mov_anulan')


def _mov_evento(m, accion_txt):
    _oc_evento(m.orden, 'MOVILIDAD', f"{_mov_codigo(m)} ({EMPRESAS_OC.get(m.empresa, {}).get('corto', m.empresa)}): {accion_txt}"[:500])


def _mov_guardar_firma(m, data_url, claves):
    """Firma dibujada en pantalla (data:image/png;base64,...) -> S3. Lanza ValueError si no es válida."""
    if not (data_url or '').startswith('data:image/png;base64,'):
        raise ValueError('Firma no válida.')
    datos = base64.b64decode(data_url.split(',', 1)[1], validate=True)
    if not datos.startswith(b'\x89PNG\r\n\x1a\n') or len(datos) > 400 * 1024:
        raise ValueError('Firma no válida o demasiado grande.')
    clave = f"ordenes/{m.empresa.lower()}/movilidad/firma_{m.id}_{uuid.uuid4().hex[:8]}.png"
    s3_client.upload_fileobj(io.BytesIO(datos), S3_BUCKET_NAME, clave, ExtraArgs={'ContentType': 'image/png'})
    claves.append(clave)
    viejo = m.firma_s3_key
    m.firma_s3_key, m.firma_fecha, m.firma_por = clave, hora_peru(), session.get('nombre', '')
    return viejo


# ---------------------------- trabajadores guardados (para que se llenen solos) ----------------------------
def _mov_rol_fuera(rol):
    return (rol or '') in MOV_ROLES_FUERA or 'auditor' in (rol or '')


def _mov_dni_valido(dni):
    return bool(re.fullmatch(r'\d{8}', dni or '') or re.fullmatch(r'[0-9A-Z]{9,12}', dni or ''))


def _mov_trab_json(t):
    return {'id': t.id, 'nombre': t.nombre, 'dni': t.dni, 'cargo': t.cargo or '', 'user_id': t.user_id, 'activo': bool(t.activo),
            'usuario': t.usuario.nombre_completo if t.usuario else '', 'rol': ROLE_LABELS.get(t.usuario.role, t.usuario.role) if t.usuario else ''}


def _mov_opciones_trabajador():
    """Opciones de "Elegir del sistema": cuentas por rol (sin auditores) + trabajadores guardados sin cuenta.
    Cada opción trae nombre y DNI si ya se guardaron (o de su última planilla)."""
    cat = OCMovilidadTrabajador.query.all()
    por_user = {t.user_id: t for t in cat if t.user_id and t.activo}
    previo_user = {}
    for uid, nombre, dni in (db.session.query(OrdenCompraMovilidad.trabajador_user_id, OrdenCompraMovilidad.trabajador_nombre, OrdenCompraMovilidad.trabajador_dni)
                             .filter(OrdenCompraMovilidad.trabajador_user_id.isnot(None)).order_by(OrdenCompraMovilidad.id).all()):
        previo_user[uid] = (nombre, dni)
    usuarios = [u for u in User.query.filter(User.desactivado.isnot(True)).order_by(User.nombre_completo).all() if not _mov_rol_fuera(u.role)]
    repetidos = {}
    for u in usuarios:
        k = ' '.join((u.nombre_completo or '').split()).upper()
        repetidos[k] = repetidos.get(k, 0) + 1
    roles = [r for r in MOV_ROLES_ORDEN if r in ROLE_LABELS] + [r for r in ROLE_LABELS if r not in MOV_ROLES_ORDEN]
    grupos, vistos = [], set()

    def opcion(u):
        t = por_user.get(u.id)
        pn, pd = previo_user.get(u.id, (None, None))
        etq = u.nombre_completo + (f" ({u.username})" if repetidos.get(' '.join((u.nombre_completo or '').split()).upper(), 0) > 1 else '')
        return {'v': f'u:{u.id}', 'txt': etq, 'nombre': (t.nombre if t else (pn or u.nombre_completo or '')).upper(), 'dni': (t.dni if t else pd) or '',
                'guardado': bool(t), 'user_id': u.id, 'trab_id': t.id if t else None}
    for rol in roles:
        if _mov_rol_fuera(rol):
            continue
        items = [opcion(u) for u in usuarios if u.role == rol]
        vistos.update(i['user_id'] for i in items)
        if items:
            grupos.append({'label': ROLE_LABELS.get(rol, rol), 'items': items})
    resto = [opcion(u) for u in usuarios if u.id not in vistos]
    if resto:
        grupos.append({'label': 'Otras cuentas', 'items': resto})
    otros = sorted((t for t in cat if t.activo and not t.user_id), key=lambda t: t.nombre)
    if otros:
        grupos.append({'label': 'Otros trabajadores (sin cuenta en el sistema)',
                       'items': [{'v': f't:{t.id}', 'txt': t.nombre + (f' · {t.cargo}' if t.cargo else ''), 'nombre': t.nombre, 'dni': t.dni,
                                  'guardado': True, 'user_id': None, 'trab_id': t.id} for t in otros]})
    return grupos


def _mov_datos_trabajadores():
    usuarios = [{'id': u.id, 'nombre': u.nombre_completo + (f" ({u.username})" if u.username else ''), 'rol': ROLE_LABELS.get(u.role, u.role)}
                for u in User.query.filter(User.desactivado.isnot(True)).order_by(User.nombre_completo).all() if not _mov_rol_fuera(u.role)]
    catalogo = [_mov_trab_json(t) for t in OCMovilidadTrabajador.query.order_by(OCMovilidadTrabajador.activo.desc(), OCMovilidadTrabajador.nombre).all()]
    return {'status': 'success', 'grupos': _mov_opciones_trabajador(), 'catalogo': catalogo, 'usuarios': usuarios}


def _mov_guardar_trabajador(nombre, dni, user_id=None, trab_id=None, cargo=None, quien=''):
    """Crea o actualiza un trabajador guardado. Devuelve (trabajador, None) o (None, error). Sin commit."""
    nombre = ' '.join((nombre or '').split()).upper()[:150]
    dni = re.sub(r'[^0-9A-Za-z]', '', dni or '').upper()[:12]
    if len(nombre) < 5:
        return None, 'Escribe los nombres y apellidos (como en el DNI).'
    if not _mov_dni_valido(dni):
        return None, 'El DNI debe tener 8 dígitos (o el carné de extranjería, de 9 a 12).'
    if user_id:
        u = User.query.get(user_id)
        if not u or _mov_rol_fuera(u.role):
            return None, 'Esa cuenta no se puede usar.'
    t = OCMovilidadTrabajador.query.get(trab_id) if trab_id else None
    if not t and user_id:
        t = OCMovilidadTrabajador.query.filter_by(user_id=user_id).first()
    if not t:
        t = OCMovilidadTrabajador.query.filter_by(dni=dni, user_id=None).first() if not user_id else None
    otro = OCMovilidadTrabajador.query.filter(OCMovilidadTrabajador.dni == dni, OCMovilidadTrabajador.activo.isnot(False)).first()
    if otro and (not t or otro.id != t.id):
        return None, f'Ese DNI ya está guardado para {otro.nombre}.'
    ahora = hora_peru()
    if not t:
        t = OCMovilidadTrabajador(creado_por=quien, fecha_creacion=ahora, activo=True)
        db.session.add(t)
    else:
        t.actualizado_por, t.fecha_actualizacion = quien, ahora
    t.nombre, t.dni, t.activo = nombre, dni, True
    if user_id:
        t.user_id = user_id
    if cargo is not None:
        t.cargo = ' '.join(cargo.split())[:100] or None
    return t, None


@app.route('/ordenes/movilidad/trabajadores')
@_ruta_mov(como_json=True)
def oc_movilidad_trabajadores():
    return _mov_datos_trabajadores()


@app.route('/ordenes/movilidad/trabajador/guardar', methods=['POST'])
@_ruta_mov(como_json=True)
def oc_movilidad_trabajador_guardar():
    """Botón "Guardar para la próxima" del formulario y el formulario del ⚙ (agregar / editar trabajador)."""
    f = request.form
    sel = f.get('sel') or ''
    user_id = f.get('user_id', type=int) or (int(sel[2:]) if sel.startswith('u:') and sel[2:].isdigit() else None)
    trab_id = f.get('id', type=int) or (int(sel[2:]) if sel.startswith('t:') and sel[2:].isdigit() else None)
    t, err = _mov_guardar_trabajador(f.get('nombre'), f.get('dni'), user_id, trab_id, f.get('cargo'), session.get('nombre', ''))
    if err:
        db.session.rollback()
        return {'status': 'error', 'msg': err}
    db.session.commit()
    d = _mov_datos_trabajadores()
    d['v'] = f'u:{t.user_id}' if t.user_id else f't:{t.id}'
    d['msg'] = f'Guardado: {t.nombre} · DNI {t.dni}. La próxima vez se llena solo.'
    return d


@app.route('/ordenes/movilidad/trabajador/<int:trab_id>/activo', methods=['POST'])
@_ruta_mov(como_json=True)
def oc_movilidad_trabajador_activo(trab_id):
    t = OCMovilidadTrabajador.query.get_or_404(trab_id)
    t.activo = not t.activo
    if t.activo:
        otro = OCMovilidadTrabajador.query.filter(OCMovilidadTrabajador.dni == t.dni, OCMovilidadTrabajador.id != t.id,
                                                  OCMovilidadTrabajador.activo.isnot(False)).first()
        if otro:
            db.session.rollback()
            return {'status': 'error', 'msg': f'Ese DNI ya está guardado para {otro.nombre}.'}
    t.actualizado_por, t.fecha_actualizacion = session.get('nombre', ''), hora_peru()
    db.session.commit()
    return _mov_datos_trabajadores()


# ---------------------------- formulario ----------------------------
def _mov_contexto(orden, m=None, previo=None):
    filas = (previo or {}).get('filas') or (_mov_filas(m) if m else [_mov_fila_sugerida(orden)])
    rmv = m.rmv if m and m.rmv else _mov_rmv()
    sel = (previo or {}).get('trabajador_sel')
    if sel is None and m:
        if m.trabajador_user_id:
            sel = f'u:{m.trabajador_user_id}'
        else:
            t = OCMovilidadTrabajador.query.filter_by(dni=m.trabajador_dni, user_id=None).first()
            sel = f't:{t.id}' if t else ''
    return dict(orden=orden, m=m, previo=previo or {}, filas=filas, filas_max=MOV_FILAS_MAX, trab_grupos=_mov_opciones_trabajador(), trab_sel=sel or '',
                motivos=_mov_motivos_previos(), empresas_oc=EMPRESAS_OC,
                rmv=rmv, tope=_mov_tope(rmv), hoy=hora_peru().date(), seccion='lista', base_legal=MOV_BASE_LEGAL, nota_legal=MOV_NOTA,
                siguiente={e: _mov_siguiente_numero(e) for e in EMPRESAS_OC}, codigo_oc=_oc_codigo(orden))


@app.route('/ordenes/<int:orden_id>/movilidad/nueva')
@_ruta_mov()
def oc_movilidad_nueva(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    return render_template('oc_movilidad_form.html', **_mov_contexto(orden))


@app.route('/ordenes/movilidad/<int:mov_id>/editar')
@_ruta_mov()
def oc_movilidad_editar(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    if m.anulada or _mov_firmada(m):
        flash('⛔ ' + ('La planilla está anulada.' if m.anulada else 'La planilla ya está firmada: para corregirla primero quita la firma (queda en el historial).'))
        return redirect(url_for('oc_detalle', orden_id=m.orden_id) + '#movilidad')
    return render_template('oc_movilidad_form.html', **_mov_contexto(m.orden, m))


@app.route('/ordenes/<int:orden_id>/movilidad/guardar', methods=['POST'])
@_ruta_mov()
def oc_movilidad_guardar(orden_id):
    orden = OrdenCompra.query.get_or_404(orden_id)
    f = request.form
    m = OrdenCompraMovilidad.query.get(f.get('mov_id', type=int)) if f.get('mov_id') else None
    if m and m.orden_id != orden.id:
        return "Planilla de otra orden", 400
    if m and (m.anulada or _mov_firmada(m)):
        flash('⛔ La planilla ya está firmada o anulada: no se puede editar.')
        return redirect(url_for('oc_detalle', orden_id=orden.id) + '#movilidad')
    errores = []
    empresa = (f.get('empresa') or orden.empresa or 'ANCLAJES').upper()
    if empresa not in EMPRESAS_OC:
        errores.append('Elige la empresa.')
    elif m and m.empresa != empresa:
        # el N° es correlativo de cada empresa: no se mueve (quedaría un hueco). Se anula y se hace otra en la otra empresa.
        errores.append('La empresa de una planilla ya creada no se cambia (su N° es correlativo de esa empresa). Anúlala y crea otra.')
    try:
        fecha = datetime.strptime(f.get('fecha_gasto') or '', '%Y-%m-%d').date()
        if fecha > hora_peru().date():
            errores.append('La fecha del gasto no puede ser futura.')
        elif fecha < date(2000, 1, 1):
            errores.append('La fecha del gasto no es válida.')
    except ValueError:
        fecha = None
        errores.append('Pon la fecha en que se hizo el gasto.')
    nombre = ' '.join((f.get('trabajador_nombre') or '').split()).upper()[:150]
    dni = re.sub(r'[^0-9A-Za-z]', '', f.get('trabajador_dni') or '').upper()[:12]
    if len(nombre) < 5:
        errores.append('Escribe los nombres y apellidos del trabajador.')
    if not (re.fullmatch(r'\d{8}', dni) or re.fullmatch(r'[0-9A-Z]{9,12}', dni)):
        errores.append('El DNI debe tener 8 dígitos (o el carné de extranjería, de 9 a 12).')
    filas = []
    motivos, destinos, montos = f.getlist('motivo'), f.getlist('destino'), f.getlist('monto')
    for i in range(max(len(motivos), len(destinos), len(montos))):
        mot = ' '.join((motivos[i] if i < len(motivos) else '').split()).upper()[:120]
        des = ' '.join((destinos[i] if i < len(destinos) else '').split()).upper()[:200]
        txt_monto = montos[i] if i < len(montos) else ''
        if not (mot or des or (txt_monto or '').strip()):
            continue
        try:
            monto = _mov_monto(txt_monto)
        except ValueError:
            errores.append(f'Fila {len(filas) + 1}: el monto no es un número válido.')
            monto = None
        if not mot or not des:
            errores.append(f'Fila {len(filas) + 1}: falta el {"motivo" if not mot else "destino"} (SUNAT pide los dos en cada desplazamiento).')
        if monto is None or monto <= 0:
            errores.append(f'Fila {len(filas) + 1}: pon el monto gastado.')
        elif monto > MOV_MONTO_MAX:
            errores.append(f'Fila {len(filas) + 1}: el monto es demasiado alto.')
        filas.append({'motivo': mot, 'destino': des, 'monto': monto})
    if not filas:
        errores.append('Agrega al menos un desplazamiento (motivo, destino y monto).')
    if len(filas) > MOV_FILAS_MAX:
        errores.append(f'Máximo {MOV_FILAS_MAX} desplazamientos por planilla (haz otra planilla).')
    obs = ' '.join((f.get('observacion') or '').split())[:300] or None
    if errores:
        for e in dict.fromkeys(errores):
            flash('⛔ ' + e)
        previo = {'empresa': empresa, 'fecha_gasto': f.get('fecha_gasto'), 'trabajador_nombre': nombre, 'trabajador_dni': dni,
                  'trabajador_sel': f.get('trabajador_sel') or '', 'observacion': obs, 'filas': filas}
        return render_template('oc_movilidad_form.html', **_mov_contexto(orden, m, previo))
    ahora = hora_peru()
    nuevo = m is None
    if nuevo:
        m = OrdenCompraMovilidad(orden_id=orden.id, empresa=empresa, numero=_mov_siguiente_numero(empresa), fecha_emision=ahora,
                                 creado_por_id=session.get('user_id'), fecha_registro=ahora, rmv=_mov_rmv())
        db.session.add(m)
    if not nuevo:
        m.actualizado_por, m.fecha_actualizacion = session.get('nombre', ''), ahora
    m.fecha_gasto, m.periodo = fecha, _mov_periodo(fecha)
    m.trabajador_nombre, m.trabajador_dni = nombre, dni
    sel = f.get('trabajador_sel') or ''
    uid = int(sel[2:]) if sel.startswith('u:') and sel[2:].isdigit() else None
    m.trabajador_user_id = uid if uid and User.query.get(uid) else None
    m.filas = json.dumps(filas, ensure_ascii=False)
    m.total = round(sum(x['monto'] for x in filas), 2)
    m.observacion = obs
    m.orden = orden
    claves = []
    try:
        db.session.flush()
        if not OCMovilidadTrabajador.query.filter(OCMovilidadTrabajador.dni == dni, OCMovilidadTrabajador.activo.isnot(False)).first():
            _mov_guardar_trabajador(nombre, dni, m.trabajador_user_id, None, None, session.get('nombre', ''))
        if f.get('firma_png'):
            _mov_guardar_firma(m, f.get('firma_png'), claves)
        _mov_evento(m, ('creada' if nuevo else 'editada') + f" · {m.trabajador_nombre} (DNI {m.trabajador_dni}) · {m.fecha_gasto.strftime('%d/%m/%Y')}"
                    + f" · S/ {m.total:,.2f}" + (' · firmada en pantalla' if claves else ''))
        registrar_log(f"{'Creó' if nuevo else 'Editó'} la {_mov_codigo(m)} de la {_oc_codigo(orden)} (S/ {m.total:,.2f})", 'bi-taxi-front', 'text-info')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        flash(f'⛔ No se pudo guardar la planilla: {e}')
        return redirect(url_for('oc_detalle', orden_id=orden.id) + '#movilidad')
    tope = _mov_tope_info(m)
    flash(f"✅ {_mov_codigo(m)} {'creada' if nuevo else 'guardada'} (S/ {m.total:,.2f})."
          + ('' if _mov_firmada(m) else ' Falta la firma del trabajador: fírmala en pantalla o imprímela y sube la hoja firmada.'))
    if tope:
        flash(f"⚠️ {m.trabajador_nombre} suma S/ {tope['dia']:,.2f} el {m.fecha_gasto.strftime('%d/%m/%Y')} y el tope deducible es S/ {tope['tope']:,.2f} "
              f"(4% de la RMV): el exceso de S/ {tope['exceso']:,.2f} no se podrá deducir como gasto.")
    return redirect(url_for('oc_detalle', orden_id=orden.id, mov=m.id) + '#movilidad')


# ---------------------------- firma, hoja firmada, anular ----------------------------
@app.route('/ordenes/movilidad/<int:mov_id>/firmar', methods=['POST'])
@_ruta_mov(como_json=True)
def oc_movilidad_firmar(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    if m.anulada:
        return {'status': 'error', 'msg': 'La planilla está anulada.'}
    if m.firma_s3_key:
        return {'status': 'error', 'msg': 'Ya tiene firma. Para cambiarla primero quítala.'}
    claves = []
    try:
        _mov_guardar_firma(m, request.form.get('firma_png'), claves)
        _mov_evento(m, f"firmada en pantalla por el trabajador {m.trabajador_nombre} (registró {session.get('nombre', '')})")
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        return {'status': 'error', 'msg': str(e)}
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3(claves)
        return {'status': 'error', 'msg': f'No se pudo guardar la firma: {e}'}
    return {'status': 'success', 'pdf': url_for('oc_movilidad_pdf', mov_id=m.id, ver=1)}


@app.route('/ordenes/movilidad/<int:mov_id>/hoja', methods=['POST'])
@_ruta_mov()
def oc_movilidad_hoja(mov_id):
    """La planilla impresa y firmada a mano (PDF o foto)."""
    request.max_content_length = LIMITE_PETICION_MOVIMIENTO
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    volver = url_for('oc_detalle', orden_id=m.orden_id, mov=m.id) + '#movilidad'
    if m.anulada:
        flash('⛔ La planilla está anulada.')
        return redirect(volver)
    archivo = request.files.get('archivo')
    ok, info = _validar_documento_kardex(archivo)
    if not ok:
        flash(f'⛔ {info}')
        return redirect(volver)
    ext, mime, _tam = info
    clave = f"ordenes/{m.empresa.lower()}/movilidad/hoja_{m.id}_{uuid.uuid4().hex[:8]}.{ext}"
    viejo = m.escaneo_s3_key
    try:
        archivo.stream.seek(0)
        s3_client.upload_fileobj(archivo.stream, S3_BUCKET_NAME, clave, ExtraArgs={'ContentType': mime})
        m.escaneo_s3_key, m.escaneo_tipo = clave, mime
        m.escaneo_nombre = secure_filename(archivo.filename)[:200] or f'planilla.{ext}'
        m.escaneo_fecha, m.escaneo_por = hora_peru(), session.get('nombre', '')
        _mov_evento(m, ('reemplazó' if viejo else 'subió') + ' la hoja firmada a mano')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _borrar_de_s3([clave])
        flash(f'⛔ No se pudo subir la hoja firmada: {e}')
        return redirect(volver)
    if viejo:
        _borrar_de_s3([viejo])
    flash('✅ Hoja firmada adjuntada. La planilla queda firmada (ya no se edita).')
    return redirect(volver)


@app.route('/ordenes/movilidad/<int:mov_id>/hoja/ver')
@_ruta_mov()
def oc_movilidad_hoja_ver(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    if not m.escaneo_s3_key:
        return "Sin hoja firmada", 404
    obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=m.escaneo_s3_key)
    ext = m.escaneo_s3_key.rsplit('.', 1)[-1].lower()
    resp = send_file(io.BytesIO(obj['Body'].read()), mimetype=m.escaneo_tipo or 'application/octet-stream',
                     as_attachment=request.args.get('download') == '1',
                     download_name=f"movilidad_{m.empresa.lower()}_{_mov_numero_txt(m)}_firmada.{ext}")
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@app.route('/ordenes/movilidad/<int:mov_id>/firma.png')
@_ruta_mov()
def oc_movilidad_firma(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    if not m.firma_s3_key:
        return "Sin firma", 404
    obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=m.firma_s3_key)
    return send_file(io.BytesIO(obj['Body'].read()), mimetype='image/png')


@app.route('/ordenes/movilidad/<int:mov_id>/quitar_firma', methods=['POST'])
@_ruta_mov(ROLES_MOV_ANULAN)
def oc_movilidad_quitar_firma(mov_id):
    """Para corregir una planilla firmada: se quita la firma (y la hoja firmada) con motivo; queda en el historial."""
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    volver = url_for('oc_detalle', orden_id=m.orden_id, mov=m.id) + '#movilidad'
    motivo = ' '.join((request.form.get('motivo') or '').split())[:200]
    if len(motivo) < 5:
        flash('⛔ Escribe por qué se quita la firma (mínimo 5 letras).')
        return redirect(volver)
    claves = [k for k in (m.firma_s3_key, m.escaneo_s3_key) if k]
    if not claves:
        flash('La planilla no tiene firma.')
        return redirect(volver)
    m.firma_s3_key = m.firma_fecha = m.firma_por = None
    m.escaneo_s3_key = m.escaneo_tipo = m.escaneo_nombre = m.escaneo_fecha = m.escaneo_por = None
    _mov_evento(m, f"se QUITÓ la firma para corregirla: {motivo}")
    registrar_log(f"Quitó la firma de la {_mov_codigo(m)}: {motivo}", 'bi-eraser', 'text-warning')
    db.session.commit()
    _borrar_de_s3(claves)
    flash('Firma quitada: ya puedes editar la planilla. Al terminar, vuelve a firmarla.')
    return redirect(volver)


@app.route('/ordenes/movilidad/<int:mov_id>/anular', methods=['POST'])
@_ruta_mov(ROLES_MOV_ANULAN)
def oc_movilidad_anular(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    volver = url_for('oc_detalle', orden_id=m.orden_id) + '#movilidad'
    motivo = ' '.join((request.form.get('motivo') or '').split())[:300]
    if m.anulada:
        flash('La planilla ya estaba anulada.')
        return redirect(volver)
    if len(motivo) < 5:
        flash('⛔ Escribe el motivo de la anulación (mínimo 5 letras).')
        return redirect(volver)
    m.anulada, m.anulada_motivo, m.anulada_por, m.fecha_anulada = True, motivo, session.get('nombre', ''), hora_peru()
    _mov_evento(m, f"ANULADA: {motivo}")
    registrar_log(f"Anuló la {_mov_codigo(m)}: {motivo}", 'bi-x-octagon', 'text-danger')
    db.session.commit()
    flash(f'{_mov_codigo(m)} anulada. El número no se vuelve a usar.')
    return redirect(volver)


@app.route('/ordenes/movilidad/rmv', methods=['POST'])
@_ruta_mov(['admin'])
def oc_movilidad_rmv():
    volver = _volver_seguro(request.form.get('volver'), url_for('oc_movilidad_lista'))
    try:
        v = round(float((request.form.get('rmv') or '').replace(',', '.')), 2)
        if not 500 <= v <= 20000:
            raise ValueError
    except ValueError:
        flash('⛔ Escribe la RMV en soles (ej. 1230).')
        return redirect(volver)
    c = OCConfig.query.get('MOV_RMV') or OCConfig(clave='MOV_RMV')
    c.valor, c.actualizado_por, c.fecha = str(v), session.get('nombre', ''), hora_peru()
    db.session.add(c)
    registrar_log(f"Cambió la RMV para el tope de movilidad a S/ {v:,.2f}", 'bi-gear', 'text-info')
    db.session.commit()
    flash(f'✅ RMV actualizada a S/ {v:,.2f}: el tope diario por trabajador queda en S/ {_mov_tope(v):,.2f} (para las planillas nuevas).')
    return redirect(volver)


@app.route('/ordenes/movilidad/dni', methods=['POST'])
@_ruta_mov(como_json=True)
def oc_movilidad_dni():
    """Nombre del trabajador: primero de planillas anteriores; si no, RENIEC (mismo servicio de SUNAT del sistema)."""
    dni = re.sub(r'\D', '', request.form.get('dni') or '')
    if len(dni) != 8:
        return {'status': 'error', 'msg': 'El DNI tiene 8 dígitos.'}
    previo = OrdenCompraMovilidad.query.filter_by(trabajador_dni=dni).order_by(OrdenCompraMovilidad.id.desc()).first()
    if previo:
        return {'status': 'success', 'nombre': previo.trabajador_nombre, 'origen': 'planillas anteriores'}
    datos, err = _sunat_consulta_externa(dni)
    if err or not datos:
        return {'status': 'error', 'msg': err or 'DNI no encontrado.'}
    return {'status': 'success', 'nombre': ' '.join(datos['razon_social'].split()).upper(), 'origen': 'RENIEC'}


# ---------------------------- PDF ----------------------------
def _mov_contexto_pdf(m):
    firma = None
    if m.firma_s3_key:
        try:
            obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=m.firma_s3_key)
            firma = _imagen_pdf(obj['Body'].read(), 52, 190, recortar=True)
        except Exception:
            app.logger.exception("No se pudo leer la firma de la planilla de movilidad %s", m.id)
    filas = _mov_filas(m)
    return {'m': m, 'o': m.orden, 'cfg': _oc_cfg(m.empresa), 'logo': _logo_pdf_insumos(m.empresa), 'firma': firma, 'filas': filas,
            'vacias': max(0, 8 - len(filas)), 'numero': _mov_numero_txt(m), 'letras': _monto_en_letras(m.total or 0, 'PEN'),
            'tema': TEMAS_PDF_OC.get(m.empresa, TEMAS_PDF_OC['ANCLAJES']), 'codigo_oc': _oc_codigo(m.orden),
            'base_legal': MOV_BASE_LEGAL, 'nota_legal': MOV_NOTA, 'registro': m.creado_por.nombre_completo if m.creado_por else ''}


def _mov_nombre_pdf(m):
    return f"Movilidad_{secure_filename(m.empresa.title())}_{_mov_numero_txt(m)}_{secure_filename(m.trabajador_nombre)[:25]}_{m.fecha_gasto.strftime('%Y%m%d')}.pdf"


@app.route('/ordenes/movilidad/<int:mov_id>/pdf')
@_ruta_mov()
def oc_movilidad_pdf(mov_id):
    m = OrdenCompraMovilidad.query.get_or_404(mov_id)
    html_pdf = render_template('pdf_movilidad.html', planillas=[_mov_contexto_pdf(m)])
    nombre = _mov_nombre_pdf(m)
    resp = _generar_respuesta_pdf(html_pdf, nombre, 'la planilla de movilidad')
    if request.args.get('ver') == '1' and not isinstance(resp, tuple):
        resp.headers['Content-Disposition'] = f'inline; filename="{nombre}"'
    return resp


# ---------------------------- LISTA (para contabilidad: todas las planillas del mes) ----------------------------
@app.route('/ordenes/movilidad')
@_ruta_mov()
def oc_movilidad_lista():
    hoy = hora_peru().date()
    a = request.args
    empresa = (a.get('empresa') or session.get('oc_empresa') or 'ANCLAJES').upper()
    empresa = empresa if empresa in EMPRESAS_OC or empresa == 'TODAS' else 'ANCLAJES'
    mes = a.get('mes') or hoy.strftime('%Y-%m')
    try:
        ini = datetime.strptime(mes + '-01', '%Y-%m-%d').date()
    except ValueError:
        ini = hoy.replace(day=1)
    fin = (ini.replace(day=28) + timedelta(days=4)).replace(day=1)
    q = OrdenCompraMovilidad.query.filter(OrdenCompraMovilidad.fecha_gasto >= ini, OrdenCompraMovilidad.fecha_gasto < fin)
    if empresa != 'TODAS':
        q = q.filter(OrdenCompraMovilidad.empresa == empresa)
    estado = a.get('estado', '')
    buscar = ' '.join((a.get('q') or '').split()).upper()
    lista = []
    for m in q.order_by(OrdenCompraMovilidad.fecha_gasto, OrdenCompraMovilidad.empresa, OrdenCompraMovilidad.numero).all():
        if estado == 'sin_firma' and (m.anulada or _mov_firmada(m)):
            continue
        if estado == 'firmadas' and (m.anulada or not _mov_firmada(m)):
            continue
        if estado == 'anuladas' and not m.anulada:
            continue
        if buscar and buscar not in f"{m.trabajador_nombre} {m.trabajador_dni} {_oc_codigo(m.orden)} {m.orden.razon_social} {m.filas}".upper():
            continue
        lista.append(m)
    vigentes = [m for m in lista if not m.anulada]
    # tope diario por trabajador (4% RMV) para avisar el exceso
    por_dia = {}
    for m in vigentes:
        k = (m.empresa, m.trabajador_dni, m.fecha_gasto)
        por_dia[k] = round(por_dia.get(k, 0) + (m.total or 0), 2)
    excesos = {k: v for k, v in por_dia.items() if v > _mov_tope() + 1e-9}
    por_trab = {}
    for m in vigentes:
        t = por_trab.setdefault(m.trabajador_dni, {'nombre': m.trabajador_nombre, 'dni': m.trabajador_dni, 'n': 0, 'total': 0.0, 'dias': set()})
        t['n'] += 1
        t['total'] = round(t['total'] + (m.total or 0), 2)
        t['dias'].add(m.fecha_gasto)
    if a.get('pdf') == '1':
        if not vigentes:
            flash('No hay planillas vigentes en ese mes para juntar en un PDF.')
            return redirect(url_for('oc_movilidad_lista', empresa=empresa, mes=mes))
        html_pdf = render_template('pdf_movilidad.html', planillas=[_mov_contexto_pdf(m) for m in vigentes])
        nombre = f"Movilidad_{empresa.title()}_{ini.strftime('%Y-%m')}.pdf"
        resp = _generar_respuesta_pdf(html_pdf, nombre, 'las planillas de movilidad del mes')
        if a.get('ver') == '1' and not isinstance(resp, tuple):
            resp.headers['Content-Disposition'] = f'inline; filename="{nombre}"'
        return resp
    meses = []
    d = hoy.replace(day=1)
    for _ in range(18):
        meses.append((d.strftime('%Y-%m'), f"{MOV_MESES[d.month - 1].title()} {d.year}"))
        d = (d - timedelta(days=1)).replace(day=1)
    return render_template('oc_movilidad_lista.html', lista=lista, empresa=empresa, mes=ini.strftime('%Y-%m'), meses=meses, estado=estado, buscar=buscar,
                           total=round(sum(m.total or 0 for m in vigentes), 2), n_vigentes=len(vigentes),
                           n_sin_firma=sum(1 for m in vigentes if not _mov_firmada(m)), excesos=excesos,
                           por_trab=sorted(por_trab.values(), key=lambda t: -t['total']), rmv=_mov_rmv(), tope=_mov_tope(),
                           empresas_oc=EMPRESAS_OC, seccion='movilidad', periodo=f"{MOV_MESES[ini.month - 1].title()} {ini.year}",
                           conteo_vaciar=_mov_conteo_vaciar() if session.get('role') == 'admin' else {})


# ---------------------------- VACIAR (pruebas) ----------------------------
def _mov_conteo_vaciar():
    """Cuántas planillas hay por empresa (todas las fechas), para la zona de pruebas."""
    try:
        res = {e: 0 for e in EMPRESAS_OC}
        for (emp,) in db.session.query(OrdenCompraMovilidad.empresa).all():
            res[emp] = res.get(emp, 0) + 1
        res['TODAS'] = sum(res.values())
        return res
    except Exception:
        db.session.rollback()
        return {}


def _mov_vaciar(empresa='TODAS'):
    """Borra las planillas (de una empresa o de todas), sus firmas/hojas en S3 y sus líneas del historial de las órdenes.
    No toca nada más (órdenes, documentos, RMV configurada). La numeración vuelve a empezar en 00-00001.
    Devuelve (n_planillas, claves_s3) SIN commit."""
    q = OrdenCompraMovilidad.query
    if empresa != 'TODAS':
        q = q.filter(OrdenCompraMovilidad.empresa == empresa)
    lista = q.all()
    claves = [k for m in lista for k in (m.firma_s3_key, m.escaneo_s3_key) if k]
    ordenes = {m.orden_id for m in lista}
    if ordenes:
        ev = OrdenCompraEvento.query.filter(OrdenCompraEvento.orden_id.in_(list(ordenes)), OrdenCompraEvento.accion == 'MOVILIDAD')
        if empresa != 'TODAS':
            ev = ev.filter(OrdenCompraEvento.detalle.like(f"%({EMPRESAS_OC[empresa]['corto']}):%"))
        ev.delete(synchronize_session=False)
    for m in lista:
        db.session.delete(m)
    return len(lista), claves


@app.route('/ordenes/movilidad/vaciar', methods=['POST'])
@_ruta_mov(['admin'])
def oc_movilidad_vaciar():
    """ZONA DE PRUEBAS: deja limpio solo el apartado de planillas de movilidad para empezar con datos reales."""
    f = request.form
    volver = url_for('oc_movilidad_lista', empresa=f.get('volver_empresa') or 'TODAS')
    empresa = (f.get('empresa') or 'TODAS').upper()
    if empresa != 'TODAS' and empresa not in EMPRESAS_OC:
        flash('⛔ Elige la empresa.')
        return redirect(volver)
    if (f.get('confirmacion') or '').strip().upper() != 'BORRAR MOVILIDAD':
        flash('⛔ Escribe BORRAR MOVILIDAD para confirmar.')
        return redirect(volver)
    try:
        n, claves = _mov_vaciar(empresa)
        txt = 'las dos empresas' if empresa == 'TODAS' else EMPRESAS_OC[empresa]['corto']
        registrar_log(f"VACIÓ las planillas de movilidad ({txt}): {n} planilla(s), {len(claves)} archivo(s) de firma", 'bi-trash3-fill', 'text-danger')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo vaciar las planillas de movilidad")
        flash(f'⛔ No se pudo vaciar (no se borró nada): {e}')
        return redirect(volver)
    _borrar_de_s3(claves)
    flash(f"✅ Planillas de movilidad vaciadas ({txt}): {n} planilla(s) y {len(claves)} archivo(s) de firma borrados. "
          "La numeración vuelve a empezar en N° 00-00001. Las órdenes y sus documentos no se tocaron.")
    return redirect(volver)
