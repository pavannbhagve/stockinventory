from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from models import User, AuditLog
from utils import log_audit_action
import os

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # Log successful login
            log_audit_action(
                user_id=user.id,
                username=user.username,
                role=user.role,
                action='LOGIN',
                details=f'Successful login from IP: {request.remote_addr}'
            )
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            if user.role == 'HOD':
                return redirect(url_for('hod.dashboard'))
            else:
                return redirect(url_for('engineer.dashboard'))
        else:
            # Log failed login attempt
            log_audit_action(
                user_id=None,
                username=username,
                role='Unknown',
                action='LOGIN_FAILED',
                details=f'Failed login attempt for username: {username} from IP: {request.remote_addr}'
            )
            
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    if 'user_id' in session:
        # Log logout
        log_audit_action(
            user_id=session.get('user_id'),
            username=session.get('username'),
            role=session.get('role'),
            action='LOGOUT',
            details='User logged out'
        )
    
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('auth.login'))