from app import app
import requests

#def image_download_link_body():
#email_body = "################### THIS IS AN AUTOMATED EMAIL ####################### \
#        Your image is now available for download."



def send_image_download_link(instructor_email):
    request = requests.post(app.config['MAILGUN_URL'], 
                            auth=('api', app.config['MAILGUN_APIKEY']),
                            data={
                                'from': 'Cloudbot <cloudbot@hrl.uoit.ca>',
                                'to': instructor_email,
                                'subject': 'Image Download Request',
                                'text': 'haha made you look'})
    print('Status: '.format(request.status_code))
    print('Body: '.format(request.text))
                            
