from app import app, login, db
from app import keystone_model as keystone
import datetime
import re
import pytz

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
                #try:
                line = re.sub('\"|\n|\r\n|\r', '', line)
                username = line.split(',')[4]
                email = line.split(',')[9]
                keystone.process_new_users.delay(course, username, email)
                #except IndexError:
                #    return render_template("500.html", error="Something is wrong with your .csv file formatting. Please make sure that the file has been formatted correctly before uploading again.")

def convert_utc_to_eastern(utc):
    if str(type(utc)) != 'datetime.datetime':
        utc = datetime.datetime.combine(datetime.date.today(), utc)
    return pytz.utc.localize(utc, is_dst=None).astimezone(pytz.timezone('America/Toronto')).strftime('%l:%M %p').lstrip()
    

def convert_int_to_weekday(weekday):
    weekday_dict = {'0': 'Monday', '1': 'Tuesday', '2': 'Wendesday', '3': 'Thursday', '4': 'Friday', '5': 'Saturday', '6': 'Sunday'}
    return weekday_dict[weekday]
