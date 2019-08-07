from .keystone_model import *
from .exceptions import *
from .email_model import send_image_download_link
from glanceclient import Client as glanceclient
from glanceclient.common import utils
import calendar
import time

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
                   G    L    A    N    C    E
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

def setup_glanceclient():
    sess = get_admin_session()
    gl = glanceclient('2', session=sess)
    return gl

def list_instructor_images(project, course):
    gl = setup_glanceclient()
    project_id = list(get_projects(course)['instructors'].values())[0]

    image_list = {}
    for image in gl.images.list():
        image_id = image.id
        # If we try to pull an image without the attribute "owner", the application will stack trace. So we need to filter out these images.
        if hasattr(image, 'owner') and hasattr(image, 'image_type'):
            if image.owner == project_id and image.image_type == 'snapshot':
                image_list[image.name] = image
    return image_list

def set_visibility(image):
    gl = setup_glanceclient()
    if image['visibility'] == 'public':
        gl.images.update(image['id'], visibility='private')
    elif image['visibility'] == 'private':
        gl.images.update(image['id'], visibility='public')

def download_image(username, course, image_name):
    print('inside download_image')
    gl = setup_glanceclient()
    
    for image in gl.images.list():
        if hasattr(image, 'owner') and hasattr(image, 'image_type'):
            if image.name == image_name and image.owner == list(get_projects(course)['instructors'].values())[0]:
                img_info = image
    
    img_data = gl.images.data(img_info.id)
    file_name = "downloads/%s-%s-%s.qcow2" % (calendar.timegm(time.gmtime()), course, img_info.name)
    utils.save_image(img_data, file_name)
    
    print('leaving download_image')
    send_image_download_link(username, file_name)
