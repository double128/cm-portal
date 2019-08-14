$(document).ready(function() { 
	$("input[type='submit']").addClass("disable-buttons")
	$("input[type='checkbox']").change(function() {
		var student_checkbox = $("input[name*='student_']").filter(":checked").length;
		var ta_checkbox = $("input[name*='ta_']").filter(":checked").length

		if ((student_checkbox == 0) && (ta_checkbox == 0)) {
			$("input[type='submit']").addClass("disable-buttons");
		} else if ((student_checkbox >= 1) && (ta_checkbox == 0)) {
			$("input[type='submit']").removeClass("disable-buttons");
		} else if ((student_checkbox >= 1) && (ta_checkbox >= 1)) {
			$("input[name*='designate_as_ta']").addClass("disable-buttons");
		} else if ((student_checkbox == 0) && (ta_checkbox >= 1)) {
			$("input[name*='reset_password']").removeClass("disable-buttons");
			$("input[name*='delete_student']").removeClass("disable-buttons");
		}
	});
});

function submitButton(clickedButton) {
	$('.submit-button').addClass('stop-interaction');
	$(clickedButton).val("Please wait...").addClass('visual-changes');
};
