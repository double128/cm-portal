from app import celery
from celery import group
from app.keystone_model import get_admin_session, get_projects, get_project_id
from app.exceptions import *
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


def list_project_network_details(course):
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
                    if the_list[name]['children'][child_name].get('subnets'):
                        student_subnet_id = s['subnets'][0]
                        for student_subnet in subnet_list:
                            if student_subnet_id == student_subnet['id']:
                                the_list[name]['children'][child_name]['subnets'] = student_subnet
                        for student_router in router_list:
                            if child_name in student_router['name'] and name in student_router['name'] and course in student_router['name']:
                                the_list[name]['children'][child_name]['router'] = student_router
            except IndexError: # Subnet creation hasn't completed yet (due to async with celery), so don't let the network display in the table yet
                the_list[name]['subnets'] = None
    return the_list


def create_network(project_id, network_name):
    nt = setup_neutronclient()
    nt.create_network(body={'network': {'name': network_name, 'project_id': project_id, 'router:external': False}})
    return get_network_id(network_name)


def delete_network(network_id):
    nt = setup_neutronclient()
    nt.delete_network(network_id)


def create_subnet(project_id, network_id, subnet_name, cidr, gateway):
    nt = setup_neutronclient()
    nt.create_subnet(body={'subnet': {'name': subnet_name, 'cidr': cidr, 'gateway_ip': gateway, 'ip_version': 4, 'network_id': network_id, 'project_id': project_id}})
    return get_subnet_id(subnet_name)


def create_router(project_id, subnet_id, router_name, external_network_id):
    nt = setup_neutronclient()
    nt.create_router(body={'router': {'name': router_name, 'project_id': project_id, 'external_gateway_info': {'network_id': external_network_id}}})
    router_id = nt.find_resource('router', router_name)['id']
    nt.add_interface_router(router_id, body={'subnet_id': subnet_id})
    return router_id
    

def delete_router(router_id, subnet_id):
    nt = setup_neutronclient()
    nt.remove_interface_router(router_id, body={'subnet_id': subnet_id})
    nt.delete_router(router_id)


def network_create_wrapper(project, course, network_name, cidr):
    import netaddr
    nt = setup_neutronclient()
    projects = get_projects(course)
    all_projects = {**projects['instructors'], **projects['students']}
    external_network_id = nt.list_networks(name='HRL')['networks'][0]['id']
    cidr = netaddr.IPNetwork(cidr + '/24')
    gateway = netaddr.IPNetwork(cidr)[1]

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
    all_networks = merge_network_dicts(project, network)
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
    

def router_create_wrapper(project, course, network_name, network):
    nt = setup_neutronclient()
    projects = get_projects(course)
    all_projects = {**projects['instructors'], **projects['students']}
    all_networks = merge_network_dicts(project, network)
    external_network_id = nt.list_networks(name='HRL')['networks'][0]['id']
    
    for project in all_projects:
        router_name = project + '-' + network_name + '-Router'
        async_router_create.delay(all_projects[project], all_networks[project]['subnets']['id'], router_name, external_network_id)
 

@celery.task(bind=True)
def async_router_create(self, project_id, subnet_id, router_name, external_network_id):
    nt = setup_neutronclient()
    nt.create_router(body={'router': {'name': router_name, 'project_id': project_id, 'external_gateway_info': {'network_id': external_network_id}}})
    router_id = nt.find_resource('router', router_name)['id']
    nt.add_interface_router(router_id, body={'subnet_id': subnet_id})


def router_delete_wrapper(project, network):
    all_networks = merge_network_dicts(project, network)
    for network in all_networks:
        async_router_delete.delay(all_networks[network]['router']['id'], all_networks[network]['subnets']['id'])


@celery.task(bind=True)
def async_router_delete(self, router_id, subnet_id):
    nt = setup_neutronclient()
    nt.remove_interface_router(router_id, body={'subnet_id': subnet_id})
    nt.delete_router(router_id)


def merge_network_dicts(project, network):
    all_networks = {project: {**network}, **network['children']}
    all_networks[project].pop('children', None)
    return all_networks


def get_network_id(network_name):
    nt = setup_neutronclient()
    return nt.find_resource('network', network_name)['id'] 


def get_subnet_id(subnet_name):
    nt = setup_neutronclient()
    return nt.find_resource('subnet', subnet_name)['id']


def get_router_id(router_name):
    nt = setup_neutronclient()
    return nt.find_resource('router', router_name)['id']


@celery.task(bind=True)
def async_create_user_networks(self, the_cooler_list, user_project):
    nt = setup_neutronclient()
    user_project_id = get_project_id(user_project)

    for key in the_cooler_list.keys():
        user_resource_base_name = user_project + '-' + key
        user_network_id = create_network(user_project_id, user_resource_base_name + '-Network')
        user_subnet_id = create_subnet(user_project_id, user_network_id, user_resource_base_name + '-Subnet', the_cooler_list[key]['subnets']['cidr'], the_cooler_list[key]['subnets']['gateway_ip'])

        if the_cooler_list[key]['router']:
            user_router_id = create_router(user_project_id, user_subnet_id, user_resource_base_name + '-Router', the_cooler_list[key]['router']['external_gateway_info']['network_id'])

@celery.task(bind=True)
def async_delete_user_networks(self, the_cooler_list, user_project):
    nt = setup_neutronclient()
    for key in the_cooler_list.keys():
        if user_project in the_cooler_list[key]['children']:
            if 'router' in the_cooler_list[key]['children'][user_project]:
                router_id = the_cooler_list[key]['children'][user_project]['router']['id']
                nt.remove_interface_router(router_id, body={'subnet_id': the_cooler_list[key]['children'][user_project]['subnets']['id']})
                nt.delete_router(router_id)
        
            nt.delete_network(the_cooler_list[key]['children'][user_project]['id'])

def toggle_network_dhcp(project, network, change):
    nt = setup_neutronclient()
    all_networks = merge_network_dicts(project, network)

    for network in all_networks:
        async_dhcp_toggle.delay(all_networks[network]['subnets']['id'], {'subnet': {'enable_dhcp': change}})


@celery.task(bind=True)
def async_dhcp_toggle(self, subnet_id, body):
    nt = setup_neutronclient()
    nt.update_subnet(subnet_id, body)


def toggle_network_port_security(project, network, change):
    nt = setup_neutronclient()
    all_networks = merge_network_dicts(project, network)

    for network in all_networks:
        async_ps_toggle.delay(all_networks[network]['id'], {'network': {'port_security_enabled': change}})


@celery.task(bind=True)
def async_ps_toggle(self, network_id, body):
    nt = setup_neutronclient()
    nt.update_network(network_id, body)


def toggle_network_internet_access(project, course, network, network_name, change):
    nt = setup_neutronclient()
    if change is False:
        router_delete_wrapper(project, network)
    elif change is True:
        router_create_wrapper(project, course, network_name, network)


def verify_network_integrity(course, network):
    nt = setup_neutronclient()
    projects = get_projects(course)
    
    networks = []
    if network:
        for name in network:
            networks.append(name)
    else:
        return

    problem_children = {}
    for n in networks:
        problem_children[n] = {}
        subnet_ip = network[n]['subnets']['cidr']
        gateway_ip = network[n]['subnets']['gateway_ip']
        
        for project in projects['students']:
            problem_children[n][project] = {}
            problem_list = []
            if not network[n]['children'].get(project):
                problem_list.append('NETWORK_NOT_FOUND')
            else:
                if not network[n]['children'][project].get('subnets'):
                    problem_list.append('SUBNET_NOT_FOUND')
                else:
                    if not 'cidr' in network[n]['children'][project]['subnets']:
                        problem_list.append('NO_CIDR_SET')
                    else:
                        if not network[n]['children'][project]['subnets']['cidr'] == subnet_ip:
                            problem_list.append('CIDR_IP_WRONG')
                    if not 'gateway_ip' in network[n]['children'][project]['subnets']:
                        problem_list.append('NO_GATEWAY_IP_SET')
                    else:
                        if not network[n]['children'][project]['subnets']['gateway_ip'] == gateway_ip:
                            problem_list.append('GATEWAY_IP_WRONG')
                    if 'router' not in network[n]['children'][project] and network[n]['router']:
                        problem_list.append('ROUTER_NOT_FOUND')
            if not problem_list:
                del problem_children[n][project]
            else:
                problem_children[n][project] = problem_list
    return problem_children

def fix_network_problems(problem_children, networks):
    fixed_networks = {}
    for network in problem_children:
        # If there are projects in the dict values (ergo, if problems exist)
        if any(problem_children[network].values()):
            fixed_networks[network] = {}
            # Iterate through the so-called 'problem children', child networks with config issues
            for project in problem_children[network]:
                network_name = network
                project_id = get_project_id(project)
                instructor_cidr = networks[network_name]['subnets']['cidr']
                instructor_gateway = networks[network_name]['subnets']['gateway_ip']

                fixed_networks[network][project] = {}
                fixed = []
                for problem in problem_children[network][project]:
                    if problem == 'NETWORK_NOT_FOUND':
                        # We can assume that if there's no network, then nothing else exists
                        network_name_full = project + '-' + network_name + '-Network'
                        network_id = create_network(project_id, network_name_full)
                        subnet_name = project + '-' + network_name + '-Subnet'
                        subnet_id = create_subnet(project_id, network_id, subnet_name, instructor_cidr, instructor_gateway)

                        # If internet access is enabled for this network
                        if networks[network_name]['router']:
                            router_name = project + '-' + network_name + '-Router'
                            external_network_id = networks[network_name]['router']['external_gateway_info']['network_id']
                            create_router(project_id, subnet_id, router_name, external_network_id)
                        fixed.append('Network "' + network_name + '" created for ' + project)
                    
                    if problem == 'SUBNET_NOT_FOUND': 
                        # If there's no subnet, then there's no CIDR IP, Gateway IP, or Router (if router is enabled)
                        full_network_name = project + '-' + network_name + '-Network'
                        network_id = get_network_id(full_network_name)
                        subnet_name = project + '-' + network_name + '-Subnet'
                        subnet_id = create_subnet(project_id, network_id, subnet_name, instructor_cidr, instructor_gateway)

                        if networks[network_name]['router']:
                            router_name = project + '-' + network_name + '-Router'
                            external_network_id = networks[network_name]['router']['external_gateway_info']['network_id']
                            create_router(project_id, subnet_id, router_name, external_network_id)
                        fixed.append('Subnet for "' + network_name + '" created for ' + project)
                    
                    if problem == 'NO_CIDR_SET':
                        pass
                        #fixed.append('CIDR IP added to "' + network_name + '" for ' + project)

                    if problem == 'CIDR_IP_WRONG': 
                        pass
                        #fixed.append('CIDR IP for "' + network_name + '" was corrected for ' + project)

                    if problem == 'NO_GATEWAY_IP_SET':
                        pass
                        #fixed.append('Gateway IP added to "' + network_name + '" for ' + project)

                    if problem == 'GATEWAY_IP_WRONG':
                        pass
                        #fixed.append('Gateway IP for "' + network_name + '" was corrected for ' + project)
                    
                    if problem == 'ROUTER_NOT_FOUND':
                        pass
                        #fixed.append('Router for "' + network_name + '" created for ' + project)

                    fixed_networks[network][project] = fixed
    return fixed_networks
                




