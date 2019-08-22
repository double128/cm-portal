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
			
			//customButtons: {
			//	calendarmenu: {
			//		text: 'test',
			//		click: function() {
			//			$('.fc-calendarMenu-button').dropdown();
			//		},
			//	},
			//},

			//bootstrapFontAwesome: {
			//	calendarmenu: 'far fa-calendar-plus'
			//},

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
				$('#view-event-modal-title').html(info.event.title);
				var event_id = info.event._def.extendedProps.event_id;

				console.log($('#time_to_remove').val());
				$('#time_to_remove').attr('value', event_id);

				//if ($('#time_to_remove').value == 0) {
				//	console.log('empty')
				//};
				$('#viewEventModal').modal();
			},

                        eventOverlap: false,
                        nowIndicator: true,
                        slotDuration: '01:00:00',
                        snapDuration: '00:10:00',
                        height: 'auto',
                        loading: function(bool) {
                                $('#loading').toggle(bool);
                        }

                        //firstDay: 0,
                        //weekNumberCalculation: 'local',
                        //dateClick: function(info) {
                        //        alert('Clicked on: ' + info.dateStr);
                        //}
                        //eventClick: function(info) {
                        //        if (info.event.durationEditable == true) {
                        //                $('#modalTitle').html(info.event.title);
                        //        
                        //                document.getElementById('modalBody').innerHTML = '';
                        //                document.getElementById('modalBody').innerHTML += info.event.start
                        //                document.getElementById('modalBody').innerHTML += info.event.end
			//
                        //                $('#calendarModal').modal();
                        //        }
			//
                        //}
                });
		
                calendar.render();
 		

		//$('.fc-calendarmenu-button').attr('data-toggle', 'dropdown');
		//$('.fc-calendarmenu-button').addClass('dropdown-toggle');

		//$('.fc-calendarMenu-button').attr('id', 'calendar-menu-button').attr('data-toggle', 'dropdown').addClass('dropdown-toggle'); //.attr('data-offset', '0, 10');

		//$(window).resize(function() {
		//	if ($(window).width() < 1522) {
		//		$('.fc-calendarMenu-button').wrap("<div class='btn-group dropup'></div>");
		//	} else {
		//		$('.fc-calendarMenu-button').wrap("<div class='btn-group dropright'></div>");
		//	};
		//});

                //$('. table').addClass('table');
                //        $('.fc-head').addClass('thead-light');

                //console.log(document.getElementsByTagName('table').length)
                //console.log($('#calendar table').length)
                //        $('#calendar table').removeClass('table-bordered').addClass('table table-bordered')
        });

	//$(window).bind("load", function() {
	//	$('.fc-calendarmenu-button').wrap('<div class="dropdown"></div>');
	//	$('.fc-calendarmenu-button').addClass('dropdown-toggle');
	//	$('button[class*="fc-calendarmenu-button"]').attr('id', 'calendar-menu-button');
	//	$('button[class*="fc-calendarmenu-button"]').attr('data-toggle', 'dropdown');
	//	$('.fc-calendarmenu-button').append(`
	//		<div class='dropdown-menu'>
	//			<div class='dropdown-header'>Schedule Options</div>
	//				<a class='dropdown-item' href='#addScheduleTime' id='add_schedule_time' name='add_schedule_time' data-toggle='modal' data-target='#addScheduleTime'>Add Weekly Lab Session</a>
	//				<a class='dropdown-item' href='#deleteScheduleTime' id='delete_schedule_time' name='delete_schedule_time' data-toggle='modal' data-target='#deleteScheduleTime'>Remove Lab Session</a>
	//		</div>
	//	`);
	//});

        $(function () {
                $('#starttimepicker').datetimepicker({ 
                        format: 'LT'
                });
                
		$('#endtimepicker').datetimepicker({ 
                        format: 'LT'
                });
        });


