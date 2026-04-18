# Production Planning App - Installation Guide

## Overview
This custom ERPNext app provides intelligent production planning and queuing across multiple manufacturing units based on quality, GSM, and unit capacity.

## Features
- **Automatic Unit Allocation**: Based on quality grades and GSM values
- **Capacity Management**: Track day/night shift capacities for each unit
- **Queue Management**: Automatic queue positioning based on delivery dates
- **Real-time Status**: View current queue and available capacity
- **Quality-based Routing**: 
  - Unit 1: High quality (SUPER PLATINUM, PLATINUM, PREMIUM, GOLD, SUPER CLASSIC) with GSM > 50
  - Unit 2: Medium quality (GOLD, SILVER, BRONZE, CLASSIC, ECO SPECIAL) with GSM > 20
  - Unit 3: Wide range (SUPER PLATINUM to BRONZE) with GSM > 10
  - Unit 4: Other items with GSM > 10

## Installation Steps for ERPNext Cloud

### Step 1: Prepare the App Structure
Since you're using ERPNext Cloud, you'll need to work with Frappe Cloud to install custom apps. Here's what you need to prepare:

1. Create a GitHub repository with the following structure:

```
production_planning/
├── production_planning/
│   ├── __init__.py
│   ├── hooks.py
│   ├── modules.txt
│   └── production_planning/
│       ├── __init__.py
│       └── doctype/
│           ├── planning_sheet/
│           │   ├── __init__.py
│           │   ├── planning_sheet.json
│           │   ├── planning_sheet.py
│           │   └── planning_sheet.js
│           ├── planning_sheet_item/
│           │   ├── __init__.py
│           │   └── planning_sheet_item.json
│           └── unit_capacity/
│               ├── __init__.py
│               └── unit_capacity.json
├── license.txt
├── README.md
└── setup.py
```

### Step 2: Create Required Files

#### modules.txt
```
Production Planning
```

#### setup.py
```python
from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="production_planning",
    version="0.0.1",
    author="Your Company",
    author_email="info@yourcompany.com",
    description="Production Planning and Queuing System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        "frappe"
    ]
)
```

#### license.txt
```
MIT License

Copyright (c) 2026 Your Company

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

### Step 3: Install on Frappe Cloud

1. **Push to GitHub**:
   - Create a new repository on GitHub
   - Push all files to the repository

2. **Add to Frappe Cloud**:
   - Log in to your Frappe Cloud account
   - Go to your site
   - Navigate to "Apps" section
   - Click "Install App"
   - Provide your GitHub repository URL
   - Wait for the app to be installed

3. **Run Migrations**:
   ```bash
   bench --site your-site-name migrate
   ```

### Step 4: Initial Configuration

After installation, configure your units:

1. **Create Unit Capacity Records**:
   - Go to: Production Planning > Unit Capacity
   - Create records for each unit:

   **Unit 1**:
   - Unit Name: Unit 1
   - Day Shift Capacity: 5000 KG (adjust as needed)
   - Night Shift Capacity: 4000 KG (adjust as needed)
   - Is Active: ✓

   **Unit 2**:
   - Unit Name: Unit 2
   - Day Shift Capacity: 4500 KG
   - Night Shift Capacity: 3500 KG
   - Is Active: ✓

   **Unit 3**:
   - Unit Name: Unit 3
   - Day Shift Capacity: 4000 KG
   - Night Shift Capacity: 3000 KG
   - Is Active: ✓

   **Unit 4**:
   - Unit Name: Unit 4
   - Day Shift Capacity: 3500 KG
   - Night Shift Capacity: 2500 KG
   - Is Active: ✓

### Step 5: User Permissions

Assign roles to users:
- **Manufacturing Manager**: Full access (create, edit, submit, delete)
- **Manufacturing User**: Limited access (create, edit)

Go to: User > [Select User] > Roles
Add: Manufacturing Manager or Manufacturing User role

## Usage

### Creating a Planning Sheet

1. **From Sales Order**:
   - Go to: Production Planning > Planning Sheet > New
   - Select Sales Order
   - Customer and delivery date will auto-populate
   - Items will be auto-filled from Sales Order

2. **Manual Entry**:
   - Add items manually
   - Fill in item details (code, name, qty, UOM)
   - Enter specifications (GSM, quality, color, etc.)
   - Enter roll details (weight per roll, number of rolls)

3. **Unit Allocation**:
   - Click "Get Unit Recommendation" to see suggested unit
   - System will automatically allocate unit on save based on:
     - Quality grade
     - Average GSM
     - Current unit capacity

4. **Submit**:
   - Review the planning sheet
   - Click "Submit" to finalize
   - Sheet will be added to the unit's queue

### Viewing Queue Status

1. Open any submitted Planning Sheet
2. Click "View Queue Status" button
3. See:
   - Unit capacity (day/night shifts)
   - Current queue weight
   - Available capacity
   - List of all orders in queue with positions

### Managing Production

1. **Start Production**:
   - Open a finalized Planning Sheet
   - Click "Start Production"
   - Status changes to "In Production"

2. **Monitor Progress**:
   - Queue automatically updates
   - Capacity calculations refresh hourly
   - Daily capacity reset at midnight

## Quality to Unit Mapping

### Unit 1 (High Quality, GSM > 50)
- SUPER PLATINUM
- PLATINUM
- PREMIUM
- GOLD
- SUPER CLASSIC

### Unit 2 (Medium Quality, GSM > 20)
- GOLD
- SILVER
- BRONZE
- CLASSIC
- ECO SPECIAL
- ECO SPL

### Unit 3 (Wide Range, GSM > 10)
- SUPER PLATINUM
- PLATINUM
- PREMIUM
- GOLD
- SILVER
- BRONZE

### Unit 4 (Others, GSM > 10)
- All other qualities with GSM > 10

## Excel Import

You can import planning data from Excel:

1. Prepare Excel file with columns:
   - Party Code
   - Customer
   - Item Code
   - Item Name
   - Quality
   - Color
   - GSM
   - Quantity
   - Weight per Roll
   - No of Rolls
   - Unit (if pre-allocated)

2. Use ERPNext Data Import tool:
   - Go to: Data Import
   - Select DocType: Planning Sheet
   - Upload your Excel file
   - Map columns
   - Import

## Scheduled Tasks

The app includes automated tasks:

1. **Daily Capacity Reset** (Daily at midnight):
   - Recalculates queue weights
   - Updates available capacities
   - Refreshes queue positions

2. **Update Production Queue** (Hourly):
   - Checks production progress
   - Updates queue status
   - Sends notifications if configured

## Troubleshooting

### Issue: Unit not being allocated automatically
**Solution**: 
- Check if quality name matches exactly with predefined list
- Verify GSM value is entered
- Ensure Unit Capacity records exist

### Issue: Queue position not updating
**Solution**:
- Make sure Planning Sheet is submitted (docstatus = 1)
- Check if unit is allocated
- Run: `bench --site your-site execute production_planning.production_planning.doctype.planning_sheet.planning_sheet.daily_capacity_reset`

### Issue: Capacity not showing
**Solution**:
- Verify Unit Capacity records are created
- Check if unit name matches exactly
- Ensure capacities are entered as numbers (KG)

## Support

For issues or questions:
- Email: info@yourcompany.com
- Create an issue on GitHub repository

## License

MIT License - See license.txt for details
