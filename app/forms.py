from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, IntegerField, SubmitField, SelectField, BooleanField, SelectMultipleField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length, IPAddress, InputRequired, ValidationError, StopValidation, Regexp

class LoginForm(FlaskForm):
    username = StringField('Username', default='test', render_kw={'placeholder': 'Username'}, validators=[DataRequired()])
    password = PasswordField('Password', render_kw={'placeholder': 'Password'}, validators=[DataRequired()])
    #course = IntegerField('Course', default=1111, render_kw={'placeholder': 'Course ID (ex. 1111)'}, validators=[DataRequired()])
    course = IntegerField('Course', default=1111, render_kw={'placeholder': 'Course ID (ex. 1111)'}, validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class UploadForm(FlaskForm):
    file = FileField('file', validators=[FileAllowed(['csv'], '.csv files only!'), FileRequired()])
    upload = SubmitField('Upload')


class QuotaForm(FlaskForm):
    instances_quota = SelectField('Instances', coerce=int)
    cores_quota = SelectField('Cores', coerce=int)
    ram_quota = SelectField('RAM', coerce=int)
    networks_quota = SelectField('Networks', coerce=int)
    subnets_quota = SelectField('Subnets', coerce=int)
    ports_quota = SelectField('Ports', coerce=int)
    fips_quota = SelectField('Floating IPs', coerce=int)
    routers_quota = SelectField('Routers', coerce=int)
    submit = SubmitField('Set Quota')

    def __init__(self, *args, **kwargs):
        super(QuotaForm, self).__init__(*args, **kwargs)
        quota_range = [(i, i) for i in range(1,11)]

        self.instances_quota.choices = quota_range
        self.cores_quota.choices = quota_range
        self.ram_quota.choices = [(512, '512 MB'), (1024, '1024 MB'), (2048, '2048 MB'), (4096, '4096 MB'), (8192, '8192 MB'), (16384, '16384 MB')]
        self.networks_quota.choices = quota_range
        self.subnets_quota.choices = quota_range
        self.ports_quota.choices = quota_range
        self.fips_quota.choices = quota_range
        self.routers_quota.choices = quota_range


#
# NETWORK FORMS 
#
#####################################

class CreateNetworkForm(FlaskForm):
    network_name = StringField('Network Name', validators=[InputRequired(), Length(max=32), Regexp('^[A-Za-z0-9\-]+$', message="Network name must only contain alphanumeric characters and hyphens (-).")])
    network_address = StringField('Network Address', validators=[InputRequired()])
    course_storage = StringField()
    create_network = SubmitField('Create Network')
    
    def validate_network_name(form, field):
        from app.neutron_model import setup_neutronclient
        nt = setup_neutronclient()
        try:
            if nt.list_networks(name=form.course_storage.data + '-Instructors-' + str(field.data) + '-Network')['networks'][0]['id']:
                raise ValidationError('A network with that name already exists.')
        except IndexError:
            pass

    def validate_network_address(form, field):
        import netaddr
        try:
            cidr = netaddr.IPNetwork(str(field.data) + '/24')
            if cidr.ip != cidr.network:
                raise ValidationError('Invalid network IP.')
        except netaddr.core.AddrFormatError:
            raise ValidationError('That is not a valid IP address.')
        except ValueError:
            raise ValidationError('That is not a valid IP address.')


class CheckNetworkForm(FlaskForm):
    check_network = SubmitField('Confirm')


class DeleteNetworkForm(FlaskForm):
    delete_network = SubmitField('Delete')


class EditNetworkForm(FlaskForm):
    dhcp_toggle = BooleanField('DHCP Enabled')
    port_security_toggle = BooleanField('Port Security Enabled')
    internet_access_toggle = BooleanField('Internet Access Enabled')
    edit_network = SubmitField('Save Configurations')

    def check_if_changed(self, submitted, previous):
        if submitted is not previous:
            return True #some change was made
        else:
            return False


class AcceptDeleteForm(FlaskForm):
    accept_delete = SubmitField('Delete')
    cancel = SubmitField('Cancel')


def create_image_checkbox_list(image_list):
    class MultipleCheckboxField(FlaskForm):
        pass
    
    keys = image_list.keys()
    for i, image in enumerate(keys):
        # Include a description that stores the visibility state of the image (public/private) for Jinja2 to sort the images into separate lists
        setattr(MultipleCheckboxField, 'image_%d' % i, BooleanField(label=image, description=image_list[image]['visibility']))
    
    setattr(MultipleCheckboxField, 'change_visibility', SubmitField('Change Visibility'))
    setattr(MultipleCheckboxField, 'download_image', SubmitField('Get Image Download Link'))
    return MultipleCheckboxField()

def create_student_checkbox_list(course_student_list):
    class MultipleCheckboxField(FlaskForm):
        pass
    
    keys = course_student_list.keys()
    for s, student in enumerate(keys):
        if 'nstructors' not in course_student_list[student]:
            setattr(MultipleCheckboxField, 'student_%d' % s, BooleanField(label=student, description=course_student_list[student]))
        else:
            setattr(MultipleCheckboxField, 'ta_%d' % s, BooleanField(label=student, description=course_student_list[student]))

    setattr(MultipleCheckboxField, 'reset_password', SubmitField('Reset Password'))
    setattr(MultipleCheckboxField, 'designate_as_ta', SubmitField('Designate Student as TA'))
    setattr(MultipleCheckboxField, 'delete_student', SubmitField('Delete Student'))
    return MultipleCheckboxField()
        

#class ImageManagementForm(FlaskForm):
#    #image_select = SelectMultipleField()
#    image_select = BooleanField()
