from app import app, login, celery
from flask_login import UserMixin
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions
from keystoneclient.v3 import client as keystoneclient
from keystoneclient import utils
from app.db_model import Course, Schedule
from app.exceptions import ClassInSession
import pprint
import re
import json
import datetime
import pytz
import random
import string

class OpenStackUser(UserMixin):
    id = None
    is_authenticated = False
    is_active = True
    is_anonymous = False
    auth = None
    osession = None
    project = None
    course = None

    def login(self, id, password, course_id):
        self.id = id
        self.project = 'INFR-' + course_id + '-Instructors'
        self.course = 'INFR-' + course_id
    
        auth = v3.Password(auth_url=app.config['OS_ENDPOINT_URL'], 
                           username=id,
                           password=password,
                           project_name=self.project,
                           user_domain_name=app.config['OS_DOMAIN'],
                           project_domain_name=app.config['OS_PROJECT_DOMAIN'])

        try:
            sess = session.Session(auth=auth)
            auth.get_token(session=sess)
        except exceptions.http.Unauthorized as e:
            raise exceptions.http.Unauthorized(e)
        
        try:
            self.check_if_course_running()
        except ClassInSession as e:
            raise ClassInSession(e.start_time, e.end_time, e.message)

        self.is_authenticated = True
        login.users[id] = self
    

    def check_if_course_running(self):
        from app.models import convert_utc_to_eastern  # Output the time in EST/EDT rather than UTC, which is how time is stored in the DB
        weekday = datetime.datetime.today().weekday()
        current_time = datetime.datetime.utcnow().timestamp() * 1000

        try:
            check = Course.query.filter_by(course=self.course).first()
        except AttributeError:
            check = None
        
        tz = pytz.timezone('America/Toronto')
        schedule = Schedule.query.all()
        for s in schedule:
            if s.weekday == weekday:
                if s.start_time < current_time < s.end_time:
                    if hasattr(check, 'id'):
                        if not s.course_id == check.id:
                            shitter_start = datetime.datetime.fromtimestamp(s.start_time/1000).astimezone(tz).strftime('%-I:%M %p')
                            shitter_end = datetime.datetime.fromtimestamp(s.end_time/1000).astimezone(tz).strftime('%-I:%M %p')
                            raise ClassInSession(start_time=shitter_start, end_time=shitter_end, message=None)
                    else:
                        shitter_start = datetime.datetime.fromtimestamp(s.start_time/1000).astimezone(tz).strftime('%-I:%M %p')
                        shitter_end = datetime.datetime.fromtimestamp(s.end_time/1000).astimezone(tz).strftime('%-I:%M %p')
                        raise ClassInSession(start_time=shitter_start, end_time=shitter_end, message=None)


"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
              K    E    Y    S    T    O    N    E

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
 
def get_admin_session():
    auth = v3.Password(auth_url=app.config['OS_ENDPOINT_URL'], 
                       username=app.config['OS_ADMIN_USERNAME'],
                       password=app.config['OS_ADMIN_PASSWORD'],
                       project_name=app.config['OS_ADMIN_PROJECT'],
                       user_domain_name=app.config['OS_DOMAIN'],
                       project_domain_name=app.config['OS_PROJECT_DOMAIN'])
    return session.Session(auth=auth)


def get_keystone_session():
    return keystoneclient.Client(session=get_admin_session())


def get_users():
    ks = get_keystone_session()
    users = {}  
    for u in ks.users.list():
        if '100' in u.name or '@' in u.name:
            users[u.name] = u.id
    return users


def get_course_users(course):
    print('INSIDE GET COURSE USERS ============================')
    ks = get_keystone_session()
    projects = get_projects(course)
    instructor_project_name = list(projects['instructors'].keys())[0]
    instructor_project_id = list(projects['instructors'].values())[0]
    user_list = ks.users.list()
    role_assignments_list = ks.role_assignments.list(role=utils.find_resource(ks.roles, 'user').id)
    
    role_dict = {}
    for role in role_assignments_list:
        # Filter out any "Group" projects
        if 'roup' not in utils.find_resource(ks.projects, role.scope['project']['id']).name:
            role_dict[role.user['id']] = role.scope['project']['id']
    
    user_dict = {}
    for user in user_list:
        if '100' in user.name or '@' in user.name:
            if user.id in role_dict:
                project_name = course + '-' + user.name
                if project_name in projects['students']:
                    if role_dict[user.id] == projects['students'][project_name]:
                        user_dict[user.name] = project_name
                else:
                    if role_dict[user.id] == instructor_project_id:
                        user_dict[user.name] = instructor_project_name

    return dict(sorted(user_dict.items())) # Return list alphabetically


def get_username_from_id(user_id):
    ks = get_keystone_session()
    return utils.find_resource(ks.users, user_id).name

def get_user_id(username):
    ks = get_keystone_session()
    try:
        return utils.find_resource(ks.users, username).id
    except:
        return None


def get_user_email(username):
    ks = get_keystone_session()
    return utils.find_resource(ks.users, username).email


def get_username_from_email(email):
    ks = get_keystone_session()
    for k in ks.users.list():
        if k.email == email:
            return k.name
    return None


def get_projects(course):
    ks = get_keystone_session()
    projects = {'instructors': {}, 'students': {}, 'groups': {}}
    for p in ks.projects.list():
        if course in p.name:
            if 'nstructor' in p.name:
                projects['instructors'][p.name] = p.id
            elif 'roup' in p.name:
                projects['groups'][p.name] = p.id
            else:
                projects['students'][p.name] = p.id
    return projects


def get_project_info(course):
    ks = get_keystone_session()
    projects = []
    for p in ks.projects.list():
        if course in p.name:
            projects.append(p)
    return projects


@celery.task(bind=True)
def enable_disable_projects(course, enable, ignore_instructors=True):
    ks = get_keystone_session()
    for project in get_project_info(course):
        if ignore_instructors and 'nstructors' in project.name:
            continue
        if not project.enabled == enable:
            ks.projects.update(project.id, enabled=enable)


def get_project_id(project):
    ks = get_keystone_session()
    return utils.find_resource(ks.projects, project).id


def get_project_role(username, project):
    # Check if the user has the 'user' role in a given project
    ks = get_keystone_session()
    
    try:
        user_id = utils.find_resource(ks.users, username).id
    except keystoneclient.exceptions.CommandError:
        return False
    
    user_role_id = utils.find_resource(ks.roles, 'user').id
    project_id = get_project_id(project)
    role = ks.role_assignments.list(user=user_id, role=user_role_id, project=project_id)

    try:
        if role[0].scope['project']['id'] == project_id:
            return True
        else:
            return False
    except IndexError:  # "role" value is returned as empty, meaning user doesn't exist period
        return False


def add_user(username, email):
    from app.email_model import send_password_reset_info
    keystone = get_keystone_session()
    success = keystone.users.create(name=username,
                email=email,
                domain='default',
                password='cisco123',
                description='Auto-generated Account',
                enabled=True)
    if success:
        send_password_reset_info(username)
        return True
    else:
        return False


def add_project(project):
    ks = get_keystone_session()
    success = ks.projects.create(name=project,
                                    domain='default',
                                    description='Auto-generated Project',
                                    enabled=False)
    if success:
        return True
    else:
        return False


def add_role(username, project, course):
    ks = get_keystone_session()

    uid = get_user_id(username)
    #pid = get_projects(course)['students'][project]
    pid = get_project_id(project)
    user_role_id = utils.find_resource(ks.roles, 'user').id

    if not uid or not pid:
        return False
    if not get_project_role(uid, pid):
        ks = get_keystone_session()
        result = ks.roles.grant(user_role_id, user=uid, project=pid)
        if not result:
            return False
    return True


@celery.task(bind=True)
def process_new_users(self, course, username, email = None, group_id = None):

    from app.email_model import send_new_course_info

    users = get_users()
    projects = get_projects(course)

    if not users or not projects:
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not get users or projects'}

    if username not in users and email:
        if not add_user(username, email):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not create user ' + username}

    if group_id:
        project = course + '-Group' + group_id
    else:
        project = course + '-' + username

    instructor_project = list(projects['instructors'].keys())[0]
    if not get_project_role(username, instructor_project): # Check if the user is a TA (included in the instructor project)
        if project not in projects['students'] and project not in projects['groups']:
            if not add_project(project):
                return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user ' + username + ' to project ' + project}

    # We check if the role assignment already exists inside of add_role()
    if not add_role(username, project, course):
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user role for ' + username + ' to project ' + project}

    send_new_course_info(username, course)
    return {'task': 'Process User', 'status': 'Complete', 'result': 'Processed user ' + username + ' with project ' + project}


def reset_user_password(username):
    ks = get_keystone_session()
    new_password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    try:
        ks.users.update(get_user_id(username), password=new_password)
        return new_password
    except:
        return None


def toggle_ta_status(username, course, current_role):
    from app.email_model import send_ta_info
    ks = get_keystone_session()
    project_list = get_projects(course)
    instructor_project_id = list(project_list['instructors'].values())[0]
    
    if current_role == 'student':
        # Promote the student to TA status
        if project_list['students'].get(course + '-' + username):
            from app.neutron_model import async_delete_user_networks, list_project_network_details
            student_project_id = project_list['students'][course + '-' + username]
            async_delete_user_networks.delay(list_project_network_details(course), course + '-' + username)
            ks.projects.delete(project_list['students'][course + '-' + username])
            ks.roles.grant(utils.find_resource(ks.roles, 'user').id, user=get_user_id(username), project=instructor_project_id)
            send_ta_info(username, course)

    elif current_role == 'ta':
        # Demote the TA to student status
        from app.neutron_model import async_create_user_networks, list_project_network_details
        user_id = get_user_id(username)
        user_role_id = utils.find_resource(ks.roles, 'user').id
        ks.roles.revoke(user_role_id, user=user_id, project=instructor_project_id)
        project_name = course + '-' + username
        add_project(project_name)
        ks.roles.grant(user_role_id, user=user_id, project=utils.find_resource(ks.projects, project_name).id)
        async_create_user_networks.delay(list_project_network_details(course), project_name)


def delete_users(to_delete, course):
    ks = get_keystone_session()
    user_list = get_course_users(course)
    user_role_id = utils.find_resource(ks.roles, 'user').id
    project_list = get_projects(course)

    for username in to_delete:
        if 'nstructors' in to_delete[username]:
            ks.roles.revoke(role=user_role_id, user=get_user_id(username), project=get_project_id(to_delete[username]))
        else:
            from app.neutron_model import async_delete_user_networks, list_project_network_details
            async_delete_user_networks.delay(list_project_network_details(course), to_delete[username])
            ks.projects.delete(project_list['students'][course + '-' + username])
