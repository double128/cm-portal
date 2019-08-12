from app import db

class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column('id', db.Integer, primary_key=True)
    course = db.Column('course', db.String(10), index=True, unique=True)
    instructor = db.Column('instructor', db.String(120), index=True)
    scheduled_times = db.relationship('schedule', backref='course_code', lazy='dynamic')

    def __repr__(self):
        return '<Course {}>'.format(self.course)


class Schedule(db.Model):
    __tablename__= "schedule"
    id = db.Column('id', db.Integer, primary_key=True)
    weekday = db.Column('weekday', db.Integer, index=True)
    start_time = db.Column('start_time', db.Time, index=True)
    end_time = db.Column('end_time', db.Time, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))

    def __repr__(self):
        return '<Schedule {}>'.format(self.course_id)


