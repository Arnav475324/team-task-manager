import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# CONFIGURATION & INITIALIZATION
# ==========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key')
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'team_task_manager.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', f'sqlite:///{db_path}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# DATABASE MODELS
# ==========================================

class ProjectMember(db.Model):
    __tablename__ = 'project_members'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('project_id', 'user_id', name='uix_project_member'),)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='Member')
    is_suspended = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_projects = db.relationship('Project', backref='owner', lazy=True)
    tasks_created = db.relationship('Task', foreign_keys='Task.created_by_id', backref='creator', lazy=True)
    membership = db.relationship('ProjectMember', backref='user', lazy=True)
    task_assignments = db.relationship('TaskAssignee', backref='user', lazy=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tasks = db.relationship('Task', backref='project', lazy=True, cascade='all, delete')
    members = db.relationship('ProjectMember', backref='project', lazy=True, cascade='all, delete')

class TaskAssignee(db.Model):
    __tablename__ = 'task_assignees'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('task_id', 'user_id', name='uix_task_assignee'),)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(24), nullable=False, default='To Do')
    priority = db.Column(db.String(16), nullable=False, default='Medium')
    due_date = db.Column(db.Date, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    assignees = db.relationship('TaskAssignee', backref='task', lazy=True, cascade='all, delete')

with app.app_context():
    db.create_all()


# ==========================================
# UTILITY FUNCTIONS & DECORATORS
# ==========================================

def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


def login_required(view):
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def admin_required(view):
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user.role != 'Admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def project_member_required(project_id):
    user = current_user()
    if not user:
        return False
    project = Project.query.get(project_id)
    if not project:
        return False
    if project.owner_id == user.id:
        return True
    return ProjectMember.query.filter_by(project_id=project_id, user_id=user.id).first() is not None


def format_overdue(task):
    if task.due_date and task.due_date < date.today() and task.status != 'Done':
        return True
    return False

TASK_STATUSES = ['To Do', 'In Progress', 'Review', 'Help Needed', 'Done']

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# ==========================================
# PUBLIC & AUTHENTICATION ROUTES
# ==========================================

@app.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user():
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('signup'))
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.', 'error')
            return redirect(url_for('signup'))
        is_admin = User.query.count() == 0
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role='Admin' if is_admin else 'Member'
        )
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        flash('Account created successfully.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user():
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
        if not user or not user.check_password(password):
            flash('Invalid credentials.', 'error')
            return redirect(url_for('login'))
        if user.is_suspended:
            admin = User.query.filter_by(role='Admin').first()
            admin_email = admin.email if admin else 'admin@example.com'
            flash(f'Your account is under review and cannot be accessed. Contact admin at {admin_email} to reopen it.', 'error')
            return redirect(url_for('login'))
        session['user_id'] = user.id
        flash('Welcome back!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# ==========================================
# DASHBOARD ROUTE
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    if user.role == 'Admin':
        projects = Project.query.order_by(Project.created_at.desc()).all()
    else:
        projects = Project.query.join(ProjectMember).filter(ProjectMember.user_id == user.id).order_by(Project.created_at.desc()).all()
    # Get tasks assigned to the current user
    assigned_tasks = Task.query.join(TaskAssignee).filter(TaskAssignee.user_id == user.id).filter(Task.status != 'Done').order_by(Task.due_date.asc().nulls_last()).all()
    all_tasks = Task.query.filter(Task.status != 'Done').order_by(Task.due_date.asc().nulls_last()).all()
    overdue = [task for task in all_tasks if format_overdue(task)]
    status_counts = {
        'To Do': Task.query.filter_by(status='To Do').count(),
        'In Progress': Task.query.filter_by(status='In Progress').count(),
        'Review': Task.query.filter_by(status='Review').count(),
        'Help Needed': Task.query.filter_by(status='Help Needed').count(),
        'Done': Task.query.filter_by(status='Done').count(),
    }
    return render_template('dashboard.html', user=user, projects=projects, assigned_tasks=assigned_tasks, overdue=overdue, status_counts=status_counts)

# ==========================================
# PROJECT MANAGEMENT ROUTES
# ==========================================

@app.route('/projects/new', methods=['GET', 'POST'])
@admin_required
def create_project():
    user = current_user()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name:
            flash('Project name is required.', 'error')
            return redirect(url_for('create_project'))
        project = Project(name=name, description=description, owner_id=user.id)
        db.session.add(project)
        db.session.commit()
        member = ProjectMember(project_id=project.id, user_id=user.id)
        db.session.add(member)
        db.session.commit()
        flash('Project created successfully.', 'success')
        return redirect(url_for('project_detail', project_id=project.id))
    return render_template('project_form.html')

@app.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    user = current_user()
    if project.owner_id != user.id and user.role != 'Admin':
        flash('Only the project owner or an admin can edit this project.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name:
            flash('Project name is required.', 'error')
            return redirect(url_for('edit_project', project_id=project.id))
        project.name = name
        project.description = description
        db.session.commit()
        flash('Project updated successfully.', 'success')
        return redirect(url_for('project_detail', project_id=project.id))
    return render_template('project_form.html', project=project, edit=True)

@app.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    user = current_user()
    is_member = project_member_required(project_id)
    if not is_member:
        flash('You must be a member of this project to view it.', 'error')
        return redirect(url_for('dashboard'))
    members = [member.user for member in project.members]
    tasks = Task.query.filter_by(project_id=project.id).order_by(Task.due_date.asc().nulls_last()).all()
    active_tasks = [task for task in tasks if task.status != 'Done']
    completed_tasks = [task for task in tasks if task.status == 'Done']
    return render_template('project_detail.html', project=project, members=members, tasks=active_tasks, completed_tasks=completed_tasks, user=user)

@app.route('/projects/<int:project_id>/team', methods=['POST'])
@login_required
def add_team_member(project_id):
    project = Project.query.get_or_404(project_id)
    user = current_user()
    if project.owner_id != user.id and user.role != 'Admin':
        flash('Only project owner or admin can add members.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    username = request.form.get('username', '').strip()
    member = User.query.filter_by(username=username).first()
    if not member:
        flash('User not found.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    if ProjectMember.query.filter_by(project_id=project.id, user_id=member.id).first():
        flash('This user is already a member.', 'warning')
        return redirect(url_for('project_detail', project_id=project.id))
    db.session.add(ProjectMember(project_id=project.id, user_id=member.id))
    db.session.commit()
    flash(f'{member.username} added to the team.', 'success')
    return redirect(url_for('project_detail', project_id=project.id))

@app.route('/projects/<int:project_id>/team/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_team_member(project_id, user_id):
    project = Project.query.get_or_404(project_id)
    user = current_user()
    if project.owner_id != user.id and user.role != 'Admin':
        flash('Only the project owner or an admin can remove team members.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    if project.owner_id == user_id:
        flash('The project owner cannot be removed from the team.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    member = ProjectMember.query.filter_by(project_id=project.id, user_id=user_id).first()
    if not member:
        flash('Team member not found.', 'error')
        return redirect(url_for('project_detail', project_id=project.id))
    db.session.delete(member)
    db.session.commit()
    flash('Team member removed successfully.', 'success')
    return redirect(url_for('project_detail', project_id=project.id))

# ==========================================
# TASK MANAGEMENT ROUTES
# ==========================================

@app.route('/projects/<int:project_id>/tasks/new', methods=['GET', 'POST'])
@login_required
def create_task(project_id):
    project = Project.query.get_or_404(project_id)
    user = current_user()
    # Only admins and project owner can create tasks
    if user.role != 'Admin' and project.owner_id != user.id:
        flash('Only admins and project owner can add tasks.', 'error')
        return redirect(url_for('project_detail', project_id=project_id))
    if not project_member_required(project_id):
        flash('You must be part of the project to add tasks.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', 'To Do')
        priority = request.form.get('priority', 'Medium')
        due_date = request.form.get('due_date', '').strip()
        assigned_usernames = request.form.getlist('assigned_to')
        if not title:
            flash('Task title is required.', 'error')
            return redirect(url_for('create_task', project_id=project.id))
        assigned_users = []
        if assigned_usernames:
            for username in assigned_usernames:
                if username:
                    assigned_user = User.query.filter_by(username=username).first()
                    if not assigned_user:
                        flash(f'User {username} not found.', 'error')
                        return redirect(url_for('create_task', project_id=project.id))
                    if not ProjectMember.query.filter_by(project_id=project.id, user_id=assigned_user.id).first():
                        flash(f'{assigned_user.username} must be a project team member.', 'error')
                        return redirect(url_for('create_task', project_id=project.id))
                    assigned_users.append(assigned_user)
        due_date_obj = None
        try:
            if due_date:
                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid due date format.', 'error')
            return redirect(url_for('create_task', project_id=project.id))
        task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date_obj,
            project_id=project.id,
            created_by_id=user.id
        )
        db.session.add(task)
        db.session.flush()
        for assigned_user in assigned_users:
            db.session.add(TaskAssignee(task_id=task.id, user_id=assigned_user.id))
        db.session.commit()
        flash('Task created successfully.', 'success')
        return redirect(url_for('project_detail', project_id=project.id))
    members = [member.user for member in project.members]
    return render_template('task_form.html', project=project, members=members)

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = current_user()
    if not project_member_required(task.project_id):
        flash('You must be part of the project to edit this task.', 'error')
        return redirect(url_for('dashboard'))
    if not (user.role == 'Admin' or task.project.owner_id == user.id or task.created_by_id == user.id):
        flash('Only the task creator, project owner, or an admin can edit task details.', 'error')
        return redirect(url_for('project_detail', project_id=task.project_id))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', task.status)
        priority = request.form.get('priority', task.priority)
        due_date = request.form.get('due_date', '').strip()
        assigned_usernames = request.form.getlist('assigned_to')
        if not title:
            flash('Task title is required.', 'error')
            return redirect(url_for('edit_task', task_id=task.id))
        assigned_users = []
        if assigned_usernames:
            for username in assigned_usernames:
                if username:
                    assigned_user = User.query.filter_by(username=username).first()
                    if not assigned_user:
                        flash(f'User {username} not found.', 'error')
                        return redirect(url_for('edit_task', task_id=task.id))
                    if not ProjectMember.query.filter_by(project_id=task.project_id, user_id=assigned_user.id).first():
                        flash(f'{assigned_user.username} must be a project team member.', 'error')
                        return redirect(url_for('edit_task', task_id=task.id))
                    assigned_users.append(assigned_user)
        due_date_obj = None
        try:
            if due_date:
                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid due date format.', 'error')
            return redirect(url_for('edit_task', task_id=task.id))
        task.title = title
        task.description = description
        task.status = status
        task.priority = priority
        task.due_date = due_date_obj
        # Update completed_at when status changes to Done
        if status == 'Done' and task.status != 'Done':
            task.completed_at = datetime.utcnow()
        elif status != 'Done':
            task.completed_at = None
        # Update assignees
        TaskAssignee.query.filter_by(task_id=task.id).delete()
        for assigned_user in assigned_users:
            db.session.add(TaskAssignee(task_id=task.id, user_id=assigned_user.id))
        db.session.commit()
        flash('Task updated successfully.', 'success')
        return redirect(url_for('project_detail', project_id=task.project_id))
    members = [member.user for member in task.project.members]
    return render_template('task_form.html', project=task.project, members=members, task=task, edit=True)

@app.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = current_user()
    if not project_member_required(task.project_id):
        flash('You must be part of the project to update tasks.', 'error')
        return redirect(url_for('dashboard'))
    can_full_update = (task.created_by_id == user.id or 
                       task.project.owner_id == user.id or 
                       user.role == 'Admin')
    # Check if user is assigned to the task
    is_assigned = TaskAssignee.query.filter_by(task_id=task.id, user_id=user.id).first() is not None
    can_status_update = (is_assigned and user.role != 'Admin')
    if not can_full_update and not can_status_update:
        flash('You do not have permission to update this task.', 'error')
        return redirect(url_for('project_detail', project_id=task.project_id))
    status = request.form.get('status', task.status)
    if can_status_update:
        if status not in ['Done', 'Help Needed']:
            flash('You may only mark the task as Done or Help Needed.', 'error')
            return redirect(url_for('project_detail', project_id=task.project_id))
        task.status = status
        if status == 'Done' and task.status != 'Done':
            task.completed_at = datetime.utcnow()
        elif status != 'Done':
            task.completed_at = None
        db.session.commit()
        flash('Task status updated.', 'success')
        return redirect(url_for('project_detail', project_id=task.project_id))
    task.status = status
    if status == 'Done' and task.status != 'Done':
        task.completed_at = datetime.utcnow()
    elif status != 'Done':
        task.completed_at = None
    db.session.commit()
    flash('Task status updated.', 'success')
    return redirect(url_for('project_detail', project_id=task.project_id))

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    user = current_user()
    # Only admin and project owner can delete tasks
    can_delete = (task.project.owner_id == user.id or user.role == 'Admin')
    if not can_delete:
        flash('You do not have permission to delete this task.', 'error')
        return redirect(url_for('project_detail', project_id=task.project_id))
    project_id = task.project_id
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted successfully.', 'success')
    return redirect(url_for('project_detail', project_id=project_id))

# ==========================================
# ADMIN DASHBOARD & MANAGEMENT ROUTES
# ==========================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    users = User.query.all()
    projects = Project.query.all()
    tasks = Task.query.all()
    user_count = len(users)
    project_count = len(projects)
    task_count = len(tasks)
    completed_tasks = len([t for t in tasks if t.status == 'Done'])
    return render_template('admin_dashboard.html', 
                         users=users, 
                         projects=projects, 
                         user_count=user_count,
                         project_count=project_count,
                         task_count=task_count,
                         completed_tasks=completed_tasks)

@app.route('/admin/users', methods=['GET'])
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def update_user_role(user_id):
    user = User.query.get_or_404(user_id)
    current = current_user()
    if current.id == user_id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin_users'))
    new_role = request.form.get('role', '').strip()
    if new_role not in ['Admin', 'Member']:
        flash('Invalid role.', 'error')
        return redirect(url_for('admin_users'))
    user.role = new_role
    db.session.commit()
    flash(f'User {user.username} role updated to {new_role}.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/suspend', methods=['POST'])
@admin_required
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    current = current_user()
    if current.id == user_id:
        flash('You cannot suspend your own account.', 'error')
        return redirect(url_for('admin_users'))
    user.is_suspended = True
    db.session.commit()
    flash(f'User {user.username} account has been suspended.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/unsuspend', methods=['POST'])
@admin_required
def unsuspend_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_suspended = False
    db.session.commit()
    flash(f'User {user.username} account has been reactivated.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    current = current_user()
    if current.id == user_id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))
    # Prevent deleting users who own projects or created tasks to avoid FK issues
    if Project.query.filter_by(owner_id=user.id).first():
        flash('Cannot delete a user who owns projects. Transfer ownership first.', 'error')
        return redirect(url_for('admin_users'))
    if Task.query.filter_by(created_by_id=user.id).first():
        flash('Cannot delete a user who created tasks. Reassign or remove those tasks first.', 'error')
        return redirect(url_for('admin_users'))

    username = user.username
    # Remove direct associations that reference the user to avoid nullable FK updates
    TaskAssignee.query.filter_by(user_id=user.id).delete()
    ProjectMember.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'User {username} deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/projects', methods=['GET'])
@admin_required
def admin_projects():
    projects = Project.query.all()
    return render_template('admin_projects.html', projects=projects)

@app.route('/admin/projects/<int:project_id>/delete', methods=['POST'])
@admin_required
def admin_delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    name = project.name
    db.session.delete(project)
    db.session.commit()
    flash(f'Project {name} deleted successfully.', 'success')
    return redirect(url_for('admin_projects'))

# ==========================================
# API ROUTES (For async operations/frontend)
# ==========================================

@app.route('/api/projects', methods=['GET', 'POST'])
def api_projects():
    if request.method == 'GET':
        projects = Project.query.all()
        return jsonify([{
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'owner': project.owner.username,
            'created_at': project.created_at.isoformat()
        } for project in projects])
    data = request.get_json(force=True)
    name = data.get('name')
    owner_id = data.get('owner_id')
    if not name or not owner_id:
        return jsonify({'error': 'name and owner_id are required'}), 400
    owner = User.query.get(owner_id)
    if not owner:
        return jsonify({'error': 'owner not found'}), 404
    project = Project(name=name, description=data.get('description', ''), owner_id=owner.id)
    db.session.add(project)
    db.session.commit()
    db.session.add(ProjectMember(project_id=project.id, user_id=owner.id))
    db.session.commit()
    return jsonify({'id': project.id, 'name': project.name}), 201

@app.route('/api/tasks', methods=['GET', 'POST'])
def api_tasks():
    if request.method == 'GET':
        tasks = Task.query.all()
        task_list = []
        for task in tasks:
            assignees = [a.user.username for a in task.assignees]
            task_list.append({
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'project': task.project.name,
                'assigned_to': assignees
            })
        return jsonify(task_list)
    data = request.get_json(force=True)
    title = data.get('title')
    project_id = data.get('project_id')
    if not title or not project_id:
        return jsonify({'error': 'title and project_id are required'}), 400
    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': 'project not found'}), 404
    assigned_user_ids = data.get('assigned_to_ids', [])
    assigned_users = []
    for user_id in assigned_user_ids:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': f'assigned user {user_id} not found'}), 404
        assigned_users.append(user)
    task = Task(
        title=title,
        description=data.get('description', ''),
        status=data.get('status', 'To Do'),
        priority=data.get('priority', 'Medium'),
        due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
        project_id=project.id,
        created_by_id=data.get('created_by_id', project.owner_id)
    )
    db.session.add(task)
    db.session.flush()
    for user in assigned_users:
        db.session.add(TaskAssignee(task_id=task.id, user_id=user.id))
    db.session.commit()
    return jsonify({'id': task.id, 'title': task.title}), 201

@app.route('/api/tasks/<int:task_id>', methods=['PATCH'])
def api_update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json(force=True)
    if data.get('status'):
        task.status = data['status']
        if data['status'] == 'Done':
            task.completed_at = datetime.utcnow()
        else:
            task.completed_at = None
    if data.get('priority'):
        task.priority = data['priority']
    if 'assigned_to_ids' in data:
        TaskAssignee.query.filter_by(task_id=task.id).delete()
        for user_id in data['assigned_to_ids']:
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': f'user {user_id} not found'}), 404
            db.session.add(TaskAssignee(task_id=task.id, user_id=user.id))
    db.session.commit()
    assignees = [a.user.username for a in task.assignees]
    return jsonify({'success': True, 'task': {'id': task.id, 'status': task.status, 'assigned_to': assignees}})

@app.route('/api/team/<int:project_id>', methods=['GET', 'POST'])
def api_team(project_id):
    project = Project.query.get_or_404(project_id)
    if request.method == 'GET':
        return jsonify([member.user.username for member in project.members])
    data = request.get_json(force=True)
    username = data.get('username')
    if not username:
        return jsonify({'error': 'username is required'}), 400
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'user not found'}), 404
    if ProjectMember.query.filter_by(project_id=project.id, user_id=user.id).first():
        return jsonify({'error': 'already a member'}), 400
    db.session.add(ProjectMember(project_id=project.id, user_id=user.id))
    db.session.commit()
    return jsonify({'success': True, 'username': username}), 201

@app.route('/api/project/<int:project_id>/search-members', methods=['GET'])
def search_members(project_id):
    project = Project.query.get_or_404(project_id)
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    # Search project team members by username prefix and return recommendations only after typing
    matching_users = User.query.join(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        User.username.ilike(f'{query}%')
    ).order_by(User.username).all()

    return jsonify([
        {'username': user.username, 'id': user.id}
        for user in matching_users
    ])

@app.context_processor
def utility_processor():
    return {'current_user': current_user, 'format_overdue': format_overdue}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
