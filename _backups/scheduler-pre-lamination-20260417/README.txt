Backup created: 20260417
Contains COPIES of working-tree files (includes any uncommitted edits).

production_entry:
- production_planning/scheduler_api.py -> production_entry_production_planning_scheduler_api.py
- production_entry/production_planning/scheduler_api.py -> production_entry_nested_production_planning_scheduler_api.py

production_scheduler:
- production_scheduler/api.py -> production_scheduler_api.py

Git tags (point to last commit; does not include uncommitted edits — use file copies above for full WIP snapshot):
- production_entry @ 2e0e31752f8094a15f660ad7c83adfeeaecb83dc
- production_scheduler @ 6a0e2e81cdd0e8db596878a4e56217d8f894d402

Restore file: copy from this folder back to the paths listed in filenames / this README.
Revert branch to tagged commit: git checkout backup/pre-lamination-20260417
