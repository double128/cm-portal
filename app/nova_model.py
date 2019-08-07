from app import celery
from novaclient import client as novaclient
from .keystone_model import * 
from .neutron_model import setup_neutronclient

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
                       N    O    V    A
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
def setup_novaclient():
    nv = novaclient.Client(version='2.1', session=get_admin_session())
    return nv
    
def get_project_quota(student_project_id):
    nv = setup_novaclient()
    nt = setup_neutronclient()
    
    nova_quota = nv.quotas.get(tenant_id=student_project_id)
    nova_quota_list = vars(nova_quota)['_info']
    
    neutron_quota = nt.show_quota(project_id=student_project_id)
    neutron_quota_list = neutron_quota['quota']

    # Merge them into a new dict
    merged_dict = { **nova_quota_list, **neutron_quota_list }

    # Grab all the important stuff from that dict and make a new one
    keys = ['cores', 'instances', 'ram', 'network', 'subnet', 'port', 'router', 'floatingip']
    quota_dict = dict((k, merged_dict[k]) for k in (keys))
    
    return quota_dict

@celery.task(bind=True)
def update_project_quota(self, student_project_id, instanceq, coreq, ramq, netq, subq, portq, fipq, routerq):
    nv = setup_novaclient()
    nt = setup_neutronclient()

    nv.quotas.update(tenant_id=student_project_id, instances=instanceq, cores=coreq, ram=ramq)
    nt.update_quota(project_id=student_project_id, body = {'quota': {
                                                    'network': netq, 
                                                    'subnet': subq, 
                                                    'port': portq, 
                                                    'floatingip': fipq, 
                                                    'router': routerq}}) 
