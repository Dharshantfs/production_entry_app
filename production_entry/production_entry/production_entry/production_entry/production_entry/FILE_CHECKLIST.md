# Production Planning App - Complete File Checklist

## ✅ Files to Copy to Your GitHub Repository

### Root Directory Files

- [ ] `README.md` - Main documentation
- [ ] `setup.py` - Python package setup
- [ ] `license.txt` - MIT License
- [ ] `INSTALLATION_GUIDE.md` - Detailed installation instructions
- [ ] `CLOUD_DEPLOYMENT.md` - ERPNext Cloud specific guide
- [ ] `.gitignore` - Git ignore file (create with content below)

### App Directory: `production_planning/`

- [ ] `__init__.py` - Main app init (contains version)
- [ ] `hooks.py` - App configuration and hooks
- [ ] `modules.txt` - Module definition

### Module Directory: `production_planning/production_planning/`

- [ ] `__init__.py` - Module init

### DocType Directory: `production_planning/production_planning/doctype/`

- [ ] `__init__.py` - Doctype package init

#### Planning Sheet DocType: `doctype/planning_sheet/`

- [ ] `__init__.py`
- [ ] `planning_sheet.json` - DocType definition
- [ ] `planning_sheet.py` - Python controller
- [ ] `planning_sheet.js` - Client-side JavaScript

#### Planning Sheet Item DocType: `doctype/planning_sheet_item/`

- [ ] `__init__.py`
- [ ] `planning_sheet_item.json` - Child DocType definition

#### Unit Capacity DocType: `doctype/unit_capacity/`

- [ ] `__init__.py`
- [ ] `unit_capacity.json` - DocType definition

## 📋 Complete Directory Structure

```
production_planning/
│
├── README.md
├── setup.py
├── license.txt
├── INSTALLATION_GUIDE.md
├── CLOUD_DEPLOYMENT.md
├── .gitignore
│
└── production_planning/
    ├── __init__.py (contains: __version__ = '0.0.1')
    ├── hooks.py
    ├── modules.txt (contains: Production Planning)
    │
    └── production_planning/
        ├── __init__.py
        │
        └── doctype/
            ├── __init__.py
            │
            ├── planning_sheet/
            │   ├── __init__.py
            │   ├── planning_sheet.json
            │   ├── planning_sheet.py
            │   └── planning_sheet.js
            │
            ├── planning_sheet_item/
            │   ├── __init__.py
            │   └── planning_sheet_item.json
            │
            └── unit_capacity/
                ├── __init__.py
                └── unit_capacity.json
```

## 📝 .gitignore Content

Create a file named `.gitignore` in the root directory with this content:

```
*.pyc
*.pyo
*.egg-info
__pycache__/
.DS_Store
*.swp
*.swo
*~
.vscode/
.idea/
*.log
node_modules/
.env
build/
dist/
```

## 🔧 Initial Configuration Steps (After Installation)

### 1. Create Unit Capacity Records

| Unit Name | Day Capacity (KG) | Night Capacity (KG) | Status |
|-----------|-------------------|---------------------|--------|
| Unit 1 | 5000 | 4000 | ✓ Active |
| Unit 2 | 4500 | 3500 | ✓ Active |
| Unit 3 | 4000 | 3000 | ✓ Active |
| Unit 4 | 3500 | 2500 | ✓ Active |

**Note**: Adjust capacities based on your actual production capabilities

### 2. User Role Assignment

Assign these roles to users:

- **Manufacturing Manager**: Full control
  - Can create, edit, submit, cancel Planning Sheets
  - Can configure Unit Capacities
  - Can view all reports

- **Manufacturing User**: Operational access
  - Can create and edit Planning Sheets
  - Can view queue status
  - Cannot delete or configure units

### 3. Test Data Creation

Create test Planning Sheet with:
- Customer: Test Customer
- Party Code: TEST001
- Items: At least 2-3 test items with different qualities
- Check unit allocation works correctly

## 📊 Quality to Unit Mapping Reference

### Unit 1 Rules
```python
Qualities: ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SUPER CLASSIC"]
GSM Requirement: > 50
```

### Unit 2 Rules
```python
Qualities: ["GOLD", "SILVER", "BRONZE", "CLASSIC", "ECO SPECIAL", "ECO SPL"]
GSM Requirement: > 20
```

### Unit 3 Rules
```python
Qualities: ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SILVER", "BRONZE"]
GSM Requirement: > 10
```

### Unit 4 Rules
```python
Qualities: All others
GSM Requirement: > 10
```

## 🧪 Testing Checklist

After installation, test these scenarios:

- [ ] Create Unit Capacity records
- [ ] Create Planning Sheet from Sales Order
- [ ] Create Planning Sheet manually
- [ ] Test automatic unit allocation with Unit 1 quality
- [ ] Test automatic unit allocation with Unit 2 quality
- [ ] Test automatic unit allocation with Unit 3 quality
- [ ] Test automatic unit allocation with Unit 4 quality
- [ ] Submit Planning Sheet
- [ ] Check queue position assigned
- [ ] View Queue Status button works
- [ ] Queue shows correct capacity info
- [ ] Queue shows all submitted sheets
- [ ] Start Production button works
- [ ] Status changes correctly
- [ ] Excel import works (if using)

## 🐛 Common Issues and Solutions

### Issue 1: Module not appearing
**Solution**: Clear cache (System Settings > Clear Cache) and reload

### Issue 2: Unit not auto-allocating
**Check**:
- Quality name matches exactly (case-insensitive but spelling must match)
- GSM value is entered as number
- Unit Capacity records exist

### Issue 3: Queue position always 1
**Check**:
- Planning Sheet is submitted (docstatus = 1)
- Multiple sheets exist for the same unit
- Planning status is "Finalized" or "In Production"

### Issue 4: Capacity showing as 0
**Solution**: Create Unit Capacity records with proper values

### Issue 5: JavaScript errors in console
**Check**:
- All .js files are in correct location
- hooks.py has correct doctype_js mapping
- Clear browser cache

## 📞 Support Resources

- **Documentation**: See INSTALLATION_GUIDE.md and CLOUD_DEPLOYMENT.md
- **Frappe Forum**: https://discuss.frappe.io
- **ERPNext Forum**: https://discuss.erpnext.com
- **GitHub Issues**: Create issue in your repository

## 🎯 Next Steps After Installation

1. **Customize quality list** if your product grades differ
2. **Adjust capacity values** based on actual production
3. **Create user training material** for your team
4. **Set up automated reports** if needed
5. **Configure notification rules** for queue updates
6. **Integrate with existing Sales Order workflow**
7. **Create dashboard for real-time monitoring**

## 📈 Future Enhancements (Optional)

Consider adding these features later:
- [ ] Work Order auto-creation on Planning Sheet submit
- [ ] Email notifications for queue position changes
- [ ] Dashboard with unit utilization charts
- [ ] Mobile app integration
- [ ] Advanced scheduling algorithms
- [ ] Machine learning for better unit allocation
- [ ] Integration with production floor systems

---

**Version**: 0.0.1
**Last Updated**: February 11, 2026
**Compatible with**: ERPNext v14, v15
