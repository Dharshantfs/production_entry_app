<template>
  <div class="pl-page">
    <section class="pl-hero">
      <h1 class="pl-hero-title">Production Learning</h1>
      <p class="pl-hero-text">
        Learn which items the system adds to your Planning Sheet and what to plan and produce first.
      </p>
      <button type="button" class="pl-btn pl-btn--primary pl-hero-cta" @click="openLesson('100')">
        Start with Fabric (100)
      </button>
    </section>

    <section v-if="recommendedPath.length" class="pl-path">
      <span class="pl-path-label">Recommended order for new users:</span>
      <span class="pl-path-chips">
        <template v-for="(code, i) in recommendedPath" :key="code">
          <button type="button" class="pl-path-chip" @click="openLesson(code)">{{ code }}</button>
          <span v-if="i < recommendedPath.length - 1" class="pl-path-sep">→</span>
        </template>
      </span>
    </section>

    <div class="pl-toolbar">
      <input
        v-model="search"
        type="search"
        class="pl-search"
        placeholder="Search by code or name (e.g. lam, 104, bopp)…"
        aria-label="Search processes"
      />
      <div class="pl-filters" role="group" aria-label="Filter by category">
        <button
          v-for="f in filterOptions"
          :key="f.id"
          type="button"
          class="pl-filter-pill"
          :class="{ 'pl-filter-pill--active': activeFilter === f.id }"
          @click="activeFilter = f.id"
        >
          {{ f.label }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="pl-loading">Loading processes…</div>
    <div v-else-if="loadError" class="pl-error">{{ loadError }}</div>
    <div v-else class="pl-grid">
      <article
        v-for="item in filteredItems"
        :key="item.code"
        class="pl-card"
        tabindex="0"
        role="button"
        @click="openLesson(item.code)"
        @keydown.enter="openLesson(item.code)"
      >
        <span class="pl-card-code">{{ item.code }}</span>
        <h2 class="pl-card-name" :title="item.name">{{ item.name }}</h2>
        <p class="pl-card-tagline">{{ item.tagline || item.summary }}</p>
        <p v-if="item.chain_label" class="pl-card-chain">{{ item.chain_label }}</p>
        <p v-else class="pl-card-chain pl-card-chain--muted">Base material</p>
      </article>
    </div>
    <p v-if="!loading && !filteredItems.length" class="pl-empty">No processes match your search.</p>

    <LearningLessonModal :open="lessonOpen" :lesson="activeLesson" @close="lessonOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import LearningLessonModal from "./LearningLessonModal.vue";

const loading = ref(true);
const loadError = ref("");
const items = ref([]);
const recommendedPath = ref([]);
const search = ref("");
const activeFilter = ref("all");
const lessonOpen = ref(false);
const activeLesson = ref(null);

const filterOptions = [
  { id: "all", label: "All" },
  { id: "base", label: "Base fabric" },
  { id: "mid", label: "Mid process" },
  { id: "sheet", label: "Sheet FG" },
  { id: "bopp", label: "BOPP" },
];

const filteredItems = computed(() => {
  let list = items.value || [];
  const q = search.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (it) =>
        String(it.code || "").toLowerCase().includes(q) ||
        String(it.name || "").toLowerCase().includes(q) ||
        String(it.tagline || "").toLowerCase().includes(q) ||
        String(it.summary || "").toLowerCase().includes(q)
    );
  }
  if (activeFilter.value !== "all") {
    list = list.filter((it) => (it.tags || []).includes(activeFilter.value));
  }
  return list;
});

async function fetchCatalog() {
  loading.value = true;
  loadError.value = "";
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.learning_api.get_learning_catalog",
      args: { phase: "fabric" },
    });
    const msg = res?.message || res;
    items.value = msg.items || [];
    recommendedPath.value = msg.recommended_path || [];
  } catch (e) {
    loadError.value = e?.message || String(e) || "Failed to load catalog.";
  } finally {
    loading.value = false;
  }
}

async function openLesson(code) {
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.learning_api.get_learning_lesson",
      args: { process_code: code },
    });
    activeLesson.value = res?.message || res;
    lessonOpen.value = true;
  } catch (e) {
    frappe.msgprint({
      title: "Lesson unavailable",
      message: e?.message || String(e),
      indicator: "red",
    });
  }
}

onMounted(() => fetchCatalog());
</script>
