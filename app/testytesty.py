import calendar
#from datetime import time
import datetime
#import time
#import datetime as dt
#from datetime import date, timedelta, datetime

# JUST TESTING SOME STUFF, LEARNING HOW 2 USE DATETIME, I DON'T LIKE THIS

def get_dates_for_weekday(day):
    year = datetime.now().year
    date_object = date(year, 1, 1)
    date_object += timedelta(days=day-date_object.isoweekday())

    date_list = []
    while date_object.year == year or date_object.year == (year - 1):
        date_object += timedelta(days=7)
        date_list.append(date_object)
    return date_list

def set_datetime_variables(start_hour, start_minute, end_hour, end_minute):
    time_range = []
    start_time = datetime.time(start_hour, start_minute)
    end_time = datetime.time(end_hour, end_minute)
    time_range.append(start_time)
    time_range.append(end_time)
    return time_range


print(set_datetime_variables(16, 40, 19, 0))
