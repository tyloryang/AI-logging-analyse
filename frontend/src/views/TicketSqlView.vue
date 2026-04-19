<template>
  <TicketListView ticket-type="sql" :config="CONFIG" />
</template>
<script setup>
import TicketListView from '../components/TicketListView.vue'
const CONFIG = {
  title: 'SQL 审计',
  subtitle: 'DDL / DML 变更审核，防止误操作影响生产数据',
  titlePlaceholder: '新增索引 / ALTER TABLE …',
  extraFields: [
    { key: 'database', label: '数据库',      placeholder: 'prod_db',           type: 'text' },
    { key: 'table',    label: '表名',        placeholder: 'users',             type: 'text' },
    { key: 'sql',      label: 'SQL 语句',    placeholder: 'ALTER TABLE …',     type: 'textarea' },
    { key: 'rollback', label: '回滚 SQL',    placeholder: '回滚用 SQL（可选）', type: 'textarea' },
    { key: 'affect',   label: '预计影响行数', placeholder: '~1000',            type: 'text' },
  ],
}
</script>
