function submitButton(clickedButton) {
	$('.submit-button').addClass('stop-interaction');
	$(clickedButton).val("Please wait...").addClass('visual-changes');
};
