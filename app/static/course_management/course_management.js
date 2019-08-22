$(document).ready(function() { 
	$('input[class*="submit-button"]').addClass('stop-interaction disabled');
	$("input[type='checkbox']").change(function() {
		var checkbox = $(this).filter(':checked').length;
		if (checkbox == 0) {
			$('input[class*="submit-button"]').addClass("stop-interaction disabled");
		} else if (checkbox >= 1) {
			$('input[class*="submit-button"]').removeClass("stop-interaction disabled");
		}
	});
});

function submitButton(clickedButton) {
	$('.submit-button').addClass('stop-interaction');
	$(clickedButton).val("Please wait...").addClass('disabled');
};
