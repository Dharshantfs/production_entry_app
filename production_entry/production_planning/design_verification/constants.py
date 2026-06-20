# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

import re

DIM_MM_RE = re.compile(
	r"(\d+(?:\.\d+)?)\s*mm\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm",
	re.I,
)
DIM_INCH_3_RE = re.compile(
	r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)",
	re.I,
)
DIM_INCH_2_RE = re.compile(
	r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)",
	re.I,
)
CMYK_RE = re.compile(r"C\s*(\d+)\s+M\s*(\d+)\s+Y\s*(\d+)\s+K\s*(\d+)", re.I)
PANTONE_RE = re.compile(r"PANTONE|PMS|\bP\s*\d", re.I)

INCH_TO_MM = 25.4

DEFAULT_LOGO_PHRASES = ["Varshine Tex"]

DEFAULT_GOV_PHRASES = [
	{"phrase": "Gov Gazette", "required": 1},
	{"phrase": "80 GSM", "required": 1},
	{"phrase": "80GSm Produce", "required": 0},
	{"phrase": "Make in India", "required": 1},
	{"phrase": "Swachh Bharat", "required": 1},
	{"phrase": "Swatch Bharath", "required": 0},
	{"phrase": "3R", "required": 1},
	{"phrase": "Quality Produce of India", "required": 1},
]


def _rule(bag_type, sno, particulars, sub_item, sub_particular, method, expected="", config=None, sort_order=0):
	label = particulars if not sub_particular else f"{particulars} - {sub_particular}"
	return {
		"bag_type": bag_type,
		"sno": sno,
		"particulars": particulars,
		"sub_item": sub_item or "",
		"sub_particular": sub_particular or "",
		"check_item": label.strip(" -"),
		"expected_measurement": expected or "",
		"check_method": method,
		"rule_config": config or {},
		"required_for_score": 1,
		"sort_order": sort_order,
	}


def get_box_bag_rules():
	rules = []
	order = 0

	def add(sno, particulars, sub_item, sub_particular, method, expected="", config=None):
		nonlocal order
		order += 1
		rules.append(_rule("Box Bag", sno, particulars, sub_item, sub_particular, method, expected, config, order))

	add(1, "Face area  Size", "a", "Face Width", "DimensionMatch", "305", {"field": "width", "expected_mm": 305})
	add(1, "Face area  Size", "b", "Face Height", "DimensionMatch", "380", {"field": "height", "expected_mm": 380})
	add(1, "Face area  Size", "c", "Gusset", "DimensionMatch", "110", {"field": "gusset", "expected_mm": 110})
	add(1, "Face area  Size", "d", "Top Folding", "DimensionMatch", "", {"field": "top_folding"})
	add(2, "Gazette Right Top", "a", "10mm gap from Side Celing", "MmAnnotationPresent", "10", {"values": [10], "tolerance": 0})
	add(2, "Gazette Right Top", "b", "8mm gap from Face Height", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(3, "Gazette Right  Bottom", "a", "10mm gap from Side Celing", "MmAnnotationPresent", "10", {"values": [10], "tolerance": 0})
	add(3, "Gazette Right  Bottom", "b", "8mm gap from Face Height", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(4, "Gazette Left  Top", "a", "10mm gap from Side Celing", "MmAnnotationPresent", "10", {"values": [10], "tolerance": 0})
	add(4, "Gazette Left  Top", "b", "8mm gap from Face width", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(5, "Gazette Left Bottom", "a", "10mm gap from Side Celing", "MmAnnotationPresent", "10", {"values": [10], "tolerance": 0})
	add(5, "Gazette Left Bottom", "b", "8mm gap from Face width", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(6, "No letter or image Matter in Side Gazette area bottom sealing area- (G/2)", "a", "Top Centre Gazette Area- VS (G/2) area", "ZoneEmpty", "", {"zone": "gusset_bottom_sealing"})
	add(6, "No letter or image Matter in Side Gazette area bottom sealing area- (G/2)", "b", "Bottom Centre Gazette Area- VS (G/2) area", "ZoneEmpty", "", {"zone": "gusset_bottom_sealing"})
	add(7, "letter or image Matter in Side Gazette area", "a", "Right Top Face folding + 10mm", "ZonePresent", "", {"zone": "gusset_right"})
	add(7, "letter or image Matter in Side Gazette area", "b", "Right Bottom Gazette Sealing (G/2)+5mm", "ZonePresent", "", {"zone": "gusset_right_bottom"})
	add(7, "letter or image Matter in Side Gazette area", "c", "Left Top Face folding + 10mm", "ZonePresent", "", {"zone": "gusset_left"})
	add(7, "letter or image Matter in Side Gazette area", "d", "Left Bottom Gazette Sealing (G/2)+5mm", "ZonePresent", "", {"zone": "gusset_left_bottom"})
	add(8, "Top Folding Area- Icons / Symbols / letters - 25mm", "a", "Right Top- (G/2)+35mm", "MmAnnotationPresent", "25", {"values": [25], "tolerance": 0})
	add(8, "Top Folding Area- Icons / Symbols / letters - 25mm", "b", "Right Bottom- (G/2)+35mm", "MmAnnotationPresent", "25", {"values": [25], "tolerance": 0})
	add(8, "Top Folding Area- Icons / Symbols / letters - 25mm", "c", "Left Top- (G/2)+35mm", "MmAnnotationPresent", "25", {"values": [25], "tolerance": 0})
	add(8, "Top Folding Area- Icons / Symbols / letters - 25mm", "d", "Right Bottom- (G/2)+35mm", "MmAnnotationPresent", "25", {"values": [25], "tolerance": 0})
	add(9, "Loop Handling Cutting Mark ( W x H ) 28mm x 4mm", "a", "Right Face width Centre", "ShapeDetect", "28x4", {"shape": "28x4"})
	add(9, "Loop Handling Cutting Mark ( W x H ) 22mm x 4mm", "b", "Left Face width Centre", "ShapeDetect", "22x4", {"shape": "22x4"})
	add(10, "Sheet Cutting Mark ( W x H ) 28mm x 2.5mm", "a", "Right Top", "ShapeDetect", "28x2.5", {"shape": "28x2.5"})
	add(10, "Sheet Cutting Mark ( W x H ) 28mm x 2.5mm", "b", "Right Bottom", "ShapeDetect", "28x2.5", {"shape": "28x2.5"})
	add(11, "Sheet Cutting Mark ( W x H ) 23mm x 2.5mm", "c", "Left Top", "ShapeDetect", "23x2.5", {"shape": "23x2.5"})
	add(11, "Sheet Cutting Mark ( W x H ) 23mm x 2.5mm", "d", "Left Bottom", "ShapeDetect", "23x2.5", {"shape": "23x2.5"})
	add(12, "Face area spill 8mm Spill Over Side Gazette", "a", "Left Top", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(12, "Face area spill 8mm Spill Over Side Gazette", "b", "Left Bottom", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(12, "Face area spill 8mm Spill Over Side Gazette", "c", "Right Top", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(12, "Face area spill 8mm Spill Over Side Gazette", "d", "Right Bottom", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(13, "Face area spill 5mm Spill Over Top Folding", "a", "Left Top Folding", "MmAnnotationPresent", "5", {"values": [5], "tolerance": 0})
	add(13, "Face area spill 5mm Spill Over Top Folding", "b", "Right Top Folding", "MmAnnotationPresent", "5", {"values": [5], "tolerance": 0})
	add(14, "Face Area spill 5mm Spill over Bottom", "", "", "MmAnnotationPresent", "5", {"values": [5], "tolerance": 0})
	add(15, "Face And Body Shouln't be cut", "a", "Left Face area", "SafeZone", "", {"zone": "face_left"})
	add(15, "Face And Body Shouln't be cut", "b", "Right Face area", "SafeZone", "", {"zone": "face_right"})
	add(16, "Registration Mark on the Top Folding Area with 6mm", "", "", "MmAnnotationPresent", "6", {"values": [6], "tolerance": 0})
	add(17, "QR Code scan- working", "", "", "QRDetect", "", {})
	add(18, "Left Side Top 1A ( Downward )", "", "", "TextMatch", "Layout outside", {"phrases": ["1A", "Layout outside"]})
	add(19, "Left Side Bottom 2B( Downward )", "", "", "TextMatch", "Layout outside", {"phrases": ["2B", "Layout outside"]})
	add(20, "Right  Side Top 1B ( Upward )", "", "", "TextMatch", "Layout outside", {"phrases": ["1B", "Layout outside"]})
	add(21, "Right  Side Bottom 2A ( Upward )", "", "", "TextMatch", "Layout outside", {"phrases": ["2A", "Layout outside"]})
	add(22, " Top folding area- Content Box Dimension", "a", "Left Table with letters Width", "DimensionMatch", "20", {"field": "content_box_w", "expected_mm": 20})
	add(22, " Top folding area- Content Box Dimension", "b", "Left table with letters Height", "DimensionMatch", "40", {"field": "content_box_h", "expected_mm": 40})
	add(22, " Top folding area- Content Box Dimension", "c", "Right table with image Width", "DimensionMatch", "20", {"field": "content_box_w2", "expected_mm": 20})
	add(22, " Top folding area- Content Box Dimension", "d", "Right table with image Height", "DimensionMatch", "60", {"field": "content_box_h2", "expected_mm": 60})
	add(23, " Top folding area- Content details", "a", "Left Top- 80GSm Produce- Gov Gazette", "TextMatch", "", {"phrases": ["Gov Gazette", "80 GSM", "80GSm Produce"]})
	add(23, " Top folding area- Content details", "b", "Left Bottom- Varshine Tex", "TextMatch", "", {"phrases": ["Varshine Tex"]})
	add(23, " Top folding area- Content details", "c", "Right Top- Make in India, Swatch Bharath", "TextMatch", "", {"phrases": ["Make in India", "Swachh Bharat", "Swatch Bharath"]})
	add(23, " Top folding area- Content details", "d", "Right Bottom- 3R, Quality Produce of India", "TextMatch", "", {"phrases": ["3R", "Quality Produce of India"]})
	add(24, "Equal space are given from Top & Bottom for whole design in Face area", "", "", "EqualSpacing", "", {"axis": "vertical"})
	add(25, "Equal space are given from Right & Left for whole design in Face area", "", "", "EqualSpacing", "", {"axis": "horizontal"})
	add(26, "Product code Added", "", "", "ProductCode", "", {})
	for letter in ("a", "b", "c", "d", "e"):
		add(27, "No. Of . Colours name with Pantone code", letter, "Colour Name", "PantonePattern", "", {"slot": letter})
	for letter in ("a", "b", "c", "d", "e"):
		add(28, "No. of . colours name with Cmyk code", letter, "Colour Name", "CMYKPattern", "", {"slot": letter})

	return rules


def get_dcut_rules():
	rules = []
	order = 1000

	def add(sno, particulars, sub_item, sub_particular, method, expected="", config=None):
		nonlocal order
		order += 1
		rules.append(_rule("D Cut", sno, particulars, sub_item, sub_particular, method, expected, config, order))

	add(1, "Face area  Size", "a", "Face Width", "DimensionMatch", "305", {"field": "width", "expected_mm": 305})
	add(1, "Face area  Size", "b", "Face Height", "DimensionMatch", "380", {"field": "height", "expected_mm": 380})
	add(1, "Face area  Size", "c", "Top Folding", "DimensionMatch", "", {"field": "top_folding"})
	add(2, "Sheet Cutting Mark ( W x H ) 20mm x 2.5mm", "a", "Right Top", "ShapeDetect", "20x2.5", {"shape": "20x2.5"})
	add(2, "Sheet Cutting Mark ( W x H ) 20mm x 2.5mm", "b", "Right Bottom", "ShapeDetect", "20x2.5", {"shape": "20x2.5"})
	add(2, "Sheet Cutting Mark ( W x H ) 20mm x 2.5mm", "c", "Left Top", "ShapeDetect", "20x2.5", {"shape": "20x2.5"})
	add(2, "Sheet Cutting Mark ( W x H ) 20mm x 2.5mm", "d", "Left Bottom", "ShapeDetect", "20x2.5", {"shape": "20x2.5"})
	add(3, "Image If any ( FaceTop folding + 10mm)", "a", "Left Sheet Face", "ZonePresent", "", {"zone": "top_folding"})
	add(3, "Image If any ( FaceTop folding + 10mm)", "b", "Right Sheet Face", "ZonePresent", "", {"zone": "top_folding"})
	add(4, "Face area spill 8mm Clearance from Sealing", "a", "Left Top", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(4, "Face area spill 8mm Clearance from Sealing", "b", "Left Bottom", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(4, "Face area spill 8mm Clearance from Sealing", "c", "Right Top", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(4, "Face area spill 8mm Clearance from Sealing", "d", "Right Bottom", "MmAnnotationPresent", "8", {"values": [8], "tolerance": 0})
	add(5, "Ensure a 10 mm gap from the face  bottom", "", "", "MmAnnotationPresent", "10", {"values": [10], "tolerance": 0})
	add(6, "Face And Body Shouln't be cut", "a", "Left Face area", "SafeZone", "", {"zone": "face_left"})
	add(6, "Face And Body Shouln't be cut", "b", "Right Face area", "SafeZone", "", {"zone": "face_right"})
	add(7, "Registration Mark on the Left Top Folding Area with 6mm", "", "", "MmAnnotationPresent", "6", {"values": [6], "tolerance": 0})
	add(8, "QR Code scan- working", "", "", "QRDetect", "", {})
	add(9, " Top folding area- Content Box Dimension", "a", "Left Table with letters Width", "DimensionMatch", "20", {"field": "content_box_w", "expected_mm": 20})
	add(9, " Top folding area- Content Box Dimension", "b", "Left table with letters Height", "DimensionMatch", "40", {"field": "content_box_h", "expected_mm": 40})
	add(9, " Top folding area- Content Box Dimension", "c", "Right table with image Width", "DimensionMatch", "20", {"field": "content_box_w2", "expected_mm": 20})
	add(9, " Top folding area- Content Box Dimension", "d", "Right table with image Height", "DimensionMatch", "60", {"field": "content_box_h2", "expected_mm": 60})
	add(10, " Top folding area- Content details", "a", "Left Top- 80GSm Produce- Gov Gazette", "TextMatch", "", {"phrases": ["Gov Gazette", "80 GSM"]})
	add(10, " Top folding area- Content details", "b", "Left Bottom- Varshine Tex ( if applicable )", "TextMatch", "", {"phrases": ["Varshine Tex"]})
	add(10, " Top folding area- Content details", "c", "Right Top- Make in India, Swatch Bharath", "TextMatch", "", {"phrases": ["Make in India", "Swachh Bharat"]})
	add(10, " Top folding area- Content details", "d", "Right Bottom- 3R, Quality Produce of India", "TextMatch", "", {"phrases": ["3R", "Quality Produce of India"]})
	add(11, "Equal space are given from Top & Bottom for whole design in Face area", "", "", "EqualSpacing", "", {"axis": "vertical"})
	add(12, "Equal space are given from Right & Left for whole design in Face area", "", "", "EqualSpacing", "", {"axis": "horizontal"})
	add(13, "Product code Added- If Applicable", "", "", "ProductCode", "", {})
	for letter in ("a", "b", "c", "d", "e"):
		add(14, "No. Of . Colours name with Pantone code", letter, "Colour Name", "PantonePattern", "", {"slot": letter})
	for letter in ("a", "b", "c", "d", "e"):
		add(15, "No. of . colours name with Cmyk code", letter, "Colour Name", "CMYKPattern", "", {"slot": letter})

	return rules


def get_all_default_rules():
	return get_box_bag_rules() + get_dcut_rules()
