<template>
  <div class="histogram-wrap">
    <!-- Y-axis labels -->
    <div class="histo-y">
      <div class="y-label" v-for="pct in [100,80,60,40,20,0]" :key="pct" :style="{bottom:(pct/100*100)+'%'}">
        {{ pct }}%
      </div>
    </div>

    <!-- Bars -->
    <div class="histo-bars" ref="barsRef">
      <div v-for="item in data" :key="item.member_id" class="histo-col">
        <div class="histo-bar-wrap" @click="emit('select', item)">
          <!-- Stacked project bars -->
          <div class="histo-bar-stack">
            <div v-for="(proj, i) in item.projects" :key="proj.project_id"
              class="histo-segment"
              :style="{
                height: (proj.allocation_pct / 100 * 100) + '%',
                background: colors[i % colors.length],
                bottom: stackBottom(item, i) + '%',
              }"
              :title="proj.project_name + ': ' + proj.allocation_pct + '%'"
            />
          </div>
          <!-- Overload line (100% = 满负荷) -->
          <div class="overload-line" v-if="item.total_allocation > 100"
            :style="{bottom:'100%'}"></div>
        </div>
        <div class="histo-name">{{ item.name }}</div>
        <div class="histo-pct" :class="{over: item.total_allocation > 100}">
          {{ item.total_allocation }}%
        </div>
        <div v-if="item.total_allocation > 100" class="histo-warn">过载</div>
      </div>
    </div>

    <!-- Tooltip -->
    <div v-if="tooltipItem" class="histo-tooltip" :style="{left:tooltipX+'px',top:tooltipY+'px'}">
      <div class="tt-name">{{ tooltipItem.name }}</div>
      <div class="tt-dept">{{ tooltipItem.department }} {{ tooltipItem.title }}</div>
      <div class="tt-bar" v-for="p in tooltipItem.projects" :key="p.project_id">
        <span class="tt-swatch" :style="{background:colors[tooltipItem.projects.indexOf(p)%colors.length]}"></span>
        <span>{{ p.project_name }}</span>
        <span style="margin-left:auto;font-weight:600">{{ p.allocation_pct }}%</span>
      </div>
      <div class="tt-total" :class="{over:tooltipItem.total_allocation>100}">
        总计: {{ tooltipItem.total_allocation }}%
      </div>
    </div>

    <!-- Summary -->
    <div class="histo-summary">
      <span class="tag tag-green">{{ normalCount }} 人正常</span>
      <span class="tag tag-orange">{{ warnCount }} 人高负载</span>
      <span class="tag tag-red">{{ overloadCount }} 人过载</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ data: { type: Array, default: () => [] } })
const emit = defineEmits(['select'])

const tooltipItem = ref(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

const colors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16']

const normalCount = computed(() => props.data.filter(d => d.total_allocation <= 80).length)
const warnCount = computed(() => props.data.filter(d => d.total_allocation > 80 && d.total_allocation <= 100).length)
const overloadCount = computed(() => props.data.filter(d => d.total_allocation > 100).length)

function stackBottom(item, idx) {
  let below = 0
  for (let i = 0; i < idx; i++) {
    below += (item.projects[i].allocation_pct || 0)
  }
  return (below / 100 * 100)
}

function onBarHover(item, e) {
  tooltipItem.value = item
  tooltipX.value = e.clientX + 10
  tooltipY.value = e.clientY - 10
}
</script>

<style scoped>
.histogram-wrap {
  position: relative;
  padding-left: 48px;
  min-height: 300px;
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 20px 20px 56px;
}

.histo-y {
  position: absolute; left: 0; top: 20px; bottom: 60px; width: 48px;
}
.y-label {
  position: absolute; right: 8px; transform: translateY(50%);
  font-size: 10px; color: var(--text-muted);
}

.histo-bars {
  display: flex; justify-content: space-around; align-items: flex-end;
  height: 280px; padding-top: 4px;
}

.histo-col {
  display: flex; flex-direction: column; align-items: center;
  width: 60px; cursor: pointer;
}
.histo-col:hover .histo-bar-wrap { transform: scaleX(1.15); }

.histo-bar-wrap {
  width: 100%; height: 100%; position: relative;
  border-bottom: 1px solid #e5e7eb;
  transition: transform .15s;
}
.histo-bar-stack {
  position: absolute; bottom: 0; left: 6px; right: 6px; height: 100%;
  overflow: hidden;
}

.histo-segment {
  position: absolute; left: 0; right: 0;
  border-radius: 2px 2px 0 0; transition: opacity .15s;
  min-height: 3px;
}
.histo-segment:hover { opacity: .8; }

.overload-line {
  position: absolute; left: 0; right: 0; height: 2px;
  background: #ef4444; z-index: 2;
  border-top: 1px dashed #ef4444;
}

.histo-name {
  font-size: 11px; color: var(--text); margin-top: 6px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 60px; text-align: center; font-weight: 500;
}
.histo-pct {
  font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-top: 2px;
}
.histo-pct.over { color: #ef4444; }
.histo-warn {
  font-size: 10px; color: #ef4444; font-weight: 600;
  background: #fef2f2; padding: 1px 6px; border-radius: 8px; margin-top: 2px;
}

.histo-tooltip {
  position: fixed; z-index: 999;
  background: #1f2937; color: #fff; padding: 12px;
  border-radius: 8px; font-size: 12px; min-width: 200px;
  box-shadow: 0 4px 12px rgba(0,0,0,.3); pointer-events: none;
}
.tt-name { font-weight: 700; font-size: 13px; margin-bottom: 2px; }
.tt-dept { color: #9ca3af; margin-bottom: 8px; font-size: 11px; }
.tt-bar { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
.tt-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.tt-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #374151; font-weight: 600; }
.tt-total.over { color: #fca5a5; }

.histo-summary {
  display: flex; gap: 8px; margin-top: 12px; justify-content: center;
}
</style>
