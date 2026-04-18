#!/bin/bash

# Production Planning App - Structure Generator
# This script creates the proper ERPNext app directory structure

echo "Creating Production Planning App Directory Structure..."

# Create main app directory
mkdir -p production_planning

# Create module directories
mkdir -p production_planning/production_planning
mkdir -p production_planning/production_planning/production_planning
mkdir -p production_planning/production_planning/production_planning/doctype
mkdir -p production_planning/production_planning/production_planning/doctype/planning_sheet
mkdir -p production_planning/production_planning/production_planning/doctype/planning_sheet_item
mkdir -p production_planning/production_planning/production_planning/doctype/unit_capacity

# Create public directories for client-side scripts
mkdir -p production_planning/production_planning/public
mkdir -p production_planning/production_planning/public/js
mkdir -p production_planning/production_planning/public/css

# Create __init__.py files
touch production_planning/__init__.py
touch production_planning/production_planning/__init__.py
touch production_planning/production_planning/production_planning/__init__.py
touch production_planning/production_planning/production_planning/doctype/__init__.py
touch production_planning/production_planning/production_planning/doctype/planning_sheet/__init__.py
touch production_planning/production_planning/production_planning/doctype/planning_sheet_item/__init__.py
touch production_planning/production_planning/production_planning/doctype/unit_capacity/__init__.py

echo "Directory structure created successfully!"
echo ""
echo "Next steps:"
echo "1. Copy the provided files to their respective directories"
echo "2. Create a GitHub repository"
echo "3. Push all files to GitHub"
echo "4. Install on your ERPNext Cloud site"
echo ""
echo "Directory structure:"
tree -L 4 production_planning/
