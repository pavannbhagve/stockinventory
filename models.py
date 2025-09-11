from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets

# Import db from flask_app to avoid circular imports
from flask import current_app
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Engineer')  # 'HOD' or 'Engineer'
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
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
    
    # Relationships
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
    # Status options: Pending, Approved, Denied, Sent, In Transit, Received
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
        return f'<StockRequest {self.id}: {self.requested_quantity} x {self.stock_item.name}>'
    
    @property
    def pending_days(self):
        """Calculate how many days this request has been pending"""
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
    # Status options: Available, Used, Returned
    notes = db.Column(db.Text)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)
    request_id = db.Column(db.Integer, db.ForeignKey('stock_requests.id'))
    
    def __repr__(self):
        return f'<EngineerStockLog {self.id}: {self.quantity} x {self.stock_item.name}>'

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
    
    def __repr__(self):
        return f'<PasswordResetToken {self.id}: User {self.user_id}>'