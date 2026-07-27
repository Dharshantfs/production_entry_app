# Clubbing Sheet — Before Save (RestrictedPython / Frappe Cloud safe)
# DocType: Clubbing Sheet | Event: Before Save
#
# Preferred: disable this site Server Script after deploying app hook:
#   production_entry.production_planning.clubbing_sheet_hooks.clubbing_sheet_before_save
#
# Uses only: doc, frappe
#
# Loading sequence: skipped when custom_lock_loading_sequence = 1 (Client Script sets on manual edit)
# Loading sequence: skipped when custom_lock_loading_sequence = 1 (set by Client Script on manual edit)

# ---------- 1) Fix customer from Sales Order ----------
for item in doc.items:
	if item.sales_order:
		correct_customer = frappe.db.get_value("Sales Order", item.sales_order, "customer")
		if correct_customer:
			item.customer = correct_customer

# ---------- 2) Total weight ----------
total = 0
for item in doc.items:
	total = total + frappe.utils.flt(item.weight_kgs)
doc.total_weight = total

# ---------- 3) Load type ----------
if not doc.items:
	doc.load_type = ""
else:
	customer_weights = {}
	for item in doc.items:
		if item.customer:
			w = customer_weights.get(item.customer, 0) + frappe.utils.flt(item.weight_kgs)
			customer_weights[item.customer] = w

	customers = list(customer_weights.keys())
	full_load_customers = []
	for c in customers:
		if customer_weights[c] >= 5000:
			full_load_customers.append(c)

	if full_load_customers:
		if len(customers) > 1:
			msg = frappe._(
				"Customer {0} has a total weight of {1} kgs (>= 5000 kgs). "
				"Orders >= 5000 kgs must be clubbed separately as a Full Load."
			).format(full_load_customers[0], customer_weights[full_load_customers[0]])
			frappe.throw(msg)
		doc.load_type = "Full Load"
	elif len(customers) >= 1:
		doc.load_type = "Part Load"
	else:
		doc.load_type = ""

# ---------- 4) Route compatibility ----------
if doc.items and len(doc.items) >= 2:
	ROUTE_BELTS = [
		["madurai", "virudhunagar", "sivakasi", "tuticorin", "thoothukudi"],
		["madurai", "karur", "coimbatore"],
		["madurai", "karur", "erode", "salem"],
		["madurai", "dindigul", "karur", "salem"],
		["madurai", "pondicherry", "puducherry", "vellore", "kanchipuram", "chennai"],
		["madurai", "trivandrum", "thiruvananthapuram", "changanacherry"],
		["madurai", "kollam", "kayankulam", "pathanamthitta", "kottayam"],
		["madurai", "coimbatore", "palakkad", "trissur", "thrissur", "ernakulam"],
		["madurai", "coimbatore", "pallakad", "trissur", "thrissur", "malappuram", "kozhikode", "calicut", "mahe", "kannur", "kasargod", "mangaluru", "mangalore", "uduppi", "udupi"],
		["madurai", "mysore", "mysuru", "hassan", "shimoga", "dawangeree", "davangere"],
		["madurai", "salem", "hosur", "bangalore", "bengaluru", "dawangeree", "davangere"],
		["madurai", "mysore", "mysuru", "bangalore", "bengaluru"],
		["madurai", "bangalore", "bengaluru", "tumkur", "hospet", "hospete", "koppal"],
		["madurai", "ananthapur", "kurnool", "hyderabad", "karimnagar"],
		["madurai", "ananthapur", "kurnool", "hyderabad", "nizambad"],
		["madurai", "kurnool", "hyderabad", "warangal"],
		["madurai", "vizag", "bhuvaneswar", "bhubaneswar", "cuttack"],
		["madurai", "brahmbur", "berhampur", "bhubaneswar", "cuttack"],
		["madurai", "guntur", "vijayawada", "kakinada"],
		["madurai", "kakinada", "vizag"],
		["madurai", "kuppam", "palamaner", "bangalore", "bengaluru"],
		["madurai", "bangalore", "bengaluru", "hospete", "hospet", "vijayapura"],
		["madurai", "bangalore", "bengaluru", "belgaum", "goa"],
		["madurai", "bangalore", "bengaluru", "hospete", "hospet", "vijayapura", "satara", "pune", "mumbai"],
	]

	selected_cities = []
	for item in doc.items:
		if item.party_location:
			c = item.party_location.strip().lower()
			if c not in selected_cities:
				selected_cities.append(c)

	if selected_cities:
		is_valid = False
		for belt in ROUTE_BELTS:
			all_in_belt = True
			for city in selected_cities:
				city_ok = False
				for bc in belt:
					if city == bc or city in bc or bc in city:
						city_ok = True
						break
				if not city_ok:
					all_in_belt = False
					break
			if all_in_belt:
				is_valid = True
				break

		if not is_valid and not doc.get("ignore_route_conflict"):
			frappe.throw(
				frappe._(
					"Route conflict detected! The selected cities do not fall together "
					"on any single established forward route/belt. Please verify or create separate Clubbing Sheets."
				)
			)

# ---------- 5) Distance + Loading sequence ----------
if doc.items:
	dm = {
		"Madurai": 0, "Melur": 30, "Usilampatti": 45, "Manamadurai": 60,
		"Sivaganga": 55, "Dindigul": 65, "Virudhunagar": 65, "Theni": 70,
		"Srivilliputhur": 75, "Aruppukottai": 80, "Sivakasi": 80,
		"Periyakulam": 85, "Tiruppathur": 90, "Oddanchatram": 95, "Sattur": 95,
		"Cumbum": 90, "Pudukkottai": 100, "Rajapalayam": 100,
		"Paramakudi": 130, "Kovilpatti": 130, "Palani": 120, "Ramanathapuram": 115,
		"Kodaikanal": 115, "Thenkasi": 115, "Tenkasi": 115, "Courtallam": 120,
		"Sankarankoil": 125, "Kumily": 130, "Gudalur": 130, "Munnar": 140,
		"Idukki": 145, "Karur": 140, "Tiruchirappalli": 135, "Trichy": 135,
		"Tirunelveli": 155, "Thoothukudi": 160, "Tuticorin": 160, "Perambalur": 160,
		"Ariyalur": 175, "Thanjavur": 175, "Pollachi": 180, "Kottayam": 185,
		"Namakkal": 200, "Alappuzha": 200, "Alleppey": 200, "Thodupuzha": 205,
		"Padmanabhapuram": 205, "Coimbatore": 210, "Tirupur": 215, "Kumbakonam": 215,
		"Ernakulam": 220, "Kochi": 220, "Cochin": 220, "Salem": 220,
		"Nagercoil": 230, "Erode": 240, "Muvattupuzha": 235, "Muvuttupuzha": 235,
		"Pala": 195, "Changanacherry": 195, "Pathanamthitta": 215,
		"Kollam": 250, "Quilon": 250, "Palakkad": 250, "Mayiladuthurai": 250,
		"Kanyakumari": 250, "Nilgiris": 265, "Ooty": 265, "Nagapattinam": 280,
		"Thrissur": 280, "Thiruvananthapuram": 290, "Trivandrum": 290,
		"Malappuram": 320, "Dharmapuri": 320, "Wayanad": 345, "Cuddalore": 365,
		"Kozhikode": 360, "Calicut": 360, "Villupuram": 370, "Mysuru": 370,
		"Mysore": 370, "Chamarajanagar": 390, "Mandya": 390, "Hosur": 385,
		"Pondicherry": 395, "Puducherry": 395, "Hassan": 395,
		"Tiruvannamalai": 400, "Virajpet": 405, "Kanchipuram": 440, "Vellore": 410,
		"Chengalpattu": 420, "Ramanagara": 420, "Kodagu": 420, "Madikeri": 420,
		"Kannur": 430, "Cannanore": 430, "Kolar": 430, "Bengaluru": 445,
		"Bangalore": 445, "Chikmagalur": 450, "Chennai": 455, "Tumkur": 475,
		"Puttur": 480, "Kasaragod": 490, "Mangaluru": 490, "Mangalore": 490,
		"Shimoga": 485, "Davangere": 510, "Nellore": 520, "Udupi": 530,
		"Tirupati": 530, "Hubli": 600, "Dharwad": 610, "Guntur": 650,
		"Vijayawada": 680, "Hyderabad": 770, "Warangal": 850, "Vizag": 970,
		"Berhampur": 1520, "Brahmapur": 1520, "Bhubaneswar": 1650,
		"Cuttack": 1680, "Puri": 1700, "Sambalpur": 1800, "Rourkela": 1850,
		"Krishnagiri": 355, "Pune": 1250, "Mumbai": 1450, "Chittoor": 480,
		"Karaikudi": 95,
	}

	for item in doc.items:
		if not frappe.utils.flt(item.distance_from_madurai):
			city = item.party_location or ""
			dist = 0
			if city in dm:
				dist = dm[city]
			else:
				city_lower = city.lower()
				for key in dm:
					if key.lower() == city_lower:
						dist = dm[key]
						break
				if dist == 0:
					for key in dm:
						if city_lower in key.lower() or key.lower() in city_lower:
							dist = dm[key]
							break
			item.distance_from_madurai = dist

	skip_auto_loading = 0
	if frappe.db.has_column("Clubbing Sheet", "custom_lock_loading_sequence"):
		skip_auto_loading = int(doc.get("custom_lock_loading_sequence") or 0)

	if not skip_auto_loading:
		ROUTE_BELTS2 = [
			["madurai", "virudhunagar", "sivakasi", "tuticorin", "thoothukudi"],
			["madurai", "karur", "coimbatore"],
			["madurai", "karur", "erode", "salem"],
			["madurai", "dindigul", "karur", "salem"],
			["madurai", "pondicherry", "puducherry", "vellore", "kanchipuram", "chennai"],
			["madurai", "trivandrum", "thiruvananthapuram", "changanacherry"],
			["madurai", "kollam", "kayankulam", "pathanamthitta", "kottayam"],
			["madurai", "coimbatore", "palakkad", "trissur", "thrissur", "ernakulam"],
			["madurai", "coimbatore", "pallakad", "trissur", "thrissur", "malappuram", "kozhikode", "calicut", "mahe", "kannur", "kasargod", "mangaluru", "mangalore", "uduppi", "udupi"],
			["madurai", "mysore", "mysuru", "hassan", "shimoga", "dawangeree", "davangere"],
			["madurai", "salem", "hosur", "bangalore", "bengaluru", "dawangeree", "davangere"],
			["madurai", "mysore", "mysuru", "bangalore", "bengaluru"],
			["madurai", "bangalore", "bengaluru", "tumkur", "hospet", "hospete", "koppal"],
			["madurai", "ananthapur", "kurnool", "hyderabad", "karimnagar"],
			["madurai", "ananthapur", "kurnool", "hyderabad", "nizambad"],
			["madurai", "kurnool", "hyderabad", "warangal"],
			["madurai", "vizag", "bhuvaneswar", "bhubaneswar", "cuttack"],
			["madurai", "brahmbur", "berhampur", "bhubaneswar", "cuttack"],
			["madurai", "guntur", "vijayawada", "kakinada"],
			["madurai", "kakinada", "vizag"],
			["madurai", "kuppam", "palamaner", "bangalore", "bengaluru"],
			["madurai", "bangalore", "bengaluru", "hospete", "hospet", "vijayapura"],
			["madurai", "bangalore", "bengaluru", "belgaum", "goa"],
			["madurai", "bangalore", "bengaluru", "hospete", "hospet", "vijayapura", "satara", "pune", "mumbai"],
		]

		all_belt_cities = []
		for belt in ROUTE_BELTS2:
			for bc in belt:
				if bc not in all_belt_cities:
					all_belt_cities.append(bc)

		selected_cities2 = []
		for item in doc.items:
			if item.party_location:
				c = item.party_location.strip().lower()
				if c not in selected_cities2:
					selected_cities2.append(c)

		known_selected = []
		for city in selected_cities2:
			found = False
			for bc in all_belt_cities:
				if city == bc or city in bc or bc in city:
					found = True
					break
			if found and city not in known_selected:
				known_selected.append(city)

		active_belt = []
		for belt in ROUTE_BELTS2:
			all_match = True
			if not known_selected:
				all_match = False
			for city in known_selected:
				city_ok = False
				for bc in belt:
					if city == bc or city in bc or bc in city:
						city_ok = True
						break
				if not city_ok:
					all_match = False
					break
			if all_match:
				active_belt = list(belt)
				break

		if not active_belt:
			max_matches = 0
			for belt in ROUTE_BELTS2:
				matches = 0
				for city in known_selected:
					for bc in belt:
						if city == bc or city in bc or bc in city:
							matches = matches + 1
							break
				if matches > max_matches:
					max_matches = matches
					active_belt = list(belt)

		sortable = []
		for item in doc.items:
			city_lower = frappe.utils.cstr(item.party_location or "").lower()
			priority = 0
			sort_val = frappe.utils.flt(item.distance_from_madurai)
			if active_belt:
				idx = 0
				while idx < len(active_belt):
					bc = active_belt[idx]
					if city_lower == bc or city_lower in bc or bc in city_lower:
						priority = 1
						sort_val = idx
						break
					idx = idx + 1
			sortable.append([priority, sort_val, item])

		n = len(sortable)
		i = 0
		while i < n:
			j = i + 1
			while j < n:
				swap = False
				if sortable[j][0] > sortable[i][0]:
					swap = True
				elif sortable[j][0] == sortable[i][0] and sortable[j][1] > sortable[i][1]:
					swap = True
				if swap:
					tmp = sortable[i]
					sortable[i] = sortable[j]
					sortable[j] = tmp
				j = j + 1
			i = i + 1

		if doc.load_type == "Full Load":
			for item in doc.items:
				item.loading_sequence = "Full Load"
		else:
			n = len(sortable)
			if n == 1:
				sortable[0][2].loading_sequence = "Full Load"
			elif n == 2:
				sortable[0][2].loading_sequence = "Inside"
				sortable[1][2].loading_sequence = "Outside"
			elif n > 2:
				sortable[0][2].loading_sequence = "Inside"
				sortable[n - 1][2].loading_sequence = "Outside"
				# DocType allows only Center 1 and Center 2 (not Center 3+)
				middle_count = n - 2
				center1_count = int((middle_count + 1) / 2)
				k = 1
				while k < n - 1:
					if (k - 1) < center1_count:
						sortable[k][2].loading_sequence = "Center 1"
					else:
						sortable[k][2].loading_sequence = "Center 2"
					k = k + 1

# ---------- 6) Bypass bad customer link display names ----------
doc.flags.ignore_links = True
