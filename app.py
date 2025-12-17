from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, inspect, text
from datetime import datetime, date, timedelta
import os
import re

app = Flask(__name__)

# --- Filtro CLP (formato chileno) ---
def clp(valor):
    # Si viene None o algo raro, devolvemos "0"
    if valor is None:
        return "0"
    try:
        # Intentamos convertir a entero y formatear
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        # Si por algún motivo no se puede (por ejemplo Undefined),
        # devolvemos "0" para no romper la plantilla
        return "0"

app.jinja_env.filters['clp'] = clp

# DB
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///vcespedes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "clave-super-secreta-vcespedes"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Archivos
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "img", "cuchillos")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

db = SQLAlchemy(app)

# Helpers
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_price(value: str) -> int:
    solo_digitos = re.sub(r"\D", "", value)
    return int(solo_digitos) if solo_digitos else 0

# ─────────────────────────────
# MODELOS
# ─────────────────────────────
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)    # Ej: N31
    nombre = db.Column(db.String(120), nullable=False)

    categoria_principal = db.Column(db.String(50))
    categoria_secundaria = db.Column(db.String(50))
    acero = db.Column(db.String(50))
    mango = db.Column(db.String(100))
    largo_hoja_cm = db.Column(db.Float)
    largo_mango_cm = db.Column(db.Float)

    precio_menor = db.Column(db.Integer, nullable=False)
    precio_concesion = db.Column(db.Integer, nullable=False)
    precio_mercadolibre = db.Column(db.Integer, nullable=False)

    imagen = db.Column(db.String(200))  # p.ej. "img/cuchillos/n31.png"

    def __repr__(self):
        return f"<Producto {self.codigo} - {self.nombre}>"

# GASTOS
CATEGORIAS_GASTO = ["Compra", "Impuestos", "Envío", "Otro"]

class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    categoria = db.Column(db.String(30), nullable=False)
    detalle = db.Column(db.String(200))
    monto = db.Column(db.Integer, nullable=False)

# TIENDAS / STOCK
class Tienda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Tienda / Bodega / Vendedor
    ciudad = db.Column(db.String(80))
    activa = db.Column(db.Boolean, default=True)

    # Archivado (soft delete)
    eliminada = db.Column(db.Boolean, default=False)
    eliminada_en = db.Column(db.DateTime)

    # Bodega o tienda desde donde se alimenta el stock
    fuente_stock_id = db.Column(db.Integer, db.ForeignKey("tienda.id"), nullable=True)
    fuente_stock = db.relationship("Tienda", remote_side=[id])

    # Tipo de precio que usa esta tienda para ventas: "menor", "concesion", "mercadolibre"
    tipo_precio = db.Column(db.String(20), default="concesion")

    # Campo antiguo (lo dejamos para compatibilidad, pero ya no lo usamos en la lógica nueva)
    cobra_iva_extra = db.Column(db.Boolean, default=False)

    # Modo IVA:
    #  - "incluido": el precio/base que usas ya incluye IVA (tú lo pagas; se calcula estimación)
    #  - "extra": se suma IVA 19% encima del monto (lo paga el cliente)
    #  - "no": no se cobra / no se declara IVA por estas ventas
    iva_modo = db.Column(db.String(20), default="incluido")

    stocks = db.relationship("StockTienda", back_populates="tienda", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tienda {self.nombre}>"

class StockTienda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tienda_id = db.Column(db.Integer, db.ForeignKey("tienda.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=0)

    tienda = db.relationship("Tienda", back_populates="stocks")
    producto = db.relationship("Producto")

    def __repr__(self):
        return f"<StockTienda tienda={self.tienda_id} producto={self.producto_id} cant={self.cantidad}>"

# VENTAS (con snapshots para historia)
class VentaTienda(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # DateTime, con hora incluida
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tienda_id = db.Column(
        db.Integer,
        db.ForeignKey("tienda.id", ondelete="SET NULL"),
        nullable=True
    )
    producto_id = db.Column(
        db.Integer,
        db.ForeignKey("producto.id"),
        nullable=False
    )

    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Integer, nullable=False)  # generalmente precio_concesion
    total = db.Column(db.Integer, nullable=False)

    # Snapshots de tienda
    tienda_nombre_snapshot = db.Column(db.String(120))
    tienda_tipo_snapshot = db.Column(db.String(20))
    tienda_ciudad_snapshot = db.Column(db.String(80))

    # Snapshots de producto
    producto_codigo_snapshot = db.Column(db.String(20))
    producto_nombre_snapshot = db.Column(db.String(120))

    # NUEVO: info de cuotas
    # "contado" o "cuotas"
    tipo_pago = db.Column(db.String(20), nullable=False, default="contado")
    # total de cuotas pactadas (solo si tipo_pago == "cuotas")
    cuotas_totales = db.Column(db.Integer)
    # cuántas cuotas se han pagado efectivamente
    cuotas_pagadas = db.Column(db.Integer, nullable=False, default=0)
    # cuánto se ha pagado en pesos
    monto_pagado = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return (
            f"<VentaTienda id={self.id} "
            f"tienda_id={self.tienda_id} "
            f"prod_id={self.producto_id} "
            f"cant={self.cantidad}>"
        )

    @property
    def monto_reconocido(self):
        """
        Lo que se debe considerar como 'ingreso' real:
        - Si es contado: el total completo.
        - Si es en cuotas: solo lo pagado hasta ahora.
        """
        if self.tipo_pago == "cuotas":
            return self.monto_pagado or 0
        return self.total or 0
# ─────────────────────────────
# USUARIOS Y AUTENTICACIÓN BÁSICA
# ─────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@app.before_request
def cargar_usuario_y_proteger_rutas():
    """
    Carga el usuario logueado en g.user y bloquea el acceso
    a todas las rutas si no hay sesión, excepto login y estáticos.
    """
    # Cargar usuario actual
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = User.query.get(user_id)

    # Endpoints que no requieren login
    endpoints_publicos = {"login", "static"}

    # Si es un endpoint público o raro (None), no bloqueamos
    if request.endpoint in endpoints_publicos or request.endpoint is None:
        return

    # Si no hay usuario logueado, mandamos a /login
    if g.user is None:
        next_url = request.path
        return redirect(url_for("login", next=next_url))

# ─────────────────────────────
# Ajuste de esquema sin migraciones
# ─────────────────────────────
def ensure_schema():
    db.create_all()
    insp = inspect(db.engine)

    # ─────────────────────────────
    # TABLA tienda: columnas nuevas
    # ─────────────────────────────
    if "tienda" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("tienda")]
        alters = []

        if "eliminada" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN eliminada BOOLEAN DEFAULT 0")
        if "eliminada_en" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN eliminada_en DATETIME")
        if "fuente_stock_id" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN fuente_stock_id INTEGER")
        if "tipo_precio" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN tipo_precio VARCHAR(20) DEFAULT 'concesion'")
        if "cobra_iva_extra" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN cobra_iva_extra BOOLEAN DEFAULT 0")
        if "iva_modo" not in cols:
            alters.append("ALTER TABLE tienda ADD COLUMN iva_modo VARCHAR(20) DEFAULT 'incluido'")

        if alters:
            with db.engine.begin() as conn:
                for sql in alters:
                    conn.execute(text(sql))

    # ─────────────────────────────
    # TABLA venta_tienda: columnas nuevas
    # ─────────────────────────────
    if "venta_tienda" in insp.get_table_names():
        vcols = [c["name"] for c in insp.get_columns("venta_tienda")]
        alters_v = []

        # columnas antiguas que tal vez faltan
        if "total" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN total INTEGER DEFAULT 0")
        if "tienda_nombre_snapshot" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN tienda_nombre_snapshot VARCHAR(120)")
        if "tienda_tipo_snapshot" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN tienda_tipo_snapshot VARCHAR(20)")
        if "tienda_ciudad_snapshot" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN tienda_ciudad_snapshot VARCHAR(80)")
        if "producto_codigo_snapshot" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN producto_codigo_snapshot VARCHAR(20)")
        if "producto_nombre_snapshot" not in vcols:
            alters_v.append("ALTER TABLE venta_tienda ADD COLUMN producto_nombre_snapshot VARCHAR(120)")

        # columnas nuevas para cuotas
        if "tipo_pago" not in vcols:
            alters_v.append(
                "ALTER TABLE venta_tienda "
                "ADD COLUMN tipo_pago VARCHAR(20) NOT NULL DEFAULT 'contado'"
            )
        if "cuotas_totales" not in vcols:
            alters_v.append(
                "ALTER TABLE venta_tienda "
                "ADD COLUMN cuotas_totales INTEGER"
            )
        if "cuotas_pagadas" not in vcols:
            alters_v.append(
                "ALTER TABLE venta_tienda "
                "ADD COLUMN cuotas_pagadas INTEGER NOT NULL DEFAULT 0"
            )
        if "monto_pagado" not in vcols:
            alters_v.append(
                "ALTER TABLE venta_tienda "
                "ADD COLUMN monto_pagado INTEGER NOT NULL DEFAULT 0"
            )

        if alters_v:
            with db.engine.begin() as conn:
                for sql in alters_v:
                    conn.execute(text(sql))

        # Normaliza 'total' en registros antiguos (si quedó en 0 o NULL)
        with db.engine.begin() as conn:
            conn.execute(text("""
                UPDATE venta_tienda
                SET total = cantidad * precio_unitario
                WHERE total IS NULL OR total = 0
            """))
# ─────────────────────────────
# AUTENTICACIÓN (login / logout)
# ─────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    # Si ya está logueado, lo mandamos al inicio
    if getattr(g, "user", None):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "1"

        if not username or not password:
            flash("Ingresa usuario y contraseña.")
            return redirect(url_for("login"))

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id

            # Si marcaste "recordarme", la cookie dura 30 días
            session.permanent = remember

            flash("Has iniciado sesión correctamente.")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)

        flash("Usuario o contraseña incorrectos.")
        return redirect(url_for("login"))

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión.")
    return redirect(url_for("login"))

# ─────────────────────────────
# RUTA PRINCIPAL
# ─────────────────────────────
@app.route("/")
def index():
    # Fecha actual
    hoy = date.today()
    año = hoy.year
    mes = hoy.month

    # Inicio y fin de mes (para ventas del mes actual)
    inicio_mes = datetime(año, mes, 1)
    if mes == 12:
        fin_mes_exclusivo = datetime(año + 1, 1, 1)
    else:
        fin_mes_exclusivo = datetime(año, mes + 1, 1)

    # -----------------------------
    # STOCK TOTAL
    # -----------------------------
    stock_total = db.session.query(func.sum(StockTienda.cantidad)).scalar() or 0

    # -----------------------------
    # VALOR INVENTARIO (CONCESIÓN Y POR MENOR)
    # -----------------------------
    valor_inv_concesion = 0
    valor_inv_menor = 0

    filas_stock = (
        db.session.query(
            StockTienda.cantidad,
            Producto.precio_concesion,
            Producto.precio_menor
        )
        .join(Producto, StockTienda.producto_id == Producto.id)
        .all()
    )

    for cant, precio_conc, precio_menor in filas_stock:
        cant = cant or 0
        precio_conc = precio_conc or 0
        precio_menor = precio_menor or 0
        valor_inv_concesion += cant * precio_conc
        valor_inv_menor += cant * precio_menor

    # -----------------------------
    # VENTAS DEL MES (monto total)
    # -----------------------------
    ventas_mes = (
        db.session.query(func.sum(VentaTienda.total))
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo,
        )
        .scalar()
        or 0
    )

    # -----------------------------
    # VENTAS DEL MES (unidades) -> para rotación
    # -----------------------------
    ventas_unidades_mes = (
        db.session.query(func.sum(VentaTienda.cantidad))
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo,
        )
        .scalar()
        or 0
    )

    if stock_total > 0:
        rotacion_porcentaje = round(ventas_unidades_mes * 100.0 / stock_total, 1)
    else:
        rotacion_porcentaje = 0.0

    # -----------------------------
    # TIENDAS ACTIVAS
    # -----------------------------
    tiendas_activas = (
        Tienda.query.filter(
            Tienda.activa == True,
            Tienda.eliminada == False
        ).count()
    )

    # -----------------------------
    # CUCHILLOS MÁS VENDIDOS DEL MES
    # -----------------------------
    best_nombre = None
    best_codigo = None
    best_img = None
    best_cantidad_mes = 0
    top3 = []

    filas_best = (
        db.session.query(
            VentaTienda.producto_id,
            func.sum(VentaTienda.cantidad).label("cant")
        )
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo,
        )
        .group_by(VentaTienda.producto_id)
        .order_by(func.sum(VentaTienda.cantidad).desc())
        .all()
    )

    if filas_best:
        # Primero: el cuchillo Nº1 del mes
        best_product_id = filas_best[0].producto_id
        best_cantidad_mes = int(filas_best[0].cant or 0)

        prod_best = Producto.query.get(best_product_id)
        if prod_best:
            best_codigo = prod_best.codigo
            best_nombre = prod_best.nombre or prod_best.codigo
            best_img = prod_best.imagen  # ruta relativa dentro de /static

        # Top 3 para la card de "Top 3 cuchillos del mes"
        for fila in filas_best[:3]:
            prod = Producto.query.get(fila.producto_id)
            if not prod:
                continue
            nombre_top = prod.nombre or prod.codigo
            cant_top = int(fila.cant or 0)
            top3.append({
                "codigo": prod.codigo,
                "nombre": nombre_top,
                "cantidad": cant_top
            })

    # -----------------------------
    # RESUMEN PARA EL INDEX
    # -----------------------------
    resumen = {
        "stock_total": stock_total,
        "valor_inventario_concesion": valor_inv_concesion,
        "valor_inventario_menor": valor_inv_menor,
        "ventas_mes": ventas_mes,
        "tiendas_activas": tiendas_activas,
        "best_nombre": best_nombre,
        "best_codigo": best_codigo,
        "best_img": best_img,
        "best_cantidad_mes": best_cantidad_mes,
        "rotacion_porcentaje": rotacion_porcentaje,
        "top3": top3,
    }

    return render_template("index.html", resumen=resumen)

# ─────────────────────────────
# TIENDAS
# ─────────────────────────────
@app.route("/tiendas")
def tiendas_index():
    # Traemos todas las tiendas NO eliminadas
    tiendas = (
        Tienda.query
        .filter(Tienda.eliminada == False)
        .order_by(Tienda.nombre)
        .all()
    )

    # Listas separadas
    bodega_central = []
    bodegas_otros = []
    solo_tiendas = []
    vendedores = []

    for t in tiendas:
        tipo = (t.tipo or "").lower()
        nombre = (t.nombre or "").lower()

        if tipo == "bodega" and "central" in nombre:
            bodega_central.append(t)
        elif tipo == "bodega":
            bodegas_otros.append(t)
        elif tipo == "tienda":
            solo_tiendas.append(t)
        elif tipo == "vendedor":
            vendedores.append(t)
        else:
            # Si por alguna razón tiene otro tipo raro, lo dejamos con bodegas_otros
            bodegas_otros.append(t)

    # -----------------------------
    # Ventas reales del MES actual por tienda
    # (usa monto_reconocido: total si contado, monto_pagado si cuotas)
    # -----------------------------
    hoy = date.today()
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    if hoy.month == 12:
        fin_mes_exclusivo = datetime(hoy.year + 1, 1, 1)
    else:
        fin_mes_exclusivo = datetime(hoy.year, hoy.month + 1, 1)

    ventas_mes_rows = (
        VentaTienda.query
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo
        )
        .all()
    )

    ventas_mes_por_tienda = {}
    for v in ventas_mes_rows:
        if not v.tienda_id:
            continue
        actual = ventas_mes_por_tienda.get(v.tienda_id, 0)
        ventas_mes_por_tienda[v.tienda_id] = actual + (v.monto_reconocido or 0)

    return render_template(
        "tiendas/tiendas.html",
        tiendas=tiendas,             # lista completa
        bodega_central=bodega_central,
        bodegas_otros=bodegas_otros,
        solo_tiendas=solo_tiendas,
        vendedores=vendedores,
        ventas_mes_por_tienda=ventas_mes_por_tienda,  # NUEVO
    )

    # ------------------------------------
    # Ventas del mes actual por tienda
    # ------------------------------------
    ahora = datetime.utcnow()
    inicio_mes = datetime(ahora.year, ahora.month, 1)
    if ahora.month == 12:
        fin_mes_exclusivo = datetime(ahora.year + 1, 1, 1)
    else:
        fin_mes_exclusivo = datetime(ahora.year, ahora.month + 1, 1)

    ventas_mes_por_tienda = {}

    ventas_mes = (
        VentaTienda.query
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo
        )
        .all()
    )

    for v in ventas_mes:
        if not v.tienda_id:
            continue
        ventas_mes_por_tienda.setdefault(v.tienda_id, 0)
        # usamos el monto "real" (total si contado, monto_pagado si cuotas)
        ventas_mes_por_tienda[v.tienda_id] += v.monto_reconocido

    # ------------------------------------
    # Listas separadas para mostrar
    # ------------------------------------
    bodega_central = []
    bodegas_otros = []
    solo_tiendas = []
    vendedores = []

    for t in tiendas:
        tipo = (t.tipo or "").lower()
        nombre = (t.nombre or "").lower()

        if tipo == "bodega" and "central" in nombre:
            bodega_central.append(t)
        elif tipo == "bodega":
            bodegas_otros.append(t)
        elif tipo == "tienda":
            solo_tiendas.append(t)
        elif tipo == "vendedor":
            vendedores.append(t)
        else:
            # Si por alguna razón tiene otro tipo raro, lo dejamos con bodegas_otros
            bodegas_otros.append(t)

    return render_template(
        "tiendas/tiendas.html",
        tiendas=tiendas,               # lista completa (por si la usas en otro lado)
        bodega_central=bodega_central,
        bodegas_otros=bodegas_otros,
        solo_tiendas=solo_tiendas,
        vendedores=vendedores,
        ventas_mes_por_tienda=ventas_mes_por_tienda,  # NUEVO
    )

@app.route("/tiendas/nueva", methods=["GET", "POST"])
def tiendas_nueva():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        tipo = request.form["tipo"]
        ciudad = request.form["ciudad"].strip()

        # id de la bodega/tienda fuente (puede venir vacío)
        fuente_stock_id_str = request.form.get("fuente_stock_id", "")
        fuente_stock_id = int(fuente_stock_id_str) if fuente_stock_id_str else None

        tipo_precio = request.form.get("tipo_precio", "concesion")
        iva_modo = request.form.get("iva_modo", "incluido")

        if not nombre:
            flash("El nombre de la tienda es obligatorio.")
            return redirect(url_for("tiendas_nueva"))

        existente = Tienda.query.filter_by(nombre=nombre).first()
        if existente:
            flash("Ya existe una tienda/bodega con ese nombre.")
            return redirect(url_for("tiendas_nueva"))

        nueva_tienda = Tienda(
            nombre=nombre,
            tipo=tipo,
            ciudad=ciudad,
            activa=True,
            fuente_stock_id=fuente_stock_id,
            tipo_precio=tipo_precio,
            iva_modo=iva_modo
        )
        # por compatibilidad con el campo viejo:
        nueva_tienda.cobra_iva_extra = (iva_modo == "extra")

        db.session.add(nueva_tienda)
        db.session.commit()

        flash("Tienda creada correctamente.")
        return redirect(url_for("tiendas_index"))

    # GET: listar posibles bodegas/tiendas fuente (generalmente solo bodegas)
    bodegas = (
        Tienda.query
        .filter(Tienda.tipo == "Bodega", Tienda.eliminada == False)
        .order_by(Tienda.nombre)
        .all()
    )

    return render_template("tiendas/tienda_nueva.html", bodegas=bodegas)

@app.route("/tiendas/editar/<int:tienda_id>", methods=["GET", "POST"])
def tiendas_editar(tienda_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        tipo = request.form["tipo"]
        ciudad = request.form["ciudad"].strip()
        activa = request.form.get("activa") == "1"

        fuente_stock_id_str = request.form.get("fuente_stock_id", "")
        fuente_stock_id = int(fuente_stock_id_str) if fuente_stock_id_str else None

        tipo_precio = request.form.get("tipo_precio", "concesion")
        iva_modo = request.form.get("iva_modo", tienda.iva_modo or "incluido")

        if not nombre:
            flash("El nombre de la tienda es obligatorio.")
            return redirect(url_for("tiendas_editar", tienda_id=tienda.id))

        tienda.nombre = nombre
        tienda.tipo = tipo
        tienda.ciudad = ciudad
        tienda.activa = activa
        tienda.fuente_stock_id = fuente_stock_id
        tienda.tipo_precio = tipo_precio
        tienda.iva_modo = iva_modo
        tienda.cobra_iva_extra = (iva_modo == "extra")

        db.session.commit()
        flash("Tienda actualizada correctamente.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    bodegas = (
        Tienda.query
        .filter(Tienda.tipo == "Bodega", Tienda.eliminada == False, Tienda.id != tienda.id)
        .order_by(Tienda.nombre)
        .all()
    )

    return render_template("tiendas/tienda_editar.html", tienda=tienda, bodegas=bodegas)

@app.route("/tiendas/eliminar/<int:tienda_id>", methods=["POST"])
def tiendas_eliminar(tienda_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

    stock_count = StockTienda.query.filter_by(tienda_id=tienda.id).count()
    ventas_count = VentaTienda.query.filter_by(tienda_id=tienda.id).count()

    # Con ventas -> archivar (soft delete)
    if ventas_count > 0:
        tienda.eliminada = True
        tienda.eliminada_en = datetime.utcnow()
        tienda.activa = False
        db.session.commit()
        if stock_count > 0:
            flash("Tienda archivada (tenía ventas). Aún tiene stock: muévelo o elimínalo si quieres ocultarla por completo.")
        else:
            flash("Tienda archivada correctamente. Las ventas históricas se mantienen para reportes.")
        return redirect(url_for("tiendas_index"))

    # Sin ventas: solo borrar si no tiene stock
    if stock_count > 0:
        flash("No se puede borrar: aún tiene stock. Mueve o elimina el stock primero.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    db.session.delete(tienda)
    db.session.commit()
    flash("Tienda eliminada definitivamente.")
    return redirect(url_for("tiendas_index"))


            
@app.route("/tiendas/<int:tienda_id>", methods=["GET", "POST"])
def tiendas_detalle(tienda_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

        # ------------------------------
    # POST: asignar / actualizar stock
    # ------------------------------
    if request.method == "POST":
        producto_id = int(request.form["producto_id"])
        cantidad_form = int(request.form["cantidad"])

        # Ahora SIEMPRE interpretamos la cantidad como "cantidad a agregar"
        if cantidad_form <= 0:
            flash("La cantidad debe ser mayor que cero.")
            return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

        # Stock actual en esta tienda
        stock = StockTienda.query.filter_by(
            tienda_id=tienda.id,
            producto_id=producto_id
        ).first()
        cantidad_actual = stock.cantidad if stock else 0

        # Caso 1: tienda/bodega SIN fuente de stock → se suma al inventario actual
        if not tienda.fuente_stock_id:
            cantidad_nueva = cantidad_actual + cantidad_form

            if not stock:
                stock = StockTienda(
                    tienda_id=tienda.id,
                    producto_id=producto_id,
                    cantidad=cantidad_nueva
                )
                db.session.add(stock)
            else:
                stock.cantidad = cantidad_nueva

            db.session.commit()
            flash(
                f"Se agregaron {cantidad_form} unidades al inventario de "
                f"{tienda.nombre}. Ahora hay {cantidad_nueva} unidades."
            )
            return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

        # Caso 2: tienda/vendedor con fuente_stock_id → la cantidad es "cantidad a AGREGAR desde la bodega"
        bodega_origen = Tienda.query.get(tienda.fuente_stock_id)
        if not bodega_origen:
            flash("La bodega de origen configurada no existe. Revisa la configuración de la tienda.")
            return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

        # Stock en la bodega de origen para este producto
        stock_origen = StockTienda.query.filter_by(
            tienda_id=bodega_origen.id,
            producto_id=producto_id
        ).first()

        if not stock_origen or (stock_origen.cantidad or 0) < cantidad_form:
            flash(
                f"No hay suficiente stock en la bodega de origen "
                f"({bodega_origen.nombre}) para enviar {cantidad_form} unidades."
            )
            return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

        # Descontamos de la bodega origen
        stock_origen.cantidad -= cantidad_form

        # Sumamos en la tienda/vendedor
        cantidad_nueva = cantidad_actual + cantidad_form
        if not stock:
            stock = StockTienda(
                tienda_id=tienda.id,
                producto_id=producto_id,
                cantidad=cantidad_nueva
            )
            db.session.add(stock)
        else:
            stock.cantidad = cantidad_nueva

        db.session.commit()
        flash(
            f"Se agregaron {cantidad_form} unidades desde {bodega_origen.nombre} "
            f"a {tienda.nombre}. Ahora hay {cantidad_nueva} unidades."
        )
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))
    # ------------------------------
    # GET: Inventario y modelos agotados
    # ------------------------------

    # 1) Todos los stocks de la tienda (incluye ceros)
    stocks_all = (
        StockTienda.query
        .filter_by(tienda_id=tienda.id)
        .join(Producto)
        .order_by(func.length(Producto.codigo), Producto.codigo)
        .all()
    )

    # 2) Inventario actual: solo líneas con stock > 0
    stocks = [s for s in stocks_all if (s.cantidad or 0) > 0]

    total_modelos = len(stocks)
    total_unidades = sum(s.cantidad for s in stocks) if stocks else 0

    # Valor total del stock usando el tipo de precio de la tienda
    total_valor_stock = 0
    for s in stocks:
        if tienda.tipo_precio == "menor":
            precio_unitario = s.producto.precio_menor
        elif tienda.tipo_precio == "mercadolibre":
            precio_unitario = s.producto.precio_mercadolibre
        else:
            # por defecto, concesión
            precio_unitario = s.producto.precio_concesion

        total_valor_stock += s.cantidad * precio_unitario

    # 3) Ventas acumuladas por producto en esta tienda (histórico)
    ventas_rows = (
        db.session.query(
            VentaTienda.producto_id,
            func.sum(VentaTienda.cantidad).label("vendidas")
        )
        .filter(VentaTienda.tienda_id == tienda.id)
        .group_by(VentaTienda.producto_id)
        .all()
    )

    ventas_dict = {
        row.producto_id: (row.vendidas or 0)
        for row in ventas_rows
    }

    # 4) Modelos vendidos sin stock (agotados)
    agotados = []
    for s in stocks_all:
        cant_stock = s.cantidad or 0
        vendidas = ventas_dict.get(s.producto_id, 0)

        # condición: stock <= 0 y tiene ventas
        if cant_stock <= 0 and vendidas > 0:
            agotados.append({
                "producto": s.producto,
                "vendidas": vendidas
            })

    # ------------------------------
    # Ventas del mes actual (usando DateTime y monto_reconocido)
    # ------------------------------
    ahora = datetime.utcnow()
    inicio_mes = datetime(ahora.year, ahora.month, 1)
    if ahora.month == 12:
        fin_mes_exclusivo = datetime(ahora.year + 1, 1, 1)
    else:
        fin_mes_exclusivo = datetime(ahora.year, ahora.month + 1, 1)

    ventas_mes = (
        VentaTienda.query
        .filter(
            VentaTienda.tienda_id == tienda.id,
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo
        )
        .all()
    )

    # Lo que de verdad se debe considerar como “ingreso” este mes:
    suma_db = sum(v.monto_reconocido for v in ventas_mes)

    # Interpretamos según iva_modo
    modo_iva = tienda.iva_modo or "incluido"

    if modo_iva == "no":
        # No se aplica IVA
        total_vendidos_monto = suma_db   # lo que recibes
        total_iva = 0
        total_con_iva = suma_db
    elif modo_iva == "extra":
        # Lo que tienes en la BD es NETO, sobre ese neto calculas IVA 19%
        total_vendidos_monto = suma_db
        total_iva = int(round(total_vendidos_monto * 0.19)) if total_vendidos_monto else 0
        total_con_iva = total_vendidos_monto + total_iva
    else:
        # "incluido": asumimos que lo guardado incluye IVA.
        # Calculamos base neta e IVA interno.
        bruto = suma_db
        if bruto:
            base_neta = int(round(bruto / 1.19))
            iva_interno = bruto - base_neta
        else:
            base_neta = 0
            iva_interno = 0

        total_vendidos_monto = base_neta   # "neto vendido"
        total_iva = iva_interno
        total_con_iva = bruto              # lo que efectivamente se cobró

    total_vendidos_unidades = sum(v.cantidad for v in ventas_mes)

    # Agrupamos ventas por producto (monto también según monto_reconocido)
    ventas_por_producto = {}
    for v in ventas_mes:
        data = ventas_por_producto.setdefault(
            v.producto_id,
            {"cantidad": 0, "monto": 0}
        )
        data["cantidad"] += v.cantidad
        data["monto"] += v.monto_reconocido

    # ------------------------------
    # Ventas en cuotas activas (pendientes de pago)
    # ------------------------------
    cuotas_activas = []
    cuotas_raw = (
        db.session.query(VentaTienda, Producto)
        .join(Producto, VentaTienda.producto_id == Producto.id)
        .filter(
            VentaTienda.tienda_id == tienda.id,
            VentaTienda.tipo_pago == "cuotas"
        )
        .order_by(VentaTienda.fecha.desc(), VentaTienda.id.desc())
        .all()
    )

    for venta, prod in cuotas_raw:
        tot_cuotas = venta.cuotas_totales or 0
        pagadas = venta.cuotas_pagadas or 0
        pagado = venta.monto_pagado or 0
        total = venta.total or 0

        # Si ya está completamente pagada, no la mostramos
        if tot_cuotas and pagadas >= tot_cuotas:
            continue

        if tot_cuotas > 0:
            valor_cuota = total // tot_cuotas
        else:
            valor_cuota = 0

        monto_pendiente = max(total - pagado, 0)
        cuotas_restantes = tot_cuotas - pagadas if tot_cuotas else 0

        cuotas_activas.append({
            "venta": venta,
            "producto": prod,
            "valor_cuota": valor_cuota,
            "monto_pendiente": monto_pendiente,
            "cuotas_restantes": cuotas_restantes,
        })

    return render_template(
        "tiendas/tienda_detalle.html",
        tienda=tienda,
        stocks=stocks,
        productos=Producto.query.order_by(func.length(Producto.codigo), Producto.codigo).all(),
        total_modelos=total_modelos,
        total_unidades=total_unidades,
        total_valor_stock=total_valor_stock,
        total_vendidos_unidades=total_vendidos_unidades,
        total_vendidos_monto=total_vendidos_monto,
        ventas_por_producto=ventas_por_producto,
        inicio_mes=inicio_mes,
        total_iva=total_iva,
        total_con_iva=total_con_iva,
        agotados=agotados,
        cuotas_activas=cuotas_activas,
    )

@app.route("/tiendas/<int:tienda_id>/ventas")
def tiendas_listar_ventas(tienda_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

    ventas = (
        VentaTienda.query
        .filter_by(tienda_id=tienda.id)
        .order_by(VentaTienda.fecha.desc(), VentaTienda.id.desc())
        .all()
    )

    return render_template(
        "tiendas/tienda_ventas.html",
        tienda=tienda,
        ventas=ventas
    )

@app.route("/tiendas/<int:tienda_id>/ventas/<int:venta_id>/eliminar", methods=["POST"])
def tiendas_eliminar_venta(tienda_id, venta_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

    venta = VentaTienda.query.get(venta_id)
    if not venta or venta.tienda_id != tienda.id:
        flash("La venta no existe o no pertenece a esta tienda.")
        return redirect(url_for("tiendas_listar_ventas", tienda_id=tienda.id))

    # Reincorporar stock en la misma tienda donde se registró la venta
    stock = StockTienda.query.filter_by(
        tienda_id=tienda.id,
        producto_id=venta.producto_id
    ).first()

    if not stock:
        stock = StockTienda(
            tienda_id=tienda.id,
            producto_id=venta.producto_id,
            cantidad=0
        )
        db.session.add(stock)

    stock.cantidad += venta.cantidad

    # Eliminar la venta
    db.session.delete(venta)
    db.session.commit()

    flash("Venta eliminada y stock restaurado.")
    return redirect(url_for("tiendas_listar_ventas", tienda_id=tienda.id))

@app.route("/tiendas/<int:tienda_id>/venta/<int:producto_id>", methods=["GET", "POST"])
def tiendas_registrar_venta(tienda_id, producto_id):
    tienda = Tienda.query.get(tienda_id)
    producto = Producto.query.get(producto_id)

    if not tienda or not producto:
        flash("La tienda o el producto no existen.")
        return redirect(url_for("tiendas_index"))

    # Verificar que el producto exista en el stock de esta tienda
    stock = StockTienda.query.filter_by(
        tienda_id=tienda.id,
        producto_id=producto.id
    ).first()

    if not stock:
        flash("Este producto aún no está en el inventario de esta tienda.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    if request.method == "POST":
        cantidad = request.form.get("cantidad", type=int)

        if not cantidad or cantidad <= 0:
            flash("La cantidad debe ser mayor que cero.")
            return redirect(url_for(
                "tiendas_registrar_venta",
                tienda_id=tienda.id,
                producto_id=producto.id
            ))

        if cantidad > stock.cantidad:
            flash("No hay suficiente stock para registrar esta venta.")
            return redirect(url_for(
                "tiendas_registrar_venta",
                tienda_id=tienda.id,
                producto_id=producto.id
            ))

        # Elegimos el precio según la configuración de la tienda
        if tienda.tipo_precio == "menor":
            precio_unitario = producto.precio_menor or 0
        elif tienda.tipo_precio == "mercadolibre":
            precio_unitario = producto.precio_mercadolibre or 0
        else:
            precio_unitario = producto.precio_concesion or 0

        total = cantidad * precio_unitario

        # Forma de pago que viene del formulario
        tipo_pago = request.form.get("tipo_pago", "contado")
        cuotas_totales = request.form.get("cuotas_totales", type=int)

        # Normalizamos: si no marcó cuotas o puso menos de 2, lo tratamos como contado
        if tipo_pago != "cuotas" or not cuotas_totales or cuotas_totales < 2:
            tipo_pago = "contado"
            cuotas_totales = None
            cuotas_pagadas = 0
            monto_pagado = total  # en contado, se paga todo al tiro
        else:
            cuotas_pagadas = 0
            monto_pagado = 0  # en cuotas, al inicio no se ha pagado nada

        venta = VentaTienda(
            fecha=datetime.utcnow(),
            tienda_id=tienda.id,
            producto_id=producto.id,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            total=total,
            tienda_nombre_snapshot=tienda.nombre,
            tienda_tipo_snapshot=tienda.tipo,
            tienda_ciudad_snapshot=tienda.ciudad,
            producto_codigo_snapshot=producto.codigo,
            producto_nombre_snapshot=producto.nombre,
            tipo_pago=tipo_pago,
            cuotas_totales=cuotas_totales,
            cuotas_pagadas=cuotas_pagadas,
            monto_pagado=monto_pagado,
        )
        db.session.add(venta)

        # Descontar del stock
        stock.cantidad -= cantidad
        db.session.commit()

        if tipo_pago == "contado":
            flash("Venta registrada correctamente (pago contado).")
        else:
            flash(
                f"Venta en {cuotas_totales} cuotas registrada. "
                "Recuerda registrar los pagos a medida que te vayan cancelando."
            )

        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    # GET: mostrar formulario
    return render_template(
        "tiendas/tienda_venta.html",
        tienda=tienda,
        producto=producto,
        stock=stock
    )
@app.route("/tiendas/<int:tienda_id>/venta/<int:venta_id>/pagar_cuota", methods=["POST"])
def tiendas_pagar_cuota(tienda_id, venta_id):
    tienda = Tienda.query.get(tienda_id)
    if not tienda:
        flash("La tienda no existe.")
        return redirect(url_for("tiendas_index"))

    venta = VentaTienda.query.get(venta_id)
    if not venta or venta.tienda_id != tienda.id:
        flash("La venta no existe o no pertenece a esta tienda.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    if venta.tipo_pago != "cuotas":
        flash("Esta venta no está configurada como pago en cuotas.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    tot_cuotas = venta.cuotas_totales or 0
    if tot_cuotas <= 0:
        flash("Esta venta no tiene número de cuotas definido.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    if venta.cuotas_pagadas >= tot_cuotas:
        flash("Esta venta ya está totalmente pagada.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    total = venta.total or 0
    # Valor de cada cuota (entero)
    valor_cuota = total // tot_cuotas
    if valor_cuota <= 0:
        valor_cuota = total

    venta.cuotas_pagadas += 1
    venta.monto_pagado += valor_cuota

    # No pasarnos del total
    if venta.monto_pagado >= total:
        venta.monto_pagado = total
        venta.cuotas_pagadas = tot_cuotas

    db.session.commit()

    if venta.cuotas_pagadas >= tot_cuotas:
        flash("Última cuota registrada. La venta quedó completamente pagada.")
    else:
        flash(f"Cuota registrada. Van {venta.cuotas_pagadas} de {tot_cuotas}.")

    return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))
@app.route("/tiendas/<int:tienda_id>/stock/sacar/<int:producto_id>", methods=["GET", "POST"])
def tiendas_sacar_stock(tienda_id, producto_id):
    tienda = Tienda.query.get(tienda_id)
    producto = Producto.query.get(producto_id)

    if not tienda or not producto:
        flash("La tienda o el producto no existen.")
        return redirect(url_for("tiendas_index"))

    stock = StockTienda.query.filter_by(
        tienda_id=tienda.id,
        producto_id=producto.id
    ).first()

    if not stock or stock.cantidad <= 0:
        flash("No hay stock disponible de este producto en esta tienda.")
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    if request.method == "POST":
        cantidad = int(request.form["cantidad"])

        if cantidad <= 0:
            flash("La cantidad debe ser mayor que cero.")
            return redirect(url_for("tiendas_sacar_stock",
                                    tienda_id=tienda.id,
                                    producto_id=producto.id))

        if cantidad > stock.cantidad:
            flash("No puedes retirar más unidades de las que hay en stock.")
            return redirect(url_for("tiendas_sacar_stock",
                                    tienda_id=tienda.id,
                                    producto_id=producto.id))

        # Restar de esta tienda
        stock.cantidad -= cantidad

        # Devolver a la fuente si existe
        if tienda.fuente_stock_id:
            fuente = Tienda.query.get(tienda.fuente_stock_id)
            if fuente:
                stock_fuente = StockTienda.query.filter_by(
                    tienda_id=fuente.id,
                    producto_id=producto.id
                ).first()
                if not stock_fuente:
                    stock_fuente = StockTienda(
                        tienda_id=fuente.id,
                        producto_id=producto.id,
                        cantidad=0
                    )
                    db.session.add(stock_fuente)

                stock_fuente.cantidad += cantidad
                msg = (
                    f"Stock retirado de {tienda.nombre} y devuelto a {fuente.nombre} "
                    f"({cantidad} unidades)."
                )
            else:
                msg = (
                    f"Stock retirado de {tienda.nombre} "
                    f"({cantidad} unidades). La fuente configurada no existe."
                )
        else:
            # Bodega central: el stock se descuenta y no se devuelve a nadie
            msg = (
                f"Stock retirado definitivamente de {tienda.nombre} "
                f"({cantidad} unidades)."
            )

        db.session.commit()
        flash(msg)
        return redirect(url_for("tiendas_detalle", tienda_id=tienda.id))

    # GET: mostrar formulario
    return render_template(
        "tiendas/tienda_sacar_stock.html",
        tienda=tienda,
        producto=producto,
        stock=stock
    )

# ─────────────────────────────
# GASTOS
# ─────────────────────────────
@app.route("/gastos")
def gastos_index():
    y = request.args.get("year", type=int)
    m = request.args.get("month", type=int)
    cat = request.args.get("cat", type=str, default="")

    hoy = date.today()
    year = y or hoy.year
    month = m or hoy.month

    inicio_mes = date(year, month, 1)
    fin_mes_exclusivo = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)

    q = Gasto.query.filter(Gasto.fecha >= inicio_mes, Gasto.fecha < fin_mes_exclusivo)
    if cat:
        q = q.filter(Gasto.categoria == cat)

    gastos = q.order_by(Gasto.fecha.desc(), Gasto.id.desc()).all()
    total_mes = sum(g.monto for g in gastos)

    q_mes = Gasto.query.filter(Gasto.fecha >= inicio_mes, Gasto.fecha < fin_mes_exclusivo)
    gastos_mes = q_mes.all()
    por_categoria = {}
    for g in gastos_mes:
        por_categoria[g.categoria] = por_categoria.get(g.categoria, 0) + g.monto

    años = list(range(hoy.year - 3, hoy.year + 1))
    meses = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre")
    ]

    return render_template(
        "gastos/gastos_index.html",
        gastos=gastos,
        total_mes=total_mes,
        por_categoria=por_categoria,
        categorias=CATEGORIAS_GASTO,
        mes_actual=month,
        año_actual=year,
        meses=meses,
        años=años,
        cat_sel=cat,
        inicio_mes=inicio_mes
    )

@app.route("/gastos/nuevo", methods=["GET", "POST"])
def gastos_nuevo():
    if request.method == "POST":
        fecha_str = request.form.get("fecha", "").strip()
        categoria = request.form.get("categoria")
        detalle = request.form.get("detalle", "").strip()
        monto_str = request.form.get("monto", "0")

        try:
            f = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            f = date.today()

        monto = clean_price(monto_str)

        if categoria not in CATEGORIAS_GASTO:
            flash("Selecciona una categoría válida.")
            return redirect(url_for("gastos_nuevo"))

        if monto <= 0:
            flash("El monto debe ser mayor a 0.")
            return redirect(url_for("gastos_nuevo"))

        g = Gasto(fecha=f, categoria=categoria, detalle=detalle, monto=monto)
        db.session.add(g)
        db.session.commit()
        flash("Gasto registrado correctamente.")
        return redirect(url_for("gastos_index", year=f.year, month=f.month))

    hoy = date.today()
    return render_template("gastos/gastos_nuevo.html", categorias=CATEGORIAS_GASTO, hoy=hoy)

@app.route("/gastos/editar/<int:gasto_id>", methods=["GET", "POST"])
def gastos_editar(gasto_id):
    g = Gasto.query.get(gasto_id)
    if not g:
        flash("El gasto no existe.")
        return redirect(url_for("gastos_index"))

    if request.method == "POST":
        fecha_str = request.form.get("fecha", "").strip()
        categoria = request.form.get("categoria")
        detalle = request.form.get("detalle", "").strip()
        monto_str = request.form.get("monto", "0")

        try:
            f = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            f = g.fecha or date.today()

        monto = clean_price(monto_str)

        if categoria not in CATEGORIAS_GASTO:
            flash("Selecciona una categoría válida.")
            return redirect(url_for("gastos_editar", gasto_id=g.id))

        if monto <= 0:
            flash("El monto debe ser mayor a 0.")
            return redirect(url_for("gastos_editar", gasto_id=g.id))

        g.fecha = f
        g.categoria = categoria
        g.detalle = detalle
        g.monto = monto

        db.session.commit()
        flash("Gasto actualizado correctamente.")
        return redirect(url_for("gastos_index", year=f.year, month=f.month))

    return render_template("gastos/gastos_editar.html", gasto=g, categorias=CATEGORIAS_GASTO)

@app.route("/gastos/eliminar/<int:gasto_id>", methods=["POST"])
def gastos_eliminar(gasto_id):
    g = Gasto.query.get(gasto_id)
    if not g:
        flash("El gasto no existe.")
        return redirect(url_for("gastos_index"))

    year = g.fecha.year if g.fecha else date.today().year
    month = g.fecha.month if g.fecha else date.today().month

    db.session.delete(g)
    db.session.commit()
    flash("Gasto eliminado correctamente.")
    return redirect(url_for("gastos_index", year=year, month=month))

# ─────────────────────────────
# CATÁLOGO
# ─────────────────────────────
@app.route("/catalogo")
def catalogo_index():
    q = request.args.get("q", "").strip()
    cat1 = request.args.get("cat1", "").strip()
    cat2 = request.args.get("cat2", "").strip()
    acero_filtro = request.args.get("acero", "").strip()

    query = Producto.query

    if q:
        if q.isdigit():
            query = query.filter(Producto.codigo == f"N{q}")
        else:
            like = f"%{q}%"
            query = query.filter((Producto.codigo.ilike(like)) | (Producto.nombre.ilike(like)))

    if cat1:
        query = query.filter(Producto.categoria_principal == cat1)
    if cat2:
        query = query.filter(Producto.categoria_secundaria == cat2)
    if acero_filtro:
        query = query.filter(Producto.acero == acero_filtro)

    cat1_opciones = [c[0] for c in db.session.query(Producto.categoria_principal).distinct().order_by(Producto.categoria_principal).all() if c[0]]
    cat2_opciones = [c[0] for c in db.session.query(Producto.categoria_secundaria).distinct().order_by(Producto.categoria_secundaria).all() if c[0]]
    acero_opciones = [c[0] for c in db.session.query(Producto.acero).distinct().order_by(Producto.acero).all() if c[0]]

    productos = query.order_by(func.length(Producto.codigo), Producto.codigo).all()

    return render_template(
        "catalogo/catalogo.html",
        productos=productos,
        q=q, cat1=cat1, cat2=cat2, acero_filtro=acero_filtro,
        cat1_opciones=cat1_opciones, cat2_opciones=cat2_opciones, acero_opciones=acero_opciones,
    )

@app.route("/catalogo/nuevo", methods=["GET", "POST"])
def catalogo_nuevo():
    if request.method == "POST":
        codigo_num = request.form["codigo_num"].strip()
        codigo = f"N{codigo_num}"

        existente = Producto.query.filter_by(codigo=codigo).first()
        if existente:
            flash(f"Ya existe un producto con el código {codigo}. Elige otro número.")
            return redirect(url_for("catalogo_nuevo"))

        nombre = request.form["nombre"].strip()
        categoria_principal = request.form["categoria_principal"]
        categoria_secundaria = request.form["categoria_secundaria"]
        acero = request.form["acero"]
        mango = request.form["mango"]

        largo_hoja = request.form.get("largo_hoja_cm", "").strip()
        largo_mango = request.form.get("largo_mango_cm", "").strip()
        largo_hoja_cm = float(largo_hoja) if largo_hoja else None
        largo_mango_cm = float(largo_mango) if largo_mango else None

        precio_menor = clean_price(request.form["precio_menor"])
        precio_concesion = clean_price(request.form["precio_concesion"])
        precio_mercadolibre = clean_price(request.form["precio_mercadolibre"])

        imagen_file = request.files.get("imagen_file")
        imagen_ruta_relativa = None
        if imagen_file and imagen_file.filename:
            if allowed_file(imagen_file.filename):
                filename = secure_filename(imagen_file.filename)
                ext = filename.rsplit(".", 1)[1].lower()
                filename = f"{codigo.lower()}.{ext}"
                os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                imagen_file.save(filepath)
                imagen_ruta_relativa = f"img/cuchillos/{filename}"
            else:
                flash("Extensión de imagen no permitida (usa: png, jpg, jpeg, gif).")
                return redirect(url_for("catalogo_nuevo"))

        nuevo_producto = Producto(
            codigo=codigo, nombre=nombre,
            categoria_principal=categoria_principal, categoria_secundaria=categoria_secundaria,
            acero=acero, mango=mango,
            largo_hoja_cm=largo_hoja_cm, largo_mango_cm=largo_mango_cm,
            precio_menor=precio_menor, precio_concesion=precio_concesion, precio_mercadolibre=precio_mercadolibre,
            imagen=imagen_ruta_relativa
        )
        db.session.add(nuevo_producto)
        db.session.commit()

        return redirect(url_for("catalogo_index"))

    return render_template("catalogo/nuevo.html")

@app.route("/catalogo/ver/<codigo>")
def catalogo_ver(codigo):
    producto = Producto.query.filter_by(codigo=codigo).first()
    if not producto:
        return redirect(url_for("catalogo_index"))
    return render_template("catalogo/ver.html", producto=producto)

@app.route("/catalogo/editar/<codigo>", methods=["GET", "POST"])
def catalogo_editar(codigo):
    producto = Producto.query.filter_by(codigo=codigo).first()
    if not producto:
        flash(f"El producto con código {codigo} no existe.")
        return redirect(url_for("catalogo_index"))

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        categoria_principal = request.form["categoria_principal"]
        categoria_secundaria = request.form["categoria_secundaria"]
        acero = request.form["acero"]
        mango = request.form["mango"]

        largo_hoja = request.form.get("largo_hoja_cm", "").strip()
        largo_mango = request.form.get("largo_mango_cm", "").strip()
        largo_hoja_cm = float(largo_hoja) if largo_hoja else None
        largo_mango_cm = float(largo_mango) if largo_mango else None

        precio_menor = clean_price(request.form["precio_menor"])
        precio_concesion = clean_price(request.form["precio_concesion"])
        precio_mercadolibre = clean_price(request.form["precio_mercadolibre"])

        imagen_file = request.files.get("imagen_file")
        if imagen_file and imagen_file.filename:
            if allowed_file(imagen_file.filename):
                if producto.imagen:
                    ruta_vieja = os.path.join(app.root_path, "static", producto.imagen.replace("/", os.sep))
                    if os.path.exists(ruta_vieja):
                        try:
                            os.remove(ruta_vieja)
                        except Exception:
                            pass
                filename = secure_filename(imagen_file.filename)
                ext = filename.rsplit(".", 1)[1].lower()
                filename = f"{producto.codigo.lower()}.{ext}"
                os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                imagen_file.save(filepath)
                producto.imagen = f"img/cuchillos/{filename}"
            else:
                flash("La extensión de la imagen no es válida. Usa JPG, PNG, JPEG o GIF.")
                return redirect(url_for("catalogo_editar", codigo=codigo))

        producto.nombre = nombre
        producto.categoria_principal = categoria_principal
        producto.categoria_secundaria = categoria_secundaria
        producto.acero = acero
        producto.mango = mango
        producto.largo_hoja_cm = largo_hoja_cm
        producto.largo_mango_cm = largo_mango_cm
        producto.precio_menor = precio_menor
        producto.precio_concesion = precio_concesion
        producto.precio_mercadolibre = precio_mercadolibre

        db.session.commit()
        flash(f"Producto {codigo} actualizado correctamente.")
        return redirect(url_for("catalogo_ver", codigo=codigo))

    return render_template("catalogo/editar.html", producto=producto)

@app.route("/catalogo/eliminar/<codigo>")
def catalogo_eliminar(codigo):
    producto = Producto.query.filter_by(codigo=codigo).first()
    if not producto:
        flash(f"El producto con código {codigo} no existe.")
        return redirect(url_for("catalogo_index"))

    if producto.imagen:
        ruta_archivo = os.path.join(app.root_path, "static", producto.imagen.replace("/", os.sep))
        if os.path.exists(ruta_archivo):
            try:
                os.remove(ruta_archivo)
            except Exception:
                pass

    db.session.delete(producto)
    db.session.commit()
    flash(f"Producto {codigo} eliminado correctamente.")
    return redirect(url_for("catalogo_index"))

@app.route("/inventario")
def inventario_index():
    # Mes actual para ventas del mes
    ahora = datetime.utcnow()
    inicio_mes = datetime(ahora.year, ahora.month, 1)
    if ahora.month == 12:
        fin_mes_exclusivo = datetime(ahora.year + 1, 1, 1)
    else:
        fin_mes_exclusivo = datetime(ahora.year, ahora.month + 1, 1)

    # Ventas del mes agrupadas por producto
    ventas_mes_rows = (
        db.session.query(
            VentaTienda.producto_id,
            func.sum(VentaTienda.cantidad).label("cant_mes")
        )
        .filter(
            VentaTienda.fecha >= inicio_mes,
            VentaTienda.fecha < fin_mes_exclusivo
        )
        .group_by(VentaTienda.producto_id)
        .all()
    )
    ventas_mes_dict = {
        row.producto_id: row.cant_mes for row in ventas_mes_rows
    }

    # Stock total por producto (solo tiendas/bodegas no eliminadas)
    stock_rows = (
        db.session.query(
            Producto.id,
            func.sum(StockTienda.cantidad).label("stock_total")
        )
        .join(StockTienda, StockTienda.producto_id == Producto.id)
        .join(Tienda, StockTienda.tienda_id == Tienda.id)
        .filter(Tienda.eliminada == False)
        .group_by(Producto.id)
        .all()
    )
    stock_dict = {
        row.id: (row.stock_total or 0) for row in stock_rows
    }

    # Construimos la lista de inventario por producto
    productos = Producto.query.order_by(
        func.length(Producto.codigo), Producto.codigo
    ).all()

    inventario = []
    total_unidades = 0

    for p in productos:
        stock_total = stock_dict.get(p.id, 0)
        ventas_mes = ventas_mes_dict.get(p.id, 0)
        total_unidades += stock_total

        es_espada = (p.categoria_principal or "").lower().startswith("espada")

        inventario.append({
            "producto": p,
            "stock_total": stock_total,
            "ventas_mes": ventas_mes,
            "es_espada": es_espada,
        })
        # Valor total del inventario (concesión y por menor)
    valor_inv_concesion = 0
    valor_inv_menor = 0

    for item in inventario:
        p = item["producto"]
        stock_total = item["stock_total"] or 0

        precio_conc = p.precio_concesion or 0
        precio_menor = p.precio_menor or 0

        valor_inv_concesion += stock_total * precio_conc
        valor_inv_menor += stock_total * precio_menor

    # Resúmenes
    modelos_con_stock = sum(
        1 for item in inventario if item["stock_total"] > 0
    )
    modelos_sin_stock = [
        item for item in inventario if item["stock_total"] == 0
    ]

    # Top más vendidos del mes (máx 8)
    top_vendidos = sorted(
        [item for item in inventario if item["ventas_mes"] > 0],
        key=lambda x: x["ventas_mes"],
        reverse=True
    )[:8]

    # Recomendación de compra:
    # - excluimos espadas (solo vitrina)
    # - prioridad a los que se venden bien y tienen poco stock
    recomendados = []
    for item in inventario:
        p = item["producto"]
        if item["es_espada"]:
            continue  # las espadas no se recomiendan, solo 1 de muestra

        stock_total = item["stock_total"]
        ventas_mes = item["ventas_mes"]

        # Regla simple:
        #  - si vende harto y el stock ya está al nivel de las ventas → recomprar
        #  - o si vende algo y queda muy poco stock → recomprar
        if ventas_mes >= 3 and stock_total <= ventas_mes:
            recomendados.append(item)
        elif ventas_mes >= 1 and stock_total <= 2:
            recomendados.append(item)

    recomendados = sorted(
        recomendados,
        key=lambda x: (-x["ventas_mes"], x["stock_total"])
    )

    return render_template(
        "inventario/inventario.html",
        inventario=inventario,
        total_unidades=total_unidades,
        modelos_con_stock=modelos_con_stock,
        modelos_sin_stock=modelos_sin_stock,
        top_vendidos=top_vendidos,
        recomendados=recomendados,
        inicio_mes=inicio_mes,
        valor_inv_concesion=valor_inv_concesion,
        valor_inv_menor=valor_inv_menor,
    )

@app.route("/finanzas")
def finanzas_index():
    # Año seleccionado
    y = request.args.get("year", type=int)
    hoy = date.today()
    year = y or hoy.year

    # Nombres de meses para mostrar en pantallas
    meses_nombres = [
        "Enero", "Febrero", "Marzo", "Abril",
        "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

       # ---------------------------
    # VENTAS POR MES + IVA (usando solo lo efectivamente pagado)
    # ---------------------------
    ventas_por_mes = [0] * 12      # ingresos netos efectivamente cobrados
    iva_por_mes    = [0] * 12      # IVA estimado sobre lo cobrado

    # también acumularemos ventas por tienda / vendedor
    acumulado_por_tienda = {}

    filas_ventas = (
        db.session.query(VentaTienda, Tienda)
        .outerjoin(Tienda, VentaTienda.tienda_id == Tienda.id)
        .filter(func.strftime("%Y", VentaTienda.fecha) == str(year))
        .all()
    )

    for venta, tienda in filas_ventas:
        if not venta.fecha:
            continue

        mes_idx = int(venta.fecha.strftime("%m")) - 1

        # Lo que realmente se debe considerar como ingreso
        monto = venta.monto_reconocido  # usa total si es contado, monto_pagado si es en cuotas

        ventas_por_mes[mes_idx] += monto

        # IVA según modo de la tienda
        iva_modo = (tienda.iva_modo if tienda and tienda.iva_modo else "incluido")
        if iva_modo != "no":
            iva_val = int(round(monto * 0.19))
            iva_por_mes[mes_idx] += iva_val

        # Acumulamos por tienda/vendedor para la tabla de abajo
        if tienda and tienda.nombre:
            nombre_tienda = tienda.nombre
        else:
            # por si se borra la tienda, usamos el snapshot
            nombre_tienda = venta.tienda_nombre_snapshot or "Sin nombre"

        acumulado_por_tienda.setdefault(nombre_tienda, 0)
        acumulado_por_tienda[nombre_tienda] += monto

    total_ventas = sum(ventas_por_mes)
    total_iva = sum(iva_por_mes)

    # Convertimos el diccionario a lista ordenada para la tabla "Ventas por tienda / vendedor"
    ventas_tiendas = [
        {"nombre": nombre, "total": total}
        for nombre, total in sorted(
            acumulado_por_tienda.items(),
            key=lambda x: x[1],
            reverse=True
        )
    ]
    # ---------------------------
    # GASTOS POR MES
    # ---------------------------
    gastos_rows = (
        db.session.query(
            func.strftime("%m", Gasto.fecha).label("mes"),
            func.sum(Gasto.monto).label("total")
        )
        .filter(func.strftime("%Y", Gasto.fecha) == str(year))
        .group_by("mes")
        .all()
    )

    gastos_por_mes = [0] * 12
    for row in gastos_rows:
        mes_str = row.mes
        total_g = row.total or 0
        if not mes_str:
            continue
        idx = int(mes_str) - 1
        gastos_por_mes[idx] = total_g

    total_gastos = sum(gastos_por_mes)

    # ---------------------------
    # GASTOS POR CATEGORÍA (para tabla)
    # ---------------------------
    gastos_cat_rows = (
        db.session.query(
            Gasto.categoria,
            func.sum(Gasto.monto).label("total")
        )
        .filter(func.strftime("%Y", Gasto.fecha) == str(year))
        .group_by(Gasto.categoria)
        .all()
    )

    gastos_cat_labels = []
    gastos_cat_data = []
    for row in gastos_cat_rows:
        gastos_cat_labels.append(row.categoria or "Sin categoría")
        gastos_cat_data.append(int(row.total or 0))
    gastos_cat_total = sum(gastos_cat_data)

    # ---------------------------
    # VENTAS POR TIENDA EN EL AÑO
    # ---------------------------
    coalesce_nombre = func.coalesce(
        Tienda.nombre,
        VentaTienda.tienda_nombre_snapshot,
        "Sin tienda"
    )

    ventas_tiendas_rows = (
        db.session.query(
            coalesce_nombre.label("nombre"),
            func.sum(VentaTienda.total).label("total")
        )
        .outerjoin(Tienda, VentaTienda.tienda_id == Tienda.id)
        .filter(func.strftime("%Y", VentaTienda.fecha) == str(year))
        .group_by(coalesce_nombre)
        .order_by(func.sum(VentaTienda.total).desc())
        .all()
    )

    ventas_tiendas = [
        {
            "nombre": row.nombre,
            "total": int(row.total or 0),
        }
        for row in ventas_tiendas_rows
    ]

    # ---------------------------
    # RESULTADOS ANUALES
    # ---------------------------
    utilidad_bruta = total_ventas - total_gastos
    utilidad_despues_iva = total_ventas - total_gastos - total_iva

    # ---------------------------
    # MESES CLAVE (mejor mes, más gastos, peor resultado)
    # ---------------------------
    resultados_por_mes = [
        ventas_por_mes[i] - gastos_por_mes[i] for i in range(12)
    ]

    mejor_mes_ventas_nombre = "Sin datos"
    mejor_mes_ventas_monto = 0
    mes_mas_gastos_nombre = "Sin datos"
    mes_mas_gastos_monto = 0
    peor_mes_resultado_nombre = "Sin datos"
    peor_mes_resultado_monto = 0

    if any(ventas_por_mes):
        idx_max_ventas = max(range(12), key=lambda i: ventas_por_mes[i])
        mejor_mes_ventas_nombre = meses_nombres[idx_max_ventas]
        mejor_mes_ventas_monto = ventas_por_mes[idx_max_ventas]

    if any(gastos_por_mes):
        idx_max_gastos = max(range(12), key=lambda i: gastos_por_mes[i])
        mes_mas_gastos_nombre = meses_nombres[idx_max_gastos]
        mes_mas_gastos_monto = gastos_por_mes[idx_max_gastos]

    # Solo si hay algún movimiento (ventas o gastos) calculamos peor resultado
    if any(ventas_por_mes) or any(gastos_por_mes):
        idx_peor_res = min(range(12), key=lambda i: resultados_por_mes[i])
        peor_mes_resultado_nombre = meses_nombres[idx_peor_res]
        peor_mes_resultado_monto = resultados_por_mes[idx_peor_res]

    # Años para el selector
    años = list(range(hoy.year - 3, hoy.year + 1))

    return render_template(
        "finanzas/finanzas.html",
        year=year,
        años=años,
        ventas_por_mes=ventas_por_mes,
        gastos_por_mes=gastos_por_mes,
        iva_por_mes=iva_por_mes,
        total_ventas=total_ventas,
        total_gastos=total_gastos,
        total_iva=total_iva,
        utilidad_bruta=utilidad_bruta,
        utilidad_despues_iva=utilidad_despues_iva,
        gastos_cat_labels=gastos_cat_labels,
        gastos_cat_data=gastos_cat_data,
        gastos_cat_total=gastos_cat_total,
        ventas_tiendas=ventas_tiendas,
        # meses clave
        mejor_mes_ventas_nombre=mejor_mes_ventas_nombre,
        mejor_mes_ventas_monto=mejor_mes_ventas_monto,
        mes_mas_gastos_nombre=mes_mas_gastos_nombre,
        mes_mas_gastos_monto=mes_mas_gastos_monto,
        peor_mes_resultado_nombre=peor_mes_resultado_nombre,
        peor_mes_resultado_monto=peor_mes_resultado_monto,
    )

# ─────────────────────────────
# MAIN
# ─────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        ensure_schema()
    # En local puedes seguir usando debug y puerto 5001 si quieres:
    app.run(debug=True, port=5001)