from production_entry.production_planning.bopp_bag_api import _parse_bopp_bag_item_code
from production_entry.production_planning.box_bag_api import _parse_box_bag_item_code, _parse_dcut_bag_item_code

print("BOPP Bag 1 (QCC):", _parse_bopp_bag_item_code("7465-2C-511-233B001QCC0M"))
print("BOPP Bag 2 (OCC):", _parse_bopp_bag_item_code("6003-0C-511-233A221OCC0M"))
print("BOPP Bag 231:", _parse_bopp_bag_item_code("6000-0C-511-231F001KCCMM"))
print("BOPP Bag 241:", _parse_bopp_bag_item_code("7465-2C-511-241F542OCCMM"))
print("BOPP Bag 242:", _parse_bopp_bag_item_code("7465-2C-511-242F542KCCCM"))
print("BOPP Bag 222:", _parse_bopp_bag_item_code("6003-0C-511-222F542Q00MM"))
print("BOPP Bag 223:", _parse_bopp_bag_item_code("7465-2C-511-223F542Q00MM"))
print("Box Bag (OCC):", _parse_box_bag_item_code("6003-0C-511-221A221OCC0M"))
print("D CUT 211:", _parse_dcut_bag_item_code("2500-201-211D542S00PP"))
print("D CUT 213:", _parse_dcut_bag_item_code("2500-201-213F542I0APP"))
print("D CUT 212:", _parse_dcut_bag_item_code("7465-2C-201-212D461Q00PP"))
print("D CUT 217:", _parse_dcut_bag_item_code("2500-1C-201-217D542KCCMM"))
print("W CUT 200:", _parse_dcut_bag_item_code("1000-001-200F542Q00PP"))
print("W CUT 201:", _parse_dcut_bag_item_code("1000-001-201F542Q00PP"))
print("W CUT 202:", _parse_dcut_bag_item_code("1000-001-202F542O0APP"))
print("D CUT 214:", _parse_dcut_bag_item_code("2500-1C-201-214F542KCCMM"))
print("W CUT 203:", _parse_dcut_bag_item_code("1000-001-203F542O0APP"))
# Production item codes (7465 design)
print("W CUT 203 (7465):", _parse_dcut_bag_item_code("7465-2C-001-203N201O0APP"))
print("D CUT 214 (7465):", _parse_dcut_bag_item_code("7465-2C-201-214F161Q0APP"))

if __name__ == "__main__":
    from production_entry.production_planning.scheduler_api import _item_process_prefix, _bom_item_process_code
    samples = [
        ("7465-2C-001-203N201O0APP", "203"),
        ("7465-2C-201-214F161Q0APP", "214"),
    ]
    ok = True
    for ic, exp in samples:
        got = _item_process_prefix(ic)
        bom = _bom_item_process_code(ic)
        if got != exp or bom != exp:
            ok = False
            print(f"FAIL {ic}: prefix={got} bom={bom} expected={exp}")
        else:
            print(f"OK {ic} -> {got}")
    if not ok:
        raise SystemExit(1)
