from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

database_url = os.environ.get("DATABASE_URL")

if database_url:
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///taxhub.db '
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'super_admin', 'user'
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    requirements = db.Column(db.Text)
    pan_last4 = db.Column(db.String(4), nullable=False)
    status = db.Column(db.String(20), default='pending')
    remark = db.Column(db.Text)
    remark_history = db.Column(db.Text)  # JSON array of {remark, timestamp, user}
    assigned_to = db.Column(db.Text)  # JSON array of user IDs
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()
    
    # Create default users if they don't exist
    if not User.query.filter_by(email='admin@123').first():
        super_admin = User(email='admin@123', password='password123', role='super_admin', name='Super Admin')
        db.session.add(super_admin)
    
    if not User.query.filter_by(email='user1@gmail.com').first():
        user1 = User(email='user1@gmail.com', password='user1', role='user', name='User One')
        db.session.add(user1)
    
    if not User.query.filter_by(email='user2@gmail.com').first():
        user2 = User(email='user2@gmail.com', password='user2', role='user', name='User Two')
        db.session.add(user2)
    
    db.session.commit()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        user = User.query.get(session['user_id'])
        if user.role != 'super_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = User.query.filter_by(email=email, password=password).first()
    if user:
        session['user_id'] = user.id
        session['user_email'] = user.email
        session['user_role'] = user.role
        session['user_name'] = user.name
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'name': user.name
            }
        })
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/current-user')
def current_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return jsonify({
            'id': user.id,
            'email': user.email,
            'role': user.role,
            'name': user.name
        })
    return jsonify({'error': 'Not logged in'}), 401

@app.route('/api/users')
@login_required
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'email': u.email,
        'role': u.role,
        'name': u.name
    } for u in users])

@app.route('/api/tasks', methods=['GET', 'POST'])
@login_required
def handle_tasks():
    if request.method == 'POST':
        data = request.json
        assigned_to = data.get('assigned_to', [1])
        
        task = Task(
            name=data['name'],
            mobile=data['mobile'],
            service=data['service'],
            requirements=data.get('requirements', ''),
            pan_last4=data['pan_last4'],
            assigned_to=json.dumps(assigned_to),
            created_by=session['user_id'],
            status='pending',
            remark_history=json.dumps([])
        )
        db.session.add(task)
        db.session.commit()
        return jsonify({'success': True, 'task_id': task.id})
    
    # GET - fetch all tasks for everyone
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'mobile': t.mobile,
        'service': t.service,
        'requirements': t.requirements,
        'pan_last4': t.pan_last4,
        'status': t.status,
        'remark': t.remark,
        'remark_history': json.loads(t.remark_history) if t.remark_history else [],
        'assigned_to': json.loads(t.assigned_to) if t.assigned_to else [],
        'created_by': t.created_by,
        'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
        'updated_at': t.updated_at.strftime('%Y-%m-%d %H:%M') if t.updated_at else ''
    } for t in tasks])

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.json
    user = User.query.get(session['user_id'])
    
    # Check if user is assigned to this task
    assigned = json.loads(task.assigned_to) if task.assigned_to else []
    is_assigned = session['user_id'] in assigned
    
    if user.role == 'super_admin':
        # Super admin can update everything
        if 'status' in data:
            task.status = data['status']
        if 'remark' in data and data['remark']:
            history = json.loads(task.remark_history) if task.remark_history else []
            history.append({
                'remark': data['remark'],
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'user': user.name or user.email
            })
            task.remark_history = json.dumps(history)
            task.remark = data['remark']
        if 'assigned_to' in data:
            task.assigned_to = json.dumps(data['assigned_to'])
        if 'name' in data:
            task.name = data['name']
        if 'mobile' in data:
            task.mobile = data['mobile']
        if 'service' in data:
            task.service = data['service']
        if 'requirements' in data:
            task.requirements = data['requirements']
        if 'pan_last4' in data:
            task.pan_last4 = data['pan_last4']
    else:
        # Normal user can only update if assigned to them
        if not is_assigned:
            return jsonify({'error': 'You are not authorized to update this task'}), 403
        
        if 'status' in data:
            task.status = data['status']
        if 'remark' in data and data['remark']:
            history = json.loads(task.remark_history) if task.remark_history else []
            history.append({
                'remark': data['remark'],
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'user': user.name or user.email
            })
            task.remark_history = json.dumps(history)
            task.remark = data['remark']
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@admin_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/form-submit', methods=['POST'])
def form_submit():
    data = request.json
    
    task = Task(
        name=data['name'],
        mobile=data['mobile'],
        service=data['service'],
        requirements=data.get('requirements', ''),
        pan_last4=data['pan_last4'],
        assigned_to=json.dumps([]),  # Unassigned initially
        created_by=1,
        status='pending',
        remark_history=json.dumps([])
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Form submitted successfully', 'task_id': task.id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)