<template>
  <div
    v-if="open && lesson"
    class="pl-modal-backdrop"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="'pl-lesson-title-' + lesson.code"
    @click.self="close"
  >
    <div class="pl-modal" ref="modalRef">
      <header class="pl-modal-header">
        <div>
          <span class="pl-modal-code">{{ lesson.code }}</span>
          <h2 :id="'pl-lesson-title-' + lesson.code" class="pl-modal-title">{{ lesson.name }}</h2>
        </div>
        <button type="button" class="pl-modal-close" aria-label="Close" @click="close">×</button>
      </header>

      <nav class="pl-stepper" aria-label="Lesson progress">
        <button
          v-for="(s, i) in slideIds"
          :key="s"
          type="button"
          class="pl-stepper-item"
          :class="{ 'pl-stepper-item--active': slideIndex === i, 'pl-stepper-item--done': slideIndex > i }"
          @click="goSlide(i)"
        >
          {{ stepperLabel(s) }}
        </button>
      </nav>

      <div class="pl-modal-body">
        <section v-if="currentSlide" class="pl-slide">
          <h3 class="pl-slide-title">{{ currentSlide.title }}</h3>
          <p v-if="currentSlide.subtitle" class="pl-slide-sub">{{ currentSlide.subtitle }}</p>
          <div class="pl-slide-html" v-html="currentSlide.body_html" />

          <div v-if="currentSlide.id === 'bom' && currentSlide.tree" class="pl-bom-tree">
            <div class="pl-bom-fg" :title="tooltipBom">
              <span>{{ currentSlide.tree.fg }}</span>
              <small>Finished good (SO line)</small>
            </div>
            <div v-if="(currentSlide.tree.children || []).length" class="pl-bom-children">
              <div
                v-for="c in currentSlide.tree.children"
                :key="c"
                class="pl-bom-child"
                title="Added automatically from BOM"
              >
                <span class="pl-bom-arrow">↓</span>
                <span>{{ c }}</span>
                <small>BOM child</small>
              </div>
            </div>
            <p v-else class="pl-bom-none">No BOM children — base material.</p>
          </div>

          <div v-if="currentSlide.id === 'priority' && priorityTimeline.length" class="pl-timeline">
            <div
              v-for="(code, ti) in priorityTimeline"
              :key="code"
              class="pl-timeline-step"
              :class="{ 'pl-timeline-step--locked': ti > unlockedThrough }"
            >
              <span class="pl-timeline-num">{{ ti + 1 }}</span>
              <span class="pl-timeline-code">{{ code }}</span>
            </div>
          </div>

          <div v-if="currentSlide.id === 'walkthrough'" class="pl-walkthrough">
            <div class="pl-walkthrough-caption">
              <p class="pl-walk-caption-main">{{ microCaption }}</p>
              <p class="pl-walk-caption-sub">Step {{ microIndex + 1 }} of {{ totalMicroSteps }}</p>
              <div class="pl-legend">
                <span class="pl-legend-chip pl-legend-chip--transfer">Transfer — next unit</span>
                <span class="pl-legend-chip pl-legend-chip--despatch">Despatch — SO finished good</span>
              </div>
            </div>
            <ProcessFlowAnimation
              :walkthrough-steps="lesson.walkthrough_steps"
              :fg-code="lesson.code"
              :action-labels="lesson.action_labels || {}"
              :micro-index="microIndex"
              :playing="playing"
            />
          </div>

          <ul v-if="currentSlide.id === 'summary' && (currentSlide.checklist || []).length" class="pl-checklist">
            <li v-for="(item, ci) in currentSlide.checklist" :key="ci">{{ item }}</li>
          </ul>
          <div v-if="currentSlide.id === 'summary' && (currentSlide.shortcuts || []).length" class="pl-shortcuts">
            <button
              v-for="sh in currentSlide.shortcuts"
              :key="sh.route"
              type="button"
              class="pl-shortcut-btn"
              @click="openRoute(sh.route)"
            >
              {{ sh.label }}
            </button>
          </div>
        </section>
      </div>

      <footer class="pl-modal-footer">
        <button type="button" class="pl-btn pl-btn--ghost" :disabled="slideIndex === 0 && microIndex === 0" @click="back">
          Back
        </button>
        <div class="pl-footer-mid">
          <button
            v-if="isWalkthroughSlide"
            type="button"
            class="pl-btn pl-btn--secondary"
            @click="togglePlay"
          >
            {{ playing ? "Pause" : "Play walkthrough" }}
          </button>
          <button
            v-if="!isWalkthroughSlide"
            type="button"
            class="pl-btn pl-btn--secondary"
            @click="skipToWalkthrough"
          >
            Skip to animation
          </button>
        </div>
        <button type="button" class="pl-btn pl-btn--primary" @click="next">
          {{ nextLabel }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import ProcessFlowAnimation from "./ProcessFlowAnimation.vue";

const props = defineProps({
  open: Boolean,
  lesson: { type: Object, default: null },
});

const emit = defineEmits(["close"]);

const slideIndex = ref(0);
const microIndex = ref(0);
const playing = ref(false);
const modalRef = ref(null);
let playTimer = null;

const slideIds = ["intro", "bom", "priority", "walkthrough", "summary"];

const slidesById = computed(() => {
  const map = {};
  for (const s of props.lesson?.slides || []) {
    if (s.id) map[s.id] = s;
  }
  return map;
});

const currentSlide = computed(() => {
  const id = slideIds[slideIndex.value];
  return slidesById.value[id] || null;
});

const isWalkthroughSlide = computed(() => slideIds[slideIndex.value] === "walkthrough");

const flatMicroSteps = computed(() => {
  const out = [];
  for (const row of props.lesson?.walkthrough_steps || []) {
    for (const act of row.actions || []) {
      out.push({ code: row.node_code, action: act });
    }
  }
  return out;
});

const totalMicroSteps = computed(() => Math.max(1, flatMicroSteps.value.length));

const priorityTimeline = computed(() => {
  const pri = slidesById.value.priority;
  if (pri?.timeline?.length) return pri.timeline;
  const ch = props.lesson?.bom_chain || [];
  const fg = props.lesson?.code;
  return fg ? [...ch, fg] : [...ch];
});

const unlockedThrough = computed(() => {
  const tl = priorityTimeline.value;
  if (!isWalkthroughSlide.value) {
    if (slideIds[slideIndex.value] === "priority") return tl.length - 1;
    return -1;
  }
  const cur = flatMicroSteps.value[microIndex.value];
  if (!cur) return -1;
  const idx = tl.indexOf(cur.code);
  return idx >= 0 ? idx : -1;
});

const microCaption = computed(() => {
  const step = flatMicroSteps.value[microIndex.value];
  if (!step) return "Press Play to start the walkthrough.";
  const labels = props.lesson?.action_labels || {};
  const act = labels[step.action] || step.action;
  return `${act} — process ${step.code}`;
});

const tooltipBom = "Added automatically from BOM on the same Sales Order line";

const nextLabel = computed(() => {
  if (slideIndex.value >= slideIds.length - 1 && microIndex.value >= totalMicroSteps.value - 1) {
    return "Done";
  }
  return "Next";
});

function stepperLabel(id) {
  const m = { intro: "Intro", bom: "BOM", priority: "Priority", walkthrough: "Walkthrough", summary: "Summary" };
  return m[id] || id;
}

function goSlide(i) {
  slideIndex.value = i;
  if (i < 3) microIndex.value = 0;
  stopPlay();
}

function close() {
  stopPlay();
  emit("close");
}

function stopPlay() {
  playing.value = false;
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
  }
}

function togglePlay() {
  if (playing.value) {
    stopPlay();
    return;
  }
  playing.value = true;
  if (playTimer) clearInterval(playTimer);
  playTimer = setInterval(() => {
    if (microIndex.value < totalMicroSteps.value - 1) {
      microIndex.value += 1;
    } else {
      stopPlay();
    }
  }, 4000);
}

function skipToWalkthrough() {
  slideIndex.value = 3;
  microIndex.value = 0;
}

function back() {
  if (isWalkthroughSlide.value && microIndex.value > 0) {
    microIndex.value -= 1;
    return;
  }
  if (slideIndex.value > 0) {
    slideIndex.value -= 1;
    if (slideIndex.value === 3) {
      microIndex.value = Math.max(0, totalMicroSteps.value - 1);
    } else {
      microIndex.value = 0;
    }
  }
}

function next() {
  if (isWalkthroughSlide.value && microIndex.value < totalMicroSteps.value - 1) {
    microIndex.value += 1;
    return;
  }
  if (slideIndex.value < slideIds.length - 1) {
    slideIndex.value += 1;
    if (slideIndex.value !== 3) microIndex.value = 0;
    return;
  }
  close();
}

function openRoute(route) {
  if (route) window.open(route, "_blank");
}

function onKeydown(e) {
  if (!props.open) return;
  if (e.key === "Escape") close();
  if (e.key === "ArrowRight") next();
  if (e.key === "ArrowLeft") back();
  if (e.key === " " && isWalkthroughSlide.value) {
    e.preventDefault();
    togglePlay();
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      slideIndex.value = 0;
      microIndex.value = 0;
      stopPlay();
    }
  }
);

watch(
  () => props.lesson?.code,
  () => {
    slideIndex.value = 0;
    microIndex.value = 0;
    stopPlay();
  }
);

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  stopPlay();
});
</script>
