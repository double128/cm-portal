from app import db
import datetime

class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column('id', db.Integer, primary_key=True)
    course = db.Column('course', db.String(10), index=True, unique=True, nullable=False)
    instructor = db.Column('instructor', db.String(120), index=True, nullable=False)
    scheduled_times = db.relationship('Schedule', lazy='dynamic', backref=db.backref('course_code', lazy='joined'))

    def __repr__(self):
        return '<Course %s with Course ID %d>' % (self.course, self.id)


class Schedule(db.Model):
    __tablename__= 'schedule'
    id = db.Column('id', db.Integer, primary_key=True)
    weekday = db.Column('weekday', db.Integer, index=True, nullable=False)
    start_time = db.Column('start_time', db.Time, index=True, nullable=False)
    end_time = db.Column('end_time', db.Time, index=True, nullable=False)
    course_info = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)

    def __repr__(self):
        return '<Schedule for Course ID %d (Weekday %d %s to %s)>' % (self.course_info, self.weekday, self.start_time, self.end_time)

