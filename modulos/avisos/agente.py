# flake8: noqa
# pyright: reportUndefinedVariable=false
# =====================================================================================
# AVISOS · "Programa de avisos" de Windows (funciona con el navegador CERRADO del todo)
# Un programita de Windows (PowerShell, viene con Windows: no hay que instalar nada más) que arranca solo al
# prender la PC, pregunta al sistema cada minuto y muestra el aviso de Windows. No depende de Chrome / Edge / Brave.
# Se instala con un archivo .cmd que se descarga desde Campana → Configurar (lleva la clave de esa computadora).
# Este archivo NO se importa: app.py lo carga en su lugar (lista MODULOS_EN_ARCHIVOS), como si
# su código estuviera escrito ahí. Usa directamente los modelos, variables y funciones de app.py
# y de los archivos que se cargan antes. Ver MAPA.md.
# =====================================================================================
import hashlib as _hl_agente
import secrets as _secrets_agente
from flask import make_response

AGENTE_CONSULTA_SEG = 60     # cada cuántos segundos pregunta el programa
AGENTE_ACTIVO_MIN = 5        # si preguntó en estos últimos minutos, se considera "funcionando"
AGENTE_MAX_POR_USUARIO = 10
AGENTE_VERSION = '1'
_agente_ok = [False]


def _asegurar_agente():
    if _agente_ok[0]:
        return
    _asegurar_oc()
    AvisoAgente.__table__.create(bind=db.engine, checkfirst=True)
    _agente_ok[0] = True


def _agente_hash(token):
    return _hl_agente.sha256((token or '').encode()).hexdigest()


def _agente_usuarios_activos(uids):
    """Usuarios con el programa de avisos funcionando ahora (para no mandarles el mismo aviso dos veces)."""
    uids = [u for u in (uids or []) if u]
    if not uids:
        return set()
    try:
        _asegurar_agente()
        limite = hora_peru() - timedelta(minutes=AGENTE_ACTIVO_MIN)
        return {a.user_id for a in AvisoAgente.query.filter(AvisoAgente.user_id.in_(uids), AvisoAgente.ultimo_contacto >= limite).all()}
    except Exception:
        db.session.rollback()
        return set()


def _agente_lista(uid):
    """Computadoras del usuario con el programa (borra los instaladores descargados y nunca usados de hace más de 7 días)."""
    try:
        _asegurar_agente()
        viejos = hora_peru() - timedelta(days=7)
        borrados = AvisoAgente.query.filter(AvisoAgente.user_id == uid, AvisoAgente.ultimo_contacto.is_(None),
                                            AvisoAgente.fecha < viejos).delete(synchronize_session=False)
        if borrados:
            db.session.commit()
        return AvisoAgente.query.filter_by(user_id=uid).order_by(AvisoAgente.id).all()
    except Exception:
        db.session.rollback()
        return []


def _agente_base_url():
    """Dirección del sistema como la ve el usuario (en Render llega por https a través de su proxy)."""
    proto = (request.headers.get('X-Forwarded-Proto') or request.scheme or 'https').split(',')[0].strip()
    return f"{proto}://{request.host}"


@app.route('/notificaciones/agente/api')
def agente_api():
    """Lo que consulta el programa de avisos (con su clave, sin sesión del navegador)."""
    token = (request.headers.get('X-Avisos-Token') or '').strip()
    if not token or len(token) > 100:
        return {'status': 'error', 'revocado': True}, 401
    try:
        _asegurar_agente()
        ag = AvisoAgente.query.filter_by(token_hash=_agente_hash(token)).first()
        if not ag:
            return {'status': 'error', 'revocado': True}, 401     # la quitaron desde el sistema: el programa se desinstala solo
        u = User.query.get(ag.user_id)
        if not u or getattr(u, 'desactivado', False) or getattr(u, 'bloqueado', False) or u.role not in ROLES_NOTIF:
            return {'status': 'error', 'msg': 'Usuario sin avisos'}, 403
        ahora = hora_peru()
        ag.ultimo_contacto = ahora
        pc = (request.headers.get('X-Avisos-PC') or '').strip()[:60]
        if pc:
            ag.nombre_pc = pc
        ag.version = (request.headers.get('X-Avisos-Version') or '')[:20] or ag.version
        prueba = bool(ag.prueba)
        ag.prueba = False
        cfg = _notif_cfg(u.id, u.role)
        n_aprobar = OrdenCompra.query.filter(OrdenCompra.estado == 'ENVIADA').count() if cfg['tipos'].get('OC_POR_APROBAR') else 0
        lista = Notificacion.query.filter(Notificacion.user_id == u.id).order_by(Notificacion.id.desc()).limit(40).all()
        ult = max([n.id for n in lista] or [0])
        ids_oc = [n.orden_id for n in lista if n.tipo == 'OC_POR_APROBAR' and n.orden_id and not n.leida]
        vivas = {o.id for o in OrdenCompra.query.filter(OrdenCompra.id.in_(ids_oc or [0]), OrdenCompra.estado == 'ENVIADA').all()}
        por_ingresar = _notif_por_ingresar_json(ahora, cfg)
        vivas_ing = {x['id'] for x in por_ingresar}
        _notif_resolver_por_ingresar(u.id, vivas_ing, ahora)
        n_ingresar = len(por_ingresar)
        no_leidas = sum(1 for n in lista if not n.leida and n.tipo != 'OC_POR_APROBAR' and n.tipo not in TIPOS_POR_INGRESAR)
        desde = request.args.get('desde', type=int)
        nuevas = []
        if desde is not None:
            for n in sorted([x for x in lista if x.id > desde and not x.leida and (x.tipo != 'OC_POR_APROBAR' or x.orden_id in vivas)
                             and (x.tipo not in TIPOS_POR_INGRESAR or x.orden_id in vivas_ing)], key=lambda x: x.id)[-5:]:
                nuevas.append({'id': n.id, 'titulo': n.titulo, 'texto': n.texto or '', 'url': url_for('notif_ir', notif_id=n.id),
                               'insistente': n.tipo in TIPOS_INSISTENTES})
        partes = []
        if n_aprobar:
            partes.append(f"{n_aprobar} orden{'es' if n_aprobar != 1 else ''} por aprobar")
        if n_ingresar:
            partes.append(f"{n_ingresar} por ingresar al inventario")
        if no_leidas:
            partes.append(f"{no_leidas} novedad{'es' if no_leidas != 1 else ''} sin leer")
        db.session.commit()
        return {'status': 'ok', 'windows': bool(cfg['windows']), 'nuevas': nuevas, 'ultimo_id': ult,
                'pendientes': n_aprobar + n_ingresar + no_leidas, 'resumen': ' · '.join(partes), 'recordar_min': cfg['recordar_min'],
                'consulta_seg': AGENTE_CONSULTA_SEG, 'abrir': (por_ingresar[0]['url'] if n_ingresar and not n_aprobar else url_for('index')), 'campana': url_for('notif_pagina'),
                'prueba': prueba, 'usuario': u.nombre_completo or u.username}
    except Exception:
        db.session.rollback()
        app.logger.exception("Programa de avisos: no se pudo responder")
        return {'status': 'error'}, 500


@app.route('/notificaciones/agente/instalador', methods=['POST'])
def agente_instalador():
    """Descarga el instalador (.cmd) para ESTA computadora: lleva una clave nueva solo para ella."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid:
        return redirect(url_for('login'))
    if rol not in ROLES_NOTIF:
        return "Acceso denegado", 403
    _asegurar_agente()
    if AvisoAgente.query.filter_by(user_id=uid).count() >= AGENTE_MAX_POR_USUARIO:
        flash(f'Ya tienes {AGENTE_MAX_POR_USUARIO} computadoras con el programa de avisos. Quita alguna que ya no uses.', 'error')
        return redirect(url_for('notif_pagina'))
    token = _secrets_agente.token_urlsafe(32)
    db.session.add(AvisoAgente(user_id=uid, token_hash=_agente_hash(token), nombre_pc='(por instalar)', fecha=hora_peru(), prueba=False))
    registrar_log('Descargó el instalador del programa de avisos de Windows', 'bi-bell', 'text-primary')
    db.session.commit()
    contenido = _agente_instalador_txt(_agente_base_url(), token)
    resp = make_response(contenido.encode('utf-8'))
    resp.headers['Content-Type'] = 'application/octet-stream'
    resp.headers['Content-Disposition'] = 'attachment; filename="Instalar-Avisos-ImportBolts.cmd"'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/notificaciones/agente/quitar', methods=['POST'])
def agente_quitar():
    """Quita una computadora: en su próxima consulta el programa se desinstala solo."""
    uid = session.get('user_id')
    if not uid:
        return {'status': 'error'}, 401
    _asegurar_agente()
    n = AvisoAgente.query.filter(AvisoAgente.user_id == uid, AvisoAgente.id == request.form.get('id', type=int)).delete(synchronize_session=False)
    db.session.commit()
    return {'status': 'ok', 'n': n}


@app.route('/notificaciones/agente/prueba', methods=['POST'])
def agente_prueba():
    """Deja un aviso de prueba: le llega a cada computadora con el programa en su próxima consulta (máx. 1 minuto)."""
    uid, rol = session.get('user_id'), session.get('role')
    if not uid or rol not in ROLES_NOTIF:
        return {'status': 'error'}, 403
    _asegurar_agente()
    q = AvisoAgente.query.filter(AvisoAgente.user_id == uid, AvisoAgente.ultimo_contacto.isnot(None))
    n = q.count()
    if not n:
        return {'status': 'error', 'msg': 'Todavía no hay ninguna computadora con el programa de avisos funcionando.'}
    q.update({'prueba': True}, synchronize_session=False)
    db.session.commit()
    return {'status': 'ok', 'n': n, 'seg': AGENTE_CONSULTA_SEG}


def _agente_instalador_txt(base, token):
    """El .cmd: unas líneas de Windows que le pasan el resto del archivo a PowerShell (que viene con Windows)."""
    if not re.fullmatch(r'https?://[A-Za-z0-9.\-:\[\]]+', base) or not re.fullmatch(r'[A-Za-z0-9_\-]+', token):
        raise ValueError('Dirección o clave no válida para el instalador')
    ps = AGENTE_INSTALADOR_PS.replace('__URL__', base).replace('__TOKEN__', token).replace('__AGENTE__', AGENTE_PS)
    cab = AGENTE_CMD_CABECERA
    return (cab + ps).replace('\r\n', '\n').replace('\n', '\r\n')


# ------------------------------------------------------------------------------------------------
# 1) Cabecera del .cmd (solo ASCII). Lee el mismo archivo desde la marca y se lo pasa a PowerShell.
# ------------------------------------------------------------------------------------------------
AGENTE_CMD_CABECERA = r"""@echo off
title Instalar avisos de Windows - Sistema ImportBolts / Anclajes
echo.
echo  Instalando el programa de avisos de Windows del sistema...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8); $i=$s.IndexOf('#INSTALADOR'+'_PS'); Invoke-Expression $s.Substring($i)"
echo.
pause
exit /b
"""

# ------------------------------------------------------------------------------------------------
# 2) Instalador (PowerShell): copia el programa a la carpeta del usuario, lo deja arrancando con Windows y lo inicia.
#    No necesita permisos de administrador.
# ------------------------------------------------------------------------------------------------
AGENTE_INSTALADOR_PS = r"""#INSTALADOR_PS
$ErrorActionPreference = 'Stop'
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $Url = '__URL__'
    $Token = '__TOKEN__'
    $Dir = Join-Path $env:LOCALAPPDATA 'AvisosImportBolts'
    $AppId = 'ImportBolts.Avisos'
    $Inicio = Join-Path ([Environment]::GetFolderPath('Startup')) 'Avisos ImportBolts.lnk'
    $PsExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $utf8 = New-Object System.Text.UTF8Encoding $true

    # si ya estaba instalado, se cierra la copia anterior
    try {
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*AvisosImportBolts*avisos.ps1*' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}

    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $cfg = @{ url = $Url; token = $Token } | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $Dir 'config.json'), $cfg, $utf8)
    if (Test-Path (Join-Path $Dir 'estado.json')) { Remove-Item (Join-Path $Dir 'estado.json') -Force }
    $agente = @'
__AGENTE__
'@
    [IO.File]::WriteAllText((Join-Path $Dir 'avisos.ps1'), $agente, $utf8)

    # logo para los avisos
    $logo = Join-Path $Dir 'logo.png'
    try { $wc = New-Object System.Net.WebClient; $wc.DownloadFile("$Url/static/img/logo.png", $logo) } catch {}

    # nombre del remitente de los avisos ("Avisos ImportBolts")
    $k = "HKCU:\Software\Classes\AppUserModelId\$AppId"
    New-Item -Path $k -Force | Out-Null
    Set-ItemProperty -Path $k -Name DisplayName -Value 'Avisos ImportBolts'
    if (Test-Path $logo) { Set-ItemProperty -Path $k -Name IconUri -Value $logo }

    # que arranque solo al iniciar sesión en Windows (carpeta Inicio del usuario)
    $args1 = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Dir\avisos.ps1`""
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Inicio)
    $lnk.TargetPath = $PsExe
    $lnk.Arguments = $args1
    $lnk.WorkingDirectory = $Dir
    $lnk.WindowStyle = 7
    $lnk.Description = 'Avisos de Windows del sistema ImportBolts / Anclajes'
    $lnk.Save()

    # se inicia ahora mismo
    Start-Process -FilePath $PsExe -ArgumentList $args1 -WindowStyle Hidden

    # aviso de confirmación
    try {
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
        $x = New-Object Windows.Data.Xml.Dom.XmlDocument
        $x.LoadXml('<toast><visual><binding template="ToastGeneric"><text>Avisos instalados</text><text>Desde ahora te llegan los avisos del sistema aunque el navegador este cerrado.</text></binding></visual></toast>')
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show([Windows.UI.Notifications.ToastNotification]::new($x))
    } catch {}

    Write-Host ''
    Write-Host '  LISTO. El programa de avisos quedo instalado y funcionando.' -ForegroundColor Green
    Write-Host '  - Arranca solo cada vez que prendes la PC (no abre ninguna ventana).'
    Write-Host '  - Te avisa aunque el navegador este cerrado.'
    Write-Host '  - Para quitarlo: en el sistema, Campana > Configurar > Programa de avisos > Quitar.'
    Write-Host '  Ya puedes borrar este archivo y cerrar esta ventana.'
} catch {
    Write-Host ''
    Write-Host ('  No se pudo instalar: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '  Si es una PC de la empresa con restricciones, pide a sistemas que permita PowerShell para tu usuario.'
}
"""

# ------------------------------------------------------------------------------------------------
# 3) El programa de avisos (queda en %LOCALAPPDATA%\AvisosImportBolts\avisos.ps1).
#    Ninguna línea puede empezar con '@ (cerraría el texto del instalador).
# ------------------------------------------------------------------------------------------------
AGENTE_PS = r"""# Avisos de Windows del sistema ImportBolts / Anclajes
# Pregunta al sistema cada minuto y muestra el aviso de Windows (no necesita el navegador abierto).
# Para quitarlo: en el sistema, Campana > Configurar > Programa de avisos > Quitar (se desinstala solo).
$ErrorActionPreference = 'Continue'
$Version = '__VERSION__'
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppId = 'ImportBolts.Avisos'
$Inicio = Join-Path ([Environment]::GetFolderPath('Startup')) 'Avisos ImportBolts.lnk'
$EstadoArch = Join-Path $Dir 'estado.json'
$Logo = Join-Path $Dir 'logo.png'

# una sola copia funcionando por usuario
$nuevo = $false
$script:Mutex = New-Object System.Threading.Mutex($true, 'Local\AvisosImportBoltsAnclajes', [ref]$nuevo)
if (-not $nuevo) { exit }

try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
$Cfg = [IO.File]::ReadAllText((Join-Path $Dir 'config.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
$Base = ([string]$Cfg.url).TrimEnd('/')

$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]

# nombre del remitente (por si lo borraron)
try {
    $k = "HKCU:\Software\Classes\AppUserModelId\$AppId"
    if (-not (Test-Path $k)) {
        New-Item -Path $k -Force | Out-Null
        Set-ItemProperty -Path $k -Name DisplayName -Value 'Avisos ImportBolts'
        if (Test-Path $Logo) { Set-ItemProperty -Path $k -Name IconUri -Value $Logo }
    }
} catch {}

function X([string]$s) { [Security.SecurityElement]::Escape($s) }

function Mostrar-Aviso([string]$titulo, [string]$texto, [string]$ruta, [bool]$insistente, [string]$tag) {
    try {
        $url = if ($ruta -match '^https?://') { $ruta } else { $Base + $ruta }
        $u = X $url
        $img = ''
        if (Test-Path $Logo) { $img = '<image placement="appLogoOverride" src="' + (X ([Uri]$Logo).AbsoluteUri) + '"/>' }
        $esc = ''
        if ($insistente) { $esc = ' scenario="reminder"' }
        $xml = '<toast activationType="protocol" launch="' + $u + '"' + $esc + '>' +
               '<visual><binding template="ToastGeneric"><text>' + (X $titulo) + '</text><text>' + (X $texto) + '</text>' + $img + '</binding></visual>' +
               '<actions><action content="Abrir" activationType="protocol" arguments="' + $u + '"/>' +
               '<action content="" activationType="system" arguments="dismiss"/></actions>' +
               '<audio src="ms-winsoundevent:Notification.Reminder"/></toast>'
        $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
        $doc.LoadXml($xml)
        $t = [Windows.UI.Notifications.ToastNotification]::new($doc)
        if ($tag) { $t.Tag = $tag.Substring(0, [Math]::Min(60, $tag.Length)) }
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($t)
    } catch {}
}

function Desinstalar {
    try { Remove-Item -LiteralPath $Inicio -Force -ErrorAction SilentlyContinue } catch {}
    try { Remove-Item -Path "HKCU:\Software\Classes\AppUserModelId\$AppId" -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    try { Remove-Item -LiteralPath $Dir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}

function Consultar([string]$q) {
    $wc = New-Object System.Net.WebClient
    $wc.Encoding = [Text.Encoding]::UTF8
    $wc.Headers.Add('X-Avisos-Token', [string]$Cfg.token)
    $wc.Headers.Add('X-Avisos-PC', [string]$env:COMPUTERNAME)
    $wc.Headers.Add('X-Avisos-Version', $Version)
    $wc.Headers.Add('Accept', 'application/json')
    try { return ($wc.DownloadString($Base + '/notificaciones/agente/api' + $q) | ConvertFrom-Json) } finally { $wc.Dispose() }
}

function Codigo-Http($err) {
    $e = $err.Exception
    while ($e) {
        if ($e -is [System.Net.WebException] -and $e.Response) { return [int]$e.Response.StatusCode }
        $e = $e.InnerException
    }
    return 0
}

$ultimo = $null
try { $est = [IO.File]::ReadAllText($EstadoArch) | ConvertFrom-Json; if ($est.ultimo -ne $null) { $ultimo = [int]$est.ultimo } } catch {}
$ultRecordatorio = [datetime]::MinValue
$espera = 60

while ($true) {
    try {
        $q = ''
        if ($ultimo -ne $null) { $q = '?desde=' + $ultimo }
        $d = Consultar $q
        if ($d.status -eq 'ok') {
            $espera = [Math]::Max(30, [int]$d.consulta_seg)
            if ($d.prueba) {
                Mostrar-Aviso 'Prueba de aviso del sistema' ('Así te llegarán los avisos aunque el navegador esté cerrado. Usuario: ' + $d.usuario) $d.campana $false 'erp-prueba'
            }
            if ($d.windows) {
                $nuevas = @($d.nuevas)
                foreach ($n in $nuevas) {
                    Mostrar-Aviso ([string]$n.titulo) ([string]$n.texto) ([string]$n.url) ([bool]$n.insistente) ('erp-' + $n.id)
                }
                if ($nuevas.Count -gt 0) {
                    $ultRecordatorio = Get-Date
                } elseif ([int]$d.recordar_min -gt 0 -and [int]$d.pendientes -gt 0 -and ((Get-Date) - $ultRecordatorio).TotalMinutes -ge [int]$d.recordar_min) {
                    Mostrar-Aviso ('Tienes ' + $d.pendientes + ' aviso(s) pendiente(s)') ([string]$d.resumen) ([string]$d.abrir) $false 'erp-recordatorio'
                    $ultRecordatorio = Get-Date
                }
            }
            if ($ultimo -ne [int]$d.ultimo_id) {
                $ultimo = [int]$d.ultimo_id
                try { [IO.File]::WriteAllText($EstadoArch, (@{ ultimo = $ultimo } | ConvertTo-Json)) } catch {}
            }
        }
    } catch {
        $c = Codigo-Http $_
        if ($c -eq 401) { Desinstalar; exit }      # la computadora se quitó desde el sistema
        if ($c -eq 403) { $espera = 600 } else { $espera = 60 }   # sin internet o el servidor arrancando: se reintenta
    }
    Start-Sleep -Seconds $espera
}
""".replace('__VERSION__', AGENTE_VERSION)
