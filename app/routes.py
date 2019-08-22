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
    return render_template('index.html', title='Home', projects=keystone.get_projects(current_user.course),
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
    
    if course_form.validate_on_submit():
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

    if upload_form.upload.data and upload_form.validate_on_submit():
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
            navbar_text='Course Management: ' + current_user.course)


@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule_management():
    add_time_form = forms.AddScheduleTimeForm()
    remove_time_form = forms.RemoveScheduleTimeForm()

    if add_time_form.validate_on_submit():
        #db_course = Course.query.filter_by(course=current_user.course).first()

        # If this user doesn't have a course entry in the DB, add it
        if not Course.query.filter_by(course=current_user.course).first():
            new_course = Course(course=current_user.course, instructor=current_user.id)
            db.session.add(new_course)
            db.session.commit()
        
        db_course = Course.query.filter_by(course=current_user.course).first()
        db_course_id = db_course.id
        
        weekday = add_time_form.weekday.data
        st = add_time_form.start_time.data
        et = add_time_form.end_time.data

        # Convert string input to datetime object
        st = datetime.strptime(st, '%I:%M %p')
        et = datetime.strptime(et, '%I:%M %p')

        # Add associated date with times (for proper UTC calculations)
        week_dates = get_week_dates(date.today())
        for w in week_dates:
            if int(w.weekday()) == int(weekday):
                st = datetime.combine(w, st.time())
                et = datetime.combine(w, et.time())
        
        # Make object TZ-aware
        tz = pytz.timezone('America/Toronto')
        st = tz.localize(st)
        et = tz.localize(et)

        # Convert to UTC
        st_utc = st.astimezone(pytz.utc)
        et_utc = et.astimezone(pytz.utc)

        # Convert to epoch value to store in DB and do comparisons
        st_utc = st_utc.replace(tzinfo=pytz.utc).timestamp() * 1000
        et_utc = et_utc.replace(tzinfo=pytz.utc).timestamp() * 1000
    
        courses = Course.query.all()
        course_schedule = CourseSchema(many=True).dump(courses)

        for c in course_schedule:
            for t in c['course_schedule']:
                if int(t['weekday']) == int(weekday):
                    c_st = t['start_time']
                    c_et = t['end_time']

                    if st_utc >= c_st and st_utc <= c_et:
                        #msg = 'The time you have entered overlaps with "' + str(c['title']) + '" (' + c_st.strftime('%A') + ' @ ' + c_st.strftime('%I:%M %p') + '-' + c_et.strftime('%I:%M %p') + ').'
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))

                    if et_utc >= c_st and et_utc <= c_et:
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))
                    
                    if st_utc < c_st and et_utc > c_et:
                        msg = 'The time you have entered conflicts with an existing entry.'
                        flash(msg, 'error')
                        return redirect(url_for('schedule_management'))
        
        time_diff = et_utc - st_utc 
        if time_diff < 0:
            flash('Invalid time range for schedule entry (end time cannot be earlier than start time).', 'error')
            return redirect(url_for('schedule_management'))
        elif time_diff == 0:
            flash('Invalid time range for schedule entry (start time cannot be the same as end time).', 'error')
            return redirect(url_for('schedule_management'))

        new_time = Schedule(weekday=weekday, start_time=st_utc, end_time=et_utc, course_id=db_course_id)
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


@app.route('/manage/edit_quota', methods=['GET', 'POST'])
@login_required
def edit_quota():
    # Get quota details from the first student in the course
    student_quota = nova.get_project_quota(list(keystone.get_projects(current_user.course)['students'].values())[0])

    form = forms.QuotaForm()
    if form.validate_on_submit():
        for pid in keystone.get_projects(current_user.course)['students'].values():
            nova.update_project_quota.delay(pid, form.instances_quota.data, form.cores_quota.data, \
                     form.ram_quota.data, form.networks_quota.data, form.subnets_quota.data, \
                     form.ports_quota.data, form.fips_quota.data, form.routers_quota.data)
        flash('Quota updated')
        return redirect(url_for('course_management'))

    # Make default value equal to whatever's currently set
    form.instances_quota.default = student_quota['instances']
    form.cores_quota.default = student_quota['cores']
    form.ram_quota.default= student_quota['ram']
    form.networks_quota.default = student_quota['network']
    form.subnets_quota.default = student_quota['subnet']
    form.ports_quota.default = student_quota['port']
    form.fips_quota.default = student_quota['floatingip']
    form.routers_quota.default = student_quota['router']
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

    if edit_form.validate_on_submit():
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


def check_if_change(prev, curr):
    if prev == curr:
        return False
    else:
        return True


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


#
# API 
#
######################################

@app.route('/api/reset', methods=['POST'])
def api_password_reset():
    if request.form['sender']: 
        print(request.form['sender'])
        email.send_password_reset_info.delay(request.form['sender'].lower())
        return jsonify({'Result': 'OK'})
    else:
        return jsonify({'Error': 'Invalid Request'})


@app.route('/api/schedule', methods=['GET'])
def api_get_schedule():

    #if not request.args.get('token') and not request.args.get('token') == app.config['API_TOKEN']:
    #   return jsonify({ 'Error': 'Invalid Token'})

    # If we get a request from fullcalendar with a date, then set the end date to today
    if request.args.get('start') and request.args.get('end'):
        today = dateutil.parser.parse(request.args.get('end'))
    else:
        today = date.today()

    courses = Course.query.all()
    #result = CourseSchema(many=True).dump(courses).data
    result = CourseSchema(many=True).dump(courses)
    tz = pytz.timezone('America/Toronto')   
    
    schedule_list = []
    for r in result:
        for t in r['course_schedule']:
            course_dict = {}
            course_dict['title'] = r['course'] + ' Lab Session'
            course_dict['instructor'] = r['instructor']
            course_dict['course'] = r['course']
            
            week_dates = get_week_dates(today)
            for w in week_dates:
                if w.weekday() == t['weekday']:
                    start = datetime.fromtimestamp(t['start_time']/1000)
                    start = pytz.utc.localize(start)
                    start = start.astimezone(tz)
                    start = datetime.combine(w, start.time())
                    end = datetime.fromtimestamp(t['end_time']/1000)
                    end = pytz.utc.localize(end)
                    end = end.astimezone(tz)
                    end = datetime.combine(w, end.time())
                    
                    course_dict['start'] = start.isoformat()
                    course_dict['end'] = end.isoformat()
                    course_dict['weekday'] = w.weekday()
                    course_dict['event_id'] = t['id']
                    
                    if course_dict['instructor'] == current_user.id:
                        #course_dict['editable'] = True # Current user owns this event so let them edit it
                        #course_dict['startEditable'] = False
                        #course_dict['durationEditable'] = False
                        #course_dict['durationEditable'] = False
                        #course_dict['resourceEditable'] = False
                        #course_dict['startEditable'] = False
                        course_dict['editable'] = False
                    else:
                        course_dict['editable'] = False
                        course_dict['backgroundColor'] = '#ccc'
                        course_dict['borderColor'] = '#ccc'

            schedule_list.append(course_dict)
    return jsonify(schedule_list)


@app.route('/api/cron', methods=['GET'])
def api_cron_tasks():

    #if not request.args.get('token') and not request.args.get('token') == app.config['API_TOKEN']:
    #   return jsonify({ 'Error': 'Invalid Token'})

    # Get current time in EST/EDT in ISO formatting
    #current_time = datetime.now().astimezone(pytz.timezone('America/Toronto'))
    course_schedule = get_schedule().json # We can use the function above since it's already parsed nicely

    #test_time = datetime(2019, 8, 20, 13, 0, 0).astimezone(pytz.timezone('America/Toronto'))
    current_time = datetime(2019, 8, 20, 18, 0, 0).astimezone(pytz.timezone('America/Toronto'))
    print('CURRENT TIME:')
    print(current_time)

    for c in course_schedule:
        course = c['course']
        start_time = dateutil.parser.parse(c['start'])
        end_time = dateutil.parser.parse(c['end'])
    
        print('')
        print(course)
        
        print(c['title'])
        print(start_time)
        print(end_time)

        if start_time.day == current_time.day:
            # Set variable for COURSE_TIME_BUFFER minutes before and after the course is scheduled
            course_time_before = start_time - timedelta(minutes=app.config['COURSE_TIME_BUFFER'])
            course_time_after = end_time + timedelta(minutes=app.config['COURSE_TIME_BUFFER'])

            # Current time is <= COURSE_TIME_BUFFER minutes before the scheduled time
            if course_time_before <= current_time < start_time:
                print('[Current time is <= 30 minutes before scheduled time]')
                # Iterate through student projects for this course and enable them, so long as they aren't enabled already

            
            # The course is running at this time
            elif start_time <= current_time <= end_time:
                print('[Course is currently scheduled for the current time]')
                

            # Current time is <= COURSE_TIME_BUFFER minutes after the scheduled time
            elif end_time < current_time <= course_time_after:
                print('[Current time is <= 30 minutes after scheduled time]')
                # Disable the student projects, but ONLY if there's no other session scheduled for this course right now or a session coming up in 30 minutes
                for c2 in course_schedule:
                    if course in c2['course']:
                        print('found other schedule for ' + course)

            else:
                print('[Course is not running anytime soon]')
                # if $RANDOM_CHOSEN_STUDENT_PROJECT is enabled then:
                #   disable

        else:
            print('[Scheduled time is not today]')
            # if $RANDOM_CHOSEN_STUDENT_PROJECT is enabled then:
            #   disable


    
    return 'ok'

#@app.before_first_request
#def setup_periodic_tasks(sender, **kwargs):
#    sender.add_periodic_task(10.0, test.s('hello'), name='add every 10s')

#
# USEFUL FUNCTIONS 
#
######################################

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
    return [start + timedelta(days=d) for d in range(7)]


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

#
# TEST ZONE
# 
######################################

@app.route('/test', methods=['GET', 'POST'])
@login_required
def testing():
    #networks_list = neutron.list_project_network_details(current_user.course)
    #neutron.verify_network_integrity(current_user.course, networks_list)

    #courses = Course.query.all()
    #result = CourseSchema(many=True).dump(courses)
    #print(result)

    return render_template('testing.html')

