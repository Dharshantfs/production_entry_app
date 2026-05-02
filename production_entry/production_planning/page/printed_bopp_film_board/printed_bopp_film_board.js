frappe.pages["printed-bopp-film-board"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Printed BOPP Film Board",
		single_column: true,
	});

	$(page.body).html('<div id="printed-bopp-film-board-app"></div>');

	new production_scheduler.PrintedBoppFilmBoardController(
		document.getElementById("printed-bopp-film-board-app")
	);
};
