from app import celery
from celery import group
from .keystone_model import *
from .exceptions import *
from neutronclient.v2_0 import client as neutronclient
import re
import pprint

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
                 N    E    U    T    R    O    N 

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

def setup_neutronclient():
    sess = get_admin_session()
    nt = neutronclient.Client(session=sess)
    return nt


def list_project_network_details(project, course):
    nt = setup_neutronclient()
    
    the_list = {}
    network_list = nt.list_networks()['networks']
    subnet_list = nt.list_subnets()['subnets']
    router_list = nt.list_routers()['routers']
    
    network_names = []
    for network in network_list:
        if course in network['name'] and 'nstructor' in network['name']:
            network_names.append(network['name'].split('-', 3)[3].rsplit('-', 1)[0])
    
    if len(network_names) == 0:
        return False

    for name in network_names:
        instructor_networks = []
        student_networks = []
        for network in network_list:
            if name in network['name']:
                if 'nstructors' in network['name']:
                    instructor_networks.append(network)
                else:
                    student_networks.append(network)
                
        for i in instructor_networks:
            the_list[name] = i
            the_list[name]['children'] = {}
            the_list[name]['router'] = {}
            try:
                subnet_id = the_list[name]['subnets'][0]
                for subnet in subnet_list:
                    if subnet_id == subnet['id']:
                        the_list[name]['subnets'] = subnet
                for router in router_list:
                    if course in router['name'] and 'nstructor' in router['name'] and name in router['name']:
                        the_list[name]['router'] = router
                for s in student_networks:
                    child_name = s['name'].split(name, 1)[0].rsplit('-', 1)[0]
                    the_list[name]['children'][child_name] = s
                    student_subnet_id = s['subnets'][0]
                    for student_subnet in subnet_list:
                        if student_subnet_id == student_subnet['id']:
                            the_list[name]['children'][child_name]['subnets'] = student_subnet
                    for student_router in router_list:
                        if child_name in student_router['name']:
                            the_list[name]['children'][child_name]['router'] = student_router
            except IndexError: # Subnet creation hasn't completed yet, so don't let the network display in the table yet
                the_list[name]['subnets'] = None

    return the_list
    # Has this been fully optimized/fixed? I have no idea. Just LEAVE IT.


def check_network_name(course, network_name):
    nt = setup_neutronclient()
    network_name = course + "-Instructors-" + network_name + "-Network"
    try:
        if nt.list_networks(name=network_name)['networks'][0]['id']:
            raise NetworkNameAlreadyExists("A network named \"" + network_name + "\" already exists. Please use another name.")
    except IndexError:
        # If this is thrown, it means there's no networks with this name, so continue
        pass

"""
CREATE NETWORK
"""
def create_network(project_id, network_name):
    nt = setup_neutronclient()
    nt.create_network(body={'network': {'name': network_name, 'project_id': project_id, 'router:external': False}})
    #return nt.find_resource('network', network_name)['id']
    return get_network_id(network_name)


"""
DELETE NETWORK
"""
def delete_network(network_id):
    nt = setup_neutronclient()
    nt.delete_network(network_id)


"""
CREATE SUBNET
"""
def create_subnet(project_id, network_id, subnet_name, cidr, gateway):
    nt = setup_neutronclient()
    nt.create_subnet(body={'subnet': {'name': subnet_name, 'cidr': cidr, 'gateway_ip': gateway, 'ip_version': 4, 'network_id': network_id, 'project_id': project_id}})
    return nt.find_resource('subnet', subnet_name)['id']


"""
CREATE ROUTER
"""
def create_router(project_id, subnet_id, router_name, external_network_id):
    nt = setup_neutronclient()
    nt.create_router(body={'router': {'name': router_name, 'project_id': project_id, 'external_gateway_info': {'network_id': external_network_id}}})
    router_id = nt.find_resource('router', router_name)['id']
    nt.add_interface_router(router_id, body={'subnet_id': subnet_id})
    return router_id
    

""" 
DELETE ROUTER
"""
def delete_router(router_id, subnet_id):
    nt = setup_neutronclient()
    nt.remove_interface_router(router_id, body={'subnet_id': subnet_id})
    nt.delete_router(router_id)


"""
ASYNC WRAPPERS
"""
def network_create_wrapper(project, course, network_name, cidr, gateway):
    nt = setup_neutronclient()

    projects = get_projects(course)
    all_projects = {**projects['instructors'], **projects['students']}
    external_network_id = nt.list_networks(name='HRL')['networks'][0]['id']

    for project in all_projects:
        network_name_template = project + '-' + network_name
        async_network_create.delay(all_projects[project], \
                network_name_template + '-Network', \
                network_name_template + '-Subnet', \
                network_name_template + '-Router', \
                str(cidr), str(gateway), external_network_id)


@celery.task(bind=True)
def async_network_create(self, project_id, network_name, subnet_name, router_name, cidr, gateway, external_network_id):
    try:
        network_id = create_network(project_id, network_name)
        if not network_id:
            return {'task': 'Create Network', 'status': 'Failed', 'result': 'Could not create network ' + network_name}
    except neutronclient.exceptions.ServiceUnavailable as exc:
        raise self.retry(exc=exc)
    except neutronclient.exceptions.NeutronClientNoUniqueMatch:
        pass
    
    try:
        subnet_id = create_subnet(project_id, network_id, subnet_name, cidr, gateway)
        if not subnet_id:
            return {'task': 'Create Subnet', 'status': 'Failed', 'result': 'Could not create subnet ' + subnet_name}
    except neutronclient.exceptions.ServiceUnavailable as exc:
        raise self.retry(exc=exc)
    except neutronclient.exceptions.NeutronClientNoUniqueMatch:
        pass

    try:
        if not create_router(project_id, subnet_id, router_name, external_network_id):
            return {'task': 'Create Router', 'status': 'Failed', 'result': 'Could not create router ' + router_name}
    except neutronclient.exceptions.ServiceUnavailable as exc:
        raise self.retry(exc=exc)
    except neutronclient.exceptions.NeutronClientNoUniqueMatch:
        pass

    return {'task': 'Create New Network', 'status': 'Complete', 'result': 'Successfully created network for project ' + project_id}


def network_delete_wrapper(project, course, network):
    all_networks = {project: {**network}, **network['children']}
    all_networks[project].pop('children', None)
    
    for network in all_networks:
        async_network_delete.delay(all_networks[network])


@celery.task(bind=True)
def async_network_delete(self, network):
    if network.get('router'):
        try:
            delete_router(network['router']['id'], network['subnets']['id'])
        except neutronclient.exceptions.ServiceUnavailable as exc:
            raise self.retry(exc=exc)
    try:
        delete_network(network['id'])
    except neutronclient.exceptions.ServiceUnavailable as exc:
        raise self.retry(exc=exc)

    return {'task': 'Delete Network', 'status': 'Complete', 'result': 'Successfully deleted network for project ' + network['project_id']}
    

def router_create_wrapper(project, course, network):
    pass

#@celery.task(bind=True)
def async_router_create(self):
    pass

def router_delete_wrapper(project, course, network):
    all_networks = {project: {**network}, **network['children']}
    all_networks[project].pop('children', None)
    
    for network in all_networks:
        async_router_delete(all_networks['router']['id'], all_networks['subnets']['id'])

def async_router_delete(self, router_id, subnet_id):
        print(router_id)
        print(subnet_id)

"""
GETTERS
"""
def get_network_id(network_name):
    nt = setup_neutronclient()
    return nt.find_resource('network', network_name)['id'] 


def get_subnet_id(subnet_name):
    nt = setup_neutronclient()
    return nt.find_resource('subnet', subnet_name)['id']


def get_router_id(router_name):
    nt = setup_neutronclient()
    return nt.find_resource('router', router_name)['id']

"""
TOGGLES
"""
def toggle_network_dhcp(network, change):
    nt = setup_neutronclient()

    change_body = {'subnet': {'enable_dhcp': change}}
    nt.update_subnet(network['subnets']['id'], change_body)

    for student in network['children']:
        nt.update_subnet(network['children'][student]['subnets']['id'], change_body)


def toggle_network_port_security(network, change):
    nt = setup_neutronclient()
    
    change_body = {'network': {'port_security_enabled': change}}
    nt.update_network(network['id'], change_body)

    for student in network['children']:
        nt.update_network(network['children'][student]['id'], change_body)


def toggle_network_internet_access(project, course, network, network_name, change):
    nt = setup_neutronclient()
    if change is False:
        router_delete_wrapper(project, course, network)
    elif change is True:
        project_id = get_projects(course)
        subnet_id = network['subnets']['id']
        create_course_network_router(project_id, course, network_name, subnet_id)

