from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, StockItem, StockRequest, EngineerStockLog
from utils import require_role, log_audit_action
from datetime import datetime

engineer_bp = Blueprint('engineer', __name__)

@engineer_bp.route('/dashboard')
@require_role('Engineer')
def dashboard():
    # Get dashboard statistics
    total_requests = StockRequest.query.filter_by(user_id=session['user_id']).count()
    pending_requests = StockRequest.query.filter_by(
        user_id=session['user_id'], 
        status='Pending'
    ).count()
    in_transit_requests = StockRequest.query.filter_by(
        user_id=session['user_id'], 
        status='In Transit'
    ).count()
    
    # Get recent requests
    recent_requests = StockRequest.query.filter_by(
        user_id=session['user_id']
    ).order_by(StockRequest.requested_at.desc()).limit(5).all()
    
    # Get personal stock summary
    personal_stock_count = EngineerStockLog.query.filter_by(
        user_id=session['user_id'],
        status='Available'
    ).count()
    
    return render_template('engineer/dashboard.html',
                         total_requests=total_requests,
                         pending_requests=pending_requests,
                         in_transit_requests=in_transit_requests,
                         recent_requests=recent_requests,
                         personal_stock_count=personal_stock_count)

@engineer_bp.route('/stock')
@require_role('Engineer')
def stock():
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
    
    return render_template('engineer/stock.html', stock_items=stock_items, search=search)

@engineer_bp.route('/request_stock', methods=['GET', 'POST'])
@require_role('Engineer')
def request_stock():
    if request.method == 'POST':
        stock_item_id = int(request.form['stock_item_id'])
        requested_quantity = int(request.form['requested_quantity'])
        notes = request.form.get('notes', '').strip()
        
        stock_item = StockItem.query.get_or_404(stock_item_id)
        
        # Validate quantity
        if requested_quantity <= 0:
            flash('Requested quantity must be greater than 0', 'error')
            return redirect(url_for('engineer.request_stock'))
        
        if requested_quantity > stock_item.available_quantity:
            flash(f'Only {stock_item.available_quantity} {stock_item.unit} available', 'error')
            return redirect(url_for('engineer.request_stock'))
        
        # Create stock request
        stock_request = StockRequest(
            user_id=session['user_id'],
            stock_item_id=stock_item_id,
            requested_quantity=requested_quantity,
            notes=notes,
            requested_at=datetime.utcnow()
        )
        
        db.session.add(stock_request)
        db.session.commit()
        
        # Log the action
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='REQUEST_STOCK',
            details=f'Requested {requested_quantity} x {stock_item.name} ({stock_item.item_id})'
        )
        
        flash('Stock request submitted successfully', 'success')
        return redirect(url_for('engineer.my_requests'))
    
    stock_items = StockItem.query.filter(StockItem.available_quantity > 0).order_by(StockItem.name).all()
    return render_template('engineer/request_stock.html', stock_items=stock_items)

@engineer_bp.route('/my_requests')
@require_role('Engineer')
def my_requests():
    status_filter = request.args.get('status', 'all')
    
    query = StockRequest.query.filter_by(user_id=session['user_id'])
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    requests_list = query.order_by(StockRequest.requested_at.desc()).all()
    
    return render_template('engineer/my_requests.html', 
                         requests=requests_list, 
                         status_filter=status_filter)

@engineer_bp.route('/requests/<int:request_id>/receive', methods=['POST'])
@require_role('Engineer')
def receive_request(request_id):
    stock_request = StockRequest.query.filter_by(
        id=request_id, 
        user_id=session['user_id']
    ).first_or_404()
    
    if stock_request.status != 'In Transit':
        flash('Request is not in transit', 'error')
        return redirect(url_for('engineer.my_requests'))
    
    # Update request status
    stock_request.status = 'Received'
    stock_request.received_at = datetime.utcnow()
    
    # Add to engineer's personal stock log
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
    
    # Log the action
    log_audit_action(
        user_id=session['user_id'],
        username=session['username'],
        role=session['role'],
        action='RECEIVE_STOCK',
        details=f'Received {stock_request.requested_quantity} x {stock_request.stock_item.name} from request #{request_id}'
    )
    
    db.session.commit()
    flash('Stock received and added to your inventory', 'success')
    return redirect(url_for('engineer.my_requests'))

@engineer_bp.route('/my_stock')
@require_role('Engineer')
def my_stock():
    status_filter = request.args.get('status', 'all')
    
    query = EngineerStockLog.query.filter_by(user_id=session['user_id'])
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    stock_logs = query.order_by(EngineerStockLog.received_at.desc()).all()
    
    return render_template('engineer/my_stock.html', 
                         stock_logs=stock_logs, 
                         status_filter=status_filter)

@engineer_bp.route('/stock_log/<int:log_id>/update', methods=['POST'])
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
            return redirect(url_for('engineer.my_stock'))
        
        stock_log.status = 'Used'
        stock_log.used_at = datetime.utcnow()
        stock_log.notes = notes
        
        # Reduce global available stock as well
        stock_item = stock_log.stock_item
        stock_item.available_quantity = max(0, stock_item.available_quantity - stock_log.quantity)
        
        # Log the action
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
            return redirect(url_for('engineer.my_stock'))
        
        stock_log.status = 'Returned'
        stock_log.returned_at = datetime.utcnow()
        stock_log.notes = notes
        
        # Return to global available stock
        stock_item = stock_log.stock_item
        stock_item.available_quantity += stock_log.quantity
        
        # Log the action
        log_audit_action(
            user_id=session['user_id'],
            username=session['username'],
            role=session['role'],
            action='RETURN_STOCK',
            details=f'Returned {stock_log.quantity} x {stock_log.stock_item.name} to inventory'
        )
        
        flash('Stock returned to inventory', 'success')
    
    db.session.commit()
    return redirect(url_for('engineer.my_stock'))