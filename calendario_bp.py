# calendario_bp.py
import json, os
from flask import Blueprint, render_template, render_template_string, request, jsonify, current_app
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# no pongas url_prefix acá; lo pones al registrar en app.py
cal_bp = Blueprint("cal", __name__)

def _veh_file():
    # Usa la ruta configurada por la app
    return current_app.config.get("VEHICULOS_FILE", os.path.join(current_app.root_path, "data.json"))

def _veh_normalizado(v):
    """Normaliza un vehículo sin perder campos importantes (km, mant, docs, etc.)."""
    if not isinstance(v, dict):
        return {}

    # 1) Leemos lo que venga del JSON / formulario
    modelo_raw = (v.get("modelo") or v.get("vehiculo_modelo") or "").strip()
    marca   = (v.get("marca")   or v.get("veh_marca")   or "").strip()
    modelo  = (v.get("modelo")  or "").strip()
    anio    = str(v.get("anio") or v.get("veh_anio") or "").strip()
    patente = (v.get("patente") or v.get("veh_patente") or "").strip()

    # 2) Si no tenemos marca / modelo / año separados,
    #    intentamos partir el texto del modelo_raw: "Kia Sorento 2012"
    if not (marca and modelo and anio) and modelo_raw:
        import re
        m = re.match(r"^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+)\s+(.+?)\s+(\d{4})$", modelo_raw)
        if m:
            marca, modelo, anio = m.groups()

    # 3) Partimos desde una copia COMPLETA del vehículo original
    out = dict(v)

    # 4) Normalizamos id (sin reventar si viene como string raro)
    vid = v.get("id")
    try:
        out["id"] = int(vid) if vid is not None else 0
    except Exception:
        out["id"] = vid or 0

    # 5) Sobrescribimos los campos "bonitos" que usas en la UI
    out["marca"] = marca
    out["modelo"] = modelo
    out["anio"] = anio
    out["patente"] = patente

    # 6) Colores y foto con valores por defecto si no vienen
    out["color_a"] = v.get("color_a") or "#0ea5e9"
    out["color_b"] = v.get("color_b") or "#ef4444"
    out["foto"]    = v.get("foto") or ""

    # 7) Km actual del vehículo
    try:
        out["km"] = int(v.get("km") or v.get("kilometraje") or 0)
    except Exception:
        out["km"] = 0

    # 8) Bloques de mantención y documentos, si existen (los mantenemos)
    mant = v.get("mant") or v.get("mantenciones") or {}
    docs = v.get("docs") or v.get("documentos") or {}
    if not isinstance(mant, dict):
        mant = {}
    if not isinstance(docs, dict):
        docs = {}
    out["mant"] = mant
    out["docs"] = docs

    return out

def load_vehiculos():
    path = _veh_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        current_app.logger.warning(f"No pude leer vehículos desde {path}. Devuelvo [].")
        return []

    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        return []

    norm = [_veh_normalizado(x) for x in data if isinstance(x, dict)]
    return [x for x in norm if x.get("id", 0) > 0]
def _emp_file():
    # mismo archivo que usa empleados_bp
    return current_app.config.get("EMPLEADOS_FILE", os.path.join(current_app.root_path, "empleados.json"))

def load_empleados():
    path = _emp_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        current_app.logger.exception(f"No pude leer empleados desde {path}")
        return []

    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        return []

    empleados = []
    for e in data:
        if not isinstance(e, dict):
            continue
        # Solo empleados con id válido
        try:
            eid = int(e.get("id") or 0)
        except Exception:
            continue
        if eid <= 0:
            continue
        # Por defecto mostramos solo activos
        estado = (e.get("estado") or "activo").lower()
        if estado not in ("activo", "activa", ""):
            continue
        e["id"] = eid
        empleados.append(e)
    return empleados


# ====== GASTOS: helpers locales para escribir en gastos.json ======

def _gastos_file():
    return current_app.config.get("GASTOS_FILE", os.path.join(current_app.root_path, "gastos.json"))

def _load_gastos():
    path = _gastos_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            current_app.logger.exception(f"No pude leer gastos desde {path}")
            return []
    return []

def _save_gastos(data):
    path = _gastos_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        current_app.logger.exception(f"No pude guardar gastos en {path}")


def _crear_gasto_empleado_para_evento(ev):
    """
    Crea un gasto categoría 'empleado' ligado a una reserva (evento) con empleado asignado.
    Usa snapshot de nombre, para que no dependa de que el empleado exista en el futuro.
    """
    empleado_id = ev.get("empleado_id")
    empleado_nombre = (ev.get("empleado_nombre") or "").strip()
    if not empleado_id or not empleado_nombre:
        return

    try:
        di = parse_iso(ev["inicio"])
        df = parse_iso(ev["fin"])
    except Exception:
        return

    dias = dias_inclusivos(di, df)
    if dias <= 0:
        return

    # valor por día configurable, por defecto 10.000
    pago_por_dia = int(current_app.config.get("PAGO_POR_DIA_EMPLEADO", 10000))
    monto = dias * pago_por_dia

    di_txt = di.strftime("%d-%m-%Y")
    df_txt = df.strftime("%d-%m-%Y")

    desc = f"Pago empleado {empleado_nombre} por arriendo {ev.get('veh_patente','')} del {di_txt} al {df_txt}"

    gastos = _load_gastos()
    next_id = (max([int(g.get("id") or 0) for g in gastos], default=0) + 1)

    g = {
        "id": next_id,
        "fecha": df_txt,  # pago al final del arriendo
        "categoria": "empleado",
        "descripcion": desc,
        "monto": int(monto),
        "nota": f"Reserva ID {ev.get('id')}",
        # campos estándar de gastos:
        "recurrente": False,
        "fin_recurrencia": "",
        # metadata útil pero ignorada por gastos_bp:
        "evento_id": ev.get("id"),
        "empleado_id": empleado_id,
        "empleado_nombre": empleado_nombre,
    }
    gastos.append(g)
    _save_gastos(gastos)


def _eliminar_gastos_por_evento(evento_id: int):
    """
    Elimina gastos creados automáticamente para un evento (reserva) al eliminarlo.
    """
    gastos = _load_gastos()
    nuevos = [g for g in gastos if int(g.get("evento_id") or 0) != int(evento_id)]
    if len(nuevos) != len(gastos):
        _save_gastos(nuevos)

def veh_label(v):
    marca  = (v.get("marca") or "").strip()
    modelo = (v.get("modelo") or "").strip()
    anio   = str(v.get("anio") or "").strip()
    label  = " ".join([x for x in (marca, modelo, anio) if x])
    return label or v.get("patente") or f"Vehículo {v.get('id')}"


def _evt_file():
    """Devuelve la ruta del archivo de eventos según configuración o fallback."""
    return current_app.config.get("EVENTOS_FILE", os.path.join(current_app.root_path, "data_eventos.json"))

def _parse_any_date_to_iso(s):
    """
    Acepta 'YYYY-MM-DD', 'YYYY/MM/DD', 'DD-MM-YYYY', 'DD/MM/YYYY'
    y devuelve 'YYYY-MM-DD'. Si falla, retorna None.
    """
    if not s:
        return None
    s = str(s).strip()
    fmts = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y")
    from datetime import datetime as _dt
    for fmt in fmts:
        try:
            return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def _normalize_event_legacy(ev):
    """
    Normaliza un evento legado al formato esperado por el calendario:
    - vehiculo_id: int
    - inicio/fin: 'YYYY-MM-DD'
    - tipo: 'reserva' | 'mantencion' | 'bloqueo'
    Mantiene campos opcionales si existen.
    """
    if not isinstance(ev, dict):
        return None
    e = dict(ev)  # copia

    # posibles claves para vehículo
    veh_id = (
        e.get("vehiculo_id")
        or e.get("veh_id")
        or e.get("vehicle_id")
        or e.get("car_id")
        or e.get("id_vehiculo")
        or e.get("vehiculo")
        or e.get("vehiculoId")
    )
    try:
        veh_id = int(veh_id)
    except Exception:
        veh_id = None

    # posibles claves para fechas
    inicio = (
        e.get("inicio")
        or e.get("start")
        or e.get("fecha_inicio")
        or e.get("desde")
        or e.get("fecha")
        or e.get("dia")
    )
    fin = (
        e.get("fin")
        or e.get("end")
        or e.get("fecha_fin")
        or e.get("hasta")
        or e.get("fecha")
        or e.get("dia")
    )

    inicio_iso = _parse_any_date_to_iso(inicio)
    fin_iso    = _parse_any_date_to_iso(fin)

    # si solo venía un día, úsalo como rango de 1 día
    if inicio_iso and not fin_iso:
        fin_iso = inicio_iso
    if fin_iso and not inicio_iso:
        inicio_iso = fin_iso

    # tipo
    tipo = (e.get("tipo") or e.get("kind") or e.get("class") or "reserva").strip().lower()
    if tipo not in ("reserva", "mantencion", "bloqueo"):
        # intenta inferir por texto
        t = (e.get("label") or e.get("title") or "").lower()
        if "mant" in t:
            tipo = "mantencion"
        elif "bloq" in t:
            tipo = "bloqueo"
        else:
            tipo = "reserva"

    # id
    try:
        _id = int(e.get("id")) if e.get("id") is not None else None
    except Exception:
        _id = None

    # arma el evento normalizado
    out = {
        "id": _id,  # si viene None, luego se corrige abajo
        "vehiculo_id": veh_id,
        "tipo": tipo,
        "inicio": inicio_iso,
        "fin": fin_iso,
        "pista": e.get("pista") or (e.get("lane") or None),
        "cruza_argentina": bool(e.get("cruza_argentina") or e.get("argentina") or e.get("cruzaArg")),
        "pricing_source": e.get("pricing_source") or e.get("pricing") or None,
        "daily_rate_applied": e.get("daily_rate_applied") or e.get("precio_dia") or e.get("rate") or 0,
        "total_amount": e.get("total_amount") or e.get("total") or 0,
        "nota": e.get("nota") or e.get("comment") or e.get("obs") or "",
        "negociada": bool(e.get("negociada") or (str(e.get("pricing_source") or "").lower() == "negociada")),
        "precio_dia": e.get("precio_dia"),
        "per_day_overrides": e.get("per_day_overrides") or {},
        "per_day_flags": e.get("per_day_flags") or {},
        "cliente": e.get("cliente") or {},

        # 👇 IMPORTANTE: mantener el snapshot del empleado si viene en el JSON
        "empleado_id": e.get("empleado_id"),
        "empleado_nombre": e.get("empleado_nombre"),

        # snapshots de vehículo (si existían)
        "veh_marca":   e.get("veh_marca"),
        "veh_modelo":  e.get("veh_modelo"),
        "veh_anio":    str(e.get("veh_anio")) if e.get("veh_anio") is not None else None,
        "veh_patente": e.get("veh_patente"),
    }

    # valida mínimos
    if not veh_id or not inicio_iso or not fin_iso:
        return None

    # corrige id si falta
    return out

def load_eventos():
    path = _evt_file()
    if not os.path.exists(path):
        current_app.logger.warning(f"No existe {path}, devolviendo lista vacía.")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        current_app.logger.exception(f"Error leyendo {path}: {e}")
        return []

    # admitir dict {id: evento}
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        current_app.logger.warning(f"{path} no es lista ni dict; devolviendo [].")
        return []

    norm = []
    for ev in raw:
        ne = _normalize_event_legacy(ev)
        if ne:
            norm.append(ne)

    # asegurar IDs consecutivos si faltaban o venían nulos/duplicados
    usados = set()
    next_id = 1
    for e in norm:
        if isinstance(e.get("id"), int) and e["id"] > 0 and e["id"] not in usados:
            usados.add(e["id"])
    for e in norm:
        if not isinstance(e.get("id"), int) or e["id"] <= 0 or e["id"] in usados:
            while next_id in usados:
                next_id += 1
            e["id"] = next_id
            usados.add(next_id)

    return norm

def save_eventos(eventos):
    path = _evt_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(eventos, f, ensure_ascii=False, indent=2)
        current_app.logger.info(f"Guardados {len(eventos)} eventos en {path}")
    except Exception as e:
        current_app.logger.exception(f"Error guardando {path}: {e}")

# ---- Helpers de fechas / mes ----
def parse_month(s):
    # "YYYY-MM" -> (year, month)
    try:
        y, m = s.split("-")
        return int(y), int(m)
    except:
        today = date.today()
        return today.year, today.month

def month_range(y, m):
    first = date(y, m, 1)
    if m == 12:
        nxt = date(y+1, 1, 1)
    else:
        nxt = date(y, m+1, 1)
    last = nxt - timedelta(days=1)
    return first, last

def daterange(d1, d2):
    cur = d1
    while cur <= d2:
        yield cur
        cur += timedelta(days=1)

def parse_iso(d):
    return datetime.strptime(d, "%Y-%m-%d").date()

def overlap(a1, a2, b1, b2):
    return not (a2 < b1 or b2 < a1)

# ---- Pistas A/B ----
def eventos_por_pista(eventos, vehiculo_id, pista):
    return [e for e in eventos if e.get("vehiculo_id")==vehiculo_id and e.get("pista")==pista]

def asignar_pista(eventos, vehiculo_id, inicio, fin):
    # Intenta pista A; si choca, intenta B; si ambas chocan -> None
    A = eventos_por_pista(eventos, vehiculo_id, "A")
    B = eventos_por_pista(eventos, vehiculo_id, "B")

    def libre(lista):
        for ev in lista:
            ei, ef = parse_iso(ev["inicio"]), parse_iso(ev["fin"])
            if overlap(ei, ef, inicio, fin):
                return False
        return True

    if libre(A): return "A"
    if libre(B): return "B"
    return None

# ---- Cálculo de precios ----
def dias_inclusivos(d1, d2):
    return (d2 - d1).days + 1

def tarifa_del_dia(veh, cruz_arg, dias):
    # Defaults por vehículo (si existen), sino globales:
    rate_1 = veh.get("rate_1dia") or 60000
    rate_std = veh.get("rate_estandar") or 50000
    rate_arg = veh.get("rate_argentina") or 80000

    if cruz_arg:
        return rate_arg, "argentina"
    if dias == 1:
        return rate_1, "1dia"
    return rate_std, "estandar"

def total_del_mes(eventos, year, month, veh_id=None):
    """
    Suma el total del mes para reservas visibles.
    - Si existe e["total_amount"], lo usa directo.
    - Si no, calcula daily * días pero tolerando None/Strings.
    - Ignora tipos no 'reserva' (mantención/bloqueo).
    Nota: 'eventos' ya viene filtrado al mes en 'home()', así que no re-filtramos fechas aquí.
    """
    total = 0

    for e in eventos:
        # Filtrar por vehículo si corresponde
        if veh_id is not None and e.get("vehiculo_id") != veh_id:
            continue

        # Solo reservas suman dinero
        if (e.get("tipo") or "reserva").lower() != "reserva":
            continue

        # 1) Preferir total_amount si está presente y es numérico
        ta = e.get("total_amount")
        if isinstance(ta, (int, float)):
            total += int(ta or 0)
            continue

        # 2) Caso legacy: daily_rate_applied * días
        #    (tolerar None, strings, etc.)
        daily_raw = e.get("daily_rate_applied")
        try:
            daily = int(daily_raw or 0)
        except Exception:
            daily = 0

        try:
            di = parse_iso(e["inicio"])
            df = parse_iso(e["fin"])
            dias = (df - di).days + 1
            if dias < 0:
                dias = 0
        except Exception:
            dias = 0

        total += daily * dias

    return total

# ---- Colores por vehículo (parejas A/B) ----
COLOR_PAIRS = [
    ("#0ea5e9", "#ef4444"),  # celeste / rojo
    ("#22c55e", "#f59e0b"),  # verde / ámbar
    ("#8b5cf6", "#06b6d4"),  # violeta / cian
    ("#f43f5e", "#10b981"),  # rosado / esmeralda
    ("#60a5fa", "#fb7185"),  # azul / rosa
    ("#a855f7", "#f97316"),  # púrpura / naranja
    ("#14b8a6", "#eab308"),  # teal / amarillo
    ("#3b82f6", "#ef4444"),  # azul / rojo
]

def _assign_color_pair(v, idx: int):
    """Asigna una pareja A/B si el vehículo no la trae."""
    if v.get("color_a") and v.get("color_b"):
        return
    a, b = COLOR_PAIRS[idx % len(COLOR_PAIRS)]
    v["color_a"], v["color_b"] = a, b

def ensure_vehicle_colors(vehiculos: list):
    """Garantiza que todos los vehículos tengan color_a y color_b."""
    for i, v in enumerate(vehiculos):
        if not v.get("color_a") or not v.get("color_b"):
            _assign_color_pair(v, i)


            # === Helpers de normalización de vehículo (para datos antiguos) ===
import re


# ---- TEMPLATE principal (usa LAYOUT_BASE de app) ----
CAL_HTML = r"""
<div class="p-3">
  <!-- Header de Calendario -->
<div class="d-flex align-items-center justify-content-between mb-3">
  <div class="d-flex align-items-center gap-2">
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('cal.home', month=prev_month, veh=veh_sel) }}">◀</a>
        <h4 class="mb-0">{{ month_label }}</h4>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('cal.home', month=next_month, veh=veh_sel) }}">▶</a>
  </div>

  <div class="text-end">
    <div class="small text-secondary">Total del mes</div>
    <div class="h5 mb-0">$ {{ '{:,}'.format(total_mes).replace(',','.') }}</div>
  </div>
</div>

  <!-- Calendario + Panel lateral -->
  <div class="row g-3">
    <!-- Calendario mensual (grid) -->
    <div class="col-12 col-xl-9">
      <div class="card border-0 shadow-sm">
        <div class="card-body">

        
        <!-- ==== CAL GRID: ENCABEZADO DE DÍAS ==== -->
<div class="row row-cols-7 g-2 text-center cal-weekdays">
  {% for wd in ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'] %}
    <div class="col"><div class="small text-secondary">{{ wd }}</div></div>
  {% endfor %}
</div>

<!-- ==== CAL GRID: CELDAS 6x7 ==== -->
{% for cell in cells %}
  {% if loop.index0 % 7 == 0 %}
    <div class="row row-cols-7 g-2 mt-1">
  {% endif %}

  <div class="col">
    <div class="cal-cell p-2 border rounded position-relative
            {% if not cell.in_month %}bg-dark-subtle{% endif %}
            {% if cell.is_today %} cal-today{% endif %}"
     data-date="{{ cell.date }}"
     data-events='{{ cell.events|tojson }}'>

      <div class="d-flex justify-content-between align-items-center mb-1">
        <div class="small {% if not cell.in_month %}text-secondary{% endif %}">{{ cell.date.day }}</div>
        {% if cell.badge_count > 3 %}
          <span class="badge text-bg-secondary">+{{ cell.badge_count - 3 }}</span>
        {% endif %}
      </div>

      <!-- eventos (máx 3 visibles por celda) -->
      <div class="d-flex flex-column gap-1">
        {% for ev in cell.events[:3] %}
          <div class="event-chip d-flex align-items-center justify-content-between px-2 py-1 rounded"
               data-veh="{{ ev.vehiculo_id }}"
               title="{{ ev.tooltip }}"
               style="background: {{ ev.bg }}; color: {{ ev.fg }}; box-shadow: 0 2px 8px rgba(0,0,0,.15); border: 1px solid rgba(0,0,0,.08);">
            
            {% if ev.cruza_argentina %}
  <span class="chip-flag" title="Cruza a Argentina">🇦🇷</span>
{% endif %}
<span class="small text-truncate flex-1">{{ ev.label }}</span>

            <button type="button"
                    class="btn btn-link btn-sm p-0 event-del"
                    data-id="{{ ev.id }}"
                    title="Eliminar"
                    style="text-decoration:none; line-height:1;">
              <i class="bi bi-trash3"></i>
            </button>
          </div>
        {% endfor %}
      </div>

      <!-- overlay para selección de rango -->
      <div class="select-overlay"></div>
    </div>
  </div>

  {% if loop.index0 % 7 == 6 %}
    </div>
  {% endif %}
{% endfor %}

<!-- fin grilla -->

          <div class="mt-2 small text-secondary">
            Consejo: clic en un día para marcar **inicio**, clic en otro para **fin**. Luego configura a la derecha y “Crear reserva”.
          </div>
        </div>
      </div>
    </div>
<!-- Modal de día -->
<div class="modal fade" id="dayModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-lg modal-dialog-scrollable">
    <div class="modal-content">
      <div class="modal-header">
        <h6 class="modal-title" id="dayModalTitle">Reservas del día</h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
      </div>
      <div class="modal-body" id="dayModalBody">
      </div> 
    </div>
  </div>
</div>
<!-- Modal datos del cliente -->
<div class="modal fade" id="clienteModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h6 class="modal-title">Datos del cliente</h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
      </div>
      <div class="modal-body">
        <div class="mb-2">
          <label class="form-label small">Nombre</label>
          <input type="text" class="form-control form-control-sm" id="c_nombre" autocomplete="name">
        </div>
        <div class="mb-2">
          <label class="form-label small">Apellido</label>
          <input type="text" class="form-control form-control-sm" id="c_apellido" autocomplete="family-name">
        </div>
        <div class="mb-2">
          <label class="form-label small">RUT</label>
          <input type="text" class="form-control form-control-sm" id="c_rut" placeholder="12.345.678-9">
        </div>
        <div class="mb-2">
          <label class="form-label small">Nacionalidad</label>
          <input type="text" class="form-control form-control-sm" id="c_nacionalidad">
        </div>
        <div class="mb-2">
          <label class="form-label small">Teléfono</label>
          <input type="tel" class="form-control form-control-sm" id="c_telefono" placeholder="+56 9 1234 5678">
        </div>
        <div class="mb-2">
          <label class="form-label small">Correo electrónico</label>
          <input type="email" class="form-control form-control-sm" id="c_email" placeholder="cliente@correo.com" autocomplete="email">
        </div>
                <div class="mb-2">
          <label class="form-label small">Encargado / empleado</label>
          <select class="form-select form-select-sm" id="modal_empleado_id">
            <option value="">— Sin empleado (lo hago yo) —</option>
            {% for emp in empleados %}
              <option value="{{ emp.id }}">
                {{ (emp.get('nombre') or '') ~ ' ' ~ (emp.get('apellido') or '') }}
              </option>
            {% endfor %}
          </select>
          <div class="form-text">
            Si eliges un empleado, se generará automáticamente un gasto de comisión por este arriendo.
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancelar</button>
        <button class="btn btn-primary btn-sm" id="btnGuardarCliente">Guardar y crear reserva</button>
      </div>
    </div>
  </div>
</div>
<!-- Panel lateral derecho -->
<div class="col-12 col-xl-3">
  <div class="card border-0 shadow-sm">
    <div class="card-body p-3" id="vehPanel">
      <h5 class="mb-3">Vehículo</h5>

      <form id="vehForm">
        <div class="mb-2">
          <select class="form-select form-select-sm" id="vehiculo_id"
                  onchange="location.href='{{ url_for('cal.home') }}?month={{ ym }}&veh='+this.value">
            <option value="all" {{ 'selected' if veh_sel=='all' else '' }}>— Todos los vehículos —</option>
            {% for v in vehiculos %}
              <option value="{{ v.id }}" {{ 'selected' if veh_sel==v.id|string else '' }}>
                {{ v.patente }} · {{ (v.marca ~ ' ' ~ v.modelo ~ ' ' ~ v.anio).strip() }}
              </option>
            {% endfor %}
          </select>
        </div>

        <!-- Info dinámica del vehículo -->
<div id="vehInfo" class="mb-2">
  <div id="vehNombre" class="fw-semibold" style="color:#111">
    {{ veh_first.marca }} {{ veh_first.modelo }} {{ veh_first.anio }}
  </div>
  <div class="text-secondary small" id="vehSub">
    Patente {{ veh_first.get('patente','') }} · {{ "{:,}".format(veh_first.get('km',0)).replace(',','.') }} km
  </div>
</div>

          {# Estados compactos pegados al nombre/patente, SOLO si hay 1 vehículo seleccionado #}
          {% if veh_sel != 'all' %}
            {% set vf = (vehiculos|selectattr('id','equalto', veh_sel|int)|list|first) %}
            {% if vf %}
              {% set stg, clsg = mant_overall(vf) %}
              {% set std, clsd = docs_overall(vf) %}
              <div id="vehEstados" class="mt-2 d-flex flex-column gap-1">
              <span class="badge rounded-pill bg-{{ clsg }} px-2 py-1 w-100 text-center">MANT.: {{ stg }}</span>
              <span class="badge rounded-pill bg-{{ clsd }} px-2 py-1 w-100 text-center">DOC.: {{ std }}</span>
              </div>
            {% endif %}
          {% endif %}

        <div class="d-flex align-items-center gap-2 mb-2 mt-3">
        <div id="colorA" class="rounded shadow-sm border" style="width:22px;height:22px;background: {{ veh_first.get('color_a','#0ea5e9') }};"></div>
        <div id="colorB" class="rounded shadow-sm border" style="width:22px;height:22px;background: {{ veh_first.get('color_b','#ef4444') }};"></div>
        <span class="small text-secondary">Colores A/B del vehículo</span>
        </div>

        <div class="mb-3">
          <img id="vehFoto" src="{{ veh_foto_url(veh_first) }}" alt=""
                style="width:100%;aspect-ratio:16/9;object-fit:contain;background:transparent"
                onerror="this.style.display='none'">
        </div>
      <div id="vehReservaWrap">
        <hr>

        <h6 class="mb-2">Rango seleccionado</h6>
        <div class="d-flex gap-2 mb-2">
          <input class="form-control form-control-sm" id="fecha_ini" placeholder="DD-MM-YYYY">
          <input class="form-control form-control-sm" id="fecha_fin" placeholder="DD-MM-YYYY">
        </div>

        <div class="mb-2">
          <label class="form-label small mb-1">Tipo</label>
          <select id="tipo_evento" class="form-select form-select-sm">
            <option value="reserva" selected>Reserva</option>
            <option value="mantencion">Mantención</option>
            <option value="bloqueo">Bloqueo</option>
          </select>
          <div class="form-text">“Mantención” usa un color fijo y no tiene precio.</div>
        </div>

        <!-- Opciones exclusivas de RESERVA -->
        <div id="wrap_reserva_opts">
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="cruza_arg">
            <label class="form-check-label" for="cruza_arg">Cruza a Argentina 🇦🇷</label>
          </div>

          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="negociada">
            <label class="form-check-label" for="negociada">Precio negociado</label>
          </div>

          <div class="d-flex gap-2 mb-2">
            <input class="form-control form-control-sm" id="precio_dia" placeholder="$ por día" disabled>
            <input class="form-control form-control-sm" id="nota" placeholder="Nota / Cliente">
          </div>

          <div class="p-3 rounded bg-light text-dark mb-3" style="border:1px solid #e5e7eb; border-radius:.5rem">
            <div class="d-flex justify-content-between">
              <span>Días</span><strong id="dias_lbl">0</strong>
            </div>
            <div class="d-flex justify-content-between">
              <span>Tarifa aplicada</span><strong id="tarifa_lbl">$0</strong>
            </div>
            <div class="d-flex justify-content-between">
              <span>Total</span><strong id="total_lbl">$0</strong>
            </div>
          </div>
        </div>
        <!-- /Opciones exclusivas de RESERVA -->

        <button type="button" class="btn btn-success w-100" id="btnCrear">Crear reserva</button>
      </div>
      </form>
    </div>
  </div>

  <div id="totalPorVehiculo" class="mt-2 card border-0 shadow-sm">
  <div class="card-body py-2 px-3 small text-secondary">
    Total del mes (este vehículo): <strong>$ {{ '{:,}'.format(total_mes_veh).replace(',','.') }}</strong>
  </div>
  </div> 
</div>

<style>
  /* Celdas básicas y selección */
  .cal-cell { 
    min-height: 120px; 
    background:#ffffff; 
    display: flex; 
    flex-direction: column; 
  }
  .cal-cell .select-overlay { position:absolute; inset:0; pointer-events:none; border-radius:.5rem; }
  .cal-cell.sel-start { outline:2px solid #0ea5e9; }
  .cal-cell.sel-in { background: #e0f2fe; }
  .cal-cell.sel-end { outline:2px solid #0ea5e9; }

  /* Botón eliminar sobre chip */
  .event-chip .event-del { opacity: 0; transition: opacity .15s ease; }
  .event-chip:hover .event-del { opacity: 1; }

  /* Panel derecho (vehPanel) */
  #vehPanel h5 { margin-bottom: .75rem; }
  #vehPanel .mb-3 { margin-bottom: .75rem !important; }
  #vehPanel .sidebar-badges .badge {
    font-size: .80rem;
    border-radius: 999px;
    font-weight: 600;
  }
  #vehPanel #vehInfo .fw-semibold { line-height: 1.2; }
  #vehPanel #vehSub { line-height: 1.2; }
  #vehPanel #vehFoto { margin-top: .25rem; }
  #vehEstados .badge { font-size: .75rem; line-height: 1; }
  #vehInfo .fw-semibold, #vehSub { line-height: 1.2; }

  /* Encabezado de días */
  .cal-weekdays .col > div {
    font-weight: 600;
    letter-spacing: .2px;
  }

  /* Resalte del día de hoy */
  .cal-today {
    outline: 3px solid #22c55e !important;
    box-shadow: inset 0 0 0 3px rgba(34,197,94,.18);
    border-radius: .5rem;
  }

  /* Fines de semana más grises en el encabezado */
  .cal-weekdays .col:nth-child(6) .small,
  .cal-weekdays .col:nth-child(7) .small {
    color: #9ca3af;
  }

  /* Mantener 7 columnas alineadas sin romper el layout */
  .cal-cell { min-width: 0 !important; }
  .row.row-cols-7 > .col {
    flex: 1 1 0 !important;
    max-width: 14.2857% !important; /* 100/7 */
  }

  /* Pastilla compacta, una sola línea y texto pequeño */
  .event-chip {
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .25rem;
    padding: 1px 4px;
    font-size: 0.70rem;
    line-height: 1.1;
    min-height: 18px;
  }
  .event-chip .text-truncate {
    flex: 1 1 auto;
    min-width: 0;
    font-size: 0.70rem;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis; /* patente + tipo en una línea */
  }
  .event-chip .event-del { flex: 0 0 auto; }
  .event-chip .event-del i { font-size: 0.8rem; }
  .day-modal .event-card { border-radius: .5rem; }
  .day-modal .event-card .fw-semibold { letter-spacing: .2px; }

  /* Menos espacio vertical entre chips para no engordar la fila */
  .cal-cell .d-flex.gap-1 > .event-chip { margin-bottom: 2px; }

  /* Título del modal más legible */
.day-modal h6.modal-title,
.day-modal h6 {
  color: #111;     /* más oscuro */
  font-weight: 600;
}
/* ==== Colores del modal de detalle ==== */
.day-modal {
  color: #000; /* texto principal negro */
}

.day-modal strong {
  color: #000; /* títulos de cada línea también negros */
}

.day-modal .small,
.day-modal .text-secondary {
  color: #000 !important; /* fuerza todo el texto secundario a negro */
}
/* Un poco más de aire en el body del modal */
#dayModal .modal-body { padding: 1rem 1.25rem; }

/* Que los botoncitos no queden pegados */
.day-modal .btn { white-space: nowrap; }

.event-chip .chip-flag{
  flex: 0 0 auto;
  font-size: 0.9rem;
  line-height: 1;
  margin-right: .25rem;
}
.day-modal span[title="Cruza a Argentina"] {
  font-size: 1rem;
  margin-left: 4px;
}

/* ==== ESTILOS VISIBLES PARA MODAL DE CLIENTE ==== */
#clienteModal .modal-content {
  background: #ffffff;              /* fondo blanco nítido */
  color: #000000;                   /* texto principal negro */
}

#clienteModal .modal-header,
#clienteModal .modal-body,
#clienteModal .modal-footer {
  background-color: #ffffff !important; /* fuerza fondo blanco puro */
  color: #000000 !important;
}

#clienteModal label.form-label {
  color: #000000 !important;       /* etiquetas negras */
  font-weight: 600;                /* un poco más gruesas */
}

#clienteModal input.form-control {
  background-color: #f9f9f9;       /* gris muy claro para contraste */
  color: #000000;                  /* texto negro */
  border: 1px solid #555555;       /* borde visible */
}

#clienteModal input.form-control::placeholder {
  color: #555555;                  /* placeholder gris oscuro */
}



</style>

<script>
(function(){
  const fmt = n => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  // Datos de vehículos para actualizar UI al vuelo
  const VEHICULOS = {{ vehiculos|tojson }};
  const EMPLEADOS = {{ empleados|tojson }};
  const elNombre = document.getElementById('vehNombre');
  const elSub    = document.getElementById('vehSub');
  const elFoto   = document.getElementById('vehFoto');
  const elColA   = document.getElementById('colorA');
  const elColB   = document.getElementById('colorB');
  
 // ==== Formato fechas: ISO (YYYY-MM-DD) <-> DMY (DD-MM-YYYY) ====
function isoToDMY(iso){
  // "2025-10-26" -> "26-10-2025"
  if(!iso) return "";
  const [y,m,d] = iso.split("-");
  if(!y||!m||!d) return iso;
  return `${d.padStart(2,'0')}-${m.padStart(2,'0')}-${y}`;
}
function dmyToISO(dmy){
  // "26-10-2025" -> "2025-10-26"
  if(!dmy) return "";
  const [d,m,y] = dmy.split("-");
  if(!d||!m||!y) return dmy;
  return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
}
// === Helpers de tarifas por día (considerando overrides y negociado global) ===
function toDigitsInt(s){
  if (s == null) return null;
  const t = String(s).replace(/\D+/g,'').trim();
  return t ? parseInt(t,10) : null;
}

// dayISO debe venir como "YYYY-MM-DD"
function effectiveTarifaForDay(ev, dayISO){
  // 1) override por día
  const per = ev.per_day_overrides || {};
  if (per && typeof per === 'object' && per[dayISO] != null) {
    const v = toDigitsInt(per[dayISO]);
    if (v != null) return v;
  }
  // 2) precio global negociado
  if (ev.negociada) {
    const g = toDigitsInt(ev.precio_dia);
    if (g != null) return g;
  }
  // 3) fallback: daily_rate_applied si viene del back
  if (ev.daily_rate_applied != null) {
    const d = toDigitsInt(ev.daily_rate_applied);
    if (d != null) return d;
  }
  // 4) lógica estimativa local (por si no viene nada del back)
  //    (ajústala si usas otra regla)
  const dias = diasEntreISO(ev.inicio, ev.fin);
  if (ev.cruza_argentina) return 80000;
  if (dias === 1) return 60000;
  return 50000;
}

// util común que ya usas en otros lados
function diasEntreISO(iniISO, finISO){
  if(!iniISO || !finISO) return 0;
  const sd = new Date(iniISO + "T00:00:00");
  const ed = new Date(finISO + "T00:00:00");
  return Math.round((ed - sd)/86400000) + 1; // inclusive
}

  // /admin/calendario/api/eventos/0  -> dejamos que JS quite el "0" final
const delBaseRaw = '{{ url_for("cal.api_eventos_delete", eid=0) }}';
const delBase = delBaseRaw.replace(/0$/, '');  // => /admin/calendario/api/eventos/

  function fmtKM(n){
    try { return (n||0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
    catch { return n; }
  }

  function vehFotoURL(v){
    if(!v || !v.foto) return '';
    return `/static/vehiculos/${v.foto}`;
  }

  function actualizarVehiculoUI(id){
  if (String(id) === 'all'){
  elNombre.textContent = 'Todos los vehículos';
  elSub.textContent = 'Mostrando todas las reservas';
  elColA.style.background = '#e5e7eb';
  elColB.style.background = '#e5e7eb';
  elFoto.style.display = 'none';

  const totalVeh = document.querySelector('#totalPorVehiculo');
  if (totalVeh) totalVeh.style.display = 'none';

  // Ocultar todo el bloque de creación de reservas
  const reservaWrap = document.querySelector('#vehReservaWrap');
  if (reservaWrap) reservaWrap.style.display = 'none';

  return;
}

  const v = VEHICULOS.find(x => String(x.id) === String(id));
  if (!v) return;

  // Mostrar marca, modelo y año juntos
  const marca  = (v.marca  || '').trim();
  const modelo = (v.modelo || '').trim();
  const anio   = (v.anio   || '').toString().trim();
  const nombre = [marca, modelo, anio].filter(Boolean).join(' ');

  elNombre.textContent = nombre || (v.patente || '');
  elSub.textContent = `Patente ${v.patente || ''} · ${fmtKM(v.km||0)} km`;
  elColA.style.background = v.color_a || '#0ea5e9';
  elColB.style.background = v.color_b || '#ef4444';

  const src = vehFotoURL(v);
  if (src){
    elFoto.src = src;
    elFoto.style.display = '';
  } else {
    elFoto.style.display = 'none';
  }

  const totalVeh = document.querySelector('#totalPorVehiculo');
  if (totalVeh) totalVeh.style.display = '';
  // Si se selecciona un vehículo individual, mostrar el bloque
const reservaWrap = document.querySelector('#vehReservaWrap');
if (reservaWrap) reservaWrap.style.display = '';
}

  const ini = document.getElementById('fecha_ini');
  const fin = document.getElementById('fecha_fin');
  const diasLbl = document.getElementById('dias_lbl');
  const tarifaLbl = document.getElementById('tarifa_lbl');
  const totalLbl = document.getElementById('total_lbl');

  const neg = document.getElementById('negociada');
  const precioDia = document.getElementById('precio_dia');
  const arg = document.getElementById('cruza_arg');
  const vehSel = document.getElementById('vehiculo_id');

// === Modal del cliente (refs) ===
const clienteModalEl = document.getElementById('clienteModal');
const cNombre        = document.getElementById('c_nombre');
const cApellido      = document.getElementById('c_apellido');
const cRut           = document.getElementById('c_rut');
const cNac           = document.getElementById('c_nacionalidad');
const cTel           = document.getElementById('c_telefono');
const cEmail         = document.getElementById('c_email');

let bsClienteModal = null;
if (window.bootstrap && clienteModalEl){
  bsClienteModal = bootstrap.Modal.getOrCreateInstance(clienteModalEl);
}

// Helpers de cliente
function limpiarClienteForm(){
  [cNombre, cApellido, cRut, cNac, cTel, cEmail].forEach(el=>{ if(el) el.value=''; });
}

function leerClienteForm(){
  return {
    nombre:        (cNombre?.value || '').trim(),
    apellido:      (cApellido?.value || '').trim(),
    rut:           (cRut?.value || '').trim(),
    nacionalidad:  (cNac?.value || '').trim(),
    telefono:      (cTel?.value || '').trim(),
    email:         (cEmail?.value || '').trim(),
  };
}

function validarClienteForm(d){
  // mínimos: nombre, apellido, rut, teléfono
  if(!d.nombre)   return 'Falta nombre';
  if(!d.apellido) return 'Falta apellido';
  if(!d.rut)      return 'Falta RUT';
  if(!d.telefono) return 'Falta teléfono';
  // validación simple de email (opcional)
  if(d.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.email)) return 'Email inválido';
  return null;
}

// Formateo suave de RUT mientras escribe (opcional)
if (cRut){
  cRut.addEventListener('input', ()=>{
    let v = cRut.value.replace(/[^\dkK]/g,'').toUpperCase();
    // 12345678K -> 12.345.678-K
    const cuerpo = v.slice(0, -1), dv = v.slice(-1);
    let out = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    if (dv) out = out + '-' + dv;
    cRut.value = out;
  });
}
// ---- Formateo en vivo con miles para #precio_dia ----
function formatMilesLive(el){
  // posición del cursor antes de formatear
  const oldStart = el.selectionStart;
  const oldEnd   = el.selectionEnd;
  const oldVal   = el.value;

  // deja solo dígitos
  const digits = oldVal.replace(/\D+/g,'');

  // aplica puntos de miles
  const formatted = digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  // calcula cuántos caracteres había a la derecha del cursor
  const rightCount = oldVal.length - oldStart;

  el.value = formatted;

  // restaura cursor aproximado desde la derecha
  const newPos = Math.max(0, el.value.length - rightCount);
  el.setSelectionRange(newPos, newPos);
}

if (precioDia) {
  precioDia.addEventListener('input', ()=>{
    if (!precioDia.disabled && !precioDia.readOnly) {
      formatMilesLive(precioDia);
    }
  });


  // si activas/desactivas “negociada”, volvemos a formatear por si cambió el valor
 if (neg) {
  neg.addEventListener('change', ()=>{
    toggleTipoUI();                         // recalcula todo según el estado actual
    if (!precioDia.disabled && !precioDia.readOnly) {
      formatMilesLive(precioDia);           // mantiene el formateo en vivo
    }
  });
}
}
  // ----- Tipo de evento y wrapper de opciones de reserva -----
const tipoSel = document.getElementById('tipo_evento');
const wrapReserva = document.getElementById('wrap_reserva_opts');
const btnCrear = document.getElementById('btnCrear');

function toggleTipoUI(){
  const isReserva = (tipoSel?.value === 'reserva');

  // mostrar/ocultar el bloque de opciones de reserva
  if (wrapReserva) wrapReserva.style.display = isReserva ? '' : 'none';

  // texto del botón
  if (btnCrear) {
    btnCrear.textContent = isReserva
      ? 'Crear reserva'
      : (tipoSel.value === 'mantencion' ? 'Crear mantención' : 'Crear bloqueo');
  }

  // campos exclusivos de reserva
  const neg   = document.getElementById('negociada');
  const arg   = document.getElementById('cruza_arg');
  const nota  = document.getElementById('nota');
  const precioDia = document.getElementById('precio_dia');

  // habilitar/deshabilitar extras
  const allowExtras = isReserva;
  if (arg)  { arg.disabled  = !allowExtras; if(!allowExtras) arg.checked = false; }
  if (nota) { nota.disabled = !allowExtras; if(!allowExtras) nota.value  = ''; }

  // regla para precio por día: solo si es reserva Y está marcada “negociada”
  const allowPrecio = isReserva && neg && neg.checked;
  if (precioDia) {
    precioDia.disabled = !allowPrecio;
    precioDia.readOnly = !allowPrecio;   // doble seguro
    if (!allowPrecio) precioDia.value = '';
  }
}

if (tipoSel) {
  tipoSel.addEventListener('change', toggleTipoUI);
  toggleTipoUI(); // estado inicial
}

  function applyVehFilter(){
  const sel = vehSel.value; // "all" o un id numérico en string
  const chips = document.querySelectorAll('.event-chip[data-veh]');
  chips.forEach(ch=>{
    const v = ch.getAttribute('data-veh');
    const show = (sel === 'all') || (String(v) === String(sel));
    ch.style.display = show ? '' : 'none';
  });
  // (Opcional) podríamos ocultar la banderita + botones si está oculto, pero display:none ya lo hace.
}

// al cambiar el select, filtra
vehSel.addEventListener('change', ()=>{
  actualizarVehiculoUI(vehSel.value);   // ya lo tenías para foto/nombre
  applyVehFilter();
});

// al cargar la página, deja el filtro aplicado
applyVehFilter();
    // Actualizar info y foto cuando cambias el vehículo
 
  // Inicializar con el seleccionado por defecto
  actualizarVehiculoUI(vehSel.value);

  const nota = document.getElementById('nota');

  // selección de rango por clic en celdas
  let selStart = null;
 document.querySelectorAll('.cal-cell').forEach(cell=>{
  cell.addEventListener('click', ()=>{
    const dISO = cell.dataset.date; // viene como "YYYY-MM-DD"
    if (!selStart) {
      selStart = dISO;
      ini.value = isoToDMY(dISO);
      fin.value = isoToDMY(dISO);
      pintarSel();
      recalc();
      return;
    }
    let a = selStart;
    let b = dISO;
    if (b < a) { const t = a; a = b; b = t; }
    ini.value = isoToDMY(a);
    fin.value = isoToDMY(b);
    selStart = null;
    pintarSel();
    recalc();
  });
});

  function pintarSel(){
  const sISO = dmyToISO(ini.value);
  const eISO = dmyToISO(fin.value);
  document.querySelectorAll('.cal-cell').forEach(c=>{
    c.classList.remove('sel-start','sel-in','sel-end');
    const dISO = c.dataset.date; // "YYYY-MM-DD"
    if(!sISO || !eISO) return;
    if (dISO===sISO) c.classList.add('sel-start');
    if (dISO===eISO) c.classList.add('sel-end');
    if (dISO>=sISO && dISO<=eISO) c.classList.add('sel-in');
  });
}

  [ini, fin, neg, precioDia, arg, vehSel].forEach(el=>{
  el.addEventListener('input', ()=>{
    if(el===neg){ precioDia.disabled = !neg.checked; }
    pintarSel();
    recalc();
  });
  el.addEventListener('change', ()=>{
    if(el===neg){ precioDia.disabled = !neg.checked; }
    pintarSel();
    recalc();
  });
});

  function diffDaysDMY(sDMY, eDMY){
  const sISO = dmyToISO(sDMY);
  const eISO = dmyToISO(eDMY);
  if(!sISO || !eISO) return 0;
  const sd = new Date(sISO+"T00:00:00"); 
  const ed = new Date(eISO+"T00:00:00");
  return Math.round((ed - sd)/86400000) + 1; // inclusivo
}

  function recalc(){
    const d = diffDaysDMY(ini.value, fin.value);
    diasLbl.textContent = d;

    let tarifa = 0, label = '';
    if (neg.checked && precioDia.value) {
      tarifa = parseInt((precioDia.value||'0').replace(/\D+/g,''))||0;
      label = 'negociada';
    } else {
      // tarifa automática: se recalcula en backend al crear, aquí es estimativa
      if (arg.checked)      { tarifa = 80000; label='argentina'; }
      else if (d===1)       { tarifa = 60000; label='1 día'; }
      else                  { tarifa = 50000; label='estándar'; }
    }

    tarifaLbl.textContent = "$"+fmt(tarifa||0);
    totalLbl.textContent  = "$"+fmt((tarifa||0)*(d||0));
  }



// === Crear reserva / mantención / bloqueo (con pre-chequeo de conflicto) ===
document.getElementById('btnCrear').addEventListener('click', async ()=>{
  const tipoSelEl = document.getElementById('tipo_evento');
  const tipo = (tipoSelEl ? tipoSelEl.value : 'reserva'); // 'reserva' | 'mantencion' | 'bloqueo'

  const ini = document.getElementById('fecha_ini');
  const fin = document.getElementById('fecha_fin');
  const vehSel = document.getElementById('vehiculo_id');

  if (!ini.value || !fin.value) {
    alert('Selecciona un rango de fechas (inicio y fin).');
    return;
  }

  const payloadBase = {
    vehiculo_id: parseInt(vehSel.value, 10),
    inicio: dmyToISO(ini.value),
    fin: dmyToISO(fin.value),
    tipo: tipo
  };

  // 1) Pre-chequeo de conflicto SIEMPRE
  try {
    const chk = await fetch('{{ url_for("cal.api_eventos_check") }}', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payloadBase)
    });
    if (!chk.ok) {
      const err = await chk.json().catch(()=>({error: `HTTP ${chk.status}`}));
      alert(err.error || `Error ${chk.status}`);
      return;
    }
  } catch(e){
    alert('Error de red durante la verificación de conflicto');
    return;
  }

  // 2) Si es RESERVA → completar extras y abrir modal cliente
  if (tipo === 'reserva') {
    const arg = document.getElementById('cruza_arg');
    const neg = document.getElementById('negociada');
    const precioDia = document.getElementById('precio_dia');
    const nota = document.getElementById('nota');

    const payload = {
      ...payloadBase,
      cruza_argentina: !!(arg && arg.checked),
      negociada: !!(neg && neg.checked),
      precio_dia: ((precioDia && precioDia.value) ? precioDia.value : '').replace(/\D+/g,''),
      nota: (nota && nota.value) ? nota.value : ''
    };
    const empSel = document.getElementById('empleado_id');
    if (empSel && empSel.value) {
      payload.empleado_id = parseInt(empSel.value, 10);
    }

    // Guardamos temporal y abrimos modal
    window._payloadReserva = payload;

    const clienteModalEl = document.getElementById('clienteModal');
    if (!clienteModalEl) {
      alert('Falta el modal del cliente en el HTML.');
      return;
    }
    if (window.bootstrap) {
      const bsClienteModal = bootstrap.Modal.getOrCreateInstance(clienteModalEl);
      bsClienteModal.show();
    } else {
      clienteModalEl.style.display = 'block';
      clienteModalEl.classList.add('show');
    }
    return;
  }

  // 3) Si es MANTENCIÓN o BLOQUEO → crear directo (ya chequeado)
  try {
    const r = await fetch('{{ url_for("cal.api_eventos_create") }}', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payloadBase)
    });
    if(!r.ok){
      const err = await r.json().catch(()=>({error:"Error"}));
      alert(err.error || "No se pudo crear el evento");
      return;
    }
    const params = new URLSearchParams(window.location.search);
    window.location = '{{ url_for("cal.home") }}?' + params.toString();
  } catch(e){
    alert('Error de red al crear el evento');
  }
});

// === Guardar cliente y crear RESERVA (sin cambios relevantes)
document.getElementById('btnGuardarCliente')?.addEventListener('click', async ()=>{
  const cNombre = document.getElementById('c_nombre');
  const cApellido = document.getElementById('c_apellido');
  const cRut = document.getElementById('c_rut');
  const cNac = document.getElementById('c_nacionalidad');
  const cTel = document.getElementById('c_telefono');
  const cEmail = document.getElementById('c_email');
  const empSelect = document.getElementById('modal_empleado_id');   // ← NUEVO

  const cliente = {
    nombre: (cNombre?.value || '').trim(),
    apellido: (cApellido?.value || '').trim(),
    rut: (cRut?.value || '').trim(),
    nacionalidad: (cNac?.value || '').trim(),
    telefono: (cTel?.value || '').trim(),
    email: (cEmail?.value || '').trim(),
  };

  if(!cliente.nombre)   { alert('Falta nombre'); return; }
  if(!cliente.apellido) { alert('Falta apellido'); return; }
  if(!cliente.rut)      { alert('Falta RUT'); return; }
  if(!cliente.telefono) { alert('Falta teléfono'); return; }
  if(cliente.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cliente.email)){
    alert('Email inválido'); return;
  }

  const base = window._payloadReserva || null;
  if(!base){ alert('No hay reserva preparada.'); return; }

  // leer empleado seleccionado (opcional)
  let empleado_id = null;
  if (empSelect && empSelect.value) {
    const n = parseInt(empSelect.value, 10);
    if (!isNaN(n) && n > 0) {
      empleado_id = n;
    }
  }

  const payload = { ...base, cliente };

  if (empleado_id) {
    payload.empleado_id = empleado_id;
  }

  try {
    const r = await fetch('{{ url_for("cal.api_eventos_create") }}', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });

    if(!r.ok){
      const err = await r.json().catch(()=>({error:"Error"}));
      alert(err.error || "No se pudo crear");
      return;
    }

    const clienteModalEl = document.getElementById('clienteModal');
    if (window.bootstrap && clienteModalEl){
      const bs = bootstrap.Modal.getOrCreateInstance(clienteModalEl);
      bs.hide();
    }

    const params = new URLSearchParams(window.location.search);
    window.location = '{{ url_for("cal.home") }}?' + params.toString();

  } catch (e) {
    alert('Error de red al crear la reserva');
  }
});


  pintarSel();
  recalc();

    // Delegación: click en 🗑️ para eliminar reserva
  document.addEventListener('click', async (ev)=>{
    const btn = ev.target.closest('.event-del');
    if(!btn) return;

    const id = btn.getAttribute('data-id');
    if(!id) return;

    if(!confirm('¿Eliminar esta reserva?')) return;

    try {
      const r = await fetch(delBase + id, { method: 'DELETE' });
      if(!r.ok){
        const err = await r.json().catch(()=>({error:'Error'}));
        alert(err.error || 'No se pudo eliminar');
        return;
      }
      // recargar manteniendo el mes/los filtros actuales
      window.location.reload();
    } catch (e) {
      alert('Error de red al eliminar');
    }
  });

// ==== Modal de doble clic por día ====

function renderDayCards(dISO, events){
  const dDMY = isoToDMY(dISO);

  const cards = (events && events.length)
    ? events.map(ev=>{
        const bg   = ev.bg || '#0ea5e9';
        const fg   = ev.fg || '#ffffff';
        const veh  = VEHICULOS.find(v=> String(v.id)===String(ev.vehiculo_id)) || null;
        const foto = veh && veh.foto ? `/static/vehiculos/${veh.foto}` : '';
        const subt = ev.tooltip || '';

        // limpiamos el texto " | pista A/B" del tooltip si existe
        const subtClean = subt.replace(/\s*\|\s*pista.*$/i, '');

        // cruza a Argentina efectivo para ese día
        const pf = ev.per_day_flags && ev.per_day_flags[dISO] ? ev.per_day_flags[dISO].cruza_argentina : undefined;
        const cruzaEff = (pf !== undefined && pf !== null) ? !!pf : !!ev.cruza_argentina;
        const flag = cruzaEff ? ' <span title="Cruza a Argentina">🇦🇷</span>' : '';

        // tipo visual (si no viene explícito, inferimos del label para mantención/bloqueo)
        const lbl = (ev.label || '').toLowerCase();
        const tipo = ev.is_reserva
          ? 'Reserva'
          : (lbl.includes('mantención') ? 'Mantención' : (lbl.includes('bloqueo') ? 'Bloqueo' : 'Evento'));

        // datos del vehículo (usa snapshot si ya no existe)
        const vMarca  = (veh && veh.marca)  || ev.veh_marca  || '';
        const vModelo = (veh && veh.modelo) || ev.veh_modelo || '';
        const vAnio   = (veh && (veh.anio||'').toString()) || (ev.veh_anio||'');
        const vPat    = (veh && veh.patente) || ev.veh_patente || '';

        const titulo    = [vMarca, vModelo, vAnio].filter(Boolean).join(' ').trim() || (ev.label || 'Evento');
        const subtitulo = `${vPat ? vPat + ' · ' : ''}${tipo}`;

        // tarifa y cliente
        const tarifaDia = ev.is_reserva ? tarifaParaDia(ev, dISO) : 0;
        const precioHtml = ev.is_reserva
          ? `<div class="small" style="opacity:.9;color:#111">Tarifa del día: $ ${fmt(tarifaDia)}</div>`
          : '';

        const cli = ev.cliente || {};
        const cliLine = (cli.nombre || cli.apellido || cli.telefono || cli.email)
          ? `<div class="small" style="opacity:.85;color:#111">
               ${[ [cli.nombre, cli.apellido].filter(Boolean).join(' '), cli.telefono, cli.email ].filter(Boolean).join(' · ')}
             </div>`
          : '';

        // ===== NUEVO: línea de encargado =====
        const empName =
          (ev.empleado_nombre && String(ev.empleado_nombre).trim()) ||
          (
            ev.empleado &&
            (
              ((ev.empleado.nombre || '') + ' ' + (ev.empleado.apellido || '')).trim()
            )
          ) ||
          '';

        const empLine = empName
          ? `<div class="small" style="opacity:.85;color:#111">Encargado: ${empName}</div>`
          : `<div class="small" style="opacity:.6;color:#111">Sin empleado (lo haces tú)</div>`;
        // =====================================

        return `
          <div class="event-card rounded p-2 mb-2"
               style="background:${bg};color:${fg};border:1px solid rgba(0,0,0,.08)">
            <div class="d-flex align-items-center gap-2">
              ${foto ? `<img src="${foto}" alt="" style="width:58px;height:42px;object-fit:cover;border-radius:.35rem;background:#fff2">` : ``}
              <div class="flex-grow-1 min-w-0">
                <div class="fw-semibold text-truncate" style="color:#111" title="${titulo}">${titulo}${flag}</div>
                <div class="small text-truncate" style="opacity:.9;color:#111" title="${subtitulo}">${subtitulo}</div>
                ${precioHtml}
                ${cliLine}
                ${empLine}
                ${subtClean ? `<div class="small" style="opacity:.85;color:#111">${subtClean}</div>` : ``}
              </div>
              <button class="btn btn-sm btn-light text-dark ver-detalle" data-id="${ev.id}">
                Ver detalle
              </button>
            </div>
          </div>
        `;
      }).join('')
    : `<div class="text-secondary">No hay eventos este día.</div>`;

  return `
    <div class="day-modal">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h6 class="mb-0">Eventos del ${dDMY}</h6>
      </div>
      ${cards}
    </div>
  `;
}
// ===== Helpers de cálculo para el detalle =====
function diasEntreISO(iniISO, finISO){
  if(!iniISO || !finISO) return 0;
  const sd = new Date(iniISO + "T00:00:00");
  const ed = new Date(finISO + "T00:00:00");
  return Math.round((ed - sd)/86400000) + 1; // inclusive
}

// Tarifa efectiva para un día específico (dayISO = "YYYY-MM-DD")
function tarifaParaDia(ev, dayISO){
  const per = ev.per_day_overrides || {};

  // 1) override por día
  if (per[dayISO] != null) {
    const n = parseInt(String(per[dayISO]).replace(/\D+/g,'')) || 0;
    return n;
  }

  // 2) precio negociado global
  if (ev.negociada && ev.precio_dia){
    const n = parseInt(String(ev.precio_dia).replace(/\D+/g,'')) || 0;
    if (n > 0) return n;
  }

  // 3) cruza a Argentina efectivo por día (per_day_flags > global)
  const pf = ev.per_day_flags && ev.per_day_flags[dayISO] ? ev.per_day_flags[dayISO].cruza_argentina : undefined;
  const cruzaEff = (pf !== undefined && pf !== null) ? !!pf : !!ev.cruza_argentina;
  if (cruzaEff) return 80000;

  // 4) regla estándar según duración
  const d = diasEntreISO(ev.inicio, ev.fin);
  if (d === 1) return 60000;
  return 50000;
}

// Total de toda la reserva considerando overrides por día
function totalConOverrides(ev){
  const per = ev.per_day_overrides || {};
  const di = ev.inicio, df = ev.fin;
  if (!di || !df) return 0;
  const sd = new Date(di+"T00:00:00");
  const ed = new Date(df+"T00:00:00");
  let tot = 0;
  for (let d = new Date(sd); d <= ed; d.setDate(d.getDate()+1)){
    const k = d.toISOString().slice(0,10); // YYYY-MM-DD
    if (per[k] != null){
      const n = parseInt(String(per[k]).replace(/\D+/g,'')) || 0;
      tot += n;
    } else if (ev.negociada && ev.precio_dia){
      const n = parseInt(String(ev.precio_dia).replace(/\D+/g,'')) || 0;
      tot += n;
    } else {
      // sin override ni negociada: aplica regla por defecto para ese día
      tot += tarifaParaDia(ev, k);
    }
  }
  return tot;
}
function openEventDetail(ev, eventsDelDia, dayISO){
  // Fallback por si no vino dayISO:
  if (!dayISO) {
    dayISO = (ev.inicio || ev.fecha || '').slice(0,10); // "YYYY-MM-DD"
  }

  const modalEl = document.getElementById('dayModal');
  const body  = modalEl.querySelector('#dayModalBody');
  const title = modalEl.querySelector('#dayModalTitle');

  const bg   = ev.bg || '#0ea5e9';
  const fg   = ev.fg || '#ffffff';
  const veh  = VEHICULOS.find(x=>String(x.id)===String(ev.vehiculo_id)) || null;
  const foto = veh && veh.foto ? `/static/vehiculos/${veh.foto}` : '';

// usar snapshot si el vehículo ya no existe
  const modelo  = (veh && veh.modelo)  || ev.veh_modelo || (ev.label || 'Reserva');
  const patente = (veh && veh.patente) || ev.veh_patente || '';
  const kmTxt   = veh && (typeof veh.km !== 'undefined') ? fmt(veh.km||0) : null;

  // día concreto del listado (si no vino, usamos el inicio del evento)

  const dayIsoLocal = (dayISO && dayISO.length ? dayISO : (ev.inicio || '').slice(0,10));
  const pfHdr = (ev.per_day_flags && ev.per_day_flags[dayIsoLocal]) ? ev.per_day_flags[dayIsoLocal].cruza_argentina : undefined;
  const cruzaHdr = (pfHdr !== undefined && pfHdr !== null) ? !!pfHdr : !!ev.cruza_argentina;
  const dias       = diasEntreISO(ev.inicio, ev.fin);
  const tarifaDia  = tarifaParaDia(ev, dayIsoLocal);                 // tarifa específica del día abierto
  const total      = (toDigitsInt(ev.total_amount) ?? totalConOverrides(ev) ?? (tarifaDia * dias));
  const rango      = (ev.inicio && ev.fin) ? `${isoToDMY(ev.inicio)} a ${isoToDMY(ev.fin)}` : '';

  const chkArg = !!ev.cruza_argentina;
  const chkNeg = !!ev.negociada;
  const valPrecio = ev.precio_dia ? ev.precio_dia.toString().replace(/\D+/g,'').replace(/\B(?=(\d{3})+(?!\d))/g, '.') : '';
  const cli = ev.cliente || {};
  const nombreCompleto = [cli.nombre, cli.apellido].filter(Boolean).join(' ').trim();
  const telHtml  = cli.telefono ? `<a href="tel:${cli.telefono}" style="text-decoration:none">${cli.telefono}</a>` : '';
  const mailHtml = cli.email    ? `<a href="mailto:${cli.email}" style="text-decoration:none">${cli.email}</a>` : '';
  const nacHtml  = cli.nacionalidad ? cli.nacionalidad : '';
 
  title.textContent = `Detalle de evento #${ev.id}`;
// título del encabezado con marca + modelo + año
  const v = VEHICULOS.find(x=>String(x.id)===String(ev.vehiculo_id)) || null;
  const tMarca  = (v && v.marca)  || ev.veh_marca  || '';
  const tModelo = (v && v.modelo) || ev.veh_modelo || '';
  const tAnio   = (v && (v.anio||'').toString()) || (ev.veh_anio||'');
  const tituloHdr = [tMarca, tModelo, tAnio].filter(Boolean).join(' ').trim() || (ev.label || 'Reserva');

  // Texto de patente y km
  const vPat = VEHICULOS.find(x=>String(x.id)===String(ev.vehiculo_id)) || null;
  const pat  = (vPat && vPat.patente) || ev.veh_patente || '';
  const km   = vPat && (typeof vPat.km !== 'undefined') ? fmt(vPat.km||0) : null;
  const patenteTexto = pat
    ? `Patente ${pat}${km ? ' · ' + km + ' km' : ''}`
    : (km ? (km + ' km') : '');

  title.textContent = `Detalle de evento #${ev.id}`;
  body.innerHTML = `
    <div class="day-modal p-4" style="background:#fff; border-radius:.75rem; border:1px solid #e5e7eb; margin-top:1rem;">
      <div class="rounded p-3 mb-3" style="background:${bg};color:${fg};border:1px solid rgba(0,0,0,.08)">
        <div class="d-flex align-items-center gap-3">
          ${foto ? `<img src="${foto}" style="width:120px;height:80px;object-fit:cover;border-radius:.5rem;background:#fff2">` : ``}
          <div class="flex-grow-1">
            <div class="fw-semibold" style="color:#111">${tituloHdr}${cruzaHdr ? ' <span title="Cruza a Argentina">🇦🇷</span>' : ''}</div>
            <div class="small" style="opacity:.9;color:#111">${patenteTexto}</div>
          </div>
        </div>
      </div>

      ${ev.label ? `<div class="mb-2"><strong style="color:#111">Título:</strong> <span style="color:#111">${ev.label}</span></div>` : ``}
      ${ev.tooltip ? `<div class="mb-2"><strong style="color:#111">Descripción:</strong> <span style="color:#111">${ev.tooltip}</span></div>` : ``}
      ${rango ? `<div class="mb-2"><strong style="color:#111">Rango:</strong> <span style="color:#111">${rango}</span></div>` : ``}
      <div class="mt-3 mb-2">
        <div class="mb-1"><strong style="color:#111">Cliente</strong></div>
        ${
          (nombreCompleto || telHtml || mailHtml || nacHtml)
          ? `<div class="small" style="color:#111">
               ${nombreCompleto ? nombreCompleto : ''}
               ${nacHtml ? ` · ${nacHtml}` : ''}
               ${telHtml ? ` · ${telHtml}` : ''}
               ${mailHtml ? ` · ${mailHtml}` : ''}
             </div>`
          : `<div class="small text-secondary">Sin datos de cliente.</div>`
        }
      </div>
            <div class="mt-3 mb-2">
        <div class="mb-1"><strong style="color:#111">Encargado</strong></div>
        <div class="small" style="color:#111">
          ${
            (()=>{
              const snap = (ev.empleado_nombre || '').trim();
              const eid  = ev.empleado_id;
              if (snap) return snap;
              if (eid) {
                const emp = EMPLEADOS.find(e => String(e.id) === String(eid));
                if (emp) {
                  const nom = (emp.nombre || '').trim();
                  const ape = (emp.apellido || '').trim();
                  const full = (nom + ' ' + ape).trim();
                  return full || ('Empleado #' + eid);
                }
                return 'Empleado #' + eid + ' (eliminado)';
              }
              return 'Sin empleado (lo haces tú)';
            })()
          }
        </div>
      </div>
      <div class="row g-2 mt-3">
        <div class="col-6"><div><strong style="color:#111">Días</strong></div><div style="color:#111">${dias}</div></div>
        <div class="col-6"><div><strong style="color:#111">Tarifa por día</strong></div><div id="tarifa_dia_lbl" style="color:#111">$ ${fmt(tarifaDia)}</div></div>
        <div class="col-12"><div><strong style="color:#111">Total arriendo</strong></div><div id="total_lbl_ev" class="h6 mb-0" style="color:#111">$ ${fmt(total)}</div></div>
      </div>

      <hr class="my-3">

      <div class="mb-2"><strong style="color:#111">Editar</strong></div>
      <div class="form-check form-switch mb-2">
        <input class="form-check-input" type="checkbox" id="ed_cruza_arg" ${chkArg ? 'checked' : ''}>
        <label class="form-check-label" for="ed_cruza_arg" style="color:#111">Cruza a Argentina</label>
      </div>

      <div class="form-check form-switch mb-2">
        <input class="form-check-input" type="checkbox" id="ed_negociada" ${chkNeg ? 'checked' : ''}>
        <label class="form-check-label" for="ed_negociada" style="color:#111">Precio negociado (global)</label>
      </div>

      <div class="input-group input-group-sm mb-3" style="max-width:220px">
        <span class="input-group-text">$</span>
        <input type="text" class="form-control" id="ed_precio_dia" placeholder="por día"
               ${chkNeg ? '' : 'disabled'} value="${valPrecio}">
      </div>

      <div class="alert alert-secondary py-2 px-3" style="font-size:.9rem">
        Nota: si ajustas el precio desde este detalle, se guardará como <em>override</em> para el día ${isoToDMY(dayIsoLocal)}.
      </div>

      <div class="d-flex gap-2 mt-2 flex-wrap">
  <button class="btn btn-sm btn-primary" id="btnGuardarEv">Guardar cambios</button>
  <a class="btn btn-sm btn-success" id="btnContrato" href="/admin/contratos/desde-reserva/${ev.id}">Generar contrato</a>
  <button class="btn btn-sm btn-outline-secondary" id="btnVolverLista">Volver</button>
</div>
    </div>
  `;

  const swArg     = body.querySelector('#ed_cruza_arg');
  const swNeg     = body.querySelector('#ed_negociada');
  const inpPrecio = body.querySelector('#ed_precio_dia');
  const lblTarifa = body.querySelector('#tarifa_dia_lbl');
  const lblTotal  = body.querySelector('#total_lbl_ev');

  function syncPrecioState(){
    const allow = swNeg.checked;
    inpPrecio.disabled = !allow;
    if (!allow) inpPrecio.value = '';
  }
  swNeg.addEventListener('change', ()=>{
    syncPrecioState();
    // no recalculamos total del evento aquí porque el total lo recalcula el backend
  });
  syncPrecioState();

  // formateo miles y actualización del label de tarifa del día
  inpPrecio.addEventListener('input', ()=>{
    if (inpPrecio.disabled) return;
    const selStart = inpPrecio.selectionStart;
    const old = inpPrecio.value;
    const digits = old.replace(/\D+/g,'');
    const fmtVal = digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const right = old.length - selStart;
    inpPrecio.value = fmtVal;
    const newPos = Math.max(0, inpPrecio.value.length - right);
    inpPrecio.setSelectionRange(newPos, newPos);

    // actualizar la vista de "Tarifa por día" con lo que estás tipeando
    const n = toDigitsInt(fmtVal) || 0;
    lblTarifa.textContent = '$ ' + fmt(n);
  });

  body.querySelector('#btnGuardarEv').addEventListener('click', async ()=>{
  // dayISO viene por parámetro; si no existe, arriba pusimos fallback
  const fechaDMY = isoToDMY(dayIsoLocal);   // "DD-MM-YYYY"

  const payload = {
    cruza_argentina: !!swArg.checked,
    negociada: !!swNeg.checked,
    precio_dia: inpPrecio.disabled ? '' : (inpPrecio.value || '').replace(/\D+/g,''),
    // IMPORTANTE: enviar SIEMPRE el día específico
    target_date: fechaDMY
  };

  try {
    const updURL = ('{{ url_for("cal.api_eventos_update", eid=0) }}'.match(/api_eventos_update/))
      ? '{{ url_for("cal.api_eventos_update", eid=0) }}'.replace(/0$/, String(ev.id))
      : (delBase.replace(/\/$/, '') + '/' + String(ev.id));

    const r = await fetch(updURL, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(!r.ok){
      const err = await r.json().catch(()=>({error:`HTTP ${r.status}`}));
      alert(err.error || `Error ${r.status}`);
      return;
    }
    window.location.reload();
  } catch(e){
    alert('Error de red al guardar');
  }
});

  body.querySelector('#btnVolverLista').addEventListener('click', ()=>{
    const backDate = dayIsoLocal || (ev.inicio || ev.fecha || '').slice(0,10) || (new Date()).toISOString().slice(0,10);
    body.innerHTML = renderDayCards(backDate, eventsDelDia);
    body.querySelectorAll('.ver-detalle').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const id = btn.getAttribute('data-id');
        const e  = eventsDelDia.find(x=>String(x.id)===String(id));
        if(e) openEventDetail(e, eventsDelDia, backDate);
      });
    });
  });
}

function openDayModal(dISO, events){
  const modalEl = document.getElementById('dayModal');
  const body = modalEl.querySelector('#dayModalBody');
  const title = modalEl.querySelector('#dayModalTitle');

  // setear título y contenido
  title.textContent = `Eventos del ${isoToDMY(dISO)}`;
  body.innerHTML = renderDayCards(dISO, events);

  // enganchar "Ver detalle"
  body.querySelectorAll('.ver-detalle').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      const id = btn.getAttribute('data-id');
      const ev = events.find(x=>String(x.id)===String(id));
      if(ev) openEventDetail(ev, events, dISO);
    });
  });

  // abrir
  if (window.bootstrap && bootstrap.Modal){
    const bs = bootstrap.Modal.getOrCreateInstance(modalEl);
    bs.show();
  } else {
    modalEl.style.display = 'block';
    modalEl.classList.add('show');
  }
}

// Doble clic con delegación: funciona aunque cambie el DOM
document.addEventListener('dblclick', (ev)=>{
  const cell = ev.target.closest('.cal-cell');
  if (!cell) return;

  const dISO = cell.getAttribute('data-date');
  if (!dISO) return;

  let events = [];
  try {
    const raw = cell.getAttribute('data-events') || '[]';
    events = JSON.parse(raw);
  } catch { events = []; }

  if (typeof openDayModal === 'function') {
    openDayModal(dISO, events);
  } else {
    console.error('openDayModal no está definida');
  }
});
})();   // ← NO LO BORRES, CIERRA TODO
</script>
"""

def veh_foto_url(v):
    foto = v.get("foto")
    if not foto: return ""
    return f"/static/vehiculos/{foto}"

def render_admin_bp(html, active="calendario"):
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)


# ---- RUTA PRINCIPAL /admin/calendario ----

@cal_bp.route("/")
def home():
    ym = request.args.get("month")
    y, m = parse_month(ym) if ym else (date.today().year, date.today().month)
    ym = f"{y:04d}-{m:02d}"

    veh_sel = (request.args.get("veh") or "all").strip()  # 'all' o id numérico

    vehiculos = load_vehiculos()
    current_app.logger.info(f"Vehículos visibles en calendario: {len(vehiculos)}")
    empleados = load_empleados()

    # IDs filtrados (o None si 'all')
    if veh_sel != "all":
        try:
            veh_ids = {int(veh_sel)}
        except Exception:
            veh_ids = None
            veh_sel = "all"
    else:
        veh_ids = None

    # Vehículo seleccionado (para panel derecho)
    sel_v = None
    if veh_sel != "all":
        try:
            sel_id = int(veh_sel)
            sel_v = next((v for v in vehiculos if int(v.get("id", 0)) == sel_id), None)
        except Exception:
            sel_v = None
    veh_first = sel_v or (vehiculos[0] if vehiculos else {})

    # Eventos del mes
    eventos = load_eventos()
    first, last = month_range(y, m)

    ev_mes = []
    for e in eventos:
        try:
            vid = int(e.get("vehiculo_id", 0))
            if veh_ids and vid not in veh_ids:
                continue

            inicio = e.get("inicio")
            fin = e.get("fin")
            if not inicio or not fin:
                continue

            ei = parse_iso(str(inicio))
            ef = parse_iso(str(fin))
            if overlap(ei, ef, first, last):
                ev_mes.append(e)
        except Exception:
            continue

    # Construir celdas (6 semanas comenzando lunes)
    first_weekday = first.weekday()  # 0=lunes ... 6=domingo
    start_grid = first - timedelta(days=first_weekday)
    cells = []

    for i in range(42):
        d = start_grid + timedelta(days=i)
        in_month = (first <= d <= last)

        # Eventos que caen en este día
        day_events = []
        for e in ev_mes:
            try:
                ei = parse_iso(str(e["inicio"]))
                ef = parse_iso(str(e["fin"]))
            except Exception:
                continue
            if not (ei <= d <= ef):
                continue

            v = next((x for x in vehiculos if int(x.get("id", 0)) == int(e.get("vehiculo_id", 0))), None)
            color_a = (v or {}).get("color_a", "#0ea5e9")
            color_b = (v or {}).get("color_b", "#ef4444")

            tipo_raw = (e.get("tipo") or "reserva").lower()
            if tipo_raw == "mantencion":
                bg, fg = "rgba(251, 191, 36, 0.6)", "#111827"
            elif tipo_raw == "bloqueo":
                bg, fg = "rgba(203, 213, 225, 0.9)", "#111827"
            else:
                bg = color_a if (e.get("pista") or "A") == "A" else color_b
                fg = "#0f172a"

            tipo_txt = "Mantención" if tipo_raw == "mantencion" else ("Bloqueo" if tipo_raw == "bloqueo" else "Reserva")
            label = f"{(v or {}).get('patente','')} · {tipo_txt}"

            k_dia = d.strftime("%Y-%m-%d")
            per_flags = e.get("per_day_flags") or {}
            pf = (per_flags.get(k_dia) or {}).get("cruza_argentina", None)
            cruza_eff = bool(e.get("cruza_argentina")) if (pf is None) else bool(pf)

            day_events.append({
            "id": e.get("id"),
            "vehiculo_id": int(e.get("vehiculo_id", 0)),
            "label": label,
            "bg": bg,
            "fg": fg,
            "cruza_argentina": cruza_eff,
            "inicio": str(e["inicio"]),
            "fin": str(e["fin"]),
            "daily": e.get("daily_rate_applied", 0),
            "pricing_source": e.get("pricing_source", "estandar"),
            "negociada": bool(e.get("negociada", (e.get("pricing_source") == "negociada"))),
            "precio_dia": e.get("precio_dia"),
            "per_day_overrides": e.get("per_day_overrides", {}),
            # tooltip sin texto de pista
            "tooltip": f"{label} | {e['inicio']} → {e['fin']}",
            "is_reserva": (tipo_raw == "reserva"),
            "per_day_flags": e.get("per_day_flags", {}),
            "cliente": e.get("cliente", {}),

            # 👇 NUEVO: datos del empleado que ya están guardados en el JSON
            "empleado_id": e.get("empleado_id"),
            "empleado_nombre": e.get("empleado_nombre"),

            # snapshots por si el vehículo ya no existe
            "veh_modelo": e.get("veh_modelo"),
            "veh_patente": e.get("veh_patente"),
        })

        cells.append({
            "date": d,
            "in_month": in_month,
            "events": day_events,
            "badge_count": len(day_events),
            "is_today": (d == date.today()),
        })

    # Totales
    total_mes = total_del_mes(ev_mes, y, m, None)
    total_mes_veh = 0
    if veh_sel != "all":
        try:
            total_mes_veh = total_del_mes(ev_mes, y, m, int(veh_sel))
        except Exception:
            total_mes_veh = 0

    ctx = dict(
        ym=ym,
        month_label=f"{y}-{m:02d}",
        prev_month=f"{(y if m>1 else y-1):04d}-{(m-1 if m>1 else 12):02d}",
        next_month=f"{(y if m<12 else y+1):04d}-{(m+1 if m<12 else 1):02d}",
        vehiculos=vehiculos,
        veh_sel=veh_sel,
        total_mes=total_mes,
        total_mes_veh=total_mes_veh,
        cells=cells,
        veh_foto_url=veh_foto_url,
        veh_first=veh_first,
        empleados=empleados,          # ← NUEVO
    )
    html = render_template_string(CAL_HTML, **ctx)
    return render_admin_bp(html, active="calendario")

# ---- API: crear evento (reserva) ----

@cal_bp.route("/api/eventos", methods=["POST"])
def api_eventos_create():
    from datetime import timedelta
    data = request.get_json(force=True) or {}

    vehiculo_id = int(data.get("vehiculo_id", 0))
    inicio = data.get("inicio")
    fin = data.get("fin")
    if not (vehiculo_id and inicio and fin):
        return jsonify({"error": "Faltan datos"}), 400

    try:
        di, df = parse_iso(inicio), parse_iso(fin)
    except Exception:
        return jsonify({"error": "Fechas inválidas"}), 400
    if df < di:
        return jsonify({"error": "Fin anterior a inicio"}), 400

    # Tipo
    tipo = (data.get("tipo") or "reserva").strip().lower()
    if tipo not in ("reserva", "mantencion", "bloqueo"):
        return jsonify({"error": "Tipo inválido"}), 400

    vehiculos = load_vehiculos()
    veh = next((x for x in vehiculos if int(x.get("id", 0)) == vehiculo_id), None)
    if not veh:
        return jsonify({"error": "Vehículo no encontrado"}), 404

    # === SNAPSHOT DE VEHÍCULO (marca/modelo/año/patente) ===
    veh = _veh_normalizado(veh)
    veh_marca   = veh.get("marca") or ""
    veh_modelo  = veh.get("modelo") or ""
    veh_anio    = veh.get("anio") or ""
    veh_patente = veh.get("patente") or ""

    eventos = load_eventos()

    # Solapes (contra cualquier tipo)
    for evx in eventos:
        if int(evx.get("vehiculo_id", 0)) != vehiculo_id:
            continue
        ei, ef = parse_iso(evx["inicio"]), parse_iso(evx["fin"])
        if overlap(ei, ef, di, df):
            tipo_exist = evx.get("tipo", "evento")
            return jsonify({
                "error": f"Conflicto: ya existe {tipo_exist} en esas fechas ({evx['inicio']}→{evx['fin']})."
            }), 409

    # Pista A/B solo para reserva
    pista = None
    if tipo == "reserva":
        pista = "A"
        one_day = timedelta(days=1)
        contigua = None
        for evx in eventos:
            if int(evx.get("vehiculo_id", 0)) != vehiculo_id or evx.get("tipo") != "reserva":
                continue
            ei, ef = parse_iso(evx["inicio"]), parse_iso(evx["fin"])
            if ef + one_day == di or df + one_day == ei:
                contigua = evx
                break
        if contigua:
            pista = "B" if contigua.get("pista") == "A" else "A"

    # Tarifas / totales
    dias = dias_inclusivos(di, df)
    if tipo == "reserva":
        cruza_arg = bool(data.get("cruza_argentina"))
        if bool(data.get("negociada")):
            try:
                daily = int(str(data.get("precio_dia") or "0").replace(".", ""))
            except Exception:
                daily = 0
            src = "negociada"
        else:
            daily, src = tarifa_del_dia(veh, cruza_arg, dias)
        total = int(daily or 0) * int(dias or 0)
        nota = (data.get("nota") or "")
    else:
        cruza_arg = False
        daily = 0
        src = tipo
        total = 0
        nota = (data.get("nota") or "")

    # Cliente (si viene en el payload)
    cliente = data.get("cliente") or {}
    cliente = {
        "nombre": (cliente.get("nombre") or "").strip(),
        "apellido": (cliente.get("apellido") or "").strip(),
        "rut": (cliente.get("rut") or "").strip(),
        "nacionalidad": (cliente.get("nacionalidad") or "").strip(),
        "telefono": (cliente.get("telefono") or "").strip(),
        "email": (cliente.get("email") or "").strip(),
    }
    # === Empleado encargado (opcional) ===
    empleados = load_empleados()
    empleado_id = None
    empleado_nombre = ""

    raw_emp = data.get("empleado_id")
    if raw_emp not in (None, "", 0, "0"):
        try:
            emp_id = int(raw_emp)
        except Exception:
            emp_id = 0
        if emp_id > 0:
            emp = next((e for e in empleados if int(e.get("id") or 0) == emp_id), None)
            if emp:
                nom = (emp.get("nombre") or "").strip()
                ape = (emp.get("apellido") or "").strip()
                full = (nom + " " + ape).strip()
                empleado_id = emp_id
                empleado_nombre = full or (emp.get("rut") or f"Empleado {emp_id}")

    ev = {
        "id": (max([e.get("id", 0) for e in eventos], default=0) + 1),
        "vehiculo_id": vehiculo_id,
        "tipo": tipo,
        "inicio": inicio,
        "fin": fin,
        "pista": pista,
        "cruza_argentina": cruza_arg,
        "pricing_source": src,            # estandar/negociada/mantencion/bloqueo
        "daily_rate_applied": daily,      # 0 si no es reserva
        "total_amount": total,            # 0 si no es reserva
        "nota": nota,
        "negociada": (src == "negociada"),
        "precio_dia": (daily if src == "negociada" else None),
        "per_day_overrides": {},
        "per_day_flags": {},
        "cliente": cliente,

        # snapshot de vehículo (para contratos/reportes)
        "veh_marca":   veh_marca,
        "veh_modelo":  veh_modelo,
        "veh_anio":    str(veh_anio),
        "veh_patente": veh_patente,
    }
    # snapshot de empleado (para historial y gastos)
    if empleado_id:
        ev["empleado_id"] = empleado_id
        ev["empleado_nombre"] = empleado_nombre

    eventos.append(ev)
    save_eventos(eventos)

        # Crear gasto de empleado (comisión) si corresponde
    try:
        if tipo == "reserva" and ev.get("empleado_id"):
            _crear_gasto_empleado_para_evento(ev)
    except Exception:
        current_app.logger.exception("Fallo al crear gasto de empleado para evento %s", ev.get("id"))

    # Sincronizar contrato automático desde la reserva
    try:
        from contratos_utils import upsert_contract_from_event
        upsert_contract_from_event(ev, veh)  # veh ya normalizado
    except Exception:
        current_app.logger.exception("Fallo al sincronizar contrato desde reserva (create)")

    return jsonify({"ok": True, "evento": ev}), 201

@cal_bp.route("/api/eventos/<int:eid>", methods=["DELETE"])
def api_eventos_delete(eid):
    eventos = load_eventos()
    idx = next((i for i, e in enumerate(eventos) if int(e.get("id", 0)) == eid), None)
    if idx is None:
        return jsonify({"error": "Evento no encontrado"}), 404

    # guardar por si quieres usarlo en el futuro
    ev_borrado = eventos[idx]

    # Eliminar evento
    del eventos[idx]
    save_eventos(eventos)

    # Eliminar gastos ligados a esta reserva (comisión empleado)
    try:
        _eliminar_gastos_por_evento(eid)
    except Exception:
        current_app.logger.exception("Fallo al eliminar gastos asociados al evento %s", eid)

    return jsonify({"ok": True})

@cal_bp.route("/api/eventos/<int:eid>", methods=["PATCH"])
def api_eventos_update(eid):
    from datetime import datetime, timedelta
    data = request.get_json(silent=True) or {}

    eventos = load_eventos()
    ev = next((e for e in eventos if int(e.get("id", 0)) == int(eid)), None)
    if not ev:
        return jsonify({"error": "No existe evento"}), 404

    # Normalización precio_dia
    precio_raw = data.get("precio_dia", None)
    precio_val = None
    if precio_raw is not None:
        s = str(precio_raw).strip().replace(".", "")
        s = "".join(ch for ch in s if ch.isdigit())
        precio_val = int(s) if s.isdigit() else None

    # Parse fecha objetivo (YYYY-MM-DD o DD-MM-YYYY)
    def parse_any_date(s):
        if not s:
            return None
        s = str(s).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        return None

    target_date = data.get("target_date") or data.get("target_date_dmy")
    d = parse_any_date(target_date)

    # Estructuras por defecto
    if ev.get("per_day_overrides") is None or not isinstance(ev.get("per_day_overrides"), dict):
        ev["per_day_overrides"] = {}
    if ev.get("per_day_flags") is None or not isinstance(ev.get("per_day_flags"), dict):
        ev["per_day_flags"] = {}

    # Merge opcional de cliente
    if "cliente" in data and isinstance(data["cliente"], dict):
        ev.setdefault("cliente", {})
        for k in ("nombre", "apellido", "rut", "nacionalidad", "telefono", "email"):
            if k in data["cliente"]:
                ev["cliente"][k] = (data["cliente"].get(k) or "").strip()

    # Edición global
    if not d:
        if "cruza_argentina" in data:
            ev["cruza_argentina"] = bool(data["cruza_argentina"])
        if "negociada" in data:
            ev["negociada"] = bool(data["negociada"])

        if (ev.get("tipo") or "reserva").lower() == "reserva":
            vehiculos = load_vehiculos()
            veh = next((v for v in vehiculos if int(v.get("id")) == int(ev.get("vehiculo_id"))), None)
            di, df = parse_iso(ev["inicio"]), parse_iso(ev["fin"])
            dias = dias_inclusivos(di, df)

            if ev.get("negociada") and (precio_val is not None):
                ev["daily_rate_applied"] = int(precio_val)
                ev["pricing_source"] = "negociada"
                ev["precio_dia"] = int(precio_val)
            else:
                daily, src = tarifa_del_dia(veh, bool(ev.get("cruza_argentina")), dias)
                ev["daily_rate_applied"] = int(daily or 0)
                ev["pricing_source"] = src or "estandar"
                ev["precio_dia"] = None

    # Edición por día
    else:
        k = d.strftime("%Y-%m-%d")
        if precio_raw is not None:
            if precio_val is not None:
                ev["per_day_overrides"][k] = int(precio_val)
            else:
                ev["per_day_overrides"].pop(k, None)
        if "cruza_argentina" in data:
            day_flags = ev["per_day_flags"].get(k, {})
            day_flags["cruza_argentina"] = bool(data["cruza_argentina"])
            ev["per_day_flags"][k] = day_flags

    # Recalcular total
    di, df = parse_iso(ev["inicio"]), parse_iso(ev["fin"])
    per_prices = ev.get("per_day_overrides") or {}
    per_flags  = ev.get("per_day_flags") or {}
    vehiculos = load_vehiculos()
    veh = next((v for v in vehiculos if int(v.get("id")) == int(ev.get("vehiculo_id"))), None)

    total = 0
    dias_totales = dias_inclusivos(di, df)
    dcur = di
    while dcur <= df:
        k = dcur.strftime("%Y-%m-%d")
        if k in per_prices and per_prices[k] is not None:
            total += int(per_prices[k] or 0)
        else:
            if ev.get("negociada") and ev.get("precio_dia"):
                total += int(ev["precio_dia"] or 0)
            else:
                day_flag = (per_flags.get(k) or {}).get("cruza_argentina", None)
                cruza_eff = bool(ev.get("cruza_argentina")) if (day_flag is None) else bool(day_flag)
                daily, _src = tarifa_del_dia(veh, cruza_eff, dias_totales)
                total += int(daily or 0)
        dcur += timedelta(days=1)

    ev["total_amount"] = int(total or 0)
    save_eventos(eventos)

    # Sincronizar contrato tras la edición
    try:
        from contratos_utils import upsert_contract_from_event
        upsert_contract_from_event(ev, veh)
    except Exception:
        current_app.logger.exception("Fallo al sincronizar contrato tras update")

    return jsonify({"ok": True, "evento": ev})

@cal_bp.route("/api/eventos/check", methods=["POST"])
def api_eventos_check():
    data = request.get_json(force=True) or {}

    vehiculo_id = int(data.get("vehiculo_id", 0))
    inicio = data.get("inicio")
    fin = data.get("fin")

    if not (vehiculo_id and inicio and fin):
        return jsonify({"error": "Faltan datos"}), 400

    try:
        di, df = parse_iso(inicio), parse_iso(fin)
    except Exception:
        return jsonify({"error": "Fechas inválidas"}), 400

    if df < di:
        return jsonify({"error": "Fin anterior a inicio"}), 400

    # Reutilizamos la lógica de conflicto de create, pero sin guardar
    eventos = load_eventos()
    for evx in eventos:
        if int(evx.get("vehiculo_id", 0)) != vehiculo_id:
            continue
        ei, ef = parse_iso(evx["inicio"]), parse_iso(evx["fin"])
        if overlap(ei, ef, di, df):
            tipo_exist = evx.get("tipo", "evento")
            return jsonify({
                "error": f"Conflicto: ya existe {tipo_exist} en esas fechas ({evx['inicio']}→{evx['fin']})."
            }), 409

    return jsonify({"ok": True}), 200