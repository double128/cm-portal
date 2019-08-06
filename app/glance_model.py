from .keystone_model import *
from .exceptions import *
from .email_model import send_image_download_link
from glanceclient import Client as glanceclient

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

def download_image(username, image_name):
    gl = setup_glanceclient()
    for image in gl.images.list():
        if image.name == image_name:
            image_id = image.id
    #download = gl.images.data(image_id)

    #download = gl.images.data(image)
   # send_image_download_link(get_instructor_email(username))
