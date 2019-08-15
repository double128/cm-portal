$(document).ready(function() { 
	$("input[type='submit']").addClass("stop-interaction disabled");
	$("input[type='checkbox']").change(function() {
		var student_checkbox = $("input[name*='student_']").filter(":checked").length;
		var ta_checkbox = $("input[name*='ta_']").filter(":checked").length

		if ((student_checkbox == 0) && (ta_checkbox == 0)) {
			$("input[type='submit']").addClass("stop-interaction disabled");
		} else if ((student_checkbox >= 1) && (ta_checkbox == 0)) {
			$("input[type='submit']").removeClass("stop-interaction disabled");
		} else if ((student_checkbox >= 1) && (ta_checkbox >= 1)) {
			$("input[name*='designate_as_ta']").addClass("stop-interaction disabled");
		} else if ((student_checkbox == 0) && (ta_checkbox >= 1)) {
			$("input[name*='reset_password']").removeClass("stop-interaction disabled");
			$("input[name*='delete_student']").removeClass("stop-interaction disabled");
		}
	});
});

function submitButton(clickedButton) {
	$('.submit-button').addClass('stop-interaction');
	$(clickedButton).val("Please wait...").addClass('disabled');
};
