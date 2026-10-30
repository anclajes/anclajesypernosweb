# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# COMPRAS · CERTIFICADOS DE CALIDAD POR SUBIR (importaciones)
# El certificado de calidad es OPCIONAL: nunca frena la llegada, la conformidad ni el ingreso al inventario.
# En las importaciones (requiere_certificado) queda como "pendiente" hasta que se suba: aviso en la orden,
# número en el menú y esta lista para subirlos apenas lleguen.
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS). Ver MAPA.md.
# =====================================================================================
ESTADOS_CERT_PEND = ['APROBADA', 'RECIBIDA', 'CONFORME']


def _certificados_pendientes(ordenes=None):
    """Importaciones aprobadas (por llegar, llegadas o conformes) a las que les falta el certificado de calidad."""
    if ordenes is None:
        ordenes = OrdenCompra.query.filter(OrdenCompra.estado.in_(ESTADOS_CERT_PEND)).all()
    ordenes = [o for o in ordenes if o.requiere_certificado and o.estado in ESTADOS_CERT_PEND]
    if not ordenes:
        return []
    con_cert = {d.orden_id for d in OrdenCompraDocumento.query.filter(
        OrdenCompraDocumento.orden_id.in_([o.id for o in ordenes]), OrdenCompraDocumento.tipo == 'CERTIFICADO').all()}
    return [o for o in ordenes if o.id not in con_cert]


@app.route('/ordenes/certificados')
@_ruta_oc('ver')
def oc_certificados():
    hoy = hora_peru().date()
    filas = []
    for o in _certificados_pendientes():
        llego = o.fecha_llegada.date() if o.fecha_llegada else None
        filas.append({'orden': o, 'llego': llego, 'dias': (hoy - llego).days if llego else None,
                      'aprobada': o.fecha_aprobacion})
    # Primero lo que ya llegó (lo más antiguo arriba); después lo que aún viene en camino
    filas.sort(key=lambda f: (f['llego'] is None, f['llego'] or hoy, f['orden'].id))
    return render_template('oc_certificados.html', seccion='certificados', filas=filas, estados=ESTADOS_OC,
                           puede_subir=session.get('role') in ROLES_OC_EDITAN, max_bytes=MAX_BYTES_DOCUMENTO)
