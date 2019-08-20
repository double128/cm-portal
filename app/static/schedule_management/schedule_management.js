        document.addEventListener('DOMContentLoaded', function() {
                var calendarEl = document.getElementById('calendar');

                var calendar = new FullCalendar.Calendar(calendarEl, {
                        plugins: [ 'interaction', 'dayGrid', 'timeGrid', 'bootstrap' ],
                        header: {
                                left: 'title',
                                center: '',
                                right: 'prev, next, today',
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

                //$('. table').addClass('table');
                //        $('.fc-head').addClass('thead-light');

                //console.log(document.getElementsByTagName('table').length)
                //console.log($('#calendar table').length)
                //        $('#calendar table').removeClass('table-bordered').addClass('table table-bordered')
        });

        $(function () {
                $('#starttimepicker').datetimepicker({ 
                        format: 'LT'
                });
                
		$('#endtimepicker').datetimepicker({ 
                        format: 'LT'
                });
        });
