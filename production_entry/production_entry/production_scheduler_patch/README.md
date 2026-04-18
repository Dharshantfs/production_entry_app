# Production Scheduler

A custom Frappe app that provides a Real-Time Kanban Board for the Planning Sheet DocType.

## Features

- **Kanban Board**: Drag-and-drop cards across Unit 1-4 columns
- **Capacity Validation**: Hard and soft limits per unit
- **Real-Time Updates**: Live sync across users via Frappe Realtime
- **Weight Aggregation**: Automatic calculation from Planning Sheet Items

## Installation

```bash
bench get-app https://github.com/Dharshantfs/production_scheduler.git
bench --site [your-site] install-app production_scheduler
```

## License

MIT
