frappe.provide("production_entry.board_access_form");

const BOARD_SELECT_FALLBACK =
	"production-board|Production Board (Kanban)\n" +
	"printing-order-board|Printing Order Board\n" +
	"lamination-board|Lamination Board\n" +
	"slitting-board|Slitting Board\n" +
	"rewinding-board|Rewinding Board\n" +
	"sheet-cutting-board|Sheet Cutting Board\n" +
	"printed-bopp-film-board|Printed BOPP Film Board\n" +
	"box-bag-board|Box Bag Board\n" +
	"w-cut-d-cut-board|W CUT / D CUT Board\n" +
	"color-chart|Color Chart\n" +
	"confirm-orders|Confirm Orders\n" +
	"planning|Planning";

function applyBoardSelectOptions(frm, options) {
	const boards = frm.fields_dict.allowed_boards;
	if (boards && boards.grid) {
		boards.grid.update_docfield_property(
			"board",
			"options",
			options || BOARD_SELECT_FALLBACK
		);
	}
}

function decorateBoardAccessForm(frm) {
	if (!frm.$wrapper || frm.$wrapper.data("pp-board-access-styled")) return;
	frm.$wrapper.data("pp-board-access-styled", 1);

	const $main = frm.$wrapper.find(".form-layout").first();
	if ($main.length) {
		$main.prepend(
			`<div class="pp-board-access-banner" style="margin:0 0 14px;padding:14px 18px;border-radius:10px;background:linear-gradient(135deg,#eff6ff,#f0fdf4);border:1px solid #bfdbfe;">
				<div style="font-weight:700;font-size:15px;color:#1e3a8a;margin-bottom:6px;">Production Board Access</div>
				<div style="font-size:12px;color:#334155;line-height:1.5;">
					Assign by <strong>user name</strong> (search shows name + email). <strong>Many users can share the same unit</strong> (shift-wise).
					Add <strong>board only</strong> — table view access is automatic. Use <strong>Freeze</strong> columns to lock Maintenance / Transfer / Despatch / Arrangement buttons (visible but disabled).
				</div>
			</div>`
		);
	}

	if (frm.doc.user_full_name) {
		frm.dashboard.set_headline(
			`<span style="font-size:14px;color:#0f172a;">${frappe.utils.escape_html(frm.doc.user_full_name)}</span>
			 <span style="color:#64748b;font-size:12px;">(${frappe.utils.escape_html(frm.doc.user || "")})</span>`
		);
	}
}

frappe.ui.form.on("Production Board Access", {
	onload(frm) {
		frm.set_query("user", () => ({
			query:
				"production_entry.production_planning.board_access.production_board_access_user_query",
		}));
	},

	refresh(frm) {
		applyBoardSelectOptions(frm, BOARD_SELECT_FALLBACK);
		frappe.call({
			method:
				"production_entry.production_planning.board_access.get_production_board_page_options",
			callback: (r) => {
				if (r && r.message) {
					applyBoardSelectOptions(frm, r.message);
				}
			},
		});
		decorateBoardAccessForm(frm);

		const boards = frm.fields_dict.allowed_boards;
		if (boards && boards.grid) {
			boards.grid.wrapper.find(".grid-heading-row").css({
				background: "#f8fafc",
				"font-weight": "600",
			});
		}
	},

	user(frm) {
		if (frm.doc.user) {
			frappe.db.get_value("User", frm.doc.user, "full_name").then((r) => {
				if (r && r.message) {
					frm.set_value("user_full_name", r.message.full_name || "");
				}
			});
		}
	},
});
