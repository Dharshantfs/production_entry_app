import { createApp } from "vue";
import ProductionScheduler from "./ProductionScheduler.vue";
import ColorChart from "./ColorChart.vue";

frappe.provide("production_scheduler");

function safeMount(component, wrapper, label) {
    try {
        if (!wrapper) return;
        const app = createApp(component);
        app.mount(wrapper);
    } catch (e) {
        console.error(`${label} mount failed`, e);
        if (wrapper) {
            wrapper.innerHTML = `<div style="padding:16px;color:#b91c1c;font-weight:600;">${label} failed to load. Check browser console for details.</div>`;
        }
    }
}

production_scheduler.Controller = class {
    constructor(wrapper) {
        safeMount(ProductionScheduler, wrapper, "Production Scheduler");
    }
};

production_scheduler.ColorChartController = class {
    constructor(wrapper) {
        safeMount(ColorChart, wrapper, "Color Chart");
    }
};

import ConfirmedOrder from "./ConfirmedOrder.vue";
import ProductionTable from "./ProductionTable.vue";
import LaminationOrderTable from "./LaminationOrderTable.vue";
import SequenceApproval from "./SequenceApproval.vue";

production_scheduler.ConfirmedOrderController = class {
    constructor(wrapper) {
        safeMount(ConfirmedOrder, wrapper, "Confirmed Order");
    }
};

production_scheduler.ProductionTableController = class {
    constructor(wrapper) {
        safeMount(ProductionTable, wrapper, "Production Table");
    }
};

production_scheduler.LaminationOrderTableController = class {
    constructor(wrapper) {
        safeMount(LaminationOrderTable, wrapper, "Lamination Order Table");
    }
};

production_scheduler.SequenceApprovalController = class {
    constructor(wrapper) {
        safeMount(SequenceApproval, wrapper, "Sequence Approval");
    }
};
