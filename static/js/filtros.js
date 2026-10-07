/* Filtros Familia / Calidad con buscador (select2), iguales a los de la Auditoría: al tocar se despliega la
 * lista completa y al escribir se reduce. Funciona también en celulares (el <datalist> anterior no
 * mostraba sugerencias en muchos teléfonos). Si lo escrito no está en la lista, se puede elegir igual:
 * el inventario busca por coincidencia (ej. "PERN" trae todas las familias que contienen PERN). */
(function () {
    function activar() {
        if (!window.jQuery || !jQuery.fn.select2) return;
        jQuery('select.filtro-s2').each(function () {
            const $s = jQuery(this);
            if ($s.data('select2')) return;
            $s.select2({
                width: '100%',
                allowClear: true,
                placeholder: $s.data('placeholder') || '-- Todas --',
                tags: true,
                createTag: function (p) {
                    const t = (p.term || '').replace(/\s+/g, ' ').trim().toUpperCase();
                    return t ? { id: t, text: t, newTag: true } : null;
                },
                insertTag: function (data, tag) { tag.text = 'Buscar "' + tag.id + '"'; data.push(tag); },
                language: { noResults: function () { return 'Sin coincidencias'; } }
            });
            const enviar = () => {
                const f = document.getElementById($s.data('form')) || $s.closest('form')[0];
                if (f) setTimeout(() => f.submit(), 0);
            };
            $s.on('select2:select', enviar);
            $s.on('select2:clear', function () { $s.val(''); enviar(); });
            // En celular, al abrir: el cursor va directo al buscador para poder escribir
            $s.on('select2:open', function () {
                setTimeout(() => { const b = document.querySelector('.select2-container--open .select2-search__field'); if (b) b.focus(); }, 0);
            });
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', activar); else activar();
})();
