from app import app, celery
from app import keystone_model as keystone

"""
@celery.task(bind=True)
def process_new_users(self, course, username, email):
    users = keystone.get_users()
    projects = keystone.get_projects(course)
    if not users or not projects:
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not get users or projects'}

    if username not in users:
        if not keystone.add_user(username, email):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not create user ' + username}

    project = course + '-' + username
    if project not in projects['students']:
        if not keystone.add_project(project):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user ' + username + ' to project ' + project}

    # We check if the role assignment already exists inside of add_role()
    if not keystone.add_role(username, project, course):
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user role for ' + username + ' to project ' + project + ' (role has likely already been added to user)'}

    return {'task': 'Process User', 'status': 'Complete', 'result': 'Processed user ' + username + ' with project ' + project}
"""
