from app import app, login
from app.celery_model import process_user
import re

@login.user_loader
def load_user(id):
    if id in login.users:
        return login.users[id]
    else:
        return None


def process_csv(course, file):
    with open(file, 'r') as filehandle:  
        for line in filehandle:
            if '@uoit' in line:
                line = re.sub('\"|\n|\r\n|\r', '', line)
                username = line.split(',')[4]
                email = line.split(',')[9]
                task = process_user.delay(course, username, email)

