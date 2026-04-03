import os

# Mocking frappe objects
class DictObj(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        return super().__getattribute__(name)

UNIT_QUALITY_ORDER = {
    "Unit 2": ["PREMIUM","PLATINUM","SUPER PLATINUM","GOLD","SILVER","BRONZE","CLASSIC","SUPER CLASSIC","LIFE STYLE","ECO SPECIAL","ECO GREEN","SUPER ECO","ULTRA","DELUXE"],
}

COLOR_ORDER_LIST = [
    "BRIGHT WHITE","SUPER WHITE","MILKY WHITE","SUNSHINE WHITE",
    "BLEACH WHITE 1.0","BLEACH WHITE 2.0","BLEACH WHITE","WHITE MIX","WHITE",
    "CREAM 2.0","CREAM 3.0","CREAM 4.0","CREAM 5.0",
    "GOLDEN YELLOW 4.0 SPL","GOLDEN YELLOW 1.0","GOLDEN YELLOW 2.0","GOLDEN YELLOW 3.0","GOLDEN YELLOW",
    "LEMON YELLOW 1.0","LEMON YELLOW 3.0","LEMON YELLOW",
    "BRIGHT ORANGE","DARK ORANGE","ORANGE 2.0",
    "PINK 7.0 DARK","PINK 6.0 DARK","DARK PINK","BABY PINK","PINK 1.0","PINK 2.0","PINK 3.0","PINK 5.0",
    "CRIMSON RED","RED","LIGHT MAROON","DARK MAROON","MAROON 1.0","MAROON 2.0",
    "BLUE 13.0 INK BLUE","BLUE 12.0 SPL NAVY BLUE","BLUE 11.0 NAVY BLUE",
    "BLUE 8.0 DARK ROYAL BLUE","BLUE 7.0 DARK BLUE","BLUE 6.0 ROYAL BLUE",
    "LIGHT PEACOCK BLUE","PEACOCK BLUE","LIGHT MEDICAL BLUE","MEDICAL BLUE",
    "ROYAL BLUE","NAVY BLUE","SKY BLUE","LIGHT BLUE",
    "BLUE 9.0","BLUE 4.0","BLUE 2.0","BLUE 1.0","BLUE",
    "PURPLE 4.0 BLACKBERRY","PURPLE 1.0","PURPLE 2.0","PURPLE 3.0","VOILET",
    "GREEN 13.0 ARMY GREEN","GREEN 12.0 OLIVE GREEN","GREEN 11.0 DARK GREEN",
    "GREEN 10.0","GREEN 9.0 BOTTLE GREEN","GREEN 8.0 APPLE GREEN",
    "GREEN 7.0","GREEN 6.0","GREEN 5.0 GRASS GREEN","GREEN 4.0",
    "GREEN 3.0 RELIANCE GREEN","GREEN 2.0 TORQUISE GREEN","GREEN 1.0 MINT",
    "MEDICAL GREEN","RELIANCE GREEN","PARROT GREEN","GREEN",
    "SILVER 1.0","SILVER 2.0","LIGHT GREY","DARK GREY","GREY 1.0",
    "CHOCOLATE BROWN 2.0","CHOCOLATE BROWN","CHOCOLATE BLACK",
    "BROWN 3.0 DARK COFFEE","BROWN 2.0 DARK","BROWN 1.0",
    "CHIKOO 1.0","CHIKOO 2.0",
    "BEIGE 1.0","BEIGE 2.0","BEIGE 3.0","BEIGE 4.0","BEIGE 5.0",
    "LIGHT BEIGE","DARK BEIGE","BEIGE MIX","BLACK MIX","COLOR MIX","BLACK",
]
COLOR_PRIORITY = {c: i for i, c in enumerate(COLOR_ORDER_LIST)}
def color_sort_key(c): return COLOR_PRIORITY.get(c, 9999)

def quality_sort_key(item, unit):
    order = UNIT_QUALITY_ORDER.get(unit, [])
    q = item["quality"]
    idx = order.index(q) if q in order else len(order)
    return (idx, item.get("gsm", 0))

def test_sequence():
    print("Testing Smart Sequence Logic...")
    
    # User Scenario: Last Order was RED / BRONZE
    # Items to push:
    # 1. GOLDEN YELLOW / BRONZE
    # 2. GOLDEN YELLOW / ULTRA
    # 3. RED / ULTRA
    # 4. PINK / BRONZE
    # 5. PINK / SILVER
    
    color_items = [
        {"name": "GY-BRONZE", "colorKey": "GOLDEN YELLOW", "quality": "BRONZE", "gsm": 80},
        {"name": "GY-ULTRA", "colorKey": "GOLDEN YELLOW", "quality": "ULTRA", "gsm": 80},
        {"name": "RED-ULTRA", "colorKey": "RED", "quality": "ULTRA", "gsm": 80},
        {"name": "PINK-BRONZE", "colorKey": "PINK 3.0", "quality": "BRONZE", "gsm": 80},
        {"name": "PINK-SILVER", "colorKey": "PINK 3.0", "quality": "SILVER", "gsm": 80},
    ]
    
    unit = "Unit 2"
    effective_seed = "BRONZE"
    current_seed_color = "RED"

    remaining = list(color_items)
    quality_order = UNIT_QUALITY_ORDER.get(unit, [])
    sequence = []
    seq_no = [0]
    
    max_loops = len(remaining) * 2 + 5
    loops = 0

    while remaining and loops < max_loops:
        loops += 1

        # 1. Check current color priority
        if current_seed_color and any(i["colorKey"] == current_seed_color for i in remaining):
            chosen_color = current_seed_color
            print(f"Loop {loops}: Picking color {chosen_color} (Priority Seed)")
        else:
            # 2. Transition quality logic
            qual_pool = [i for i in remaining if i["quality"] == effective_seed]
            print(f"Loop {loops}: Effective Quality={effective_seed}, Items in Quality={len(qual_pool)}")

            if not qual_pool:
                advanced = False
                if quality_order:
                    try:
                        qi = quality_order.index(effective_seed)
                    except ValueError:
                        qi = -1
                    search_order = quality_order[qi+1:] + quality_order[:qi+1] if qi != -1 else quality_order
                    for nq in search_order:
                        if any(i["quality"] == nq for i in remaining):
                            effective_seed = nq
                            advanced = True
                            current_seed_color = None
                            print(f"  --> Advancing Quality to {nq}")
                            break
                if not advanced:
                    effective_seed = remaining[0]["quality"]
                    current_seed_color = None
                continue

            # Sort colors in this quality light -> dark
            pool_colors = sorted(list({i["colorKey"] for i in qual_pool}), key=color_sort_key)
            
            if current_seed_color and current_seed_color in COLOR_PRIORITY:
                seed_idx = COLOR_PRIORITY[current_seed_color]
                valid_options = [c for c in pool_colors if COLOR_PRIORITY.get(c, -1) >= seed_idx]
                chosen_color = valid_options[0] if valid_options else pool_colors[0]
            else:
                chosen_color = pool_colors[0]
            print(f"  --> Picking next color: {chosen_color}")

        # 3. Batch EVERY item of 'chosen_color' across EVERY quality
        color_batch = sorted(
            [i for i in remaining if i["colorKey"] == chosen_color],
            key=lambda i: quality_sort_key(i, unit)
        )

        for i in color_batch:
            remaining.remove(i)

        for idx, item in enumerate(color_batch):
            seq_no[0] += 1
            sequence.append({
                **item,
                "sequence_no": seq_no[0]
            })
            print(f"    - Added Result: {item['name']} (Qual={item['quality']}, Color={item['colorKey']})")

        # Update seeds
        current_seed_color = chosen_color
        effective_seed = color_batch[-1]["quality"]
        print(f"  --> End of batch. New Seed Color={current_seed_color}, New Effective Qual={effective_seed}")

    print("\nFINAL SEQUENCE:")
    for s in sequence:
        print(f"{s['sequence_no']}. {s['colorKey']} / {s['quality']}")

test_sequence()
