import os
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://localhost/stock_inventory')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Render PostgreSQL URL format
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Email configuration
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
ADMIN_RESET_EMAIL = os.environ.get('ADMIN_RESET_EMAIL', 'service.aur@ptespl.com')

# Models
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Engineer')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    stock_requests = db.relationship('StockRequest', backref='requester', lazy=True)
    engineer_stock_logs = db.relationship('EngineerStockLog', backref='engineer', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

class StockItem(db.Model):
    __tablename__ = 'stock_items'
    
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    total_quantity = db.Column(db.Integer, nullable=False, default=0)
    available_quantity = db.Column(db.Integer, nullable=False, default=0)
    unit = db.Column(db.String(20), nullable=False, default='pcs')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    stock_requests = db.relationship('StockRequest', backref='stock_item', lazy=True)
    engineer_stock_logs = db.relationship('EngineerStockLog', backref='stock_item', lazy=True)
    
    def __repr__(self):
        return f'<StockItem {self.item_id}: {self.name}>'

class StockRequest(db.Model):
    __tablename__ = 'stock_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stock_item_id = db.Column(db.Integer, db.ForeignKey('stock_items.id'), nullable=False)
    requested_quantity = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='Pending')
    docket_number = db.Column(db.String(100))
    
    # Timestamps
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)
    
    # Approval details
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approval_notes = db.Column(db.Text)
    
    def __repr__(self):
        return f'<StockRequest {self.id}: {self.requested_quantity} x {self.stock_item.name if self.stock_item else "Unknown"}>'
    
    @property
    def pending_days(self):
        if self.status == 'Pending':
            return (datetime.utcnow() - self.requested_at).days
        elif self.status == 'Approved' and not self.sent_at:
            return (datetime.utcnow() - self.approved_at).days if self.approved_at else 0
        return 0

class EngineerStockLog(db.Model):
    __tablename__ = 'engineer_stock_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stock_item_id = db.Column(db.Integer, db.ForeignKey('stock_items.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Available')
    notes = db.Column(db.Text)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)
    request_id = db.Column(db.Integer, db.ForeignKey('stock_requests.id'))
    
    def __repr__(self):
        return f'<EngineerStockLog {self.id}: {self.quantity} x {self.stock_item.name if self.stock_item else "Unknown"}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    username = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    
    def __repr__(self):
        return f'<AuditLog {self.id}: {self.username} - {self.action}>'

class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    
    def __init__(self, user_id, expires_in_hours=24):
        self.user_id = user_id
        self.token = secrets.token_urlsafe(32)
        self.expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

# Utility functions
def require_role(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('login'))
            
            if session.get('role') != role:
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_audit_action(user_id, username, role, action, details):
    audit_log = AuditLog(
        user_id=user_id,
        username=username,
        role=role,
        action=action,
        details=details,
        timestamp=datetime.utcnow(),
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Failed to log audit action: {e}')

def send_email(to_email, subject, body, urgency_color='black'):
    if not SMTP_USER or not SMTP_PASS:
        app.logger.warning('SMTP credentials not configured, skipping email')
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f'[{urgency_color.upper()}] {subject}'
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="border-left: 4px solid {urgency_color}; padding-left: 20px;">
                    <h2 style="color: {urgency_color};">Stock Request Alert</h2>
                    {body}
                </div>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        
        return True
    except Exception as e:
        app.logger.error(f'Failed to send email: {e}')
        return False

def check_pending_requests():
    """Background job to check for pending requests and send escalation emails"""
    with app.app_context():
        try:
            # Get all pending requests
            pending_requests = StockRequest.query.filter_by(status='Pending').all()
            approved_not_sent = StockRequest.query.filter_by(status='Approved').filter(
                StockRequest.sent_at.is_(None)
            ).all()
            
            all_requests = pending_requests + approved_not_sent
            
            for request in all_requests:
                days_pending = request.pending_days
                
                if days_pending >= 7:
                    urgency = 'red'
                    urgency_text = 'URGENT - 7+ days'
                elif days_pending >= 3:
                    urgency = 'orange'
                    urgency_text = 'HIGH - 3+ days'
                elif days_pending >= 1:
                    urgency = 'gold'
                    urgency_text = 'MEDIUM - 1+ days'
                else:
                    continue  # Skip if less than 1 day
                
                status_text = 'pending approval' if request.status == 'Pending' else 'approved but not sent'
                
                subject = f'Stock Request {urgency_text} - Request #{request.id}'
                body = f"""
                <p><strong>Alert:</strong> Stock request has been {status_text} for {days_pending} day(s)</p>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Request ID:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.id}</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Engineer:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.requester.username}</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Item:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.stock_item.name} ({request.stock_item.item_id})</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Quantity:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.requested_quantity} {request.stock_item.unit}</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Requested:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.requested_at.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Status:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{request.status}</td></tr>
                    <tr><td style="border: 1px solid #ddd; padding: 8px;"><strong>Days Pending:</strong></td><td style="border: 1px solid #ddd; padding: 8px;">{days_pending}</td></tr>
                </table>
                <p><strong>Notes:</strong> {request.notes or 'None'}</p>
                <p>Please take action on this request.</p>
                """
                
                send_email(ADMIN_RESET_EMAIL, subject, body, urgency)
                
                # Log the escalation
                log_audit_action(
                    user_id=None,
                    username='SYSTEM',
                    role='SYSTEM',
                    action='ESCALATION_EMAIL',
                    details=f'Sent {urgency} escalation email for request #{request.id} ({days_pending} days pending)'
                )
            
        except Exception as e:
            app.logger.error(f'Error in check_pending_requests job: {e}')

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_pending_requests,
    trigger=IntervalTrigger(hours=6),
    id='check_pending_requests',
    name='Check pending requests for escalation emails',
    replace_existing=True
)

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if user.role == 'HOD':
        return redirect(url_for('hod_dashboard'))
    else:
        return redirect(url_for('engineer_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            log_audit_action(
                user_id=user.id,
                username=user.username,
                role=user.role,
                action='LOGIN',
                details=f'Successful login from IP: {request.remote_addr}'
            )
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            if user.role == 'HOD':
                return redirect(url_for('hod_dashboard'))
            else:
                return redirect(url_for('engineer_dashboard'))
        else:
            log_audit_action(
                user_id=None,
                username=username,
                role='Unknown',
                action='LOGIN_FAILED',
                details=f'Failed login attempt for username: {username} from IP: {request.remote_addr}'
            )
            
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_audit_action(
            user_id=session.get('user_id'),
            username=session.get('username'),
            role=session.get('role'),
            action='LOGOUT',
            details='User logged out'
        )
    
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

# HOD Routes
@app.route('/hod/dashboard')
@require_role('HOD')
def hod_dashboard():
    total_engineers = User.query.filter_by(role='Engineer', is_active=True).count()
    total_stock_items = StockItem.query.count()
    pending_requests = StockRequest.query.filter_by(status='Pending').count()
    recent_requests = StockRequest.query.order_by(StockRequest.requested_at.desc()).limit(5).all()
    low_stock_items = StockItem.query.filter(StockItem.available_quantity < 10).all()
    
    return render_template('hod_dashboard.html', 
                         total_engineers=total_engineers,
                         total_stock_items=total_stock_items,
                         pending_requests=pending_requests,
                         recent_requests=recent_requests,
                         low_stock_items=low_stock_items)

@app.route('/hod/engineers')
@require_role('HOD')
def hod_engineers():
    search = request.args.get('search', '')
    if search:
        engineers_list = User.query.filter(
            User.role == 'Engineer',
            User.username.contains(search)
        ).order_by(User.created_at.desc()).all()
    else:
        engineers_list = User.query.filter_by(role='Engineer').order_by(User.created_at.desc()).all()
    
    return render_template('hod_engineers.html', engineers=engineers_list, search=search)

@app.route('/hod/engineers/create', methods=['GET', 'POST'])
@require_role('HOD')
def create_engineer():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('create_engineer.html')
        
        engineer = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='Engineer',
            created_by=session['user_id'],
            created_at=datetime.utcnow()
        )
        
        db.session.add(engineer)
        db.session.commit()
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='CREATE_ENGINEER',
            details=f'Created engineer account: {username}'
        )
        
        flash(f'Engineer account created successfully for {username}', 'success')
        return redirect(url_for('hod_engineers'))
    
    return render_template('create_engineer.html')

@app.route('/hod/stock')
@require_role('HOD')
def hod_stock():
    search = request.args.get('search', '')
    if search:
        stock_items = StockItem.query.filter(
            db.or_(
                StockItem.item_id.contains(search),
                StockItem.name.contains(search),
                StockItem.description.contains(search)
            )
        ).order_by(StockItem.created_at.desc()).all()
    else:
        stock_items = StockItem.query.order_by(StockItem.created_at.desc()).all()
    
    return render_template('hod_stock.html', stock_items=stock_items, search=search)

@app.route('/hod/stock/create', methods=['GET', 'POST'])
@require_role('HOD')
def create_stock_item():
    if request.method == 'POST':
        item_id = request.form['item_id'].strip()
        name = request.form['name'].strip()
        description = request.form['description'].strip()
        total_quantity = int(request.form['total_quantity'])
        unit = request.form['unit'].strip()
        
        if StockItem.query.filter_by(item_id=item_id).first():
            flash('Item ID already exists', 'error')
            return render_template('create_stock_item.html')
        
        stock_item = StockItem(
            item_id=item_id,
            name=name,
            description=description,
            total_quantity=total_quantity,
            available_quantity=total_quantity,
            unit=unit,
            created_by=session['user_id'],
            created_at=datetime.utcnow()
        )
        
        db.session.add(stock_item)
        db.session.commit()
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='CREATE_STOCK_ITEM',
            details=f'Created stock item: {item_id} - {name} (Qty: {total_quantity} {unit})'
        )
        
        flash(f'Stock item {item_id} created successfully', 'success')
        return redirect(url_for('hod_stock'))
    
    return render_template('create_stock_item.html')

@app.route('/hod/requests')
@require_role('HOD')
def hod_requests():
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    query = StockRequest.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if search:
        query = query.join(User).join(StockItem).filter(
            db.or_(
                User.username.contains(search),
                StockItem.name.contains(search),
                StockItem.item_id.contains(search)
            )
        )
    
    requests_list = query.order_by(StockRequest.requested_at.desc()).all()
    
    return render_template('hod_requests.html', 
                         requests=requests_list, 
                         status_filter=status_filter,
                         search=search)

@app.route('/hod/requests/<int:request_id>/approve', methods=['POST'])
@require_role('HOD')
def approve_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status != 'Pending':
        flash('Request has already been processed', 'error')
        return redirect(url_for('hod_requests'))
    
    action = request.form.get('action')
    approval_notes = request.form.get('approval_notes', '').strip()
    
    if action == 'approve':
        if stock_request.requested_quantity > stock_request.stock_item.available_quantity:
            flash('Insufficient stock available', 'error')
            return redirect(url_for('hod_requests'))
        
        stock_request.status = 'Approved'
        stock_request.approved_at = datetime.utcnow()
        stock_request.approved_by = session['user_id']
        stock_request.approval_notes = approval_notes
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='APPROVE_REQUEST',
            details=f'Approved request #{request_id} for {stock_request.requested_quantity} x {stock_request.stock_item.name}'
        )
        
        flash('Request approved successfully', 'success')
        
    elif action == 'deny':
        stock_request.status = 'Denied'
        stock_request.approved_at = datetime.utcnow()
        stock_request.approved_by = session['user_id']
        stock_request.approval_notes = approval_notes
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='DENY_REQUEST',
            details=f'Denied request #{request_id} for {stock_request.requested_quantity} x {stock_request.stock_item.name}'
        )
        
        flash('Request denied', 'info')
    
    db.session.commit()
    return redirect(url_for('hod_requests'))

@app.route('/hod/requests/<int:request_id>/send', methods=['POST'])
@require_role('HOD')
def send_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status != 'Approved':
        flash('Request must be approved first', 'error')
        return redirect(url_for('hod_requests'))
    
    docket_number = request.form.get('docket_number', '').strip()
    
    if not docket_number:
        flash('Docket number is required', 'error')
        return redirect(url_for('hod_requests'))
    
    stock_request.status = 'In Transit'
    stock_request.docket_number = docket_number
    stock_request.sent_at = datetime.utcnow()
    
    stock_request.stock_item.available_quantity -= stock_request.requested_quantity
    
    log_audit_action(
        user_id=session['user_id'],
        username=session['username'],
        role=session['role'],
        action='SEND_REQUEST',
        details=f'Sent request #{request_id} with docket: {docket_number}'
    )
    
    db.session.commit()
    flash(f'Request sent successfully with docket number: {docket_number}', 'success')
    return redirect(url_for('hod_requests'))

# Engineer Routes
@app.route('/engineer/dashboard')
@require_role('Engineer')
def engineer_dashboard():
    total_requests = StockRequest.query.filter_by(user_id=session['user_id']).count()
    pending_requests = StockRequest.query.filter_by(
        user_id=session['user_id'], 
        status='Pending'
    ).count()
    in_transit_requests = StockRequest.query.filter_by(
        user_id=session['user_id'], 
        status='In Transit'
    ).count()
    
    recent_requests = StockRequest.query.filter_by(
        user_id=session['user_id']
    ).order_by(StockRequest.requested_at.desc()).limit(5).all()
    
    personal_stock_count = EngineerStockLog.query.filter_by(
        user_id=session['user_id'],
        status='Available'
    ).count()
    
    return render_template('engineer_dashboard.html',
                         total_requests=total_requests,
                         pending_requests=pending_requests,
                         in_transit_requests=in_transit_requests,
                         recent_requests=recent_requests,
                         personal_stock_count=personal_stock_count)

@app.route('/engineer/stock')
@require_role('Engineer')
def engineer_stock():
    search = request.args.get('search', '')
    if search:
        stock_items = StockItem.query.filter(
            db.or_(
                StockItem.item_id.contains(search),
                StockItem.name.contains(search),
                StockItem.description.contains(search)
            )
        ).order_by(StockItem.name).all()
    else:
        stock_items = StockItem.query.order_by(StockItem.name).all()
    
    return render_template('engineer_stock.html', stock_items=stock_items, search=search)

@app.route('/engineer/request_stock', methods=['GET', 'POST'])
@require_role('Engineer')
def request_stock():
    if request.method == 'POST':
        stock_item_id = int(request.form['stock_item_id'])
        requested_quantity = int(request.form['requested_quantity'])
        notes = request.form.get('notes', '').strip()
        
        stock_item = StockItem.query.get_or_404(stock_item_id)
        
        if requested_quantity <= 0:
            flash('Requested quantity must be greater than 0', 'error')
            return redirect(url_for('request_stock'))
        
        if requested_quantity > stock_item.available_quantity:
            flash(f'Only {stock_item.available_quantity} {stock_item.unit} available', 'error')
            return redirect(url_for('request_stock'))
        
        stock_request = StockRequest(
            user_id=session['user_id'],
            stock_item_id=stock_item_id,
            requested_quantity=requested_quantity,
            notes=notes,
            requested_at=datetime.utcnow()
        )
        
        db.session.add(stock_request)
        db.session.commit()
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='REQUEST_STOCK',
            details=f'Requested {requested_quantity} x {stock_item.name} ({stock_item.item_id})'
        )
        
        flash('Stock request submitted successfully', 'success')
        return redirect(url_for('my_requests'))
    
    stock_items = StockItem.query.filter(StockItem.available_quantity > 0).order_by(StockItem.name).all()
    return render_template('request_stock.html', stock_items=stock_items)

@app.route('/engineer/my_requests')
@require_role('Engineer')
def my_requests():
    status_filter = request.args.get('status', 'all')
    
    query = StockRequest.query.filter_by(user_id=session['user_id'])
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    requests_list = query.order_by(StockRequest.requested_at.desc()).all()
    
    return render_template('my_requests.html', 
                         requests=requests_list, 
                         status_filter=status_filter)

@app.route('/engineer/requests/<int:request_id>/receive', methods=['POST'])
@require_role('Engineer')
def receive_request(request_id):
    stock_request = StockRequest.query.filter_by(
        id=request_id, 
        user_id=session['user_id']
    ).first_or_404()
    
    if stock_request.status != 'In Transit':
        flash('Request is not in transit', 'error')
        return redirect(url_for('my_requests'))
    
    stock_request.status = 'Received'
    stock_request.received_at = datetime.utcnow()
    
    stock_log = EngineerStockLog(
        user_id=session['user_id'],
        stock_item_id=stock_request.stock_item_id,
        quantity=stock_request.requested_quantity,
        status='Available',
        received_at=datetime.utcnow(),
        request_id=request_id,
        notes=f'Received from request #{request_id}'
    )
    
    db.session.add(stock_log)
    
    log_audit_action(
        user_id=session['user_id'],
        username=session['username'],
        role=session['role'],
        action='RECEIVE_STOCK',
        details=f'Received {stock_request.requested_quantity} x {stock_request.stock_item.name} from request #{request_id}'
    )
    
    db.session.commit()
    flash('Stock received and added to your inventory', 'success')
    return redirect(url_for('my_requests'))

@app.route('/engineer/my_stock')
@require_role('Engineer')
def my_stock():
    status_filter = request.args.get('status', 'all')
    
    query = EngineerStockLog.query.filter_by(user_id=session['user_id'])
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    stock_logs = query.order_by(EngineerStockLog.received_at.desc()).all()
    
    return render_template('my_stock.html', 
                         stock_logs=stock_logs, 
                         status_filter=status_filter)

@app.route('/engineer/stock_log/<int:log_id>/update', methods=['POST'])
@require_role('Engineer')
def update_stock_log(log_id):
    stock_log = EngineerStockLog.query.filter_by(
        id=log_id, 
        user_id=session['user_id']
    ).first_or_404()
    
    action = request.form.get('action')
    notes = request.form.get('notes', '').strip()
    
    if action == 'use':
        if stock_log.status != 'Available':
            flash('Item is not available for use', 'error')
            return redirect(url_for('my_stock'))
        
        stock_log.status = 'Used'
        stock_log.used_at = datetime.utcnow()
        stock_log.notes = notes
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='USE_STOCK',
            details=f'Marked {stock_log.quantity} x {stock_log.stock_item.name} as used'
        )
        
        flash('Stock marked as used', 'success')
        
    elif action == 'return':
        if stock_log.status != 'Available':
            flash('Only available items can be returned', 'error')
            return redirect(url_for('my_stock'))
        
        stock_log.status = 'Returned'
        stock_log.returned_at = datetime.utcnow()
        stock_log.notes = notes
        
        stock_item = stock_log.stock_item
        stock_item.available_quantity += stock_log.quantity
        
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='RETURN_STOCK',
            details=f'Returned {stock_log.quantity} x {stock_log.stock_item.name} to inventory'
        )
        
        flash('Stock returned to inventory', 'success')
    
    db.session.commit()
    return redirect(url_for('my_stock'))

# Initialize database
@app.before_first_request
def create_tables():
    """Initialize database and create default HOD account"""
    db.create_all()
    
    # Create default HOD if doesn't exist
    if not User.query.filter_by(username='PTESPL').first():
        hod_user = User(
            username='PTESPL',
            password_hash=generate_password_hash('ptespl@123'),
            role='HOD',
            created_at=datetime.utcnow()
        )
        db.session.add(hod_user)
        
        audit_log = AuditLog(
            user_id=None,
            username='SYSTEM',
            role='SYSTEM',
            action='CREATE_DEFAULT_HOD',
            details='Created default HOD account: PTESPL',
            timestamp=datetime.utcnow()
        )
        db.session.add(audit_log)
        db.session.commit()
        
        app.logger.info('Default HOD account created: PTESPL')

if __name__ == '__main__':
    # Start background scheduler
    if not scheduler.running:
        scheduler.start()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
