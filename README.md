# cm-portal

## Structuring request bodies
### neutronclient
#### network
###### Create a network
```python
body = {'network': {'name': network_name, 
                    'project_id': project_id,
                    'description': network_description}}
neutronclient.create_network(body=body)
```

#### subnet
###### Create a subnet
```python
body = {'subnets': [{'name': subnet_name,
                     'cidr': subnet_cidr,
                     'gateway_ip': gateway_ip,
                     'network_id': network_id,
                     'project_id': project_id}]}
neutronclient.create_subnet(body=body)
```

###### Update a subnet
```python
# In this example, we want to disable DHCP
body = {'subnet': {'enable_dhcp': False}}
neutronclient.update_subnet(subnet_id, body=body)
```

## Writing functions
In all these examples, `nt` means "neutronclient".

#### Create router/external gateway
```python
# Get the ID of our external network which can reach the Internet
external_network = nt.list_networks(name='LAN')['networks'][0]['id']

# Create a body that sets up the router with a name, project ID, and external gateway info
router_body = {'router': {'name': 'Router_Name',
                          'project_id': project_id
                          'external_gateway_info': {
                            'network_id': external_network}}}

# Create the router
nt.create_router(body=router_body)

# Get the newly created router's ID
router_id = nt.list_routers(name='Router_Name')['routers'][0]['id']

# Create a body that adds an internal subnet to the router to use as a gateway
router_port_body = {'subnet_id': subnet_id}

# Add the internal interface to the router
nt.add_interface_router(router_id, body=router_port_body)
```
