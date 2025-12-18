# finanzas_bp.py
from flask import Blueprint, current_app, render_template_string, request
from datetime import datetime, date
import os, json 

# Usamos las mismas funciones que contratos para leer eventos y vehículos
from calendario_bp import load_eventos, load_vehiculos

finanzas_bp = Blueprint("finanzas", __name__, url_prefix="/admin/finanzas")

def render_admin_bp(html, active="finanzas"):
    """
    Envuelve el HTML dentro del layout base (la plantilla que tiene el sidebar, topbar, etc.)
    """
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)

# =========================
#   PLANTILLA DE FINANZAS
# =========================

FINANZAS_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">Finanzas</h3>
</div>

<form id="filtrosFinanzas" class="card border-0 shadow-sm mb-3" method="get">
  <div class="card-body row g-2 align-items-end">
    <div class="col-md-3">
      <label class="form-label small mb-1">Año</label>
      <select class="form-select form-select-sm" name="year">
        {% for y in years %}
          <option value="{{ y }}" {{ 'selected' if y == year else '' }}>{{ y }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label small mb-1">Mes</label>
      <select class="form-select form-select-sm" name="month">
        {% for code, label in months %}
          <option value="{{ code }}" {{ 'selected' if code == month else '' }}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-4">
      <label class="form-label small mb-1">Vehículo</label>
      <select class="form-select form-select-sm" name="veh">
        <option value="all" {{ 'selected' if veh == 'all' else '' }}>— Todos los vehículos —</option>
        {% for v in vehiculos %}
          <option value="{{ v.id }}" {{ 'selected' if veh == v.id|string else '' }}>
            {{ v.patente }} · {{ v.marca }} {{ v.modelo }} {{ v.anio }}
          </option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-2 text-end">
      <button class="btn btn-primary btn-sm w-100" type="submit">Actualizar</button>
    </div>
  </div>
</form>

<!-- TARJETAS: INGRESOS -->
<div class="row g-3 mb-3">
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">
          Ingresos del mes ({{ month_label }} {{ year }})
        </div>
        <div class="h4 mb-0 text-success">
          $ {{ '{:,.0f}'.format(summary.ingresos_mes or 0).replace(',', '.') }}
        </div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">
          Ingresos del año ({{ year }})
        </div>
        <div class="h4 mb-0 text-success">
          $ {{ '{:,.0f}'.format(summary.ingresos_anual or 0).replace(',', '.') }}
        </div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">Reservas consideradas</div>
        <div class="h4 mb-0">{{ summary.cant_reservas or 0 }}</div>
      </div>
    </div>
  </div>
</div>

<!-- TARJETAS: GASTOS Y NETO -->
<div class="row g-3 mb-3">
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">
          Gastos del mes ({{ month_label }} {{ year }})
        </div>
        <div class="h4 mb-0 text-danger">
          $ {{ '{:,.0f}'.format(summary.gastos_mes or 0).replace(',', '.') }}
        </div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">
          Gastos del año ({{ year }})
        </div>
        <div class="h4 mb-0 text-danger">
          $ {{ '{:,.0f}'.format(summary.gastos_anual or 0).replace(',', '.') }}
        </div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">Resultado neto (mes)</div>
        <div class="h4 mb-1 text-warning">
          $ {{ '{:,.0f}'.format(summary.neto_mes or 0).replace(',', '.') }}
        </div>
        <div class="small text-secondary">
          Neto anual {{ year }}:
          <span class="text-warning">
            $ {{ '{:,.0f}'.format(summary.neto_anual or 0).replace(',', '.') }}
          </span>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="row g-3 mb-3">
  <div class="col-md-6">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="mb-0">Ingresos por mes ({{ year }})</h6>
        </div>
        <canvas id="chartMeses" style="max-height:260px;"></canvas>
      </div>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="mb-0">Ingresos por vehículo</h6>
        </div>
        <canvas id="chartVehiculos" style="max-height:260px;"></canvas>
      </div>
    </div>
  </div>
</div>

<!-- NUEVO: gráfico de resultado neto por mes -->
<div class="row g-3 mb-3">
  <div class="col-md-12">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <h6 class="mb-0">Resultado neto por mes ({{ year }})</h6>
        </div>
        <canvas id="chartNetos" style="max-height:260px;"></canvas>
      </div>
    </div>
  </div>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <h6 class="mb-3">Detalle de reservas</h6>
    {% if rows %}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Vehículo</th>
              <th>Cliente</th>
              <th class="text-end">Monto</th>
            </tr>
          </thead>
          <tbody>
          {% for r in rows %}
            <tr>
              <td>{{ r.fecha }}</td>
              <td>{{ r.vehiculo }}</td>
              <td>{{ r.cliente }}</td>
              <td class="text-end">$ {{ '{:,.0f}'.format(r.monto or 0).replace(',', '.') }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="text-secondary small">No hay reservas para este filtro.</div>
    {% endif %}
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
  const datosMeses = {{ chart_meses|tojson }};
  const datosNetos = {{ chart_netos|tojson }};
  const datosVehiculos = {{ chart_vehiculos|tojson }};

  // Helper: formato chileno de miles con puntos
  function fmtMiles(n){
    if (typeof n !== 'number') {
      n = Number(n) || 0;
    }
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  // Helper: convertir número de mes (01, 02, 03...) a abreviatura (Ene, Feb, Mar...)
  function nombreMes(num){
    const nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    const idx = parseInt(num, 10) - 1;
    return nombres[idx] || num;
  }

  document.addEventListener('DOMContentLoaded', function(){
    // Gráfico mensual de ingresos (barras verdes)
    const ctxM = document.getElementById('chartMeses');
    if (ctxM && datosMeses.length){
      new Chart(ctxM, {
        type: 'bar',
        data: {
          labels: datosMeses.map(d => nombreMes(d.label)),
          datasets: [{
            label: 'Ingresos',
            data: datosMeses.map(d => d.monto),
            backgroundColor: '#22c55e' // verde
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display:false },
            tooltip: {
              callbacks: {
                label: function(context){
                  const v = context.parsed.y || 0;
                  return 'Ingresos: $ ' + fmtMiles(v);
                }
              }
            }
          },
          scales: {
            y: {
              beginAtZero:true,
              ticks: {
                callback: function(value) {
                  return '$ ' + fmtMiles(value);
                }
              }
            }
          }
        }
      });
    }

    // Gráfico por vehículo (también ingresos, barras verdes)
    const ctxV = document.getElementById('chartVehiculos');
    if (ctxV && datosVehiculos.length){
      new Chart(ctxV, {
        type: 'bar',
        data: {
          labels: datosVehiculos.map(d => d.label),
          datasets: [{
            label: 'Ingresos',
            data: datosVehiculos.map(d => d.monto),
            backgroundColor: '#22c55e'
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          plugins: {
            legend: { display:false },
            tooltip: {
              callbacks: {
                label: function(context){
                  const v = context.parsed.x || 0;
                  return 'Ingresos: $ ' + fmtMiles(v);
                }
              }
            }
          },
          scales: {
            x: {
              beginAtZero:true,
              ticks: {
                callback: function(value) {
                  return '$ ' + fmtMiles(value);
                }
              }
            }
          }
        }
      });
    }

    // Nuevo: gráfico de resultado neto por mes (barras amarillas)
    const ctxN = document.getElementById('chartNetos');
    if (ctxN && datosNetos.length){
      new Chart(ctxN, {
        type: 'bar',
        data: {
          labels: datosNetos.map(d => nombreMes(d.label)),
          datasets: [{
            label: 'Resultado neto',
            data: datosNetos.map(d => d.monto),
            backgroundColor: '#eab308' // amarillo
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display:false },
            tooltip: {
              callbacks: {
                label: function(context){
                  const v = context.parsed.y || 0;
                  return 'Neto: $ ' + fmtMiles(v);
                }
              }
            }
          },
          scales: {
            y: {
              beginAtZero:true,
              ticks: {
                callback: function(value) {
                  return '$ ' + fmtMiles(value);
                }
              }
            }
          }
        }
      });
    }
  });
</script>
"""


# =========================
#   LÓGICA DEL PANEL
# =========================

def _parse_iso_date(s: str | None):
    if not s:
        return None
    try:
        # "2025-03-15"
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def _vehiculo_label(veh: dict) -> str:
    if not veh:
        return "—"
    return f"{veh.get('patente','')} · {veh.get('marca','')} {veh.get('modelo','')} {veh.get('anio','')}"
def _gastos_data_file():
    # Usa la misma convención que gastos_bp
    return current_app.config.get(
        "GASTOS_FILE",
        os.path.join(current_app.root_path, "gastos.json")
    )

def _load_gastos():
    path = _gastos_data_file()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _parse_dmy(s: str | None):
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None

def _compute_gastos_totales(year: int, month: str):
    """
    Calcula:
      - gastos_anual: suma de todos los gastos del año (incluyendo recurrentes cada mes)
      - gastos_mes:   suma de gastos del mes filtrado (o de todo el año si month == 'all')
      - gastos_por_mes: dict {mes(int 1..12): total_gastos_mes}
    Usa la misma lógica de recurrencia que el módulo de gastos.
    """
    gastos = _load_gastos()
    year_int = int(year)

    try:
        month_int = int(month) if month != "all" else None
    except ValueError:
        month_int = None

    gastos_anual = 0
    gastos_mes = 0
    gastos_por_mes = {m: 0 for m in range(1, 13)}

    for g in gastos:
        d_ini = _parse_dmy(g.get("fecha"))
        if not d_ini:
            continue

        try:
            monto = int(g.get("monto") or 0)
        except Exception:
            monto = 0

        recurrente = bool(g.get("recurrente"))
        fin_txt = g.get("fin_recurrencia") or ""
        d_fin = _parse_dmy(fin_txt) if fin_txt else None

        # Gasto NO recurrente: solo en su fecha
        if not recurrente:
            if d_ini.year != year_int:
                continue

            gastos_anual += monto
            gastos_por_mes[d_ini.month] = gastos_por_mes.get(d_ini.month, 0) + monto

            if month_int is None or d_ini.month == month_int:
                gastos_mes += monto
            continue

        # Gasto recurrente mensual: una ocurrencia por cada mes válido dentro del año
        for m in range(1, 13):
            # Antes del inicio
            if (year_int, m) < (d_ini.year, d_ini.month):
                continue
            # Después del fin (si hay fecha de término)
            if d_fin and (year_int, m) > (d_fin.year, d_fin.month):
                continue

            gastos_anual += monto
            gastos_por_mes[m] = gastos_por_mes.get(m, 0) + monto

            if month_int is None or m == month_int:
                gastos_mes += monto

    return {
        "gastos_anual": gastos_anual,
        "gastos_mes": gastos_mes,
        "gastos_por_mes": gastos_por_mes,
    }
@finanzas_bp.route("/panel")
def panel():
    # Filtros
    today = date.today()
    year = int(request.args.get("year") or today.year)
    # por defecto, mes actual (ej: "11" para noviembre)
    month = (request.args.get("month") or f"{today.month:02d}")
    veh = (request.args.get("veh") or "all")

    eventos = [e for e in load_eventos() if (e.get("tipo") or "reserva") == "reserva"]
    vehiculos = load_vehiculos()

    # Años disponibles según eventos
    years_found = set()
    for ev in eventos:
        d = _parse_iso_date(ev.get("inicio"))
        if d:
            years_found.add(d.year)
    if not years_found:
        years = [year]
    else:
        years = sorted(years_found, reverse=True)
        if year not in years:
            years.insert(0, year)

    # Meses fijos
    months = [
        ("01", "Enero"), ("02", "Febrero"), ("03", "Marzo"),
        ("04", "Abril"), ("05", "Mayo"), ("06", "Junio"),
        ("07", "Julio"), ("08", "Agosto"), ("09", "Septiembre"),
        ("10", "Octubre"), ("11", "Noviembre"), ("12", "Diciembre"),
        ("all", "Todo el año"),
    ]
    month_label_map = {code: label for code, label in months}
    if month == "all":
        month_label = "Todo el año"
    else:
        month_label = month_label_map.get(month, month)

    # Map rápido de vehículo por id
    veh_map = {int(v["id"]): v for v in vehiculos if "id" in v}

    # Acumuladores de ingresos
    total_anual = 0
    total_mes = 0
    cant_reservas = 0

    # Para charts de ingresos
    montos_por_mes = {m: 0 for m in range(1, 13)}  # 1..12
    montos_por_veh = {}  # veh_id -> monto

    rows = []

    for ev in eventos:
        d = _parse_iso_date(ev.get("inicio"))
        if not d:
            continue

        # Filtrar por año
        if d.year != year:
            continue

        # Filtrar por vehículo (si no es "all")
        ev_vid = int(ev.get("vehiculo_id") or 0)
        if veh != "all" and str(ev_vid) != str(veh):
            continue

        monto = int(ev.get("total_amount") or 0)

        total_anual += monto

        # Filtrar para "total_mes" y la tabla
        if month == "all" or int(month) == d.month:
            total_mes += monto
            cant_reservas += 1

            v = veh_map.get(ev_vid)
            cli = ev.get("cliente") or {}
            nombre = (ev.get("cliente_nombre") or cli.get("nombre") or ev.get("nombre") or "").strip()
            apellido = (ev.get("cliente_apellido") or cli.get("apellido") or ev.get("apellido") or "").strip()
            cliente_nom = (nombre + " " + apellido).strip() or "—"

            rows.append({
                "fecha": d.strftime("%d-%m-%Y"),
                "vehiculo": _vehiculo_label(v),
                "cliente": cliente_nom,
                "monto": monto,
            })

        # Siempre sumamos al gráfico anual por mes (ingresos)
        montos_por_mes[d.month] = montos_por_mes.get(d.month, 0) + monto

        # Sumar al gráfico por vehículo (dentro del filtro de mes)
        if month == "all" or int(month) == d.month:
            montos_por_veh[ev_vid] = montos_por_veh.get(ev_vid, 0) + monto

    # === GASTOS: anual, mensual y por mes ===
    gastos_info = _compute_gastos_totales(year, month)
    gastos_mes = gastos_info["gastos_mes"]
    gastos_anual = gastos_info["gastos_anual"]
    gastos_por_mes = gastos_info["gastos_por_mes"]

    # === Gráfico de ingresos por mes ===
    chart_meses = []
    for m in range(1, 13):
        label = f"{m:02d}"
        chart_meses.append({
            "label": label,
            "monto": montos_por_mes.get(m, 0)
        })

    # === NUEVO: gráfico de resultado neto por mes (ingresos - gastos) ===
    chart_netos = []
    for m in range(1, 13):
        label = f"{m:02d}"
        ingreso_m = montos_por_mes.get(m, 0)
        gasto_m = gastos_por_mes.get(m, 0)
        neto_m = ingreso_m - gasto_m
        chart_netos.append({
            "label": label,
            "monto": neto_m
        })

    # Gráfico por vehículo (ingresos)
    chart_vehiculos = []
    for vid, monto in montos_por_veh.items():
        v = veh_map.get(vid)
        chart_vehiculos.append({
            "label": _vehiculo_label(v),
            "monto": monto
        })

    # Resumen para las tarjetas
    summary = {
        # Ingresos
        "ingresos_mes": total_mes,
        "ingresos_anual": total_anual,
        "total_mes": total_mes,       # alias
        "total_anual": total_anual,   # alias

        # Gastos
        "gastos_mes": gastos_mes,
        "gastos_anual": gastos_anual,

        # Resultado neto
        "neto_mes": total_mes - gastos_mes,
        "neto_anual": total_anual - gastos_anual,

        # Otros datos
        "cant_reservas": cant_reservas,
    }

    # Ordenamos filas por fecha descendente
    rows = sorted(rows, key=lambda r: datetime.strptime(r["fecha"], "%d-%m-%Y"), reverse=True)

    html = render_template_string(
        FINANZAS_HTML,
        year=year,
        month=month,
        month_label=month_label,
        veh=veh,
        years=years,
        months=months,
        vehiculos=vehiculos,
        summary=summary,
        chart_meses=chart_meses,
        chart_netos=chart_netos,          # ← importante
        chart_vehiculos=chart_vehiculos,
        rows=rows,
    )
    return render_admin_bp(html, active="finanzas")

@finanzas_bp.route("/")
def lista():
    # Para que url_for('finanzas.lista') funcione y lleve al panel
    return panel()