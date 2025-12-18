# inicio_bp.py
from flask import Blueprint, current_app, render_template_string, url_for, redirect
from datetime import datetime, date

# Filtro utilitario: "YYYY-MM-DD" -> "DD-MM-YYYY"
def iso_to_dmy(s: str) -> str:
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return s

# Blueprint
inicio_bp = Blueprint("inicio", __name__, url_prefix="/admin")

def render_admin_bp(html, active="inicio"):
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)

@inicio_bp.route("/inicio")
def inicio():
    # Asegura el filtro en este entorno Jinja (por si no se registró en app.py)
    env = current_app.jinja_env
    if "iso_to_dmy" not in env.filters:
        env.filters["iso_to_dmy"] = iso_to_dmy
        env.globals["iso_to_dmy"] = iso_to_dmy

    # Importes diferidos para evitar ciclos y tomar helpers/datos
    from calendario_bp import (
        load_vehiculos, load_eventos,
        month_range, overlap, parse_iso, total_del_mes
    )

    vehiculos = load_vehiculos()
    eventos = load_eventos()
        # KPIs: flota total / arrendados hoy / disponibles hoy
    hoy = date.today()

    def is_active_rental(e):
        if (e.get("tipo") or "reserva") != "reserva":
            return False
        ei, ef = parse_iso(e.get("inicio")), parse_iso(e.get("fin"))
        return bool(ei and ef and (ei <= hoy <= ef))

    arrendados_hoy_ids = {e.get("vehiculo_id") for e in eventos if is_active_rental(e)}
    kpi_flota_total = len(vehiculos)
    kpi_arrendados_hoy = len(arrendados_hoy_ids)
    kpi_disponibles_hoy = max(0, kpi_flota_total - kpi_arrendados_hoy)

    # 1) Próximos movimientos: solo eventos que no han terminado (fin >= hoy), ordenados por inicio
    def to_d(iso):
        try:
            return datetime.strptime((iso or "").strip(), "%Y-%m-%d").date()
        except Exception:
            return None

    hoy = date.today()

    proximos = [
        e for e in eventos
        if to_d(e.get("fin")) and to_d(e.get("fin")) >= hoy
    ]
    proximos.sort(key=lambda e: to_d(e.get("inicio")) or hoy)
    proximos = proximos[:10]

    # 2) KPIs del mes actual
    y, m = hoy.year, hoy.month
    first, last = month_range(y, m)

    def ev_in_month(e):
        ei, ef = parse_iso(e["inicio"]), parse_iso(e["fin"])
        return overlap(ei, ef, first, last)

    ev_mes = [e for e in eventos if ev_in_month(e)]
    kpi_reservas_mes = sum(1 for e in ev_mes if (e.get("tipo") or "reserva") == "reserva")
    kpi_total_mes = total_del_mes(ev_mes, y, m, None)
    kpi_mant_bloq = sum(1 for e in ev_mes if (e.get("tipo") in ("mantencion", "bloqueo")))

    # Helpers de estado ya registrados como globals en tu app principal
    _mant_overall = current_app.jinja_env.globals.get("mant_overall")
    _docs_overall = current_app.jinja_env.globals.get("docs_overall")

    INICIO_HTML = r"""
<div class="p-3">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h4 class="mb-0">Inicio</h4>
    <a class="btn btn-sm btn-outline-primary" href="{{ url_for('cal.home') }}">Ir al Calendario</a>
  </div>

  <!-- KPIs -->
    <div class="row g-3 mb-3">
    <div class="col-12 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Flota total</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">{{ kpi_flota_total }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Arrendados hoy</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">{{ kpi_arrendados_hoy }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Disponibles hoy</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">{{ kpi_disponibles_hoy }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Reservas este mes</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">{{ kpi_reservas_mes }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Ingr. estimados mes</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">$ {{ '{:,}'.format(kpi_total_mes).replace(',','.') }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-lg-2">
      <div class="card border-0 shadow-sm h-100 d-flex justify-content-center align-items-center">
        <div class="card-body">
          <div class="small text-secondary">Mant./Bloq. activos</div>
          <div class="h4 mb-0 d-flex justify-content-center align-items-center">{{ kpi_mant_bloq }}</div>
        </div>
      </div>
    </div>
  </div>

  <div class="row g-3">
    <!-- Estado de la flota (más angosto) -->
    <div class="col-12 col-xl-4">
      <div class="card border-0 shadow-sm h-100">
        <div class="card-body">
          <h6 class="mb-3">Estado rápido de la flota</h6>
          <div class="row g-3">
            {% for v in vehiculos %}
              <div class="col-12">
                <div class="d-flex align-items-center gap-3">
  <div class="rounded" style="width:12px;height:32px;background: {{ v.color_a or '#0ea5e9' }}"></div>
  <div class="flex-grow-1">
    <!-- Línea principal: marca + modelo + año -->
    <div class="fw-semibold">
      {{ v.marca }} {{ v.modelo }} {{ v.anio }}
    </div>
    <!-- Segunda línea: patente -->
    <div class="small text-secondary">
      Patente: {{ v.patente }}
    </div>
    <!-- Tercera línea: kilometraje -->
    <div class="small text-secondary">
      KM {{ "{:,}".format(v.km or 0).replace(",",".") }}
    </div>
    <div class="mt-1 d-flex flex-wrap gap-1">
      {% set stg, clsg = mant_overall(v) %}
      {% set std, clsd = docs_overall(v) %}
      <span class="badge rounded-pill bg-{{ clsg }}">MANT.: {{ stg }}</span>
      <span class="badge rounded-pill bg-{{ clsd }}">DOC.: {{ std }}</span>
    </div>
  </div>
</div>
                {% if not loop.last %}<hr class="my-2">{% endif %}
              </div>
            {% endfor %}
          </div>
        </div>
      </div>
    </div>

    <!-- Próximos movimientos (más ancho) -->
    <div class="col-12 col-xl-8">
      <div class="card border-0 shadow-sm h-100">
        <div class="card-body">
          <h6 class="mb-3">Próximos movimientos</h6>
          {% if proximos %}
          <div class="table-responsive">
            <table class="table table-sm align-middle">
              <thead>
                <tr>
                  <th>Fechas</th>
                  <th>Vehículo</th>
                  <th>Tipo</th>
                  <th>Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {% for e in proximos %}
                  {% set v = (vehiculos | selectattr('id','equalto', e.vehiculo_id) | list | first) %}
                  <tr>
                    <td class="text-nowrap">
                      <div><strong>Salida:</strong> {{ e.inicio|iso_to_dmy }}</div>
                      <div class="small text-secondary"><strong>Retorno:</strong> {{ e.fin|iso_to_dmy }}</div>
                    </td>
                    <td>{{ v.patente if v else '' }} · {{ v.modelo if v else '' }}</td>
                    <td>{{ e.tipo|capitalize }}</td>
                    <td>$ {{ '{:,}'.format(e.total_amount or 0).replace(',','.') }}</td>
                    <td><a class="btn btn-sm btn-outline-secondary" href="{{ url_for('cal.home') }}?veh={{ e.vehiculo_id }}">Abrir</a></td>
                  </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          {% else %}
            <div class="text-secondary">No hay movimientos próximos.</div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</div>
"""

    html = render_template_string(
        INICIO_HTML,
        vehiculos=vehiculos,
        proximos=proximos,
        kpi_reservas_mes=kpi_reservas_mes,
        kpi_total_mes=kpi_total_mes,
        kpi_mant_bloq=kpi_mant_bloq,
        kpi_flota_total=kpi_flota_total,
        kpi_arrendados_hoy=kpi_arrendados_hoy,
        kpi_disponibles_hoy=kpi_disponibles_hoy,
        mant_overall=_mant_overall,
        docs_overall=_docs_overall,
    )
    return render_admin_bp(html, active="inicio")

# Redirección opcional: /admin -> /admin/inicio
@inicio_bp.route("")
def root_redirect():
    return redirect(url_for("inicio.inicio"))