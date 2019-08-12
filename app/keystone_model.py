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
            auth.get_token(session=sess)
        except exceptions.http.Unauthorized as e:
            raise exceptions.http.Unauthorized(e)
        
        try:
            check_if_course_running(self.course)
        except ClassInSession as e:
            raise ClassInSession(e)

        self.is_authenticated = True
        login.users[id] = self
        

def check_if_course_running(user_course):
    weekday = datetime.datetime.today().weekday()
    current_time = datetime.datetime.utcnow().time()
    #current_time = datetime.time(1, 0, 0)

    check = Course.query.filter_by(course=user_course).first()
    schedule = check.scheduled_times.all()
    for time in schedule:
        if time.weekday == weekday:
            if time.start_time < current_time < time.end_time:
                return True
            else:
                raise ClassInSession("A class is currently in session.")


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
    ks = get_keystone_session()
    projects = get_projects(course)
    instructor_project_name = list(projects['instructors'].keys())[0]
    instructor_project_id = list(projects['instructors'].values())[0]
    user_list = ks.users.list()
    role_assignments_list = ks.role_assignments.list(role=utils.find_resource(ks.roles, 'user').id)
    
    role_dict = {}
    for role in role_assignments_list:
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
    return utils.find_resource(ks.users, username).id


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


def get_project_id(project):
    ks = get_keystone_session()
    return utils.find_resource(ks.projects, project).id


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
        from app.neutron_model import async_delete_user_networks, list_project_network_details
        student_project_id = project_list['students'][course + '-' + username]
        async_delete_user_networks(list_project_network_details(course), course + '-' + username)
        ks.projects.delete(project_list['students'][course + '-' + username])
        ks.roles.grant(utils.find_resource(ks.roles, 'user').id, user=get_user_id(username), project=instructor_project_id)


def delete_users(to_delete, course):
    # Just remove their project, networks, subnets, and routers
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
    

    #role_assignments_list = ks.role_assignments.list(project=list(get_projects(course)['instructors'].values())[0])
    #project_list = get_projects(course)

    #for username in username_list:
    #    user_id = get_user_id(username)
    #    if user_id in [u.user['id'] for u in role_assignments_list]:
    #        pass
            #ks.roles.revoke(role=user_role_id, user=user_id, project=list(get_projects(course)['instructors'].values())[0])
    #    else:
    #        from app.neutron_model import get_user_networks
    #        get_user_networks(get_user_id
            #nt.list_networks(project_id=project_list['students'][course + '-' + username])
            #print(nt.list_networks)

            #ks.projects.delete(project_list['students'][course + '-' + username])

    

