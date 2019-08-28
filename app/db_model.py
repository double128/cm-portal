from app import db, ma
import datetime

class Course(db.Model):
    __tablename__ = 'course'
    
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    course = db.Column('course', db.String(10), index=True, unique=True, nullable=False)
    instructor = db.Column('instructor', db.String(120), index=True, nullable=False)
    course_schedule = db.relationship('Schedule', backref='course_code', lazy='dynamic')

class Schedule(db.Model):
    __tablename__= 'schedule'
    
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    weekday = db.Column('weekday', db.Integer, index=True, nullable=False)
    start_hour = db.Column('start_hour', db.Integer, index=True, nullable=False)
    start_minute = db.Column('start_minute', db.Integer, index=True, nullable=False)
    end_hour = db.Column('end_hour', db.Integer, index=True, nullable=False)
    end_minute = db.Column('end_minute', db.Integer, index=True, nullable=False)

    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))


### MARSHMALLOW SCHEMAS ##############################

class ScheduleSchema(ma.ModelSchema):
    class Meta:
        model = Schedule
        fields = ('id', 'weekday', 'start_hour', 'start_minute', 'end_hour', 'end_minute', 'course_id')

class CourseSchema(ma.ModelSchema):
    course_schedule = ma.Nested(ScheduleSchema, many=True)
    class Meta:
        model = Course
