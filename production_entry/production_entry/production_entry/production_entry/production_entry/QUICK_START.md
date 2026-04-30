# 🚀 Quick Start Guide - Production Planning App

## For ERPNext Cloud Users (5-Minute Setup)

### Step 1: Create GitHub Repository (2 minutes)

1. Create account on https://github.com (if you don't have one)
2. Click "New Repository"
3. Name: `production_planning`
4. Set to Public
5. Click "Create repository"

### Step 2: Upload Files (1 minute)

You have two options:

**Option A: Upload via GitHub Web Interface**
1. Click "uploading an existing file"
2. Drag and drop all the files I've provided
3. Commit with message: "Initial commit"

**Option B: Use Git Command Line**
```bash
git clone https://github.com/YOUR_USERNAME/production_planning.git
cd production_planning
# Copy all provided files here
git add .
git commit -m "Initial commit - Production Planning App"
git push
```

### Step 3: Install on ERPNext Cloud (2 minutes)

1. Log in to https://frappecloud.com
2. Go to your site
3. Click "Apps" in sidebar
4. Click "Install App" button
5. Enter: `https://github.com/YOUR_USERNAME/production_planning`
6. Click "Install"
7. Wait for installation (usually 30 seconds - 2 minutes)

### Step 4: Configure Units (3 minutes)

1. Log in to your ERPNext site
2. Search for "Unit Capacity" in the search bar
3. Click "New"
4. Create 4 records:

**Quick Config**:
```
Unit 1: Day=5000, Night=4000
Unit 2: Day=4500, Night=3500  
Unit 3: Day=4000, Night=3000
Unit 4: Day=3500, Night=2500
```

### Step 5: Test! (1 minute)

1. Search for "Planning Sheet"
2. Click "New"
3. Add a customer and item
4. Set GSM to 90 and Quality to "PLATINUM"
5. Save - Unit 1 should be auto-assigned!
6. Submit to add to queue

## 🎉 You're Done!

Your production planning system is now live!

---

## Common First Questions

### Q: Where do I find the files to upload?
**A**: All files are in the `/home/claude/production_planning_app/` folder. I'll provide you with download links.

### Q: What if I get an error during installation?
**A**: Check:
- GitHub repository is public
- All files are uploaded
- You have System Manager role in ERPNext
- Try the installation again

### Q: Can I customize the quality list?
**A**: Yes! Edit `planning_sheet.py` and modify the UNIT_1, UNIT_2, UNIT_3 lists.

### Q: How do I update capacity values later?
**A**: Just go to Unit Capacity > Select Unit > Edit > Save

### Q: Can I import from Excel?
**A**: Yes! Use ERPNext's Data Import tool with Planning Sheet doctype.

---

## Need Help?

- 📖 Full Guide: See `INSTALLATION_GUIDE.md`
- ☁️ Cloud Guide: See `CLOUD_DEPLOYMENT.md`
- ✅ Checklist: See `FILE_CHECKLIST.md`
- 📧 Support: Create an issue on GitHub

---

**Time to Production**: ~10 minutes
**Difficulty**: ⭐⭐☆☆☆ (Easy)
**Requirements**: ERPNext Cloud account, GitHub account
