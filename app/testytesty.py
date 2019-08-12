import calendar
import datetime
from dateutil import tz
import pytz
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



utc_time = datetime.time(19, 0, 0)
utc_time = datetime.datetime.combine(datetime.date.today(), utc_time)
print(utc_time)

#utc_time = utc_time.strftime('%H:%M:%S')
eastern_time = pytz.timezone('America/Toronto')


print(pytz.utc.localize(utc_time, is_dst=None).astimezone(eastern_time))

#tz = pytz.timezone('America/Toronto')
#utc_time = utc_time.replace(tzinfo=tz)
#print(utc_time)
#print(utc.replace(tzinfo=datetime.datetime.timezone.utc).astimezone(tz=to_zone))
