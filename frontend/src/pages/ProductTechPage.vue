<template>
  <div class="pt-page" v-loading="loading" element-loading-text="加载产品数据...">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h2 style="margin:0;font-size:18px">产品技术库</h2>
        <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted)">按电机专业 · 电机控制专业管理全部产品型号及技术参数</p>
      </div>
    </div>

    <!-- Specialty Tabs -->
    <el-tabs v-model="activeSpecialty" type="card" @tab-change="onTabChange">
      <el-tab-pane v-for="spec in specialties" :key="spec.value" :label="spec.label" :name="spec.value" />
    </el-tabs>

    <!-- ═══════════ Motor Specialty Layout ═══════════ -->
    <template v-if="activeSpecialty === '电机专业'">
      <!-- Stats Cards -->
      <div class="stat-grid" style="margin-bottom:12px">
        <div class="stat-card stat-info">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">产品总数</div>
        </div>
        <div class="stat-card stat-success">
          <div class="stat-value">{{ stats.on_sale }}</div>
          <div class="stat-label">在售产品</div>
        </div>
        <div class="stat-card stat-warning">
          <div class="stat-value">{{ stats.in_dev }}</div>
          <div class="stat-label">研发中</div>
        </div>
        <div class="stat-card" style="background:var(--bg-card);border:1px solid #6366f1">
          <div class="stat-value" style="color:#6366f1">{{ stats.pre_research }}</div>
          <div class="stat-label">预研储备</div>
        </div>
      </div>
      <!-- Product Line & Motor Type breakdown -->
      <div v-if="stats.product_lines" style="display:flex;gap:16px;margin-bottom:12px;font-size:12px;color:var(--text-muted);flex-wrap:wrap">
        <div v-for="(cnt,line) in stats.product_lines" :key="line" style="background:var(--bg-hover);padding:2px 8px;border-radius:4px;white-space:nowrap">
          {{ line }} <b>{{ cnt }}</b>
        </div>
        <div v-if="stats.motor_types" style="width:100px;border-left:1px solid var(--border);padding-left:12px">
          <div v-for="(cnt,mt) in stats.motor_types" :key="mt">{{ mt }} <b>{{ cnt }}</b></div>
        </div>
      </div>

      <!-- Toolbar -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <el-button size="small" @click="batchQrcode" :disabled="selectedIds.size===0">
          🔲 生成二维码 ({{ selectedIds.size }})
        </el-button>
        <el-button size="small" type="danger" @click="batchDelete" :disabled="selectedIds.size===0">
          🗑 批量删除 ({{ selectedIds.size }})
        </el-button>
        <el-button size="small" @click="exportExcel">📥 导出Excel</el-button>
        <el-button size="small" @click="openBatchDrawings">📎 批量上传图纸</el-button>
        <el-button size="small" @click="downloadTemplate">📥 下载模板</el-button>
        <el-button size="small" type="success" @click="addDemoProduct">🧪 添加示例</el-button>
        <el-button type="primary" size="small" @click="openEdit(null)" style="margin-left:auto">+ 新增产品</el-button>
        <span v-if="qrResults.length>0" style="font-size:12px;color:var(--text-secondary);margin-left:8px">
          已生成 {{ qrResults.length }} 个二维码
        </span>
      </div>

      <!-- QR Code Preview -->
      <div v-if="qrResults.length>0" class="card" style="margin-bottom:12px;padding:12px">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start">
          <div v-for="qr in qrResults" :key="qr.id" style="text-align:center;border:1px solid var(--border);border-radius:8px;padding:8px;min-width:100px">
            <img :src="qr.qr" style="width:80px;height:80px;display:block" />
            <span style="font-size:10px;color:var(--text-secondary);display:block;margin-top:4px;max-width:80px;overflow:hidden;text-overflow:ellipsis">{{ qr.label }}</span>
          </div>
        </div>
        <el-button size="small" style="margin-top:8px" @click="qrResults=[]">关闭</el-button>
      </div>

      <!-- Search & Filters -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <el-input v-model="search" placeholder="搜索型号/名称..." size="small" clearable style="width:200px" @input="applyFilters" @clear="applyFilters">
          <template #prepend>🔍</template>
        </el-input>
        <el-select v-model="filterMotorType" placeholder="电机种类" clearable size="small" style="width:160px" @change="applyFilters">
          <el-option v-for="opt in motorTypeOptions" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-select v-model="filterProductLine" placeholder="产品线" clearable size="small" style="width:130px" @change="applyFilters">
          <el-option v-for="opt in productLineOptions" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width:110px" @change="applyFilters">
          <el-option v-for="opt in statusOptions" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-button size="small" @click="expandAll">{{ allExpanded ? '📂 全部收起' : '📁 全部展开' }}</el-button>
        <el-button size="small" @click="showAdvFilter=!showAdvFilter">🔧 高级筛选</el-button>
        <span style="font-size:13px;color:var(--text-muted);line-height:32px;margin-left:4px">共 {{ filteredItems.length }} 款产品</span>
      </div>

      <!-- Advanced filter bar -->
      <div v-if="showAdvFilter" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;padding:8px;background:var(--bg);border-radius:6px">
        <el-input v-model="advRatedPower" placeholder="额定功率(如 60)" size="small" style="width:140px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-input v-model="advRatedVoltage" placeholder="额定电压(如 380)" size="small" style="width:140px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-input v-model="advRatedSpeed" placeholder="额定转速(如 3000)" size="small" style="width:150px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-input v-model="advPeakTorque" placeholder="峰值转矩(如 200)" size="small" style="width:150px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-input v-model="advInsulation" placeholder="绝缘等级" size="small" style="width:110px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-input v-model="advProtection" placeholder="防护等级" size="small" style="width:110px" clearable @input="applyFilters" @clear="applyFilters" />
        <el-button size="small" @click="advRatedPower='';advRatedVoltage='';advRatedSpeed='';advPeakTorque='';advInsulation='';advProtection='';applyFilters()">清除</el-button>
      </div>

      <!-- Product Table grouped by product_line — collapsible -->
      <div v-loading="loading">
        <template v-for="group in groupedItems" :key="group.line">
          <div v-if="group.items.length" class="card" style="margin-bottom:12px">
            <div class="card-header" style="background:var(--bg-hover);padding:8px 16px;border-radius:8px 8px 0 0;cursor:pointer;display:flex;align-items:center" @click="toggleGroup(group.line)">
              <span style="font-size:16px;width:20px;transition:transform 0.2s" :style="{transform: expandedGroups[group.line]||allExpanded?'rotate(90deg)':'rotate(0deg)'}">▶</span>
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--primary);margin:0 8px"></span>
              <span style="font-size:14px;font-weight:600">{{ group.line || '未分类' }}</span>
              <span style="font-weight:400;color:var(--text-muted);font-size:12px;margin-left:4px">({{ group.items.length }}款)</span>
              <span v-if="group.items.length>0" style="margin-left:auto;font-size:11px;color:var(--text-muted)">
                {{ [...new Set(group.items.map(i=>i.motor_type))].filter(Boolean).slice(0,3).join(' / ') }}
              </span>
            </div>
            <template v-if="allExpanded?expandedGroups[group.line]!==false:!!expandedGroups[group.line]">
            <el-table :data="group.items" size="small" stripe @selection-change="(rows) => onGroupSelect(rows, group.items)"
              style="border-radius:0 0 8px 8px">
              <el-table-column type="selection" width="40" />
              <el-table-column prop="product_code" label="产品编码">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">产品编码</span><el-input v-model="colFilters['product_code']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                <template #default="{row}">
                  <span v-if="row.product_code" style="color:var(--primary);cursor:pointer;font-weight:500" @click="$router.push('/product-tech/'+row.id)">{{ row.product_code }}</span>
                  <span v-else style="color:var(--text-muted)">-</span>
                </template>
              </el-table-column>
              <el-table-column v-if="group.line==='辅驱电机'" prop="product_drawing_no" label="产品图号" width="150">
                <template #default="{row}">
                  <span style="font-weight:600;color:var(--primary);cursor:pointer;text-decoration:underline" @click="$router.push('/product-tech/'+row.id)">{{ row.product_drawing_no || row.product_model || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column v-else prop="product_model" label="产品型号" width="150">
                <template #default="{row}">
                  <span style="font-weight:600;color:var(--primary);cursor:pointer;text-decoration:underline" @click="$router.push('/product-tech/'+row.id)">{{ row.product_model || row.name || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="电机种类" width="130">
                <template #header>
                  <div style="display:flex;flex-direction:column;gap:2px">
                    <span style="font-size:12px">电机种类</span>
                    <el-input v-model="colFilters['motor_type']" size="small" placeholder="筛选..." clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" />
                  </div>
                </template>
                <template #default="{row}">
                  <span :class="'tag tag-' + motorTypeColor(row.motor_type)" style="font-size:11px">{{ row.motor_type || '-' }}</span>
                </template>
              </el-table-column>
              <!-- Product-line-specific columns -->
              <template v-if="group.line==='主驱电机'">
                <el-table-column prop="rated_power" label="额定功率(kW)" width="100" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定功率</span><el-input v-model="colFilters['rated_power']" size="small" placeholder="kW" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_power || '-' }}</span></template>
                </el-table-column>
                <el-table-column prop="rated_voltage" label="额定电压(V)" width="100" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定电压</span><el-input v-model="colFilters['rated_voltage']" size="small" placeholder="V" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_voltage || '-' }}</span></template>
                </el-table-column>
                <el-table-column prop="rated_speed" label="额定转速(rpm)" width="105" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定转速</span><el-input v-model="colFilters['rated_speed']" size="small" placeholder="rpm" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_speed || '-' }}</span></template>
                </el-table-column>
                <el-table-column prop="em_design_no" label="电磁方案编号">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">电磁方案编号</span><el-input v-model="colFilters['em_design_no']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.em_design_no || '-' }}</span></template></el-table-column>
                <el-table-column prop="back_emf_coef" label="反电势系数">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">反电势系数</span><el-input v-model="colFilters['back_emf_coef']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.back_emf_coef || '-' }}</span></template></el-table-column>
                <el-table-column prop="peak_torque" label="峰值转矩(Nm)" width="110" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">峰值转矩</span><el-input v-model="colFilters['peak_torque']" size="small" placeholder="Nm" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.peak_torque || '-' }}</span></template></el-table-column>
                <el-table-column prop="peak_torque_current" label="峰值转矩电流(A)" width="120" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">转矩电流</span><el-input v-model="colFilters['peak_torque_current']" size="small" placeholder="A" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.peak_torque_current || '-' }}</span></template></el-table-column>
                <el-table-column prop="peak_torque_speed" label="峰值转矩转速(rpm)" width="130" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">转矩转速</span><el-input v-model="colFilters['peak_torque_speed']" size="small" placeholder="rpm" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.peak_torque_speed || '-' }}</span></template></el-table-column>
                <el-table-column prop="stack_height" label="叠高(mm)" width="95" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">叠高</span><el-input v-model="colFilters['stack_height']" size="small" placeholder="mm" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.stack_height || '-' }}</span></template></el-table-column>
                <el-table-column prop="winding" label="绕组">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">绕组</span><el-input v-model="colFilters['winding']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.winding || '-' }}</span></template></el-table-column>
                <el-table-column prop="insulation_class" label="绝缘等级">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">绝缘等级</span><el-input v-model="colFilters['insulation_class']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.insulation_class || '-' }}</span></template></el-table-column>
                <el-table-column prop="protection_level" label="防护等级">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">防护等级</span><el-input v-model="colFilters['protection_level']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.protection_level || '-' }}</span></template></el-table-column>
              </template>
              <template v-else-if="group.line==='辅驱电机'">
                <el-table-column prop="rated_power" label="额定功率" width="95" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定功率</span><el-input v-model="colFilters['rated_power']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_power || '-' }}</span></template></el-table-column>
                <el-table-column prop="rated_speed" label="额定转速" width="95" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定转速</span><el-input v-model="colFilters['rated_speed']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_speed || '-' }}</span></template></el-table-column>
                <el-table-column prop="rated_voltage" label="额定电压" width="95" show-overflow-tooltip>
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定电压</span><el-input v-model="colFilters['rated_voltage']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_voltage || '-' }}</span></template></el-table-column>
                <el-table-column prop="rear_cover" label="后端盖">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">后端盖</span><el-input v-model="colFilters['rear_cover']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.rear_cover || '-' }}</span></template></el-table-column>
                <el-table-column prop="temp_wire" label="温度线">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">温度线</span><el-input v-model="colFilters['temp_wire']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.temp_wire || '-' }}</span></template></el-table-column>
                <el-table-column prop="ground_wire" label="接地线">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">接地线</span><el-input v-model="colFilters['ground_wire']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.ground_wire || '-' }}</span></template></el-table-column>
                <el-table-column prop="shaft_dia" label="轴伸直径">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">轴伸直径</span><el-input v-model="colFilters['shaft_dia']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.shaft_dia || '-' }}</span></template></el-table-column>
                <el-table-column prop="front_cover_spigot" label="前端盖止口">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">前端盖止口</span><el-input v-model="colFilters['front_cover_spigot']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.front_cover_spigot || '-' }}</span></template></el-table-column>
                <el-table-column prop="mounting_hole" label="安装孔">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">安装孔</span><el-input v-model="colFilters['mounting_hole']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.mounting_hole || '-' }}</span></template></el-table-column>
                <el-table-column prop="shaft_rotation" label="轴伸转向">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">轴伸转向</span><el-input v-model="colFilters['shaft_rotation']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.shaft_rotation || '-' }}</span></template></el-table-column>
                <el-table-column prop="harness_bracket" label="线束固定架">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">线束固定架</span><el-input v-model="colFilters['harness_bracket']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.harness_bracket || '-' }}</span></template></el-table-column>
              </template>
              <template v-else>
                <el-table-column prop="rated_power" label="额定功率" width="100">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定功率</span><el-input v-model="colFilters['rated_power']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_power || '-' }}</span></template></el-table-column>
                <el-table-column prop="rated_voltage" label="额定电压" width="100">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定电压</span><el-input v-model="colFilters['rated_voltage']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_voltage || '-' }}</span></template></el-table-column>
                <el-table-column prop="rated_speed" label="额定转速" width="100">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">额定转速</span><el-input v-model="colFilters['rated_speed']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                  <template #default="{row}"><span>{{ row.rated_speed || '-' }}</span></template></el-table-column>
                <el-table-column prop="cooling_method" label="冷却方式">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">冷却方式</span><el-input v-model="colFilters['cooling_method']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template><template #default="{row}"><span>{{ row.cooling_method || '-' }}</span></template></el-table-column>
              </template>
              <el-table-column label="状态" width="75">
                <template #default="{row}">
                  <span :class="'tag tag-' + statusColor(row.status)" style="font-size:11px">{{ row.status || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{row}">
                  <el-button link size="small" @click="openEdit(row)">编辑</el-button>
                  <el-button link size="small" @click="openFilesDialog(row)" v-if="getFileCount(row.id)>0">📎{{ getFileCount(row.id) }}</el-button>
                  <el-button link size="small" @click="openFilesDialog(row)" v-else>+附件</el-button>
                  <el-popconfirm title="确认删除?" @confirm="delItem(row.id)"><template #reference><el-button link size="small" type="danger">删除</el-button></template></el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
            </template>
          </div>
        </template>
        <div v-if="totalCount===0 && !loading" style="text-align:center;padding:40px;color:var(--text-muted)">暂无产品数据，点击右上角 "+ 新增产品" 添加</div>
      </div>

      <div style="position:fixed;bottom:32px;right:32px;z-index:100">
        <el-button type="primary" circle size="large" @click="openEdit(null)" style="width:48px;height:48px;font-size:24px">+</el-button>
      </div>
    </template>

    <!-- ═══════════ Control Specialty: same layout as Motor ═══════════ -->
    <template v-if="activeSpecialty === '电机控制专业'">
      <!-- Stats -->
      <div style="display:flex;gap:16px;margin-bottom:16px">
        <div class="stat-card" style="flex:1"><div class="stat-num">{{ stats?.total || filteredItems.length }}</div><div class="stat-label">产品总数</div></div>
        <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#22c55e">{{ stats?.on_sale || 0 }}</div><div class="stat-label">在售</div></div>
        <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#e6a23c">{{ stats?.in_dev || 0 }}</div><div class="stat-label">研发中</div></div>
        <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#909399">{{ stats?.pre_research || 0 }}</div><div class="stat-label">预研</div></div>
      </div>
      <!-- Toolbar -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <el-button size="small" @click="batchDelete" :disabled="selectedIds.size===0">🗑 批量删除 ({{ selectedIds.size }})</el-button>
        <el-button size="small" @click="exportExcel">📥 导出Excel</el-button>
        <el-button size="small" @click="openBatchDrawings">📎 批量上传图纸</el-button>
        <el-button size="small" @click="downloadTemplate">📥 下载模板</el-button>
        <el-button type="primary" size="small" @click="openEdit(null)" style="margin-left:auto">+ 新增产品</el-button>
      </div>
      <!-- Search & Filters -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <el-input v-model="search" placeholder="搜索型号/名称..." size="small" clearable style="width:200px" @input="applyFilters" @clear="applyFilters"><template #prepend>🔍</template></el-input>
        <el-select v-model="filterMotorType" placeholder="控制器类型" clearable size="small" style="width:140px" @change="applyFilters">
          <el-option v-for="opt in (activeEnums?.controller_type||[])" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-select v-model="filterProductLine" placeholder="产品线" clearable size="small" style="width:140px" @change="applyFilters">
          <el-option v-for="opt in (activeEnums?.product_line||productLineOptions)" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width:110px" @change="applyFilters">
          <el-option v-for="opt in (activeEnums?.status||statusOptions)" :key="opt" :label="opt" :value="opt" />
        </el-select>
        <el-button size="small" @click="expandAll">{{ allExpanded ? '📂 全部收起' : '📁 全部展开' }}</el-button>
        <span style="font-size:13px;color:var(--text-muted);line-height:32px">共 {{ filteredItems.length }} 款</span>
      </div>
      <!-- Collapsible product line groups -->
      <div v-loading="loading">
        <template v-for="group in groupedItems" :key="group.line">
          <div v-if="group.items.length" class="card" style="margin-bottom:12px">
            <div class="card-header" style="background:var(--bg-hover);padding:8px 16px;border-radius:8px 8px 0 0;cursor:pointer;display:flex;align-items:center" @click="toggleGroup(group.line)">
              <span style="font-size:16px;width:20px;transition:transform 0.2s" :style="{transform: expandedGroups[group.line]||allExpanded?'rotate(90deg)':'rotate(0deg)'}">▶</span>
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--primary);margin:0 8px"></span>
              <span style="font-size:14px;font-weight:600">{{ group.line || '未分类' }}</span>
              <span style="font-weight:400;color:var(--text-muted);font-size:12px;margin-left:4px">({{ group.items.length }}款)</span>
            </div>
            <template v-if="allExpanded?expandedGroups[group.line]!==false:!!expandedGroups[group.line]">
            <el-table :data="group.items" size="small" stripe @selection-change="(rows) => onGroupSelect(rows, group.items)" style="border-radius:0 0 8px 8px">
              <el-table-column type="selection" width="40" />
              <el-table-column prop="product_model" label="产品型号">
                  <template #header><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px">产品型号</span><el-input v-model="colFilters['product_model']" size="small" placeholder="筛选" clearable style="width:100%;font-size:11px" @input="applyColFilters" @clear="applyColFilters" /></div></template>
                <template #default="{row}"><span style="font-weight:600;color:var(--primary);cursor:pointer;text-decoration:underline" @click="$router.push('/product-tech/'+row.id)">{{ row.product_model || row.name || '-' }}</span></template>
              </el-table-column>
              <template v-for="col in currentFields.filter(f => !['product_model','product_code','name','standard','supplier','notes','product_line'].includes(f.key))" :key="col.key">
                <el-table-column :prop="col.key" :label="col.label" :width="100" show-overflow-tooltip>
                  <template #default="{row}"><span>{{ row[col.key] || '-' }}</span></template>
                </el-table-column>
              </template>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{row}">
                  <el-button link size="small" @click="openEdit(row)">编辑</el-button>
                  <el-popconfirm title="确认删除?" @confirm="delItem(row.id)"><template #reference><el-button link size="small" type="danger">删除</el-button></template></el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
            </template>
          </div>
        </template>
        <div v-if="totalCount===0 && !loading" style="text-align:center;padding:40px;color:var(--text-muted)">暂无产品数据，点击右上角 "+ 新增产品" 添加</div>
      </div>
    </template>

    <!-- ═══════════ Edit Dialog ═══════════ -->
    <el-dialog v-model="showDialog" :title="editing ? '编辑产品' : '新增产品'" width="650px" top="20px">
      <el-form :model="form" label-width="100px" size="small">
        <el-form-item label="专业" required>
          <el-select v-model="form.specialty" style="width:100%" @change="onSpecialtyChange">
            <el-option v-for="s in specialties" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="form.product_line==='辅驱电机'?'产品图号':'产品型号'" required>
          <el-input v-model="form[form.product_line==='辅驱电机'?'product_drawing_no':'product_model']" :placeholder="form.product_line==='辅驱电机'?'如 YPS-E50-A00':'如 YPS-E50-T01'" />
        </el-form-item>
        <el-form-item label="导入数据">
          <input type="file" ref="singleImportInput" @change="onParseFile" style="display:none" />
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <el-button size="small" @click="$refs.singleImportInput.click()" :disabled="importingSingle">
              📄 {{ importingSingle ? '解析中...' : '从文件导入' }}
            </el-button>
            <el-select v-model="manualEncoding" size="small" style="width:110px" placeholder="自动检测">
              <el-option label="自动检测" value="" />
              <el-option label="GBK (简体)" value="gbk" />
              <el-option label="GB2312" value="gb2312" />
              <el-option label="GB18030" value="gb18030" />
              <el-option label="UTF-8" value="utf-8" />
              <el-option label="UTF-8 BOM" value="utf-8-sig" />
              <el-option label="UTF-16" value="utf-16" />
            </el-select>
          </div>
          <div style="margin-top:4px">
            <el-button link size="small" @click="showPasteImport=true">📋 或从Excel直接粘贴数据</el-button>
          </div>
        </el-form-item>
        <!-- 辅驱电机: custom fields -->
        <template v-if="form.product_line==='辅驱电机'">
          <template v-for="col in currentFormFields" :key="col.key">
            <el-form-item v-if="col.key!=='notes'&&col.key!=='standard'&&col.key!=='supplier'&&col.key!=='product_code'&&col.key!=='product_model'&&col.key!=='product_drawing_no'&&col.key!=='status'" :label="col.label">
              <el-select v-if="getEnumOptions(col.key).length > 0" v-model="form[col.key]" style="width:100%" clearable :placeholder="'选择'+col.label">
                <el-option v-for="opt in getEnumOptions(col.key)" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <el-input v-else v-model="form[col.key]" :placeholder="'请输入'+col.label" />
            </el-form-item>
          </template>
          <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
        </template>
        <!-- 非辅驱: standard form -->
        <template v-else>
          <template v-for="col in currentFormFields" :key="col.key">
            <el-form-item v-if="col.key!=='notes'&&col.key!=='standard'&&col.key!=='supplier'&&col.key!=='product_code'&&col.key!=='product_model'&&col.key!=='product_drawing_no'" :label="col.label">
              <el-select v-if="getEnumOptions(col.key).length > 0" v-model="form[col.key]" style="width:100%" clearable :placeholder="'选择'+col.label">
                <el-option v-for="opt in getEnumOptions(col.key)" :key="opt" :label="opt" :value="opt" />
              </el-select>
              <el-input v-else v-model="form[col.key]" :placeholder="'请输入'+col.label" />
            </el-form-item>
          </template>
          <el-form-item label="参考标准"><el-input v-model="form.standard" /></el-form-item>
          <el-form-item label="供应商"><el-input v-model="form.supplier" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
        </template>
        <el-divider content-position="left" style="margin:8px 0 12px"><span style="font-size:12px;color:var(--text-muted)">📎 图纸 / 相关文件</span></el-divider>
        <el-form-item label="已上传" v-if="editFiles.length > 0">
          <div style="width:100%;max-height:150px;overflow-y:auto">
            <div v-for="f in editFiles" :key="f.id" style="display:flex;align-items:center;padding:4px 8px;margin-bottom:4px;border:1px solid var(--border);border-radius:6px;font-size:12px;gap:6px">
              <img v-if="isImageFile(f.filename)" :src="previewUrl(editing.id, f.id)" style="width:36px;height:36px;object-fit:cover;border-radius:3px;flex-shrink:0;cursor:pointer" @click="openPreview(editing.id, f.id)" @error="$event.target.style.display='none'" />
              <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ f.filename }}</span>
              <span style="color:var(--text-muted);font-size:11px;white-space:nowrap">{{ formatFileSize(f.size) }}</span>
              <el-button link size="small" type="primary" @click="openPreview(editing.id, f.id)">预览</el-button>
              <el-button link size="small" @click="downloadFile(editing.id, f.id, f.filename)">下载</el-button>
              <el-button link size="small" type="danger" @click="deleteFile(editing.id, f.id)">删除</el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="添加文件">
          <input type="file" ref="editFileInput" multiple @change="onEditFileChange" style="display:block" />
          <span style="font-size:11px;color:var(--text-muted)">支持任何格式：图纸/PDF/Word/Excel/图片/压缩包等</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog=false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Paste Import Dialog -->
    <el-dialog v-model="showPasteImport" title="📋 粘贴导入" width="780px" top="20px">
      <div style="margin-bottom:6px;font-size:12px;color:var(--text-secondary)">
        从 Excel 复制数据区域（<b>不含表头</b>），Ctrl+V 粘贴，选择产品线后解析。列顺序需与下载模板一致。
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
        <span style="font-size:12px;white-space:nowrap">产品线：</span>
        <el-select v-model="pasteProductLine" size="small" style="width:130px" @change="onPasteProductLineChange">
          <el-option v-for="pl in productLineOptions" :key="pl" :label="pl" :value="pl" />
        </el-select>
        <span style="font-size:12px;margin-left:8px;white-space:nowrap">分隔符：</span>
        <el-radio-group v-model="pasteDelim" size="small">
          <el-radio value="auto">自动</el-radio>
          <el-radio value="tab">Tab</el-radio>
          <el-radio value="comma">逗号</el-radio>
        </el-radio-group>
        <el-button size="small" type="primary" @click="doPasteImport" :loading="pasteLoading" style="margin-left:auto">解析数据</el-button>
      </div>
      <el-input v-model="pasteText" type="textarea" :rows="4" placeholder="在此粘贴数据（不含表头）..." style="font-size:12px;font-family:monospace" />
      <div v-if="pasteError" style="margin-top:8px;padding:8px 12px;background:#fef0f0;border:1px solid #fde2e2;border-radius:4px;color:#f56c6c;font-size:12px;white-space:pre-wrap">{{ pasteError }}</div>
      <div v-if="pasteResults.length>0" style="margin-top:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:4px">
          <span style="font-size:12px;color:var(--text-secondary)">识别到 <b>{{ pasteResults.length }}</b> 条 · 模板: {{ pasteProductLine }}</span>
          <div style="display:flex;gap:4px;flex-wrap:wrap">
            <el-button size="small" @click="pasteSelectAll">全选</el-button>
            <el-button size="small" @click="pasteSelectNone">取消</el-button>
            <el-button size="small" type="danger" @click="pasteDeleteSelected" :disabled="pasteSelectedCount===0">删除({{ pasteSelectedCount }})</el-button>
            <el-button size="small" type="primary" @click="pasteImportSelected" :disabled="pasteSelectedCount===0">导入选中({{ pasteSelectedCount }})</el-button>
            <el-button size="small" type="primary" @click="pasteImportAll">全部导入</el-button>
          </div>
        </div>
        <div style="max-height:380px;overflow-y:auto;border:1px solid var(--border);border-radius:6px">
          <div v-for="(rec, idx) in pasteResults" :key="idx"
            style="display:flex;align-items:center;padding:5px 10px;border-bottom:1px solid var(--border);font-size:12px;"
            :style="{background: rec._selected ? '#ecf5ff' : 'transparent'}">
            <el-checkbox v-model="rec._selected" style="margin-right:8px;height:auto" />
            <span style="font-weight:600;min-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ rec.product_code || rec.product_drawing_no || rec.product_model || '(无)' }}</span>
            <span v-if="rec.product_drawing_no && rec.product_code" style="margin-left:6px;font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px">{{ rec.product_drawing_no }}</span>
            <span v-if="rec.motor_type" style="margin-left:6px;font-size:11px;color:var(--text-muted)">{{ rec.motor_type }}</span>
            <span style="margin-left:6px;font-size:11px;color:var(--text-secondary)">{{ rec.product_line }}</span>
            <span v-if="rec.rated_power" style="margin-left:6px;font-size:11px;color:var(--text-muted)">{{ rec.rated_power }}kW</span>
            <span v-if="rec.rated_speed" style="margin-left:4px;font-size:11px;color:var(--text-muted)">{{ rec.rated_speed }}rpm</span>
            <el-button link size="small" type="danger" @click="pasteResults.splice(idx,1)" style="margin-left:auto;font-size:11px">✕</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="closePasteDialog">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Parse Results Dialog -->
    <el-dialog v-model="showParseDlg" title="文件解析结果" width="750px" top="20px">
      <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:13px;color:var(--text-secondary)">
          识别到 <b>{{ parseRecords.length }}</b> 条，编码：<b>{{ parseEncoding }}</b>，匹配列：{{ parseHeaders.join(', ') }}
          <span v-if="parseSample" style="display:block;margin-top:2px;font-size:11px">示例：{{ parseSample }}</span>
          <span v-if="parseRawHeaders.length" style="display:block;margin-top:2px;font-size:11px;color:var(--text-muted)">原始表头：{{ parseRawHeaders.join(' | ') }}</span>
        </span>
        <el-button type="primary" size="small" @click="importAllParsed" :loading="importingAll">
          全部导入 ({{ parseRecords.length }}条)
        </el-button>
      </div>
      <div style="max-height:420px;overflow-y:auto">
        <div v-for="(rec, idx) in parseRecords" :key="idx"
          style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;margin-bottom:4px;border:1px solid var(--border);border-radius:6px;font-size:13px;
            ">
          <div style="flex:1;min-width:0">
            <span style="font-weight:600">{{ rec.product_model || rec.name || '(无型号)' }}</span>
            <span v-if="rec.motor_type" style="margin-left:8px;font-size:11px" :class="'tag tag-'+motorTypeColor(rec.motor_type)">{{ rec.motor_type }}</span>
            <span v-if="rec.product_line" style="margin-left:4px;font-size:11px;color:var(--text-secondary)">{{ rec.product_line }}</span>
            <span v-if="rec.status" style="margin-left:4px;font-size:11px" :class="'tag tag-'+statusColor(rec.status)">{{ rec.status }}</span>
            <span v-if="rec.rated_power" style="margin-left:8px;font-size:11px;color:var(--text-muted)">{{ rec.rated_power }}</span>
            <span v-if="rec.rated_voltage" style="margin-left:4px;font-size:11px;color:var(--text-muted)">{{ rec.rated_voltage }}</span>
          </div>
          <el-button link size="small" type="primary" @click="fillForm(rec)">填入表单</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="showParseDlg=false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Files Dialog -->
    <el-dialog v-model="showFilesDlg" :title="'文件管理 - ' + selectedProductName" width="650px" top="30px">
      <div v-if="selectedFiles.length===0" style="color:var(--text-muted);text-align:center;padding:20px">暂未上传文件</div>
      <div v-for="f in selectedFiles" :key="f.id" style="display:flex;align-items:center;padding:8px 12px;margin-bottom:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;gap:10px">
        <!-- Image thumbnail -->
        <img v-if="isImageFile(f.filename)" :src="previewUrl(selectedProductId, f.id)" style="width:48px;height:48px;object-fit:cover;border-radius:4px;border:1px solid var(--border);cursor:pointer;flex-shrink:0"
          @click="openPreview(selectedProductId, f.id)" @error="$event.target.style.display='none'" />
        <span v-else style="width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:var(--bg-hover);border-radius:4px;flex-shrink:0;font-size:20px">
          {{ fileIcon(f.filename) }}
        </span>
        <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px">{{ f.filename }}</span>
        <span style="color:var(--text-muted);font-size:11px;white-space:nowrap">{{ formatFileSize(f.size) }}</span>
        <el-button link size="small" type="primary" @click="openPreview(selectedProductId, f.id)">预览</el-button>
        <el-button link size="small" @click="downloadFile(selectedProductId, f.id, f.filename)">下载</el-button>
        <el-button link size="small" type="danger" @click="deleteFileFromDialog(f.id)">删除</el-button>
      </div>
      <div style="margin-top:12px">
        <input type="file" ref="quickFileInput" multiple @change="onQuickFileChange" style="display:block" />
        <span style="font-size:11px;color:var(--text-muted)">选择文件直接上传到该产品</span>
      </div>
      <template #footer><el-button @click="showFilesDlg=false">关闭</el-button></template>
    </el-dialog>

    <!-- Batch Drawing Upload Dialog -->
    <el-dialog v-model="showDrawingsDlg" title="批量上传图纸" width="500px">
      <div style="font-size:13px;margin-bottom:12px;color:var(--text-secondary)">
        文件通过文件名自动匹配产品型号。请确保文件名包含产品型号。
      </div>
      <input type="file" ref="drawingInput" multiple @change="onDrawingChange" style="display:block;margin-bottom:8px" />
      <div v-if="drawingFiles.length>0" style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
        已选 {{ drawingFiles.length }} 个文件
      </div>
      <div v-if="drawingResults.length>0" style="max-height:200px;overflow-y:auto;font-size:12px">
        <div v-for="r in drawingResults" :key="r.filename" :style="{color:r.ok?'#22c55e':'#ef4444',marginTop:'2px'}">
          {{ r.ok ? '✓' : '✗' }} {{ r.filename }} {{ r.msg ? '('+r.msg+')' : '' }}
        </div>
      </div>
      <template #footer>
        <el-button @click="showDrawingsDlg=false">取消</el-button>
        <el-button type="primary" @click="doBatchDrawings" :loading="drawingLoading" :disabled="drawingFiles.length===0">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const specialties = ref([])
const activeSpecialty = ref('电机专业')
const items = ref([])
const filteredItems = ref([])
const expandedGroups = reactive({})  // { groupLine: true/false } - reactive object for Vue tracking
const allExpanded = ref(true)
const loading = ref(false)
const search = ref('')
const filterMotorType = ref('')
const filterProductLine = ref('')
const filterStatus = ref('')
const showAdvFilter = ref(false)
const advRatedPower = ref('')
const advRatedVoltage = ref('')
const advRatedSpeed = ref('')
const advPeakTorque = ref('')
const advInsulation = ref('')
const advProtection = ref('')
const colFilters = reactive({}) // generic column filters: { propName: filterValue }
const stats = ref({ total: 0, on_sale: 0, in_dev: 0, pre_research: 0 })
const totalCount = computed(() => filteredItems.value.length)

// Multi-select for QR code
const selectedIds = ref(new Set())
const qrResults = ref([])

// Edit dialog
const showDialog = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = ref({})
const editFiles = ref([])
const editFileInput = ref(null)
const editPendingFiles = ref([])
const thumbnailCache = ref({})

// Files dialog
const showFilesDlg = ref(false)
const selectedProductId = ref(null)
const selectedProductName = ref('')
const selectedFiles = ref([])
const quickFileInput = ref(null)

// Batch drawings
const showDrawingsDlg = ref(false)
const drawingInput = ref(null)
const drawingFiles = ref([])
const drawingResults = ref([])
const drawingLoading = ref(false)

// Single file import for form auto-fill
const singleImportInput = ref(null)
const importingSingle = ref(false)
const manualEncoding = ref('')

// Parse results
const showParseDlg = ref(false)
const parseRecords = ref([])
const parseHeaders = ref([])
const parseEncoding = ref('')
const parseSample = ref('')
const parseRawHeaders = ref([])
const importingAll = ref(false)

// Paste import (no-header mode, template-column-order mapping)
const showPasteImport = ref(false)
const pasteText = ref('')
const pasteDelim = ref('auto')
const pasteResults = ref([])
const pasteLoading = ref(false)
const pasteError = ref('')
const pasteDebug = ref('')
const pasteProductLine = ref('辅驱电机')

// Attachments cache
const attachmentsCache = ref({})

const currentFields = computed(() => {
  const spec = specialties.value.find(s => s.value === activeSpecialty.value)
  return spec?.fields || []
})
const currentFormFields = computed(() => {
  const spec = specialties.value.find(s => s.value === form.value.specialty)
  if (!spec) return []
  const pl = form.value.product_line
  if (spec.product_line_fields && pl && spec.product_line_fields[pl]) {
    let common = spec.fields || []
    // 辅驱电机: exclude 状态/标准/供应商/产品型号, keep 产品图号
    if (pl === '辅驱电机') {
      common = common.filter(f => !['status','standard','supplier','product_model'].includes(f.key))
      common = common.map(f => f.key === 'product_drawing_no' ? {key:'product_drawing_no',label:'产品图号'} : f)
    }
    return [...common, ...spec.product_line_fields[pl]]
  }
  return spec.fields || []
})
const currentEnums = computed(() => {
  const spec = specialties.value.find(s => s.value === form.value.specialty)
  return spec?.enums || {}
})
const activeEnums = computed(() => {
  const spec = specialties.value.find(s => s.value === activeSpecialty.value)
  return spec?.enums || {}
})
const motorTypeOptions = computed(() => activeEnums.value.motor_type || [])
const productLineOptions = computed(() => activeEnums.value.product_line || [])
const statusOptions = computed(() => activeEnums.value.status || [])

// Grouped items by product_line
const groupedItems = computed(() => {
  const lines = productLineOptions.value.length ? productLineOptions.value : []
  const seen = new Set(lines)
  // Collect any product_lines not in the enum
  for (const item of filteredItems.value) {
    const pl = item.product_line || ''
    if (pl && !seen.has(pl)) { seen.add(pl); lines.push(pl) }
  }
  return lines.map(line => ({
    line,
    items: filteredItems.value.filter(x => (x.product_line || '') === line),
  }))
})

function getEnumOptions(fieldKey) { return currentEnums.value[fieldKey] || [] }
function showFormField(key) {
  // Always hide: notes, standard, supplier (hardcoded at bottom)
  if (['notes','standard','supplier'].includes(key)) return false
  // Hide product_code, product_model, product_drawing_no (hardcoded at top)
  if (['product_code','product_model','product_drawing_no'].includes(key)) return false
  // For 辅驱电机: hide status
  if (form.value.product_line === '辅驱电机' && key === 'status') return false
  return true
}
function getFileCount(itemId) { return (attachmentsCache.value[itemId] || []).length }

function motorTypeColor(type) {
  if (!type) return 'gray'
  if (type.includes('永磁')) return 'blue'
  if (type.includes('异步')) return 'orange'
  if (type.includes('直流无刷')||type.includes('BLDC')) return 'green'
  if (type.includes('开关磁阻')||type.includes('SRM')) return 'purple'
  if (type.includes('同步磁阻')||type.includes('SynRM')) return 'teal'
  return 'gray'
}
function statusColor(status) {
  if (!status) return 'gray'
  if (status === '在售') return 'green'
  if (status === '研发中') return 'orange'
  if (status === '预研') return 'purple'
  return 'gray'
}

async function loadSpecs() {
  try { const r = await api.get('/product-tech/specialties'); specialties.value = r.data || [] }
  catch { specialties.value = [] }
}

async function load() {
  search.value = ''; filterMotorType.value = ''; filterProductLine.value = ''; filterStatus.value = ''
  selectedIds.value = new Set(); qrResults.value = []
  loading.value = true
  try {
    const params = { specialty: activeSpecialty.value }
    const r = await api.get('/product-tech', { params })
    items.value = r.data || []
    filteredItems.value = [...items.value]
    loadStats()  // async but don't block
  } catch { items.value = []; filteredItems.value = [] }
  loading.value = false
}

// Debounced column filter — client-side only, no API call
let _colFilterTimer = null
function applyColFilters() {
  clearTimeout(_colFilterTimer)
  _colFilterTimer = setTimeout(() => {
    let result = [...items.value]
    const numMatch = (val, query) => {
      if (!query) return true
      return String(val || '').toLowerCase().includes(query.toLowerCase())
    }
    for (const [key, val] of Object.entries(colFilters)) {
      if (val) result = result.filter(x => numMatch(x[key], val))
    }
    // Also apply advanced filters
    if (advRatedPower.value) result = result.filter(x => numMatch(x.rated_power, advRatedPower.value))
    if (advRatedVoltage.value) result = result.filter(x => numMatch(x.rated_voltage, advRatedVoltage.value))
    if (advRatedSpeed.value) result = result.filter(x => numMatch(x.rated_speed, advRatedSpeed.value))
    if (advPeakTorque.value) result = result.filter(x => numMatch(x.peak_torque, advPeakTorque.value))
    if (advInsulation.value) result = result.filter(x => (x.insulation_class||'').includes(advInsulation.value))
    if (advProtection.value) result = result.filter(x => (x.protection_level||'').includes(advProtection.value))
    filteredItems.value = result
  }, 250)
}

function toggleGroup(line) {
  expandedGroups[line] = !expandedGroups[line]
}
function expandAll() {
  allExpanded.value = !allExpanded.value
  if (allExpanded.value) Object.keys(expandedGroups).forEach(k => delete expandedGroups[k])
}

async function applyFilters() {
  loading.value = true
  try {
    const params = { specialty: activeSpecialty.value }
    if (search.value) params.search = search.value
    if (filterMotorType.value) {
      if (activeSpecialty.value === '电机控制专业') params.controller_type = filterMotorType.value
      else params.motor_type = filterMotorType.value
    }
    if (filterProductLine.value) params.product_line = filterProductLine.value
    if (filterStatus.value) params.status = filterStatus.value
    const r = await api.get('/product-tech', { params })
    items.value = r.data || []

    // Apply any active column/advanced filters to the new data
    applyColFilters()
  } catch { items.value = []; filteredItems.value = [] }
  loading.value = false
}

async function loadStats() {
  try { const r = await api.get('/product-tech/stats', { params: { specialty: activeSpecialty.value } }); stats.value = r.data || {} }
  catch { stats.value = { total: 0, on_sale: 0, in_dev: 0, pre_research: 0 } }
}

async function loadAllAttachmentCounts() {
  for (const item of items.value) {
    try { const r = await api.get(`/product-tech/${item.id}/files`); attachmentsCache.value[item.id] = r.data || [] }
    catch { attachmentsCache.value[item.id] = [] }
  }
}

function onTabChange() { load() }

function onGroupSelect(rows, groupItems) {
  for (const row of rows) selectedIds.value.add(row.id)
  for (const item of groupItems) {
    if (!rows.find(r => r.id === item.id)) selectedIds.value.delete(item.id)
  }
}

// ── Toolbar actions ──

async function batchDelete() {
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.size} 个产品？此操作不可恢复。`, '批量删除', { type: 'warning', confirmButtonText: '确认删除' })
    await api.post('/product-tech/batch-delete', { ids: [...selectedIds.value] })
    ElMessage.success(`已删除${selectedIds.value.size}个产品`)
    selectedIds.value = new Set()
    await load()
  } catch {}
}

async function batchQrcode() {
  if (selectedIds.value.size === 0) { ElMessage.warning('请先勾选产品'); return }
  try {
    const res = await api.post('/product-tech/qrcode', { ids: [...selectedIds.value] })
    qrResults.value = res.data?.results || []
    ElMessage.success(`已生成${qrResults.value.length}个二维码`)
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '生成失败') }
}

async function exportExcel() {
  try {
    // Gather all data (respect current filters)
    const data = filteredItems.value
    if (!data.length) { ElMessage.warning('无数据可导出'); return }
    const headers = currentFields.value.map(f => f.label)
    const keys = currentFields.value.map(f => f.key)
    let csv = '﻿' + headers.join(',') + '\n'
    for (const item of data) {
      csv += keys.map(k => {
        const v = (item[k] || '').toString()
        return v.includes(',') || v.includes('"') || v.includes('\n') ? `"${v.replace(/"/g,'""')}"` : v
      }).join(',') + '\n'
    }
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `产品技术库_${activeSpecialty.value}.csv`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出${data.length}条`)
  } catch (e) { ElMessage.error('导出失败') }
}

function openBatchDrawings() { drawingFiles.value = []; drawingResults.value = []; showDrawingsDlg.value = true }

async function downloadTemplate() {
  try {
    const params = { specialty: activeSpecialty.value }
    if (activeSpecialty.value === '电机专业') {
      params.product_line = filterProductLine.value || productLineOptions.value[0] || '主驱电机'
    }
    const res = await api.get('/product-tech/template', { params, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a'); a.href = url
    a.download = `产品技术库_${activeSpecialty.value}_导入模板.xlsx`
    a.click(); URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('下载失败: ' + (e?.response?.data?.detail || e?.message || '')) }
}

async function addDemoProduct() {
  try {
    const demo = {
      specialty: activeSpecialty.value,
      product_code: 'DEMO-001',
      product_model: '测试电机-T01',
      motor_type: '永磁同步电机(PMSM)',
      product_line: '主驱电机',
      status: '研发中',
      rated_power: '200',
      rated_voltage: '380',
      rated_speed: '3000',
      em_design_no: 'EM-DEMO-001',
      back_emf_coef: '45',
      peak_torque: '640',
      peak_torque_current: '350',
      peak_torque_speed: '2000',
      stack_height: '120',
      winding: '4-0.8*15',
      sensor_type: '旋变',
      spline_spec: 'DIN5480',
      mounting_spigot_dia: '180',
      mounting_method: '法兰安装',
      rear_cover_fixing: '螺栓固定',
      brake: '无',
      standard: 'GB/T 18488',
      supplier: '测试供应商',
      notes: '这是一条测试数据，验证中文存储正常',
    }
    await api.post('/product-tech', demo)
    ElMessage.success('示例产品已添加，请查看列表')
    await load()
  } catch (e) { ElMessage.error('添加失败') }
}
function onDrawingChange() { drawingFiles.value = Array.from(drawingInput.value?.files || []) }

async function doBatchDrawings() {
  if (!drawingFiles.value.length) return
  drawingLoading.value = true; drawingResults.value = []
  try {
    const fd = new FormData()
    for (const f of drawingFiles.value) fd.append('files', f)
    const res = await api.post('/product-tech/batch-upload-drawings', fd)
    drawingResults.value = res.data?.results || []
    const ok = drawingResults.value.filter(r => r.ok).length
    const fail = drawingResults.value.length - ok
    ElMessage.success(`完成：${ok}成功${fail>0?'，'+fail+'失败':''}`)
    drawingFiles.value = []
    if (drawingInput.value) drawingInput.value.value = ''
    await loadAllAttachmentCounts()
  } catch (e) { ElMessage.error('上传失败') }
  drawingLoading.value = false
}

// ── Edit ──

function getDefaultForm(specialty) {
  const spec = specialties.value.find(s => s.value === specialty)
  const f = { specialty, product_model: '', name: '', standard: '', supplier: '', notes: '' }
  if (spec?.fields) spec.fields.forEach(col => { if (!(col.key in f)) f[col.key] = '' })
  return f
}

async function openEdit(row) {
  editing.value = row
  if (row) {
    form.value = { ...row }
    try { const r = await api.get(`/product-tech/${row.id}/files`); editFiles.value = r.data || [] }
    catch { editFiles.value = [] }
    loadAllThumbnails(editFiles.value, row.id)
  } else {
    form.value = getDefaultForm(activeSpecialty.value)
    editFiles.value = []
  }
  editPendingFiles.value = []
  showDialog.value = true
}

function onSpecialtyChange(newSpec) {
  const old = { ...form.value }
  form.value = getDefaultForm(newSpec)
  form.value.product_model = old.product_model
  form.value.name = old.name
  form.value.specialty = newSpec
}

function onEditFileChange() { editPendingFiles.value = Array.from(editFileInput.value?.files || []) }

async function onParseFile(e) {
  const files = e.target?.files || []
  if (!files.length) return
  importingSingle.value = true
  try {
    const fd = new FormData()
    fd.append('file', files[0])
    fd.append('specialty', form.value.specialty || activeSpecialty.value)
    if (manualEncoding.value) fd.append('encoding', manualEncoding.value)
    const res = await api.post('/product-tech/parse-all', fd)
    parseRecords.value = res.data?.records || []
    parseHeaders.value = res.data?.headers_found || []
    parseEncoding.value = res.data?.encoding || '?'
    parseSample.value = res.data?.sample || ''
    parseRawHeaders.value = res.data?.raw_headers || []
    if (parseRecords.value.length === 0) {
      ElMessage.warning('未识别到有效产品记录')
    } else {
      showParseDlg.value = true
      ElMessage.success(`识别到${parseRecords.value.length}条记录`)
    }
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '解析失败') }
  importingSingle.value = false
  e.target.value = ''
}

function fillForm(rec) {
  for (const [k, v] of Object.entries(rec)) {
    if (v) form.value[k] = v
  }
  // If 辅驱电机 with product_drawing_no, also set product_model for compatibility
  if (rec.product_line === '辅驱电机' && rec.product_drawing_no && !rec.product_model) {
    form.value.product_drawing_no = rec.product_drawing_no
  }
  showParseDlg.value = false
  ElMessage.success('已填入表单，请核实后保存')
}

// ── Template field order per product line (matches download template columns) ──
const PL_FIELD_ORDERS = {
  '主驱电机': ['product_code','rated_power','rated_voltage','rated_speed','product_model',
               'em_design_no','back_emf_coef','peak_torque','peak_torque_current','peak_torque_speed',
               'stack_height','winding','sensor_type','spline_spec',
               'mounting_spigot_dia','mounting_method','rear_cover_fixing','brake',
               'insulation_class','protection_level','motor_type','status','notes'],
  '辅驱电机': ['product_code','product_drawing_no','motor_type',
               'rated_power','rated_speed','rated_voltage',
               'rear_cover','temp_wire','ground_wire','shaft_dia',
               'front_cover_spigot','mounting_hole','shaft_rotation','harness_bracket','notes'],
  '空压机': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes',
             'rated_power','rated_speed','rated_voltage','rated_current','efficiency','cooling_method',
             'protection_level','em_design_no','winding','mounting_method','weight'],
  '转向泵': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes',
             'rated_power','rated_speed','rated_voltage','rated_current','efficiency','cooling_method',
             'protection_level','em_design_no','winding','mounting_method','weight'],
  '工业永磁': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes',
               'rated_power','peak_power','rated_torque','peak_torque','rated_speed','max_speed',
               'rated_voltage','efficiency','cooling_method','insulation_class','protection_level',
               'em_design_no','winding','mounting_method','weight'],
  'EMB': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes',
          'rated_power','rated_torque','peak_torque','rated_speed','rated_voltage','rated_current',
          'efficiency','cooling_method','protection_level','em_design_no','winding','brake',
          'mounting_method','weight'],
  '关节模组': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes',
               'rated_power','rated_torque','peak_torque','rated_speed','rated_voltage',
               'efficiency','cooling_method','protection_level','em_design_no','winding',
               'sensor_type','mounting_method','weight'],
  '其他': ['product_code','product_model','motor_type','product_line','status','standard','supplier','notes'],
}

function onPasteProductLineChange() {
  pasteError.value = ''
}

function closePasteDialog() {
  showPasteImport.value = false
  pasteText.value = ''
  pasteResults.value = []
  pasteError.value = ''
  pasteDebug.value = ''
}

const pasteSelectedCount = computed(() => pasteResults.value.filter(r => r._selected).length)

function pasteSelectAll() { pasteResults.value.forEach(r => r._selected = true) }
function pasteSelectNone() { pasteResults.value.forEach(r => r._selected = false) }

function pasteDeleteSelected() {
  pasteResults.value = pasteResults.value.filter(r => !r._selected)
}

function doPasteImport() {
  pasteError.value = ''
  pasteDebug.value = ''
  if (!pasteText.value.trim()) { pasteError.value = '请先粘贴数据'; return }
  pasteLoading.value = true
  try {
    // Detect delimiter
    const text = pasteText.value
    let delim = pasteDelim.value
    if (delim === 'auto') {
      const sample = text.split('\n').slice(0, 3).join('')
      const tabCount = (sample.match(/\t/g) || []).length
      const commaCount = (sample.match(/,/g) || []).length
      delim = tabCount >= commaCount ? '\t' : ','
    }

    // Split lines
    const lines = text.trim().split('\n').filter(l => l.trim())
    if (lines.length < 1) { pasteError.value = '无有效数据行'; pasteLoading.value = false; return }

    const rows = lines.map(line =>
      line.split(delim).map(c => c.trim().replace(/^"|"$/g, ''))
    )

    // Use template field order for selected product line
    const pl = pasteProductLine.value || '其他'
    let fieldOrder = PL_FIELD_ORDERS[pl] || PL_FIELD_ORDERS['其他'] || []

    // Auto-detect if data has an extra 产品线 column (old template compatibility)
    // Check if there's a column containing known product line names right after motor_type
    const KNOWN_PRODUCT_LINES = Object.keys(PL_FIELD_ORDERS)
    let hasProductLineCol = false
    if (rows.length > 0 && rows[0].length >= 3) {
      // Check col 2 (after 产品编码, 产品图号) and col 3 (after 电机种类)
      for (const checkCol of [2, 3]) {
        const vals = rows.map(r => (r[checkCol] || '').trim()).filter(Boolean)
        const matchCount = vals.filter(v => KNOWN_PRODUCT_LINES.includes(v)).length
        if (matchCount >= vals.length * 0.5) {
          hasProductLineCol = true
          // Insert product_line at this position in fieldOrder
          const newOrder = [...fieldOrder]
          newOrder.splice(checkCol, 0, 'product_line')
          fieldOrder = newOrder
          break
        }
      }
    }

    const results = []
    const colCount = Math.max(...rows.map(r => r.length), 0)
    if (colCount === 0) { pasteError.value = '未检测到任何列数据，请检查分隔符设置'; pasteLoading.value = false; return }

    for (let r = 0; r < rows.length; r++) {
      const row = rows[r]
      if (!row.some(c => c)) continue
      const rec = { specialty: form.value.specialty || activeSpecialty.value, status: '研发中', product_line: pl, _selected: false }
      for (let i = 0; i < Math.min(row.length, fieldOrder.length); i++) {
        const val = row[i]
        if (val) rec[fieldOrder[i]] = val
      }
      // If data had its own product_line value, prefer it over dropdown selection
      if (hasProductLineCol && rec.product_line && rec.product_line !== pl) {
        // Keep the data's product_line
      } else if (!rec.product_line) {
        rec.product_line = pl
      }
      // Accept row if it has at least one identifying field
      if (rec.product_code || rec.product_drawing_no || rec.product_model || rec.name) {
        results.push(rec)
      }
    }

    pasteResults.value = results
    if (results.length === 0) {
      pasteError.value = `未识别到有效数据。共${rows.length}行，${colCount}列，产品线模板: ${pl}(${fieldOrder.length}列)`
    } else {
      const fieldsUsed = fieldOrder.slice(0, colCount)
      pasteDebug.value = fieldsUsed.join(', ')
      pasteSelectAll()  // default all selected
    }
  } catch (e) {
    pasteError.value = '解析失败: ' + (e.message || e)
  }
  pasteLoading.value = false
}

async function pasteImportSelected() {
  const selected = pasteResults.value.filter(r => r._selected)
  if (selected.length === 0) return
  let ok = 0, fail = 0
  for (const rec of selected) {
    try {
      const clean = {}
      for (const [k, v] of Object.entries(rec)) {
        if (k !== '_selected' && v) clean[k] = v
      }
      await api.post('/product-tech', clean)
      ok++
    } catch (e) {
      fail++
      if (fail === 1 && e?.response?.data?.detail) {
        pasteError.value = '导入错误: ' + e.response.data.detail
      }
    }
  }
  if (ok > 0) {
    ElMessage.success(`导入完成：${ok}个成功${fail > 0 ? '，' + fail + '个失败' : ''}`)
    // Remove successfully imported from list
    pasteResults.value = pasteResults.value.filter(r => !r._selected)
    pasteError.value = ''
    await load()
  }
}

async function pasteImportAll() {
  pasteSelectAll()
  await pasteImportSelected()
}

async function importAllParsed() {
  importingAll.value = true
  let ok = 0, fail = 0
  for (const rec of parseRecords.value) {
    try {
      await api.post('/product-tech', rec)
      ok++
    } catch { fail++ }
  }
  ElMessage.success(`全部导入完成：${ok}个成功${fail > 0 ? `，${fail}个失败` : ''}`)
  showParseDlg.value = false
  importingAll.value = false
  await load()
}

async function save() {
  if (!form.value.product_model) { ElMessage.warning('请输入产品型号'); return }
  saving.value = true
  try {
    let itemId
    if (editing.value) {
      await api.put(`/product-tech/${editing.value.id}`, form.value)
      itemId = editing.value.id
    } else {
      const res = await api.post('/product-tech', form.value)
      itemId = res.data.id
    }
    if (editPendingFiles.value.length > 0) {
      const fd = new FormData()
      for (const f of editPendingFiles.value) fd.append('files', f)
      await api.post(`/product-tech/${itemId}/files`, fd)
    }
    ElMessage.success(editing.value ? '已更新' : '已添加')
    showDialog.value = false
    if (itemId !== undefined) {
      try { const r = await api.get(`/product-tech/${itemId}/files`); attachmentsCache.value[itemId] = r.data || [] } catch {}
    }
    await load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '保存失败') }
  saving.value = false
}

async function delItem(id) {
  try {
    await ElMessageBox.confirm('删除此产品型号及所有附件？', '确认', { type: 'warning' })
    await api.delete(`/product-tech/${id}`)
    ElMessage.success('已删除')
    await load()
  } catch {}
}

// ── Files ──

async function openFilesDialog(row) {
  selectedProductId.value = row.id; selectedProductName.value = row.product_model || row.name || ''
  try {
    const r = await api.get(`/product-tech/${row.id}/files`)
    selectedFiles.value = r.data || []; attachmentsCache.value[row.id] = r.data || []
  } catch { selectedFiles.value = [] }
  loadAllThumbnails(selectedFiles.value, row.id)
  showFilesDlg.value = true
}

function onQuickFileChange() {
  const files = Array.from(quickFileInput.value?.files || [])
  if (files.length) uploadQuickFiles(selectedProductId.value, files)
}

async function uploadQuickFiles(itemId, files) {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  await api.post(`/product-tech/${itemId}/files`, fd)
  const r = await api.get(`/product-tech/${itemId}/files`)
  selectedFiles.value = r.data || []; attachmentsCache.value[itemId] = r.data || []
  loadAllThumbnails(selectedFiles.value, itemId)
  if (quickFileInput.value) quickFileInput.value.value = ''
  ElMessage.success('已上传')
}

async function deleteFile(itemId, fileId) {
  await api.delete(`/product-tech/${itemId}/files/${fileId}`)
  if (thumbnailCache.value[fileId]) { URL.revokeObjectURL(thumbnailCache.value[fileId]); delete thumbnailCache.value[fileId] }
  try { const r = await api.get(`/product-tech/${itemId}/files`); editFiles.value = r.data || []; attachmentsCache.value[itemId] = r.data || []; loadAllThumbnails(editFiles.value, itemId) } catch { editFiles.value = [] }
}

async function deleteFileFromDialog(fileId) {
  await deleteFile(selectedProductId.value, fileId)
  try { const r = await api.get(`/product-tech/${selectedProductId.value}/files`); selectedFiles.value = r.data || []; attachmentsCache.value[selectedProductId.value] = r.data || []; loadAllThumbnails(selectedFiles.value, selectedProductId.value) } catch { selectedFiles.value = [] }
}

function downloadFile(itemId, fileId, filename) {
  api.get(`/product-tech/${itemId}/files/${fileId}/download`, { responseType: 'blob' }).then(res => {
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }).catch(() => ElMessage.error('下载失败'))
}

function isImageFile(fn) {
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(fn || '')
}

function isPreviewable(fn) {
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico|pdf|txt|csv|json|xml|html?|xlsx?|xls|docx?)$/i.test(fn || '')
}

function previewUrl(itemId, fileId) {
  return thumbnailCache.value[fileId] || ''
}

async function loadThumbnail(file, itemId) {
  if (!file || !isImageFile(file.filename)) return
  if (thumbnailCache.value[file.id]) return
  try {
    const res = await api.get(`/product-tech/${itemId}/files/${file.id}/preview`, { responseType: 'blob' })
    thumbnailCache.value[file.id] = URL.createObjectURL(res.data)
  } catch { /* ignore load errors */ }
}

async function loadAllThumbnails(files, itemId) {
  await Promise.all(files.map(f => loadThumbnail(f, itemId)))
}

async function openPreview(itemId, fileId) {
  try {
    const res = await api.get(`/product-tech/${itemId}/files/${fileId}/preview`, { responseType: 'blob' })
    const blob = new Blob([res.data], { type: res.headers['content-type'] || 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    // Revoke after a delay to allow the new tab to load
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch { ElMessage.error('预览失败') }
}

function fileIcon(fn) {
  const ext = (fn || '').split('.').pop().toLowerCase()
  const icons = {
    pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊',
    ppt: '📽️', pptx: '📽️',
    zip: '📦', rar: '📦', '7z': '📦', gz: '📦',
    dwg: '📐', dxf: '📐', step: '📐', stp: '📐',
    mp4: '🎬', avi: '🎬', mov: '🎬',
    mp3: '🎵', wav: '🎵',
  }
  return icons[ext] || '📎'
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let s = bytes
  while (s >= 1024 && i < units.length - 1) { s /= 1024; i++ }
  return s.toFixed(i === 0 ? 0 : 1) + ' ' + units[i]
}

onMounted(async () => {
  await loadSpecs()
  if (specialties.value.length) activeSpecialty.value = specialties.value[0].value
  await load()
})
</script>

<style scoped>
.pt-page { max-width: 1400px; }
.stat-grid { display:flex;gap:12px;flex-wrap:wrap }
.stat-card { flex:1;min-width:140px;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center }
.stat-value { font-size:28px;font-weight:700;line-height:1.2 }
.stat-label { font-size:12px;color:var(--text-secondary);margin-top:4px }
.stat-info .stat-value { color:#3b82f6 }
.stat-success .stat-value { color:#22c55e }
.stat-warning .stat-value { color:#f59e0b }
</style>
