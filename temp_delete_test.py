from app import app, db, User, Project, ProjectMember, Task, TaskAssignee

with app.app_context():
    admin = User.query.filter_by(username='testadmin').first()
    target = User.query.filter_by(username='bob').first()
    print('Admin id, target id:', admin.id if admin else None, target.id if target else None)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id
    resp = client.post(f'/admin/users/{target.id}/delete')
    print('Delete response status:', resp.status_code)
    # List remaining users
    users = [u.username for u in User.query.order_by(User.id).all()]
    print('Users after delete:', users)
