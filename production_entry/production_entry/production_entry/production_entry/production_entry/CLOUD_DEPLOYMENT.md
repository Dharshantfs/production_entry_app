# ERPNext Cloud Deployment Guide

## Quick Start for ERPNext Cloud

Since you're using **ERPNext Cloud**, here's the streamlined process to deploy your custom Production Planning app:

### Option 1: Using Frappe Cloud (Recommended for Cloud Users)

#### Step 1: Prepare Files for GitHub

1. **Create a new folder on your computer** called `production_planning`

2. **Create the following directory structure**:

```
production_planning/
├── production_planning/
│   ├── __init__.py
│   ├── hooks.py
│   ├── modules.txt
│   └── production_planning/
│       ├── __init__.py
│       └── doctype/
│           ├── __init__.py
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
├── README.md
├── setup.py
├── license.txt
└── .gitignore
```

3. **Copy the files I've created** into this structure

#### Step 2: Create GitHub Repository

1. Go to https://github.com and create a new repository
2. Name it: `production_planning`
3. Initialize with README (or use the one provided)
4. Clone to your computer:
   ```bash
   git clone https://github.com/YOUR_USERNAME/production_planning.git
   ```

5. Copy all files into the cloned directory

6. Commit and push:
   ```bash
   git add .
   git commit -m "Initial commit - Production Planning App"
   git push origin main
   ```

#### Step 3: Install on Frappe Cloud

1. **Log in to Frappe Cloud**: https://frappecloud.com

2. **Navigate to your site**

3. **Go to Apps section**

4. **Click "Install App" or "Add App"**

5. **Enter your GitHub repository URL**:
   ```
   https://github.com/YOUR_USERNAME/production_planning
   ```

6. **Select branch**: `main` (or `master`)

7. **Click Install** and wait for the installation to complete

8. The app will be automatically installed and migrated

#### Step 4: Initial Configuration

Once installed, configure your app:

1. **Log in to your ERPNext site**

2. **Go to: Production Planning module** (should appear in the modules list)

3. **Create Unit Capacity records**:
   - Search for "Unit Capacity" in the search bar
   - Create 4 records (Unit 1, Unit 2, Unit 3, Unit 4)
   - Set capacities for each unit

4. **Assign user permissions**:
   - Go to User List
   - Add "Manufacturing Manager" or "Manufacturing User" role to relevant users

5. **Start creating Planning Sheets**!

### Option 2: Using Bench (For Self-Hosted)

If you're self-hosting (not on Frappe Cloud):

```bash
# Get the app
cd ~/frappe-bench
bench get-app https://github.com/YOUR_USERNAME/production_planning.git

# Install on your site
bench --site your-site-name install-app production_planning

# Migrate
bench --site your-site-name migrate

# Restart
bench restart
```

### File Content Quick Reference

For each file in the structure, use these contents:

#### `production_planning/__init__.py`
```python
__version__ = '0.0.1'
```

#### `production_planning/modules.txt`
```
Production Planning
```

#### `production_planning/hooks.py`
[Copy from the hooks.py file I created]

#### `production_planning/setup.py`
[Copy from the setup.py file I created]

#### `production_planning/production_planning/__init__.py`
```python
# Leave empty or add:
from __future__ import unicode_literals
```

#### `production_planning/production_planning/doctype/__init__.py`
```python
# Empty file
```

#### For each doctype folder (`planning_sheet`, `planning_sheet_item`, `unit_capacity`):

**`__init__.py`**: Empty file

**`.json` files**: Copy from the respective JSON files I created

**`.py` files**: Copy from the Python controller files I created

**`.js` files**: Copy from the JavaScript files I created

### Troubleshooting ERPNext Cloud Installation

#### Issue: App doesn't appear after installation
**Solution**: 
- Clear cache: Go to System Settings > Clear Cache
- Reload the page
- Check if migration completed successfully

#### Issue: Permission denied errors
**Solution**:
- Ensure you have System Manager role
- Check app is installed: `Apps > Installed Apps`
- Verify user has Manufacturing Manager role

#### Issue: Doctypes not showing
**Solution**:
- Run migration again from Frappe Cloud console
- Check if all JSON files are properly formatted
- Verify module.txt has "Production Planning" entry

### Testing Your Installation

After installation, test the app:

1. **Check Module**:
   - Look for "Production Planning" in modules list
   - Click to open

2. **Create Unit Capacity**:
   - Go to Unit Capacity > New
   - Create Unit 1 with test capacities
   - Save

3. **Create Planning Sheet**:
   - Go to Planning Sheet > New
   - Add a test item
   - Check if unit allocation works
   - Submit

4. **View Queue**:
   - Open the submitted Planning Sheet
   - Click "View Queue Status"
   - Should show capacity and queue info

### Configuration Checklist

- [ ] App installed on Frappe Cloud
- [ ] Migration completed successfully
- [ ] Production Planning module visible
- [ ] Unit Capacity records created for all 4 units
- [ ] User roles assigned (Manufacturing Manager/User)
- [ ] Test Planning Sheet created and submitted
- [ ] Queue status displaying correctly

### Getting Help

If you encounter issues:

1. **Check Frappe Cloud Logs**:
   - Go to your site dashboard
   - Click on "Logs" or "Error Logs"
   - Look for any errors related to production_planning

2. **Verify File Structure**:
   - Ensure all __init__.py files are present
   - Check JSON files are valid (use JSONLint)
   - Verify Python syntax is correct

3. **Contact Support**:
   - Frappe Cloud Support (for cloud-specific issues)
   - GitHub Issues (for app-specific bugs)

### Updates and Maintenance

To update the app after making changes:

1. Push changes to GitHub:
   ```bash
   git add .
   git commit -m "Update description"
   git push
   ```

2. On Frappe Cloud:
   - Go to Apps section
   - Find production_planning
   - Click "Update"
   - Wait for update to complete

3. Migration runs automatically on Frappe Cloud

### Best Practices

1. **Always test in development first** (if you have a dev site)
2. **Backup your site** before major updates
3. **Document customizations** in comments
4. **Use version control** (Git) for all changes
5. **Monitor error logs** regularly

---

**You're all set!** Your Production Planning app should now be running on ERPNext Cloud.
