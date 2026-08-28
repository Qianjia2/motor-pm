<template>
  <div class="proj-detail" v-loading="loading">
    <!-- Top bar -->
    <div class="pd-topbar">
      <div>
        <el-button link @click="$router.push('/projects')"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
        <span class="pd-title">{{ project.name }}</span>
        <span class="tag tag-blue" style="margin-left:8px">{{ project.code }}</span>
      </div>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="$router.push(`/projects/${project.id}/edit`)"><el-icon><Edit /></el-icon> 编辑</el-button>
        <el-button size="small" type="success" @click="confirmCloneProj">📋 复制</el-button>
        <el-button size="small" type="warning" @click="downloadPlan">📄 项目计划书</el-button>
        <DingTalkApproval ref="dtRef" :project-name="project.name" :project-id="project.id"
          :prefill-content="'项目: ' + project.name + '\n编号: ' + (project.code||'') + '\n阶段: ' + (currentPhaseName||'')" />
        <el-button size="small" type="danger" @click="confirmDeleteProj">✕ 删除</el-button>
      </div>
    </div>

    <!-- Phase progress bar -->
    <div class="pd-phase-bar">
      <div class="phase-bar-track">
        <div v-for="(pg, i) in phaseSteps" :key="pg.id" class="phase-step"
          :class="{ active: isCurrentPhase(pg.id), done: isPhaseDone(pg.id) }"
          @click="goDeliverableView(pg.id)">
          <div class="phase-dot">{{ i+1 }}</div>
          <div class="phase-label">{{ pg.name }}</div>
          <div class="phase-desc">{{ pg.desc }}</div>
          <div v-if="i < phaseSteps.length-1" class="phase-connector" :class="{done: isPhaseDone(pg.id)}"></div>
        </div>
      </div>
    </div>

    <!-- Body: left nav + content -->
    <div class="pd-body">
      <!-- Left Phase Nav -->
      <div class="pd-nav">
        <template v-for="grp in phaseGroups" :key="grp.id">
          <div class="pd-nav-group" :class="{collapsed: !expandedPhases.includes(grp.id)}">
            <div class="pd-nav-group-hdr" @click="togglePhase(grp.id)" :style="{borderLeftColor: grp.color}">
              <span class="group-dot" :style="{background:grp.color}"></span>
              <span class="group-name">{{ grp.name }}</span>
              <span class="group-desc">{{ grp.desc }}</span>
              <el-icon class="group-arrow" :class="{open: expandedPhases.includes(grp.id)}"><ArrowRight /></el-icon>
            </div>
            <div v-show="expandedPhases.includes(grp.id)" class="pd-nav-items">
              <!-- 顶层组(如全程管控):直接显示模块 -->
              <template v-if="!grp.children || !grp.children.length">
                <div v-for="tab in tabsByPhase(grp.id)" :key="tab.name"
                  class="pd-nav-item" :class="{active: activeTab===tab.name}"
                  @click="activeTab=tab.name">
                  {{ tab.label }}
                  <span v-if="tabBadge(tab.name)" class="nav-badge">{{ tabBadge(tab.name) }}</span>
                </div>
                <div v-if="tabsByPhase(grp.id).length===0" class="pd-nav-empty">无模块</div>
              </template>
              <!-- 交付物矩阵:全部阶段 + 各阶段子组 -->
              <template v-else>
                <div class="pd-nav-item" :class="{active: activeTab==='docs' && !deliverablePhase}"
                  @click="goDeliverableView(null)">全部阶段</div>
                <div v-for="child in grp.children" :key="child.id" class="pd-nav-subgroup"
                  :class="{collapsed: !expandedPhases.includes(child.id)}">
                  <div class="pd-nav-subgroup-hdr" @click="togglePhase(child.id)" :style="{borderLeftColor: child.color}">
                    <span class="group-dot" :style="{background:child.color}"></span>
                    <span class="group-name">{{ child.name }}</span>
                    <el-icon class="group-arrow" :class="{open: expandedPhases.includes(child.id)}"><ArrowRight /></el-icon>
                  </div>
                  <div v-show="expandedPhases.includes(child.id)" class="pd-nav-items">
                    <div class="pd-nav-item" :class="{active: activeTab==='docs' && deliverablePhase===child.id}"
                      @click="goDeliverableView(child.id)">交付物</div>
                    <div v-for="tab in tabsByPhase(child.id)" :key="tab.name"
                      class="pd-nav-item" :class="{active: activeTab===tab.name}"
                      @click="activeTab=tab.name">
                      {{ tab.label }}
                      <span v-if="tabBadge(tab.name)" class="nav-badge">{{ tabBadge(tab.name) }}</span>
                    </div>
                    <div v-if="tabsByPhase(child.id).length===0" class="pd-nav-empty">无其他模块</div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>

      <!-- Right Content -->
      <div class="pd-content">
        <div class="pd-content-hdr">{{ currentTabLabel }}</div>
        <!-- Overview -->
        <template v-if="activeTab==='overview'">
          <el-row :gutter="16">
            <el-col :span="14">
              <GoalSummary :project="project" @edit="$router.push(`/projects/${project.id}/edit`)" />
              <el-card shadow="never" style="margin-top:12px" v-if="project.client">
                <template #header><strong>客户信息</strong></template>
                <p>名称：{{ project.client.name }}</p>
                <p v-if="project.client.contact_person">联系人：{{ project.client.contact_person }} {{ project.client.contact_phone }}</p>
              </el-card>
            </el-col>
            <el-col :span="10">
              <CurrentStatus :project="project" />
              <BlockerList :project="project" :risks="openRisks" @edit="activeTab='risks'" style="margin-top:12px" />
              <NextSteps :project="project" @edit="activeTab='risks'" style="margin-top:12px" />
            </el-col>
          </el-row>
        </template>
        <!-- Phases -->
        <template v-else-if="activeTab==='phases'">
          <div style="margin-bottom:12px"><el-radio-group v-model="phaseView" size="small"><el-radio-button label="stepper">步骤视图</el-radio-button><el-radio-button label="tree">树状图</el-radio-button></el-radio-group></div>
          <PhaseStepper v-if="phaseView==='stepper'" ref="stepperRef" :phase-gates="phaseGates" :project-id="pid" @select="onPhaseSelect" @update="onPhaseUpdate" />
          <PhaseTreeView v-else :phase-gates="phaseGates" :project-id="pid" @leafClick="onTreeLeafClick" />
        </template>
        <!-- Milestones -->
        <template v-else-if="activeTab==='milestones'">
          <div class="card-header mb-md"><span></span><el-button type="primary" size="small" @click="addMilestone"><el-icon><Plus /></el-icon> 添加里程碑</el-button></div>
          <div v-if="!milestoneGroups.length" style="text-align:center;padding:40px;color:var(--text-muted)">暂无里程碑</div>
          <template v-else>
            <template v-for="grp in milestoneGroups" :key="grp.key">
              <div class="ms-group-hdr">
                <span class="ms-group-name">{{ grp.label }}</span>
                <span class="ms-group-count">{{ grp.items.length }} 个里程碑</span>
              </div>
              <el-table :data="grp.items" stripe><el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip /><el-table-column prop="line.name" label="技术线" width="100" /><el-table-column label="计划开始" width="105"><template #default="{row}"><span>{{ row.planned_date||'-' }}</span></template></el-table-column><el-table-column label="计划结束" width="105"><template #default="{row}"><span>{{ row.planned_end_date||'-' }}</span></template></el-table-column><el-table-column label="实际完成" width="105"><template #default="{row}"><span :style="{color:row.actual_date?'#10b981':'#c0c4cc'}">{{ row.actual_date||row.actual_end_date||'-' }}</span></template></el-table-column><el-table-column label="状态" width="90"><template #default="{row}"><StatusBadge :status="row.status" /></template></el-table-column><el-table-column label="关键" width="60"><template #default="{row}"><el-tag v-if="row.is_key" type="danger" size="small">关键</el-tag></template></el-table-column><el-table-column label="操作" width="140"><template #default="{row}"><el-button type="primary" link size="small" @click="editMilestone(row)">编辑</el-button><el-popconfirm title="删除?" @confirm="removeMilestone(row.id)"><template #reference><el-button type="danger" link size="small">删除</el-button></template></el-popconfirm></template></el-table-column></el-table>
            </template>
          </template>
<!-- Gantt chart tab -->
        </template>
        <template v-else-if="activeTab==='gantt'">
          <ProjectGantt :milestones="milestones" @changed="onGanttChanged" />
        </template>
        <!-- Team -->
        <template v-else-if="activeTab==='team'">
          <div class="card-header mb-md"><span></span><el-button type="primary" size="small" @click="showAddMemberDialog=true"><el-icon><Plus /></el-icon> 添加成员</el-button></div>
          <el-table :data="projectMembers" stripe><el-table-column prop="member.name" label="姓名" width="100" /><el-table-column label="项目角色" width="130"><template #default="{row}"><el-select v-model="row.role_id" size="small" @change="onRoleChange(row)" style="width:100%"><el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" /></el-select></template></el-table-column><el-table-column prop="member.title" label="职务" width="100" /><el-table-column prop="member.department" label="部门" width="130" /><el-table-column label="投入比例" width="150"><template #header><span style="display:inline-flex;align-items:center;gap:3px">投入比例<el-tooltip content="该成员在本项目投入的工作量占比（0~100%），100% 表示全职投入本项目，50% 表示一半时间投入。用于资源负载评估与人员调配参考。" placement="top"><el-icon style="cursor:help;color:var(--text-muted)"><QuestionFilled /></el-icon></el-tooltip></span></template><template #default="{row}"><el-slider v-model="row.allocation_pct" :min="0" :max="100" :marks="{0:'0',25:'25',50:'50',75:'75',100:'100'}" @change="onAllocationChange(row)" style="width:120px" /></template></el-table-column><el-table-column label="关键" width="90"><template #default="{row}"><el-switch v-model="row.is_key" size="small" @change="onMemberKeyChange(row)" /></template></el-table-column><el-table-column label="操作" width="70"><template #default="{row}"><el-popconfirm title="移除?" @confirm="removeMember(row)"><template #reference><el-button type="danger" link size="small">移除</el-button></template></el-popconfirm></template></el-table-column></el-table>
        </template>
        <!-- Reports -->
        <template v-else-if="activeTab==='reports'">
          <template v-if="reportView==='form'"><div class="mb-md"><el-button @click="reportView='history'" size="small"><el-icon><List /></el-icon> 查看历史</el-button></div><WeeklyReportForm :project-id="pid" :report-data="editingReport" @submit="onReportSubmit" @cancel="reportView='history'" /></template>
          <template v-else-if="reportView==='detail'"><ReportDetail :report="selectedReport" @back="reportView='history'" @edit="(r)=>{editingReport=r;reportView='form'}" /></template>
          <template v-else><div class="card-header mb-md"><span></span><div style="display:flex;gap:8px"><el-upload :http-request="handleImportUpload" :show-file-list="false" accept=".xlsx,.xls,.csv,.tsv,.txt" style="display:inline-block"><el-button size="small">📥 导入文件</el-button></el-upload><el-button size="small" @click="showPasteDlg=true">📋 粘贴导入</el-button><el-button type="primary" size="small" @click="reportView='form'"><el-icon><Plus /></el-icon> 填写本周周报</el-button></div></div><ReportHistory :reports="reports" @view="(r)=>{selectedReport=r;reportView='detail'}" @edit="(r)=>{editingReport=r;reportView='form'}" @delete="onReportDelete" /></template>
        </template>
        <!-- Analytics tab -->
        <template v-else-if="activeTab==='analytics'">
          <ProgressChart :tasks="taskTree" :milestones="milestones" :phases="phases" />
          <div style="margin-top:20px">
            <div class="card-title" style="margin-bottom:12px">任务看板（拖拽切换状态）</div>
            <KanbanBoard :tasks="flatTasks" @update="loadTasks" />
          </div>
        </template>

        <!-- Generic component tabs -->
        <component v-else :is="tabComponent(activeTab)" :project-id="pid" :project="project"
          :items="activeTab==='risks' ? riskItems : activeTab==='changes' ? changeItems : []"
          :lines="lines" :phases="phases" :members="allMembers" :roles="roles"
          :phase-code="deliverablePhase"
          :current-member-id="auth.currentMemberId" :is-admin="auth.isAdmin"
          @refresh="loadRefData"
          @goDeliverable="goTab('deliverables')" />
      </div>
    </div>

    <!-- Phase Gate Detail Dialog -->
    <el-dialog v-model="showPhaseDetail" :title="(selectedPhaseGate?.phase?.name || '') + ' - 阶段详情'" width="560px">
      <PhaseGatePanel v-if="selectedPhaseGate" :phase-gate="selectedPhaseGate" :project-id="pid"
        :members="allMembers" @save="onPhaseGateSave" @cancel="showPhaseDetail=false" />
    </el-dialog>

    <!-- Dialogs -->
    <el-dialog v-model="milestoneDialogVisible" :title="editingMilestone ? '编辑里程碑' : '添加里程碑'" width="500px">
      <el-form :model="milestoneForm" label-width="100px"><el-form-item label="名称" required><el-input v-model="milestoneForm.name" /></el-form-item><el-row :gutter="12"><el-col :span="12"><el-form-item label="计划日期"><el-date-picker v-model="milestoneForm.planned_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col><el-col :span="12"><el-form-item label="结束日期"><el-date-picker v-model="milestoneForm.planned_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col></el-row><el-row :gutter="12"><el-col :span="12"><el-form-item label="实际开始"><el-date-picker v-model="milestoneForm.actual_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col><el-col :span="12"><el-form-item label="实际结束"><el-date-picker v-model="milestoneForm.actual_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col></el-row><el-row :gutter="12"><el-col :span="12"><el-form-item label="阶段"><el-select v-model="milestoneForm.phase_id" clearable style="width:100%"><el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item label="技术线"><el-select v-model="milestoneForm.line_id" clearable style="width:100%"><el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.id" /></el-select></el-form-item></el-col></el-row><el-row :gutter="12"><el-col :span="12"><el-form-item label="状态"><el-select v-model="milestoneForm.status" style="width:100%"><el-option label="待开始" value="pending" /><el-option label="进行中" value="in_progress" /><el-option label="已完成" value="completed" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item label="关键节点"><el-switch v-model="milestoneForm.is_key" /></el-form-item></el-col></el-row></el-form>
      <template #footer><el-button @click="milestoneDialogVisible=false">取消</el-button><el-button type="primary" @click="saveMilestone">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="showAddMemberDialog" title="添加项目成员" width="550px">
      <el-form :model="addMemberForm" label-width="100px">
        <el-form-item label="成员"><el-select v-model="addMemberForm.member_id" placeholder="选择成员" filterable style="width:100%"><el-option v-for="m in availableMembers" :key="m.id" :label="`${m.name} (${m.department})`" :value="m.id" /></el-select></el-form-item>
        <el-form-item label="角色"><el-select v-model="addMemberForm.role_id" style="width:100%"><el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" /></el-select></el-form-item>
        <el-form-item label="投入比例(%)"><el-input-number v-model="addMemberForm.allocation_pct" :min="0" :max="100" /><div style="font-size:11px;color:var(--text-muted);margin-top:4px">成员在本项目投入的工作量占比，100%=全职投入（默认），50%=一半时间投入，可随时在成员列表调整</div></el-form-item>
        <el-form-item label="关键人员"><el-switch v-model="addMemberForm.is_key" /></el-form-item>
        <el-form-item label="可访问阶段">
          <el-checkbox-group v-model="addMemberForm.phase_ids">
            <el-checkbox v-for="p in phases" :key="p.id" :label="p.id" :value="p.id" style="margin-right:12px">{{ p.name }}</el-checkbox>
          </el-checkbox-group>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">留空=全部可见，勾选=仅可见指定阶段</div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="showAddMemberDialog=false">取消</el-button><el-button type="primary" @click="addMember">添加</el-button></template>
    </el-dialog>

    <!-- AI Import Preview Dialog -->
    <el-dialog v-model="aiImportShow" title="AI 解析结果" width="800px" top="3vh">
      <div v-if="aiProjects && aiProjects.length">
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
          识别到 {{ aiSheetCount }} 个Sheet，共 {{ aiTotalWeeks }} 条周报记录
        </div>
        <div v-for="(proj, pi) in aiProjects" :key="pi" style="margin-bottom:16px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
          <div style="padding:8px 12px;background:#f0f7ff;font-weight:600;font-size:13px;display:flex;align-items:center;gap:8px">
            <span class="tag tag-blue">{{ proj.sheet_name || proj.project_name || '未知项目' }}</span>
            <span v-if="proj.year">{{ proj.year }}年 W{{ proj.week }}</span>
            <span v-if="proj.error" class="tag tag-red" style="font-size:11px">{{ proj.error }}</span>
          </div>
          <div v-if="proj.overall" style="padding:6px 12px;font-size:12px;color:var(--text-secondary)">{{ proj.overall }}</div>
          <el-table v-if="proj.items && proj.items.length" :data="proj.items" stripe size="small">
            <el-table-column label="专业" width="100">
              <template #default="{row}">{{ row.line_name }}</template>
            </el-table-column>
            <el-table-column label="本周完成" min-width="200">
              <template #default="{row}">{{ row.this_week }}</template>
            </el-table-column>
            <el-table-column label="下周计划" min-width="200">
              <template #default="{row}">{{ row.next_week }}</template>
            </el-table-column>
            <el-table-column label="状态" width="70">
              <template #default="{row}">
                <el-tag size="small" :type="row.status==='blocked'?'danger':row.status==='at_risk'?'warning':'success'">
                  {{ row.status==='on_track'?'正常':row.status==='at_risk'?'风险':row.status==='blocked'?'阻塞':'—' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div v-else-if="proj.rows" style="padding:8px;font-size:11px;max-height:200px;overflow:auto;white-space:pre-wrap;background:#fafafa">{{ proj.rows.slice(0,1000) }}</div>
        </div>
      </div>
      <div v-else style="padding:20px;text-align:center;color:#ef4444">
        {{ aiError || 'AI未能识别任何数据' }}
      </div>
      <template #footer>
        <el-button @click="aiImportShow=false">取消</el-button>
        <el-button v-if="aiProjects && aiProjects.length" type="primary" @click="confirmAiImport" :loading="aiImportIng">全部导入</el-button>
      </template>
    </el-dialog>

    <!-- Paste Import Dialog -->
    <el-dialog v-model="showPasteDlg" title="粘贴导入周报" width="700px" top="3vh">
      <div style="margin-bottom:8px;font-size:12px;color:var(--text-muted)">
        粘贴你的周报数据（Tab/逗号分隔均可）。第一行为表头，之后每行为一条记录。
      </div>
      <el-input v-model="pasteText" type="textarea" :rows="10" placeholder="粘贴周报内容..." />
      <div v-if="pastePreview && pastePreview.length" style="margin-top:12px;max-height:300px;overflow:auto">
        <el-table :data="pastePreview" stripe size="small">
          <el-table-column v-for="(h,i) in pasteHeaders" :key="i" :label="h" min-width="120">
            <template #default="{row}">{{ row[i] || '' }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showPasteDlg=false">取消</el-button>
        <el-button type="primary" @click="doPasteImport" :loading="pasteIng">解析并导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Plus, List, ArrowLeft, ArrowRight, QuestionFilled } from '@element-plus/icons-vue'
import api from '../api/index.js'
import { currentProjectType } from '../stores/projectType.js'
import {
  getProject, deleteProject, copyProject, getPhaseGates, updatePhaseGate,
  getMilestones, createMilestone, updateMilestone, deleteMilestone,
  getProjectMembers, addProjectMember, updateProjectMember, removeProjectMember,
  getRisks, getChanges, getLines, getPhases, getRoles, getTeamMembers, getReports, createReport, updateReport,
} from '../api/index.js'
import StatusBadge from '../components/common/StatusBadge.vue'
import DingTalkApproval from '../components/common/DingTalkApproval.vue'
import PhaseStepper from '../components/common/PhaseStepper.vue'
import PhaseGatePanel from '../components/project/PhaseGatePanel.vue'
import PhaseTreeView from '../components/project/PhaseTreeView.vue'
import ProjectGantt from '../components/project/ProjectGantt.vue'
import ReportGenerator from '../components/project/ReportGenerator.vue'
import GoalSummary from '../components/project/GoalSummary.vue'
import CurrentStatus from '../components/project/CurrentStatus.vue'
import NextSteps from '../components/project/NextSteps.vue'
import BlockerList from '../components/project/BlockerList.vue'
import WeeklyReportForm from '../components/project/WeeklyReportForm.vue'
import ReportHistory from '../components/project/ReportHistory.vue'
import ReportDetail from '../components/project/ReportDetail.vue'
import RiskTable from '../components/risk/RiskTable.vue'
import ChangeList from '../components/risk/ChangeList.vue'
import DeliverableMatrix from '../components/project/DeliverableMatrix.vue'
import ProjectDeliverableChecklist from '../components/project/ProjectDeliverableChecklist.vue'
import FinancialPanel from '../components/project/FinancialPanel.vue'
import RequirementList from '../components/project/RequirementList.vue'
import TaskTree from '../components/project/TaskTree.vue'
import TestPanel from '../components/project/TestPanel.vue'
import PrototypePanel from '../components/project/PrototypePanel.vue'
import KanbanBoard from '../components/project/KanbanBoard.vue'
import ProgressChart from '../components/project/ProgressChart.vue'

import { useAuthStore } from '../stores/auth.js'

const route = useRoute(); const router = useRouter()
const auth = useAuthStore()
const pid = computed(() => Number(route.params.id))
const KNOWN_TABS = ['overview','phases','milestones','gantt','team','reports','analytics','requirements','tasks','risks','changes','docs','deliverables','testing','prototype','finance','reportgen']
const qTab = route.query.tab
const loading = ref(true); const activeTab = ref(typeof qTab === 'string' && KNOWN_TABS.includes(qTab) ? qTab : 'overview')
const activePhase = ref('P0'); const expandedPhases = ref(['all','deliverables','P0','PP1','PP2','PP3','PP4'])
const deliverablePhase = ref(null) // 交付物矩阵下的阶段筛选(null=全部阶段)
const currentPhaseName = computed(() => {
  const pg = flatGroups.value.find(g => g.id === activePhase.value)
  return pg ? pg.name : ''
})

// Phase groups + Tabs config
const phaseGroups = ref([])
const tabsConfig = ref([])

async function loadConfig() {
  const type = project.value?.project_type || 'hardware'
  try { const r = await api.get('/lookups/admin/project-phase-groups', { params: { project_type: type } }); phaseGroups.value = r.data||[] } catch(e) {}
  try { const r = await api.get('/lookups/admin/project-tabs-config', { params: { project_type: type } }); tabsConfig.value = r.data||[] } catch(e) {}
}

// 树形组展平:子组放在父组位置,无子组的顶层组保持
const flatGroups = computed(() => {
  const out = []
  for (const g of phaseGroups.value) {
    if (g.children && g.children.length) out.push(...g.children)
    else out.push(g)
  }
  return out
})
// 顶部进度条只显示阶段(交付物矩阵的子组)
const phaseSteps = computed(() => (phaseGroups.value.find(g => g.id === 'deliverables')?.children) || [])

// 交付物矩阵作为独立导航组,排除其 tab(docs/deliverables)避免重复
function tabsByPhase(phaseId) { return tabsConfig.value.filter(t => t.visible && !['docs','deliverables'].includes(t.name) && (t.phase||'all') === phaseId) }
function togglePhase(id) { const i = expandedPhases.value.indexOf(id); if(i>=0) expandedPhases.value.splice(i,1); else expandedPhases.value.push(id) }
function goDeliverableView(phaseCode) {
  deliverablePhase.value = phaseCode
  activeTab.value = 'docs'
  if (phaseCode) {
    activePhase.value = phaseCode
    if (!expandedPhases.value.includes('deliverables')) expandedPhases.value.push('deliverables')
    if (!expandedPhases.value.includes(phaseCode)) expandedPhases.value.push(phaseCode)
  }
}
function isCurrentPhase(pgId) { return activePhase.value === pgId }
function isPhaseDone(pgId) {
  const order = phaseSteps.value.map(s => s.id)
  const cur = project.value?.current_phase?.code || project.value?.current_phase?.name || ''
  return order.indexOf(pgId) < order.indexOf(cur)
}
function tabBadge(name) { if(name==='risks') return openRisks.value.length||null; return null }
const currentTabLabel = computed(() => {
  if (activeTab.value === 'docs') {
    if (deliverablePhase.value) {
      const p = flatGroups.value.find(g => g.id === deliverablePhase.value)
      return (p ? p.name : deliverablePhase.value) + ' - 交付物'
    }
    return '阶段交付物矩阵'
  }
  return tabsConfig.value.find(t=>t.name===activeTab.value)?.label||''
})

const componentMap = {
  requirements: RequirementList, tasks: TaskTree, risks: RiskTable, changes: ChangeList,
  docs: ProjectDeliverableChecklist, deliverables: DeliverableMatrix, testing: TestPanel,
  prototype: PrototypePanel, finance: FinancialPanel, analytics: null,
  gantt: ProjectGantt, reportgen: ReportGenerator,
}
function tabComponent(name) { return componentMap[name]||null }
function goTab(name) { activeTab.value = name }

// State
const project = ref({}); const phaseGates = ref([]); const milestones = ref([])
// 里程碑按阶段分组(与甘特图一致);未绑定阶段的排最后
const milestoneGroups = computed(() => {
  const map = new Map()
  milestones.value.forEach(m => {
    const k = m.phase_id || 0
    const label = m.phase_name || m.phase?.name || '未分配阶段'
    if (!map.has(k)) map.set(k, { key: k, label, items: [] })
    map.get(k).items.push(m)
  })
  return [...map.values()].sort((a, b) => (a.key === 0 ? 1 : 0) - (b.key === 0 ? 1 : 0) || a.key - b.key)
})
const projectMembers = ref([]); const lines = ref([]); const phases = ref([]); const roles = ref([])
const allMembers = ref([]); const openRisks = ref([]); const reports = ref([]); const riskItems = ref([]); const changeItems = ref([])
const phaseView = ref('stepper'); const reportView = ref('history')
const editingReport = ref(null); const selectedReport = ref(null)
const editingMilestone = ref(null); const milestoneDialogVisible = ref(false)
const milestoneForm = reactive({ name:'', planned_date:'', planned_end_date:'', actual_date:'', actual_end_date:'', phase_id:null, line_id:null, status:'pending', is_key:false })
function addMilestone() {
  editingMilestone.value = null
  Object.assign(milestoneForm, { name:'', planned_date:'', planned_end_date:'', actual_date:'', actual_end_date:'', phase_id:null, line_id:null, status:'pending', is_key:false })
  milestoneDialogVisible.value = true
}
// Tasks for kanban + analytics
const taskTree = ref([])
const flatTasks = computed(() => { const r=[]; function walk(l){for(const t of l){r.push(t);if(t.children)walk(t.children)}};walk(taskTree.value);return r })
async function loadTasks() { try { const r = await api.get(`/projects/${pid.value}/tasks`); taskTree.value = r.data||[] } catch(e){} }

const availableMembers = computed(() => {
  const assignedIds = new Set(projectMembers.value.map(pm => pm.member?.id || pm.member_id))
  return allMembers.value.filter(m => !assignedIds.has(m.id))
})
const showAddMemberDialog = ref(false)
const addMemberForm = ref({ member_id:null, role_id:null, allocation_pct:100, is_key:false, phase_ids:[] })

onMounted(async () => {
  const KNOWN_TABS = ['overview','phases','milestones','gantt','team','reports','analytics','requirements','tasks','risks','changes','docs','deliverables','testing','prototype','finance','reportgen']
  const qTab = route.query.tab
  if (qTab && KNOWN_TABS.includes(String(qTab))) activeTab.value = String(qTab)
  try {
    const [projRes, linesRes, phasesRes, rolesRes, membersRes] = await Promise.all([
      getProject(pid.value), getLines(), getPhases(), getRoles(), getTeamMembers(),
    ])
    project.value = projRes.data; phaseGates.value = projRes.data.phase_gates||[]
    currentProjectType.value = projRes.data.project_type || 'hardware'
    await loadConfig()  // 需要 project_type 已就绪再加载阶段组/tab 配置
    lines.value = linesRes.data
    // 阶段下拉只显示本项目类型的阶段(软件项目用 S0-S4)
    const projType = project.value.project_type || 'hardware'
    if (projType === 'software') {
      phases.value = phasesRes.data.filter(p => p.project_type === 'software')
    } else {
      phases.value = phasesRes.data.filter(p => !p.project_type || p.project_type === 'hardware')
    }
    // Load milestones separately
    try { milestones.value = (await getMilestones(pid.value)).data||[] } catch(e) { milestones.value = [] }
    roles.value = rolesRes.data; allMembers.value = membersRes.data
    try { const pmRes = await getProjectMembers(pid.value); projectMembers.value = pmRes.data||[] } catch(e){}
    try { openRisks.value = ((await getRisks(pid.value,{type:'risk'})).data||[]).filter(r=>r.status==='open') } catch(e){}
    try { reports.value = (await getReports(pid.value)).data||[] } catch(e){}
    try { riskItems.value = (await getRisks(pid.value)).data||[] } catch(e){}
    try { changeItems.value = (await getChanges(pid.value)).data||[] } catch(e){}
    await loadTasks()
    // Auto-expand current phase
    const phaseCode = project.value?.current_phase?.code || 'P0'
    activePhase.value = phaseCode
    if (!expandedPhases.value.includes(phaseCode)) expandedPhases.value.push(phaseCode)
  } catch(e) {
    const d = e?.response?.data?.detail
    const msg = Array.isArray(d) ? d.map(x => x.msg || '').join(';')
      : (typeof d === 'string' ? d : (e?.message || '项目不存在或网络错误'))
    ElMessage.error('项目加载失败: ' + msg)
  } finally {
    loading.value = false
  }
})

const selectedPhaseGate = ref(null)
const showPhaseDetail = ref(false)
function onPhaseSelect(pg) { selectedPhaseGate.value = pg; showPhaseDetail.value = true }
async function onPhaseGateSave(data) {
  try {
    await updatePhaseGate(selectedPhaseGate.value.id, data)
    showPhaseDetail.value = false
    phaseGates.value = (await getPhaseGates(pid.value)).data
  } catch(e) { ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || '')) }
}
async function onPhaseUpdate(data) {
  try {
    const pg = phaseGates.value.find(p => p.phase_id === data.phase_id)
    if (!pg) { ElMessage.error('未找到对应阶段记录'); return }
    await updatePhaseGate(pg.id, data)
    phaseGates.value = (await getPhaseGates(pid.value)).data
    ElMessage.success('阶段已保存')
  } catch(e) { ElMessage.error('阶段保存失败: ' + (e?.response?.data?.detail || e?.message || '')) }
}
function onTreeLeafClick() { goTab('deliverables') }
function editMilestone(row) { editingMilestone.value=row; Object.assign(milestoneForm,{name:row.name,planned_date:row.planned_date||'',planned_end_date:row.planned_end_date||'',actual_date:row.actual_date||'',actual_end_date:row.actual_end_date||'',phase_id:row.phase_id,line_id:row.line_id,status:row.status||'pending',is_key:row.is_key}); milestoneDialogVisible.value=true }
async function saveMilestone() { try { const payload = {}; for(const[k,v] of Object.entries(milestoneForm)){ payload[k] = v === undefined ? null : v } if(editingMilestone.value){ await updateMilestone(editingMilestone.value.id,payload) }else{ await createMilestone(pid.value,payload) }; milestoneDialogVisible.value=false; editingMilestone.value=null; milestones.value=(await getMilestones(pid.value)).data; ElMessage.success('已保存') } catch(e){ const d=e?.response?.data?.detail; ElMessage.error('保存失败: '+(Array.isArray(d)?d.map(x=>x.msg).join(';'):(typeof d==='string'?d:'请重试'))) } }
async function removeMilestone(id) { await deleteMilestone(id); milestones.value=(await getMilestones(pid.value)).data }
async function onGanttChanged() { try { milestones.value = (await getMilestones(pid.value)).data||[] } catch(e){} }
async function addMember() { if(!addMemberForm.value.member_id||!addMemberForm.value.role_id){ElMessage.warning('请选择');return}; try{const d={...addMemberForm.value}; if(d.phase_ids&&d.phase_ids.length) d.phase_ids=JSON.stringify(d.phase_ids); else d.phase_ids='[]'; await addProjectMember(pid.value,d); ElMessage.success('已添加');showAddMemberDialog.value=false;addMemberForm.value={member_id:null,role_id:null,allocation_pct:100,is_key:false,phase_ids:[]};projectMembers.value=(await getProjectMembers(pid.value)).data}catch(e){const detail=e?.response?.data?.detail; ElMessage.error('添加失败: ' + (typeof detail==='string'?detail:(Array.isArray(detail)?detail.map(x=>x.msg).join(';'):(e.message||'未知错误'))))} }
async function removeMember(row) { await removeProjectMember(row.id); projectMembers.value=(await getProjectMembers(pid.value)).data }
async function onRoleChange(row) { try{await updateProjectMember(row.id,{role_id:row.role_id})}catch(e){} }
async function onAllocationChange(row) { try{await updateProjectMember(row.id,{allocation_pct:row.allocation_pct})}catch(e){} }
async function onMemberKeyChange(row) { try{await updateProjectMember(row.id,{is_key:row.is_key})}catch(e){} }
async function onReportSubmit(data) { try { let res; if(editingReport.value){ res=await updateReport(editingReport.value.id,data) }else{ res=await createReport(pid.value,data) }; reportView.value='history'; editingReport.value=null; reports.value=(await getReports(pid.value)).data; const n=res.data?._risks_created; if(n>0){ ElMessage.success(`周报已提交，自动提取了 ${n} 条风险项`) }else{ ElMessage.success('周报已提交') } } catch(e) { const d=e?.response?.data?.detail; ElMessage.error('提交失败: '+(Array.isArray(d)?d.map(x=>x.msg).join(';'):(d||e.message||''))) } }
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
// AI import
const aiImportIng = ref(false)
const aiImportShow = ref(false)
const aiProjects = ref(null)
const aiSheetCount = ref(0)
const aiTotalWeeks = ref(0)
const aiError = ref('')
const importUrl = '/api/reports/import-excel'
async function handleImportUpload(options) {
  aiImportIng.value = true; aiError.value = ''; aiProjects.value = null
  try {
    const fd = new FormData()
    fd.append('file', options.file)
    const res = await api.post('/reports/import-excel-ai', fd)
    aiProjects.value = res.data?.projects || []
    aiSheetCount.value = res.data?.sheet_count || aiProjects.value.length
    aiTotalWeeks.value = aiProjects.value.reduce((s, p) => s + ((p.items && p.items.length) ? 1 : 0), 0)
    aiError.value = res.data?.ok ? '' : (res.data?.error || '解析失败')
    aiImportShow.value = true
  } catch(e) {
    aiError.value = '请求失败: ' + (e?.response?.data?.detail || e.message)
    aiProjects.value = null
    aiImportShow.value = true
  }
  aiImportIng.value = false
}
async function confirmAiImport() {
  if (!aiProjects.value?.length) return
  aiImportIng.value = true
  try {
    const res = await api.post('/reports/import-excel-ai-confirm', {
      projects: aiProjects.value,
      project_id: pid.value,
    })
    const ok = res.data?.results?.filter(r => r.ok)?.length || 0
    ElMessage.success(`导入成功！${ok}条记录`)
    aiImportShow.value = false
    reports.value = (await getReports(pid.value)).data||[]
  } catch(e) { ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e.message)) }
  aiImportIng.value = false
}
async function onImportSuccess(res) { ElMessage.success(res.message || `导入了 ${res.created} 条周报`); if (res.created>0) { reports.value = (await getReports(pid.value)).data||[] } }

// Paste import
const showPasteDlg = ref(false)
const pasteText = ref('')
const pasteIng = ref(false)
const pasteHeaders = ref([])
const pastePreview = ref([])

function parsePasteText() {
  const text = pasteText.value.trim()
  if (!text) { pastePreview.value = []; pasteHeaders.value = []; return }
  const lines = text.split('\n').filter(l => l.trim())
  if (lines.length < 2) { pastePreview.value = []; pasteHeaders.value = []; return }
  // Detect delimiter
  const sep = lines[0].includes('\t') ? '\t' : (lines[0].includes(',') ? ',' : '\t')
  pasteHeaders.value = lines[0].split(sep).map(h => h.trim()).filter(h => h)
  pastePreview.value = lines.slice(1, 21).map(line => line.split(sep).map(c => c.trim()))
}

// Auto-parse on paste
const _parseTimer = ref(null)
watch(pasteText, () => {
  clearTimeout(_parseTimer.value)
  _parseTimer.value = setTimeout(parsePasteText, 300)
})

async function doPasteImport() {
  if (!pasteText.value.trim()) { ElMessage.warning('请先粘贴周报内容'); return }
  pasteIng.value = true
  try {
    const res = await api.post('/reports/import-paste', {
      text: pasteText.value,
      project_id: pid.value,
    })
    if (res.data?.ok) {
      ElMessage.success(`导入成功！${res.data.count || res.data.item_count || ''}条`)
      showPasteDlg.value = false
      pasteText.value = ''
      reports.value = (await getReports(pid.value)).data||[]
    } else {
      ElMessage.error(res.data?.error || '解析失败')
    }
  } catch(e) {
    ElMessage.error('导入失败: ' + (e?.response?.data?.detail || e.message))
  }
  pasteIng.value = false
}
async function loadRefData() {
  try { reports.value = (await getReports(pid.value)).data||[] } catch(e){}
  try { riskItems.value = (await getRisks(pid.value)).data||[] } catch(e){}
  try { changeItems.value = (await getChanges(pid.value)).data||[] } catch(e){}
}
async function onReportDelete(r) { try { await api.delete(`/reports/${r.id}`); ElMessage.success('已删除'); reports.value=(await getReports(pid.value)).data } catch(e) { ElMessage.error('删除失败') } }
async function downloadPlan() {
  try {
    const res = await api.get(`/projects/${pid.value}/plan`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url
    a.download = `ProjectPlan-${project.value.code || pid.value}.xlsx`
    a.click(); URL.revokeObjectURL(url)
  } catch(e) { ElMessage.error('生成失败') }
}

onUnmounted(() => { currentProjectType.value = null })

async function confirmDeleteProj() { try { await ElMessageBox.confirm(`确认删除「${project.value.name}」?`,'删除项目',{type:'warning'}); await deleteProject(project.value.id); ElMessage.success('已删除'); router.push('/projects') } catch(e){} }
async function confirmCloneProj() { try { const {value:code}=await ElMessageBox.prompt(`复制「${project.value.name}」`,`新编号：${project.value.code}-COPY`,{inputValue:`${project.value.code}-COPY`}); await copyProject(project.value.id,{new_code:code}); ElMessage.success('已复制'); router.push('/projects') } catch(e){} }
</script>

<style scoped>
.proj-detail { max-width:100%; }
.pd-topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; background:var(--bg-white); padding:12px 20px; border-radius:8px; box-shadow:var(--shadow-sm); }
.pd-title { font-size:16px; font-weight:700; color:var(--text); margin-left:12px; }

/* Phase bar */
.pd-phase-bar { background:var(--bg-white); border-radius:8px; padding:16px 24px; margin-bottom:16px; box-shadow:var(--shadow-sm); }
.phase-bar-track { display:flex; align-items:flex-start; }
.phase-step { display:flex; flex-direction:column; align-items:center; flex:1; cursor:pointer; position:relative; }
.phase-dot { width:32px; height:32px; border-radius:50%; background:#e5e7eb; color:#9ca3af; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:13px; transition:all .2s; }
.phase-step.active .phase-dot { background:var(--primary); color:#fff; box-shadow:0 0 0 4px var(--primary-light); }
.phase-step.done .phase-dot { background:#10b981; color:#fff; }
.phase-label { font-size:12px; font-weight:600; color:var(--text-secondary); margin-top:6px; }
.phase-step.active .phase-label { color:var(--primary); }
.phase-desc { font-size:10px; color:var(--text-muted); margin-top:2px; }
.phase-connector { position:absolute; top:16px; left:calc(50% + 20px); right:calc(-50% + 20px); height:3px; background:#e5e7eb; }
.phase-connector.done { background:#10b981; }

/* Body layout */
.pd-body { display:flex; gap:16px; min-height:500px; }
.pd-nav { width:200px; flex-shrink:0; background:var(--bg-white); border-radius:8px; box-shadow:var(--shadow-sm); padding:8px 0; overflow-y:auto; max-height:calc(100vh - 260px); position:sticky; top:70px; }
.pd-nav-group { border-bottom:1px solid #f3f4f6; }
.pd-nav-group-hdr { display:flex; align-items:center; gap:6px; padding:10px 12px; cursor:pointer; border-left:3px solid transparent; transition:background .15s; }
.pd-nav-group-hdr:hover { background:#f9fafb; }
.group-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.group-name { font-size:12px; font-weight:700; color:var(--text); }
.group-desc { font-size:10px; color:var(--text-muted); margin-left:auto; margin-right:4px; display:none; }
.group-arrow { font-size:12px; color:var(--text-muted); transition:transform .2s; }
.group-arrow.open { transform:rotate(90deg); }
.pd-nav-items { padding:4px 0 8px 20px; }
.pd-nav-item { padding:6px 12px; font-size:12px; color:var(--text-secondary); cursor:pointer; border-radius:4px; display:flex; align-items:center; transition:all .1s; }
.pd-nav-item:hover { background:var(--bg); color:var(--text); }
.pd-nav-item.active { background:var(--primary-light); color:var(--primary); font-weight:600; }
.pd-nav-empty { font-size:11px; color:var(--text-muted); padding:6px 12px; }
.nav-badge { margin-left:auto; background:var(--danger); color:#fff; font-size:10px; padding:1px 6px; border-radius:8px; min-width:18px; text-align:center; }
.pd-nav-subgroup { margin:2px 0; }
.pd-nav-subgroup-hdr { display:flex; align-items:center; gap:6px; padding:6px 8px; margin-left:8px; cursor:pointer; border-left:3px solid transparent; border-radius:4px; transition:background .15s; }
.pd-nav-subgroup-hdr:hover { background:#f9fafb; }
.pd-nav-subgroup-hdr .group-name { font-size:12px; font-weight:600; }
.pd-nav-subgroup .pd-nav-items { padding:2px 0 6px 14px; }

.pd-content { flex:1; min-width:0; background:var(--bg-white); border-radius:8px; box-shadow:var(--shadow-sm); padding:20px; }
.pd-content-hdr { font-size:14px; font-weight:600; color:var(--text); margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid var(--border); }

/* Milestone groups */
.ms-group-hdr { display:flex; align-items:center; gap:8px; padding:8px 12px; background:#f9fafb; border:1px solid #f0f0f0; border-bottom:none; border-radius:6px 6px 0 0; margin-top:14px; }
.ms-group-hdr:first-of-type { margin-top:0; }
.ms-group-name { font-size:13px; font-weight:700; color:#1f2937; }
.ms-group-count { font-size:11px; color:#9ca3af; }
</style>
