/* Editor de UBICACIÓN de un producto (Editar Producto en Inventario Anclajes / Import Bolts).
 * - Una o varias ubicaciones "ANAQUEL X CASILLERO Y" elegidas de los MISMOS catálogos que usa la
 *   Auditoría (Catálogos > Anaqueles / Casilleros), con buscador (select2) que funciona en celular.
 * - Si hace falta, también una línea de texto libre (ej. "PATIO EXTERIOR").
 * - Todo se guarda en el único campo "ubicacion" del producto, separado por " + " (el mismo formato que
 *   usa la Auditoría al combinar ubicaciones), así se ve igual en su inventario y en el Inventario General.
 */
window.UbicEditor = (function () {
    const SEP = ' + ';
    const MAX = 200;                       // largo de la columna en la base de datos
    let cfg = null, catalogo = null, cargando = null, tocado = false, valorOriginal = '';

    function css() {
        if (document.getElementById('ubic-editor-css')) return;
        const st = document.createElement('style');
        st.id = 'ubic-editor-css';
        st.textContent = `
            .ubic-filas { display: grid; gap: 6px; }
            .ubic-fila { display: flex; gap: 6px; align-items: center; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px; }
            .ubic-fila .ubic-num { flex: 0 0 22px; height: 22px; border-radius: 50%; background: #0B3D91; color: #fff; font-size: .7rem;
                                   font-weight: 700; display: flex; align-items: center; justify-content: center; }
            .ubic-fila.texto .ubic-num { background: #64748b; }
            .ubic-fila .ubic-campo { flex: 1 1 0; min-width: 0; }
            .ubic-fila .ubic-campo label { display: block; font-size: .62rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin: 0 0 1px 2px; }
            .ubic-fila .select2-container .select2-selection--single { height: 31px; }
            .ubic-fila .select2-container .select2-selection__rendered { line-height: 29px; font-size: .85rem; }
            .ubic-fila .select2-container .select2-selection__arrow { height: 29px; }
            .ubic-fila .ubic-quitar { flex: 0 0 auto; border: 0; background: transparent; color: #94a3b8; padding: 4px 6px; align-self: flex-end; }
            .ubic-fila .ubic-quitar:hover { color: #dc2626; }
            .ubic-fila.incompleta { border-color: #f59e0b; background: #fffbeb; }
            .ubic-vacio { font-size: .78rem; color: #94a3b8; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 8px; text-align: center; }
            .ubic-preview { font-size: .72rem; color: #475569; margin-top: 4px; word-break: break-word; }
            .ubic-preview b { color: #0f172a; }
            .ubic-preview.excede { color: #dc2626; }
        `;
        document.head.appendChild(st);
    }

    function cargarCatalogo() {
        if (catalogo) return Promise.resolve(catalogo);
        if (!cargando) {
            const pedir = (t) => fetch('/api/catalogo/' + t).then(r => r.ok ? r.json() : { valores: [] }).then(d => d.valores || []).catch(() => []);
            cargando = Promise.all([pedir('ANAQUEL'), pedir('NICHO')]).then(([a, n]) => (catalogo = { anaqueles: a, casilleros: n }));
        }
        return cargando;
    }

    function limpiar(t) { return String(t == null ? '' : t).replace(/\s+/g, ' ').trim().toUpperCase(); }

    // "ANAQUEL 3 CASILLERO B + PATIO" -> [{tipo:'par', anaquel:'3', casillero:'B'}, {tipo:'texto', texto:'PATIO'}]
    function parsear(texto) {
        const partes = String(texto || '').split(/\s\+\s/).map(p => p.trim()).filter(Boolean);
        return partes.map(p => {
            const m = p.match(/^ANAQUEL\s+(.+?)\s+CASILLERO\s+(.+)$/i);
            if (m && catalogo && catalogo.anaqueles.includes(m[1].trim()) && catalogo.casilleros.includes(m[2].trim())) {
                return { tipo: 'par', anaquel: m[1].trim(), casillero: m[2].trim() };
            }
            return { tipo: 'texto', texto: p };     // lo que no es del catálogo se conserva tal cual
        });
    }

    function opcionesHtml(lista, elegido) {
        let html = '<option value=""></option>';
        const vals = lista.slice();
        if (elegido && !vals.includes(elegido)) vals.unshift(elegido);
        vals.forEach(v => {
            const o = document.createElement('option');
            o.value = v; o.textContent = v; if (v === elegido) o.setAttribute('selected', 'selected');
            html += o.outerHTML;
        });
        return html;
    }

    function cambio() { tocado = true; actualizar(); }

    function filaPar(datos) {
        const fila = document.createElement('div');
        fila.className = 'ubic-fila par';
        fila.innerHTML = `
            <span class="ubic-num"></span>
            <div class="ubic-campo"><label>Anaquel</label><select class="ubic-anaquel" style="width:100%;">${opcionesHtml(catalogo.anaqueles, datos.anaquel)}</select></div>
            <div class="ubic-campo"><label>Casillero</label><select class="ubic-casillero" style="width:100%;">${opcionesHtml(catalogo.casilleros, datos.casillero)}</select></div>
            <button type="button" class="ubic-quitar" title="Quitar esta ubicación"><i class="bi bi-x-circle-fill"></i></button>`;
        return fila;
    }

    function filaTexto(datos) {
        const fila = document.createElement('div');
        fila.className = 'ubic-fila texto';
        fila.innerHTML = `
            <span class="ubic-num"></span>
            <div class="ubic-campo"><label>Texto libre</label>
                <input type="text" class="form-control form-control-sm text-uppercase ubic-texto" maxlength="80" placeholder="Ej: PATIO EXTERIOR"></div>
            <button type="button" class="ubic-quitar" title="Quitar esta ubicación"><i class="bi bi-x-circle-fill"></i></button>`;
        fila.querySelector('.ubic-texto').value = datos.texto || '';
        return fila;
    }

    function activarFila(fila) {
        if (fila.classList.contains('par') && window.jQuery && jQuery.fn.select2) {
            const padre = cfg.modal ? jQuery(cfg.modal) : jQuery(document.body);
            jQuery(fila).find('.ubic-anaquel').select2({ placeholder: 'Anaquel', width: '100%', allowClear: true, dropdownParent: padre });
            jQuery(fila).find('.ubic-casillero').select2({ placeholder: 'Casillero', width: '100%', allowClear: true, dropdownParent: padre });
            jQuery(fila).find('select').on('change', cambio);
        } else {
            fila.querySelectorAll('select').forEach(s => s.addEventListener('change', cambio));
        }
        const txt = fila.querySelector('.ubic-texto');
        if (txt) txt.addEventListener('input', () => { const p = txt.selectionStart; txt.value = txt.value.toUpperCase(); try { txt.setSelectionRange(p, p); } catch (e) {} cambio(); });
        fila.querySelector('.ubic-quitar').addEventListener('click', () => {
            if (window.jQuery && jQuery.fn.select2) jQuery(fila).find('select').each(function () { if (jQuery(this).data('select2')) jQuery(this).select2('destroy'); });
            fila.remove(); cambio();
        });
    }

    function filas() { return Array.from(cfg.contenedor.querySelectorAll('.ubic-fila')); }

    function leer() {
        const partes = [], errores = [];
        filas().forEach((f, i) => {
            f.classList.remove('incompleta');
            if (f.classList.contains('par')) {
                const a = f.querySelector('.ubic-anaquel').value, c = f.querySelector('.ubic-casillero').value;
                if (a && c) partes.push(`ANAQUEL ${a} CASILLERO ${c}`);
                else if (a || c) { f.classList.add('incompleta'); errores.push(`En la ubicación ${i + 1} falta elegir ${a ? 'el Casillero' : 'el Anaquel'}.`); }
            } else {
                const t = limpiar(f.querySelector('.ubic-texto').value);
                if (t) partes.push(t);
            }
        });
        const unicas = [...new Set(partes)];
        return { texto: unicas.join(SEP), errores };
    }

    function actualizar() {
        filas().forEach((f, i) => { f.querySelector('.ubic-num').textContent = i + 1; });
        const vacio = cfg.contenedor.querySelector('.ubic-vacio');
        if (vacio) vacio.style.display = filas().length > 0 ? 'none' : '';
        const { texto } = leer();
        if (tocado) cfg.hidden.value = texto;
        const actual = tocado ? texto : valorOriginal;
        if (cfg.preview) {
            cfg.preview.classList.toggle('excede', actual.length > MAX);
            cfg.preview.innerHTML = actual
                ? `Se guardará: <b>${actual.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))}</b>`
                  + (actual.length > MAX ? ` — muy largo (${actual.length}/${MAX} letras)` : '')
                : 'Sin ubicación.';
        }
    }

    function agregar(tipo, datos) {
        const crear = () => {
            const fila = tipo === 'texto' ? filaTexto(datos || {}) : filaPar(datos || {});
            cfg.contenedor.querySelector('.ubic-filas').appendChild(fila);
            activarFila(fila);
            actualizar();
            return fila;
        };
        if (tipo === 'texto') return Promise.resolve(crear());
        return cargarCatalogo().then(crear);
    }

    return {
        /* opciones: {contenedor, hidden, preview, modal} (elementos del DOM) */
        init(opciones) {
            css();
            cfg = opciones;
            cfg.contenedor.innerHTML = '<div class="ubic-filas"></div><div class="ubic-vacio">Sin ubicación. Usa los botones de abajo para agregar una.</div>';
            cargarCatalogo();
        },
        /* Carga la ubicación guardada del producto (texto) en el editor */
        cargar(texto) {
            valorOriginal = String(texto || '').trim();
            tocado = false;
            cfg.hidden.value = valorOriginal;
            if (window.jQuery && jQuery.fn.select2) jQuery(cfg.contenedor).find('select').each(function () { if (jQuery(this).data('select2')) jQuery(this).select2('destroy'); });
            cfg.contenedor.querySelector('.ubic-filas').innerHTML = '';
            actualizar();
            return cargarCatalogo().then(() => {
                parsear(valorOriginal).forEach(p => {
                    const fila = p.tipo === 'par' ? filaPar(p) : filaTexto(p);
                    cfg.contenedor.querySelector('.ubic-filas').appendChild(fila);
                    activarFila(fila);
                });
                actualizar();
            });
        },
        agregar(tipo) { tocado = true; return agregar(tipo); },
        /* Devuelve un mensaje de error si algo está mal, o '' si se puede guardar */
        validar() {
            const { texto, errores } = leer();
            if (errores.length) return errores.join(' ');
            if ((tocado ? texto : valorOriginal).length > MAX) return `La ubicación es muy larga (${texto.length} letras, máximo ${MAX}). Quita alguna o acórtala.`;
            if (tocado) cfg.hidden.value = texto;
            return '';
        },
        _parsear: parsear,
    };
})();
