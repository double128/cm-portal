from app import app, celery
from app.keystone_model import get_user_email, reset_user_password
import requests

def send_image_download_link(username, file_name):
    instructor_email = get_user_email(username)
    email_body = """<pre>
    ################### THIS IS AN AUTOMATED EMAIL #######################
    Your image is now available for download <a href="https://cloud.hrl.uoit.ca/%s">here</a>.
    This download link will only be valid for <b>24 hours</b>.
    </pre>""" % file_name

    request = requests.post(app.config['MAILGUN_URL'], 
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': instructor_email,
                                'subject': 'Image Download Request',
                                'html': email_body})
    #print('Status: '.format(request.status_code))
    #print('Body: '.format(request.text))

@celery.task(bind=True)
def send_password_reset_info(self, username):
    new_password = reset_user_password(username)
    if not new_password:
       return
    user_email = get_user_email(username)
    email_body = """<pre>
    ################### THIS IS AN AUTOMATED EMAIL #######################
    Your instructor has requested a password reset for your account, %s.
    Your password has been reset to <b>%s</b>. Please change it as soon as possible.
    </pre>""" % (username, new_password)

    request = requests.post(app.config['MAILGUN_URL'],
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': user_email,
                                'subject': 'Cloud Password Reset',
                                'html': email_body})
