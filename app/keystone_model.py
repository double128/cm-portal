from app import app, login, celery
from flask_login import UserMixin
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystoneclient
from keystoneclient import utils 
import pprint 

class OpenStackUser(UserMixin):
    id = None
    is_authenticated = False
    is_active = True
    is_anonymous = False
    auth = None
    osession = None
    project = None
    course = None
    
    def __init__(self):
        return

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
            if auth.get_token(session=sess):
                self.is_authenticated = True
                login.users[id] = self
                return True
            else:
                return False
        except:
            return False


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


def get_user_id(username):
    users = get_users()
    if users[username]:
        return users[username]
    else:
        return None

def get_user_email(username):
    ks = get_keystone_session()
    return utils.find_resource(ks.users, username).email

def get_projects(course):
    ks = get_keystone_session()
    projects = {'instructors': {}, 'students': {}}
    for p in ks.projects.list():
        if course in p.name:
            if 'nstructor' in p.name:
                projects['instructors'][p.name] = p.id
            else:
                projects['students'][p.name] = p.id
    return projects


def get_project_role(user_id, project_id):
    keystone = get_keystone_session()
    role = keystone.roles.list(user=user_id, project=project_id)
    if not role or not role[0].name == 'user':
        return False
    else:
        return True


def add_user(username, email):
    keystone = get_keystone_session()
    success = keystone.users.create(name=username,
                email=email,
                domain='default',
                password='cisco123',
                description='Auto-generated Account',
                enabled=True)
    if success:
        return True
    else:
        return False


def add_project(project):
    ks = get_keystone_session()
    success = ks.projects.create(name=project,
                                    domain='default',
                                    description='Auto-generated Project',
                                    enabled=True) 
    if success:
        return True
    else:
        return False


def add_role(username, project, course):
    ks = get_keystone_session()

    uid = get_user_id(username)
    pid = get_projects(course)['students'][project]
    user_role_id = utils.find_resource(ks.roles, 'user').id

    if not uid or not pid:
        return False
    #if not ks.role_assignments.list(project=pid, role=user_role_id):
    if not get_project_role(uid, pid):
        keystone = get_keystone_session()
        result = keystone.roles.grant(user_role_id, user=uid, project=pid)
        if not result:
            return False
    return True


@celery.task(bind=True)
def process_new_users(self, course, username, email):
    users = get_users()
    projects = get_projects(course)
    if not users or not projects:
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not get users or projects'}

    if username not in users:
        if not add_user(username, email):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not create user ' + username}

    project = course + '-' + username
    if project not in projects['students']:
        if not add_project(project):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user ' + username + ' to project ' + project}

    # We check if the role assignment already exists inside of add_role()
    if not add_role(username, project, course):
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user role for ' + username + ' to project ' + project}

    return {'task': 'Process User', 'status': 'Complete', 'result': 'Processed user ' + username + ' with project ' + project}
        

def get_course_student_info(project, course):
    ks = get_keystone_session()
    projects = get_projects(course)
    instructor_project_id = list(projects['instructors'].values())[0]
    role_assignments_list = ks.role_assignments.list(project=instructor_project_id)
    user_list = get_users()

    user_info_dict = {}
    for student_username in user_list:
        if projects['students'].get(course + '-' + student_username):
            user_info_dict[student_username] = course + '-' + student_username

        elif get_user_id(student_username) in [u.user['id'] for u in role_assignments_list]:
            user_info_dict[student_username] = list(projects['instructors'].keys())[0]
 
    return user_info_dict


def reset_user_password(username):
    ks = get_keystone_session()
    ks.users.update(get_user_id(username), password='cisco123')


def set_student_as_ta(username, course):
    ks = get_keystone_session()
    project_list = get_projects(course)
    instructor_project_id = list(project_list['instructors'].values())[0]
    
    # Project should exist at all times if the student is not a TA, but we check anyways
    # FOR REFERENCE: .get() will return "None" if that key does not exist, instead of causing a stack trace, so use it for checks like this plz
    if project_list['students'].get(course + '-' + username):
        student_project_id = project_list['students'][course + '-' + username]
        ks.projects.delete(project_list['students'][course + '-' + username])
        ks.roles.grant(utils.find_resource(ks.roles, 'user').id, user=get_user_id(username), project=instructor_project_id)
        # TODO: Also delete their networks, subnets, and routers


def get_instructor_project_users(course, project):
    ks = get_keystone_session()
    project_list = get_projects(course)
    instructor_project_id = list(project_list['instructors'].values())[0]

    user_id = get_user_id('100111111')
    user_id_other = get_user_id('100222222')

    print(ks.role_assignments.list(user=user_id, project=instructor_project_id))
    print(ks.role_assignments.list(user=user_id_other, project=instructor_project_id))

def delete_users(username_list, course):
    # Just remove their project, networks, subnets, and routers
    ks = get_keystone_session()
    role_assignments_list = ks.role_assignments.list(project=list(get_projects(course)['instructors'].values())[0])
    project_list = get_projects(course)
    user_role_id = utils.find_resource(ks.roles, 'user').id

    for username in username_list:
        user_id = get_user_id(username)
        # if user is a TA
        if user_id in [u.user['id'] for u in role_assignments_list]:
            ks.roles.revoke(role=user_role_id, user=user_id, project=list(get_projects(course)['instructors'].values())[0])
        else:
            ks.projects.delete(project_list['students'][course + '-' + username])
