<template>
  <el-table :data="moduleRows" size="small" border>
    <el-table-column prop="label" label="模块" min-width="140" />
    <el-table-column v-for="a in actions" :key="a.value" :label="a.label" align="center" width="72">
      <template #default="{ row }">
        <el-checkbox
          :model-value="!!modelValue[row.module]?.[a.value]"
          :disabled="disabled"
          @change="(v) => toggle(row.module, a.value, v)" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { computed } from 'vue'
import { ACTIONS, ALL_MODULES } from '../../utils/permissionMatrix.js'

/**
 * 16 模块 × 5 动作的权限矩阵编辑器。
 *
 * 部门模板和「某个人的权限」共用这一个组件——两处配的是同一种矩阵,
 * 分开写两份迟早会漂移（ResourcePage 里原先就复制过一版）。
 *
 * 它是**受控**的:传进来的矩阵不会被就地改动,toggle 时抛一份新对象出去,
 * 父组件直接 v-model 即可。
 */
const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
  /** 只看部分模块；不传就是全部 16 个 */
  modules: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue', 'change'])

const actions = ACTIONS
const MODULES = computed(() => props.modules || ALL_MODULES)
const moduleRows = computed(() => MODULES.value.map(([key, label]) => ({ module: key, label })))

function toggle(module, action, val) {
  const next = {
    ...props.modelValue,
    [module]: { ...(props.modelValue?.[module] || {}), [action]: !!val },
  }
  emit('update:modelValue', next)
  emit('change', next)
}
</script>
