# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# v31 · REVERTIR MOVIMIENTOS DEL KARDEX DE INSUMOS (Anclajes, Import Bolts y General)
# Para errores: se ingresó al inventario equivocado, se eligió mal el ítem, se cargó mal un Excel, se pasó a herramientas
# algo que no era... Lo hacen Gerencia, Logística y el Jefe de Almacén (ROLES_INSUMOS_REVIERTEN), siempre con MOTIVO,
# y queda en el Kardex (movimiento ANULACIÓN; el original queda tachado y ninguno de los dos cuenta en los totales) y en el log.
#   · Ingreso (compra, con o sin OC) -> se anula EL INGRESO COMPLETO (_anular_ingreso). Si vino de una OC, la orden vuelve
#     a "Ingresos pendientes" para registrarla bien. Solo si lo ingresado sigue completo en su lote.
#   · Salida (consumo)              -> se anula LA SALIDA (_anular_salida): lo despachado vuelve a los mismos lotes.
#   · Carga Excel (entrada)         -> se quita ese lote (tiene que estar completo).
#   · Carga Excel (salida / conteo) -> lo descontado vuelve al mismo lote.
#   · Pasó a herramientas           -> se borran del registro esas herramientas (solo si siguen en almacén, sin préstamos)
#                                      y las unidades vuelven al mismo lote.
#   · Precio completado / ajuste de costo / anulaciones: no se revierten aquí (el precio se corrige en el lote).
# Este archivo NO se importa: app.py lo carga (lista MODULOS_EN_ARCHIVOS), después de herramientas.py. Ver MAPA.md.
# =====================================================================================
from models import Herramienta, HerramientaMovimiento, InsumoMovimiento     # (los nuevos se importan en cada módulo)

CONCEPTOS_REVERTIBLES = ('COMPRA', 'CONSUMO', 'IMPORTACION', 'A_HERRAMIENTAS')


def _puede_revertir_insumos():
    return session.get('role') in ROLES_INSUMOS_REVIERTEN


def _usos_lote_txt(lote, maximo=4):
    """Por qué un lote ya no está completo: qué movimientos sacaron de él (para decir qué revertir primero). '' si no se sabe."""
    try:
        movs = InsumoMovimiento.query.filter(InsumoMovimiento.lote_id == lote.id, InsumoMovimiento.tipo == 'SALIDA',
                                             InsumoMovimiento.concepto != 'ANULACION').order_by(InsumoMovimiento.fecha).all()
    except Exception:
        db.session.rollback()
        return ''
    if not movs:
        return ''
    revertidos = _movs_revertidos([m.id for m in movs])
    sal_anul = {i for (i,) in db.session.query(InsumoSalida.id).filter(
        InsumoSalida.id.in_({m.salida_id for m in movs if m.salida_id} or {0}), InsumoSalida.estado == 'ANULADA').all()}
    partes = []
    for m in movs:
        if m.id in revertidos or m.salida_id in sal_anul:
            continue
        cant = _cant_txt(m.cantidad)
        if m.concepto == 'CONSUMO':
            partes.append(f'salida {m.referencia or "#" + str(m.salida_id)} ({cant})')
        elif m.concepto == 'A_HERRAMIENTAS':
            partes.append(f'pasó a herramientas el {m.fecha.strftime("%d/%m/%Y")} ({cant})')
        elif m.concepto == 'IMPORTACION':
            partes.append(f'ajuste por carga Excel del {m.fecha.strftime("%d/%m/%Y")} ({cant})')
        else:
            partes.append(f'{m.concepto.lower()} ({cant})')
    if not partes:
        return ''
    extra = f' y {len(partes) - maximo} más' if len(partes) > maximo else ''
    return 'Salió en: ' + ', '.join(partes[:maximo]) + extra + '. '


def _movs_revertidos(ids):
    """Ids (de la lista) de movimientos que ya tienen un movimiento de reversión."""
    ids = [i for i in ids if i]
    if not ids:
        return set()
    try:
        return {i for (i,) in db.session.query(InsumoMovimiento.anula_mov_id).filter(InsumoMovimiento.anula_mov_id.in_(ids)).all()}
    except Exception:
        db.session.rollback()
        return set()


def _movs_revertidos_empresa(empresa):
    """Ids de todos los movimientos de esa bolsa que ya se revirtieron (son pocos: solo los que tienen reversión)."""
    try:
        return {i for (i,) in db.session.query(InsumoMovimiento.anula_mov_id).filter(
            InsumoMovimiento.empresa == empresa, InsumoMovimiento.anula_mov_id.isnot(None)).all()}
    except Exception:
        db.session.rollback()
        return set()


def _herr_de_mov(m):
    """Las herramientas que se crearon con ese movimiento 'PASÓ A HERRAMIENTAS' (mismo insumo, mismo lote, mismo momento)."""
    return Herramienta.query.filter(Herramienta.origen == 'INSUMOS', Herramienta.insumo_id == m.insumo_id,
                                    Herramienta.insumo_lote_id == m.lote_id, Herramienta.fecha_creacion == m.fecha,
                                    Herramienta.empresa == m.empresa).order_by(Herramienta.id).all()


def _plan_revertir_mov(m):
    """Qué pasaría al revertir este movimiento. Devuelve dict: que ('ingreso' | 'salida' | 'mov'), titulo, lineas (lo que se
    hará), bloqueo (por qué NO se puede, o None), aviso (opcional). No cambia nada."""
    emp = EMPRESAS_INSUMOS.get(m.empresa, {}).get('corto', m.empresa)
    r = {'que': 'mov', 'titulo': 'Revertir movimiento', 'lineas': [], 'bloqueo': None, 'aviso': None, 'empresa': emp}
    if m.concepto == 'ANULACION' or m.anula_mov_id:
        r['bloqueo'] = 'Este movimiento ya es una anulación.'
        return r
    if m.concepto in ('VALORIZACION', 'AJUSTE_COSTO'):
        r['bloqueo'] = ('Es un cambio de precio, no de cantidad: para corregirlo vuelve a ponerle el precio correcto al lote '
                        'desde la ficha del insumo (queda como AJUSTE DE COSTO).')
        return r
    if _movs_revertidos([m.id]):
        r['bloqueo'] = 'Este movimiento ya se revirtió.'
        return r
    cerrado = m.empresa == EMPRESA_GENERAL and _general_cerrado()
    # ---------- un ingreso (compra): se anula el ingreso completo ----------
    if m.ingreso_id:
        ing = InsumoIngreso.query.get(m.ingreso_id)
        r.update(que='ingreso', titulo=f'Anular el ingreso #{m.ingreso_id}', url=url_for('insumos_ingreso_detalle', ingreso_id=m.ingreso_id))
        if not ing or ing.estado != 'REGISTRADO':
            r['bloqueo'] = 'Este ingreso ya estaba anulado.'
            return r
        no, plan = _plan_anular_ingreso(ing)
        if no:
            r['bloqueo'] = no
            return r
        r['lineas'] = [f'Se quita del stock de {emp}: {d.insumo.codigo} {d.insumo.descripcion or ""} × {_cant_txt(d.cantidad)}'
                       for d, _p in plan]
        if len(plan) > 1:
            r['aviso'] = f'Se anula el ingreso COMPLETO ({len(plan)} ítems), no solo esta línea. Luego regístralo de nuevo como corresponde.'
        oc = OrdenCompra.query.filter(OrdenCompra.insumo_ingreso_id == ing.id).first()
        if oc:
            r['lineas'].append(f'La orden de compra {_oc_codigo(oc)} vuelve a "Ingresos pendientes (Insumos)" para registrarla bien '
                               f'(al inventario o con el ítem correcto).')
        else:
            r['lineas'].append('Después regístralo de nuevo en el inventario y con el ítem que corresponde.')
        return r
    # ---------- una salida (consumo): se anula la salida ----------
    if m.salida_id:
        sal = InsumoSalida.query.get(m.salida_id)
        r.update(que='salida', titulo=f'Anular la salida N° {sal.numero:06d}' if sal else 'Anular la salida',
                 url=url_for('insumos_salida_detalle', salida_id=m.salida_id))
        if not sal or sal.estado != 'REGISTRADA':
            r['bloqueo'] = 'Esta salida ya estaba anulada.'
            return r
        if cerrado:
            r['bloqueo'] = 'El inventario General está cerrado: Gerencia tiene que volver a abrirlo para devolverle stock.'
            return r
        r['lineas'] = [f'Vuelve al stock de {emp}: {d.insumo.codigo} {d.insumo.descripcion or ""} × {_cant_txt(d.cantidad_despachada)}'
                       for d in sal.detalles]
        r['lineas'].append(f'Deja de contar en el gasto del área{(" " + sal.area.nombre) if getattr(sal, "area", None) else ""}.')
        if len(sal.detalles) > 1:
            r['aviso'] = f'Se anula la salida COMPLETA ({len(sal.detalles)} ítems), no solo esta línea.'
        if getattr(sal, 'grupo', None):
            otras = InsumoSalida.query.filter(InsumoSalida.grupo == sal.grupo, InsumoSalida.id != sal.id,
                                              InsumoSalida.estado == 'REGISTRADA').count()
            if otras:
                r['aviso'] = ((r['aviso'] + ' ') if r['aviso'] else '') + (
                    f'Esta salida se hizo junto con {otras} salida(s) de otro inventario: solo se anula la de {emp}; '
                    f'las otras se anulan aparte si también están mal.')
        return r
    # ---------- movimientos sueltos ----------
    lote = InsumoLote.query.get(m.lote_id) if m.lote_id else None
    if not lote:
        r['bloqueo'] = 'Es un movimiento antiguo (de antes de los lotes): corrígelo con una carga Excel del conteo.'
        return r
    if m.concepto == 'IMPORTACION' and m.tipo == 'ENTRADA':
        r['titulo'] = 'Revertir la carga Excel (entrada)'
        if lote.estado != 'ACTIVO':
            r['bloqueo'] = f'El lote #{lote.id} ya no está vigente.'
        elif float(lote.cantidad_restante or 0) + 1e-9 < float(lote.cantidad_inicial or 0):
            r['bloqueo'] = (f'Del lote #{lote.id} ya salió una parte (quedan {_cant_txt(lote.cantidad_restante)} de '
                            f'{_cant_txt(lote.cantidad_inicial)}). {_usos_lote_txt(lote)}Revierte primero eso y vuelve a intentarlo.')
        else:
            r['lineas'] = [f'Se quita del stock de {emp}: {m.insumo.codigo} {m.insumo.descripcion or ""} × {_cant_txt(lote.cantidad_inicial)} '
                           f'(lote #{lote.id} de la carga Excel).']
        return r
    if m.concepto == 'IMPORTACION' and m.tipo == 'SALIDA':
        r['titulo'] = 'Revertir el ajuste de la carga Excel (salida)'
        if lote.estado != 'ACTIVO':
            r['bloqueo'] = f'El lote #{lote.id} del que salió ya no está vigente (se anuló).'
        elif cerrado:
            r['bloqueo'] = 'El inventario General está cerrado: Gerencia tiene que volver a abrirlo para devolverle stock.'
        else:
            r['lineas'] = [f'Vuelve al stock de {emp}: {m.insumo.codigo} {m.insumo.descripcion or ""} × {_cant_txt(m.cantidad)} '
                           f'(al mismo lote #{lote.id}, con su precio).']
        return r
    if m.concepto == 'A_HERRAMIENTAS':
        r['titulo'] = 'Revertir "pasó a herramientas"'
        herrs = _herr_de_mov(m)
        n = int(round(float(m.cantidad or 0)))
        if lote.estado != 'ACTIVO':
            r['bloqueo'] = f'El lote #{lote.id} del que salió ya no está vigente (se anuló).'
            return r
        if cerrado:
            r['bloqueo'] = 'El inventario General está cerrado: Gerencia tiene que volver a abrirlo para devolverle stock.'
            return r
        if len(herrs) != n:
            r['bloqueo'] = (f'No se encontraron las {n} herramienta(s) que se crearon con este movimiento (hay {len(herrs)}). '
                            f'Revísalo en Herramientas.')
            return r
        ocupadas = []
        for h in herrs:
            tipos = {t for (t,) in db.session.query(HerramientaMovimiento.tipo).filter(HerramientaMovimiento.herramienta_id == h.id).all()}
            if h.estado != 'DISPONIBLE' or tipos - {'ALTA', 'EDICION'}:
                ocupadas.append(f'{h.codigo} ({HERR_ESTADOS.get(h.estado, {}).get("txt", h.estado)}'
                                f'{", ya tuvo préstamos o reparaciones" if h.estado == "DISPONIBLE" else ""})')
        if ocupadas:
            r['bloqueo'] = ('Solo se revierte si las herramientas siguen en almacén y nunca se prestaron: ' + ', '.join(ocupadas[:6])
                            + ('…' if len(ocupadas) > 6 else '') + '. Si de verdad no es herramienta, dale de baja desde su ficha.')
            return r
        cods = [h.codigo for h in herrs]
        r['lineas'] = [f'Se borran del registro de herramientas: {", ".join(cods[:8])}{"…" if len(cods) > 8 else ""}.',
                       f'Vuelve al stock de insumos de {emp}: {m.insumo.codigo} × {_cant_txt(m.cantidad)} (al mismo lote #{lote.id}, con su precio).']
        return r
    r['bloqueo'] = 'Este tipo de movimiento no se puede revertir.'
    return r


def _revertir_mov_suelto(m, motivo, ahora):
    """Hace la reversión de un movimiento suelto (carga Excel / pasó a herramientas). Ya validado con _plan_revertir_mov."""
    lote = InsumoLote.query.get(m.lote_id)
    st = _stock_de(m.insumo_id, m.empresa)
    antes = float(st.stock_actual or 0)
    if m.tipo == 'ENTRADA':                  # carga Excel que metió un lote: se quita el lote completo
        cant = float(lote.cantidad_restante or 0)
        lote.cantidad_restante = 0.0
        lote.estado = 'ANULADO'
        tipo = 'SALIDA'
    else:                                    # lo que salió del lote vuelve a él
        cant = float(m.cantidad or 0)
        lote.cantidad_restante = round(float(lote.cantidad_restante or 0) + cant, 6)
        tipo = 'ENTRADA'
    _sincronizar_stock(st)
    if m.concepto == 'A_HERRAMIENTAS':
        for h in _herr_de_mov(m):
            HerramientaMovimiento.query.filter(HerramientaMovimiento.herramienta_id == h.id).delete(synchronize_session=False)
            db.session.delete(h)
    ref = {'IMPORTACION': 'Reversión carga Excel', 'A_HERRAMIENTAS': 'Reversión: no pasó a herramientas'}.get(m.concepto, 'Reversión')
    db.session.add(InsumoMovimiento(
        empresa=m.empresa, insumo_id=m.insumo_id, fecha=ahora, tipo=tipo, concepto='ANULACION', cantidad=cant,
        costo_unitario=lote.costo_unitario or 0, costo_total=round(cant * (lote.costo_unitario or 0), 2), stock_antes=antes,
        stock_despues=st.stock_actual, **_datos_mov_lote(lote), referencia=f'{ref} (mov. #{m.id})'[:120], anula_mov_id=m.id,
        observacion=motivo, user_id=session.get('user_id'), fecha_registro=ahora))


@app.route('/insumos/kardex/movimiento/<int:mov_id>/revertir', methods=['GET', 'POST'])
@_ruta_insumos(editar=True)
def insumos_mov_revertir(mov_id):
    """GET (JSON): qué pasará al revertir este movimiento, o por qué no se puede. POST: lo revierte (con motivo)."""
    m = InsumoMovimiento.query.get_or_404(mov_id)
    volver = request.form.get('volver') or request.referrer or ''
    if not volver.startswith('/insumos/') and '/insumos/' in volver:
        volver = volver[volver.index('/insumos/'):]
    if not volver.startswith('/insumos/'):
        volver = url_for('insumos_kardex', empresa=m.empresa, insumo_id=m.insumo_id)
    if not _puede_revertir_insumos():
        if request.method == 'GET':
            return {'status': 'error', 'msg': 'No tienes permiso para revertir movimientos.'}, 403
        flash('⛔ No tienes permiso para revertir movimientos.')
        return redirect(volver)
    plan = _plan_revertir_mov(m)
    if request.method == 'GET':
        return {'status': 'ok', 'que': plan['que'], 'titulo': plan['titulo'], 'lineas': plan['lineas'], 'bloqueo': plan['bloqueo'],
                'aviso': plan['aviso'], 'url': plan.get('url'), 'empresa': plan['empresa'],
                'mov': f"{m.insumo.codigo} · {m.tipo} {_cant_txt(m.cantidad)} · {m.fecha.strftime('%d/%m/%Y %H:%M')}"}
    motivo = ' '.join((request.form.get('motivo') or '').split())[:255]
    if plan['bloqueo']:
        flash(f"⛔ No se puede revertir: {plan['bloqueo']}")
        return redirect(volver)
    if len(motivo) < 5:
        flash('⛔ Escribe el motivo (mín. 5 letras): por qué se revierte.')
        return redirect(volver)
    try:
        if plan['que'] == 'ingreso':
            ok, msg = _anular_ingreso(InsumoIngreso.query.get(m.ingreso_id), motivo)
        elif plan['que'] == 'salida':
            ok, msg = _anular_salida(InsumoSalida.query.get(m.salida_id), motivo)
        else:
            _revertir_mov_suelto(m, motivo, hora_peru())
            registrar_log(f"Revirtió en el Kardex de insumos {plan['empresa']} el movimiento #{m.id} ({plan['titulo']}: {m.insumo.codigo} "
                          f"× {_cant_txt(m.cantidad)}): {motivo}", 'bi-arrow-counterclockwise', 'text-danger')
            ok, msg = True, f"✅ {plan['titulo']}: listo. Ya no cuenta en los totales (queda tachado en el Kardex con el motivo)."
        if ok:
            db.session.commit()
        else:
            db.session.rollback()
    except Exception:
        db.session.rollback()
        app.logger.exception("No se pudo revertir el movimiento de insumos %s", m.id)
        ok, msg = False, '⛔ No se pudo revertir: ocurrió un error. No se cambió nada.'
    flash(msg)
    return redirect(volver)
