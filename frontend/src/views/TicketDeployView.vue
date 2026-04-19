<template>
  <TicketListView ticket-type="deploy" :config="CONFIG" />
</template>
<script setup>
import TicketListView from '../components/TicketListView.vue'
const CONFIG = {
  title: '应用发布',
  subtitle: '标准化应用发布流程，支持蓝绿 / 滚动 / 金丝雀发布',
  titlePlaceholder: '服务名称 v1.2.3 发布申请',
  extraFields: [
    { key: 'service',     label: '服务名称',   placeholder: 'my-service',       type: 'text' },
    { key: 'version',     label: '版本号',     placeholder: 'v1.2.3',           type: 'text' },
    { key: 'env',         label: '目标环境',   placeholder: 'staging / prod',   type: 'text' },
    { key: 'strategy',    label: '发布策略',   placeholder: 'rolling / blue-green / canary', type: 'text' },
    { key: 'change_log',  label: '变更说明',   placeholder: '本次变更内容…',    type: 'textarea' },
  ],
}
</script>
