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
    return nt.find_resource('network', network_name)['id']


"""
DELETE NETWORK
"""
def delete_course_network(project, course, network):
    nt = setup_neutronclient()

    nt.delete_network(network['id'])
    for student in network['children']:
        nt.delete_network(network['children'][student]['id'])

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
def delete_course_network_router(network):
    nt = setup_neutronclient()
    
    instructor_port_body = {'subnet_id': network['subnets']['id']}
    instructor_router_id = network['router']['id']
    nt.remove_interface_router(instructor_router_id, instructor_port_body)
    nt.delete_router(instructor_router_id)
    
    for student in network['children']:
        student_port_body = {'subnet_id': network['children'][student]['subnets']['id']}
        student_router_id = network['children'][student]['router']['id']
        nt.remove_interface_router(student_router_id, student_port_body)
        nt.delete_router(student_router_id)


"""
ASYNC WRAPPERS
"""
def network_create_wrapper(project, course, network_name, cidr, gateway):
    nt = setup_neutronclient()
    projects = get_projects(course)
    all_projects = { **projects['instructors'], **projects['students']}
    external_network_id = nt.list_networks(name='HRL')['networks'][0]['id']
    
    for project in all_projects:
        async_network_create.delay(all_projects[project], \
                project + '-' + network_name + '-Network', \
                project + '-' + network_name + '-Subnet', \
                project + '-' + network_name + '-Router', \
                str(cidr), str(gateway), external_network_id)


@celery.task(bind=True)
def async_network_create(self, project_id, network_name, subnet_name, router_name, cidr, gateway, external_network_id):
    try:
        network_id = create_network(project_id, network_name)
        if not network_id:
            return {'task': 'Create Network', 'status': 'Failed', 'result': 'Could not create network ' + network_name}
    except Exception as exc: #TODO: Find out what exception exists for Openstack timeouts
        raise self.retry(exc=exc)
    
    try:
        subnet_id = create_subnet(project_id, network_id, subnet_name, cidr, gateway)
        if not subnet_id:
            return {'task': 'Create Subnet', 'status': 'Failed', 'result': 'Could not create subnet ' + subnet_name}
    except Exception as exc:
        raise self.retry(exc=exc)

    try:
        if not create_router(project_id, subnet_id, router_name, external_network_id):
            return {'task': 'Create Router', 'status': 'Failed', 'result': 'Could not create router ' + router_name}
    except Exception as exc:
        raise self.retry(exc=exc)

    return {'task': 'Create New Network', 'status': 'Complete', 'result': 'Successfully created network for project ' + project_id}


def network_delete_wrapper(project, course, network):
    all_networks = {project: {**network}, **network['children']}
    all_networks[project].pop('children', None)
    
    for network in all_networks:
        async_network_delete.delay(all_networks[network])


@celery.task(bind=True)
def async_network_delete(self, network):
    if network['router']:
        try:
            if not delete_router(network['router']['id'], network['subnets']['id']):
                return {'task': 'Delete Router', 'status': 'Failed', 'result': 'Could not delete router ' + network['router']['name']}
        except Exception as exc:
            raise self.retry(exc=exc)
    
    try:
        if not delete_network(network['network']['id']):
                return {'task': 'Delete Network', 'status': 'Failed', 'result': 'Could not delete network ' + network['name']}
    except Exception as exc:
        raise self.retry(exc=exc)
    

def delete_router(router_id, subnet_id):
    nt = setup_neutronclient()
    nt.remove_interface_router(router_id, body={'subnet_id': subnet_id})
    nt.delete_router(router_id)


def delete_network(network_id):
    nt = setup_neutronclient()
    nt.delete_network(network_id)
    

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


def toggle_network_internet_access(course, network, network_name, change):
    nt = setup_neutronclient()
    if change is False:
        delete_course_network_router(network)
    elif change is True:
        project_id = get_projects(course)
        subnet_id = network['subnets']['id']
        create_course_network_router(project_id, course, network_name, subnet_id)

