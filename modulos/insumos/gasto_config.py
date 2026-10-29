# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# INSUMOS INTERNOS · gasto, configuración y mantenimiento
# gasto por área, configuración (áreas, trabajadores, categorías), ajuste del costo promedio y vaciar el módulo
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================

# ---------------------------- GASTO POR ÁREA ----------------------------
MESES_CORTOS_INSUMOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic']


@app.route('/insumos/gasto')
@_ruta_insumos()
def insumos_gasto():
    ahora = hora_peru()
    empresa = request.args.get('empresa', 'AMBAS')
    hasta = _fecha_param('hasta', ahora.date())
    desde = _fecha_param('desde', ahora.date().replace(day=1))
    if desde > hasta:
        desde, hasta = hasta, desde
    ini = datetime.combine(desde, datetime.min.time())
    fin = datetime.combine(hasta, datetime.min.time()) + timedelta(days=1)

    categoria = request.args.get('categoria', '')

    def en_cat(d):
        return not categoria or (d.insumo.categoria or '') == categoria

    def salidas_entre(a, b):
        """Salidas no anuladas del rango con su monto (solo lo de la categoría elegida, si hay filtro)."""
        q = InsumoSalida.query.filter(InsumoSalida.estado == 'REGISTRADA', InsumoSalida.fecha >= a, InsumoSalida.fecha < b)
        if empresa in EMPRESAS_INSUMOS:
            q = q.filter(InsumoSalida.empresa == empresa)
        res = []
        for s in q.all():
            # soles y dólares por separado (lo comprado en US$ se gasta en US$: no se convierte)
            monto = (s.total_costo or 0) if not categoria else sum(d.costo_total or 0 for d in s.detalles if en_cat(d))
            monto_usd = (s.total_costo_usd or 0) if not categoria else sum(d.costo_total_usd or 0 for d in s.detalles if en_cat(d))
            if not categoria or any(en_cat(d) for d in s.detalles):
                res.append((s, monto, monto_usd))
        return res
    salidas = salidas_entre(ini, fin)
    total = sum(m for _, m, _u in salidas)
    total_usd = sum(u for _, _m, u in salidas)
    areas, personas, insumos, cats = {}, {}, {}, {}
    for s, monto, monto_usd in salidas:
        a = areas.setdefault(s.area_id, {'id': s.area_id, 'nombre': s.area.nombre if s.area else 'Sin área', 'total': 0, 'total_usd': 0, 'salidas': 0,
                                         'anclajes': 0, 'importbolts': 0, 'anclajes_usd': 0, 'importbolts_usd': 0})
        a['total'] += monto
        a['total_usd'] += monto_usd
        a['salidas'] += 1
        a['anclajes' if s.empresa == 'ANCLAJES' else 'importbolts'] += monto
        a[('anclajes' if s.empresa == 'ANCLAJES' else 'importbolts') + '_usd'] += monto_usd
        quien = s.a_cuenta_de or s.solicitado_por
        if quien:
            p = personas.setdefault(quien.id, {'id': quien.id, 'nombre': quien.nombre, 'area': quien.area.nombre if quien.area else '',
                                               'total': 0, 'total_usd': 0, 'salidas': 0})
            p['total'] += monto
            p['total_usd'] += monto_usd
            p['salidas'] += 1
        for d in s.detalles:
            if not en_cat(d):
                continue
            i = insumos.setdefault(d.insumo_id, {'codigo': d.insumo.codigo, 'descripcion': d.insumo.descripcion,
                                                 'unidad': d.unidad or d.insumo.unidad, 'cantidad': 0, 'total': 0, 'total_usd': 0})
            i['cantidad'] += d.cantidad_despachada or 0
            i['total'] += d.costo_total or 0
            i['total_usd'] += d.costo_total_usd or 0
            c = cats.setdefault(d.insumo.categoria or 'Sin categoría', {'nombre': d.insumo.categoria or 'Sin categoría', 'total': 0, 'total_usd': 0, 'items': 0})
            c['total'] += d.costo_total or 0
            c['total_usd'] += d.costo_total_usd or 0
            c['items'] += 1
    # % y barras por moneda (no se suman soles con dólares)
    lista_areas = sorted(areas.values(), key=lambda a: (-a['total'], -a['total_usd']))
    maximo = max([a['total'] for a in lista_areas] + [0]) or 1
    maximo_usd = max([a['total_usd'] for a in lista_areas] + [0]) or 1
    for a in lista_areas:
        a['pct'] = round(100 * a['total'] / total, 1) if total else 0
        a['pct_usd'] = round(100 * a['total_usd'] / total_usd, 1) if total_usd else 0
        a['barra'] = round(100 * a['total'] / maximo)
        a['barra_usd'] = round(100 * a['total_usd'] / maximo_usd)
    lista_cats = sorted(cats.values(), key=lambda c: (-c['total'], -c['total_usd']))
    total_cats = sum(c['total'] for c in lista_cats) or 1
    total_cats_usd = sum(c['total_usd'] for c in lista_cats) or 1
    for c in lista_cats:
        c['pct'] = round(100 * c['total'] / total_cats, 1)
        c['pct_usd'] = round(100 * c['total_usd'] / total_cats_usd, 1)
    # Últimos 6 meses (hasta el mes de "hasta"), por área
    meses = []
    y, m = hasta.year, hasta.month
    for _ in range(6):
        meses.insert(0, (y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    ini6 = datetime(meses[0][0], meses[0][1], 1)
    fin6 = datetime(hasta.year + (hasta.month == 12), hasta.month % 12 + 1, 1)
    matriz, matriz_usd = {}, {}
    for s, monto, monto_usd in salidas_entre(ini6, fin6):
        nombre = s.area.nombre if s.area else 'Sin área'
        clave = (s.fecha.year, s.fecha.month)
        fila = matriz.setdefault(nombre, {})
        fila[clave] = fila.get(clave, 0) + monto
        fu = matriz_usd.setdefault(nombre, {})
        fu[clave] = fu.get(clave, 0) + monto_usd
    mensual = sorted(({'area': k, 'meses': [v.get(mm, 0) for mm in meses], 'total': sum(v.values()),
                       'meses_usd': [matriz_usd.get(k, {}).get(mm, 0) for mm in meses], 'total_usd': sum(matriz_usd.get(k, {}).values())}
                      for k, v in matriz.items()), key=lambda r: (-r['total'], -r['total_usd']))
    max_celda = max([x for r in mensual for x in r['meses']] + [0]) or 1
    return render_template('insumos_gasto.html', empresa=empresa, empresas=EMPRESAS_INSUMOS, desde=desde, hasta=hasta, total=total, total_usd=total_usd,
                           n_salidas=len(salidas), areas=lista_areas, personas=sorted(personas.values(), key=lambda p: (-p['total'], -p['total_usd']))[:15],
                           insumos=sorted(insumos.values(), key=lambda i: (-i['total'], -i['total_usd']))[:15], mensual=mensual, max_celda=max_celda,
                           categoria=categoria, categorias_filtro=_categorias_insumos(), por_categoria=lista_cats,
                           meses=[f"{MESES_CORTOS_INSUMOS[mm - 1]} {str(yy)[2:]}" for yy, mm in meses], seccion='gasto')


# ---------------------------- CONFIGURACIÓN ----------------------------
@app.route('/insumos/config')
@_ruta_insumos(editar=True)
def insumos_config():
    formato = {}
    for e in EMPRESAS_INSUMOS:
        for k, v in FORMATO_SALIDA_DEF.items():
            cfg = SystemConfig.query.get(f'insumos_formato_{k}_{e}')
            formato[f'{k}_{e}'] = cfg.value if cfg else v
    # Cuánto se usa cada cosa (para avisar antes de borrar)
    uso_trab, uso_area = {}, {}
    for sal in InsumoSalida.query.all():
        for tid in {sal.solicitado_por_id, sal.recibido_por_id, sal.autorizado_por_id, sal.a_cuenta_de_id} - {None}:
            uso_trab[tid] = uso_trab.get(tid, 0) + 1
        if sal.area_id:
            uso_area[sal.area_id] = uso_area.get(sal.area_id, 0) + 1
    compras = {}
    for ing in InsumoIngreso.query.filter(InsumoIngreso.insumo_proveedor_id.isnot(None)).all():
        compras[ing.insumo_proveedor_id] = compras.get(ing.insumo_proveedor_id, 0) + 1
    proveedores = sorted(InsumoProveedor.query.all(), key=lambda p: _clave_alfabetica(p.razon_social or ''))
    es_admin = session.get('role') == 'admin'
    conteo_vaciar = None
    if es_admin:
        conteo_vaciar = {'ingresos': InsumoIngreso.query.count(), 'salidas': InsumoSalida.query.count(),
                         'movimientos': InsumoMovimiento.query.count(), 'documentos': InsumoDocumento.query.count(),
                         'firmas': InsumoSalida.query.filter(InsumoSalida.firma_s3_key.isnot(None)).count(),
                         'insumos': Insumo.query.count(), 'proveedores': InsumoProveedor.query.count(),
                         'trabajadores': InsumoTrabajador.query.count(), 'areas': InsumoArea.query.count(),
                         'stocks': InsumoStock.query.count()}
    return render_template('insumos_config.html', areas=InsumoArea.query.order_by(InsumoArea.nombre).all(),
                           trabajadores=InsumoTrabajador.query.order_by(InsumoTrabajador.activo.desc(), InsumoTrabajador.nombre).all(),
                           catalogos={t: _catalogo_insumos(t, incluir_inactivos=True) for t in CATALOGOS_INSUMOS},
                           nombres_catalogo=CATALOGOS_INSUMOS, formato=formato, formato_def=FORMATO_SALIDA_DEF, empresas=EMPRESAS_INSUMOS,
                           uso_trab=uso_trab, uso_area=uso_area, proveedores=proveedores, compras=compras,
                           es_admin=es_admin, conteo_vaciar=conteo_vaciar,
                           tab=request.args.get('tab', 'trabajadores'), seccion='config')


def _uso_area(area_id):
    return InsumoSalida.query.filter_by(area_id=area_id).count() + InsumoMovimiento.query.filter_by(area_id=area_id).count()


@app.route('/insumos/config/area', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_config_area():
    area_id = request.form.get('id', type=int)
    accion = request.form.get('accion')
    if accion == 'toggle':
        a = InsumoArea.query.get_or_404(area_id)
        a.activo = not a.activo
        db.session.commit()
        return {'status': 'success', 'activo': a.activo}
    if accion == 'borrar':
        a = InsumoArea.query.get_or_404(area_id)
        n = InsumoSalida.query.filter_by(area_id=a.id).count()
        if n or InsumoMovimiento.query.filter_by(area_id=a.id).count():
            return {'status': 'error', 'msg': f'El área {a.nombre} tiene {n} salida(s) registradas: si se borra, se perdería a quién se cargó ese gasto. '
                                              f'Desactívala (deja de aparecer para elegir) o renómbrala.'}
        InsumoTrabajador.query.filter_by(area_id=a.id).update({'area_id': None})
        registrar_log(f"Borró el área de insumos {a.nombre}", 'bi-trash', 'text-danger')
        db.session.delete(a)
        db.session.commit()
        return {'status': 'success'}
    nombre = ' '.join((request.form.get('nombre') or '').split()).upper()[:100]
    if len(nombre) < 2:
        return {'status': 'error', 'msg': 'Escribe el nombre del área.'}
    if InsumoArea.query.filter(func.upper(InsumoArea.nombre) == nombre, InsumoArea.id != (area_id or 0)).first():
        return {'status': 'error', 'msg': f'El área {nombre} ya existe.'}
    if area_id:
        InsumoArea.query.get_or_404(area_id).nombre = nombre
    else:
        db.session.add(InsumoArea(nombre=nombre, activo=True))
    db.session.commit()
    return {'status': 'success'}


@app.route('/insumos/config/trabajador', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_config_trabajador():
    f = request.form
    tid = f.get('id', type=int)
    accion = f.get('accion')
    if accion in ('toggle', 'jefe'):
        t = InsumoTrabajador.query.get_or_404(tid)
        if accion == 'toggle':
            t.activo = not t.activo
        else:
            t.es_jefe = not t.es_jefe
            registrar_log(f"{'Marcó' if t.es_jefe else 'Quitó'} a {t.nombre} como jefe de área (insumos)", 'bi-person-badge', 'text-info')
        db.session.commit()
        return {'status': 'success', 'activo': t.activo, 'es_jefe': t.es_jefe}
    if accion == 'borrar':
        t = InsumoTrabajador.query.get_or_404(tid)
        n = InsumoSalida.query.filter(or_(InsumoSalida.solicitado_por_id == t.id, InsumoSalida.recibido_por_id == t.id,
                                          InsumoSalida.autorizado_por_id == t.id, InsumoSalida.a_cuenta_de_id == t.id)).count()
        if n:
            return {'status': 'error', 'msg': f'{t.nombre} figura en {n} salida(s) (solicitó, recibió, autorizó o fue a su cuenta): '
                                              f'si se borra, esas salidas quedarían sin nombre. Desactívalo para que ya no aparezca.'}
        registrar_log(f"Borró al trabajador de insumos {t.nombre}", 'bi-trash', 'text-danger')
        db.session.delete(t)
        db.session.commit()
        return {'status': 'success'}
    nombre = ' '.join((f.get('nombre') or '').split()).title()[:150]
    if len(nombre) < 3:
        return {'status': 'error', 'msg': 'Escribe el nombre del trabajador.'}
    area = InsumoArea.query.get(f.get('area_id', type=int)) if f.get('area_id', type=int) else None
    empresa = (f.get('empresa') or 'AMBAS').upper()
    t = InsumoTrabajador.query.get_or_404(tid) if tid else InsumoTrabajador(activo=True)
    t.nombre, t.codigo, t.cargo = nombre, ' '.join((f.get('codigo') or '').split())[:30] or None, ' '.join((f.get('cargo') or '').split())[:100] or None
    t.area_id = area.id if area else None
    t.empresa = empresa if empresa in ('ANCLAJES', 'IMPORTBOLTS', 'AMBAS') else 'AMBAS'
    t.es_jefe = f.get('es_jefe') == '1'
    if not tid:
        db.session.add(t)
    db.session.commit()
    return {'status': 'success'}


def _cambiar_valor_catalogo_insumos(tipo, antes, despues):
    """Al renombrar un valor del catálogo, se actualiza donde ya se usaba. Devuelve cuántos registros cambió."""
    cambios = 0
    if tipo == 'INSUMO_CATEGORIA':
        cambios += Insumo.query.filter(Insumo.categoria == antes).update({'categoria': despues}, synchronize_session=False)
    elif tipo == 'INSUMO_UNIDAD':
        cambios += Insumo.query.filter(Insumo.unidad == antes).update({'unidad': despues}, synchronize_session=False)
    elif tipo == 'INSUMO_MOTIVO':
        cambios += InsumoSalida.query.filter(InsumoSalida.motivo == antes).update({'motivo': despues}, synchronize_session=False)
    elif tipo == 'INSUMO_ALMACEN':
        cambios += InsumoStock.query.filter(InsumoStock.almacen == antes).update({'almacen': despues}, synchronize_session=False)
        cambios += InsumoIngreso.query.filter(InsumoIngreso.almacen == antes).update({'almacen': despues}, synchronize_session=False)
        cambios += InsumoSalidaDetalle.query.filter(InsumoSalidaDetalle.ubicacion == antes).update({'ubicacion': despues}, synchronize_session=False)
    return cambios


@app.route('/insumos/config/catalogo', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_config_catalogo():
    f = request.form
    accion = f.get('accion')
    if accion in ('toggle', 'editar', 'borrar'):
        v = CatalogoValor.query.get_or_404(f.get('id', type=int))
        if v.tipo not in CATALOGOS_INSUMOS:
            return {'status': 'error', 'msg': 'No autorizado'}, 403
        if accion == 'toggle':
            v.activo = not v.activo
            db.session.commit()
            return {'status': 'success', 'activo': v.activo}
        if accion == 'editar':
            nuevo = ' '.join((f.get('valor') or '').split()).upper()[:100]
            if not nuevo:
                return {'status': 'error', 'msg': 'Escribe el nuevo nombre.'}
            if any(x.id != v.id and ' '.join((x.valor or '').split()).upper() == nuevo for x in CatalogoValor.query.filter_by(tipo=v.tipo).all()):
                return {'status': 'error', 'msg': f'"{nuevo}" ya existe.'}
            antes = v.valor
            v.valor = nuevo
            n = _cambiar_valor_catalogo_insumos(v.tipo, antes, nuevo)
            registrar_log(f"Renombró en {CATALOGOS_INSUMOS[v.tipo]} (insumos): {antes} → {nuevo} ({n} registro(s) actualizados)", 'bi-pencil', 'text-warning')
            db.session.commit()
            return {'status': 'success', 'msg': f'Actualizado también en {n} registro(s).' if n else ''}
        # borrar
        if v.tipo == 'INSUMO_UNIDAD':
            n = Insumo.query.filter(Insumo.unidad == v.valor).count()
            if n:
                return {'status': 'error', 'msg': f'La unidad {v.valor} la usan {n} insumo(s) del maestro (la unidad es obligatoria). '
                                                  f'Cámbiales la unidad primero, o renómbrala / desactívala.'}
        if v.tipo == 'INSUMO_CATEGORIA':
            n = Insumo.query.filter(Insumo.categoria == v.valor).count()
            if n and f.get('forzar') != '1':
                return {'status': 'confirmar', 'msg': f'La categoría {v.valor} la usan {n} insumo(s). Si la borras, esos insumos quedarán '
                                                      f'"sin categoría". ¿Borrar igual?'}
            Insumo.query.filter(Insumo.categoria == v.valor).update({'categoria': None}, synchronize_session=False)
        registrar_log(f"Borró de {CATALOGOS_INSUMOS[v.tipo]} (insumos): {v.valor}", 'bi-trash', 'text-danger')
        db.session.delete(v)
        db.session.commit()
        return {'status': 'success'}
    tipo = (f.get('tipo') or '').upper()
    valor = ' '.join((f.get('valor') or '').split()).upper()[:100]
    if tipo not in CATALOGOS_INSUMOS or not valor:
        return {'status': 'error', 'msg': 'Escribe un valor.'}
    if any(' '.join((x.valor or '').split()).upper() == valor for x in CatalogoValor.query.filter_by(tipo=tipo).all()):
        return {'status': 'error', 'msg': f'"{valor}" ya existe.'}
    db.session.add(CatalogoValor(tipo=tipo, valor=valor, activo=True, es_predeterminado=False, creado_por_id=session.get('user_id')))
    db.session.commit()
    return {'status': 'success'}


@app.route('/insumos/config/proveedor', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_config_proveedor():
    f = request.form
    p = InsumoProveedor.query.get_or_404(f.get('id', type=int)) if f.get('id', type=int) else None
    if f.get('accion') == 'borrar':
        if not p:
            return {'status': 'error', 'msg': 'No existe.'}
        InsumoIngreso.query.filter(InsumoIngreso.insumo_proveedor_id == p.id).update({'insumo_proveedor_id': None}, synchronize_session=False)
        registrar_log(f"Borró el proveedor de insumos {p.razon_social}", 'bi-trash', 'text-danger')
        db.session.delete(p)
        db.session.commit()
        return {'status': 'success'}
    razon = _limpio(f.get('razon_social'), 200)
    ruc = re.sub(r'\D', '', f.get('ruc') or '')[:20]
    if len(razon) < 3:
        return {'status': 'error', 'msg': 'Escribe el nombre / razón social.'}
    if ruc and len(ruc) not in (8, 11):
        return {'status': 'error', 'msg': 'El RUC debe tener 11 dígitos (o 8 si es DNI). Déjalo vacío si no tiene.'}
    if ruc and InsumoProveedor.query.filter(InsumoProveedor.ruc == ruc, InsumoProveedor.id != (p.id if p else 0)).first():
        return {'status': 'error', 'msg': f'Ya hay un proveedor guardado con el RUC/DNI {ruc}.'}
    nuevo = p is None
    if nuevo:
        p = InsumoProveedor(creado_por=session.get('nombre', ''), fecha_creacion=hora_peru())
        db.session.add(p)
    else:
        p.actualizado_por, p.fecha_actualizacion = session.get('nombre', ''), hora_peru()
    p.ruc, p.razon_social = ruc or None, razon
    p.direccion = _limpio(f.get('direccion'), 250) or None
    p.contacto_nombre = _limpio(f.get('contacto_nombre'), 120) or None
    p.contacto_telefono = _limpio(f.get('contacto_telefono'), 40) or None
    registrar_log(f"{'Creó' if nuevo else 'Editó'} el proveedor de insumos {razon}", 'bi-building', 'text-info')
    db.session.commit()
    return {'status': 'success'}


@app.route('/insumos/config/formato', methods=['POST'])
@_ruta_insumos(editar=True)
def insumos_config_formato():
    if request.form.get('accion') == 'restablecer':
        for e in EMPRESAS_INSUMOS:
            for k in FORMATO_SALIDA_DEF:
                cfg = SystemConfig.query.get(f'insumos_formato_{k}_{e}')
                if cfg:
                    db.session.delete(cfg)
        db.session.commit()
        flash('✅ Formato del PDF restablecido a los valores iniciales.')
        return redirect(url_for('insumos_config', tab='formato'))
    for e in EMPRESAS_INSUMOS:
        for k in FORMATO_SALIDA_DEF:
            valor = ' '.join((request.form.get(f'{k}_{e}') or '').split())[:30]
            if not valor:
                continue
            clave = f'insumos_formato_{k}_{e}'
            cfg = SystemConfig.query.get(clave)
            if cfg:
                cfg.value = valor
            else:
                db.session.add(SystemConfig(key=clave, value=valor, updated_by=session.get('username', '')))
    db.session.commit()
    flash('✅ Formato del PDF guardado.')
    return redirect(url_for('insumos_config', tab='formato'))


# ---------------------------- AJUSTE DEL COSTO PROMEDIO (con auditoría) ----------------------------
@app.route('/insumos/stock/<int:insumo_id>/<empresa>/costo', methods=['POST'])
@_ruta_insumos(solo_admin=True, como_json=True)
def insumos_ajustar_costo(insumo_id, empresa):
    """Gerencia corrige el costo promedio de un insumo en una empresa. Queda en el Kardex (AJUSTE DE COSTO) con
    el costo anterior, el nuevo, quién, cuándo y por qué. Las salidas ya registradas NO cambian; las siguientes
    se valorizan con el costo nuevo."""
    empresa = empresa.upper()
    ins = Insumo.query.get(insumo_id)
    if empresa not in EMPRESAS_INSUMOS or not ins:
        return {'status': 'error', 'msg': 'Datos inválidos'}
    moneda = 'USD' if (request.form.get('moneda') or '').upper() == 'USD' else 'PEN'
    sim = MONEDAS_INSUMOS[moneda]
    nuevo = _num(request.form.get('costo'))
    motivo = ' '.join((request.form.get('motivo') or '').split())[:255]
    if nuevo is None or nuevo < 0:
        return {'status': 'error', 'msg': f'Escribe el nuevo costo promedio ({sim} por unidad).'}
    if len(motivo) < 5:
        return {'status': 'error', 'msg': 'Escribe el motivo del ajuste (queda en la auditoría).'}
    st = _stock_de(ins.id, empresa)
    stock, antes = _bolsa(st, moneda)
    if abs(round(nuevo, 6) - round(antes, 6)) < 1e-9:
        return {'status': 'error', 'msg': 'Es el mismo costo que ya tiene.'}
    ahora = hora_peru()
    if moneda == 'USD':
        st.costo_usd = round(nuevo, 6)
    else:
        st.costo_promedio = round(nuevo, 6)
    total = float(st.stock_actual or 0)
    db.session.add(InsumoMovimiento(
        empresa=empresa, insumo_id=ins.id, fecha=ahora, tipo='AJUSTE', concepto='AJUSTE_COSTO', cantidad=0,
        costo_unitario=antes, costo_total=round(stock * (nuevo - antes), 2), stock_antes=total, stock_despues=total,
        **_datos_mov_moneda(st, moneda), referencia=f'Costo promedio {sim} {antes:,.4f} → {sim} {nuevo:,.4f}'[:120],
        observacion=motivo, user_id=session.get('user_id'), fecha_registro=ahora))
    registrar_log(f"Ajustó el costo promedio ({sim}) de {ins.codigo} en {EMPRESAS_INSUMOS[empresa]['corto']}: {sim} {antes:,.4f} → {sim} {nuevo:,.4f} ({motivo})",
                  'bi-currency-exchange', 'text-warning')
    db.session.commit()
    return {'status': 'success'}


@app.route('/insumos/maestro/<int:insumo_id>/borrar', methods=['POST'])
@_ruta_insumos(editar=True, como_json=True)
def insumos_maestro_borrar(insumo_id):
    ins = Insumo.query.get_or_404(insumo_id)
    usos = (InsumoMovimiento.query.filter_by(insumo_id=ins.id).count() + InsumoIngresoDetalle.query.filter_by(insumo_id=ins.id).count()
            + InsumoSalidaDetalle.query.filter_by(insumo_id=ins.id).count())
    if usos:
        return {'status': 'error', 'msg': f'{ins.codigo} ya tiene ingresos o salidas registradas: si se borra se perdería su historial. '
                                          f'Desactívalo para que ya no aparezca (o vacía los datos de prueba en Configuración).'}
    InsumoStock.query.filter_by(insumo_id=ins.id).delete()
    registrar_log(f"Borró el insumo {ins.codigo} {ins.descripcion}", 'bi-trash', 'text-danger')
    db.session.delete(ins)
    db.session.commit()
    return {'status': 'success'}


# ---------------------------- VACIAR DATOS DEL MÓDULO (pruebas) ----------------------------
@app.route('/insumos/config/vaciar', methods=['POST'])
@_ruta_insumos(solo_admin=True)
def insumos_vaciar():
    """Borra SOLO los datos de Insumos Internos (y sus archivos en S3). No toca ningún otro módulo."""
    f = request.form
    destino = url_for('insumos_config', tab='vaciar')
    if (f.get('confirmacion') or '').strip().upper() != 'BORRAR INSUMOS':
        flash('⛔ Escribe BORRAR INSUMOS para confirmar.')
        return redirect(destino)
    maestro, proveedores, personal, catalogos = (f.get(k) == '1' for k in ('maestro', 'proveedores', 'personal', 'catalogos'))
    claves = [d.s3_key for d in InsumoDocumento.query.all() if d.s3_key]
    claves += [x.firma_s3_key for x in InsumoSalida.query.filter(InsumoSalida.firma_s3_key.isnot(None)).all()]
    resumen = {'ingresos': InsumoIngreso.query.count(), 'salidas': InsumoSalida.query.count()}
    try:
        try:
            OrdenCompra.query.filter(OrdenCompra.insumo_ingreso_id.isnot(None)).update({'insumo_ingreso_id': None}, synchronize_session=False)
        except Exception:
            db.session.rollback()
            app.logger.exception("No se pudo soltar las OC de los ingresos de insumos")
        for modelo in (InsumoDocumento, InsumoMovimiento, InsumoSalidaDetalle, InsumoSalida, InsumoIngresoDetalle, InsumoIngreso, InsumoStock):
            modelo.query.delete(synchronize_session=False)
        if maestro:
            try:      # las órdenes de compra de insumos conservan su descripción, pero ya no apuntan al insumo borrado
                OrdenCompraItem.query.filter(OrdenCompraItem.insumo_id.isnot(None)).update({'insumo_id': None}, synchronize_session=False)
            except Exception:
                app.logger.exception("No se pudo soltar los ítems de OC de los insumos")
                raise
            Insumo.query.delete(synchronize_session=False)
        if proveedores:
            InsumoProveedor.query.delete(synchronize_session=False)
        if personal:
            InsumoTrabajador.query.delete(synchronize_session=False)
            InsumoArea.query.delete(synchronize_session=False)
        if catalogos:
            CatalogoValor.query.filter(CatalogoValor.tipo.in_(list(CATALOGOS_INSUMOS))).delete(synchronize_session=False)
            for e in EMPRESAS_INSUMOS:
                for k in FORMATO_SALIDA_DEF:
                    SystemConfig.query.filter_by(key=f'insumos_formato_{k}_{e}').delete(synchronize_session=False)
            db.session.flush()
            _sembrar_catalogos_insumos()
        extra = [n for n, v in (('maestro', maestro), ('proveedores', proveedores), ('trabajadores y áreas', personal),
                                ('catálogos', catalogos)) if v]
        registrar_log(f"VACIÓ los datos de Insumos Internos: {resumen['ingresos']} ingreso(s), {resumen['salidas']} salida(s), "
                      f"{len(claves)} archivo(s){' + ' + ', '.join(extra) if extra else ''}", 'bi-trash3-fill', 'text-danger')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo vaciar el módulo de insumos")
        flash(f'⛔ No se pudo vaciar (no se borró nada): {e}')
        return redirect(destino)
    _borrar_de_s3(claves)        # después del commit: si la base fallaba, los archivos seguían ahí
    flash(f'✅ Módulo de insumos vaciado: {resumen["ingresos"]} ingreso(s), {resumen["salidas"]} salida(s) y {len(claves)} archivo(s) '
          f'(PDF/fotos/firmas) borrados{", además: " + ", ".join(extra) if extra else ""}.')
    return redirect(destino)


