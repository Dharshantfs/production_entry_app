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
