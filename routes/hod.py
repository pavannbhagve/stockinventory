from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash
from models import db, User, StockItem, StockRequest, AuditLog, EngineerStockLog, PasswordResetToken
from utils import require_role, log_audit_action, EmailService
from datetime import datetime
import os

hod_bp = Blueprint('hod', __name__)

@hod_bp.route('/dashboard')
@require_role('HOD')
def dashboard():
    # Get dashboard statistics
    total_engineers = User.query.filter_by(role='Engineer', is_active=True).count()
    total_stock_items = StockItem.query.count()
    pending_requests = StockRequest.query.filter_by(status='Pending').count()
    recent_requests = StockRequest.query.order_by(StockRequest.requested_at.desc()).limit(5).all()
    
    # Get low stock items (less than 10 available)
    low_stock_items = StockItem.query.filter(StockItem.available_quantity < 10).all()
    
    return render_template('hod/dashboard.html', 
                         total_engineers=total_engineers,
                         total_stock_items=total_stock_items,
                         pending_requests=pending_requests,
                         recent_requests=recent_requests,
                         low_stock_items=low_stock_items)

@hod_bp.route('/engineers')
@require_role('HOD')
def engineers():
    search = request.args.get('search', '')
    if search:
        engineers_list = User.query.filter(
            User.role == 'Engineer',
            User.username.contains(search)
        ).order_by(User.created_at.desc()).all()
    else:
        engineers_list = User.query.filter_by(role='Engineer').order_by(User.created_at.desc()).all()
    
    return render_template('hod/engineers.html', engineers=engineers_list, search=search)

@hod_bp.route('/engineers/create', methods=['GET', 'POST'])
@require_role('HOD')
def create_engineer():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('hod/create_engineer.html')
        
        # Create new engineer
        engineer = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='Engineer',
            created_by=session['user_id'],
            created_at=datetime.utcnow()
        )
        
        db.session.add(engineer)
        db.session.commit()
        
        # Log the action
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='CREATE_ENGINEER',
            details=f'Created engineer account: {username}'
        )
        
        flash(f'Engineer account created successfully for {username}', 'success')
        return redirect(url_for('hod.engineers'))
    
    return render_template('hod/create_engineer.html')

@hod_bp.route('/stock')
@require_role('HOD')
def stock():
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
    
    return render_template('hod/stock.html', stock_items=stock_items, search=search)

@hod_bp.route('/stock/create', methods=['GET', 'POST'])
@require_role('HOD')
def create_stock_item():
    if request.method == 'POST':
        item_id = request.form['item_id'].strip()
        name = request.form['name'].strip()
        description = request.form['description'].strip()
        total_quantity = int(request.form['total_quantity'])
        unit = request.form['unit'].strip()
        
        # Check if item_id already exists
        if StockItem.query.filter_by(item_id=item_id).first():
            flash('Item ID already exists', 'error')
            return render_template('hod/create_stock_item.html')
        
        # Create new stock item
        stock_item = StockItem(
            item_id=item_id,
            name=name,
            description=description,
            total_quantity=total_quantity,
            available_quantity=total_quantity,  # Initially all quantity is available
            unit=unit,
            created_by=session['user_id'],
            created_at=datetime.utcnow()
        )
        
        db.session.add(stock_item)
        db.session.commit()
        
        # Log the action
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='CREATE_STOCK_ITEM',
            details=f'Created stock item: {item_id} - {name} (Qty: {total_quantity} {unit})'
        )
        
        flash(f'Stock item {item_id} created successfully', 'success')
        return redirect(url_for('hod.stock'))
    
    return render_template('hod/create_stock_item.html')

@hod_bp.route('/requests')
@require_role('HOD')
def requests():
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
    
    return render_template('hod/requests.html', 
                         requests=requests_list, 
                         status_filter=status_filter,
                         search=search)

@hod_bp.route('/requests/<int:request_id>/approve', methods=['POST'])
@require_role('HOD')
def approve_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status != 'Pending':
        flash('Request has already been processed', 'error')
        return redirect(url_for('hod.requests'))
    
    action = request.form.get('action')
    approval_notes = request.form.get('approval_notes', '').strip()
    
    if action == 'approve':
        # Check if enough stock is available
        if stock_request.requested_quantity > stock_request.stock_item.available_quantity:
            flash('Insufficient stock available', 'error')
            return redirect(url_for('hod.requests'))
        
        stock_request.status = 'Approved'
        stock_request.approved_at = datetime.utcnow()
        stock_request.approved_by = session['user_id']
        stock_request.approval_notes = approval_notes
        
        # Log the action
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
        
        # Log the action
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='DENY_REQUEST',
            details=f'Denied request #{request_id} for {stock_request.requested_quantity} x {stock_request.stock_item.name}'
        )
        
        flash('Request denied', 'info')
    
    db.session.commit()
    return redirect(url_for('hod.requests'))

@hod_bp.route('/requests/<int:request_id>/send', methods=['POST'])
@require_role('HOD')
def send_request(request_id):
    stock_request = StockRequest.query.get_or_404(request_id)
    
    if stock_request.status != 'Approved':
        flash('Request must be approved first', 'error')
        return redirect(url_for('hod.requests'))
    
    docket_number = request.form.get('docket_number', '').strip()
    
    if not docket_number:
        flash('Docket number is required', 'error')
        return redirect(url_for('hod.requests'))
    
    # Update request status and reduce available stock
    stock_request.status = 'In Transit'
    stock_request.docket_number = docket_number
    stock_request.sent_at = datetime.utcnow()
    
    # Reduce available stock
    stock_request.stock_item.available_quantity -= stock_request.requested_quantity
    
    # Log the action
    log_audit_action(
        user_id=session['user_id'],
        username=session['username'],
        role=session['role'],
        action='SEND_REQUEST',
        details=f'Sent request #{request_id} with docket: {docket_number}'
    )
    
    db.session.commit()
    flash(f'Request sent successfully with docket number: {docket_number}', 'success')
    return redirect(url_for('hod.requests'))

@hod_bp.route('/audit_logs')
@require_role('HOD')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    search = request.args.get('search', '')
    if search:
        logs = AuditLog.query.filter(
            db.or_(
                AuditLog.username.contains(search),
                AuditLog.action.contains(search),
                AuditLog.details.contains(search)
            )
        ).order_by(AuditLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    else:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    return render_template('hod/audit_logs.html', logs=logs, search=search)