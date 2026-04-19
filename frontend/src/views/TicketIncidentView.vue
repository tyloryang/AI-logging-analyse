<template>
  <TicketListView ticket-type="incident" :config="CONFIG" />
</template>
<script setup>
import TicketListView from '../components/TicketListView.vue'
const CONFIG = {
  title: '事务工单',
  subtitle: '运维变更与故障处理，全流程 SLA 追踪',
  titlePlaceholder: '生产环境 XXX 服务异常',
  extraFields: [
    { key: 'affected',    label: '受影响系统',  placeholder: 'order-service',    type: 'text' },
    { key: 'severity',    label: '影响等级',    placeholder: 'P1 / P2 / P3',    type: 'text' },
    { key: 'root_cause',  label: '根因描述',    placeholder: '已知或怀疑的原因…',  type: 'textarea' },
    { key: 'resolution',  label: '处理方案',    placeholder: '预计处理步骤…',     type: 'textarea' },
  ],
}
</script>
