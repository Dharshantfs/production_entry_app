from production_entry.production_planning.bopp_bag_api import _parse_bopp_bag_item_code
from production_entry.production_planning.box_bag_api import _parse_box_bag_item_code

print("BOPP Bag 1 (QCC):", _parse_bopp_bag_item_code("7465-2C-511-233B001QCC0M"))
print("BOPP Bag 2 (OCC):", _parse_bopp_bag_item_code("6003-0C-511-233A221OCC0M"))
print("Box Bag (OCC):", _parse_box_bag_item_code("6003-0C-511-221A221OCC0M"))
