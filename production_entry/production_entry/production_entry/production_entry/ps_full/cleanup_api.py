import os

path = r"c:\Users\Admin\Planning\production_scheduler\production_scheduler\api.py"

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

clean_lines = []
for line in lines:
    if "Elisa:" not in line:
        clean_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(clean_lines)

print(f"Cleaned {len(lines) - len(clean_lines)} corrupted lines.")
