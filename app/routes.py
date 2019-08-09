from flask import render_template, flash, redirect, url_for, request, jsonify, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug import secure_filename
from werkzeug.urls import url_parse
from app import app, celery
from app.forms import LoginForm, UploadForm, QuotaForm, CreateNetworkForm, EditNetworkForm, AcceptDeleteForm
from app.models import process_csv
from . import cache
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

@app.route('/')
@login_required
def index():
    #jobs = inspect()
    #print(jobs.active())
    #return render_template('index.html', title='Home', projects=keystone.get_projects(current_user.course), active_jobs=jobs.active(), scheduled_jobs=jobs.scheduled())
    return render_template('index.html', title='Home', projects=keystone.get_projects(current_user.course))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        osession = keystone.OpenStackUser()

        if not osession.login(form.username.data, form.password.data, str(form.course.data)):
            flash('Login Failed')
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


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()

    if form.validate_on_submit():
        filename = secure_filename(form.file.data.filename)
        form.file.data.save('uploads/' + filename)
        process_csv(current_user.course, 'uploads/' + filename)
        return redirect(url_for('index'))

    return render_template('upload.html', form=form)


@app.route('/manage', methods=['GET', 'POST'])
@login_required
def course_management():
    from app.forms import create_student_checkbox_list
    #course_student_list = keystone.get_course_student_info(current_user.project, current_user.course)
    course_student_list = keystone.get_course_users(current_user.course)
    form = create_student_checkbox_list(course_student_list)
    
    if form.validate_on_submit():
        if form.reset_password.data is True:
            for submitted in form:
                if submitted.data is True and submitted.type == "BooleanField":
                    email.send_password_reset_info.delay(clean_html_tags(str(submitted.label)))
            flash("User password(s) have been reset")
        
        elif form.designate_as_ta.data is True:
            for submitted in form:
                if submitted.data is True and submitted.type == "BooleanField":
                    keystone.set_student_as_ta(clean_html_tags(str(submitted.label)), current_user.course)
            flash("Student has been designated as a course TA")
            return redirect(url_for('course_management'))
        
        elif form.delete_student.data is True:
            to_delete = []
            for submitted in form:
                if submitted.data is True and submitted.type == "BooleanField":
                    to_delete.append(clean_html_tags(str(submitted.label)))
            session['to_delete'] = to_delete
            return redirect(url_for('delete_students'))

    return render_template('course_management.html', course_student_list=course_student_list, course=current_user.course, form=form)


@app.route('/manage/delete', methods=['GET', 'POST'])
@login_required
def delete_students():
    form = AcceptDeleteForm()
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

    return render_template('delete_students.html', form=form, to_delete=to_delete)


@app.route('/manage/edit_quota', methods=['GET', 'POST'])
@login_required
def edit_quota():
    # Get quota details from the first student in the course
    student_quota = nova.get_project_quota(list(keystone.get_projects(current_user.course)['students'].values())[0])

    form = QuotaForm()
    if form.validate_on_submit():
        for pid in keystone.get_projects(current_user.course)['students'].values():
            print(pid)
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

    return render_template('edit_quota.html', form=form)


@app.route('/networks', methods=['GET', 'POST'])
@login_required
def network_panel():
    networks_list = neutron.list_project_network_details(current_user.project, current_user.course)
    # We're going to pass this to the specific network view through a session variable
    session['networks_list'] = networks_list
    return render_template('network.html', networks_list=networks_list)


@app.route('/networks/create', methods=['GET', 'POST'])
@login_required
def create_networks():
    form = CreateNetworkForm()
    if form.validate_on_submit():
        try:
            neutron.check_network_name(current_user.course, form.network_name.data)
        except exceptions.NetworkNameAlreadyExists as e:
            flash(e)
            return redirect(url_for('create_networks'))
        
        cidr = form.check_cidr()
        gateway = form.set_gateway(cidr)

        neutron.network_create_wrapper(current_user.project, current_user.course, form.network_name.data, cidr, gateway)

        flash('Network creation in progress')
        return redirect(url_for('index'))

    form.network_address.default = '192.168.0.0'
    form.process()

    return render_template('create_network.html', form=form)


@app.route('/networks/<network_name>_<network_id>', methods=['GET', 'POST'])
@login_required
def view_network(network_id, network_name):
    networks_list = session['networks_list']
    this_network = networks_list[network_name]

    return render_template('view_network.html', this_network=this_network, network_id=network_id, network_name=network_name)


@app.route('/networks/<network_name>_<network_id>/edit', methods=['GET', 'POST'])
@login_required
def modify_network(network_id, network_name):
    networks_list = session['networks_list']
    this_network = networks_list[network_name]
    network_id = this_network['id']
    subnet_id = this_network['subnets']['id']

    prev_dhcp_toggle = this_network['subnets']['enable_dhcp']
    prev_port_security_toggle = this_network['port_security_enabled']

    if this_network['router']:
        prev_internet_access_toggle = True
    else:
        prev_internet_access_toggle = False

    form = EditNetworkForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            dhcp_toggle_change = form.check_if_changed(form.dhcp_toggle.data, prev_dhcp_toggle)
            ps_toggle_change = form.check_if_changed(form.port_security_toggle.data, prev_port_security_toggle)
            internet_toggle_change = form.check_if_changed(form.internet_access_toggle.data, prev_internet_access_toggle)

            if dhcp_toggle_change is True:
                neutron.toggle_network_dhcp(this_network, form.dhcp_toggle.data)

            if ps_toggle_change is True:
                neutron.toggle_network_port_security(this_network, form.port_security_toggle.data)

            if internet_toggle_change is True:
                neutron.toggle_network_internet_access(current_user.project, current_user.course, this_network, network_name, form.internet_access_toggle.data)

            flash("Network configurations have been successfully updated")
            return redirect(url_for('view_network', network_name=network_name, network_id=network_id))

    if request.method == 'GET':
        form.dhcp_toggle.default = prev_dhcp_toggle
        form.port_security_toggle.default = prev_port_security_toggle
        form.internet_access_toggle.default = prev_internet_access_toggle
        form.process()

    return render_template('modify_network.html', form=form, network_id=network_id, network_name=network_name, this_network=this_network)


@app.route('/networks/<network_name>_<network_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_network(network_id, network_name):
    networks_list = session['networks_list']
    this_network = networks_list[network_name]
    try:
        subnet_id = this_network['subnets']['id']
    except TypeError:
        flash("Network create task has not finished yet. Please wait until the network has finished being created before deleting it.")
        return redirect(url_for('network_panel'))
    
    form = AcceptDeleteForm()
    
    if form.validate_on_submit():
        if form.accept_delete.data:
            neutron.network_delete_wrapper(current_user.project, current_user.course, this_network)
            flash('Network deletion in progress')
            return redirect(url_for('network_panel'))
    
        elif form.cancel.data:
            return redirect(url_for('view_network', network_id=network_id, network_name=network_name))

    return render_template('delete_network.html', form=form, network_id=network_id, network_name=network_name)


@app.route('/manage/images', methods=['GET', 'POST'])
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
            # Check if only one box is checked
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
                        flash("A download link will be sent to your email (%s) shortly" % keystone.get_instructor_email(current_user.id))
                        return redirect(url_for('image_management'))
    return render_template('image_management.html', image_list=image_list, form=form)

def clean_html_tags(html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', html)
    return cleantext

@app.route('/test', methods=['GET', 'POST'])
@login_required
def testing():
    keystone.get_course_users(current_user.course)
    return render_template('testing.html')


@app.route('/celery_test')
@login_required
def celery_test():
    worker.example.delay('hello world')
    return ''
