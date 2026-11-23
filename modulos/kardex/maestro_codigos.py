# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v36 · MAESTRO: CAMBIAR EL CÓDIGO DE UN PRODUCTO y VER DÓNDE QUEDA EN EL ORDEN DE SU FAMILIA
# Los códigos ordenan las listas (Maestro, inventarios, Kardex): dentro de una familia van por medida de abajo hacia arriba
# (ej. P18128I400A 5/8" X 4 1/2" → P18128I420A 5/8" X 5" → P18128I455A 5/8" X 8"). Un código fuera de la secuencia
# (ej. PER0001) manda el producto al final de la lista.
#   · _codigo_posicion: con un código (nuevo o cambiado) dice entre qué productos queda, si sigue el formato de la familia,
#     si las medidas de la descripción encajan ahí, y sugiere un código libre en el lugar que le toca por su medida.
#   · Cambiar código: en el Maestro, Anclajes, Import Bolts (y su "sombra" IBT-), órdenes de compra y requerimientos
#     pendientes y en el historial. Los movimientos del Kardex, ventas y fotos van por producto (id): no se pierden.
#   · Revisar orden de una familia: lista por código con las medidas leídas de la descripción y marca las que
#     parecen fuera de lugar (para corregirlas una por una).
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS), después de maestro_familias.py. Ver MAPA.md.
# =====================================================================================
from collections import Counter
from models import MaestroCambioLog, MaestroProducto, MovimientoEliminado, OrdenCompraItem, OrdenCompraEntregaItem, RequerimientoItem

ROLES_CODIGOS_MAESTRO = ['admin', 'almacen', 'logistica']

_TOK_MEDIDA = r'(?<![\w\-/.,])(?:M\s?|#\s?)?(?:\d{1,2}\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)'
_RX_AXB = re.compile(r'(' + _TOK_MEDIDA + r')\s*(?:"|\'\'|MM|PULG\.?)?\s*X\s*(' + _TOK_MEDIDA + r')')
_RX_UNA = re.compile(r'(' + _TOK_MEDIDA + r')\s*(?:"|\'\'|MM)')


def _valor_medida(t):
    """'5/8' → 0.625 · '1 1/2' → 1.5 · 'M10' → 10 · '#10' → 10 · '2.5' → 2.5"""
    t = t.strip().lstrip('M#').strip().replace(',', '.')
    try:
        if ' ' in t:
            ent, fr = t.split(None, 1)
            a, b = fr.split('/')
            return float(ent) + float(a) / float(b)
        if '/' in t:
            a, b = t.split('/')
            return float(a) / float(b)
        return float(t)
    except Exception:
        return None


def _medidas_desc(nombre):
    """Medidas leídas de la descripción: (diámetro, largo) en un "A X B", o (medida,) si hay una sola con " o MM.
    None si no se reconoce. Solo para ORDENAR / avisar; no se guarda."""
    s = ' '.join((nombre or '').upper().replace('´', "'").replace('”', '"').replace('“', '"').split())
    m = _RX_AXB.search(s)
    if m:
        a, b = _valor_medida(m.group(1)), _valor_medida(m.group(2))
        if a is not None and b is not None:
            return (a, b)
    m = _RX_UNA.search(s)
    if m:
        a = _valor_medida(m.group(1))
        if a is not None:
            return (a,)
    return None


def _txt_medida(t):
    if not t:
        return ''
    def f(x):
        ent = int(x)
        fr = x - ent
        for den in (2, 4, 8, 16, 32, 64):
            num = round(fr * den)
            if abs(fr - num / den) < 1e-6:
                if num == 0:
                    return str(ent)
                if num == den:
                    return str(ent + 1)
                g_ = math.gcd(num, den)
                return (f'{ent} ' if ent else '') + f'{num // g_}/{den // g_}'
        return f'{x:g}'
    return ' × '.join(f(x) for x in t)


def _forma_codigo(sku):
    """Formato del código: letras → A, números → 9 (P18128I456A → A99999A999A)."""
    return re.sub(r'[A-Z]', 'A', re.sub(r'\d', '9', (sku or '').upper()))


def _partes_numericas(a, b):
    """Si dos códigos solo difieren en un bloque de números (mismo antes y después), devuelve (prefijo, na, nb, ancho, sufijo)."""
    if not a or not b or len(a) != len(b):
        return None
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    while i > 0 and a[i - 1].isdigit():
        i -= 1
    ja = i
    while ja < len(a) and a[ja].isdigit():
        ja += 1
    jb = i
    while jb < len(b) and b[jb].isdigit():
        jb += 1
    if ja == i or jb == i or ja != jb or a[ja:] != b[jb:]:
        return None
    return a[:i], int(a[i:ja]), int(b[i:jb]), ja - i, a[ja:]


def _codigo_entre(antes, despues, ocupados, paso=None):
    """Un código libre entre `antes` y `despues` (o justo después de `antes` / antes de `despues` si falta uno),
    cambiando solo el bloque de números en que difieren. None si no hay hueco o los códigos no son de la misma secuencia."""
    if antes and despues:
        p = _partes_numericas(antes, despues)
        if not p:
            return None
        pre, na, nb, ancho, suf = p
        if nb - na < 2:
            return None
        n = (na + nb) // 2
        for k in [0] + [d for j in range(1, nb - na) for d in (j, -j)]:
            c = n + k
            if na < c < nb:
                cod = f'{pre}{str(c).zfill(ancho)}{suf}'
                if cod not in ocupados:
                    return cod
        return None
    ref = antes or despues
    m = re.search(r'(\d+)(\D*)$', ref or '')
    if not m:
        return None
    pre, num, suf = ref[:m.start(1)], int(m.group(1)), m.group(2)
    ancho = len(m.group(1))
    paso = paso or 1
    for k in range(1, 30):
        c = num + paso * k if antes else num - paso * k
        if c < 0 or len(str(c)) > ancho:
            return None
        cod = f'{pre}{str(c).zfill(ancho)}{suf}'
        if cod not in ocupados:
            return cod
    return None


def _paso_tipico(skus):
    """Separación más común entre códigos seguidos de la familia (ej. de 5 en 5) para sugerir al final de la lista."""
    difs = []
    for a, b in zip(skus, skus[1:]):
        p = _partes_numericas(a, b)
        if p and p[2] > p[1]:
            difs.append(p[2] - p[1])
    if not difs:
        return 1
    return Counter(difs).most_common(1)[0][0]


def _codigo_posicion(familia, codigo, actual=None, nombre=None, calidad=None, vecinos=4):
    """Dónde queda `codigo` en la lista de la familia (ordenada por código) y si encaja. `actual`: el código que se está
    cambiando (se saca de la lista). Devuelve un dict listo para JSON."""
    codigo = _limpiar_codigo_maestro(codigo).upper() if codigo else ''
    filas = (MaestroProducto.query.filter(db.func.lower(db.func.trim(MaestroProducto.familia)) == (familia or '').strip().lower())
             .order_by(MaestroProducto.sku.asc()).all())
    filas = [m for m in filas if m.sku != actual]
    skus = [m.sku for m in filas]
    medida = _medidas_desc(nombre) if nombre else None
    r = {'codigo': codigo, 'familia': familia, 'total': len(filas), 'medida': _txt_medida(medida), 'avisos': [], 'filas': [],
         'formato': None, 'ejemplo': None, 'sugerido': None, 'sugerido_entre': None}
    formas = Counter(_forma_codigo(s) for s in skus)
    if formas:
        forma, n = formas.most_common(1)[0]
        if n >= max(2, len(skus) * 0.5):
            r['formato'] = forma
            r['ejemplo'] = next(s for s in skus if _forma_codigo(s) == forma)
    # ---- dónde le toca por su MEDIDA (misma calidad si hay, si no en toda la familia) ----
    if medida:
        grupo = [m for m in filas if calidad and (m.calidad or '').upper() == calidad.upper()] or filas
        con_med = [(m, _medidas_desc(m.nombre)) for m in grupo]
        con_med = [(m, md) for m, md in con_med if md and len(md) == len(medida)]
        if con_med:
            sig = next((m for m, md in con_med if md > medida), None)
            ant = None
            for m, md in con_med:
                if md <= medida:
                    ant = m
            cod = _codigo_entre(ant.sku if ant else None, sig.sku if sig else None, set(skus) | {actual or ''}, _paso_tipico(skus))
            r['sugerido'] = cod
            r['sugerido_entre'] = {'antes': ant.sku if ant else None, 'antes_nombre': ant.nombre if ant else None,
                                   'despues': sig.sku if sig else None, 'despues_nombre': sig.nombre if sig else None}
    if not codigo:
        return r
    # ---- dónde queda con el código escrito ----
    pos = sum(1 for s in skus if s < codigo)
    lista = [(m.sku, m.nombre, m.calidad, _medidas_desc(m.nombre), False) for m in filas]
    lista.insert(pos, (codigo, nombre or '(este producto)', calidad, medida, True))
    ini, fin = max(0, pos - vecinos), min(len(lista), pos + vecinos + 1)
    r['filas'] = [{'sku': s, 'nombre': n, 'calidad': c or '', 'medida': _txt_medida(md), 'es_este': e} for s, n, c, md, e in lista[ini:fin]]
    r['posicion'], r['de'] = pos + 1, len(lista)
    r['al_final'] = pos == len(skus) and len(skus) > 3
    if r['formato'] and _forma_codigo(codigo) != r['formato']:
        r['avisos'].append(f'No sigue el formato de los códigos de esta familia (ej. {r["ejemplo"]}): por eso se iría a otro lugar de la lista.')
    if r['al_final']:
        r['avisos'].append('Queda al FINAL de la familia: revisa si de verdad le toca ahí por su medida.')
    if medida:
        ant = next((md for s, n, c, md, e in reversed(lista[:pos]) if md and len(md) == len(medida) and (not calidad or (c or '').upper() == calidad.upper())), None)
        sig = next((md for s, n, c, md, e in lista[pos + 1:] if md and len(md) == len(medida) and (not calidad or (c or '').upper() == calidad.upper())), None)
        if (ant and ant > medida) or (sig and sig < medida):
            r['avisos'].append(f'Por su medida ({_txt_medida(medida)}) no le toca aquí: '
                               + (f'el de arriba es más grande ({_txt_medida(ant)}). ' if ant and ant > medida else '')
                               + (f'el de abajo es más chico ({_txt_medida(sig)}).' if sig and sig < medida else ''))
    if r['sugerido'] == codigo:
        r['sugerido'] = None
    return r


def _codigo_existe_en_algun_lado(codigo):
    if MaestroProducto.query.filter(db.func.upper(MaestroProducto.sku) == codigo).first():
        return 'el Maestro'
    if Product.query.filter(db.func.upper(Product.sku) == codigo).first():
        return 'Anclajes'
    if ProductImportBolts.query.filter(db.func.upper(ProductImportBolts.sku) == codigo).first():
        return 'Import Bolts'
    if Product.query.filter(db.func.upper(Product.sku) == f'IBT-{codigo}').first():
        return 'Anclajes (traslado IBT-)'
    return None


def _cambiar_codigo_maestro(viejo, nuevo, motivo=''):
    """Cambia el código en todos lados. Devuelve (ok, mensaje, resumen). NO hace commit."""
    viejo, nuevo = (viejo or '').strip().upper(), _limpiar_codigo_maestro(nuevo).upper()
    if not nuevo:
        return False, 'Escribe el código nuevo.', None
    if re.search(r'\s', nuevo):
        return False, 'El código no puede tener espacios.', None
    if len(nuevo) > 50:
        return False, 'El código es muy largo (máx. 50).', None
    if nuevo == viejo:
        return False, 'Es el mismo código.', None
    m = MaestroProducto.query.filter_by(sku=viejo).first()
    if not m:
        return False, f'"{viejo}" no existe en el Maestro.', None
    donde = _codigo_existe_en_algun_lado(nuevo)
    if donde:
        return False, f'El código {nuevo} ya existe en {donde}. Elige otro.', None
    ahora, usuario = hora_peru(), session.get('username', 'Sistema')
    res = {'anclajes': 0, 'importbolts': 0, 'sombra': 0, 'oc': 0, 'req': 0, 'historial': 0}
    m.sku, m.actualizado_por, m.fecha_actualizacion = nuevo, usuario, ahora
    for p in Product.query.filter(Product.sku == viejo).all():
        p.sku = nuevo
        res['anclajes'] += 1
    for p in Product.query.filter(Product.sku == f'IBT-{viejo}').all():          # el producto "sombra" del traslado Import Bolts → Anclajes
        p.sku = f'IBT-{nuevo}'
        p.shadow_origen_sku = nuevo
        res['sombra'] += 1
    for p in Product.query.filter(Product.shadow_origen_sku == viejo).all():
        p.shadow_origen_sku = nuevo
    for p in ProductImportBolts.query.filter(ProductImportBolts.sku == viejo).all():
        p.sku = nuevo
        res['importbolts'] += 1
    # órdenes de compra / requerimientos: para que al ingresar encuentren el producto con su código nuevo
    for it in OrdenCompraItem.query.filter(OrdenCompraItem.insumo_id.is_(None),
                                           or_(OrdenCompraItem.codigo == viejo, OrdenCompraItem.sku_ingreso == viejo)).all():
        if it.codigo == viejo:
            it.codigo = nuevo
        if it.sku_ingreso == viejo:
            it.sku_ingreso = nuevo
        res['oc'] += 1
    for it in OrdenCompraEntregaItem.query.filter(OrdenCompraEntregaItem.sku_ingreso == viejo).all():
        it.sku_ingreso = nuevo
    for it in RequerimientoItem.query.filter(RequerimientoItem.insumo_id.is_(None), RequerimientoItem.codigo == viejo).all():
        it.codigo = nuevo
        res['req'] += 1
    # el historial del producto lo sigue (cambios del Maestro y movimientos eliminados)
    res['historial'] += MaestroCambioLog.query.filter(MaestroCambioLog.sku == viejo).update({'sku': nuevo}, synchronize_session=False)
    try:
        MovimientoEliminado.query.filter(MovimientoEliminado.sku == viejo).update({'sku': nuevo}, synchronize_session=False)
    except Exception:
        app.logger.exception("No se pudo pasar el código nuevo a los movimientos eliminados")
    db.session.add(MaestroCambioLog(fecha=ahora, usuario=usuario, lote_id=f"COD-{ahora.strftime('%Y%m%d%H%M%S')}", sku=nuevo,
                                    inventario='MAESTRO+AMBOS', campo='codigo', valor_anterior=viejo[:100],
                                    valor_nuevo=(nuevo + (f' · {motivo}' if motivo else ''))[:100], familia=m.familia, calidad=m.calidad))
    registrar_log(f"Cambió el código {viejo} → {nuevo} en el Maestro (Anclajes: {res['anclajes']}, Import Bolts: {res['importbolts']}, "
                  f"ítems de OC: {res['oc']}){(': ' + motivo) if motivo else ''}", 'bi-upc-scan', 'text-warning')
    return True, f'Código cambiado: {viejo} → {nuevo}.', res


@app.route('/api/maestro/codigo/posicion')
def api_maestro_codigo_posicion():
    """En vivo, mientras se escribe un código (nuevo producto o cambio de código): dónde queda y si encaja."""
    if session.get('role') not in ROLES_CODIGOS_MAESTRO:
        return {'status': 'error'}, 403
    a = request.args
    familia = (a.get('familia') or '').strip()
    if not familia:
        return {'status': 'ok', 'filas': [], 'avisos': []}
    try:
        r = _codigo_posicion(familia, a.get('codigo', ''), actual=(a.get('actual') or '').strip().upper() or None,
                             nombre=a.get('nombre') or None, calidad=a.get('calidad') or None)
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudo calcular la posición del código")
        return {'status': 'error', 'msg': 'No se pudo revisar la posición.'}, 500
    existe = _codigo_existe_en_algun_lado(r['codigo']) if r['codigo'] and r['codigo'] != (a.get('actual') or '').strip().upper() else None
    r.update(status='ok', existe=existe)
    return r


@app.route('/admin/maestro/<path:sku>/cambiar_codigo', methods=['POST'])
def admin_maestro_cambiar_codigo(sku):
    if session.get('role') not in ROLES_CODIGOS_MAESTRO:
        return {'status': 'error', 'msg': 'No autorizado'}, 403
    motivo = ' '.join((request.form.get('motivo') or '').split())[:60]
    try:
        ok, msg, res = _cambiar_codigo_maestro(sku, request.form.get('nuevo', ''), motivo)
        if not ok:
            db.session.rollback()
            return {'status': 'error', 'msg': msg}
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("No se pudo cambiar el código %s", sku)
        return {'status': 'error', 'msg': f'No se pudo cambiar el código: {e}'}, 500
    return {'status': 'success', 'msg': msg, 'nuevo': _limpiar_codigo_maestro(request.form.get('nuevo', '')).upper(), 'resumen': res}


@app.route('/admin/maestro/orden')
def admin_maestro_orden():
    """Revisar el orden de una familia: por código, con la medida leída de la descripción y las que parecen fuera de lugar."""
    if session.get('role') not in ROLES_CODIGOS_MAESTRO:
        return "Acceso denegado", 403
    familias = [c.nombre for c in Category.query.order_by(Category.nombre).all()]
    familia = (request.args.get('familia') or '').strip()
    solo = request.args.get('solo') == '1'
    filas, n_fuera = [], 0
    formato = None
    if familia:
        prods = (MaestroProducto.query.filter(db.func.lower(db.func.trim(MaestroProducto.familia)) == familia.lower())
                 .order_by(MaestroProducto.sku.asc()).all())
        formas = Counter(_forma_codigo(m.sku) for m in prods)
        formato = formas.most_common(1)[0][0] if formas else None
        ultimo = {}                      # última medida vista por calidad
        for m in prods:
            md = _medidas_desc(m.nombre)
            cal = (m.calidad or '').upper()
            avisos = []
            prev = ultimo.get((cal, len(md) if md else 0))
            if md and prev and md < prev[1]:
                avisos.append(f'Medida {_txt_medida(md)} después de {_txt_medida(prev[1])} ({prev[0]}): parece fuera de orden')
            if formato and _forma_codigo(m.sku) != formato and len(prods) > 3:
                avisos.append('No sigue el formato de la familia')
            if md:
                ultimo[(cal, len(md))] = (m.sku, md)
            n_fuera += 1 if avisos else 0
            filas.append({'m': m, 'medida': _txt_medida(md), 'avisos': avisos})
    if solo:
        filas = [f for f in filas if f['avisos']]
    return render_template('admin_maestro_orden.html', familias=familias, familia=familia, filas=filas, n_fuera=n_fuera, solo=solo,
                           formato=formato)
