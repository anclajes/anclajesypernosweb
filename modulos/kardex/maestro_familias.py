# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v29 · MAESTRO DE PRODUCTOS: FAMILIAS
#   · Crear una FAMILIA NUEVA sola (antes solo se podía al crear un producto).
#   · TRASPASAR productos de una familia a otra: se marcan con los checks del catálogo (la misma selección que
#     "Imprimir códigos", que se mantiene entre páginas y filtros) y se elige la familia destino (o se crea ahí mismo).
#     El cambio se reparte al Maestro, Anclajes e ImportBolts y queda en el historial del Maestro (MaestroCambioLog).
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================

ROLES_FAMILIAS_MAESTRO = ['admin', 'almacen', 'logistica']     # los mismos que editan el Maestro
FAMILIA_MAX_LARGO = 50                                         # Category.nombre es VARCHAR(50)
TRASPASO_MAX = 500


def _familias_catalogo_conteo():
    """[{nombre, n}] de TODAS las familias (Category), con cuántos productos del Maestro tiene cada una (0 = vacía)."""
    cuenta = {f: n for f, n in db.session.query(MaestroProducto.familia, db.func.count(MaestroProducto.id))
              .group_by(MaestroProducto.familia).all() if f}
    return [{'nombre': c.nombre, 'n': cuenta.get(c.nombre, 0)} for c in Category.query.order_by(Category.nombre).all()]


app.add_template_global(_familias_catalogo_conteo, 'maestro_familias_conteo')


def _familia_norm(t):
    """Para comparar familias: mayúsculas, sin acentos, sin puntos / comas / guiones y sin espacios de más
    ("TUERCA HEX. INOX." = "tuerca hex inox"). Igual que famNorm() en admin_maestro.html."""
    import unicodedata
    t = unicodedata.normalize('NFD', (t or '').upper())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r"[.,;:\-_/()'\"]+", ' ', t).split())


def _familia_validar_nueva(nombre):
    """(nombre limpio, None) o (None, error). No puede existir ya (sin importar mayúsculas, acentos, puntos ni espacios)
    en Anclajes ni ImportBolts."""
    nombre = ' '.join(_texto_limpio(nombre or '').upper().split())
    if not nombre:
        return None, 'Escribe el nombre de la familia nueva.'
    if len(nombre) > FAMILIA_MAX_LARGO:
        return None, f'El nombre es muy largo ({len(nombre)} letras): máximo {FAMILIA_MAX_LARGO}.'
    clave = _familia_norm(nombre)
    for modelo in (Category, CategoryImportBolts):
        ya = next((c.nombre for c in modelo.query.all() if _familia_norm(c.nombre) == clave), None)
        if ya:
            return None, f'La familia "{nombre}" ya existe como "{ya}": elígela de la lista.'
    return nombre, None


def _familia_crear(nombre):
    """Crea la familia en Anclajes y en ImportBolts (sin commit)."""
    _crear_categoria_si_falta(nombre, Category, {c.nombre: c.prefijo for c in Category.query.all()})
    _crear_categoria_si_falta(nombre, CategoryImportBolts, {c.nombre: c.prefijo for c in CategoryImportBolts.query.all()})


@app.route('/admin/maestro/familia/nueva', methods=['POST'])
def admin_maestro_familia_nueva():
    if session.get('role') not in ROLES_FAMILIAS_MAESTRO:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    nombre, err = _familia_validar_nueva(request.form.get('nombre'))
    if err:
        return {'status': 'error', 'msg': err}
    try:
        _familia_crear(nombre)
        registrar_log(f'Creó la familia "{nombre}" en el Maestro (Anclajes e ImportBolts), todavía sin productos', 'bi-folder-plus', 'text-success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return {'status': 'error', 'msg': f'No se pudo crear: {e}'}, 500
    return {'status': 'success', 'msg': f'Familia "{nombre}" creada. Ya puedes pasarle productos o elegirla en "Nuevo Producto".', 'nombre': nombre}


@app.route('/admin/maestro/familia/traspasar', methods=['POST'])
def admin_maestro_familia_traspasar():
    """Pasa los productos marcados (skus separados por coma) a otra familia: Maestro + Anclajes + ImportBolts, con historial."""
    if session.get('role') not in ROLES_FAMILIAS_MAESTRO:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    skus = list(dict.fromkeys(s.strip().upper() for s in (request.form.get('skus') or '').split(',') if s.strip()))
    if not skus:
        return {'status': 'error', 'msg': 'No hay productos marcados.'}
    if len(skus) > TRASPASO_MAX:
        return {'status': 'error', 'msg': f'Son {len(skus)} productos: máximo {TRASPASO_MAX} por vez.'}
    destino = _texto_limpio(request.form.get('familia') or '')
    nueva = request.form.get('es_nueva') == '1'
    if nueva:
        destino, err = _familia_validar_nueva(destino)
        if err:
            return {'status': 'error', 'msg': err}
    else:
        destino = next((c.nombre for c in Category.query.all() if c.nombre == destino), None)
        if not destino:
            return {'status': 'error', 'msg': 'Elige la familia a la que pasan (o crea una nueva).'}
    maestros = {m.sku: m for m in MaestroProducto.query.filter(MaestroProducto.sku.in_(skus)).all()}
    no_estan = [s for s in skus if s not in maestros]
    mover = [maestros[s] for s in skus if s in maestros and maestros[s].familia != destino]
    ya_estaban = [s for s in skus if s in maestros and maestros[s].familia == destino]
    if not mover:
        return {'status': 'error', 'msg': 'Ninguno cambia: ' + ('ya están en esa familia.' if ya_estaban else 'no están en el Maestro.')}
    try:
        if nueva:
            _familia_crear(destino)
        else:      # por si la familia existe en Anclajes pero no en ImportBolts
            _crear_categoria_si_falta(destino, CategoryImportBolts, {c.nombre: c.prefijo for c in CategoryImportBolts.query.all()})
        usuario, ahora = session.get('username', 'Sistema'), hora_peru()
        lote = f"FAM-{ahora.strftime('%Y%m%d%H%M%S')}"
        anc = {p.sku: p for p in Product.query.filter(Product.sku.in_([m.sku for m in mover])).all()}
        ib = {p.sku: p for p in ProductImportBolts.query.filter(ProductImportBolts.sku.in_([m.sku for m in mover])).all()}
        origenes = {}
        for m in mover:
            antes = m.familia
            origenes[antes] = origenes.get(antes, 0) + 1
            m.familia, m.actualizado_por, m.fecha_actualizacion = destino, usuario, ahora
            for p in (anc.get(m.sku), ib.get(m.sku)):
                if p is not None:
                    p.categoria = destino
                    p.ultima_edicion_manual_fecha, p.ultima_edicion_manual_por = ahora, usuario
            db.session.add(MaestroCambioLog(fecha=ahora, usuario=usuario, lote_id=lote, sku=m.sku, inventario='MAESTRO+AMBOS', campo='familia',
                                            valor_anterior=_recortar_para_log(antes), valor_nuevo=_recortar_para_log(destino),
                                            familia=destino, calidad=m.calidad))
        de = ', '.join(f'{f} ({n})' for f, n in origenes.items())
        registrar_log(f'Traspasó {len(mover)} producto(s) a la familia "{destino}"{" (nueva)" if nueva else ""} desde: {de}'[:480],
                      'bi-folder-symlink', 'text-warning')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception('No se pudo traspasar de familia')
        return {'status': 'error', 'msg': f'No se pudo traspasar (no se cambió nada): {e}'}, 500
    extra = []
    if ya_estaban:
        extra.append(f'{len(ya_estaban)} ya estaban en esa familia')
    if no_estan:
        extra.append(f'{len(no_estan)} no están en el Maestro: {", ".join(no_estan[:5])}')
    return {'status': 'success', 'movidos': len(mover), 'familia': destino,
            'msg': f'✅ {len(mover)} producto(s) pasaron a "{destino}" (Maestro, Anclajes e ImportBolts).' + (f' ({"; ".join(extra)})' if extra else '')}


@app.route('/admin/maestro/familia/origen', methods=['POST'])
def admin_maestro_familia_origen():
    """v29.1 · De qué familia vienen los productos marcados (para mostrarlo antes de pasarlos): [{sku, nombre, familia}]."""
    if session.get('role') not in ROLES_FAMILIAS_MAESTRO:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    skus = list(dict.fromkeys(s.strip().upper() for s in (request.form.get('skus') or '').split(',') if s.strip()))[:TRASPASO_MAX]
    ms = {m.sku: m for m in MaestroProducto.query.filter(MaestroProducto.sku.in_(skus)).all()} if skus else {}
    items = [{'sku': s, 'nombre': ms[s].nombre if s in ms else '', 'familia': ms[s].familia if s in ms else None} for s in skus]
    return {'status': 'success', 'items': items}
