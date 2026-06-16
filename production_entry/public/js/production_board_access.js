frappe.provide("production_entry.board_access_form");

const BOARD_SELECT_OPTIONS =
	"production-board|Production Board (Kanban)\n" +
	"production-table|Production Table\n" +
	"printing-order-board|Printing Order Board\n" +
	"lamination-board|Lamination Board\n" +
	"slitting-board|Slitting Board\n" +
	"rewinding-board|Rewinding Board\n" +
	"sheet-cutting-board|Sheet Cutting Board\n" +
	"printed-bopp-film-board|Printed BOPP Film Board\n" +
	"box-bag-board|Box Bag Board\n" +
	"w-cut-d-cut-board|W-Cut / D-Cut Board\n" +
	"color-chart|Color Chart\n" +
	"confirm-orders|Confirm Orders\n" +
	"planning|Planning";

frappe.ui.form.on("Production Board Access", {
	refresh(frm) {
		const boards = frm.fields_dict.allowed_boards;
		if (boards && boards.grid) {
			boards.grid.update_docfield_property("board", "options", BOARD_SELECT_OPTIONS);
		}
	},
});
