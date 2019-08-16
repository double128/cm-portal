function submitButton(clickedButton) {
	$('.submit-button').addClass('stop-interaction disabled');
	$(clickedButton).val("Please wait...").addClass('visual-changes');
};
