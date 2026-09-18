/**
 * 权限矩阵的模块/动作定义 —— 前端唯一一份。
 *
 * 必须与后端 backend_v2/permissions.py 的 MODULES / ACTIONS 一一对应，
 * 顺序也照抄（那就是侧边栏顺序）。改这里就要同步改后端，否则矩阵对不上号。
 */
export const ALL_MODULES = [
  ['my_work', '我的工作台'], ['dashboard', '项目驾驶舱'], ['mgmt_weekly', '管理层周报'],
  ['product_tech', '产品技术库'], ['bom', 'BOM管理'], ['projects', '系统集成开发项目台账'],
  ['tasks_milestones', '任务与里程碑'], ['issue_risks', '问题风险管理'], ['phase_gate', '阶段门评审'],
  ['reports', '报告中心'], ['ai', 'AI 助手'], ['knowledge', '知识库'],
  ['clients', '客户管理'], ['users', '资源管理'], ['audit_logs', '操作审计'], ['settings', '系统设置'],
]

export const ACTIONS = [
  { value: 'view', label: '查看' }, { value: 'create', label: '新建' },
  { value: 'edit', label: '编辑' }, { value: 'delete', label: '删除' }, { value: 'export', label: '导出' },
]

/** 数一份矩阵开了多少个模块（任一动作 true 就算开）。 */
export function countEnabledModules(matrix) {
  if (!matrix || typeof matrix !== 'object') return 0
  return ALL_MODULES.filter(([key]) => {
    const m = matrix[key]
    return m && typeof m === 'object' && Object.values(m).some(Boolean)
  }).length
}

/** 一份没有任何权限的矩阵（16 模块全 false）。 */
export function emptyMatrix() {
  const m = {}
  for (const [key] of ALL_MODULES) {
    m[key] = {}
    for (const a of ACTIONS) m[key][a.value] = false
  }
  return m
}
