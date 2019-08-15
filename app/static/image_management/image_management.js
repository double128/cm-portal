$(document).ready(function() { 
	const button = $("input[type='submit']")
       	button.addClass("disable-buttons")
       	$("input[type='checkbox']").change(function() {
       	        if (this.checked) {
       	                button.removeClass("disable-buttons").css("cursor", "pointer");
       	        } else {
       	                button.addClass("disable-buttons").css("cursor", "not-allowed");
       	        }
       	});
        	
	{# Only allow one image at a time to be selected for download; this is the first of two checks, the backend can check as well just in case #}
       	$("input[name='download_image']").click(function(event) {
       	        var n = $("input[type='checkbox']:checked").length;
       	        if (n > 1) {
       	                alert("You can only select one image at a time to download.")
       	                event.preventDefault();
       	                location.reload();
       	        }
       	});
});

function submitButton(clickedButton) {
        $('.submit-button').addClass('stop-interaction');
        $(clickedButton).val("Please wait...").addClass('visual-changes');
};
