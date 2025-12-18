# contratos_bp.py
from flask import Blueprint, current_app, render_template_string, request, redirect, url_for, Response
import os, json
from datetime import datetime, date

# WeasyPrint opcional
try:
    from weasyprint import HTML, CSS
    WEASY_OK = True
except Exception:
    WEASY_OK = False

contratos_bp = Blueprint("contratos", __name__, url_prefix="/admin/contratos")

# === Archivo JSON unificado ===
# POR ESTE BLOQUE (COPIAR Y PEGAR):

# === Archivo JSON (por cuenta / tenant) ===
def _data_file():
    # app.py setea esto por tenant en cada request:
    # app.config["CONTRATOS_FILE"] = data/contratos_<tenant>.json
    #
    # fallback: si alguien aún usa CONTRACTS_FILE, lo respetamos
    return (
        current_app.config.get("CONTRATOS_FILE")
        or current_app.config.get("CONTRACTS_FILE")
        or "contracts.json"
    )

def _load_contracts():
    path = _data_file()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _save_contracts(data):
    path = _data_file()
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_dmy(s):
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None

def iso_to_dmy(iso):
    try:
        return datetime.strptime((iso or "").strip(), "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return (iso or "")

def render_admin_bp(html, active="contratos"):
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)

    import re

def _split_modelo_legacy(modelo_txt):
    """
    Intenta partir 'Chevrolet Trax 2016' -> ('Chevrolet', 'Trax', '2016')
    Retorna (marca, modelo, anio_str) o ('', modelo_txt, '')
    """
    s = (modelo_txt or "").strip()
    if not s:
        return "", "", ""
    m = re.match(r"^\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\-\&\.\/]+)\s+(.*?)(?:\s+(\d{4}))?\s*$", s)
    if not m:
        return "", s, ""
    marca = (m.group(1) or "").strip()
    resto = (m.group(2) or "").strip()
    anio  = (m.group(3) or "").strip() if m.lastindex and m.group(3) else ""
    # Si no pudimos separar bien y quedó todo en 'resto', devolvemos al menos el texto original como modelo
    if not resto and marca:
        return "", s, ""
    return marca, resto, anio

# =======================
#        TEMPLATES
# =======================

LIST_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">Contratos</h3>
  <a class="btn btn-primary btn-sm" href="{{ url_for('contratos.nuevo') }}">+ Nuevo contrato</a>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    {% if contratos %}
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>ID</th>
            <th>Cliente</th>
            <th>Vehículo</th>
            <th>Desde</th>
            <th>Hasta</th>
            <th>Monto</th>
            <th class="text-end">Acciones</th>
          </tr>
        </thead>
        <tbody>
        {% for c in contratos %}
          <tr>
            <td>{{ c.id }}</td>
            <td>{{ (c.cliente_nombre or '') ~ ' ' ~ (c.cliente_apellido or '') }}</td>
            <td>{{ _vehiculo_label(c) }}</td>
            <td>{{ c.desde }}</td>
            <td>{{ c.hasta }}</td>
            <td>$ {{ '{:,}'.format(c.monto or 0).replace(',','.') }}</td>
            <td class="text-end">
  <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('contratos.vista', cid=c.id) }}" target="_blank">Ver</a>
  <button class="btn btn-sm btn-outline-danger btn-del" data-id="{{ c.id }}" title="Eliminar contrato">
    <i class="bi bi-trash3"></i>
  </button>
</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
      <div class="text-secondary">Aún no hay contratos.</div>
    {% endif %}
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.btn-del').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id = btn.dataset.id;
      if(!confirm('¿Seguro que quieres eliminar el contrato #' + id + '?')) return;
      try {
        const r = await fetch('{{ url_for("contratos.eliminar") }}', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({id})
        });
        if(!r.ok){
          alert('No se pudo eliminar el contrato.');
          return;
        }
        location.reload();
      } catch(e){
        alert('Error de conexión al intentar eliminar.');
      }
    });
  });
});
</script>
"""

FORM_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">{{ 'Editar' if c_default and c_default.get('id') else 'Nuevo' }} contrato</h3>
  <a class="btn btn-outline-light btn-sm" href="{{ url_for('contratos.lista') }}">Volver</a>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <form method="post">
      <!-- ======= SECCIÓN: DATOS DEL CLIENTE ======= -->
      <h6 class="section-title">Datos del cliente</h6>
      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <label class="form-label">Nombre</label>
          <input type="text" name="cliente_nombre" class="form-control" required
                 value="{{ (c_default.get('cliente_nombre') if c_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Apellido</label>
          <input type="text" name="cliente_apellido" class="form-control" required
                 value="{{ (c_default.get('cliente_apellido') if c_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">RUT</label>
          <input type="text" name="cliente_rut" class="form-control rut" placeholder="12.345.678-9" required
                 value="{{ (c_default.get('cliente_rut') if c_default else '') or '' }}">
        </div>

        <div class="col-md-4">
          <label class="form-label">Teléfono</label>
          <input type="text" name="cliente_telefono" class="form-control fono" placeholder="+56912345678" required
                 value="{{ (c_default.get('cliente_telefono') if c_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Correo</label>
          <input type="email" name="cliente_email" class="form-control" placeholder="cliente@correo.cl" required
                 value="{{ (c_default.get('cliente_email') if c_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Nacionalidad</label>
          <input type="text" name="cliente_nacionalidad" class="form-control"
                 value="{{ (c_default.get('cliente_nacionalidad') if c_default else '') or '' }}">
        </div>
      </div>

      <hr class="my-4" />

      <!-- ======= SECCIÓN: DATOS DEL VEHÍCULO ======= -->
<h6 class="section-title">Datos del vehículo</h6>
<div class="row g-3 mb-3">
  <div class="col-md-3">
    <label class="form-label">Marca</label>
    <input type="text" name="veh_marca" class="form-control" required
           value="{{ (c_default.vehiculo_marca if c_default else '') }}">
  </div>
  <div class="col-md-3">
    <label class="form-label">Modelo</label>
    <input type="text" name="veh_modelo" class="form-control" required
           value="{{ (c_default.vehiculo_modelo if c_default else '') }}">
  </div>
  <div class="col-md-3">
    <label class="form-label">Año</label>
    <input type="text" name="veh_anio" class="form-control anio" placeholder="2017" required
           value="{{ (c_default.vehiculo_anio if c_default else '') }}">
  </div>
  <div class="col-md-3">
    <label class="form-label">Patente</label>
    <input type="text" name="veh_patente" class="form-control" required
           value="{{ (c_default.vehiculo_patente if c_default else '') }}">
  </div>
</div>

      <hr class="my-4" />

     <!-- ======= SECCIÓN: FECHAS E IMPORTE ======= -->
<div class="section-box">
  <div class="section-title">Fechas e importe</div>
  <div class="row g-3">
    <div class="col-md-3">
      <label class="form-label">Fecha de inicio</label>
      <input id="fecha_inicio" name="fecha_inicio" type="text" class="form-control fecha"
             placeholder="DD-MM-YYYY" autocomplete="off"
             value="{{ (c_default.get('desde') if c_default else '') or '' }}">
    </div>
    <div class="col-md-3">
      <label class="form-label">Fecha de finalización</label>
      <input id="fecha_fin" name="fecha_fin" type="text" class="form-control fecha"
             placeholder="DD-MM-YYYY" autocomplete="off"
             value="{{ (c_default.get('hasta') if c_default else '') or '' }}">
    </div>
    <div class="col-md-2">
      <label class="form-label">Días</label>
      <input id="dias" name="dias" type="text" class="form-control" readonly value="">
    </div>
    <div class="col-md-2">
      <label class="form-label">Precio por día</label>
      <input id="precio_dia" name="precio_dia" type="text" class="form-control moneda"
             placeholder="ej: 50.000" autocomplete="off"
             value="{{ (('{:,}'.format(c_default.get('precio_dia',0)).replace(',','.')) if c_default and c_default.get('precio_dia') else '') }}">
    </div>
    <div class="col-md-2">
      <label class="form-label">Monto total</label>
      <input id="monto_total" name="monto_total" type="text" class="form-control moneda"
             placeholder="ej: 150.000" autocomplete="off"
             value="{{ (('{:,}'.format(c_default.get('monto',0)).replace(',','.')) if c_default else '') or '' }}">
    </div>
  </div>
</div>

      <hr class="my-4" />

            <!-- ======= SECCIÓN: OBSERVACIONES ======= -->
      <h6 class="section-title">Observaciones</h6>
      <div class="row g-3 mb-3">
        <div class="col-12">
          <label class="form-label">Observaciones</label>
          <textarea name="observaciones" class="form-control" rows="2" placeholder="Notas adicionales (opcional)">{{ (c_default.get('obs') if c_default else '') or '' }}</textarea>
        </div>
      </div>

      <div class="mt-4 d-flex gap-2">
        <button class="btn btn-success">Guardar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('contratos.lista') }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>

<!-- ===== BLOQUE DE SCRIPTS ===== -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/es.js"></script>
<script>
  // fuerza el cálculo inicial si los inputs ya traen valores
  if (typeof recompute === 'function') {
    document.addEventListener('DOMContentLoaded', ()=> { recompute(); });
  }
</script>
<script>
document.addEventListener('DOMContentLoaded', function(){
  // Calendarios
  if (window.flatpickr){
    const fpInicio = flatpickr("#fecha_inicio", {
      dateFormat: "d-m-Y",
      locale: "es",
      onChange: ([d]) => {
        if (d && window.fpFin) window.fpFin.set("minDate", d);
        recompute();
      }
    });
    window.fpFin = flatpickr("#fecha_fin", {
      dateFormat: "d-m-Y",
      locale: "es",
      onChange: ()=> recompute()
    });
  }

  // Helpers
  function parseDMY(s){
    s = (s || "").trim();
    const m = s.match(/^(\d{2})-(\d{2})-(\d{4})$/);
    if (!m) return null;
    const [_, dd, mm, yyyy] = m;
    const d = new Date(Number(yyyy), Number(mm)-1, Number(dd));
    if (d.getFullYear()!==Number(yyyy) || (d.getMonth()+1)!==Number(mm) || d.getDate()!==Number(dd)) return null;
    return d;
  }
  function diffDaysInclusive(d1, d2){
    const ms = (d2 - d1);
    const days = Math.floor(ms / (1000*60*60*24)) + 1;
    return Math.max(1, days);
  }
  function rawNumber(str){
    return Number((str || "").toString().replace(/\./g,"").replace(/[^0-9\-]/g,"")) || 0;
  }
  function fmtMiles(n){
    const s = String(Math.max(0, Math.floor(n)));
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  const inpInicio = document.getElementById("fecha_inicio");
  const inpFin    = document.getElementById("fecha_fin");
  const inpDias   = document.getElementById("dias");
  const inpPrecio = document.getElementById("precio_dia");
  const inpTotal  = document.getElementById("monto_total");

  // Formato miles en vivo
  document.querySelectorAll("input.moneda, input.miles").forEach(inp=>{
    if (inp.value) inp.value = fmtMiles(rawNumber(inp.value));
    inp.addEventListener("input", ()=>{
      const selStart = inp.selectionStart;
      const old = inp.value;
      const digits = rawNumber(old);
      const right = old.length - selStart;
      const nuevo = fmtMiles(digits);
      inp.value = nuevo;
      const newPos = Math.max(0, inp.value.length - right);
      inp.setSelectionRange(newPos, newPos);
      recompute();
    });
  });

  function recompute(){
    const d1 = parseDMY(inpInicio.value);
    const d2 = parseDMY(inpFin.value);
    if (d1 && d2){
      const dias = diffDaysInclusive(d1, d2);
      inpDias.value = String(dias);
      const precio = rawNumber(inpPrecio.value);
      if (precio > 0){
        inpTotal.value = fmtMiles(dias * precio);
      }
    } else {
      inpDias.value = "";
    }
  }

  // Reacciones
  ["change","blur","keyup"].forEach(ev=>{
    inpInicio.addEventListener(ev, recompute);
    inpFin.addEventListener(ev, recompute);
    inpPrecio.addEventListener(ev, recompute);
  });

  // RUT formateado
  function fmtRUT(val){
    val = (val || "").replace(/[^0-9kK]/g, "").toUpperCase();
    if(!val) return "";
    const cuerpo = val.slice(0, -1);
    const dv = val.slice(-1);
    const cuerpoFmt = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (cuerpoFmt ? cuerpoFmt + "-" : "") + dv;
  }
  function rawRUT(val){
    val = (val || "").toUpperCase().replace(/[^0-9kK-\.]/g, "").replace(/\./g,"");
    if(!/-/.test(val) and val.length>1){
      return val[:-1] + "-" + val[-1];
    }
    return val;
  }
  document.querySelectorAll('input.rut').forEach(inp=>{
    inp.addEventListener('input', ()=>{
      const posRight = inp.value.length - (inp.selectionStart || 0);
      inp.value = fmtRUT(inp.value);
      const newPos = Math.max(0, inp.value.length - posRight);
      inp.setSelectionRange(newPos, newPos);
    });
    inp.addEventListener('blur', ()=>{ inp.value = fmtRUT(inp.value); });
    if (inp.form){
      inp.form.addEventListener('submit', ()=>{ inp.value = rawRUT(inp.value); });
    }
  });

  // Teléfono con +
  function normalizePhone(val){
    val = (val || "").replace(/\s+/g, "");
    val = "+" + val.replace(/^\+/, "").replace(/\D+/g, "");
    return val;
  }
  document.querySelectorAll('input.fono').forEach(inp=>{
    if (inp.value) inp.value = normalizePhone(inp.value);
    inp.addEventListener('input', ()=>{
      const digits = inp.value.replace(/\D+/g,"");
      inp.value = "+" + digits;
    });
    inp.addEventListener('blur', ()=>{ inp.value = normalizePhone(inp.value); });
  });

  // Año a 4 dígitos
  document.querySelectorAll('input.anio').forEach(inp=>{
    inp.addEventListener('input', ()=>{
      inp.value = (inp.value || '').replace(/\D+/g,'').slice(0,4);
    });
  });

  // Prefill: si ya hay fechas, calcular días al abrir
  recompute();
});
</script>
"""

CONTRATO_FULL_HTML = r"""
<style>
  .contrato { max-width: 900px; margin: 0 auto; padding: 24px; background: #fff; color:#111; }
  .encabezado { display:flex; justify-content: space-between; align-items:center; margin-bottom:16px; }
  .acciones a { margin-right:8px; }
  .titulo { font-size:20px; margin:12px 0 18px 0; }
  .bloque { margin: 14px 0; }
  .sub { font-weight:600; margin-bottom:6px; }
  .tabla { width:100%; border-collapse: collapse; margin-top:6px; }
  .tabla td { padding:6px 8px; vertical-align:top; }
  .check span { display:inline-block; border:1px solid #999; width:14px; height:14px; margin-right:6px; }
  @media print {
    .acciones { display:none; }
    body { background:#fff; }
    .contrato { box-shadow:none; }
  }
</style>

<div class="contrato">
    <div class="encabezado">
    <div class="acciones">
      <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('contratos.lista') }}">Volver</a>
      <a class="btn btn-primary btn-sm" href="#" onclick="window.print()">Imprimir</a>
    </div>
    <div style="text-align:right;">
      <img src="{{ url_for('static', filename='img/logo_formal.png') }}"
           alt="Ruta Sur Rent A Car"
           style="height:60px; display:block; margin-left:auto; margin-bottom:4px;">
      <div>Contrato #{{ c.id }}</div>
    </div>
  </div>

  <div class="titulo">CONTRATO DE ARRIENDO DE VEHÍCULO</div>

  <div class="bloque">
    Entre: Don Víctor Alejandro Céspedes Guichamán, RUT 17.238.541-9, representante de Ruta Sur Rent A Car,
    con domicilio en la ciudad de Punta Arenas, en adelante el ARRENDADOR; y
    Sr(a) {{ c.cliente_nombre }} {{ c.cliente_apellido }}, RUT {{ c.cliente_rut or '—' }}, nacionalidad {{ c.cliente_nacionalidad or '—' }},
    domicilio {{ c.cliente_domicilio or '—' }}, teléfono {{ c.cliente_telefono or '—' }}, correo electrónico {{ c.cliente_email or '—' }},
    en adelante el ARRENDATARIO; se celebra el siguiente contrato, que se regirá por las cláusulas que siguen:
  </div>

  <div class="bloque">
  <div class="sub">1. Identificación del vehículo</div>
  <table class="tabla">
    <tr><td>Descripción:</td><td>{{ _vehiculo_label(c) }}</td></tr>
    <tr><td>Marca:</td><td>{{ c.vehiculo_marca or c.veh_marca or '—' }}</td></tr>
    <tr><td>Modelo:</td><td>{{ c.vehiculo_modelo or c.veh_modelo or '—' }}</td></tr>
    <tr><td>Año:</td><td>{{ c.vehiculo_anio or c.veh_anio or '—' }}</td></tr>
    <tr><td>Patente:</td><td>{{ c.vehiculo_patente or c.veh_patente or '—' }}</td></tr>
  </table>
</div>

  <div class="bloque">
    <div class="sub">2. Duración y monto del arriendo</div>
    <table class="tabla">
      <tr><td>Desde:</td><td>{{ c.desde or '—' }}</td></tr>
      <tr><td>Hasta:</td><td>{{ c.hasta or '—' }}</td></tr>
      <tr><td>Días:</td><td>{{ dias or 0 }}</td></tr>
      <tr><td>Valor total:</td><td>$ {{ monto_fmt }}</td></tr>
    </table>
  </div>

  <div class="bloque">
    <div class="sub">3. Condiciones del vehículo y uso</div>
    a) El vehículo se entrega en buen estado mecánico, con estanque lleno, y debe devolverse en iguales condiciones.<br>
    b) Solo podrá ser conducido por el ARRENDATARIO, quien declara poseer licencia de conducir vigente.<br>
    c) Cualquier daño, multa, pérdida de llave o documento será de exclusiva responsabilidad del ARRENDATARIO.<br>
    d) El vehículo podrá salir a territorio argentino únicamente con autorización escrita del ARRENDADOR.<br>
    e) El vehículo debe devolverse a más tardar a las 21:00 horas, salvo acuerdo previo.
  </div>

  <div class="bloque">
    <div class="sub">4. Condiciones de arriendo</div>
    • No se solicita garantía, solo documentación al día (licencia de conducir y cédula).<br>
    • Se requiere un pago de $20.000 como reserva, descontable del total.<br>
    • No se permite fumar dentro del vehículo.<br>
    • Pinchazo de neumático: $8.000.<br>
    • Neumático irreparable: $40.000.
  </div>

  <div class="bloque">
    <div class="sub">5. Autorización y responsabilidad</div>
    El ARRENDATARIO reconoce haber recibido el vehículo en buen estado, se compromete a utilizarlo conforme a la ley
    y acepta que cualquier infracción, daño o pérdida durante el arriendo será de su exclusiva responsabilidad.
  </div>

  <div class="bloque">
    <div class="sub">6. Checklist de entrega y recepción</div>
    Combustible: [   ] Completo   [   ] ¾   [   ] ½   [   ] ¼<br>
    Estado exterior: [   ] Sin daños   [   ] Detalles menores   [   ] Rayas visibles<br>
    Accesorios: [   ] Gata   [   ] Llave de ruedas   [   ] Extintor   [   ] Rueda de repuesto<br>
    Observaciones: _____________________________________________
  </div>

  <div class="bloque">
    <div class="sub">7. Declaración final</div>
    El ARRENDATARIO declara haber revisado el vehículo, encontrándolo conforme, y se compromete a devolverlo en las mismas condiciones.
  </div>

  <div class="bloque" style="margin-top:28px;">
    En Punta Arenas, a {{ hoy.strftime('%d-%m-%Y') }}.
  </div>

  <div class="bloque" style="margin-top:40px;">
    ARRENDATARIO: ____________________________________<br>
    Nombre: {{ c.cliente_nombre }} {{ c.cliente_apellido }}<br>
    RUT: {{ c.cliente_rut or '—' }}
  </div>
</div>
"""
PRINT_HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Contrato #{{ c.id }}</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; font-size: 12pt; color: #111; margin: 24px; }
    h1 { font-size: 18pt; margin: 0 0 12px 0; }
    h2 { font-size: 14pt; margin: 18px 0 8px 0; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; }
    .label { color: #555; font-size: 10pt; }
    .value { margin-bottom: 6px; }
    .row { margin-bottom: 8px; }
    .hr { border-top: 1px solid #ccc; margin: 16px 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
    .firma { margin-top: 40px; }
    .firma .linea { border-top: 1px solid #000; width: 60%; margin-top: 48px; }
    @page { size: A4; margin: 20mm; }
  </style>
</head>
<body>
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
    <img src="{{ url_for('static', filename='img/logo_formal.png') }}"
         alt="Ruta Sur Rent A Car"
         style="height:60px;">
    <h1>Contrato de arriendo de vehículo #{{ c.id }}</h1>
  </div>

  <h2>Partes</h2>
  <div class="row">
    Arrendador: Víctor Alejandro Céspedes Guichamán, RUT 17.238.541-9, Ruta Sur Rent A Car, Punta Arenas.
  </div>
  <div class="row">
    Arrendatario: {{ c.cliente_nombre }} {{ c.cliente_apellido }}, RUT {{ c.cliente_rut or '—' }}, nacionalidad {{ c.cliente_nacionalidad or '—' }}, teléfono {{ c.cliente_telefono or '—' }}, correo {{ c.cliente_email or '—' }}.
  </div>

  <h2>Identificación del vehículo</h2>
  <div class="grid">
    <div>
      <div class="label">Marca</div>
      <div class="value mono">{{ c.vehiculo_marca or '—' }}</div>
    </div>
    <div>
      <div class="label">Modelo</div>
      <div class="value mono">{{ c.vehiculo_modelo or '—' }}</div>
    </div>
    <div>
      <div class="label">Año</div>
      <div class="value mono">{{ c.vehiculo_anio or '—' }}</div>
    </div>
    <div>
      <div class="label">Patente</div>
      <div class="value mono">{{ c.vehiculo_patente or '—' }}</div>
    </div>
  </div>

  <h2>Duración y monto</h2>
  <div class="grid">
    <div>
      <div class="label">Desde</div>
      <div class="value mono">{{ c.desde }}</div>
    </div>
    <div>
      <div class="label">Hasta</div>
      <div class="value mono">{{ c.hasta }}</div>
    </div>
    <div>
      <div class="label">Monto total</div>
      <div class="value mono">$ {{ '{:,}'.format(c.monto or 0).replace(',','.') }}</div>
    </div>
    <div>
      <div class="label">Estado</div>
      <div class="value mono">{{ c.estado|capitalize }}</div>
    </div>
  </div>

  <div class="hr"></div>

  <h2>Condiciones</h2>
  <div class="row">a) El vehículo se entrega en buen estado mecánico, con estanque lleno y debe devolverse en iguales condiciones.</div>
  <div class="row">b) Solo podrá ser conducido por el arrendatario con licencia vigente.</div>
  <div class="row">c) Daños, multas, pérdidas de llave o documentos: responsabilidad del arrendatario.</div>
  <div class="row">d) Salida a Argentina solo con autorización escrita del arrendador.</div>
  <div class="row">e) Devolución a más tardar 21:00 horas, salvo acuerdo previo.</div>

  <h2>Condiciones de arriendo</h2>
  <div class="row">No se solicita garantía, solo documentación al día. Reserva de $20.000 se descuenta del total. Prohibido fumar.</div>
  <div class="row">Pinchazo: $8.000. Neumático irreparable: $40.000.</div>

  <h2>Observaciones</h2>
  <div class="row">{{ c.obs or '—' }}</div>

  <div class="firma">
    <div>En Punta Arenas, a ____ de __________________ de 20____.</div>
    <div class="linea"></div>
    <div>Firma arrendatario</div>
    <div>RUT: __________________________</div>
  </div>
</body>
</html>
"""
# ===== Helpers de formateo y plantilla del contrato =====
from io import BytesIO
from flask import send_file

def _parse_dmy(s):
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None

def _vehiculo_label(c: dict) -> str:
    # Soporta registros nuevos (marca/modelo/año separados) y antiguos (modelo con todo)
    marca   = (c.get("vehiculo_marca") or c.get("veh_marca") or "").strip()
    modelo  = (c.get("vehiculo_modelo") or c.get("veh_modelo") or "").strip()
    anio    = (c.get("vehiculo_anio") or c.get("veh_anio") or "").strip()
    patente = (c.get("vehiculo_patente") or c.get("veh_patente") or "").strip()

    if marca or anio:
        base = " ".join(x for x in [marca, modelo, anio] if x)
    else:
        # fallback legado: solo modelo (que podría traer "Chevrolet Trax 2016")
        base = modelo

    return (base + (f" · {patente}" if patente else "")).strip()

def _dias_inclusivos(d1, d2):
    if not d1 or not d2:
        return 0
    return max(1, (d2 - d1).days + 1)

def _fmt_miles(n):
    try:
        s = str(int(n))
    except Exception:
        s = "0"
    return s.replace(",", "").replace(".", "").replace("\u202f","").replace("\u00a0","")
    # not used directly; usamos format en jinja

def _build_contrato_context(c):
    # Soporta nombres antiguos o nuevos de los campos
    marca   = c.get("vehiculo_marca") or c.get("veh_marca") or ""
    modelo  = c.get("vehiculo_modelo") or c.get("veh_modelo") or ""
    anio    = c.get("vehiculo_anio") or c.get("veh_anio") or ""
    patente = c.get("vehiculo_patente") or ""

    # Derivar desde formato legado si faltan marca o año pero modelo trae todo junto
    if (not marca or not anio) and modelo and (" " in modelo):
        d_marca, d_modelo, d_anio = _split_modelo_legacy(modelo)
        if not marca and d_marca:
            marca = d_marca
        if d_modelo and d_modelo != modelo:
            modelo = d_modelo
        if not anio and d_anio:
            anio = d_anio

    d1 = _parse_dmy(c.get("desde"))
    d2 = _parse_dmy(c.get("hasta"))
    dias = _dias_inclusivos(d1, d2)

    ctx = {
        "id": c.get("id"),
        "arrendador_nombre": "Víctor Alejandro Céspedes Guichamán",
        "arrendador_rut": "17.238.541-9",
        "arrendador_razon": "Ruta Sur Rent A Car",
        "arrendador_ciudad": "Punta Arenas",

        "cli_nombre": c.get("cliente_nombre") or "",
        "cli_apellido": c.get("cliente_apellido") or "",
        "cli_rut": c.get("cliente_rut") or "",
        "cli_nacionalidad": c.get("cliente_nacionalidad") or "",
        "cli_tel": c.get("cliente_telefono") or "",
        "cli_mail": c.get("cliente_email") or "",

        "veh_marca": marca,
        "veh_modelo": modelo,
        "veh_anio": anio,
        "veh_patente": patente,

        "desde": c.get("desde") or "",
        "hasta": c.get("hasta") or "",
        "dias_total": dias,
        "monto": int(c.get("monto") or 0),
        "estado": c.get("estado") or "borrador",
        "obs": c.get("obs") or "",
    }
    return ctx

def _vehiculo_label(c):
    """Devuelve una descripción uniforme del vehículo, compatible con datos viejos y nuevos."""
    import re

    marca = c.get("vehiculo_marca") or c.get("veh_marca") or ""
    modelo = c.get("vehiculo_modelo") or c.get("veh_modelo") or ""
    anio = c.get("vehiculo_anio") or c.get("veh_anio") or ""
    patente = c.get("vehiculo_patente") or c.get("veh_patente") or ""

    # Si no hay marca o año, intentar extraerlos desde un texto tipo "Chevrolet Trax 2016"
    if (not marca or not anio) and modelo:
        m = re.match(r"^\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\-\&\.\/]+)\s+(.*?)(?:\s+(\d{4}))?\s*$", modelo)
        if m:
            d_marca = (m.group(1) or "").strip()
            d_modelo = (m.group(2) or "").strip()
            d_anio = (m.group(3) or "").strip() if m.lastindex and m.group(3) else ""
            if not marca and d_marca:
                marca = d_marca
            if d_modelo and d_modelo != modelo:
                modelo = d_modelo
            if not anio and d_anio:
                anio = d_anio

    partes = [p for p in [marca, modelo, anio] if p]
    label = " ".join(partes) if partes else (modelo or "—")

    if patente:
        label += f" · {patente}"

    return label.strip()

CONTRATO_DOC_HTML = r"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Contrato #{{ ctx.id or '' }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; line-height:1.35; padding:20px; color:#111;}
  h1,h2,h3{ margin:0 0 .5rem 0; }
  .muted{ color:#666; }
  .grid{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px 24px; }
  .section{ margin: 16px 0; }
  .hr{ height:1px; background:#ddd; margin:16px 0; }
  .field{ margin: 3px 0; }
  .title{ font-weight:600; margin-bottom:6px; }
  .print-toolbar{ position:sticky; top:0; background:#f8f9fa; padding:8px; border:1px solid #e5e7eb; border-radius:8px; display:flex; gap:8px; margin-bottom:12px;}
  .btn{ display:inline-block; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; text-decoration:none; color:#111; background:#fff;}
  .btn-primary{ background:#2563eb; color:#fff; border-color:#2563eb; }
  .btn-outline{ background:#fff; }
  @media print{
    .print-toolbar{ display:none; }
    body{ padding:0; }
  }
</style>
</head>
<body>

<div class="print-toolbar">
  <a class="btn btn-outline" href="{{ url_for('contratos.lista') }}">Volver</a>
  <a class="btn btn-primary" href="#" onclick="window.print();return false;">Imprimir</a>
</div>

<img src="{{ url_for('static', filename='img/logo_formal.png') }}"
     alt="Ruta Sur Rent A Car"
     style="height:60px; margin:12px 0;">

<h2>CONTRATO DE ARRIENDO DE VEHÍCULO</h2>
<p class="muted">Contrato #{{ ctx.id or '' }} — Estado: {{ ctx.estado|capitalize }}</p>

<div class="section">
  Entre: Don {{ ctx.arrendador_nombre }}, RUT {{ ctx.arrendador_rut }}, representante de {{ ctx.arrendador_razon }},
  con domicilio en la ciudad de {{ ctx.arrendador_ciudad }}, en adelante el ARRENDADOR, y
  Sr(a) {{ ctx.cli_nombre }} {{ ctx.cli_apellido }}, RUT {{ ctx.cli_rut }}, nacionalidad {{ ctx.cli_nacionalidad }},
  teléfono {{ ctx.cli_tel }}, correo {{ ctx.cli_mail }}, en adelante el ARRENDATARIO, se celebra el siguiente contrato de arriendo de vehículo:
</div>

<div class="hr"></div>

<div class="section">
  <div class="title">1. IDENTIFICACIÓN DEL VEHÍCULO</div>
  <div class="grid">
    <div class="field"><b>Marca:</b> {{ ctx.veh_marca }}</div>
    <div class="field"><b>Modelo:</b> {{ ctx.veh_modelo }}</div>
    <div class="field"><b>Año:</b> {{ ctx.veh_anio }}</div>
    <div class="field"><b>Patente:</b> {{ ctx.veh_patente }}</div>
  </div>
</div>

<div class="section">
  <div class="title">2. DURACIÓN Y MONTO DEL ARRIENDO</div>
  <div class="field"><b>Desde:</b> {{ ctx.desde }}</div>
  <div class="field"><b>Hasta:</b> {{ ctx.hasta }}</div>
  <div class="field"><b>Días totales:</b> {{ ctx.dias_total }}</div>
  <div class="field"><b>Valor total del arriendo:</b> $ {{ "{:,}".format(ctx.monto).replace(",", ".") }}</div>
</div>

<div class="section">
  <div class="title">3. CONDICIONES DEL VEHÍCULO Y USO</div>
  <ol>
    <li>El vehículo se entrega en buen estado mecánico, con estanque lleno y debe devolverse en iguales condiciones.</li>
    <li>Solo podrá ser conducido por el ARRENDATARIO, quien declara poseer licencia de conducir vigente.</li>
    <li>Cualquier daño, multa, pérdida de llave o documento será de exclusiva responsabilidad del ARRENDATARIO.</li>
    <li>El vehículo podrá salir a territorio argentino únicamente con autorización escrita del ARRENDADOR.</li>
    <li>El vehículo debe ser devuelto a más tardar a las 21:00 horas, salvo acuerdo previo entre las partes.</li>
  </ol>
</div>

<div class="section">
  <div class="title">4. CONDICIONES DE ARRIENDO</div>
  <ul>
    <li>No se solicita garantía, solo documentación al día (licencia de conducir y cédula de identidad).</li>
    <li>Se requiere un pago de $20.000 como reserva de fecha, que se descuenta del total del arriendo.</li>
    <li>No se permite fumar dentro del vehículo.</li>
    <li>Pinchazo de neumático: costo de reparación $8.000.</li>
    <li>Neumático dañado irreparablemente: costo de reemplazo $40.000.</li>
  </ul>
</div>

<div class="section">
  <div class="title">5. AUTORIZACIÓN Y RESPONSABILIDAD</div>
  <p>El ARRENDATARIO reconoce haber recibido el vehículo en buen estado, se compromete a utilizarlo conforme a la ley y declara comprender que cualquier infracción, daño o pérdida durante el arriendo será de su exclusiva responsabilidad.</p>
</div>

<div class="section">
  <div class="title">6. CHECKLIST DE ENTREGA Y RECEPCIÓN</div>
  <p>Combustible: [ ] Completo  [ ] ¾  [ ] ½  [ ] ¼</p>
  <p>Estado exterior: [ ] Sin daños  [ ] Detalles menores  [ ] Rayas visibles</p>
  <p>Accesorios: [ ] Gata  [ ] Llave de ruedas  [ ] Extintor  [ ] Rueda de repuesto</p>
  <p>Observaciones: {{ ctx.obs or '—' }}</p>
</div>

<div class="section">
  <div class="title">7. DECLARACIÓN FINAL</div>
  <p>El ARRENDATARIO declara haber revisado el vehículo, encontrándolo conforme, y se compromete a devolverlo en las mismas condiciones.</p>
  <p>En {{ ctx.arrendador_ciudad }}, a ____ de __________________ de 20____.</p>
</div>

<div class="hr"></div>

<div class="section">
  <div>ARRENDATARIO:</div>
  <div style="height:60px;"></div>
  <div>_____________________________</div>
  <div>Nombre completo</div>
  <div>RUT __________________________</div>
</div>

</body>
</html>
"""
# =======================
#        RUTAS
# =======================

@contratos_bp.route("/")
def lista():
    contratos = _load_contracts()
    # ordenar por fecha desde (DD-MM-YYYY) descendente
    def key_d(c):
        d = parse_dmy(c.get("desde"))
        return d or date(1900,1,1)
    contratos = sorted(contratos, key=key_d, reverse=True)
    html = render_template_string(LIST_HTML, contratos=contratos, _vehiculo_label=_vehiculo_label)
    return render_admin_bp(html, active="contratos")

@contratos_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        contratos = _load_contracts()
        def next_id():
            return (max([c["id"] for c in contratos]) + 1) if contratos else 1

        # normaliza monto_total -> int
        raw_monto = (request.form.get("monto_total") or "").replace(".", "").strip()
        try:
            monto = int(raw_monto) if raw_monto else 0
        except ValueError:
            monto = 0

        c = {
            "id": next_id(),

            "cliente_nombre": (request.form.get("cliente_nombre") or "").strip(),
            "cliente_apellido": (request.form.get("cliente_apellido") or "").strip(),
            "cliente_rut": (request.form.get("cliente_rut") or "").strip(),
            "cliente_telefono": (request.form.get("cliente_telefono") or "").strip(),
            "cliente_email": (request.form.get("cliente_email") or "").strip(),
            "cliente_nacionalidad": (request.form.get("cliente_nacionalidad") or "").strip(),

            "vehiculo_marca": (request.form.get("veh_marca") or "").strip(),
            "vehiculo_modelo": (request.form.get("veh_modelo") or "").strip(),
            "vehiculo_anio": (request.form.get("veh_anio") or "").strip(),
            "vehiculo_patente": (request.form.get("veh_patente") or "").strip(),

            "desde": (request.form.get("fecha_inicio") or "").strip(),  # DD-MM-YYYY
            "hasta": (request.form.get("fecha_fin") or "").strip(),     # DD-MM-YYYY
            "monto": monto,
            "estado": (request.form.get("estado") or "borrador").strip(),
            "obs": (request.form.get("observaciones") or "").strip(),

            # opcional: guardar vínculo a evento del calendario
            "evento_id": None,
        }
        contratos.append(c)
        _save_contracts(contratos)
        return redirect(url_for("contratos.lista"))

    html = render_template_string(FORM_HTML, c_default=None)
    return render_admin_bp(html, active="contratos")

@contratos_bp.route("/<int:cid>")
def ver(cid):
    contratos = _load_contracts()
    c = next((x for x in contratos if x["id"] == cid), None)
    if not c:
        return "Contrato no encontrado", 404

    # días entre desde y hasta (formato DD-MM-YYYY), inclusivo
    di = parse_dmy(c.get("desde"))
    df = parse_dmy(c.get("hasta"))
    dias = ((df - di).days + 1) if (di and df) else 0

    monto_fmt = "{:,}".format(int(c.get("monto") or 0)).replace(",", ".")
    html = render_template_string(
    CONTRATO_FULL_HTML,
    c=c, dias=dias, monto_fmt=monto_fmt, hoy=date.today(),
    _vehiculo_label=_vehiculo_label
    )
    current_app.jinja_env.globals["_vehiculo_label"] = _vehiculo_label
    return render_admin_bp(html, active="contratos")

@contratos_bp.route("/desde-reserva/<int:eid>", methods=["GET", "POST"])
def desde_reserva(eid):
    # carga datos del calendario sin crear dependencia circular a nivel módulo
    from calendario_bp import load_eventos, load_vehiculos

    eventos = load_eventos()
    vehiculos = load_vehiculos()

    ev = next((x for x in eventos if int(x.get("id") or 0) == eid), None)
    if not ev:
        return "Reserva no encontrada", 404

    v = next((x for x in vehiculos if int(x.get("id") or 0) == int(ev.get("vehiculo_id") or 0)), None)

    # Prefill desde la reserva
    cliente = ev.get("cliente") or {}
    nombre = (ev.get("cliente_nombre") or cliente.get("nombre") or ev.get("nombre") or "").strip()
    apellido = (ev.get("cliente_apellido") or cliente.get("apellido") or ev.get("apellido") or "").strip()
    rut = (cliente.get("rut") or ev.get("rut") or ev.get("cliente_rut") or "").strip()
    tel = (cliente.get("telefono") or ev.get("telefono") or ev.get("cliente_telefono") or "").strip()
    correo = (cliente.get("email") or ev.get("email") or ev.get("correo") or ev.get("cliente_email") or "").strip()
    nac = (cliente.get("nacionalidad") or ev.get("nacionalidad") or "").strip()

    desde = iso_to_dmy(ev.get("inicio"))
    hasta = iso_to_dmy(ev.get("fin"))
    monto = int(ev.get("total_amount") or 0)

    c_default = {
        "cliente_nombre": nombre,
        "cliente_apellido": apellido,
        "cliente_rut": rut,
        "cliente_telefono": tel,
        "cliente_email": correo,
        "cliente_nacionalidad": nac,

        "vehiculo_marca": (v.get("marca") if v else ""),
        "vehiculo_modelo": (v.get("modelo") if v else ""),
        "vehiculo_anio": (v.get("anio") if v else ""),
        "vehiculo_patente": (v.get("patente") if v else ""),

        "desde": desde,
        "hasta": hasta,
        "monto": monto,
        "estado": "vigente",
        "obs": (ev.get("tooltip") or ev.get("label") or ""),
        "evento_id": eid,
    }

    if request.method == "POST":
        contratos = _load_contracts()
        def next_id():
            return (max([c["id"] for c in contratos]) + 1) if contratos else 1

        raw_monto = (request.form.get("monto_total") or "").replace(".", "").strip()
        try:
            monto_val = int(raw_monto) if raw_monto else 0
        except ValueError:
            monto_val = 0

        c = {
            "id": next_id(),

            "cliente_nombre": (request.form.get("cliente_nombre") or "").strip(),
            "cliente_apellido": (request.form.get("cliente_apellido") or "").strip(),
            "cliente_rut": (request.form.get("cliente_rut") or "").strip(),
            "cliente_telefono": (request.form.get("cliente_telefono") or "").strip(),
            "cliente_email": (request.form.get("cliente_email") or "").strip(),
            "cliente_nacionalidad": (request.form.get("cliente_nacionalidad") or "").strip(),

            "vehiculo_marca": (request.form.get("veh_marca") or "").strip(),
            "vehiculo_modelo": (request.form.get("veh_modelo") or "").strip(),
            "vehiculo_anio": (request.form.get("veh_anio") or "").strip(),
            "vehiculo_patente": (request.form.get("veh_patente") or "").strip(),

            "desde": (request.form.get("fecha_inicio") or "").strip(),
            "hasta": (request.form.get("fecha_fin") or "").strip(),
            "monto": monto_val,
            "estado": (request.form.get("estado") or "vigente").strip(),
            "obs": (request.form.get("observaciones") or "").strip(),
            "evento_id": eid,
        }
        contratos.append(c)
        _save_contracts(contratos)
        return redirect(url_for("contratos.lista"))

    html = render_template_string(FORM_HTML, c_default=c_default)
    return render_admin_bp(html, active="contratos")

@contratos_bp.route("/<int:cid>/vista")
def vista(cid):
    contratos = _load_contracts()
    c = next((x for x in contratos if x["id"] == cid), None)
    if not c:
        return "Contrato no encontrado", 404
    ctx = _build_contrato_context(c)
    # Renderizamos SOLO el documento, sin layout/admin
    html_doc = render_template_string(CONTRATO_DOC_HTML, ctx=ctx, _vehiculo_label=_vehiculo_label)
    return html_doc


@contratos_bp.route("/<int:cid>/pdf")
def descargar_pdf(cid):
    contratos = _load_contracts()
    c = next((x for x in contratos if x["id"] == cid), None)
    if not c:
        return "Contrato no encontrado", 404

    # Renderiza el HTML imprimible
    html_str = render_template_string(PRINT_HTML, c=c)

    # Si no está disponible WeasyPrint, muestra el mismo aviso que viste antes
    if not WEASY_OK:
        msg = (
            "No se pudo generar el PDF en el servidor.<br>"
            "Para habilitar la descarga directa en PDF, instala WeasyPrint:<br>"
            "<code>pip install weasyprint</code><br>"
            "Mientras tanto, puedes usar el botón “Imprimir” en la vista del contrato y elegir “Guardar como PDF”."
        )
        return render_admin_bp(f"<div class='alert alert-warning'>{msg}</div>", active="contratos")

    # Genera PDF en memoria
    try:
        pdf_bytes = HTML(string=html_str, base_url=request.url_root).write_pdf()
        fname = f"contrato_{cid}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={fname}"
            },
        )
    except Exception:
        current_app.logger.exception("Error generando PDF con WeasyPrint")
        return render_admin_bp("<div class='alert alert-danger'>Error al generar el PDF.</div>", active="contratos")
    
@contratos_bp.route("/eliminar", methods=["POST"])
def eliminar():
    data = request.get_json(silent=True) or {}
    cid = int(data.get("id") or 0)
    contratos = _load_contracts()
    nuevos = [c for c in contratos if int(c.get("id") or 0) != cid]
    if len(nuevos) == len(contratos):
        return {"error": "No encontrado"}, 404
    _save_contracts(nuevos)
    return {"ok": True}