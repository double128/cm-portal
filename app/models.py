from app import app, login
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
                try:
                    line = re.sub('\"|\n|\r\n|\r', '', line)
                    username = line.split(',')[4]
                    email = line.split(',')[9]
                    task = process_user.delay(course, username, email)
                except IndexError:
                    return render_template("500.html", error="Something is wrong with your .csv file formatting. Please make sure that the file has been formatted correctly before uploading again.")

