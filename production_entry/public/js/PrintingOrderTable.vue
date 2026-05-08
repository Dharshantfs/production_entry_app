<template>
  <LaminationOrderTable :tableBoardKind="'printing_105'" />
</template>

<script>
import LaminationOrderTable from './LaminationOrderTable.vue';

export default {
  name: 'PrintingOrderTable',
  components: { LaminationOrderTable },
};
</script>

<style scoped>
/* small wrapper - no styles */
</style>
