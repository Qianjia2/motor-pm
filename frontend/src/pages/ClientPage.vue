<template>
  <div class="client-page">
    <div class="page-head">
      <h2>客户管理</h2>
      <el-button type="primary" size="small" @click="showDialog(null)">+ 新增客户</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- ══════════ Tab 1: 客户列表 ══════════ -->
      <el-tab-pane label="客户列表" name="list">
        <el-table :data="clients" size="small" v-loading="loading" stripe>
          <el-table-column prop="name" label="客户名称" min-width="160">
            <template #default="{row}">
              <el-link type="primary" @click="openProfile(row)">{{ row.name }}</el-link>
            </template>
          </el-table-column>
          <el-table-column prop="abbreviation" label="简称" width="80" />
          <el-table-column prop="industry" label="行业" width="100" />
          <el-table-column prop="contact_person" label="联系人" width="100" />
          <el-table-column prop="contact_phone" label="电话" width="120" />
          <el-table-column prop="address" label="地区" min-width="120" />
          <el-table-column label="合作状态" width="110">
            <template #default="{row}">
              <el-popover trigger="click" :width="132" popper-style="padding:8px">
                <template #reference>
                  <el-tag :type="statusTagType(row.cooperation_status)" size="small" style="cursor:pointer" effect="light">
                    {{ row.cooperation_status || '潜在' }}
                  </el-tag>
                </template>
                <div style="display:flex;flex-direction:column;gap:6px">
                  <el-button v-for="s in statusOptions" :key="s.value" size="small"
                    :type="(row.cooperation_status || '潜在') === s.value ? 'primary' : 'default'"
                    @click="changeStatus(row, s.value)">{{ s.label }}</el-button>
                </div>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{row}">
              <el-button link size="small" type="primary" @click="openProfile(row)">360</el-button>
              <el-button link size="small" @click="openOppDialog(null, row)">商机</el-button>
              <el-button link size="small" @click="showDialog(row)">编辑</el-button>
              <el-button link size="small" type="danger" @click="delClient(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ══════════ Tab 2: 商机看板 ══════════ -->
      <el-tab-pane label="商机看板" name="board">
        <div v-loading="boardLoading">
          <div class="stat-cards">
            <div class="stat-card"><div class="stat-num">{{ board.total_count || 0 }}</div><div class="stat-label">商机总数</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#e6a23c">{{ fmtAmount(board.open_amount) }}</div><div class="stat-label">在谈金额(万)</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#67c23a">{{ board.won?.count || 0 }}</div><div class="stat-label">已赢单</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#409eff">{{ fmtAmount(board.won?.amount) }}</div><div class="stat-label">赢单金额(万)</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#f56c6c">{{ board.conversion_rate || 0 }}%</div><div class="stat-label">赢单转化率</div></div>
          </div>

          <!-- 漏斗 -->
          <div class="funnel-bar">
            <div v-for="(st, i) in funnel" :key="st.name" class="funnel-seg" :style="{ width: st.pct + '%', background: st.color }"
              :title="st.name + ': ' + st.count + ' 家 (' + st.rate + '%)'">
              <span class="funnel-seg-label">{{ st.name }} {{ st.count }}</span>
            </div>
          </div>

          <div class="board-toolbar">
            <span class="board-title">阶段看板</span>
            <el-button type="primary" size="small" @click="openOppDialog(null, null)">+ 新增商机</el-button>
          </div>
          <div class="kanban">
            <div v-for="col in board.columns || []" :key="col.stage" class="kb-col">
              <div class="kb-head">
                <span>{{ col.stage }}</span>
                <el-tag size="small" type="info">{{ col.count }}</el-tag>
                <span class="kb-amount">{{ fmtAmount(col.amount) }}万</span>
              </div>
              <div class="kb-body">
                <div v-for="o in col.items" :key="o.id" class="kb-card" @click="openOppDialog(o, null)">
                  <div class="kb-card-name">{{ o.name }}</div>
                  <div class="kb-card-client">{{ o.client_name }}</div>
                  <div v-if="o.project_name" class="kb-card-proj" :title="o.project_code">
                    <el-link type="primary" :underline="false" size="small" @click.stop="goProject(o.project_id)">📎 {{ o.project_name }}</el-link>
                  </div>
                  <div class="kb-card-row"><span class="kb-money">{{ o.amount || 0 }}万</span><span class="kb-prob">{{ o.probability }}%</span></div>
                  <div class="kb-card-foot">
                    <span>{{ o.owner || '-' }}</span>
                    <span class="kb-src">{{ o.lead_source || '·' }}</span>
                  </div>
                </div>
                <div v-if="!col.items.length" class="kb-empty">暂无</div>
              </div>
            </div>
            <div class="kb-col kb-closed">
              <div class="kb-head"><span style="color:#67c23a">已赢单</span><el-tag size="small" type="success">{{ board.won?.count || 0 }}</el-tag></div>
              <div class="kb-body">
                <div v-for="o in board.won?.items || []" :key="o.id" class="kb-card" @click="openOppDialog(o, null)">
                  <div class="kb-card-name">{{ o.name }}</div>
                  <div class="kb-card-client">{{ o.client_name }}</div>
                  <div v-if="o.project_name" class="kb-card-proj" :title="o.project_code">
                    <el-link type="primary" :underline="false" size="small" @click.stop="goProject(o.project_id)">📎 {{ o.project_name }}</el-link>
                  </div>
                  <div class="kb-card-row"><span class="kb-money">{{ o.amount || 0 }}万</span></div>
                </div>
                <div v-if="!(board.won?.items || []).length" class="kb-empty">暂无</div>
              </div>
            </div>
            <div class="kb-col kb-closed">
              <div class="kb-head"><span style="color:#f56c6c">已丢单</span><el-tag size="small" type="danger">{{ board.lost?.count || 0 }}</el-tag></div>
              <div class="kb-body">
                <div v-for="o in board.lost?.items || []" :key="o.id" class="kb-card" @click="openOppDialog(o, null)">
                  <div class="kb-card-name">{{ o.name }}</div>
                  <div class="kb-card-client">{{ o.client_name }}</div>
                  <div v-if="o.project_name" class="kb-card-proj" :title="o.project_code">
                    <el-link type="primary" :underline="false" size="small" @click.stop="goProject(o.project_id)">📎 {{ o.project_name }}</el-link>
                  </div>
                  <div class="kb-card-row"><span class="kb-money">{{ o.amount || 0 }}万</span></div>
                </div>
                <div v-if="!(board.lost?.items || []).length" class="kb-empty">暂无</div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑客户 -->
    <el-dialog :title="editing ? '编辑客户' : '新增客户'" v-model="dialogVisible" width="500px">
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="客户名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="简称"><el-input v-model="form.abbreviation" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact_person" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.contact_email" /></el-form-item>
        <el-form-item label="地区"><el-input v-model="form.address" /></el-form-item>
        <el-form-item label="合作状态">
          <el-select v-model="form.cooperation_status" style="width:100%">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="primary" @click="saveClient" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 商机编辑 -->
    <el-dialog :title="oppEditing ? '编辑商机' : '新增商机'" v-model="oppVisible" width="560px">
      <el-form :model="oppForm" label-width="100px" size="small">
        <el-form-item label="商机名称" required><el-input v-model="oppForm.name" placeholder="如：XX电机平台开发项目" /></el-form-item>
        <el-form-item label="关联客户" required>
          <el-select v-model="oppForm.client_id" style="width:100%" filterable :disabled="!!oppForm._lockedClient" @change="onOppClientChange">
            <el-option v-for="c in clients" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联项目">
          <el-select v-model="oppForm.project_id" style="width:100%" filterable clearable placeholder="商机对应的实际项目（如已立项）">
            <el-option v-for="p in clientProjects" :key="p.id" :label="`${p.name}（${p.code}）`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="当前阶段">
              <el-select v-model="oppForm.stage" style="width:100%">
                <el-option v-for="s in stageOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="线索来源">
              <el-select v-model="oppForm.lead_source" style="width:100%" clearable>
                <el-option v-for="s in leadSources" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="预计金额(万)"><el-input-number v-model="oppForm.amount" :min="0" :precision="2" style="width:100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="成交概率%"><el-input-number v-model="oppForm.probability" :min="0" :max="100" style="width:100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="预计成交日期"><el-date-picker v-model="oppForm.expected_close" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="负责人"><el-input v-model="oppForm.owner" placeholder="如：张翔" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="oppForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="oppEditing" type="danger" plain size="small" style="float:left" @click="delOpp">删除商机</el-button>
        <el-button @click="oppVisible=false">取消</el-button>
        <el-button type="primary" @click="saveOpp" :loading="savingOpp">保存</el-button>
      </template>
    </el-dialog>

    <!-- 客户360 -->
    <el-drawer v-model="profileVisible" :title="profile?.client?.name || '客户360'" size="700px">
      <div v-loading="profileLoading" style="min-height:320px">
        <template v-if="profile && profile.client">
          <div class="p360-head">
            <el-tag :type="statusTagType(profile.client.cooperation_status)">{{ profile.client.cooperation_status || '潜在' }}</el-tag>
            <span class="p360-brief">{{ profile.client.industry || '-' }} · {{ profile.client.address || '地区未填' }}</span>
          </div>
          <div class="stat-cards" style="grid-template-columns: repeat(6, 1fr); margin-bottom: 14px">
            <div class="stat-card"><div class="stat-num">{{ profile.stats.opportunity_count }}</div><div class="stat-label">商机</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#67c23a">{{ profile.stats.won_count }}</div><div class="stat-label">赢单</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#409eff">{{ fmtAmount(profile.stats.won_amount) }}</div><div class="stat-label">赢单金额(万)</div></div>
            <div class="stat-card"><div class="stat-num">{{ profile.stats.project_count }}</div><div class="stat-label">项目总数</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#67c23a">{{ profile.stats.active_project_count }}</div><div class="stat-label">进行中</div></div>
            <div class="stat-card"><div class="stat-num" style="color:#e6a23c">{{ profile.client.cooperation_status === '合作中' ? '活跃' : '一般' }}</div><div class="stat-label">客户热度</div></div>
          </div>

          <el-tabs v-model="p360Tab">
            <!-- 商机概览 -->
            <el-tab-pane label="商机概览" name="overview">
              <div class="p360-section">
                <div class="p360-title">
                  商机（{{ profile.opportunities.length }}）
                  <el-button link size="small" type="primary" @click="openOppDialog(null, profile.client)">+ 新增</el-button>
                </div>
                <div v-for="o in profile.opportunities" :key="o.id" class="p360-opp" @click="openOppDialog(o, null)">
                  <div style="flex:1">
                    <div style="font-weight:600">{{ o.name }}</div>
                    <div style="font-size:12px;color:#909399">{{ o.stage }} · 概率 {{ o.probability }}% · {{ o.owner || '未指定负责人' }}</div>
                    <div v-if="o.project_name" style="font-size:12px;margin-top:2px">
                      <el-link type="primary" :underline="false" size="small" @click.stop="goProject(o.project_id)">📎 {{ o.project_name }}（{{ o.project_code }}）</el-link>
                    </div>
                  </div>
                  <span style="color:#e6a23c;font-weight:700">{{ o.amount || 0 }}万</span>
                  <el-tag size="small" :type="o.status==='won'?'success':(o.status==='lost'?'danger':'info')" style="margin-left:8px">
                    {{ o.status==='won'?'赢单':(o.status==='lost'?'丢单':'在谈') }}
                  </el-tag>
                </div>
                <div v-if="!profile.opportunities.length" class="p360-empty">暂无商机，点击右上角新增</div>
              </div>
            </el-tab-pane>

            <!-- 关联项目 -->
            <el-tab-pane label="关联项目" name="projects">
              <div class="p360-section">
                <div class="p360-title">关联项目（{{ profile.projects.length }}）</div>
                <div v-for="p in profile.projects" :key="p.id" class="p360-proj">
                  <div style="flex:1">
                    <router-link :to="`/projects/${p.id}`" style="font-weight:600;color:#409eff;text-decoration:none">{{ p.name }}</router-link>
                    <div style="font-size:12px;color:#909399">{{ p.code || '' }} · 进度 {{ p.completion_pct }}%</div>
                  </div>
                  <el-tag size="small" :type="p.overall_status==='blocked'?'danger':(p.overall_status==='risk'?'warning':'success')">
                    {{ p.overall_status==='blocked'?'阻塞':(p.overall_status==='risk'?'风险':'正常') }}
                  </el-tag>
                </div>
                <div v-if="!profile.projects.length" class="p360-empty">暂无关联项目</div>
              </div>
            </el-tab-pane>

            <!-- 联系人 -->
            <el-tab-pane label="联系人" name="contacts">
              <div class="p360-section">
                <div class="p360-title">
                  联系人（{{ (profile.contacts || []).length }}）
                  <el-button link size="small" type="primary" @click="openContactDialog(null)">+ 新增</el-button>
                </div>
                <div v-for="k in profile.contacts" :key="k.id" class="contact-item">
                  <div style="flex:1">
                    <div class="contact-name">
                      {{ k.name }}
                      <el-tag v-if="k.is_primary" size="small" type="warning" effect="plain" style="margin-left:6px">主要</el-tag>
                      <span v-if="k.title" class="contact-title">{{ k.title }}</span>
                    </div>
                    <div class="contact-line">
                      <span v-if="k.phone">📞 {{ k.phone }}</span>
                      <span v-if="k.email">✉️ {{ k.email }}</span>
                    </div>
                    <div v-if="k.notes" class="contact-line" style="color:#909399">{{ k.notes }}</div>
                  </div>
                  <div style="display:flex;gap:6px">
                    <el-button link size="small" type="primary" @click="openContactDialog(k)">编辑</el-button>
                    <el-button link size="small" type="danger" @click="delContact(k)">删除</el-button>
                  </div>
                </div>
                <div v-if="!(profile.contacts || []).length" class="p360-empty">暂无联系人，点击右上角新增</div>
              </div>
            </el-tab-pane>

            <!-- 关系图谱 -->
            <el-tab-pane label="关系图谱" name="graph">
              <div class="p360-section">
                <div class="p360-title">客户-项目-商机 关系图谱</div>
                <svg :viewBox="`0 0 ${graph.W} ${graph.H}`" class="g-svg">
                  <defs>
                    <marker id="garr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 Z" fill="#c0c4cc"/>
                    </marker>
                  </defs>
                  <circle :cx="graph.client.x" :cy="graph.client.y" r="26" fill="#409eff"/>
                  <text :x="graph.client.x" :y="graph.client.y + 5" text-anchor="middle" fill="#fff" font-size="11" font-weight="700">
                    {{ profile.client.name.length > 5 ? profile.client.name.slice(0, 5) + '…' : profile.client.name }}
                  </text>
                  <line v-for="(l, i) in graph.links" :key="'l' + i" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2"
                    stroke="#c0c4cc" stroke-width="1.2" marker-end="url(#garr)"/>
                  <g v-for="n in graph.nodes" :key="n.type + n.id">
                    <rect :x="n.x - n.w / 2" :y="n.y - n.h / 2" :width="n.w" :height="n.h" rx="6"
                      :class="n.type === 'project' ? 'g-node g-proj' : 'g-node g-opp'"/>
                    <text :x="n.x" :y="n.y - 1" text-anchor="middle" font-size="12" font-weight="600" fill="#303133"
                      class="g-name">{{ n.name.length > 11 ? n.name.slice(0, 11) + '…' : n.name }}</text>
                    <text v-if="n.type === 'project'" :x="n.x" :y="n.y + 13" text-anchor="middle" font-size="10" fill="#909399">
                      {{ n.pm && n.pm.length ? 'PM: ' + n.pm.join('/') : '暂无PM' }}
                    </text>
                    <text v-else :x="n.x" :y="n.y + 13" text-anchor="middle" font-size="10"
                      :fill="n.status === 'won' ? '#67c23a' : (n.status === 'lost' ? '#f56c6c' : '#e6a23c')">
                      {{ n.stage }}{{ n.amount ? ' · ' + n.amount + '万' : '' }}
                    </text>
                  </g>
                </svg>
                <div class="g-legend">
                  <span><i class="dot" style="background:#409eff"></i>客户</span>
                  <span><i class="dot" style="background:#67c23a"></i>关联项目</span>
                  <span><i class="dot" style="background:#e6a23c"></i>商机</span>
                </div>
                <div v-if="graph.moreP > 0 || graph.moreO > 0" style="font-size:12px;color:#909399;text-align:center;margin-top:6px">
                  另有 {{ graph.moreP }} 个项目、{{ graph.moreO }} 个商机未展示（见其他标签页）
                </div>
              </div>
            </el-tab-pane>

            <!-- 沟通记录 -->
            <el-tab-pane label="沟通记录" name="comms">
              <div class="p360-section">
                <div class="p360-title">
                  沟通记录（{{ filteredComms.length }}<template v-if="commProjectFilter !== null"> / {{ (profile.communications || []).length }}</template>）
                  <el-button link size="small" type="primary" @click="openCommDialog(null)">+ 新增</el-button>
                </div>
                <div v-if="(profile.communications || []).length" class="comm-filter">
                  <el-select v-model="commProjectFilter" size="small" style="width:230px" placeholder="按项目筛选">
                    <el-option label="全部记录" :value="null" />
                    <el-option label="未关联项目" :value="0" />
                    <el-option v-for="p in profileProjects" :key="p.id" :label="`${p.name}（${p.code}）`" :value="p.id" />
                  </el-select>
                </div>
                <div v-for="c in filteredComms" :key="c.id" class="comm-item" @click="openCommDialog(c)">
                  <div class="comm-head">
                    <el-tag size="small" effect="plain">{{ c.comm_type }}</el-tag>
                    <span class="comm-subject">{{ c.subject }}</span>
                    <span class="comm-date">{{ c.comm_date || '' }}</span>
                  </div>
                  <div class="comm-content">{{ c.content || '（无内容）' }}</div>
                  <div v-if="(c.images || []).length" class="comm-thumbs">
                    <a v-for="img in (c.images || []).slice(0, 4)" :key="img" :href="'/uploads/' + img" target="_blank">
                      <img :src="'/uploads/' + img" class="comm-thumb" alt="沟通图片" />
                    </a>
                    <span v-if="(c.images || []).length > 4" class="comm-more">+{{ (c.images || []).length - 4 }}</span>
                  </div>
                  <div class="comm-foot">
                    <span v-if="c.contact_person">对方：{{ c.contact_person }}</span>
                    <span v-if="c.owner">我方：{{ c.owner }}</span>
                    <span v-if="c.project_id" class="comm-proj" title="打开关联项目" @click.stop="goProject(c.project_id)">
                      📎 {{ c.project_name || c.project_code || ('项目 #' + c.project_id) }}
                    </span>
                  </div>
                </div>
                <div v-if="!filteredComms.length" class="p360-empty">
                  {{ (profile.communications || []).length ? '该筛选下暂无沟通记录' : '暂无沟通记录，点击右上角新增' }}
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-drawer>

    <!-- 沟通记录编辑 -->
    <CommDialog
      v-model="commVisible"
      :client-id="profile?.client?.id ?? null"
      :projects="profileProjects"
      :comm="commEditing"
      @saved="loadProfile(profile?.client?.id)"
      @deleted="loadProfile(profile?.client?.id)"
    />

    <!-- 联系人编辑 -->
    <el-dialog :title="contactEditing ? '编辑联系人' : '新增联系人'" v-model="contactVisible" width="480px">
      <el-form :model="contactForm" label-width="80px" size="small">
        <el-form-item label="姓名" required><el-input v-model="contactForm.name" placeholder="联系人姓名" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="职务"><el-input v-model="contactForm.title" placeholder="如：技术总监" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="主要联系人">
              <el-switch v-model="contactForm.is_primary" active-text="是" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="电话"><el-input v-model="contactForm.phone" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱"><el-input v-model="contactForm.email" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="contactForm.notes" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactVisible=false">取消</el-button>
        <el-button type="primary" @click="saveContact" :loading="savingContact">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'
import CommDialog from '../components/client/CommDialog.vue'

const router = useRouter()
const activeTab = ref('list')
const clients = ref([])
const loading = ref(false)
const board = ref({})
const boardLoading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = ref({})

const statusOptions = [
  { value: '潜在', label: '潜在' },
  { value: '合作中', label: '合作中' },
  { value: '已暂停', label: '已暂停' },
  { value: '已结束', label: '已结束' },
]
const statusTagMap = { 潜在: 'info', 合作中: 'success', 已暂停: 'warning', 已结束: 'danger' }
const stageColorMap = { 线索: '#909399', 需求确认: '#409eff', 方案报价: '#7a5cff', 合同签订: '#e6a23c', 样机试制: '#67c23a', 量产: '#f56c6c' }
function statusTagType(s) { return statusTagMap[s] || 'info' }

const stages = ['线索', '需求确认', '方案报价', '合同签订', '样机试制', '量产']
const stageOptions = [
  ...stages.map(s => ({ label: s, value: s })),
  { label: '已赢单', value: 'won' },
  { label: '已丢单', value: 'lost' },
]
const leadSources = ['展会', '网络', '转介绍', '老客户回访', '电话营销', '招投标', '其他']
const fmtAmount = v => (v === 0 || v == null ? '0' : String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ','))

// 漏斗（线索→量产→赢单）
const funnel = computed(() => {
  const cols = board.value.columns || []
  const wonCount = board.value.won?.count || 0
  const stagesArr = [...cols.map(c => ({ name: c.stage, count: c.count })), { name: '赢单', count: wonCount }]
  const max = Math.max(...stagesArr.map(s => s.count), 1)
  return stagesArr.map((s, i) => ({
    ...s,
    color: s.name === '赢单' ? '#67c23a' : (stageColorMap[s.name] || '#909399'),
    pct: Math.max(6, Math.round(s.count / max * 100)),
    rate: i > 0 && stagesArr[i - 1].count > 0 ? Math.round(s.count / stagesArr[i - 1].count * 100) : 100,
  }))
})

async function loadClients() {
  loading.value = true
  try { const res = await api.get('/clients'); clients.value = Array.isArray(res.data) ? res.data : (res.data?.clients || []) } catch { clients.value = [] }
  loading.value = false
}
async function loadBoard() {
  boardLoading.value = true
  try { const res = await api.get('/opportunities/board'); board.value = res.data || {} } catch {}
  boardLoading.value = false
}
function onTabChange(tab) {
  if (tab === 'board' && !Object.keys(board.value).length) loadBoard()
}

async function changeStatus(row, v) {
  try {
    await api.put(`/clients/${row.id}`, { cooperation_status: v })
    row.cooperation_status = v
    // 若 360 抽屉正展示同一客户，同步状态
    if (profile.value?.client?.id === row.id) profile.value.client.cooperation_status = v
    ElMessage.success('合作状态已更新')
  } catch (e) {
    ElMessage.error('更新失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
}

// ── 商机 ──
const oppVisible = ref(false)
const oppEditing = ref(null)
const savingOpp = ref(false)
const oppForm = ref({})
const allProjects = ref([])
const projectsLoaded = ref(false)
async function loadProjects() {
  try {
    const res = await api.get('/projects', { params: { page_size: 100, sort_by: 'code' } })
    // 现网返回 { data: [...], total, page, page_size },不是 { items: [...] } —— 这里原先只认 items,
    // 导致 allProjects 恒为空、商机/沟通记录的项目下拉永远是空的
    const d = res.data
    allProjects.value = Array.isArray(d) ? d : (d?.data || d?.items || [])
    projectsLoaded.value = true
  } catch { allProjects.value = [] }
}
const clientProjects = computed(() =>
  oppForm.value.client_id
    ? allProjects.value.filter(p => p.client?.id === oppForm.value.client_id)
    : []
)
function onOppClientChange() {
  if (oppForm.value.project_id && !clientProjects.value.some(p => p.id === oppForm.value.project_id)) {
    oppForm.value.project_id = null
  }
}
function goProject(id) {
  // 应用是 history 模式(router.js createWebHistory),写 '#/projects/x' 只会改 hash、不换路由
  if (id) router.push(`/projects/${id}`)
}
async function openOppDialog(opp, client) {
  if (!projectsLoaded.value) await loadProjects()
  if (opp) {
    oppEditing.value = opp
    oppForm.value = { ...opp }
  } else {
    oppEditing.value = null
    oppForm.value = {
      name: '', client_id: client ? client.id : null, project_id: null,
      lead_source: '', amount: 0, stage: '线索', probability: 0,
      expected_close: null, owner: '', description: '', status: 'open',
      _lockedClient: client ? true : false,
    }
  }
  oppVisible.value = true
}
async function saveOpp() {
  if (!oppForm.value.name) { ElMessage.warning('请输入商机名称'); return }
  if (!oppForm.value.client_id) { ElMessage.warning('请选择关联客户'); return }
  savingOpp.value = true
  try {
    const data = { ...oppForm.value }
    delete data._lockedClient
    if (oppEditing.value) {
      await api.put(`/opportunities/${oppEditing.value.id}`, data)
      ElMessage.success('已更新')
    } else {
      await api.post('/opportunities', data)
      ElMessage.success('已创建')
    }
    oppVisible.value = false
    loadBoard()
    // 360 抽屉开着且是同一客户时刷新
    if (profileVisible.value && profile.value?.client?.id && oppForm.value.client_id === profile.value.client.id) {
      loadProfile(profile.value.client.id)
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  savingOpp.value = false
}
async function delOpp() {
  try {
    await ElMessageBox.confirm('删除该商机？', '确认', { type: 'warning' })
    await api.delete(`/opportunities/${oppEditing.value.id}`)
    ElMessage.success('已删除')
    oppVisible.value = false
    loadBoard()
    if (profileVisible.value && profile.value?.client) {
      loadProfile(profile.value.client.id)
    }
  } catch {}
}

// ── 客户360 ──
const profileVisible = ref(false)
const profileLoading = ref(false)
const profile = ref(null)
const p360Tab = ref('overview')
async function loadProfile(cid) {
  profileLoading.value = true
  try {
    const res = await api.get(`/clients/${cid}/profile`)
    profile.value = res.data
  } catch (e) {
    ElMessage.error('加载失败: ' + (e?.response?.data?.detail || e?.message || ''))
    profileVisible.value = false
  }
  profileLoading.value = false
}
async function openProfile(client) {
  profileVisible.value = true
  profile.value = null
  p360Tab.value = 'overview'
  commProjectFilter.value = null      // 换客户时重置筛选,防止残留
  commEditing.value = null
  if (!projectsLoaded.value) loadProjects()   // 沟通记录的项目筛选/下拉都依赖 allProjects
  await loadProfile(client.id)
}

// 关系图谱布局（纯 SVG：客户居中，左项目右商机）
const graph = computed(() => {
  const g = profile.value?.graph || { projects: [], opportunities: [] }
  const pros = (g.projects || []).slice(0, 8)
  const opps = (g.opportunities || []).slice(0, 8)
  const W = 600
  const client = { x: W / 2, y: 42 }
  const maxCol = Math.max(pros.length, opps.length, 1)
  const H = Math.max(420, 100 + maxCol * 78)
  const nodes = []
  const links = []
  const mkCol = (items, x) => {
    const startY = 116
    items.forEach((it, i) => {
      const y = startY + i * 78
      nodes.push({ ...it, x, y, w: 218, h: 42 })
      links.push({ x1: client.x, y1: client.y + 26, x2: x, y2: y })
    })
  }
  mkCol(pros, 118)
  mkCol(opps, W - 118)
  return {
    W, H, client, nodes, links,
    moreP: (g.projects || []).length - pros.length,
    moreO: (g.opportunities || []).length - opps.length,
  }
})

// ── 沟通记录 ──
// 表单与上传/AI汇总逻辑在 components/client/CommDialog.vue,这里只保留可见性、可选项目与筛选
const commVisible = ref(false)
const commEditing = ref(null)
const commProjectFilter = ref(null)   // null=全部, 0=未关联项目, 其余=project_id
// 当前客户名下的项目(供「关联项目」下拉)。不能复用 clientProjects——那个绑定的是 oppForm.client_id
const profileProjects = computed(() => {
  const cid = profile.value?.client?.id
  return cid ? allProjects.value.filter(p => p.client?.id === cid) : []
})
const filteredComms = computed(() => {
  const list = profile.value?.communications || []
  if (commProjectFilter.value === null) return list
  return commProjectFilter.value === 0
    ? list.filter(c => !c.project_id)
    : list.filter(c => c.project_id === commProjectFilter.value)
})
async function openCommDialog(comm) {
  if (!projectsLoaded.value) await loadProjects()
  commEditing.value = comm || null
  commVisible.value = true
}

// ── 联系人 ──
const contactVisible = ref(false)
const contactEditing = ref(null)
const savingContact = ref(false)
const contactForm = ref({})
function openContactDialog(contact) {
  if (contact) {
    contactEditing.value = contact
    contactForm.value = { ...contact }
  } else {
    contactEditing.value = null
    contactForm.value = { name: '', title: '', phone: '', email: '', is_primary: false, notes: '' }
  }
  contactVisible.value = true
}
async function saveContact() {
  const cid = profile.value?.client?.id
  if (!cid) return
  if (!contactForm.value.name?.trim()) { ElMessage.warning('请输入联系人姓名'); return }
  savingContact.value = true
  try {
    if (contactEditing.value) {
      await api.put(`/contacts/${contactEditing.value.id}`, contactForm.value)
    } else {
      await api.post(`/clients/${cid}/contacts`, contactForm.value)
    }
    ElMessage.success('已保存')
    contactVisible.value = false
    loadProfile(cid)
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  savingContact.value = false
}
async function delContact(contact) {
  try {
    await ElMessageBox.confirm(`删除联系人「${contact.name}」？`, '确认', { type: 'warning' })
    await api.delete(`/contacts/${contact.id}`)
    ElMessage.success('已删除')
    loadProfile(profile.value?.client?.id)
  } catch {}
}

function showDialog(row) {
  editing.value = row
  form.value = row ? { ...row } : { name: '', abbreviation: '', industry: '', contact_person: '', contact_phone: '', contact_email: '', address: '', cooperation_status: '潜在' }
  dialogVisible.value = true
}
async function saveClient() {
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/clients/${editing.value.id}`, form.value)
      ElMessage.success('已更新')
    } else {
      await api.post('/clients', form.value)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false; loadClients()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  saving.value = false
}
async function delClient(id) {
  try {
    await ElMessageBox.confirm('删除此客户？关联项目不受影响', '确认', { type: 'warning' })
    await api.delete(`/clients/${id}`)
    ElMessage.success('已删除'); loadClients()
  } catch {}
}

onMounted(() => loadClients())
</script>

<style scoped>
.client-page { max-width: 1400px; }
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.page-head h2 { font-size: 18px; font-weight: 700; margin: 0; }

.stat-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: #fff; border: 1px solid #e4e7ed; border-radius: 8px; padding: 14px; text-align: center; }
.stat-num { font-size: 26px; font-weight: 700; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }

/* 漏斗条 */
.funnel-bar { display: flex; gap: 3px; height: 34px; margin-bottom: 16px; border-radius: 6px; overflow: hidden; background: #f0f2f5; }
.funnel-seg { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; min-width: 6%; transition: width .3s; }
.funnel-seg-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 6px; }

/* 看板 */
.board-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.board-title { font-size: 15px; font-weight: 700; }
.kanban { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }
.kb-col { min-width: 210px; max-width: 210px; background: #f5f7fa; border-radius: 8px; padding: 8px; display: flex; flex-direction: column; }
.kb-closed { background: #fdf6f6; }
.kb-head { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 4px 6px 8px; }
.kb-amount { margin-left: auto; font-size: 11px; color: #e6a23c; font-weight: 600; }
.kb-body { display: flex; flex-direction: column; gap: 8px; min-height: 60px; }
.kb-card { background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px 10px; cursor: pointer; transition: box-shadow .15s; }
.kb-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.kb-card-name { font-size: 13px; font-weight: 600; }
.kb-card-client { font-size: 12px; color: #909399; margin-top: 2px; }
.kb-card-proj { margin-top: 3px; font-size: 12px; }
.kb-card-proj :deep(.el-link) { font-size: 12px; }
.kb-card-row { display: flex; justify-content: space-between; margin-top: 6px; }
.kb-money { color: #e6a23c; font-weight: 700; font-size: 13px; }
.kb-prob { font-size: 12px; color: #409eff; }
.kb-card-foot { display: flex; justify-content: space-between; font-size: 11px; color: #909399; margin-top: 6px; }
.kb-empty { color: #c0c4cc; font-size: 12px; text-align: center; padding: 14px 0; }

/* 客户360 */
.p360-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.p360-brief { font-size: 13px; color: #909399; }
.p360-section { border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.p360-title { display: flex; justify-content: space-between; align-items: center; font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.p360-opp { display: flex; align-items: center; border-bottom: 1px solid #f0f2f5; padding: 8px 0; cursor: pointer; }
.p360-opp:last-child { border-bottom: none; }
.p360-opp:hover { background: #fafafa; }
.p360-proj { display: flex; align-items: center; border-bottom: 1px solid #f0f2f5; padding: 8px 0; }
.p360-proj:last-child { border-bottom: none; }
.p360-empty { color: #c0c4cc; font-size: 13px; padding: 10px 0; text-align: center; }

/* 关系图谱 */
.g-svg { width: 100%; }
.g-node { stroke-width: 1.4; }
.g-proj { fill: #f0f9eb; stroke: #67c23a; }
.g-opp { fill: #fdf6ec; stroke: #e6a23c; }
.g-name { user-select: none; }
.g-legend { display: flex; justify-content: center; gap: 18px; margin-top: 8px; font-size: 12px; color: #606266; }
.g-legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: -1px; }

/* 沟通记录 */
.comm-item { border-bottom: 1px solid #f0f2f5; padding: 9px 0; cursor: pointer; }
.comm-item:last-child { border-bottom: none; }
.comm-item:hover { background: #fafafa; }
.comm-head { display: flex; align-items: center; gap: 8px; }
.comm-subject { font-weight: 600; font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.comm-date { font-size: 12px; color: #909399; }
.comm-content { font-size: 12px; color: #606266; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.comm-thumbs { display: flex; gap: 5px; margin-top: 6px; }
.comm-thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 4px; border: 1px solid #f0f2f5; }
.comm-more { font-size: 12px; color: #909399; align-self: center; }
.comm-foot { display: flex; justify-content: flex-start; gap: 14px; font-size: 11px; color: #909399; margin-top: 4px; }
.comm-filter { margin-bottom: 6px; }
.comm-proj { color: #409eff; cursor: pointer; margin-left: auto; }
.comm-proj:hover { text-decoration: underline; }

/* 联系人 */
.contact-item { display: flex; align-items: center; border-bottom: 1px solid #f0f2f5; padding: 9px 0; }
.contact-item:last-child { border-bottom: none; }
.contact-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; }
.contact-title { font-size: 12px; color: #909399; font-weight: 400; margin-left: 8px; }
.contact-line { display: flex; gap: 14px; font-size: 12px; color: #606266; margin-top: 3px; }
</style>
