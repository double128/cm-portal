# DOCS
# novaclient https://docs.openstack.org/python-novaclient/queens/reference/api/index.html
# neutronclient https://www.pydoc.io/pypi/python-neutronclient-6.8.0/autoapi/v2_0/client/index.html (cert is invalid for some reason)
# keystoneclient https://docs.openstack.org/python-keystoneclient/queens/using-api-v3.html
#
from flask import render_template, flash, redirect, url_for, request, jsonify, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug import secure_filename
from werkzeug.urls import url_parse
from app import app, celery
#from app.forms import LoginForm, UploadForm, QuotaForm, CreateNetworkForm, EditNetworkForm, AcceptDeleteForm, CheckNetworkForm, DeleteNetworkForm
import app.forms as forms
from . import cache
#from app.models import process_csv, convert_utc_to_eastern
from app.models import convert_utc_to_eastern
from app.db_model import Course, Schedule, CourseSchema, ScheduleSchema
from app import db
from app import keystone_model as keystone
from app import nova_model as nova
from app import neutron_model as neutron
from app import glance_model as glance
from app import celery_model as worker
from app import email_model as email
from app import exceptions as exceptions
from celery.task.control import inspect
import re
import pprint
from datetime import date, time, timedelta, datetime
import dateutil.parser
import pytz
import calendar
import json
from datetimerange import DateTimeRange
from celery.schedules import crontab


@app.context_processor
def course_management_utils():
    return dict(convert_int_to_weekday=convert_int_to_weekday, convert_utc_to_eastern=convert_utc_to_eastern)


@app.route('/')
@login_required
def index():
    #jobs = inspect()
    #print(jobs.active())
    #return render_template('index.html', title='Home', projects=keystone.get_projects(current_user.course), active_jobs=jobs.active(), scheduled_jobs=jobs.scheduled())
    return render_template('index.html', title='Home', projects=keystone.get_projects(current_user.course), project_info=keystone.get_project_info(current_user.course),
            navbar_text = 'Course Overview: ' + current_user.course)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = forms.LoginForm()
    if form.validate_on_submit():
        osession = keystone.OpenStackUser()
        try:
            osession.login(form.username.data, form.password.data, str(form.course.data))
        except keystone.exceptions.http.Unauthorized:
            flash('Login failed', 'error')
            return redirect(url_for('login'))
        except exceptions.ClassInSession as e:
            flash(e.message, 'info')
            return redirect(url_for('login'))

        login_user(osession)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)


@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))


@app.route('/manage', methods=['GET', 'POST'])
@login_required
def course_management():
    from app.forms import create_student_checkbox_list

    course_student_list = keystone.get_course_users(current_user.course)
    course_form = create_student_checkbox_list(course_student_list)
    upload_form = forms.UploadForm()
    adduser_form = forms.AddUserForm()
    

    if adduser_form.add_user.data and adduser_form.validate_on_submit():
        if len(str(adduser_form.username.data)) == 6:
            username = '100' + str(adduser_form.username.data)
        else:
            adduser_form.username.errors.append('Your input must be 6 characters long')
            return redirect(url_for('course_management'))

        if adduser_form.is_ta.data == True:
            email = adduser_form.email.data + '@ontariotechu.ca'
        else:
            email = adduser_form.email.data + '@ontariotechu.net'
        print(username)
        print(email)
        
        keystone.add_user_manual(current_user.course, '100' + adduser_form.username.data, email, is_ta)

        flash('User has been successfully added.')
        return redirect(url_for('course_management'))

    elif course_form.reset_password.data or \
            course_form.toggle_ta_status.data or \
            course_form.delete_student.data and \
            course_form.validate_on_submit():
        print('INSIDE COURSE FORM VALIDATE')
        if course_form.reset_password.data is True:
            for submitted in course_form:
                if submitted.data is True and submitted.type == "BooleanField":
                    email.send_password_reset_info.delay(clean_html_tags(str(submitted.label)))
            flash("User password(s) have been reset")
        
        elif course_form.toggle_ta_status.data is True:
            for submitted in course_form:
                if submitted.data is True and submitted.type == "BooleanField":
                    field_id = clean_html_tags(str(submitted.id))
                    if 'student' in field_id:
                        current_role = 'student'
                    elif 'ta' in field_id:
                        current_role = 'ta'
                    keystone.toggle_ta_status(clean_html_tags(str(submitted.label)), current_user.course, current_role)
            flash("Role(s) have been modified.")
            return redirect(url_for('course_management'))
        
        elif course_form.delete_student.data is True:
            to_delete = {}
            for submitted in course_form:
                if submitted.data is True and submitted.type == "BooleanField":
                    to_delete[clean_html_tags(str(submitted.label))] = clean_html_tags(str(submitted.description))
            session['to_delete'] = to_delete
            return redirect(url_for('delete_students'))

    elif upload_form.upload.data and upload_form.validate_on_submit():
        filename = secure_filename(upload_form.file.data.filename)
        upload_form.file.data.save('uploads/' + filename)
        process_csv(current_user.course, 'uploads/' + filename)
        flash('Course list upload in progress')
        return redirect(url_for('index'))

    return render_template('course_management.html', 
            title='Course Management', 
            course_student_list=course_student_list, 
            course=current_user.course, 
            course_form=course_form, 
            upload_form=upload_form, 
            adduser_form=adduser_form,
            navbar_text='Course Management: ' + current_user.course,
            project_info=keystone.get_project_info(current_user.course))


@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule_management():
    add_time_form = forms.AddScheduleTimeForm()
    remove_time_form = forms.RemoveScheduleTimeForm()

    if add_time_form.validate_on_submit():
        # If this user doesn't have a course entry in the DB, add it
        if not Course.query.filter_by(course=current_user.course).first():
            new_course = Course(course=current_user.course, instructor=current_user.id)
            db.session.add(new_course)
            db.session.commit()
        
        db_course = Course.query.filter_by(course=current_user.course).first()
        db_course_id = db_course.id
        
        wd = add_time_form.weekday.data
        st = add_time_form.start_time.data
        et = add_time_form.end_time.data
        
        tz = pytz.timezone('America/Toronto')

        st = datetime.strptime(st, '%I:%M %p')
        et = datetime.strptime(et, '%I:%M %p')

        weekday_dict = {'Sun': 0, 'Mon': 1, 'Tues': 2, 'Wed': 3, 'Thurs': 4, 'Fri': 5, 'Sat': 6}
        today = datetime.utcnow().astimezone(tz)
        today_weekday = today.strftime('%a')
        for w in weekday_dict:
            if w == today_weekday:
                today_weekday = weekday_dict[w]

        week_date_list = {}
        week_start = today - timedelta(days=today_weekday)
        for d in range(7):
            week_date_list[str(d)] = week_start + timedelta(days=d)

        st = datetime.combine(week_date_list[wd].date(), st.time())
        st = tz.localize(st).astimezone(pytz.utc)
        et = datetime.combine(week_date_list[wd].date(), et.time())
        et = tz.localize(et).astimezone(pytz.utc)

        courses = Course.query.all()
        course_schedule = CourseSchema(many=True).dump(courses)
        
        for c in course_schedule:
            for t in c['course_schedule']:
                if int(t['weekday']) == int(wd):
                    c_st = t['start_time']
                    c_et = t['end_time']

                    if st >= c_st and et <= c_et:
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))

                    if st >= c_st and et <= c_et:
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))
                    
                    if st < c_st and et > c_et:
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))

        time_diff = et - st
        time_diff = time_diff.total_seconds()/3600
        if time_diff < 0:
            flash('Invalid time range for schedule entry (end time cannot be earlier than start time).', 'error')
            return redirect(url_for('schedule_management'))
        elif time_diff == 0:
            flash('Invalid time range for schedule entry (start time cannot be the same as end time).', 'error')
            return redirect(url_for('schedule_management'))
        
        wd = int(wd)
        start_hour = int(st.hour)
        start_minute = int(st.minute)
        end_hour = int(et.hour)
        end_minute = int(et.minute)

        new_time = Schedule(weekday=wd, start_hour=start_hour, start_minute=start_minute, end_hour=end_hour, end_minute=end_minute, course_id=db_course_id)
        db.session.add(new_time)
        db.session.commit()
        
        return redirect(url_for('schedule_management'))

    if remove_time_form.remove_time.data and remove_time_form.validate_on_submit():
        event_id = remove_time_form.time_to_remove.data
        entry = Schedule.query.get(event_id)
        db.session.delete(entry)
        db.session.commit()


    return render_template('schedule_management.html', 
            title='Schedule Management',
            add_time_form=add_time_form,
            remove_time_form=remove_time_form,
            navbar_text='Schedule: ' + current_user.course)


@app.route('/manage/delete', methods=['GET', 'POST'])
@login_required
def delete_students():
    form = forms.AcceptDeleteForm()
    to_delete = session['to_delete']

    if form.validate_on_submit():
        if form.accept_delete.data:
            keystone.delete_users(to_delete, current_user.course)
            session.pop('to_delete')
            flash('Users have been deleted')
            return redirect(url_for('course_management'))

        elif form.cancel.data:
            session.pop('to_delete')
            return redirect(url_for('course_management'))

    return render_template('delete_students.html', 
            title='Delete Students', 
            form=form, 
            to_delete=to_delete)


@app.route('/quota', methods=['GET', 'POST'])
@login_required
def edit_quota():
    # Get quota details from the first student in the course
    students = list(keystone.get_projects(current_user.course)['students'].values())
    if not students:
        flash('No students registered!')
        return redirect(url_for('index'))

    #student_quota = nova.get_project_quota(list(keystone.get_projects(current_user.course)['students'].values())[0])
    student_quota = nova.get_project_quota(students[0])

    form = forms.QuotaForm()

    form.instances_quota.choices = [(i, i) for i in range(1, int(app.config['QUOTA_INSTANCES_MAX'])+1)]
    form.cores_quota.choices = [(i, i) for i in range(1, int(app.config['QUOTA_CORES_MAX'])+1)]

    ram_values = []
    for i in range(1024, int(app.config['QUOTA_RAM_MAX'])+1, 1024):
        if i <= 8192 and i % 1024 == 0:
            ram_values.append((i, str(i)+' MB'))
        elif i % 2048 == 0:
            ram_values.append((i, str(i)+' MB'))

    form.ram_quota.choices = ram_values
    form.networks_quota.choices = [(i, i) for i in range(1, int(app.config['QUOTA_NETWORKS_MAX'])+1)]

    if form.validate_on_submit():
        for pid in keystone.get_projects(current_user.course)['students'].values():
            nova.update_project_quota.delay(pid, form.instances_quota.data, form.cores_quota.data, form.ram_quota.data, form.networks_quota.data,
                    form.networks_quota.data, int(form.networks_quota.data)*10, form.instances_quota.data, form.networks_quota.data) 
        flash('Quota updated')
        return redirect(url_for('index'))

    # Make default value equal to whatever's currently set
    form.instances_quota.default = student_quota['instances']
    form.cores_quota.default = student_quota['cores']
    form.ram_quota.default= student_quota['ram']
    form.networks_quota.default = student_quota['network']
    
    form.process()

    return render_template('edit_quota.html', 
            title='Edit Quota', 
            form=form,
            navbar_text='Quota: ' + current_user.course)


@app.route('/networks', methods=['GET', 'POST'])
@login_required
def network_panel():
    networks_list = neutron.list_project_network_details(current_user.course)
    
    create_form = forms.CreateNetworkForm()
    check_form = forms.CheckNetworkForm()
    delete_form = forms.DeleteNetworkForm()
    edit_form = forms.create_edit_network_list(networks_list)

    if networks_list:
        previous_values = {}
        for network in networks_list:
            prev_dhcp_toggle = networks_list[network]['subnets']['enable_dhcp']
            prev_port_security_toggle = networks_list[network]['port_security_enabled']
            if networks_list[network].get('router'):
                prev_internet_access_toggle = True
            else:
                prev_internet_access_toggle = False
            previous_values[network] = {'dhcp': prev_dhcp_toggle, 'port_security': prev_port_security_toggle, 'internet_access': prev_internet_access_toggle}

    create_form.course_storage.data = current_user.course # Store the course value in the form so the validator can use it
    if create_form.create_network.data and create_form.validate_on_submit():
        if not create_form.errors:
            neutron.network_create_wrapper(current_user.project, current_user.course, create_form.network_name.data, create_form.network_address.data)
            flash('Network creation in progress')
            return redirect(url_for('index'))
    
    if check_form.check_network.data and check_form.validate_on_submit():
        problems = neutron.verify_network_integrity(current_user.course, networks_list)
        fixed = neutron.fix_network_problems(problems, networks_list)

        flash('Networks have been checked and repaired')
        return redirect(url_for('network_panel'))

    
    if edit_form and edit_form.validate_on_submit():
        for n in networks_list:
            submit_button = 'edit_network_' + n
            delete_button = 'delete_network_' + n
            if submit_button in request.form:
                new_dhcp_toggle = request.form.get('dhcp_toggle_' + n)
                if new_dhcp_toggle:
                    new_dhcp_toggle = True
                else:
                    new_dhcp_toggle = False
                new_ps_toggle = request.form.get('port_security_toggle_' + n)
                if new_ps_toggle:
                    new_ps_toggle = True
                else:
                    new_ps_toggle = False
                new_internet_toggle = request.form.get('internet_access_toggle_' + n)
                if new_internet_toggle:
                    new_internet_toggle = True
                else:
                    new_internet_toggle = False

                dhcp_check = check_if_change(previous_values[n]['dhcp'], new_dhcp_toggle)
                ps_check = check_if_change(previous_values[n]['port_security'], new_ps_toggle)
                internet_check = check_if_change(previous_values[n]['internet_access'], new_internet_toggle)

                if dhcp_check is True:
                    neutron.toggle_network_dhcp(current_user.project, networks_list[n], new_dhcp_toggle)    
                if ps_check is True:
                    neutron.toggle_network_port_security(current_user.project, networks_list[n], new_ps_toggle)
                if internet_check is True:
                    neutron.toggle_network_internet_access(current_user.project, current_user.course, networks_list[n], n, new_internet_toggle)

                flash('Network configurations are being updated')
                return redirect(url_for('index'))
            
            elif delete_button in request.form:
                neutron.network_delete_wrapper(current_user.project, current_user.course, networks_list[n])
                flash('Network deletion in progress')
                return redirect(url_for('index'))

    return render_template('network.html', title='Networks', 
            networks_list=networks_list, 
            create_form=create_form, check_form=check_form, 
            delete_form=delete_form, edit_form=edit_form,
            navbar_text='Networks: ' + current_user.course)


@app.route('/images', methods=['GET', 'POST'])
@login_required
def image_management():
    image_list = glance.list_instructor_images(current_user.project, current_user.course)
    from app.forms import create_image_checkbox_list
    form = create_image_checkbox_list(image_list)

    if form.validate_on_submit():
        if form.change_visibility.data is True:
            for submitted in form:
                if submitted.type == "BooleanField":
                    if submitted.data is True:
                        glance.set_visibility(image_list[clean_html_tags(str(submitted.label))])
            flash("Image visibility updated")
            return redirect(url_for('image_management'))

        elif form.download_image.data is True:
            # Check if only one box is checked, there is a jquery check for this on the webpage itself but it's good to have a backup plan
            form_dict = form.data
            boolean_list = []
            for key in form_dict:
                if 'image_' in key:
                    boolean_list.append(form_dict[key])
            
            if boolean_list.count(True) > 1:
                flash("You can only select one image at a time for download.")
                return redirect(url_for('image_management'))

            else:
                for submitted in form:
                    if submitted.type == "BooleanField" and submitted.data is True:
                        glance.download_image(current_user.id, current_user.course, clean_html_tags(str(submitted.label)))
                        flash("A download link will be sent to your email (%s) shortly" % keystone.get_user_email(current_user.id))
                        return redirect(url_for('image_management'))
    
    return render_template('image_management.html', 
            title='Image Management', 
            image_list=image_list, 
            form=form, 
            navbar_text='Images: ' + current_user.course)


######################################
#
# API Functions
#
######################################

@app.route('/api/reset-d617hd83nvjfer4', methods=['POST'])
def api_password_reset():
    if request.form['sender'] and request.form['sender'].split('@')[1] in app.config['EMAIL_DOMAINS']:
        email.send_password_reset_info.delay(request.form['sender'].lower(), email=True)
        return jsonify({'Result': 'OK'})
    else:
        return jsonify({'Error': 'Invalid Request'})


@app.route('/api/schedule', methods=['GET'])
def api_get_schedule():
    #if not hasattr(current_user, 'id'):
    #    if not request.args.get('token') and not request.args.get('token') == app.config['API_TOKEN']:
    #      return jsonify({ 'Error': 'Invalid Token'})

    # If we get a REST request from fullcalendar, make "today" the start of the week (Sunday)
    if request.args.get('start') and request.args.get('end'):
        today = dateutil.parser.parse(request.args.get('start'))
    else:
        today = date.today()

    courses = Course.query.all()
    result = CourseSchema(many=True).dump(courses)
    tz = pytz.timezone('America/Toronto')   
    
    schedule_list = []
    week_date_list = {}
    # Start of week will always be Sunday, so we don't have to set our "week start" value like we do in schedule_management()
    for d in range(7):
        week_date_list[str(d)] = today + timedelta(days=d)

    for r in result:
        for t in r['course_schedule']:
            course_dict = {}
            
            course_dict['title'] = r['course'] + ' Lab Session'
            course_dict['instructor'] = r['instructor']
            course_dict['course'] = r['course']
            
            for w in week_date_list:
                if w == str(t['weekday']):
                    start_time = time(t['start_hour'], t['start_minute'])
                    end_time = time(t['end_hour'], t['end_minute'])
                    
                    start_time = pytz.utc.localize(start_time)
                    end_time = pytz.utc.localize(end_time)

                    start_time = datetime.combine(week_date_list[w], start_time)
                    end_time = datetime.combine(week_date_list[w], end_time)
                    
                    start_time = start_time.astimezone(tz)
                    end_time = end_time.astimezone(tz)

                    # Have to re-use this because the dates will be wrong if the time is after 8PM EDT, and the UTC->Eastern conversion will set the time to be the next day
                    start_time = datetime.combine(week_date_list[w], start_time.time())
                    end_time = datetime.combine(week_date_list[w], end_time.time())
                    
                    course_dict['start'] = start_time.isoformat()
                    course_dict['end'] = end_time.isoformat()
                    course_dict['weekday'] = t['weekday']
                    course_dict['event_id'] = t['id']
                    
                    if hasattr(current_user, 'course') and course_dict['course'] == current_user.course:
                        #course_dict['editable'] = True # Current user owns this event so let them edit it
                        #course_dict['startEditable'] = False
                        #course_dict['durationEditable'] = False
                        #course_dict['durationEditable'] = False
                        #course_dict['resourceEditable'] = False
                        #course_dict['startEditable'] = False
                        course_dict['editable'] = True
                        course_dict['backgroundColor'] = '#3498DB'
                        course_dict['borderColor'] = '#3498DB'
                    elif 'Open Weekend' in course_dict['course']:
                        course_dict['backgroundColor'] = '#18BC9C'
                        course_dict['borderColor'] = '#18BC9C'
                    else:
                        course_dict['editable'] = False
                        course_dict['backgroundColor'] = '#ccc'
                        course_dict['borderColor'] = '#ccc'
            schedule_list.append(course_dict)

    return jsonify(schedule_list)


@app.route('/api/cron', methods=['GET'])
def api_cron_tasks():

    if not request.args.get('token') and not request.args.get('token') == app.config['API_TOKEN']:
      return jsonify({ 'Error': 'Invalid Token'})

    # Get current time in EST/EDT in ISO formatting
    current_time = datetime.now() #.astimezone(pytz.timezone('America/Toronto'))
    course_schedule = api_get_schedule().json # We can use the function above since it's already parsed nicely
    current_time = datetime(2019, 8, 28, 14, 0, 0) #.astimezone(pytz.timezone('America/Toronto'))
    print('CURRENT TIME: ' + str(current_time))

    for c in course_schedule:

        if 'Open Weekend' in c['title']:
            continue

        course = c['course']
        start_time = dateutil.parser.parse(c['start']) #.astimezone(pytz.timezone('America/Toronto'))
        end_time = dateutil.parser.parse(c['end']) #.astimezone(pytz.timezone('America/Toronto'))
        print(c['title'] + ': ' + str(start_time) + ' -> ' + str(end_time))

        if current_time.weekday() == 5 or current_time.weekday() == 6:
            print('Open Weekend')
            keystone.enable_disable_projects(c['title'].split(' ')[0], True)

        elif start_time.day == current_time.day:
           
            course_time_before = start_time - timedelta(minutes=app.config['COURSE_TIME_BUFFER'])
            course_time_after = end_time + timedelta(minutes=app.config['COURSE_TIME_BUFFER'])

            if course_time_before <= current_time < course_time_after:
                print('Course running')
                keystone.enable_disable_projects(c['title'].split(' ')[0], True)
                keystone.enable_disable_projects('-Group', False)

        else:
            print('Course not running')
            keystone.enable_disable_projects(c['title'].split(' ')[0], False)
            keystone.enable_disable_projects('-Group', True)

    return 'ok'


#@app.before_first_request
#def setup_periodic_tasks(sender, **kwargs):
#    sender.add_periodic_task(10.0, test.s('hello'), name='add every 10s')


######################################
#
# USEFUL FUNCTIONS 
#
######################################

def check_if_change(prev, curr):
    if prev == curr:
        return False
    else:
        return True


def clean_html_tags(html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', html)
    return cleantext


def set_datetime_variables(start_hour, start_minute, end_hour, end_minute):
    time_range = {}
    start_time = time(start_hour, start_minute)
    end_time = time(end_hour, end_minute)
    time_range['start'] = start_time
    time_range['end'] = end_time
    return time_range


def convert_int_to_weekday(weekday):
    weekday_dict = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    return weekday_dict[weekday]


def get_week_dates(today):
    weekday = today.weekday()
    start = today - timedelta(days=weekday)
    datelist = []
    for d in range(6):
        datelist.append(start + timedelta(days=d))
    datelist.append(today - timedelta(days=7))
    return datelist


def process_csv(course, file):
    with open(file, 'r') as filehandle:
        for line in filehandle:
            line = re.sub('\"|\n|\r\n|\r', '', line)
            if '@' in line:
                try:
                    username = line.split(',')[4]
                    email = line.split(',')[9]
                    keystone.process_new_users.delay(course, username, email)
                except IndexError:
                    return render_template("500.html", error="Something is wrong with your .csv file formatting. Please make sure that the file has been formatted correctly before uploading again.")
            if 'Group' or 'group' in line:
                try:
                    group_id = line.split(',')[1]
                    for username in line.split(',')[2:]:
                        print('Group ' + group_id + ' add ' + username)
                        keystone.process_new_users(course, username, None, group_id)
                except IndexError:
                    return render_template("500.html", error="Something is wrong with your .csv file formatting. Please make sure that the file has been formatted correctly before uploading again.")

######################################
#
# TEST ZONE
# 
######################################

# @app.route('/test', methods=['GET', 'POST'])
# @login_required
# def testing():
#     #networks_list = neutron.list_project_network_details(current_user.course)
#     #neutron.verify_network_integrity(current_user.course, networks_list)

#     #courses = Course.query.all()
#     #result = CourseSchema(many=True).dump(courses)
#     #print(result)

#     return render_template('testing.html')

