<template>
  <!-- 流程节点卡片:谁做 / 做什么 / 产出什么 / 交给谁 / 平台落点 / 注意 -->
  <div class="node" :class="{ mine: isMine }">
    <div class="node-head">
      <span class="node-seq">{{ node.seq }}</span>
      <span class="node-name">{{ node.name }}</span>
      <el-tag size="small" effect="dark" :type="venueType" class="venue-tag">{{ node.venue }}</el-tag>
      <el-tag v-for="r in node.roles" :key="r" size="small" effect="plain"
        :type="r === myRole ? 'success' : 'info'" class="role-chip">{{ r }}</el-tag>
      <span class="node-deadline">{{ node.deadline }}</span>
    </div>
    <div class="node-body">
      <div class="node-row"><span class="k">做什么</span><span class="v">{{ node.actions }}</span></div>
      <div class="node-row"><span class="k">产出什么</span><span class="v">{{ node.output }}</span></div>
      <div class="node-row"><span class="k">交给谁</span><span class="v handoff">{{ node.handoff }}</span></div>
      <div class="node-row"><span class="k">平台落点</span><span class="v">{{ node.module }}</span></div>
      <div v-if="node.tip" class="node-row tip"><span class="k">注意</span><span class="v">{{ node.tip }}</span></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  myRole: { type: String, default: '' },
})

// 「在哪办」:审批类节点在钉钉,平台内操作在本平台,其余线下
const venueType = computed(() => {
  if (props.node.venue === '钉钉') return 'warning'
  if (props.node.venue === '本平台') return 'primary'
  return 'info'
})
const isMine = computed(() =>
  !!props.myRole && (props.node.roles || []).join(' ').includes(props.myRole))
</script>

<style scoped>
.node { border: 1px solid #eef0f3; border-radius: 8px; padding: 10px 12px; margin-bottom: 9px; background: #fff; }
.node.mine { border-color: #22c55e; background: #f0fdf4; }
.node-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 7px; }
.node-seq {
  width: 20px; height: 20px; border-radius: 50%; background: #e5e7eb; color: #4b5563;
  font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.node-name { font-size: 14px; font-weight: 700; color: #1f2937; }
.node-deadline { margin-left: auto; font-size: 11.5px; color: #f59e0b; }
.node-body { display: flex; flex-direction: column; gap: 4px; }
.node-row { display: flex; gap: 8px; font-size: 12.5px; }
.node-row .k { flex-shrink: 0; width: 62px; color: #9ca3af; }
.node-row .v { color: #4b5563; }
.node-row .handoff { color: #2563eb; font-weight: 600; }
.node-row.tip .v { color: #b45309; }
.venue-tag { transform: scale(.88); }
</style>
