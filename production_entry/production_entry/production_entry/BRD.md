# Business Requirements Document (BRD)

## 1. Document Control
- Project: Production Planning and Execution App (Frappe/ERPNext)
- Repository/App Name: production_entry
- BRD Version: 1.0
- Date: 2026-04-06
- Prepared By: GitHub Copilot (analysis based on current codebase)

## 2. Executive Summary
The application provides an integrated workflow from order-driven production planning through unit allocation, queue management, production run execution, and manufacturing entry posting in ERPNext.

The core business value is to reduce manual planning errors, improve plant utilization across Unit 1 to Unit 4, and ensure traceable conversion from Sales Orders to Planning Sheet, Production Plan, Work Order, Shaft Production Run, and Roll Production Entry.

## 3. Business Problem Statement
Manufacturing planning teams need to:
- Allocate production to the right unit based on quality, GSM, color, width, and available capacity.
- Maintain an ordered queue per production unit.
- Convert planning decisions into executable production documents without duplicate plans or broken links.
- Track actual production outcomes and close Work Orders accurately.

Without this app, these steps are fragmented, manual, and error-prone, causing delays, rework, and inconsistent planning data.

## 4. Business Objectives
- Improve planning throughput and consistency by automating unit recommendation and queue updates.
- Increase schedule reliability through capacity-aware queue monitoring.
- Ensure end-to-end traceability from Sales Order to manufacturing transactions.
- Reduce manual data entry for planners and shop-floor users.
- Provide operational visibility (queue status, capacity utilization, production progress).

## 5. Scope

### 5.1 In Scope
- Planning Sheet lifecycle: Draft, Finalized, In Production, Completed, Cancelled.
- Auto/assisted unit allocation using quality and GSM rules.
- Unit Capacity master and queue/capacity recalculation.
- Sales Order integration and optional auto-creation of Planning Sheet.
- Production Plan and Work Order linkage/creation logic on Planning Sheet finalization.
- Shop-floor execution via Shaft Production Run and Roll Production Entry.
- Manufacturing Stock Entry creation from Roll Production Entry.
- Queue status visibility and recommendation APIs.
- Scheduled recalculation jobs (daily and hourly).

### 5.2 Out of Scope (for this BRD baseline)
- Advanced finite-capacity optimization algorithms.
- Real-time IoT machine telemetry integration.
- Customer self-service portal.
- Cost accounting redesign beyond ERPNext standard posting.

## 6. Stakeholders and User Roles
- Manufacturing Manager:
	- Configure capacities, approve/monitor planning, supervise execution.
- Manufacturing User:
	- Create and update planning sheets and production entries.
- System Manager:
	- Deployment, permissions, schema repair utilities, and governance.
- Production Planner:
	- Maintains queue sequence and unit assignment.
- Shop-floor Operator:
	- Executes shaft/roll production data capture.

## 7. Current Product Analysis (As Implemented)

### 7.1 Core Business Modules
- Planning Sheet (header + legacy item table + board item table).
- Unit Capacity.
- Planning Table (board rows).
- Planning Sheet Item (legacy rows).
- Shaft Production Run and related child jobs/items.
- Roll Production Entry and child items.

### 7.2 Primary Workflow
1. Sales Order exists (or is submitted).
2. Planning Sheet is created (manual and/or auto-create hook).
3. Item details are validated and enriched (quality/color extraction, totals).
4. Unit is allocated through business rules (quality + GSM, with capacity context).
5. On submit, queue is updated and production docs are linked/created.
6. Production proceeds via Shaft Production Run.
7. Roll Production Entry posts manufacturing Stock Entries and updates WO status.

### 7.3 Business Rules Observed
- Unit recommendation by thresholds:
	- Unit 1: high GSM with premium quality groups.
	- Unit 2: medium GSM with mid-tier quality groups.
	- Unit 3: lower GSM with broader quality groups.
	- Unit 4: fallback for eligible low-threshold cases.
- Queue positions are unit-specific and incremented for finalized/in-production sheets.
- Capacity metrics are computed as day + night shift capacities minus queued load.
- Planning rows normalize unit values to controlled select options.
- Planning submission supports link-only mode to avoid duplicate Production Plans.

### 7.4 Integration Touchpoints
- ERPNext Sales Order.
- ERPNext Production Plan.
- ERPNext Work Order.
- ERPNext Stock Entry (Manufacture).
- ERPNext Item/BOM/Company defaults.

## 8. To-Be Business Requirements

### 8.1 Functional Requirements

FR-001 Planning Sheet Creation
- The system shall allow manual Planning Sheet creation.
- The system shall support auto-creation from Sales Order submit event.

FR-002 Planning Data Validation
- The system shall require at least one planning item before save/submit.
- The system shall validate mandatory item attributes (item, qty, GSM, UOM, quality where required).

FR-003 Planning Enrichment
- The system shall auto-calculate total quantity and total weight.
- The system shall infer quality and color from item names when missing.

FR-004 Unit Recommendation and Allocation
- The system shall recommend an eligible unit based on dominant quality and weighted GSM.
- The system shall store allocated unit at sheet level and line-level derived assignment.

FR-005 Capacity and Queue Management
- The system shall maintain per-unit queue weight, queue count, and available capacity.
- The system shall assign queue position on Planning Sheet submit for active queue states.
- The system shall provide queue status view/API for planners.

FR-006 Planning to Manufacturing Document Flow
- The system shall link each planning line to existing Production Plan/Work Order when available.
- The system shall prevent duplicate Production Plan creation for same planning context.
- The system shall create Production Plan in legacy fallback mode if linkage is absent and configuration permits.

FR-007 Production Execution (Shaft and Roll)
- The system shall allow creation of shaft job rows from Production Plan details.
- The system shall support manual shaft job creation where needed.
- The system shall capture roll-level production metrics and compute net weight.

FR-008 Manufacturing Posting
- On Roll Production Entry submit, the system shall create Manufacture Stock Entry per Work Order group.
- The system shall update linked Work Order status to Completed when produced quantity criteria is met.
- On cancellation, the system shall reverse/cancel linked manufacturing entries.

FR-009 Status Lifecycle and Actions
- The system shall support Planning Sheet status transitions:
	- Draft -> Finalized -> In Production -> Completed.
- The system shall provide UI actions for Start Production and consolidated production entry where applicable.

FR-010 Administration and Recovery
- The system shall provide admin utilities for child-table schema repair in case of metadata drift.
- The system shall run scheduled tasks for capacity/queue maintenance.

### 8.2 Non-Functional Requirements

NFR-001 Reliability
- Submission flows shall be transactional and prevent inconsistent partial linkage.

NFR-002 Data Integrity
- Referential integrity between planning rows, production plans, and work orders shall be preserved.

NFR-003 Usability
- Planners shall be able to obtain unit recommendation and queue status within one form session.

NFR-004 Performance
- Queue and recommendation retrieval shall be responsive for day-to-day operational usage.

NFR-005 Auditability
- Status and document transitions shall remain traceable through ERPNext document history.

NFR-006 Security and Access
- Role-based access shall be enforced according to Manufacturing Manager/User/System Manager permissions.

## 9. Data and Reporting Requirements
- Master data:
	- Unit Capacity definitions and active/inactive flags.
	- Quality/color dictionaries inferred from item naming conventions.
- Transactional data:
	- Planning Sheet headers and line items.
	- Queue metrics and production statuses.
	- Production and stock movement documents.
- Required views/reports:
	- Unit capacity utilization snapshot.
	- Unit queue details by position and due date.
	- Planning-to-WO conversion coverage.
	- Production completion against planned quantity.

## 10. Assumptions
- ERPNext/Frappe versions are compatible with app dependencies (Frappe 15+).
- Core manufacturing doctypes (BOM, Production Plan, Work Order, Stock Entry) are active and configured.
- Item master data quality (GSM, naming, UOM, warehouse defaults) is maintained by business users.

## 11. Constraints
- Unit routing is rule-based and currently deterministic, not optimization-based.
- Quality/color extraction depends on naming patterns and maintained keyword lists.
- Legacy and board child-table coexistence requires synchronization safeguards.

## 12. Risks and Mitigations
- Risk: Duplicate planning-to-production links in repeated user actions.
	- Mitigation: Existing dedup/link resolution logic and link-only submit mode.
- Risk: Incomplete master data (missing BOM/warehouse/company) blocks flow.
	- Mitigation: Pre-submit validation and clear user error messages.
- Risk: Data drift in child-table schema after migrations.
	- Mitigation: Admin repair utility and migration governance.
- Risk: Queue mis-prioritization under manual interventions.
	- Mitigation: Enforce standardized status transitions and queue dashboards.

## 13. Acceptance Criteria
- AC-001 Planner can create and submit Planning Sheet with valid lines and receive unit allocation.
- AC-002 Queue position and capacity values update after Planning Sheet submit.
- AC-003 For linked Production Plan rows, Work Orders are attached without duplicate Production Plans.
- AC-004 Roll Production Entry submit creates Manufacture Stock Entries and updates WO completion status.
- AC-005 Queue status can be viewed through UI/API by allocated unit.
- AC-006 Scheduled jobs run without errors and keep capacity/queue metrics current.

## 14. KPIs and Success Metrics
- Planning cycle time (Sales Order to Finalized Planning Sheet).
- Percentage of planning lines auto-allocated without manual override.
- Queue adherence (planned order vs actual production initiation).
- Work Order linkage success rate on first submit.
- Reduction in manual corrections/reopened planning documents.

## 15. Recommended Implementation Roadmap

### Phase 1: Stabilize Core Planning
- Validate all role permissions and mandatory master data checks.
- Standardize planner SOP for Planning Sheet and queue review.

### Phase 2: Strengthen Execution Quality
- Add dashboard widgets for conversion and queue health.
- Improve exception handling and proactive alerts for missing BOM/WO links.

### Phase 3: Optimization and Analytics
- Introduce advanced prioritization (delivery urgency, machine constraints, changeover costs).
- Expand reporting for throughput, yield, and on-time delivery trends.

## 16. Open Decisions
- Confirm whether production should always require pre-linked Production Plan (strict mode) or allow controlled legacy fallback creation.
- Confirm formal priority rule for queue ordering beyond submit sequence.
- Confirm final approval workflow responsibilities for Pending Approval/Approved states.

## 17. Traceability (Source Artifacts Reviewed)
- Hooks and event orchestration.
- Planning Sheet and child table doctypes.
- Unit Capacity doctype and queue update logic.
- Scheduler APIs for recommendation, linkage, and schema repair.
- Client scripts for planner and production execution UX.

