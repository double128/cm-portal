from app import celery
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


def create_course_network(project, course, network_name):
    nt = setup_neutronclient()
    
    instructor_network_name = course + "-Instructors-" + network_name + "-Network"
    
    try:
        if nt.list_networks(name=instructor_network_name)['networks'][0]['id']:
            raise NetworkNameAlreadyExists("A network named \"" + network_name + "\" already exists. Please use another name.")
    except IndexError:
        # If this is thrown, it means there's no networks with this name
        pass

    project_ids = get_projects(course)
    instructor_network_body = {'network': {
                                'name': instructor_network_name, 
                                'project_id': list(project_ids['instructors'].values())[0],
                                'router:external': False}}
    nt.create_network(body=instructor_network_body)

    for student in project_ids['students']:
        student_network_name = student + "-" + network_name + "-Network"
        student_project_id = project_ids['students'][student]
        student_network_body = {'network': {
                                    'name': student_network_name,
                                    'project_id': student_project_id,
                                    'router:external': False}}
        nt.create_network(body=student_network_body)


def delete_course_network(project, course, network):
    nt = setup_neutronclient()

    nt.delete_network(network['id'])
    for student in network['children']:
        nt.delete_network(network['children'][student]['id'])


def create_course_subnet(project, course, network_name, subnet, gateway):
    nt = setup_neutronclient()

    project_ids = get_projects(course)
    instructor_network_name = course + "-Instructors-" + network_name + "-Network"
    instructor_subnet_name = course + "-Instructors-" + network_name + "-Subnet"
    instructor_subnet_body = {'subnet':
                                {'name': instructor_subnet_name,
                                  'cidr': subnet,
                                  'ip_version': 4, 
                                  'gateway_ip': gateway,
                                  'network_id': nt.list_networks(name=instructor_network_name)['networks'][0]['id'],
                                  'project_id': list(project_ids['instructors'].values())[0]}}
    instructor_subnet = nt.create_subnet(body=instructor_subnet_body)

    for student in project_ids['students']:
        student_network_name = student + "-" + network_name + "-Network"
        student_subnet_name = student + "-" + network_name + "-Subnet"
        student_subnet_body = {'subnet':
                                   {'name': student_subnet_name,
                                    'cidr': subnet,
                                    'ip_version': 4,
                                    'gateway_ip': gateway,
                                    'network_id': nt.list_networks(name=student_network_name)['networks'][0]['id'],
                                    'project_id': project_ids['students'][student]}}
        nt.create_subnet(body=student_subnet_body)

    instructor_subnet_id = nt.list_subnets(name=instructor_subnet_name)['subnets'][0]['id']
    create_course_network_router(project_ids, course, network_name, instructor_subnet_id)


def create_course_network_router(project_ids, course, network_name, subnet_id):
    nt = setup_neutronclient()

    external_network_id = nt.list_networks(name='HRL')['networks'][0]['id']
    instructor_router_name = course + "-Instructors-" + network_name + "-Router"
    instructor_router_body = {'router': {
                                'name': instructor_router_name,
                                'project_id': list(project_ids['instructors'].values())[0],
                                'external_gateway_info': {
                                    'network_id': external_network_id}}}
    nt.create_router(body=instructor_router_body)
    router_id = nt.list_routers(name=instructor_router_name)['routers'][0]['id']
    router_port_body = {'subnet_id': subnet_id}
    nt.add_interface_router(router_id, body=router_port_body)

    for student in project_ids['students']:
        student_router_name = student + "-" + network_name + "-Router"
        student_router_body = {'router': {
                                    'name': student_router_name,
                                    'project_id': project_ids['students'][student],
                                    'external_gateway_info': {
                                        'network_id': external_network_id}}}
        nt.create_router(body=student_router_body)
        student_router_id = nt.list_routers(name=student_router_name)['routers'][0]['id']
        student_subnet_name = student + "-" + network_name + "-Subnet"
        student_subnet_id = nt.list_subnets(name=student_subnet_name)['subnets'][0]['id']
        student_router_port_body = {'subnet_id': student_subnet_id}
        nt.add_interface_router(student_router_id, body=student_router_port_body)
 

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

