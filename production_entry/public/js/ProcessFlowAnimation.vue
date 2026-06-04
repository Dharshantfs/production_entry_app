<template>
  <div class="pl-flow" :class="{ 'pl-flow--static': reducedMotion, 'pl-flow--fast': fastPlay }">
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
          <span class="pl-flow-node-name">{{ nodeName(node.code) }}</span>
          <span v-if="node.role === 'fg'" class="pl-flow-badge pl-flow-badge--fg">FG · Despatch</span>
          <span v-else-if="node.role !== 'fabric'" class="pl-flow-badge pl-flow-badge--child">Child · Transfer</span>
          <span v-if="node.done" class="pl-flow-check" aria-hidden="true">✓</span>
          <span v-if="node.active && !reducedMotion" class="pl-flow-pulse" aria-hidden="true" />
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
            v-if="showTransferOnConnector(ni)"
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
      <div class="pl-flow-action-text">
        <span class="pl-flow-action-label">{{ actionLabel(activeAction) }}</span>
        <span v-if="activeNodeCode" class="pl-flow-action-node">{{ activeNodeCode }} — {{ nodeName(activeNodeCode) }}</span>
        <p v-if="subtitle" class="pl-flow-subtitle">{{ subtitle }}</p>
      </div>
      <div
        v-if="activeAction === 'produce' && !reducedMotion && !fastPlay"
        class="pl-flow-ring"
        :style="{ '--pl-ring-pct': ringPct + '%' }"
      />
      <div v-else-if="activeAction === 'despatch'" class="pl-flow-despatch-chip">Despatch</div>
    </div>
    <p v-else class="pl-flow-idle">Select <strong>Start walkthrough</strong> or use <strong>Next</strong> to step through.</p>
  </div>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from "vue";
import LearningIcons from "./learning/LearningIcons.vue";

const props = defineProps({
  walkthroughSteps: { type: Array, default: () => [] },
  fgCode: { type: String, default: "" },
  actionLabels: { type: Object, default: () => ({}) },
  processNames: { type: Object, default: () => ({}) },
  microIndex: { type: Number, default: 0 },
  playing: { type: Boolean, default: false },
  fastPlay: { type: Boolean, default: false },
  subtitle: { type: String, default: "" },
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
  () => [props.microIndex, activeAction.value, props.playing, props.fastPlay],
  () => {
    if (ringTimer) clearInterval(ringTimer);
    ringTimer = null;
    if (activeAction.value === "produce" && !reducedMotion.value && !props.fastPlay) {
      ringPct.value = 0;
      ringTimer = setInterval(() => {
        ringPct.value = Math.min(100, ringPct.value + 12);
      }, 80);
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

function nodeName(code) {
  return props.processNames[code] || "";
}

function nodeStateClass(node) {
  return {
    "pl-flow-node--active": node.active,
    "pl-flow-node--done": node.done,
    "pl-flow-node--fg": node.role === "fg",
  };
}

function staggerStyle(i) {
  if (reducedMotion.value || props.fastPlay) return {};
  return { animationDelay: `${i * 50}ms` };
}

function connectorActive(ni) {
  const next = displayNodes.value[ni + 1];
  return next && (next.active || next.done);
}

function connectorPathStyle(ni) {
  const on = connectorActive(ni);
  if (props.fastPlay) {
    return { strokeDashoffset: on ? 0 : 48 };
  }
  if (reducedMotion.value) return {};
  return {
    strokeDashoffset: on ? 0 : 48,
    transition: props.fastPlay ? "none" : "stroke-dashoffset 0.35s ease",
  };
}

function showTransferOnConnector(ni) {
  const cur = flatMicroSteps.value[props.microIndex];
  if (!cur || cur.action !== "transfer") return false;
  const nodeIdx = displayNodes.value.findIndex((n) => n.code === cur.code);
  return nodeIdx === ni;
}

function truckRunning(ni) {
  return showTransferOnConnector(ni) && props.playing && !props.fastPlay;
}

function actionLabel(act) {
  return props.actionLabels[act] || act;
}
</script>
