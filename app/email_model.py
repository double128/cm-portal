from app import app, celery
from app.keystone_model import get_user_email, get_username_from_email, get_user_id, reset_user_password
import requests
import os


def send_image_download_link(username, file_name):
    instructor_email = get_user_email(username)

    with open('./app/templates/email_templates/image-download.template', 'r') as file:
        data = file.read()

    email_body = data % file_name

    request = requests.post(app.config['MAILGUN_URL'], 
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': instructor_email,
                                'subject': 'Image Download Request',
                                'html': email_body})


@celery.task(bind=True)
def send_password_reset_info(self, username, email=False, keep_password=False):

    if email:
        username = get_username_from_email(username)

    if not get_user_id(username):
        return

    if keep_password:
        new_password = '[See Registration Email]'
    else:
        new_password = reset_user_password(username)
        if not new_password:
            return

    user_email = get_user_email(username)

    with open('./app/templates/email_templates/password-reset.template', 'r') as file:
        data = file.read()

    email_body = data % (username, new_password)

    request = requests.post(app.config['MAILGUN_URL'],
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': user_email,
                                'subject': 'Cloud Password Reset',
                                'html': email_body})


@celery.task(bind=True)
def send_new_course_info(self, username, course):

    user_email = get_user_email(username)

    with open('./app/templates/email_templates/new-course.template', 'r') as file:
        data = file.read()

    email_body = data % (course, username)

    request = requests.post(app.config['MAILGUN_URL'],
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': user_email,
                                'subject': 'New Cloud Course Available',
                                'html': email_body})


@celery.task(bind=True)
def send_ta_info(self, username, course):

    user_email = get_user_email(username)

    with open('./app/templates/email_templates/ta-course-info.template', 'r') as file:
        data = file.read()

    email_body = data % (course, username)

    request = requests.post(app.config['MAILGUN_URL'],
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': user_email,
                                'subject': 'Added as TA to Cloud Course',
                                'html': email_body})
