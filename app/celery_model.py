from app import app, celery
from app.keystone_model import process_new_user

@celery.task(bind=True)
def process_user(self, course, username, email):
    self.update_state(state='PENDING', 
        meta={'task': 'Adding new user ' + username + ' to ' + course, 'status': 'Pending'})
    return process_new_user(course, username, email, )
