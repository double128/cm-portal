from app import app, login
from flask_login import UserMixin
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystoneclient
from novaclient import client as novaclient
from neutronclient.v2_0 import client as neutronclient

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
    keystone = get_keystone_session()
    users = {}
    for p in keystone.users.list():
        users[p.name] = p.id
    return users


def get_user_id(username):
    users = get_users()
    if users[username]:
        return users[username]
    else:
        return None


# List all the projects that exist in Openstack
def get_projects(course=None):
    keystone = get_keystone_session()
    projects = {}
    for p in keystone.projects.list():
        if course:
            if course in p.name:
                projects[p.name] = p.id
        else:
            projects[p.name] = p.id
    return projects


# Get the ID of a project by name
def get_project_id(project):
    projects = get_projects()
    if projects[project]:
        return projects[project]
    else:
        return None


# Get THE INSTRUCTOR'S project ID for the course
def get_instructor_project_id(project, course):
    projects = get_projects()
    for project in projects:
        if 'Instructors' in project and course in project:
            return projects[project]


# Get one project ID that's associated with the course argument
# TODO: DEPRECATE
def get_course_subproject_id(course):
    projects = get_projects(course)
    for project in projects:
        if 'Instructors' not in project:
            return projects[project]
    return None


# Get all project IDs that're associated with the course and shove them into a dict
def get_all_course_subproject_id(course):
    projects = get_projects(course)
    subprojects = {}
    for project in projects:
        if 'Instructors' not in project:
            subprojects.update({project: projects[project]})
    return subprojects


# Create a list of all the users that are associated with a course
def get_project_users(course):
    # Call this function so we get a list of keys formatted as "INFR-XXXX-100XXXXXX" and the project ID as the value
    users_dict = get_all_course_subproject_id(course)
    # We only want the keys because they tell us the user as well as the course they're associated with specifically
    # (Student usernames are just their student IDs, which doesn't tell us enough about the user's associated projects)
    keys = list(users_dict.keys())  
    
    # Create a new list where we can store our values after removing the "INFR-1111-" part
    project_users = []
    for k in keys:
        project_users.append(k.split("INFR-1111-", 2)[1])
    
    return project_users


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
    keystone = get_keystone_session()
    success = keystone.projects.create(name=project,
                                    domain='default',
                                    description='Auto-generated Project',
                                    enabled=True) 
    if success:
        return True
    else:
        return False


def add_role(username, project):
    uid = get_user_id(username)
    pid = get_project_id(project)
    if not uid or not pid:
        return False
    if not get_project_role(uid, pid):
        keystone = get_keystone_session()
        result = keystone.roles.grant('3af37119e0df4aa48c51df8ee8c14791', user=uid, project=pid)
        if not result:
            return False
    return True


def process_new_user(course, username, email):
    users = get_users()
    projects = get_projects(course)
    if not users or not projects:
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not get users or projects'}

    if username not in users:
        if not add_user(username, email):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not create user ' + username}

    project = course + '-' + username
    if project not in projects:
        if not add_project(project):
            return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user ' + username + ' to project ' + project}

    if not add_role(username, project):
        return {'task': 'Process User', 'status': 'Failed', 'result': 'Could not add user role for ' + username + ' to project ' + project}

    return {'task': 'Process User', 'status': 'Complete', 'result': 'Processed user ' + username + ' with project ' + project}


def get_project_quota(project_id):
    sess = get_admin_session()
    nv = novaclient.Client(version='2.1', session=sess)
    nova_quota = nv.quotas.get(tenant_id=project_id)
    nova_quota_list = vars(nova_quota)['_info']
    
    nt = neutronclient.Client(session=sess)
    neutron_quota = nt.show_quota(project_id=project_id)
    neutron_quota_list = neutron_quota.get('quota', [])

    # Merge them into a new dict
    merged_dict = { **nova_quota_list, **neutron_quota_list }
    
    # Grab all the important stuff from that dict and make a new one
    keys = ['cores', 'instances', 'ram', 'network', 'subnet', 'port', 'router', 'floatingip']
    quota_dict = dict((k, merged_dict[k]) for k in (keys))
    
    return quota_dict

# TODO: Probably include changing the COURSE INSTRUCTOR quota here, too
def update_project_quota(project_id, instanceq, coreq, ramq, netq, subq, portq, fipq, routerq):
    sess = get_admin_session()
    nv = novaclient.Client(version='2.1', session=sess)
    nova_success = nv.quotas.update(tenant_id=project_id, instances=instanceq, cores=coreq, ram=ramq)
    
    nt = neutronclient.Client(session=sess)
    neutron_success = nt.update_quota(project_id=project_id, 
                      body={'quota': {"network": netq, "subnet": subq, "port": portq, "floatingip": fipq, "router": routerq}}) 
    
    if nova_success and neutron_success:
        return True
    else:
        return False




"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
                 N    E    U    T    R    O    N 

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

def setup_neutronclient():
    sess = get_admin_session()
    nt = neutronclient.Client(session=sess)
    return nt


def list_project_network_details(project, course):
    """
    Create a dict that is used to display information about
    networks and subnets for a given course.
    """
    nt = setup_neutronclient()

    inst_project_id = get_instructor_project_id(project, course)
    inst_netw = nt.list_networks(project_id=inst_project_id).get('networks', [])
    inst_subn = nt.list_subnets(project_id=inst_project_id).get('subnets', [])

    # Create a dictionary with n amount of subdictionaries, where n = number of networks

    netw_count = get_network_count(nt, inst_project_id)
    netw_names = get_network_names(project, course)
    netw_details = {}
    for i in range(0, netw_count):
        netw_details[netw_names[i]] = {'network': {
                                         'admin_state_up': inst_netw[i]['admin_state_up'],
                                         'created_at': inst_netw[i]['created_at'],
                                         'description': inst_netw[i]['description'],
                                         'id': inst_netw[i]['id'],
                                         'name': inst_netw[i]['name'],
                                         'port_security_enabled': inst_netw[i]['port_security_enabled'],
                                         'project_id': inst_netw[i]['project_id'],
                                         'provider:network_type': inst_netw[i]['provider:network_type'],
                                         'provider:physical_network': inst_netw[i]['provider:physical_network'],
                                         'provider:segmentation_id': inst_netw[i]['provider:segmentation_id'],
                                         'router:external': inst_netw[i]['router:external'],
                                         'shared': inst_netw[i]['shared'],
                                         'status': inst_netw[i]['status'],
                                         'subnets': inst_netw[i]['subnets'],
                                         'updated_at': inst_netw[i]['updated_at']}, 
                                       'subnet': {
                                         'allocation_pools': inst_subn[i]['allocation_pools'],
                                         'cidr': inst_subn[i]['cidr'],
                                         'created_at': inst_subn[i]['created_at'],
                                         'enable_dhcp': inst_subn[i]['enable_dhcp'],
                                         'gateway_ip': inst_subn[i]['gateway_ip'],
                                         'host_routes': inst_subn[i]['host_routes'],
                                         'id': inst_subn[i]['id'],
                                         'ip_version': inst_subn[i]['ip_version'],
                                         'name': inst_subn[i]['name'],
                                         'network_id': inst_subn[i]['network_id'],
                                         'project_id': inst_subn[i]['project_id'],
                                         'updated_at': inst_subn[i]['updated_at']}}
    return netw_details


def get_network_count(nt, pid):
    """
    This might seem unneccessary, but I think it's useful.
    DO NOT CALL THIS ON ITS OWN. Make sure it's used in a function.
    
    Also, I reinit the "netw" variable since if you don't specify the .get('networks', []) bit,
    list_length will always return "1" due to how OSC formats its list_networks() output.

    I basically added this so I don't screw up and wonder why only 1 network is listed
    even though there's 2 or more.
    """
    netw = nt.list_networks(project_id=pid).get('networks', [])
    list_length = len(netw)
    return list_length
   
    
def get_network_names(project, course):
    nt = setup_neutronclient()
    
    # We can assume what every network/subnet name will be based on the instructor's network name
    inst_project_id = get_project_id(project)
    
    inst_netw = nt.list_networks(project_id=inst_project_id).get('networks', [])
    inst_netw_count = get_network_count(nt, inst_project_id)

    course_splitter = course + '-Instructors-'  # Verify that we will ONLY split after the course ID and "instructors" phrase
    network_name_list = []
    for i in range(0, inst_netw_count):
        network_name_list.append(str(inst_netw[i]['name']).split(course_splitter)[1].rsplit('-', 1)[0])

    return network_name_list


# TODO: LEARN HOW TO DO ERROR HANDLING HERE KTHX
def create_course_network(project, course, network_name):
    sess = get_admin_session()
    nt = neutronclient.Client(session=sess)
    
    # We'll create the network for the instructor first, and then create clones of this network for the students after
    instructor_project_id = get_project_id(project)
    instructor_netw_name = course + "-Instructors-" + network_name + "-Network"
    
    # TODO: Check if a network name with "network_name" already exists
    # Search through existing networks and cancel if network already exists with that name
    list_of_networks = nt.list_networks(project_id=instructor_project_id)
    if instructor_netw_name in list_of_networks:
        return False

    instructor_netw_body = {'network': {'name': instructor_netw_name, 'admin_state_up': True, 'project_id': instructor_project_id, 'router:external': False, 'description': 'Created by CM Portal'}}
    instructor_netw = nt.create_network(body=instructor_netw_body)

    # Get a list of the project names and their IDs from another function
    project_user_list = get_all_course_subproject_id(course)
    for k in project_user_list:
        netw_name = k + "-" + network_name + "-Network"
        project_id = project_user_list[k]
        netw_body = {'network': {'name': netw_name, 'admin_state_up': True, 'project_id': project_id, 'router:external': False, 'description': 'Created by CM Portal'}}
        netw = nt.create_network(body=netw_body)

    # Get the new network's ID
    inst_netw_id = nt.list_networks(name=instructor_netw_name)['networks'][0]['id']


def delete_course_network(project, course, network_id, network_name):
    nt = setup_neutronclient()

    inst_project_id = get_instructor_project_id(project, course)
    subproject_ids = get_all_course_subproject_id(course)

    subproject_netw_list = []
    for k in subproject_ids:
        netw_name = k + "-" + network_name + "-Network"
        netw_id = nt.list_networks(name=netw_name)['networks'][0]['id']
        subproject_netw_list.append(netw_id)
     
    subproject_netw_list.append(network_id)
    for nid in subproject_netw_list:
        nt.delete_network(nid)


def create_course_subnet(project, course, network_name, subnet, gateway):
    '''
    As a note, we don't need a "delete_course_subnet" function as deleting
    a network will automatically delete any associated subnets.
    '''
    nt = setup_neutronclient()

    instructor_project_id = get_project_id(project)
    instructor_netw_name = course + "-" + "Instructors-" + network_name + "-Network"
    instructor_netw_body = nt.list_networks(name=instructor_netw_name)
    instructor_netw_id = instructor_netw_body['networks'][0]['id']
    
    instructor_subnet_name = course + "-" + "Instructors-" + network_name + "-Subnet"
    instructor_subnet_body = {'subnet':
                                {'name': instructor_subnet_name, 
                                  'cidr': subnet,
                                  'ip_version': 4, 
                                  'gateway_ip': gateway,
                                  'network_id': instructor_netw_id,
                                  'project_id': instructor_project_id}}
    instructor_subnet = nt.create_subnet(body=instructor_subnet_body)
    
    # Create router for instructor subnet
    inst_subnet_id = nt.list_subnets(name=instructor_subnet_name)['subnets'][0]['id']
    create_course_network_router(instructor_project_id, course, instructor_netw_id, network_name, inst_subnet_id)

    project_user_list = get_all_course_subproject_id(course)
    for k in project_user_list:
        netw_name = k + "-" + network_name + "-Network"
        project_id = project_user_list[k]
        netw_body = nt.list_networks(name=netw_name)
        netw_id = netw_body['networks'][0]['id']
        subnet_name = k + "-" + network_name + "-Subnet"
        subnet_body = {'subnet':
                        {'name': subnet_name,
                          'cidr': subnet,
                          'ip_version': 4,
                          'gateway_ip': gateway,
                          'network_id': netw_id,
                          'project_id': project_id}}
        nt.create_subnet(body=subnet_body)


def create_course_network_router(project_id, course, network_id, network_name, subnet_id):
    '''
    This will be called directly from create_course_network
    '''
    nt = setup_neutronclient()

    external_network = nt.list_networks(name='LAN')['networks'][0]['id']
    inst_router_name = course + "-Instructors-" + network_name + "-Router"
    router_body = {'router': {'name': inst_router_name,
                              'project_id': project_id,
                              'external_gateway_info': {
                                'network_id': external_network}}}
    nt.create_router(body=router_body)

    router_id = nt.list_routers(name=inst_router_name)['routers'][0]['id']

    router_port_body = {'subnet_id': subnet_id}
    nt.add_interface_router(router_id, body=router_port_body)

    #TODO:
    # neutronclient.common.exceptions.IpAddressAlreadyAllocatedClient error handling

def delete_network_router(network_id):
    print('hello world')


def toggle_network_dhcp(course, network_name, subnet_id, change):
    nt = setup_neutronclient()

    # We need to get all the subproject subnets so we can apply changes
    project_user_list = get_all_course_subproject_id(course)
    subnet_id_list = []
    for k in project_user_list:
        subnet_name = k + "-" + network_name + "-Subnet"
        subproject_subnet_id = nt.list_subnets(name=subnet_name)['subnets'][0]['id']
        subnet_id_list.append(subproject_subnet_id)
    
    subnet_id_list.append(subnet_id)
    change_body = {'subnet': {'enable_dhcp': change}}
    
    for sid in subnet_id_list:
        nt.update_subnet(sid, body=change_body)

def toggle_network_port_security(course, network_name, network_id, change):
    nt = setup_neutronclient()

    project_user_list = get_all_course_subproject_id(course)
    network_id_list = []
    for k in project_user_list:
        subproject_network_name = k + "-" + network_name + "-Network"
        subproject_network_id = nt.list_networks(name=subproject_network_name)['networks'][0]['id']
        network_id_list.append(subproject_network_id)

    network_id_list.append(network_id)
    change_body = {'network': {'port_security_enabled': change}}

    for nid in network_id_list:
        nt.update_network(nid, body=change_body)
