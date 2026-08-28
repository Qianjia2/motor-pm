import { reactive } from 'vue'

// 当前正在查看的项目类型(hardware/software),供侧边栏在详情页时高亮对应台账菜单
export const currentProjectType = reactive({ value: null })
