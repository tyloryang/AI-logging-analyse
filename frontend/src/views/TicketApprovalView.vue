<template>
  <TicketListView ticket-type="approval" :config="CONFIG" />
</template>
<script setup>
import TicketListView from '../components/TicketListView.vue'
const CONFIG = {
  title: '审批流',
  subtitle: '跨团队审批协同，支持串行与并行审批节点',
  titlePlaceholder: '权限申请 / 资源变更审批…',
  extraFields: [
    { key: 'approver',    label: '审批人',      placeholder: '张三 / 运维组',       type: 'text' },
    { key: 'deadline',    label: '期望完成时间', placeholder: '2024-12-31',          type: 'text' },
    { key: 'reason',      label: '申请原因',    placeholder: '为什么需要此次审批…',   type: 'textarea' },
    { key: 'impact',      label: '影响范围',    placeholder: '影响哪些系统/人员…',    type: 'textarea' },
  ],
}
</script>
