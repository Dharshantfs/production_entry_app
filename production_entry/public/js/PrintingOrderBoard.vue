<template>
  <LaminationOrderTable :tableBoardKind="'printing_105'" tableMode="board" />
</template>

<script>
import LaminationOrderTable from './LaminationOrderTable.vue';

export default {
  name: 'PrintingOrderBoard',
  components: { LaminationOrderTable },
};
</script>

<style scoped>
/* wrapper styles if needed */
</style>
