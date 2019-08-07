from app import app, celery

@celery.task(bind=True)
def example(self, message):
	print('Message: ' + message)
