from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone
# To run this code you need to install the following dependencies:
# pip install google-genai
import base64
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY")
        ,
    )

model = "gemini-2.5-flash-lite"





app = Flask(__name__)
app.secret_key = 'clave_secreta'

# Configuración de la base de datos (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///usuarios.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

limiter = Limiter(key_func=get_remote_address, app=app)

# Modelo de usuario
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    stock = db.Column(db.Integer, default=0)
    precio = db.Column(db.Float)
    user_id =db.Column(db.Integer)
    fecha_agregado = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    stock = db.Column(db.Integer, default=0)
    costo = db.Column(db.Float)
    user_id =db.Column(db.Integer)
    fecha_agregado = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'))
    cantidad = db.Column(db.Integer)
    precio_unitario = db.Column(db.Float)
    user_id =db.Column(db.Integer)
    fecha_venta = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    producto = db.relationship('Producto')

# Cargar usuario para Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        user =  User.query.filter_by(username=username).first()
        if user and user.verify_password(password):
            
            login_user(user)
            return redirect(url_for('home'))
        else:
            return "Credenciales incorrectas."

    return render_template('login.html')

@app.route('/')
@login_required
def home():
    productos = Producto.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', username=current_user.id, productos=productos)

@app.route('/chatbot', methods=['POST', 'GET'])
@limiter.limit("15 per minute") 
@login_required
def chatbot():
    ventas=Venta.query.filter_by(user_id=current_user.id)
    ventass="Las ventas: "
    for venta in ventas:
        ventass+=(f"nombre:{venta.producto.nombre}, ")
        ventass+=(f"precio de venta unitario:{venta.precio_unitario}, ")
        ventass+=(f"cantidad:{venta.cantidad}, ")
        ventass+=(f"fecha de venta:{venta.fecha_venta}\n")
    compras=Compra.query.filter_by(user_id=current_user.id)
    comprass=" \nLas compras de la empresa: "
    for venta in compras:
        comprass+=(f"nombre:{venta.nombre}, ")
        comprass+=(f"costo de compra unitario:{venta.costo}, ")
        comprass+=(f"cantidad comprada:{venta.stock}, ")
        comprass+=(f"fecha de compra:{venta.fecha_agregado}\n")
    productos= Producto.query.filter_by(user_id=current_user.id)
    productoss=" \nLas compras de la empresa: "
    for venta in productos:
        productoss+=(f"nombre:{venta.nombre}, ")
        productoss+=(f"precio de venta unitario:{venta.precio}, ")
        productoss+=(f"stock:{venta.stock}, ")
        productoss+=(f"fecha que se agrego:{venta.fecha_agregado}\n")
    generate_content_config = types.GenerateContentConfig(
    temperature=0.25,
    max_output_tokens=1000,
    thinking_config = types.ThinkingConfig(
        thinking_budget=0,
        ),
    system_instruction=[
        types.Part.from_text(text="responde las preguntas segun la siguiente informacion de la base de datos:\n"+comprass+productoss+ventass+"\n si los campos estan vacios significa que no hay resultados. Responde sin formato Markdown ni asteriscos. intenta responder la pregunta con los datos que tienes aunque limiten su precision "),
        ],
    )
    x=""
    if request.method == 'POST':
        user_input = request.form['pregunta']
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_input),
            ],
        ),
    ]
        try:
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
    ):
             x+=(chunk.text or "")
        except Exception as e:
            return {"response": f"Error al generar respuesta: {str(e)}"}, 500
    return render_template('chatbot.html', respuesta=x)

@app.route('/ventas', methods=['GET'])
@login_required
def ventas():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    
    query = Venta.query.filter_by(user_id=current_user.id)

    # Agregar filtros opcionales
    if year:
        query = query.filter(db.extract('year', Venta.fecha_venta) == year)
    if month:
        query = query.filter(db.extract('month', Venta.fecha_venta) == month)

    ventas = query.all()


    # Total vendido
    total = sum(v.cantidad * v.precio_unitario for v in ventas)

    return render_template('ventas.html', productos=ventas, total=total, year=year, month=month)
@app.route('/compras', methods=['GET'])
@login_required
def compras():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    query = Compra.query.filter_by(user_id=current_user.id)
    if year:
        query = query.filter(db.extract('year', Compra.fecha_agregado) == year)
    if month:
        query = query.filter(db.extract('month', Compra.fecha_agregado) == month)
    
    compras = query.all()
    total = sum(v.stock * v.costo for v in compras)
    return render_template('compras.html',productos=compras, total=total, year=year, month=month)

@app.route('/about_us')
def about_us():
    return render_template('about_us.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('about_us'))

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        # Validaciones básicas
        if not username or not password:
            return "Por favor, llena todos los campos."

        # Revisar si el usuario ya existe
        if User.query.filter_by(username=username).first():
            return "Este usuario ya está registrado."

        # Crear nuevo usuario con contraseña hasheada
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        # Iniciar sesión automáticamente
        login_user(new_user)
        return redirect(url_for('home'))

    return render_template('register.html')

@app.route('/agregar', methods=['GET', 'POST'])
@login_required
def agregar_producto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        precio = float(request.form['precio'])
        stock = int(request.form['stock'])
        user_id=current_user.id
        nuevo = Producto(nombre=nombre, precio=precio, stock=stock, user_id=user_id)
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('home'))
    
    return render_template('agregar.html', x="Producto", y="Precio")

@app.route('/añadir', methods=['GET', 'POST'])
@login_required
def añadir_inventario():
    productos = Producto.query.filter_by(user_id=current_user.id).all()
    if request.method == 'POST':
        producto_id = int(request.form['producto_id'])
        cantidad = int(request.form['cantidad'])
        producto = Producto.query.get_or_404(producto_id)
        producto.stock=producto.stock+cantidad
        
        db.session.commit()
        return redirect(url_for('home'))
    
    return render_template('añadir.html',productos=productos)
@app.route('/agregar_compra', methods=['GET', 'POST'])
@login_required
def agregar_compra():
    if request.method == 'POST':
        nombre = request.form['nombre']
        costo = float(request.form['precio'])
        stock = int(request.form['stock'])
        user_id=current_user.id
        nuevo = Compra(nombre=nombre, costo=costo,  stock=stock, user_id=user_id)
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('home'))
    
    return render_template('agregar.html', x="Compra", y="costo")

@app.route('/añadir_compra', methods=['GET', 'POST'])
@login_required
def añadir_compra():
    productos = Compra.query.filter_by(user_id=current_user.id).all()
    if request.method == 'POST':
        nombre = (request.form['producto_nombre'])
        cantidad = int(request.form['cantidad'])
        producto = Compra.query.filter_by(nombre=nombre, user_id=current_user.id).first_or_404()
        compra =Compra(nombre=producto.nombre, stock=cantidad, costo=producto.costo,user_id=current_user.id)
        db.session.add(compra)
        db.session.commit()
        return redirect(url_for('home'))
    
    return render_template('añadir_compra.html',productos=productos)

@app.route('/vender', methods=['GET', 'POST'])
@login_required
def vender_producto():
    productos = Producto.query.filter_by(user_id=current_user.id).all()

    if request.method == 'POST':
        producto_id = int(request.form['producto_id'])
        cantidad = int(request.form['cantidad'])
        producto = Producto.query.get_or_404(producto_id)

        if producto.stock >= cantidad:
            producto.stock -= cantidad
            venta = Venta(producto_id=producto.id, cantidad=cantidad, precio_unitario=producto.precio, user_id=current_user.id)
            db.session.add(venta)
            db.session.commit()

        return redirect(url_for('home'))
    return render_template('vender.html', productos=productos)

if __name__ == '__main__':
    app.run(debug=True)



