/* Firma en pantalla (dedo, lápiz o mouse) sobre un <canvas>. Devuelve PNG en base64.
 * Uso: const pad = FirmaPad(canvas); pad.limpiar(); pad.vacia(); pad.png() */
window.FirmaPad = function (canvas) {
    const ctx = canvas.getContext('2d');
    let dibujando = false, trazos = 0, ultimo = null;
    function ajustar() {
        const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        const copia = trazos ? canvas.toDataURL() : null;
        canvas.width = Math.max(1, Math.round(r.width * dpr));
        canvas.height = Math.max(1, Math.round(r.height * dpr));
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0f172a';
        if (copia) { const img = new Image(); img.onload = () => ctx.drawImage(img, 0, 0, r.width, r.height); img.src = copia; }
    }
    function punto(e) {
        const r = canvas.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
    }
    canvas.style.touchAction = 'none';
    canvas.addEventListener('pointerdown', e => { dibujando = true; ultimo = punto(e); canvas.setPointerCapture(e.pointerId);
        ctx.beginPath(); ctx.arc(ultimo.x, ultimo.y, 1, 0, Math.PI * 2); ctx.fillStyle = '#0f172a'; ctx.fill(); trazos++; });
    canvas.addEventListener('pointermove', e => {
        if (!dibujando) return;
        const p = punto(e);
        ctx.beginPath(); ctx.moveTo(ultimo.x, ultimo.y); ctx.lineTo(p.x, p.y); ctx.stroke();
        ultimo = p; trazos++;
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => canvas.addEventListener(ev, () => { dibujando = false; }));
    window.addEventListener('resize', ajustar);
    ajustar();
    return {
        limpiar() { ctx.clearRect(0, 0, canvas.width, canvas.height); trazos = 0; },
        vacia() { return trazos < 5; },
        png() {
            // Fondo blanco para que se vea bien en el PDF
            const c = document.createElement('canvas'); c.width = canvas.width; c.height = canvas.height;
            const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.drawImage(canvas, 0, 0);
            return c.toDataURL('image/png');
        },
        ajustar,
    };
};
