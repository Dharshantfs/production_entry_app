<template>
  <div class="pl-flow" :class="{ 'pl-flow--static': reducedMotion }">
    <div class="pl-flow-nodes">
      <div
        v-for="(node, ni) in displayNodes"
        :key="`${node.code}-${ni}`"
        class="pl-flow-node-wrap"
      >
        <div
          class="pl-flow-node"
          :class="nodeStateClass(node)"
          :style="staggerStyle(ni)"
        >
          <span class="pl-flow-node-code">{{ node.code }}</span>
          <span v-if="node.role === 'fg'" class="pl-flow-badge pl-flow-badge--fg">FG</span>
          <span v-if="node.done" class="pl-flow-check" aria-hidden="true">✓</span>
        </div>
        <div
          v-if="ni < displayNodes.length - 1"
          class="pl-flow-connector"
          :class="{ 'pl-flow-connector--active': connectorActive(ni) }"
        >
          <svg viewBox="0 0 40 48" class="pl-flow-connector-svg">
            <path
              class="pl-flow-connector-path"
              d="M20 0 L20 48"
              :style="connectorPathStyle(ni)"
            />
          </svg>
          <div
            v-if="showTransferOnConnector(ni) && !reducedMotion"
            class="pl-flow-truck"
            :class="{ 'pl-flow-truck--run': truckRunning(ni) }"
          >
            <LearningIcons name="transfer" />
          </div>
        </div>
      </div>
    </div>
    <div v-if="activeAction" class="pl-flow-action">
      <LearningIcons :name="activeAction" />
      <span class="pl-flow-action-label">{{ actionLabel(activeAction) }}</span>
      <span v-if="activeNodeCode" class="pl-flow-action-node">Process {{ activeNodeCode }}</span>
      <div
        v-if="activeAction === 'produce' && !reducedMotion"
        class="pl-flow-ring"
        :style="{ '--pl-ring-pct': ringPct + '%' }"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from "vue";
import LearningIcons from "./learning/LearningIcons.vue";

const props = defineProps({
  walkthroughSteps: { type: Array, default: () => [] },
  fgCode: { type: String, default: "" },
  actionLabels: { type: Object, default: () => ({}) },
  /** Current micro-step index within walkthrough (flat) */
  microIndex: { type: Number, default: 0 },
  playing: { type: Boolean, default: false },
});

const reducedMotion = computed(() => {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
});

const flatMicroSteps = computed(() => {
  const out = [];
  for (const row of props.walkthroughSteps || []) {
    const code = row.node_code || "";
    for (const act of row.actions || []) {
      out.push({ code, role: row.node_role, action: act });
    }
  }
  return out;
});

const currentMicro = computed(() => flatMicroSteps.value[props.microIndex] || null);

const activeAction = computed(() => currentMicro.value?.action || "");
const activeNodeCode = computed(() => currentMicro.value?.code || "");

const ringPct = ref(0);
let ringTimer = null;

watch(
  () => [props.microIndex, activeAction.value, props.playing],
  () => {
    if (ringTimer) clearInterval(ringTimer);
    ringTimer = null;
    if (activeAction.value === "produce" && !reducedMotion.value) {
      ringPct.value = 0;
      ringTimer = setInterval(() => {
        ringPct.value = Math.min(100, ringPct.value + 8);
      }, 120);
    } else {
      ringPct.value = activeAction.value === "produce" ? 100 : 0;
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  if (ringTimer) clearInterval(ringTimer);
});

const displayNodes = computed(() => {
  const seen = new Set();
  const nodes = [];
  for (const row of props.walkthroughSteps || []) {
    const code = row.node_code;
    if (!code || seen.has(code)) continue;
    seen.add(code);
    const idxEnd = flatMicroSteps.value.findIndex(
      (s, i) => s.code === code && i > props.microIndex
    );
    const lastForNode = flatMicroSteps.value
      .map((s, i) => ({ s, i }))
      .filter((x) => x.s.code === code)
      .pop();
    const done = lastForNode ? props.microIndex > lastForNode.i : false;
    const active = currentMicro.value?.code === code;
    nodes.push({ code, role: row.node_role, done, active });
  }
  return nodes;
});

function nodeStateClass(node) {
  return {
    "pl-flow-node--active": node.active,
    "pl-flow-node--done": node.done,
    "pl-flow-node--fg": node.role === "fg",
  };
}

function staggerStyle(i) {
  if (reducedMotion.value) return {};
  return { animationDelay: `${i * 90}ms` };
}

function connectorActive(ni) {
  const next = displayNodes.value[ni + 1];
  return next && (next.active || next.done);
}

function connectorPathStyle(ni) {
  if (reducedMotion.value) return {};
  const on = connectorActive(ni);
  return {
    strokeDashoffset: on ? 0 : 48,
    transition: "stroke-dashoffset 0.6s ease",
  };
}

function showTransferOnConnector(ni) {
  const cur = flatMicroSteps.value[props.microIndex];
  if (!cur || cur.action !== "transfer") return false;
  const nodeIdx = displayNodes.value.findIndex((n) => n.code === cur.code);
  return nodeIdx === ni;
}

function truckRunning(ni) {
  return showTransferOnConnector(ni) && props.playing;
}

function actionLabel(act) {
  return props.actionLabels[act] || act;
}
</script>
