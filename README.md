# Stock Inventory Management System

A complete, production-ready Stock Inventory Management web application built with Flask backend and Bootstrap frontend, designed for deployment on Render with PostgreSQL.

## Features

### Role-Based Access Control
- **HOD (Head of Department)**: Full system administration
- **Engineer**: Stock viewing and request management

### Core Functionality

#### HOD Features
- Dashboard with statistics and alerts
- Create and manage engineer accounts
- Add, edit, and delete stock items
- View and process stock requests (approve/deny)
- Send approved requests with docket numbers
- Audit logs and activity tracking
- Low stock alerts
- Email escalation system (1/3/7 day alerts)

#### Engineer Features
- Personal dashboard with request statistics
- View available stock (read-only)
- Submit stock requests with notes
- Track request status (Pending/Approved/In Transit/Received)
- Mark received items and manage personal stock
- Mark items as used/returned

### Email Notifications
- Automated escalation emails for pending requests
- Color-coded urgency levels (yellow/orange/red)
- Background job monitoring with APScheduler

## Technology Stack
- **Backend**: Flask, SQLAlchemy, Flask-Migrate
- **Database**: PostgreSQL (production), SQLite (development)
- **Frontend**: Bootstrap 5, JavaScript
- **Email**: SMTP with Gmail support
- **Deployment**: Render with Gunicorn

## Installation & Setup

### Local Development

1. **Clone and Setup**
```bash
git clone <your-repo-url>
cd stock-inventory-management
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Environment Variables**
Create a `.env` file in the project root:
```env
SECRET_KEY=your-super-secret-key-here
DATABASE_URL=sqlite:///stock_inventory.db
FLASK_ENV=development

# SMTP Configuration (optional for local development)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ADMIN_RESET_EMAIL=service.aur@ptespl.com
```

3. **Initialize Database**
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

4. **Run Application**
```bash
python flask_app.py
```

The application will be available at `http://localhost:5000`

**Default HOD Login**: Username: `PTESPL`, Password: `ptespl@123`

## Render Deployment

### Step 1: Create Render Account
1. Sign up at [render.com](https://render.com)
2. Connect your GitHub account

### Step 2: Create PostgreSQL Database
1. Go to Render Dashboard
2. Click "New" → "PostgreSQL"
3. Configure database:
   - Name: `stock-inventory-db`
   - Database: `stock_inventory`
   - User: `stock_user`
   - Region: Choose closest to your location
4. Click "Create Database"
5. Note down the connection details (especially the `External Database URL`)

### Step 3: Deploy Web Service
1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Configure service:
   - **Name**: `stock-inventory-app`
   - **Root Directory**: Leave blank (if app is in root)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn flask_app:app`
   - **Instance Type**: Free tier or Starter

### Step 4: Environment Variables
In the Render Web Service dashboard, add these environment variables:

```
SECRET_KEY=your-production-secret-key-minimum-32-characters-long
DATABASE_URL=<your-render-postgresql-external-database-url>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-production-email@gmail.com
SMTP_PASS=your-gmail-app-password
ADMIN_RESET_EMAIL=service.aur@ptespl.com
```

**Important**: Use the External Database URL from your PostgreSQL service, not the Internal URL.

### Step 5: Deploy
1. Click "Create Web Service"
2. Wait for deployment to complete
3. Access your app at the provided Render URL

### Step 6: Initialize Production Database
After first deployment, you may need to run migrations:
1. Go to your Web Service dashboard
2. Open the "Shell" tab
3. Run:
```bash
python -c "from flask_app import app, db; app.app_context().push(); db.create_all()"
```

## Email Configuration

### Gmail Setup
1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password:
   - Google Account → Security → App passwords
   - Select "Mail" and your device
   - Use the generated 16-character password as `SMTP_PASS`

### Email Features
- **Escalation Alerts**: Automatic emails for overdue requests
- **Color Coding**: Yellow (1 day), Orange (3 days), Red (7+ days)
- **Background Jobs**: Runs every 6 hours to check pending requests

## Database Schema

### Users Table
- `id`: Primary key
- `username`: Unique username
- `password_hash`: Hashed password
- `role`: 'HOD' or 'Engineer'
- `is_active`: Account status
- `created_at`: Creation timestamp
- `created_by`: Creator reference

### Stock Items Table
- `id`: Primary key
- `item_id`: Unique item identifier
- `name`: Item name
- `description`: Item description
- `total_quantity`: Total stock
- `available_quantity`: Available stock
- `unit`: Unit of measurement
- `created_by`: Creator reference

### Stock Requests Table
- `id`: Primary key
- `user_id`: Engineer reference
- `stock_item_id`: Stock item reference
- `requested_quantity`: Requested amount
- `status`: Request status
- `docket_number`: Shipping docket
- `requested_at`: Request timestamp
- `approved_at`: Approval timestamp
- `sent_at`: Shipment timestamp
- `received_at`: Receipt timestamp

## API Endpoints

### Authentication
- `GET /login`: Login page
- `POST /login`: Process login
- `GET /logout`: Logout user

### HOD Routes
- `GET /hod/dashboard`: HOD dashboard
- `GET /hod/engineers`: Engineer management
- `POST /hod/engineers/create`: Create engineer
- `GET /hod/stock`: Stock management
- `POST /hod/stock/create`: Add stock item
- `GET /hod/requests`: View all requests
- `POST /hod/requests/<id>/approve`: Approve/deny request
- `POST /hod/requests/<id>/send`: Send with docket

### Engineer Routes
- `GET /engineer/dashboard`: Engineer dashboard
- `GET /engineer/stock`: View available stock
- `GET /engineer/request_stock`: Request stock form
- `POST /engineer/request_stock`: Submit request
- `GET /engineer/my_requests`: View own requests
- `POST /engineer/requests/<id>/receive`: Mark received
- `GET /engineer/my_stock`: Personal stock log
- `POST /engineer/stock_log/<id>/update`: Update stock status

## Business Logic

### Stock Request Workflow
1. **Engineer Request**: Engineer selects item and quantity
2. **HOD Review**: HOD approves or denies request
3. **HOD Send**: HOD enters docket number and marks as sent
4. **Stock Reduction**: Available stock decreases when sent
5. **Engineer Receive**: Engineer marks as received
6. **Personal Stock**: Item added to engineer's personal inventory

### Escalation System
- **Day 1**: Yellow alert email to admin
- **Day 3**: Orange alert email to admin  
- **Day 7+**: Red urgent alert email to admin
- Applies to both pending approval and approved-but-not-sent requests

### Stock Management
- **Total Quantity**: Never changes unless HOD edits item
- **Available Quantity**: Decreases when HOD sends, increases when engineer returns
- **Allocation Tracking**: Personal stock logs track engineer inventory

## Security Features

- Password hashing with Werkzeug
- Session-based authentication
- Role-based access control
- CSRF protection (Flask built-in)
- SQL injection prevention (SQLAlchemy ORM)
- Audit logging for all actions

## Monitoring & Maintenance

### Logs
- Application logs via Python logging
- Audit logs in database
- All user actions tracked with timestamps

### Background Jobs
- APScheduler runs escalation checks every 6 hours
- Automatic email notifications
- Error handling and logging

### Database Maintenance
```bash
# Create new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback migration
flask db downgrade
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify DATABASE_URL format
   - Ensure PostgreSQL service is running
   - Check network connectivity

2. **Email Not Sending**
   - Verify SMTP credentials
   - Check firewall settings
   - Test with Gmail App Password

3. **Permission Denied**
   - Check user roles in database
   - Verify session data
   - Clear browser cookies

4. **Background Jobs Not Running**
   - Check APScheduler logs
   - Verify Render worker process
   - Monitor job execution

### Database Reset (Development Only)
```bash
rm instance/stock_inventory.db  # SQLite only
flask db init
flask db migrate -m "Fresh start"
flask db upgrade
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions:
1. Check this README
2. Review application logs
3. Contact: service.aur@ptespl.com

---

**Important Notes for Render Deployment:**
- Use PostgreSQL External Database URL, not Internal
- Set all environment variables before first deployment
- Monitor logs during initial deployment
- Default HOD account is created automatically on first run
- Background jobs require web service to be running (included in main app)