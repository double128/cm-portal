from app import app
from app.keystone_model import get_instructor_email
import requests

def send_image_download_link(username, file_name):
    print('inside send_image_download_link')
    instructor_email = get_instructor_email(username)
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
                            
