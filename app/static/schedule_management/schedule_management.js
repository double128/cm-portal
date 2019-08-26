        document.addEventListener('DOMContentLoaded', function() {
                var calendarEl = document.getElementById('calendar');

                var calendar = new FullCalendar.Calendar(calendarEl, {
                        plugins: [ 'interaction', 'dayGrid', 'timeGrid', 'bootstrap' ],
                        header: {
                        //        left: 'calendarmenu',
				left: '',
                                center: '',
                                right: 'prev, next, today',
                        },
			footer: {
				left: '',
				center: 'title',
				right: '',
			},

                        themeSystem: 'bootstrap',

                        defaultView: $(window).width() < 768 ? 'timeGridDay':'timeGridWeek',
                        windowResize: function changeCalendarView() {
                                      		var ww = $(window).width();
                                        	var view = (ww <= 768) ? 'timeGridDay':'timeGridWeek';
                                        	var currentView = calendar.view;
                                        	if (view != currentView) {
                                        		calendar.changeView(view);
                                       		}
                                        },
                        defaultDate: moment().format('YYYY-MM-DD'),
                        allDaySlot: false,
                        events: {
                                url: '/api/schedule',
                                failure: function() {
                                        document.getElementById('script-warning').style.display = 'block'
                                }
                        },

			eventClick: function(info) {
				var get_course = info.event._def.extendedProps.course;
				// Don't open the modal if the user doesn't own the entry
				if (get_course == $('.navbar-text').children('span').text().split('Schedule:')[1].trim()) {
					$('#view-event-modal-title').html(info.event.title);
					$('#event-creator').html(info.event._def.extendedProps.instructor);
					$('#event-start-time').html(moment(info.event.start).format('LT'));
					$('#event-end-time').html(moment(info.event.end).format('LT'));
					var event_id = info.event._def.extendedProps.event_id;
					$('#time_to_remove').attr('value', event_id);
					$('#viewEventModal').modal();
				}
			},

                        eventOverlap: false,
                        nowIndicator: true,
                        slotDuration: '01:00:00',

                        height: 'auto',
                        loading: function(bool) {
                                $('#loading').toggle(bool);
                        },
			minTime: '07:00:00',
			maxTime: '23:00:00',
                        
			firstDay: 0,
                });
		
                calendar.render();
        });

        $(function () {
                $('#starttimepicker').datetimepicker({ 
                        format: 'LT'
                });
                
		$('#endtimepicker').datetimepicker({ 
                        format: 'LT'
                });
        });

	$(function () {
		btn = $('#remove-time');
	});
