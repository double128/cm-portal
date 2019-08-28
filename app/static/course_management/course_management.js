$(document).ready(function() { 
	$('input[class*="submit-button"]').addClass('stop-interaction disabled');
	$("input[id!='is_ta']").change(function() {
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

$(function() {
	$('#is_ta').click(function() {
		var state = $(this).is(':checked');
		if (state == true) {
			$('#email-append-text').html('@ontariotechu.ca');
		} else {
			$('#email-append-text').html('@ontariotechu.net');
		};
	});
});
