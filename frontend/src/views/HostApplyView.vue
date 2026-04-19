<template>
  <TicketListView ticket-type="host_apply" :config="CONFIG" />
</template>
<script setup>
import TicketListView from '../components/TicketListView.vue'
const CONFIG = {
  title: '主机申请',
  subtitle: '主机资源申请与审批，支持多环境多规格',
  titlePlaceholder: '申请 2台 4C8G CentOS 7 生产主机',
  extraFields: [
    { key: 'count',    label: '申请数量',  placeholder: '2',                        type: 'text' },
    { key: 'spec',     label: '规格',      placeholder: '4C8G / 8C16G',             type: 'text' },
    { key: 'os',       label: '操作系统',  placeholder: 'CentOS 7 / Ubuntu 22.04', type: 'text' },
    { key: 'env',      label: '环境',      placeholder: 'dev / staging / prod',     type: 'text' },
    { key: 'purpose',  label: '用途',      placeholder: '部署 XXX 服务…',            type: 'textarea' },
    { key: 'duration', label: '使用期限',  placeholder: '长期 / 6个月',             type: 'text' },
  ],
}
</script>
