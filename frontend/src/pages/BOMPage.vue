<template>
<div class="bom-v2">
  <h2 style="margin:0 0 16px;font-size:18px">BOM 管理</h2>
  <el-tabs v-model="tab">
    <!-- ═══ TAB 1: 产品BOM管理 ═══ -->
    <el-tab-pane label="产品BOM管理" name="p">
      <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap">
        <el-input v-model="s1" placeholder="搜索名称..." size="small" clearable style="width:180px" @keyup.enter="refreshP" @clear="refreshP" />
        <el-select v-model="filtProj" size="small" placeholder="关联项目" clearable style="width:150px" @change="refreshP" filterable>
          <el-option v-for="p in projs" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button type="primary" size="small" @click="showUp=true">上传BOM文件</el-button>
        <el-button size="small" type="success" @click="showConv=true">🔧 转换工具BOM</el-button>
        <el-button type="success" size="small" @click="showPaste=!showPaste">{{ showPaste?'收起粘贴区':'粘贴数据' }}</el-button>
        <el-button size="small" @click="openCmp" :disabled="selIds.length!==2">BOM对比</el-button>
        <el-button size="small" @click="openGen">自动生成BOM</el-button>
        <el-button size="small" @click="downloadTemplate">下载模板</el-button>
        <el-select v-model="bomCat" size="small" style="width:100px" @change="refreshP">
          <el-option label="全部类别" value="" />
          <el-option label="电机类" value="电机类" />
          <el-option label="电控类" value="电控类" />
          <el-option label="其他类" value="其他类" />
        </el-select>
        <el-button size="small" @click="refreshP" :loading="lp">刷新</el-button>
        <span v-if="plist.length" style="font-size:13px;color:var(--text-muted);line-height:32px">共 {{ plist.length }} 个BOM</span>
      </div>

      <!-- Batch bar: 勾选后出现, 同知识库的批量操作下拉 -->
      <div v-if="selIds.length" style="margin-bottom:12px;padding:8px 12px;border:1px solid #f0c36d;background:#fdf6e3;border-radius:6px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span style="font-size:13px;font-weight:600">已选择 {{ selIds.length }} 个BOM</span>
        <el-select v-model="batchOp" size="small" placeholder="批量操作..." style="width:150px" @change="doBatchOp">
          <el-option label="批量删除" value="delete" />
          <el-option label="批量设为失效" value="expire" />
          <el-option label="批量移动" value="move" />
        </el-select>
        <el-button size="small" text @click="selIds = []; batchOp = ''">取消选择</el-button>
      </div>

      <!-- Paste area -->
      <div v-if="showPaste" style="margin-bottom:12px;padding:12px;border:1px solid var(--border-color);border-radius:8px;background:var(--bg)">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start">
          <!-- Left: paste textarea -->
          <div style="flex:1;min-width:400px">
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px">从 Excel 选中全部内容 Ctrl+C → 在下框 Ctrl+V 粘贴</div>
            <el-input v-model="upPaste" type="textarea" :rows="4" placeholder="在此粘贴（Ctrl+V），自动识别Excel表格结构..." @input="onUpPasteInput" @paste.native="onPasteNative" />
            <div v-if="upPastePreview" style="margin-top:4px;font-size:12px;color:var(--text-muted)">
              表头(行{{ upPastePreview.headerRow+1 }},{{ upPastePreview.headers.length }}列): {{ upPastePreview.headers.join(' | ') }}（数据 {{ upPastePreview.dataRows }} 行）
            </div>
            <!-- Preview table: all data rows, scrollable -->
            <div v-if="upPreviewRows.length" style="margin-top:6px;overflow:auto;max-height:280px;max-width:100%;border:1px solid #e0e0e0;border-radius:4px">
              <table style="font-size:11px;border-collapse:collapse;white-space:nowrap">
                <thead><tr>
                  <th style="border:1px solid #bbb;padding:2px 4px;background:#e8f0fe;position:sticky;top:0;z-index:1;min-width:30px;font-size:10px">列数</th>
                  <th v-for="(h,i) in upPastePreview.headers" :key="i" style="border:1px solid #bbb;padding:2px 6px;background:#e8f0fe;position:sticky;top:0;z-index:1">{{ h }}<br><span style="font-weight:normal;color:#999;font-size:10px">{{ i+1 }}</span></th>
                </tr></thead>
                <tbody>
                  <tr v-for="(row,ri) in upPreviewRows" :key="ri">
                    <td style="border:1px solid #eee;padding:2px 4px;text-align:center;font-size:10px;color:#999">{{ upRowMeta[ri] || '-' }}</td>
                    <td v-for="(cell,ci) in (upPastePreview.headers||[]).length" :key="ci" style="border:1px solid #eee;padding:2px 6px;max-width:160px;overflow:hidden;text-overflow:ellipsis" :style="(row[ci]||'')===''?{color:'#ccc'}:{}">{{ row[ci] || '(空)' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="upPreviewColWarn" style="font-size:11px;color:#e6a23c;margin-top:2px">{{ upPreviewColWarn }}</div>
            <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              <el-button type="primary" size="small" @click="doPasteUpload" :loading="upIng">保存为BOM表格</el-button>
              <el-button size="small" @click="pasteFillDown" :disabled="!upPaste.trim()">向下填充空值</el-button>
              <el-button size="small" @click="fixMultiline" :disabled="!upPaste.trim()" title="合并因单元格内换行被拆分的行">修复换行</el-button>
              <input type="file" ref="ocrInput" accept="image/*" style="display:none" @change="onOcrFile" />
              <el-button size="small" @click="$refs.ocrInput.click()" :loading="ocrIng">📷 截图转表格</el-button>
              <span v-if="upMsg" style="font-size:12px;color:var(--text-muted)">{{ upMsg }}</span>
            </div>
          </div>
          <!-- Right: meta fields (auto-filled from template) -->
          <div style="width:260px;font-size:12px">
            <div style="font-weight:600;margin-bottom:6px">BOM 信息 <el-button link size="small" @click="autoDetectMeta">智能识别</el-button></div>
            <div v-for="m in upMetaFields" :key="m.key" style="margin-bottom:4px">
              <span style="color:var(--text-muted);display:inline-block;width:56px">{{ m.label }}</span>
              <el-input v-model="upMeta[m.key]" size="small" :placeholder="m.placeholder" style="width:190px" />
            </div>
          </div>
        </div>
      </div>

      <el-table :data="plist" size="small" stripe v-loading="lp" max-height="calc(100vh - 260px)" empty-text="暂无BOM清单，请导入" @selection-change="s=>selIds=s.map(x=>x.id)">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="name" label="BOM名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="产品名称" width="140" show-overflow-tooltip>
          <template #default="{row}">{{ row.meta?.product_name || row.product_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="产品型号" width="110" show-overflow-tooltip>
          <template #default="{row}">{{ row.meta?.product_model || row.product_model || '-' }}</template>
        </el-table-column>
        <el-table-column prop="project_name" label="关联项目" width="180" show-overflow-tooltip />
        <el-table-column label="类别" width="80">
          <template #default="{row}">{{ row.meta?.bom_category || row.bom_category || '-' }}</template>
        </el-table-column>
        <el-table-column label="版本" width="80">
          <template #default="{row}">{{ row.meta?.version || row.version || '-' }}</template>
        </el-table-column>
        <el-table-column prop="item_count" label="行数" width="70" />
        <el-table-column prop="status" label="状态" width="75">
          <template #default="{row}">
            <el-tag :type="row.status==='失效'?'info':'success'" size="small" style="cursor:pointer" @click="toggleBomStatus(row)">{{ row.status||'有效' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_file" label="来源文件" width="150" show-overflow-tooltip />
        <el-table-column prop="created_at" label="日期" width="110"><template #default="{row}">{{ (row.created_at||'').slice(0,10) }}</template></el-table-column>
        <el-table-column label="操作" width="270">
          <template #default="{row}">
            <el-button link size="small" @click="viewDetail(row.id)">查看</el-button>
            <el-button link size="small" @click="editBom(row)">编辑</el-button>
            <el-button link size="small" @click="exportOne(row.id)">导出</el-button>
            <el-button link size="small" @click="openBomFiles(row)">📎</el-button>
            <el-button link size="small" @click="checkBom(row)">🔍</el-button>
            <el-button link size="small" @click="openAsk(row)">💬</el-button>
            <el-button link size="small" @click="estCost(row)">💰</el-button>
            <el-button link size="small" type="danger" @click="delOne(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- File upload dialog -->
      <el-dialog v-model="showUp" title="上传BOM文件" width="450px" @close="upFile=null;upPreview=null;upError=''">
        <input type="file" ref="fileInput" style="display:none" @change="onNativeFilePick" />
        <div @click="$refs.fileInput.click()" style="border:2px dashed var(--border-color);border-radius:8px;padding:24px;text-align:center;cursor:pointer" :style="upFile?{borderColor:'var(--el-color-primary)'}:{}">
          <div style="font-size:28px;margin-bottom:6px">📄</div>
          <div style="font-size:13px">{{ upFile ? upFile.name : '点击选择文件' }}</div>
        </div>
        <template #footer>
          <el-button @click="showUp=false">取消</el-button>
          <el-button type="primary" @click="doUpload" :loading="upIng" :disabled="!upFile">上传</el-button>
        </template>
      </el-dialog>

      <!-- Detail dialog with inline editing -->
      <el-dialog v-model="showDet" :title="det?.name||'BOM明细'" width="1100px" top="3vh" @close="detEdit=null">
        <!-- Meta info bar -->
        <div v-if="det?.meta && Object.values(det.meta).some(v=>v)" style="margin-bottom:8px;padding:8px 12px;background:#f8fafc;border-radius:6px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--text-secondary)">
          <span v-if="det.meta.product_model"><b>产品型号:</b> {{ det.meta.product_model }}</span>
          <span v-if="det.meta.version"><b>版本:</b> {{ det.meta.version }}</span>
          <span v-if="det.meta.release_date"><b>发布日期:</b> {{ det.meta.release_date }}</span>
          <span v-if="det.meta.designer"><b>设计:</b> {{ det.meta.designer }}</span>
          <span v-if="det.meta.reviewer"><b>审核:</b> {{ det.meta.reviewer }}</span>
          <span v-if="det.meta.approver"><b>批准:</b> {{ det.meta.approver }}</span>
          <span v-if="det.meta.customer"><b>客户:</b> {{ det.meta.customer }}</span>
        </div>
        <!-- 表头信息块(内部模板: 标题+标准字段+模板字段布局) -->
        <div v-if="det?.info?.length" style="margin-bottom:8px;padding:8px 12px;background:#f8fafc;border-radius:6px">
          <div v-if="infoTitleDet" style="font-weight:700;font-size:13px;text-align:center;margin-bottom:4px">{{ infoTitleDet.label }}</div>
          <div v-if="infoStdDet.length" style="display:flex;gap:6px 18px;flex-wrap:wrap;font-size:12px;margin-bottom:4px;padding-bottom:4px;border-bottom:1px dashed #e5e7eb">
            <span v-for="f in infoStdDet" :key="f.label" style="color:var(--text-secondary)">
              <b>{{ f.label }}:</b> <span :style="f.value?{}:{color:'#ccc'}">{{ f.value || '(未填)' }}</span>
            </span>
          </div>
          <div v-for="(grp, gi) in infoGroupsDet" :key="'g'+gi" style="display:flex;gap:6px 18px;flex-wrap:wrap;font-size:12px;margin-bottom:2px">
            <span v-for="f in grp" :key="f.label" style="color:var(--text-secondary)">
              <b>{{ f.label }}:</b> <span :style="f.value?{}:{color:'#ccc'}">{{ f.value || '(未填)' }}</span>
            </span>
          </div>
          <div v-for="n in infoNotesDet" :key="'n'+n.label" style="font-size:11px;color:#909399">※ {{ n.label }}</div>
        </div>
        <div v-if="det" style="font-size:13px;color:var(--text-muted);margin-bottom:8px;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
          <span>项目: {{ det.project_name || '-' }}</span>
          <span>行数: {{ (detEdit||det.items||[]).length }}</span>
          <span>来源: {{ det.source_file || '-' }}</span>
          <template v-if="detEdit">
            <el-button size="small" type="primary" @click="saveDetEdit" :loading="detSaving">保存修改</el-button>
            <el-button size="small" @click="detEdit=null">取消编辑</el-button>
            <el-button size="small" @click="detEdit.push((det.headers||[]).map(()=>''))">+ 插入行</el-button>
            <el-button size="small" @click="fillDownEdit">向下填充</el-button>
          </template>
          <el-button v-else size="small" @click="startEdit">编辑表格</el-button>
        </div>
        <el-table :data="(detEdit||det?.items||[])" size="small" border max-height="55vh" v-if="det">
          <el-table-column v-for="(h,i) in (det?.headers||[])" :key="i" :label="h||('列'+(i+1))" min-width="90" show-overflow-tooltip>
            <template #default="{row,$index}">
              <el-input v-if="detEdit" v-model="detEdit[$index][i]" size="small" :placeholder="h" />
              <span v-else>{{ (row[i]||'') }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="detEdit" label="操作" width="60" fixed="right">
            <template #default="{ $index }">
              <el-button link size="small" type="danger" @click="detEdit.splice($index,1)">删行</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-dialog>

      <!-- BOM对比 dialog -->
      <el-dialog v-model="showCmpDlg" title="BOM对比" width="1100px" top="3vh">
        <div v-if="cmpR" style="font-size:13px">
          <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">
            <el-tag>A: {{ cmpR.name_a }} ({{ cmpR.count_a }}项)</el-tag>
            <el-tag type="success">B: {{ cmpR.name_b }} ({{ cmpR.count_b }}项)</el-tag>
            <el-tag type="warning">公共: {{ cmpR.common }}项</el-tag>
            <el-tag type="danger">仅A: {{ cmpR.only_in_a?.length || 0 }}项</el-tag>
            <el-tag type="info">仅B: {{ cmpR.only_in_b?.length || 0 }}项</el-tag>
            <el-tag v-if="cmpR.changed_detail?.length" type="danger">{{ cmpR.changed_detail.length }}项有差异</el-tag>
          </div>
          <!-- Per-cell diff table: only show differing columns -->
          <div v-if="cmpR.changed_detail?.length" style="margin-bottom:16px">
            <div style="font-weight:600;margin-bottom:6px">差异明细（共{{ cmpR.changed_detail.length }}项，仅显示有差异的列）</div>
            <div v-for="item in cmpR.changed_detail" :key="item.code" style="margin-bottom:8px;border:1px solid #f0c0c0;border-radius:4px;overflow:hidden">
              <div style="background:#fff5f5;padding:4px 8px;font-size:12px;font-weight:600;border-bottom:1px solid #f0c0c0">编码: {{ item.code }}（{{ item.cells.length }}处差异）</div>
              <table style="width:100%;font-size:12px;border-collapse:collapse">
                <thead><tr>
                  <th style="border:1px solid #f0c0c0;padding:4px 8px;background:#fff5f5;text-align:left;width:90px">列名</th>
                  <th style="border:1px solid #f0c0c0;padding:4px 8px;background:#e8f5e9;text-align:left">BOM-A</th>
                  <th style="border:1px solid #f0c0c0;padding:4px 8px;background:#e3f2fd;text-align:left">BOM-B</th>
                </tr></thead>
                <tbody>
                  <tr v-for="cell in item.cells" :key="cell.col" style="background:#fff5f5">
                    <td style="border:1px solid #f0c0c0;padding:4px 8px;font-weight:500">{{ cell.header }}</td>
                    <td style="border:1px solid #f0c0c0;padding:4px 8px;color:#d32f2f;font-weight:600">{{ cell.a || '(空)' }}</td>
                    <td style="border:1px solid #f0c0c0;padding:4px 8px;color:#d32f2f;font-weight:600">{{ cell.b || '(空)' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <!-- Only in A -->
          <div v-if="cmpR.only_in_a?.length" style="margin-bottom:16px">
            <div style="font-weight:600;margin-bottom:6px;color:#d32f2f">仅在 A ({{ cmpR.only_in_a.length }}项)</div>
            <el-table :data="cmpR.only_in_a" size="small" border max-height="200px">
              <el-table-column v-for="(h,i) in (cmpR.headers_a||[])" :key="i" :label="h" min-width="80" show-overflow-tooltip>
                <template #default="{row}">{{ row[i] || '' }}</template>
              </el-table-column>
            </el-table>
          </div>
          <!-- Only in B -->
          <div v-if="cmpR.only_in_b?.length">
            <div style="font-weight:600;margin-bottom:6px;color:#1565c0">仅在 B ({{ cmpR.only_in_b.length }}项)</div>
            <el-table :data="cmpR.only_in_b" size="small" border max-height="200px">
              <el-table-column v-for="(h,i) in (cmpR.headers_b||[])" :key="i" :label="h" min-width="80" show-overflow-tooltip>
                <template #default="{row}">{{ row[i] || '' }}</template>
              </el-table-column>
            </el-table>
          </div>
          <div v-if="!cmpR.changed_detail?.length && !cmpR.only_in_a?.length && !cmpR.only_in_b?.length" style="color:var(--text-muted);text-align:center;padding:20px">两份BOM完全一致</div>
        </div>
        <template #footer>
          <div style="display:flex;gap:8px;justify-content:space-between">
            <el-button @click="showCmpDlg=false">关闭</el-button>
            <el-button type="primary" @click="genEcn" :loading="ecnIng" :disabled="!cmpR">🔄 生成变更单(ECN)</el-button>
          </div>
        </template>
      </el-dialog>

      <!-- 自动生成BOM dialog (upgraded with drawing upload) -->
      <el-dialog v-model="showGenDlg" title="自动生成BOM" width="500px">
        <el-divider>📋 模板</el-divider>
        <el-form label-width="80px" size="small" style="margin-bottom:12px">
          <el-form-item label="模板">
            <el-select v-model="genTpl" style="width:100%">
              <el-option label="电机类BOM (11项)" value="standard_motor" />
              <el-option label="电控类BOM (10项)" value="standard_control" />
              <el-option label="其他类BOM (5项)" value="standard_other" />
              <el-option v-for="t in internalTpls" :key="t.id"
                         :label="'📄 内部模板' + (t.is_default ? '(默认)' : '') + ': ' + (t.name || t.filename)"
                         :value="'internal:' + t.id" />
              <el-option v-if="!internalTpls.length" label="📄 内部模板 (未上传)" value="internal" disabled />
            </el-select>
          </el-form-item>
          <el-form-item v-if="genTpl && genTpl.startsWith('internal')" label="内部模板">
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;width:100%">
              <el-button size="small" type="primary" plain @click="itFileRef?.click()">🔄 更换模板文件</el-button>
              <el-button size="small" plain @click="addTplClick">➕ 新增模板</el-button>
              <span v-if="curTplMeta" style="font-size:12px;color:var(--text-muted)">{{ curTplMeta.filename }} ({{ curTplMeta.sheets?.join(' / ') }})</span>
              <span v-else style="font-size:12px;color:#e6a23c">请先上传公司模板(.xls/.xlsx)</span>
            </div>
          </el-form-item>
          <el-form-item label="关联项目">
            <el-select v-model="genPid" style="width:100%" filterable clearable>
              <el-option v-for="p in projs" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <input type="file" ref="itFileRef" accept=".xls,.xlsx" style="display:none" @change="uploadInternalTpl" />
        <input type="file" ref="addFileRef" accept=".xls,.xlsx" style="display:none" @change="addTplFile" />
        <el-divider>🤖 图纸识别生成</el-divider>
        <div style="border:2px dashed #3b82f6;border-radius:8px;padding:30px;text-align:center;cursor:pointer;background:#f0f7ff" @click="genFileRef?.click()">
          <div style="font-size:36px;margin-bottom:8px">📐</div>
          <div style="font-size:14px;font-weight:600;margin-bottom:4px">点击上传电机/电控图纸</div>
          <div style="font-size:11px;color:var(--text-muted)">图片或PDF，AI自动识别物料并生成BOM清单</div>
        </div>
        <input type="file" ref="genFileRef" accept="image/*,.pdf" style="display:none" @change="doGenFromDrawing" />
        <div v-if="genFile" style="margin-top:8px;font-size:12px">📐 {{ genFile.name }} ({{ (genFile.size/1024).toFixed(1) }}KB)</div>
        <div v-if="genItems.length" style="font-size:11px;color:#e6a23c;margin-top:4px">⚠️ AI识别结果仅供参考，请人工核对数量和名称后再保存</div>
        <div v-if="genStatus" style="margin-top:8px;font-size:12px;white-space:pre-line;padding:8px;border-radius:4px" :style="{background:genOk?'#f0fdf4':'#fef2f2',color:genOk?'#22c55e':'#ef4444'}">{{ genStatus }}</div>
        <div v-if="genRaw" style="margin-top:4px;font-size:11px;color:var(--text-muted);background:#f5f7fa;padding:8px;border-radius:4px;max-height:150px;overflow-y:auto;white-space:pre-wrap;word-break:break-all">🔍 AI返回原文: {{ genRaw }}</div>
        <!-- Drawing result table -->
        <div v-if="genItems.length" style="margin-top:12px">
          <el-table :data="genItems" size="small" max-height="300">
            <el-table-column prop="seq" label="序号" width="50" />
            <el-table-column prop="category" label="类别" width="70" />
            <el-table-column prop="name" label="物料名称" width="140" />
            <el-table-column prop="spec" label="规格型号" width="150" />
            <el-table-column prop="position" label="元件位置" width="80" />
            <el-table-column prop="unit" label="单位" width="50" />
            <el-table-column prop="qty" label="数量" width="50" />
            <el-table-column prop="brand" label="品牌" width="80" />
            <el-table-column prop="supplier" label="供应商" width="100" />
            <el-table-column prop="note" label="备注" min-width="120" />
          </el-table>
        </div>
        <template #footer>
          <el-button @click="showGenDlg=false;genItems=[];genFile=null;genStatus='';genRaw=''">取消</el-button>
          <el-button v-if="genItems.length" type="primary" @click="openDraftFromGen" :loading="genIng">✏️ 核对并保存</el-button>
          <el-button type="primary" @click="doGen" :loading="genIng">生成并编辑</el-button>
        </template>
      </el-dialog>

      <!-- 模板生成预览编辑 dialog：模板仅为起点，每个产品的物料清单不同，必须人工核对增删改后再保存 -->
      <el-dialog v-model="showDraftDlg" title="模板生成 — 核对并编辑物料清单" width="1100px">
        <el-form label-width="80px" size="small" style="margin-bottom:8px">
          <el-form-item label="清单名称" style="margin-bottom:8px">
            <el-input v-model="draftName" />
          </el-form-item>
        </el-form>
        <div style="font-size:11px;color:#e6a23c;margin-bottom:6px">⚠️ 模板仅为参考起点，每个产品的物料清单不同，请在下方增删改后再保存</div>
        <div v-if="draftSrc === 'internal' && draftInfo.length" style="margin-bottom:10px;border:1px solid #e5e7eb;border-radius:6px;padding:8px 12px">
          <div style="font-weight:700;font-size:13px;text-align:center;margin-bottom:6px">{{ infoTitle?.label }}</div>
          <div v-if="infoStd.length" style="display:flex;gap:8px 14px;flex-wrap:wrap;margin-bottom:6px;padding-bottom:6px;border-bottom:1px dashed #e5e7eb">
            <div v-for="f in infoStd" :key="f.label" style="display:flex;align-items:center;gap:4px;font-size:12px;flex:0 0 auto">
              <span style="color:var(--text-muted);white-space:nowrap">{{ f.label }}</span>
              <el-input v-model="f.value" size="small" style="width:160px" />
            </div>
          </div>
          <div v-for="(grp, gi) in infoGroups" :key="'g'+gi" style="display:flex;gap:8px 14px;flex-wrap:wrap;margin-bottom:4px">
            <div v-for="f in grp" :key="f.label" style="display:flex;align-items:center;gap:4px;font-size:12px;flex:0 0 auto">
              <span style="color:var(--text-muted);white-space:nowrap">{{ f.label }}</span>
              <el-input v-model="f.value" size="small" style="width:130px" />
            </div>
          </div>
          <div v-for="n in infoNotes" :key="'n'+n.label" style="font-size:11px;color:#909399;margin-top:2px">※ {{ n.label }}</div>
        </div>
        <el-table :data="draftItems" size="small" border max-height="400">
          <el-table-column label="#" type="index" width="42" />
          <template v-if="draftSrc === 'internal'">
            <el-table-column label="类别" width="80">
              <template #default="{row}">
                <el-select v-model="row.cat" size="small">
                  <el-option label="半成品" value="半成品" />
                  <el-option label="主材" value="主材" />
                  <el-option label="标准件" value="标准件" />
                  <el-option label="辅材" value="辅材" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="物料编码" width="110"><template #default="{row}"><el-input v-model="row.code" size="small" /></template></el-table-column>
            <el-table-column label="物料名称" width="120"><template #default="{row}"><el-input v-model="row.name" size="small" /></template></el-table-column>
            <el-table-column label="零件图号" width="130"><template #default="{row}"><el-input v-model="row.part_no" size="small" /></template></el-table-column>
            <el-table-column label="材料、牌号、规格、技术条件" min-width="180"><template #default="{row}"><el-input v-model="row.spec" size="small" /></template></el-table-column>
            <el-table-column label="单位" width="60"><template #default="{row}"><el-input v-model="row.unit" size="small" /></template></el-table-column>
            <el-table-column label="用量" width="70"><template #default="{row}"><el-input v-model="row.qty" size="small" /></template></el-table-column>
            <el-table-column label="备注" min-width="100"><template #default="{row}"><el-input v-model="row.note" size="small" /></template></el-table-column>
          </template>
          <template v-else-if="draftSrc === 'drawing'">
            <el-table-column label="类别" width="80">
              <template #default="{row}">
                <el-select v-model="row.cat" size="small">
                  <el-option label="成品" value="成品" />
                  <el-option label="半成品" value="半成品" />
                  <el-option label="辅料" value="辅料" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="物料编码" width="100"><template #default="{row}"><el-input v-model="row.code" size="small" /></template></el-table-column>
            <el-table-column label="物料名称" width="130"><template #default="{row}"><el-input v-model="row.name" size="small" /></template></el-table-column>
            <el-table-column label="规格型号" width="120"><template #default="{row}"><el-input v-model="row.spec" size="small" /></template></el-table-column>
            <el-table-column label="元件位置" width="80"><template #default="{row}"><el-input v-model="row.position" size="small" /></template></el-table-column>
            <el-table-column label="封装" width="70"><template #default="{row}"><el-input v-model="row.package" size="small" /></template></el-table-column>
            <el-table-column label="品牌" width="80"><template #default="{row}"><el-input v-model="row.brand" size="small" /></template></el-table-column>
            <el-table-column label="单位" width="50"><template #default="{row}"><el-input v-model="row.unit" size="small" /></template></el-table-column>
            <el-table-column label="数量" width="50"><template #default="{row}"><el-input v-model="row.qty" size="small" /></template></el-table-column>
            <el-table-column label="供应商" width="80"><template #default="{row}"><el-input v-model="row.supplier" size="small" /></template></el-table-column>
            <el-table-column label="备注" min-width="90"><template #default="{row}"><el-input v-model="row.note" size="small" /></template></el-table-column>
          </template>
          <template v-else>
            <el-table-column label="物料编码" width="100"><template #default="{row}"><el-input v-model="row.code" size="small" /></template></el-table-column>
            <el-table-column label="物料名称" width="130"><template #default="{row}"><el-input v-model="row.name" size="small" /></template></el-table-column>
            <el-table-column label="规格型号" width="120"><template #default="{row}"><el-input v-model="row.spec" size="small" /></template></el-table-column>
            <el-table-column label="元件位置" width="80"><template #default="{row}"><el-input v-model="row.position" size="small" /></template></el-table-column>
            <el-table-column label="封装" width="70"><template #default="{row}"><el-input v-model="row.package" size="small" /></template></el-table-column>
            <el-table-column label="品牌" width="80"><template #default="{row}"><el-input v-model="row.brand" size="small" /></template></el-table-column>
            <el-table-column label="单位" width="50"><template #default="{row}"><el-input v-model="row.unit" size="small" /></template></el-table-column>
            <el-table-column label="数量" width="50"><template #default="{row}"><el-input v-model="row.qty" size="small" /></template></el-table-column>
            <el-table-column label="供应商" width="80"><template #default="{row}"><el-input v-model="row.supplier" size="small" /></template></el-table-column>
            <el-table-column label="备注" min-width="90"><template #default="{row}"><el-input v-model="row.note" size="small" /></template></el-table-column>
          </template>
          <el-table-column label="" width="56" fixed="right"><template #default="{$index}"><el-button link type="danger" size="small" @click="delDraftRow($index)">删除</el-button></template></el-table-column>
        </el-table>
        <div style="margin-top:8px">
          <el-button size="small" @click="addDraftRow">+ 添加物料行</el-button>
          <span style="font-size:11px;color:#909399;margin-left:8px">共 {{ draftItems.length }} 行</span>
        </div>
        <template #footer>
          <el-button @click="showDraftDlg=false">取消</el-button>
          <el-button type="primary" :loading="genIng" @click="saveDraft">💾 保存为BOM</el-button>
        </template>
      </el-dialog>

      <!-- 关联项目 dialog -->
      <el-dialog v-model="showAscDlg" :title="selIds.length > 1 ? '批量移动' : '关联项目'" width="400px">
        <el-form label-width="80px" size="small">
          <el-form-item label="选择项目">
            <el-select v-model="ascPid" style="width:100%" filterable>
              <el-option v-for="p in projs" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
          <div style="font-size:13px;color:var(--text-muted)">已选择 {{ selIds.length }} 个BOM清单</div>
        </el-form>
        <template #footer><el-button @click="showAscDlg=false">取消</el-button><el-button type="primary" @click="doAsc" :loading="ascIng">{{ selIds.length > 1 ? '移动' : '关联' }}</el-button></template>
      </el-dialog>

      <!-- 编辑BOM dialog -->
      <el-dialog v-model="showEditDlg" title="编辑BOM清单" width="450px">
        <el-form :model="eb" label-width="70px" size="small">
          <el-form-item label="名称"><el-input v-model="eb.name" /></el-form-item>
          <el-form-item label="产品名称"><el-input v-model="eb.product_name" placeholder="如：电机控制器总成" /></el-form-item>
          <el-form-item label="产品型号"><el-input v-model="eb.product_model" placeholder="如：CM02" /></el-form-item>
          <el-form-item label="版本号"><el-input v-model="eb.version" placeholder="如 V1.0，可从文件名自动提取" /></el-form-item>
          <el-form-item label="类别"><el-select v-model="eb.bom_category" style="width:100%"><el-option label="电机类" value="电机类" /><el-option label="电控类" value="电控类" /><el-option label="其他类" value="其他类" /></el-select></el-form-item>
          <el-form-item label="项目"><el-select v-model="eb.project_id" style="width:100%" filterable clearable><el-option v-for="p in projs" :key="p.id" :label="p.name" :value="p.id" /></el-select></el-form-item>
          <el-form-item label="状态"><el-select v-model="eb.status" style="width:100%"><el-option label="有效" value="有效" /><el-option label="失效" value="失效" /></el-select></el-form-item>
        </el-form>
        <template #footer><el-button @click="showEditDlg=false">取消</el-button><el-button type="primary" @click="saveBomEdit" :loading="ebIng">保存</el-button></template>
      </el-dialog>
    </el-tab-pane>

    <!-- ═══ TAB 3: 成本趋势 ═══ -->
    <el-tab-pane label="成本趋势" name="cost">
      <div v-loading="costLoading" style="min-height:200px">
        <div class="cost-stats">
          <div class="cost-stat"><div class="cost-num">{{ costData?.summary?.bom_count ?? 0 }}</div><div class="cost-label">BOM 数量</div></div>
          <div class="cost-stat"><div class="cost-num">¥{{ fmtCost(costData?.summary?.total_material) }}</div><div class="cost-label">总物料成本</div></div>
          <div class="cost-stat"><div class="cost-num">¥{{ fmtCost(costData?.summary?.total_cost) }}</div><div class="cost-label">总成本(含{{ (costData?.overhead_rate ?? 0.1) * 100 }}%制造估算)</div></div>
          <el-button size="small" style="margin-left:auto" @click="loadCostTrend" :loading="costLoading">刷新</el-button>
        </div>

        <!-- Bar comparison chart -->
        <div v-if="costData?.items?.length" class="cost-chart">
          <div v-for="it in costData.items" :key="it.id" class="cost-bar-row">
            <div class="cost-bar-label" :title="it.bom_name">
              <b>{{ it.product_name }}</b>
              <span v-if="it.product_model" class="t-muted2">/ {{ it.product_model }}</span>
              <span v-if="it.version" class="t-muted2">/ {{ it.version }}</span>
            </div>
            <div class="cost-bar-track">
              <div class="cost-bar" style="background:#3b82f6" :style="{ width: pct(it.material_cost) }"></div>
              <div class="cost-bar cost-bar-total" :style="{ width: pct(it.total_cost) }"></div>
            </div>
            <div class="cost-bar-val">
              <span class="v-material">¥{{ fmtCost(it.material_cost) }}</span>
              <span class="v-total">¥{{ fmtCost(it.total_cost) }}</span>
            </div>
          </div>
          <div class="cost-legend">
            <span><i style="background:#3b82f6"></i>物料成本</span>
            <span><i style="background:#10b981"></i>总成本</span>
          </div>
        </div>
        <div v-else-if="!costLoading" class="empty-hint2">暂无BOM数据，请先在产品BOM管理上传BOM</div>

        <!-- Detail table -->
        <el-table :data="costData?.items || []" size="small" stripe style="margin-top:14px">
          <el-table-column prop="product_name" label="产品名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="product_model" label="产品型号" width="110" show-overflow-tooltip />
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="date" label="日期" width="100" />
          <el-table-column prop="rows" label="行数" width="70" />
          <el-table-column prop="rows_priced" label="有价行" width="70" />
          <el-table-column label="物料成本" width="120" align="right">
            <template #default="{row}">¥{{ fmtCost(row.material_cost) }}</template>
          </el-table-column>
          <el-table-column label="制造估算" width="110" align="right">
            <template #default="{row}">¥{{ fmtCost(row.overhead_cost) }}</template>
          </el-table-column>
          <el-table-column label="总成本" width="120" align="right">
            <template #default="{row}"><b>¥{{ fmtCost(row.total_cost) }}</b></template>
          </el-table-column>
        </el-table>
      </div>
    </el-tab-pane>

    <!-- ═══ TAB 2: 研发物料档案 ═══ -->
    <el-tab-pane label="研发物料档案" name="a">
      <div style="margin-bottom:12px;display:flex;gap:8px">
        <el-input v-model="s2" placeholder="搜索..." size="small" clearable style="width:180px" @keyup.enter="loadA" />
        <el-select v-model="fc2" size="small" placeholder="类别" clearable style="width:130px" @change="loadA">
          <el-option v-for="c in ['电机类物料','电控类物料','其他类物料']" :key="c" :label="c" :value="c" />
        </el-select>
        <el-button size="small" @click="loadA" :loading="la">搜索</el-button>
        <el-button size="small" type="primary" @click="editA(null)">+ 新增</el-button>
        <el-button size="small" @click="exportA">导出</el-button>
        <el-button size="small" @click="showImpA=true">导入</el-button>
        <el-button size="small" @click="downloadMatTemplate">下载模板</el-button>
        <el-button size="small" type="danger" @click="batchDelA" :disabled="!selAIds.length">批量删除({{selAIds.length}})</el-button>
      </div>
      <el-table :data="alist" size="small" stripe v-loading="la" max-height="calc(100vh - 260px)" @selection-change="s=>selAIds=s.map(x=>x.id)">
        <el-table-column type="selection" width="35" />
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column prop="code" label="编码" width="120" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="spec" label="规格" width="130" show-overflow-tooltip />
        <el-table-column prop="unit" label="单位" width="55" />
        <el-table-column prop="supplier" label="供应商" width="110" show-overflow-tooltip />
        <el-table-column prop="unit_price" label="单价" width="75"><template #default="{row}">{{ row.unit_price||'-' }}</template></el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{row}">
            <el-button link size="small" @click="editA(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click="delA(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Edit dialog -->
      <el-dialog v-model="showEdA" :title="editingA?'编辑物料':'新增物料'" width="500px">
        <el-form :model="fa" label-width="70px" size="small">
          <el-form-item label="类别"><el-select v-model="fa.category" style="width:100%"><el-option v-for="c in ['电机类物料','电控类物料','其他类物料']" :key="c" :label="c" :value="c" /></el-select></el-form-item>
          <el-row :gutter="8"><el-col :span="12"><el-form-item label="编码"><el-input v-model="fa.code" /></el-form-item></el-col><el-col :span="12"><el-form-item label="名称"><el-input v-model="fa.name" /></el-form-item></el-col></el-row>
          <el-form-item label="规格"><el-input v-model="fa.spec" /></el-form-item>
          <el-row :gutter="8"><el-col :span="8"><el-form-item label="单位"><el-input v-model="fa.unit" /></el-form-item></el-col><el-col :span="8"><el-form-item label="数量"><el-input-number v-model="fa.qty" :min="1" style="width:100%" /></el-form-item></el-col><el-col :span="8"><el-form-item label="单价"><el-input v-model="fa.unit_price" /></el-form-item></el-col></el-row>
          <el-row :gutter="8"><el-col :span="12"><el-form-item label="供应商"><el-input v-model="fa.supplier" /></el-form-item></el-col><el-col :span="12"><el-form-item label="供应商料号"><el-input v-model="fa.supplier_code" /></el-form-item></el-col></el-row>
          <el-form-item label="备注"><el-input v-model="fa.notes" type="textarea" :rows="2" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="showEdA=false">取消</el-button><el-button type="primary" @click="saveA" :loading="sa">保存</el-button></template>
      </el-dialog>

      <!-- Import dialog -->
      <el-dialog v-model="showImpA" title="批量导入物料" width="550px">
        <div style="margin-bottom:10px;display:flex;align-items:center;gap:10px">
          <span style="font-size:13px">物料类别：</span>
          <el-radio-group v-model="icat" size="small">
            <el-radio-button value="电机类物料">电机类</el-radio-button>
            <el-radio-button value="电控类物料">电控类</el-radio-button>
            <el-radio-button value="其他类物料">其他类</el-radio-button>
          </el-radio-group>
        </div>
        <div style="border:2px solid #409EFF;border-radius:8px;padding:12px;margin-bottom:8px;background:#ecf5ff">
          <div style="font-weight:bold;font-size:14px;margin-bottom:8px">📋 粘贴导入（推荐）</div>
          <div style="font-size:12px;color:#666;margin-bottom:6px">1. 打开Excel/WPS → 全选Ctrl+A → 复制Ctrl+C</div>
          <div style="font-size:12px;color:#666;margin-bottom:6px">2. 在下框按 Ctrl+V 粘贴</div>
          <el-input v-model="pt" type="textarea" :rows="6" placeholder="Ctrl+V 粘贴表格数据到此处..." style="margin-top:4px;font-family:Consolas,monospace;font-size:12px" />
          <el-button type="primary" size="small" style="margin-top:8px" @click="doPasteA" :disabled="!pt.trim()">确认粘贴导入</el-button>
        </div>
        <div style="text-align:center;color:#999;margin:8px 0;font-size:12px">— 或 —</div>
        <el-upload :http-request="doImpA" :show-file-list="true" drag>
          <div style="padding:12px">📁 上传文件（CSV格式推荐）</div>
        </el-upload>
        <div v-if="ir" style="margin-top:8px;font-size:13px;white-space:pre-wrap" :style="{color:ir.includes('成功')?'#22c55e':'#ef4444'}">{{ ir }}</div>
      </el-dialog>
    </el-tab-pane>
  </el-tabs>

  <!-- ECN变更单 dialog -->
  <el-dialog v-model="showEcn" title="📋 ECN工程变更通知单" width="600px">
    <div v-if="ecnR" style="font-size:14px;line-height:1.8">
      <div style="margin-bottom:12px"><b>编号:</b> {{ecnR.ecn_number}}</div>
      <div style="margin-bottom:12px"><b>标题:</b> {{ecnR.title}}</div>
      <div style="margin-bottom:12px"><b>变更描述:</b> {{ecnR.change_description}}</div>
      <div style="margin-bottom:12px"><b>影响物料:</b> 新增{{ecnR.affected_items?.added}}项 / 删除{{ecnR.affected_items?.removed}}项 / 不变{{ecnR.affected_items?.common}}项</div>
      <div style="margin-bottom:12px"><b>影响评估:</b> {{ecnR.impact}}</div>
      <div style="margin-bottom:12px"><b>审批级别:</b> <el-tag :type="ecnR.approval_level==='紧急'?'danger':ecnR.approval_level==='重要'?'warning':'info'" size="small">{{ecnR.approval_level}}</el-tag></div>
      <div style="font-size:11px;color:var(--text-muted)">生成方式: {{ecnR.source==='ai'?'AI自动生成':'规则生成'}}</div>
    </div>
    <template #footer>
      <el-button @click="showEcn=false">关闭</el-button>
      <el-button type="primary" @click="copyEcn" v-if="ecnR">复制全文</el-button>
    </template>
  </el-dialog>

  <!-- BOM成本估算 dialog -->
  <el-dialog v-model="showCost" title="💰 BOM成本估算" width="700px">
    <div v-if="costR" style="margin-bottom:12px;font-size:16px;font-weight:bold;text-align:center" :style="{color:'#22c55e'}">{{costR.summary}}</div>
    <el-table v-if="costR?.items?.length" :data="costR.items" size="small" max-height="400" border stripe>
      <el-table-column prop="row" label="行" width="45" />
      <el-table-column prop="name" label="物料名称" width="130" />
      <el-table-column prop="spec" label="规格" width="120" />
      <el-table-column prop="qty" label="数量" width="55" />
      <el-table-column prop="unit_price" label="历史单价" width="90">
        <template #default="{row}"><span :style="{color:row.has_price?'':'#ccc'}">{{row.has_price?'¥'+row.unit_price:'无数据'}}</span></template>
      </el-table-column>
      <el-table-column prop="total_price" label="小计" width="90">
        <template #default="{row}"><span :style="{fontWeight:row.has_price?'bold':''}">{{row.has_price?'¥'+row.total_price:'-'}}</span></template>
      </el-table-column>
      <el-table-column prop="supplier" label="参考供应商" width="100" />
    </el-table>
    <template #footer><el-button @click="showCost=false">关闭</el-button></template>
  </el-dialog>

  <!-- BOM智能问答 dialog -->
  <el-dialog v-model="showAsk" title="💬 BOM智能问答" width="600px">
    <div style="margin-bottom:12px;max-height:350px;overflow-y:auto" ref="askChatBox">
      <div v-for="(m,i) in askMsgs" :key="i" style="margin-bottom:8px">
        <div v-if="m.role==='user'" style="text-align:right"><span style="background:#e6f4ff;padding:8px 12px;border-radius:12px 12px 0 12px;font-size:13px;display:inline-block;max-width:80%">{{m.text}}</span></div>
        <div v-else style="text-align:left"><span style="background:#f0fdf4;padding:8px 12px;border-radius:12px 12px 12px 0;font-size:13px;display:inline-block;max-width:90%;white-space:pre-wrap">{{m.text}}</span></div>
      </div>
    </div>
    <div style="display:flex;gap:8px">
      <el-input v-model="askQ" placeholder="例: 最贵的5个料是什么？哪些电容用的最多？" @keyup.enter="doAsk" size="small" style="flex:1" />
      <el-button type="primary" size="small" @click="doAsk" :loading="askIng" :disabled="!askQ.trim()">提问</el-button>
    </div>
    <div style="margin-top:8px;font-size:11px;color:var(--text-muted)">快捷提问:
      <el-button link size="small" @click="askQ='最贵的5个物料是什么';doAsk()">最贵TOP5</el-button>
      <el-button link size="small" @click="askQ='哪些物料没有供应商';doAsk()">缺供应商</el-button>
      <el-button link size="small" @click="askQ='数量最多的物料是什么';doAsk()">数量最多</el-button>
      <el-button link size="small" @click="askQ='总共有多少颗电容';doAsk()">电容统计</el-button>
    </div>
    <template #footer><el-button @click="showAsk=false">关闭</el-button></template>
  </el-dialog>

  <!-- BOM检查结果 dialog -->
  <el-dialog v-model="showCheck" title="🔍 BOM完整性检查" width="650px">
    <div v-if="checkR" style="text-align:center;margin-bottom:16px">
      <div style="font-size:48px;font-weight:bold" :style="{color:checkR.score>=80?'#22c55e':checkR.score>=50?'#e6a23c':'#ef4444'}">{{checkR.score}}分</div>
      <div style="font-size:14px;color:var(--text-muted)">{{checkR.summary}}</div>
    </div>
    <el-table v-if="checkR?.issues?.length" :data="checkR.issues" size="small" max-height="400" border>
      <el-table-column prop="row" label="行" width="50" />
      <el-table-column prop="field" label="字段" width="90">
        <template #default="{row}"><el-tag :type="row.severity==='error'?'danger':row.severity==='warning'?'warning':'info'" size="small">{{row.field}}</el-tag></template>
      </el-table-column>
      <el-table-column prop="msg" label="问题描述" min-width="200" />
      <el-table-column prop="severity" label="级别" width="65">
        <template #default="{row}"><span :style="{color:row.severity==='error'?'#ef4444':row.severity==='warning'?'#e6a23c':'#909399'}">{{row.severity==='error'?'❌错误':row.severity==='warning'?'⚠️警告':'ℹ️提示'}}</span></template>
      </el-table-column>
    </el-table>
    <div v-else style="text-align:center;padding:32px;color:var(--text-muted)">✅ 未发现问题，BOM完整度良好</div>
    <template #footer><el-button @click="showCheck=false">关闭</el-button></template>
  </el-dialog>

  <!-- 转换工具BOM dialog -->
  <el-dialog v-model="showConv" title="🔧 硬件工具BOM → 平台模板" width="700px">
    <div style="text-align:center;padding:20px;border:2px dashed #ddd;border-radius:8px;cursor:pointer;margin-bottom:12px" @click="convFileInput?.click()">
      <div style="font-size:36px;margin-bottom:8px">📄</div>
      <div style="font-size:14px">上传Altium/Cadence/KiCad导出的BOM文件</div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:4px">CSV或Excel格式，自动映射到平台模板</div>
    </div>
    <input type="file" ref="convFileInput" accept=".csv,.xlsx,.xls" style="display:none" @change="doConvBom" />
    <div v-if="convMsg" style="font-size:12px;margin-bottom:8px;white-space:pre-line">{{ convMsg }}</div>
    <el-table v-if="convItems.length" :data="convItems" size="small" max-height="350" border>
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column prop="name" label="物料名称" width="140" />
      <el-table-column prop="spec" label="规格型号" width="130" />
      <el-table-column prop="position" label="元件位置" width="80" />
      <el-table-column prop="package" label="封装" width="80" />
      <el-table-column prop="qty" label="数量" width="50" />
      <el-table-column prop="brand" label="品牌" width="80" />
      <el-table-column prop="supplier" label="供应商" width="90" />
      <el-table-column prop="note" label="备注" min-width="100" />
    </el-table>
    <template #footer>
      <el-button @click="showConv=false;convItems=[];convMsg=''">取消</el-button>
      <el-button v-if="convItems.length" type="primary" @click="saveConvBom" :loading="convIng">💾 保存为BOM</el-button>
    </template>
  </el-dialog>

  <!-- BOM File Attachments Dialog -->
  <el-dialog v-model="showBomFiles" :title="'📎 文件管理 - ' + bomFilesName" width="650px">
    <div v-if="bomFiles.length===0" style="text-align:center;color:var(--text-muted);padding:20px">暂无附件</div>
    <div v-for="f in bomFiles" :key="f.id" style="display:flex;align-items:center;padding:8px 12px;margin-bottom:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;gap:10px">
      <img v-if="isBomImage(f.filename)" :src="bomThumbUrl(f.id)" style="width:48px;height:48px;object-fit:cover;border-radius:4px;border:1px solid var(--border);cursor:pointer;flex-shrink:0" @click="bomPreview(f.id)" @error="e=>e.target.style.display='none'" />
      <span v-else style="width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:var(--bg-hover);border-radius:4px;flex-shrink:0;font-size:20px">{{ bomFileIcon(f.filename) }}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px">{{ f.filename }}</span>
      <span style="color:var(--text-muted);font-size:11px;white-space:nowrap">{{ bomFormatSize(f.size) }}</span>
      <el-button link size="small" type="primary" @click="bomPreview(f.id)">预览</el-button>
      <el-button link size="small" @click="bomDownload(f.id, f.filename)">下载</el-button>
      <el-button link size="small" type="danger" @click="bomDelFile(f.id)">删除</el-button>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
      <input type="file" ref="bomFileInput" multiple @change="onBomFileChange" style="display:block" />
      <span style="font-size:11px;color:var(--text-muted)">上传后可直接预览，确认无误后点「导入为BOM数据」</span>
    </div>
    <template #footer>
      <el-button v-if="bomFiles.length" type="success" size="small" @click="importFromAttachment" :loading="bomImporting">📥 从附件导入为BOM数据</el-button>
      <el-button @click="showBomFiles=false">关闭</el-button>
    </template>
  </el-dialog>
</div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const tab = ref('p')

// ── TAB 1: BOM Lists ──
const plist = ref([]); const lp = ref(false)
const showUp = ref(false); const upFile = ref(null); const upPreview = ref(null)
const upIng = ref(false); const upError = ref('')
const showPaste = ref(false); const selIds = ref([]); const batchOp = ref('')
const s1 = ref(''); const bomCat = ref(''); const filtProj = ref(null)
const upPaste = ref(''); const upPastePreview = ref(null); const upMsg = ref('')
const upPreviewRows = ref([]); const upPreviewColWarn = ref('')
const upRowMeta = ref([])  // original column count per preview row
const upParsedItems = ref(null) // cache: { headers, items } ready for save
const ocrIng = ref(false)
const showCmpDlg = ref(false); const cmpR = ref(null)
const showGenDlg = ref(false); const genTpl = ref('standard_motor'); const genPid = ref(null); const genIng = ref(false)
const genTab = ref('tpl'); const genFile = ref(null); const genFileRef = ref(null)
const genItems = ref([]); const genStatus = ref(''); const genOk = ref(false); const genRaw = ref('')
async function doGenFromDrawing(e) {
  genFile.value = (e.target.files||[])[0]||null; if (!genFile.value) return
  genIng.value = true; genStatus.value = '正在识别图纸...'; genItems.value = []
  const fd = new FormData(); fd.append('file', genFile.value)
  try {
    const r = await api.post('/bom/from-drawing', fd, { timeout: 180000 })
    const items = r.data?.items
    genItems.value = Array.isArray(items) ? items.filter(i=>i&&i.name) : []
    genRaw.value = r.data?.raw_answer || ''
    genOk.value = genItems.value.length > 0
    genStatus.value = genOk.value ? `✅ 识别到 ${genItems.value.length} 项物料，已自动展开核对表格（行数=识别数量），请核对后保存` : ('❌ 未识别到物料: ' + (r.data?.error||'AI未返回有效结果'))
    if (genOk.value) openDraftFromGen()
  } catch(ex) { genStatus.value = '识别失败: ' + (ex?.response?.data?.detail||ex.message); genOk.value = false }
  genIng.value = false
}
function genItemToObj(it) {
  return { cat: it?.category||'', code: it?.code||'', name: it?.name||'', spec: it?.spec||'', position: it?.position||'',
           package: it?.package||'', brand: it?.brand||'', unit: it?.unit||'个', qty: it?.qty||'1',
           supplier: it?.supplier||'', price: it?.price||'', note: it?.note||'' }
}
function openDraftFromGen() {
  if (!genItems.value.length) return
  draftSrc.value = 'drawing'
  draftItems.value = genItems.value.map(genItemToObj)
  draftName.value = '图纸识别BOM-' + new Date().toISOString().slice(0,16)
  draftCat.value = ''
  showDraftDlg.value = true
}
const showAscDlg = ref(false); const ascPid = ref(null); const ascIng = ref(false)
// BOM check
const showCheck = ref(false); const checkR = ref(null); const checkIng = ref(false)
async function checkBom(row) {
  checkIng.value = true; showCheck.value = true; checkR.value = null
  try {
    const r = await api.get(`/bom-lists/${row.id}/check`)
    checkR.value = r.data
  } catch(e) { checkR.value = {score:0,summary:'检查失败: '+(e?.response?.data?.detail||e.message),issues:[]} }
  checkIng.value = false
}

// BOM ECN
const showEcn = ref(false); const ecnR = ref(null); const ecnIng = ref(false)
async function genEcn() {
  const sel = selIds.value; if (sel.length !== 2) return
  ecnIng.value = true; showEcn.value = true; ecnR.value = null
  try {
    const r = await api.post('/bom-lists/compare/generate-ecn', {bom_a:sel[0], bom_b:sel[1]})
    ecnR.value = r.data
  } catch(e) { ecnR.value = {title:'生成失败',change_description:(e?.response?.data?.detail||e.message)} }
  ecnIng.value = false
}
function copyEcn() {
  const e = ecnR.value; if (!e) return
  const text = `[${e.ecn_number}] ${e.title}\n变更描述: ${e.change_description}\n影响评估: ${e.impact}\n审批级别: ${e.approval_level}`
  navigator.clipboard.writeText(text).then(()=>ElMessage.success('已复制'))
}

// BOM Cost
const showCost = ref(false); const costR = ref(null)
async function estCost(row) {
  showCost.value = true; costR.value = null
  try {
    const r = await api.get(`/bom-lists/${row.id}/estimate-cost`)
    costR.value = r.data
  } catch(e) { costR.value = {summary:'估算失败: '+(e?.response?.data?.detail||e.message),items:[]} }
}

// BOM Q&A
const showAsk = ref(false); const askQ = ref(''); const askIng = ref(false); const askMsgs = ref([]); const askBomId = ref(null)
function openAsk(row) {
  showAsk.value = true; askBomId.value = row.id; askQ.value = ''; askMsgs.value = []
}
async function doAsk() {
  const q = askQ.value.trim(); if (!q || !askBomId.value) return
  askMsgs.value.push({role:'user',text:q})
  askQ.value = ''; askIng.value = true
  try {
    const r = await api.post(`/bom-lists/${askBomId.value}/ask`, {question:q})
    askMsgs.value.push({role:'bot',text:r.data?.answer||'无回复'})
  } catch(e) { askMsgs.value.push({role:'bot',text:'提问失败: '+(e?.response?.data?.detail||e.message)}) }
  askIng.value = false
}

// Convert tool BOM
const showConv = ref(false); const convItems = ref([]); const convMsg = ref(''); const convIng = ref(false); const convFileInput = ref(null)
async function doConvBom(e) {
  const file = (e.target.files||[])[0]; if (!file) return
  convIng.value = true; convMsg.value = '正在处理...'
  convItems.value = []
  const fd = new FormData(); fd.append('file', file)
  try {
    const r = await api.post('/bom/convert-tool-bom', fd, { timeout: 120000 })
    const items = r.data?.items
    if (Array.isArray(items)) {
      convItems.value = items
    } else if (items && typeof items === 'object') {
      convItems.value = Object.values(items).filter(v => v && typeof v === 'object')
    }
    const cm = r.data?.column_map || {}
    const dh = r.data?.debug_headers || []
    const dr = r.data?.debug_first_rows || []
    const raw = r.data?.raw_answer || ''
    convMsg.value = [
      convItems.value.length ? `✅ ${convItems.value.length}行` : '⚠️ 无数据',
      `列映射(${Object.keys(cm).length}): ${JSON.stringify(cm)}`,
      `表头(${dh.length}): ${JSON.stringify(dh)}`,
      `前${dr.length}行: ${JSON.stringify(dr)}`,
      `原始: ${raw}`,
      convItems.value.length ? `首行数据: ${JSON.stringify(convItems.value[0])}` : '',
    ].join('\n')
  } catch(ex) { convMsg.value = '失败: ' + (ex?.response?.data?.detail||ex.message||ex.toString()) }
  convIng.value = false
  e.target.value = ''
}
async function saveConvBom() {
  if (!convItems.value.length) return
  convIng.value = true
  const headers = ["序号","物料编码","物料名称","规格型号","元件位置","封装","品牌","单位","数量","供应商","参考单价","备注"]
  const rows = convItems.value.map(item => [item.seq||'',item.code||'',item.name||'',item.spec||'',item.position||'',item.package||'',item.brand||'',item.unit||'个',item.qty||'1',item.supplier||'',item.price||'',item.note||''])
  try {
    await api.post('/bom/lists', { name: '转换BOM-' + new Date().toISOString().slice(0,16), headers, items: rows })
    ElMessage.success('已保存')
    showConv.value = false; convItems.value = []; convMsg.value = ''
    await refreshP()
  } catch(e) { ElMessage.error('保存失败') }
  convIng.value = false
}
const showEditDlg = ref(false); const eb = ref({}); const ebIng = ref(false)
const projs = ref([])
const showDet = ref(false); const det = ref(null); const detEdit = ref(null); const detSaving = ref(false)

function openUpload() { showUp.value = true }
function downloadTemplate() {
  if (internalMeta.value?.uploaded) {
    api.get('/bom-lists/internal-template', { responseType: 'blob' }).then(r => {
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = internalMeta.value.filename || '内部BOM模板.xls'; a.click()
      URL.revokeObjectURL(url)
    }).catch(() => ElMessage.error('下载失败'))
    return
  }
  const cat = bomCat.value || '电机类'
  api.get('/bom-lists/template', { params: { bom_category: cat }, responseType: 'blob' }).then(r => {
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url; a.download = `BOM模板-${cat}.xlsx`; a.click()
    URL.revokeObjectURL(url)
  }).catch(() => ElMessage.error('下载失败'))
}
async function loadProjs() { try { projs.value = (await api.get('/bom/projects')).data || [] } catch { projs.value = [] } }
async function refreshP() { lp.value = true; try { const p = {}; if (bomCat.value) p.category = bomCat.value; if (s1.value.trim()) p.search = s1.value.trim(); if (filtProj.value) p.project_id = filtProj.value; plist.value = (await api.get('/bom-lists', { params: p })).data || [] } catch { plist.value = [] }; lp.value = false }

// ── TAB 3: Cost trend ──
const costData = ref(null)
const costLoading = ref(false)
const maxCost = computed(() => Math.max(1, ...(costData.value?.items || []).map(x => x.total_cost)))
function pct(v) { return Math.round((v || 0) / maxCost.value * 100) + '%' }
function fmtCost(v) {
  if (v === null || v === undefined) return '0'
  const n = Number(v)
  if (!isFinite(n)) return '0'
  return n >= 100000 ? (n / 10000).toFixed(1) + '万' : n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
async function loadCostTrend() {
  costLoading.value = true
  try { costData.value = (await api.get('/bom-lists/cost-trend')).data } catch { costData.value = { items: [], summary: {} } }
  costLoading.value = false
}

function onNativeFilePick(e) {
  const f = e.target.files?.[0]
  if (!f) return
  upFile.value = f; upPreview.value = null; upError.value = ''
}

const upMeta = reactive({
  bomName: '', productModel: '', version: '', releaseDate: '',
  designer: '', reviewer: '', approver: '', projectName: '', customer: '',
  bomCategory: '', notes: ''
})
const upMetaFields = [
  {key:'bomName',label:'BOM名称',placeholder:'如：西山CM02-BOM'},
  {key:'productName',label:'产品名称',placeholder:'如：电机控制器总成'},
  {key:'productModel',label:'产品型号',placeholder:'如：CM02'},
  {key:'version',label:'版本号',placeholder:'如：V1.0'},
  {key:'releaseDate',label:'发布日期',placeholder:'如：2026-07-20'},
  {key:'designer',label:'设计人员',placeholder:''},
  {key:'reviewer',label:'审核人员',placeholder:''},
  {key:'approver',label:'批准人员',placeholder:''},
  {key:'projectName',label:'项目名称',placeholder:''},
  {key:'customer',label:'客户名称',placeholder:''},
  {key:'bomCategory',label:'BOM类别',placeholder:'电机类/电控类/其他类'},
  {key:'notes',label:'备注',placeholder:''},
]

// Scan for rows matching template meta patterns
const META_MAP = { '产品名称':'productName','产品型号':'productModel','版本号':'version','发布日期':'releaseDate',
  '设计人员':'designer','审核人员':'reviewer','批准人员':'approver',
  '项目名称':'projectName','客户名称':'customer','备注':'notes' }
const HEADER_KEYS = ['物料编码','物料名称','规格型号','序号','元件位置','封装','品牌','单位','数量','供应商','参考单价','备注']

function _autoDetectMeta() {
  const text = upPaste.value; if (!text.trim()) return
  const lines = _mergeLines(text).map(l => l.trim()).filter(Boolean)
  for (const line of lines) {
    const cells = line.split('\t').map(c => c.trim())
    for (let i = 0; i < cells.length; i += 2) {
      const label = cells[i]; const val = cells[i+1]||''
      if (META_MAP[label] && !upMeta[META_MAP[label]]) { upMeta[META_MAP[label]] = val }
    }
  }
}

function autoDetectMeta() {
  _autoDetectMeta()
  ElMessage.success('已识别 BOM 信息')
}

// Normalize and merge lines with too-few tabs (multi-line cells from Excel)
function _mergeLines(rawText) {
  // Handle Windows \r\n and normalize
  const rawLines = rawText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  if (rawLines.length < 2) return rawLines
  // Phase 1: find header row to get expected tab count
  let expectedTabs = 0, headerIdx = -1
  for (let i = 0; i < Math.min(rawLines.length, 20); i++) {
    const tabs = (rawLines[i].match(/\t/g) || []).length
    const cells = rawLines[i].split('\t').map(c => c.trim())
    const matchCount = HEADER_KEYS.filter(k => cells.includes(k)).length
    if (matchCount >= 2 && tabs > expectedTabs) { expectedTabs = tabs; headerIdx = i }
  }
  if (expectedTabs < 5) return rawLines  // not tabular data
  // Phase 2: merge continuation lines (very conservative: < 20% of expected tabs)
  const threshold = Math.max(1, Math.floor(expectedTabs * 0.2))
  const merged = []
  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i]
    const tabs = (line.match(/\t/g) || []).length
    const trimmed = line.trim()
    // Only merge if: line has very few tabs AND previous line was a full-width data row
    if (tabs < threshold && merged.length > 0 && trimmed && i > headerIdx) {
      const prev = merged[merged.length - 1]
      const prevTabs = (prev.match(/\t/g) || []).length
      if (prevTabs >= expectedTabs - 2) {
        merged[merged.length - 1] = prev + ' ' + trimmed
        continue
      }
    }
    merged.push(line)
  }
  return merged
}

// Smart parse: find the actual table header row, skipping template meta rows
function _smartParse(pasteText) {
  const rawLines = _mergeLines(pasteText)
  const lines = rawLines.map(l => l.trim()).filter(Boolean)
  if (lines.length < 2) return { headers: [], dataRows: 0, headerRow: -1 }
  let headerRow = -1
  let bestScore = 0
  for (let i = 0; i < Math.min(lines.length, 15); i++) {
    const cells = lines[i].split('\t').map(c => c.trim())
    const matchCount = HEADER_KEYS.filter(k => cells.includes(k)).length
    const nonEmpty = cells.filter(c => c).length
    const score = matchCount * 10 + nonEmpty
    if (matchCount >= 2 && score > bestScore) { headerRow = i; bestScore = score }
  }
  // Fallback: if no header pattern found, use row with most non-empty cells
  if (headerRow < 0) {
    let maxCells = 0
    for (let i = 0; i < Math.min(lines.length, 15); i++) {
      const n = lines[i].split('\t').filter(c => c.trim()).length
      if (n > maxCells) { maxCells = n; headerRow = i }
    }
  }
  const headers = headerRow >= 0 ? lines[headerRow].split('\t').map(c => c.trim()) : []
  // Count data rows (non-empty rows after header)
  const dataRows = headerRow >= 0 ? lines.slice(headerRow + 1).filter(l => {
    return l.split('\t').map(c => c.trim()).some(c => c)
  }).length : 0
  return { headers, dataRows, headerRow }
}

// Intercept paste to read HTML table structure from clipboard (avoids newline-in-cell issues)
function onPasteNative(e) {
  const html = (e.clipboardData || window.clipboardData)?.getData?.('text/html')
  if (!html) return // no HTML, let default text paste happen
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const rows = doc.querySelectorAll('tr')
  if (rows.length < 2) return // not a table, fall back to text
  e.preventDefault() // stop default text paste
  const lines = []
  for (const tr of rows) {
    const cells = [...tr.querySelectorAll('td, th')].map(td => (td.textContent || '').replace(/\t/g, ' ').replace(/\n/g, ' ').trim())
    if (cells.some(c => c)) lines.push(cells.join('\t'))
  }
  if (lines.length < 2) return
  upPaste.value = lines.join('\n')
  onUpPasteInput()
}

function onUpPasteInput() {
  const parsed = _smartParse(upPaste.value)
  upPastePreview.value = parsed.headerRow >= 0 ? parsed : null
  upPreviewRows.value = []
  upPreviewColWarn.value = ''
  upParsedItems.value = null
  if (parsed.headerRow >= 0) {
    const lines = _mergeLines(upPaste.value).map(l => l.trim()).filter(Boolean)
    const nCols = parsed.headers.length
    const items = []; const rowMeta = []  // track original column count per row
    for (let i = parsed.headerRow + 1; i < lines.length; i++) {
      const cells = lines[i].split('\t').map(c => c.trim())
      if (!cells.some(c => c)) continue
      const origLen = cells.length
      // Pad to header width (right-pad only)
      while (cells.length < nCols) cells.push('')
      if (cells.length > nCols) cells.length = nCols
      items.push(cells)
      rowMeta.push(origLen)
      upPreviewRows.value.push([...cells])
    }
    upParsedItems.value = { headers: parsed.headers, items }
    upRowMeta.value = rowMeta
    // Only warn about rows with MORE columns than header (will be truncated)
    const overSize = rowMeta.map((c, i) => c > nCols ? i + 1 : 0).filter(Boolean)
    if (overSize.length) {
      upPreviewColWarn.value = `⚠ ${overSize.length} 行超出表头列数，尾部将被截断: 行 ${overSize.slice(0,10).join(',')}`
    } else if (items.length > 0) {
      upPreviewColWarn.value = `${items.length} 行数据，已自动补到${nCols}列，可保存`
    }
  }
  if (parsed.headerRow > 2) _autoDetectMeta()
}

function pasteFillDown() {
  if (!upPaste.value.trim()) return
  const parsed = _smartParse(upPaste.value)
  if (parsed.headerRow < 0) { ElMessage.warning('未找到表头'); return }
  // Use same line processing as _smartParse: merge + trim + filter empty
  const allLines = _mergeLines(upPaste.value).map(l => l.trim()).filter(Boolean)
  const metaLines = allLines.slice(0, parsed.headerRow + 1)
  const dataLines = allLines.slice(parsed.headerRow + 1)
  const nCols = parsed.headers.length
  const rows = dataLines.map(l => l.split('\t').map(c => c.trim()))
  for (const r of rows) { while (r.length < nCols) r.push('') }
  for (let col = 0; col < nCols; col++) {
    let lastVal = ''
    for (let i = 0; i < rows.length; i++) {
      const val = rows[i][col]
      if (val) lastVal = val
      else if (lastVal) rows[i][col] = lastVal
    }
  }
  // Replace paste text with clean version (meta + filled data)
  upPaste.value = [...metaLines, ...rows.map(r => r.join('\t'))].join('\n')
  onUpPasteInput()
  ElMessage.success('已向下填充空值')
}

function fixMultiline() {
  // Apply _mergeLines and replace paste text with merged result
  const merged = _mergeLines(upPaste.value)
  upPaste.value = merged.join('\n')
  onUpPasteInput()
  const before = upPaste.value.split('\n').length
  ElMessage.success(`已合并换行: ${merged.length} 行 (合并了单元格内换行)`)
}

async function onOcrFile(e) {
  const f = e.target.files?.[0]
  if (!f) return
  ocrIng.value = true; upMsg.value = 'OCR识别中...'
  try {
    const fd = new FormData(); fd.append('file', f)
    const r = await api.post('/bom-lists/ocr-to-table', fd, { timeout: 120000 })
    if (r.data?.text) {
      upPaste.value = r.data.text
      onUpPasteInput()
      upMsg.value = `识别到 ${r.data.rows} 行，可编辑后保存`
    } else {
      upMsg.value = r.data?.message || '未识别到文字'
    }
  } catch (e) { upMsg.value = 'OCR失败: ' + (e?.response?.data?.detail || e?.message || '') }
  ocrIng.value = false
}

async function doPasteUpload() {
  if (!upPaste.value.trim()) { upMsg.value = '请先粘贴数据'; return }
  if (!upMeta.bomName && !upMeta.productModel) { upMsg.value = '请在右侧填写 BOM名称 或 产品型号'; return }
  // Use cached parsed data (same as preview) to guarantee consistency
  if (!upParsedItems.value || !upParsedItems.value.items.length) {
    upMsg.value = '请先粘贴数据并检查预览'; return
  }
  upIng.value = true; upMsg.value = ''
  try {
    const { headers, items } = upParsedItems.value
    const r = await api.post('/bom-lists', {
      name: upMeta.bomName || (upMeta.productModel + ' BOM'),
      status: '有效',
      headers, items,
      project_name: upMeta.projectName || '',
      notes: upMeta.notes || '',
      meta: {
        product_name: upMeta.productName,
        product_model: upMeta.productModel,
        version: upMeta.version,
        release_date: upMeta.releaseDate,
        designer: upMeta.designer,
        reviewer: upMeta.reviewer,
        approver: upMeta.approver,
        customer: upMeta.customer,
        bom_category: upMeta.bomCategory,
      }
    })
    upMsg.value = `已保存: ${items.length}行, ${headers.length}列`
    upPaste.value = ''; upPastePreview.value = null; upPreviewRows.value = []; upPreviewColWarn.value = ''; upParsedItems.value = null
    for (const f of upMetaFields) { upMeta[f.key] = '' }
    await refreshP()
  } catch (e) { upMsg.value = '保存失败: ' + (e?.response?.data?.detail || e?.message || '') }
  upIng.value = false
}

async function doUpload() {
  if (!upFile.value) return
  upIng.value = true
  const file = upFile.value
  try {
    // Step 1: Create empty BOM list with version auto-extracted
    const name = file.name.replace(/\.(xlsx?|xls|csv)$/i, '')
    // Auto-extract version from filename: V4.3, v1.0, _V2.1, (2.0), etc.
    const vMatch = file.name.match(/[Vv]\s*(\d+[\d.]*)|[\(（]\s*(\d+[\d.]*)\s*[\)）]/)
    const version = vMatch ? `V${vMatch[1] || vMatch[2]}` : ''
    const { data: bom } = await api.post('/bom-lists', { name, status: '有效', meta: { version } })
    const listId = bom.id

    // Step 2: Upload file as attachment (raw binary — same as Product Tech)
    const fd1 = new FormData(); fd1.append('files', file)
    await api.post(`/bom-lists/${listId}/files`, fd1)

    // Step 3: Get the uploaded file ID
    const { data: files } = await api.get(`/bom-lists/${listId}/files`)
    const excelFiles = files.filter(f => /\.(xlsx?|xls|csv)$/i.test(f.filename))
    const excelFile = excelFiles.sort((a, b) => (b.id || 0) - (a.id || 0))[0]  // latest by ID
    if (!excelFile) { ElMessage.error('上传成功但未找到可导入文件'); upIng.value = false; return }

    // Step 4: Import from the saved attachment (openpyxl direct — no encoding issues)
    const { data: result } = await api.post(`/bom-lists/${listId}/files/${excelFile.id}/import`)
    ElMessage.success(`导入 ${result.item_count} 行`)
    showUp.value = false; upFile.value = null; upPreview.value = null; await refreshP()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e?.response?.data?.detail || e?.message || '网络错误'))
  }
  upIng.value = false
}

async function viewDetail(id) {
  try { det.value = (await api.get(`/bom-lists/${id}`)).data; detEdit.value = null; showDet.value = true } catch { ElMessage.error('加载失败') }
}

function startEdit() {
  if (!det.value) return
  detEdit.value = (det.value.items||[]).map(row => [...row])
}

function fillDownEdit() {
  if (!detEdit.value) return
  const rows = detEdit.value.map(r => [...r]) // deep copy
  const maxCols = Math.max(...rows.map(r => r.length))
  for (const r of rows) { while (r.length < maxCols) r.push('') }
  for (let col = 0; col < maxCols; col++) {
    let lastVal = ''
    for (let rowIdx = 0; rowIdx < rows.length; rowIdx++) {
      const val = rows[rowIdx][col]
      if (val) lastVal = val
      else if (lastVal) rows[rowIdx][col] = lastVal
    }
  }
  detEdit.value = rows
}

async function saveDetEdit() {
  if (!det.value || !detEdit.value) return
  detSaving.value = true
  try {
    await api.put(`/bom-lists/${det.value.id}`, { items: detEdit.value })
    det.value.items = detEdit.value.map(row => [...row])
    detEdit.value = null
    ElMessage.success('已保存')
  } catch (e) { ElMessage.error('保存失败') }
  detSaving.value = false
}

function exportOne(id) {
  // 模板样式 .xlsx: 表头信息区在上 + 物料表格在下
  api.get(`/bom-lists/${id}/export-xlsx`, { responseType: 'blob' }).then(r => {
    const b = new Blob([r.data], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
    const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `BOM_${id}.xlsx`; a.click()
  }).catch(() => ElMessage.error('导出失败'))
}

async function delOne(id) {
  try { await ElMessageBox.confirm('删除？','确认',{type:'warning'}); await api.delete(`/bom-lists/${id}`); ElMessage.success('已删除'); await refreshP() }
  catch(e) { if(e!=='cancel') ElMessage.error('删除失败') }
}

// ── BOM对比 ──
async function openCmp() {
  try { cmpR.value = (await api.post('/bom-lists/compare', { id_a: selIds.value[0], id_b: selIds.value[1] })).data; showCmpDlg.value = true }
  catch(e) { ElMessage.error('对比失败') }
}

// ── 自动生成 ──
const itFileRef = ref(null); const addFileRef = ref(null)
const internalMeta = ref({ uploaded: false })
const internalTpls = ref([])      // [{id,name,filename,sheets,groups,is_default}]
const draftTplId = ref('default') // 保存时绑定的模板 id
const pendingTplName = ref('')
const curTplMeta = computed(() => {
  const id = genTpl.value?.startsWith('internal') ? (genTpl.value.split(':')[1] || 'default') : null
  return internalTpls.value.find(t => t.id === id) || null
})
async function loadInternalTpls() {
  try { internalTpls.value = (await api.get('/bom-lists/internal-templates')).data?.templates || [] }
  catch { internalTpls.value = [] }
  internalMeta.value = { uploaded: internalTpls.value.length > 0,
                         filename: internalTpls.value.find(t => t.is_default)?.filename || '' }
}
function currentTplId() { return (genTpl.value || '').startsWith('internal') ? (genTpl.value.split(':')[1] || 'default') : 'default' }
async function uploadInternalTpl(e) {
  const f = e.target.files?.[0]; if (!f) return
  const fd = new FormData(); fd.append('file', f)
  genIng.value = true
  try {
    const r = await api.post('/bom-lists/internal-template/' + currentTplId(), fd)
    await loadInternalTpls()
    ElMessage.success('模板已更新: ' + (r.data?.filename || ''))
  } catch(err) { ElMessage.error('上传失败: ' + (err?.response?.data?.detail || err?.message || '')) }
  genIng.value = false
  e.target.value = ''
}
function addTplClick() {
  ElMessageBox.prompt('请输入新模板名称(可留空)', '新增内部模板',
    { inputPlaceholder: '如: 高压电机BOM', confirmButtonText: '选择文件', cancelButtonText: '取消' })
    .then(({ value }) => { pendingTplName.value = (value || '').trim(); addFileRef.value?.click() })
    .catch(() => {})
}
async function addTplFile(e) {
  const f = e.target.files?.[0]; if (!f) return
  const fd = new FormData(); fd.append('file', f); fd.append('name', pendingTplName.value || '')
  genIng.value = true
  try {
    const r = await api.post('/bom-lists/internal-templates', fd)
    genTpl.value = 'internal:' + r.data.id
    await loadInternalTpls()
    ElMessage.success('新增模板成功')
  } catch(err) { ElMessage.error('新增失败: ' + (err?.response?.data?.detail || err?.message || '')) }
  genIng.value = false
  e.target.value = ''
}
function openGen() { genTpl.value = 'standard_motor'; genPid.value = null; loadInternalTpls(); showGenDlg.value = true }
const showDraftDlg = ref(false); const draftItems = ref([]); const draftName = ref(''); const draftCat = ref('')
const draftInfo = ref([]) // 内部模板表头信息(按模板布局: type/label/row/col/value)
// 按模板原始布局分组: 标题行 + 字段按 row 分组(组内按 col 排位) + 说明文字
const infoTitle = computed(() => draftInfo.value.find(f => f.type === 'title') || null)
const infoStd = computed(() => draftInfo.value.filter(f => f.type === 'std'))
const infoGroups = computed(() => {
  const by = {}
  for (const f of draftInfo.value) if (f.type === 'field') (by[f.row] ||= []).push(f)
  return Object.keys(by).sort((a, b) => a - b).map(r => by[r].sort((a, b) => (a.col || 0) - (b.col || 0)))
})
const infoNotes = computed(() => draftInfo.value.filter(f => f.type === 'note'))
const infoTitleDet = computed(() => (det.value?.info || []).find(f => f.type === 'title') || null)
const infoStdDet = computed(() => (det.value?.info || []).filter(f => f.type === 'std'))
const infoGroupsDet = computed(() => {
  const by = {}
  for (const f of det.value?.info || []) if (f.type === 'field') (by[f.row] ||= []).push(f)
  return Object.keys(by).sort((a, b) => a - b).map(r => by[r].sort((a, b) => (a.col || 0) - (b.col || 0)))
})
const infoNotesDet = computed(() => (det.value?.info || []).filter(f => f.type === 'note'))
const draftSrc = ref('template') // template | drawing | internal
const GEN_HEADERS = ["序号","物料编码","物料名称","规格型号","元件位置","封装","品牌","单位","数量","供应商","参考单价","备注"]
const INTERNAL_HEADERS = ["类别","序号","物料编码","物料名称","零件图号","材料、牌号、规格、技术条件","单位","用量","备注"]
function rowToObj(row) {
  return { code: row[1]||'', name: row[2]||'', spec: row[3]||'', position: row[4]||'', package: row[5]||'',
           brand: row[6]||'', unit: row[7]||'个', qty: row[8]||'1', supplier: row[9]||'', price: row[10]||'', note: row[11]||'' }
}
function internalRowToObj(row) {
  return { cat: row[0]||'主材', code: row[2]||'', name: row[3]||'', part_no: row[4]||'',
           spec: row[5]||'', unit: row[6]||'pcs', qty: row[7]||'1', note: row[8]||'' }
}
function addDraftRow() {
  if (draftSrc.value === 'internal')
    draftItems.value.push({ cat:'主材', code:'', name:'', part_no:'', spec:'', unit:'pcs', qty:'1', note:'' })
  else if (draftSrc.value === 'drawing')
    draftItems.value.push({ cat:'', code:'', name:'', spec:'', position:'', package:'', brand:'', unit:'个', qty:'1', supplier:'', price:'', note:'' })
  else
    draftItems.value.push({ code:'', name:'', spec:'', position:'', package:'', brand:'', unit:'个', qty:'1', supplier:'', price:'', note:'' })
}
function delDraftRow(i) { draftItems.value.splice(i, 1) }
async function doGen() {
  genIng.value = true
  try {
    const isInt = genTpl.value.startsWith('internal')
    const tplId = isInt ? (genTpl.value.split(':')[1] || 'default') : undefined
    const r = await api.post('/bom/generate', { template: genTpl.value, template_id: tplId, preview: true, items: genItems.value.length ? genItems.value : undefined })
    draftSrc.value = isInt ? 'internal' : 'template'
    draftTplId.value = isInt ? tplId : 'default'
    draftItems.value = (r.data?.items || []).map(isInt ? internalRowToObj : rowToObj)
    draftInfo.value = (r.data?.info || []).map(f => ({ ...f, label: f.label || '', value: f.value || '' }))
    draftName.value = r.data?.name || 'BOM-' + new Date().toISOString().slice(0,16)
    draftCat.value = r.data?.bom_category || (genTpl.value.replace('standard_','')+'类')
    showDraftDlg.value = true
  } catch(e) { ElMessage.error('生成失败: ' + (e?.response?.data?.detail || e?.message || '')) }
  genIng.value = false
}
async function saveDraft() {
  if (!draftItems.value.length) { ElMessage.warning('清单为空，请先添加物料'); return }
  genIng.value = true
  try {
    let rows, headers
    if (draftSrc.value === 'internal') {
      headers = INTERNAL_HEADERS
      rows = draftItems.value.map((o) => [
        o.cat||'主材', '', o.code||'', o.name||'', o.part_no||'',
        o.spec||'', o.unit||'pcs', String(o.qty||1), o.note||''
      ]).filter(r => r[3] || r[2]).map((r, i) => (r[1] = String(i+1), r))
    } else if (draftSrc.value === 'drawing') {
      headers = ["序号","类别","物料编码","物料名称","规格型号","元件位置","封装","品牌","单位","数量","供应商","参考单价","备注"]
      rows = draftItems.value.map((o, i) => [
        String(i+1), o.cat||'', o.code||'', o.name||'', o.spec||'', o.position||'',
        o.package||'', o.brand||'', o.unit||'个', String(o.qty||1),
        o.supplier||'', o.price||'', o.note||''
      ]).filter(r => r[3] || r[2])
    } else {
      headers = GEN_HEADERS
      rows = draftItems.value.map((o, i) => [
        String(i+1), o.code||'', o.name||'', o.spec||'', o.position||'',
        o.package||'', o.brand||'', o.unit||'个', String(o.qty||1),
        o.supplier||'', o.price||'', o.note||''
      ]).filter(r => r[2] || r[1])
    }
    if (!rows.length) { ElMessage.warning('请至少填写一项物料的名称或编码'); genIng.value = false; return }
    const r = await api.post('/bom-lists', {
      name: draftName.value, headers: headers, items: rows,
      bom_category: draftCat.value || '',
      info: draftSrc.value === 'internal' ? draftInfo.value : [],
      meta: draftSrc.value === 'internal' ? { template_id: draftTplId.value } : {}
    })
    if (genPid.value) { try { await api.put('/bom-lists/batch/associate-project', { ids: [r.data.id], project_id: genPid.value }) } catch {} }
    ElMessage.success('BOM已保存')
    showDraftDlg.value = false
    await refreshP()
  } catch(e) { ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || '')) }
  genIng.value = false
}

// ── 关联项目 ──
function openAsc() { ascPid.value = null; showAscDlg.value = true }
function quickAsc(row) {
  selIds.value = [row.id]
  openAsc()
}
async function doAsc() {
  if (!ascPid.value) { ElMessage.warning('请选择项目'); return }
  ascIng.value = true
  try { await api.put('/bom-lists/batch/associate-project', { ids: selIds.value, project_id: ascPid.value }); ElMessage.success(selIds.value.length > 1 ? `已移动 ${selIds.value.length} 个BOM` : '已关联'); showAscDlg.value = false; selIds.value = []; await refreshP() }
  catch(e) { ElMessage.error('操作失败') }
  ascIng.value = false
}

// ── 状态切换 ──
async function toggleBomStatus(row) {
  const ns = row.status === '有效' ? '失效' : '有效'
  try { await api.put(`/bom-lists/${row.id}`, { status: ns }); row.status = ns } catch { ElMessage.error('操作失败') }
}

function editBom(row) {
  eb.value = {
    id: row.id, name: row.name, version: row.meta?.version || row.version || '',
    product_name: row.meta?.product_name || row.product_name || '',
    product_model: row.meta?.product_model || row.product_model || '',
    project_id: row.project_id, status: row.status || '有效',
    bom_category: row.meta?.bom_category || row.bom_category || ''
  }
  showEditDlg.value = true
}
async function saveBomEdit() {
  ebIng.value = true
  try {
    const payload = { ...eb.value }
    // Put version/product into meta
    if (payload.version !== undefined || payload.product_name !== undefined || payload.product_model !== undefined) {
      payload.meta = { ...(payload.meta || {}) }
      if (payload.version !== undefined) payload.meta.version = payload.version
      if (payload.product_name !== undefined) payload.meta.product_name = payload.product_name
      if (payload.product_model !== undefined) payload.meta.product_model = payload.product_model
    }
    await api.put(`/bom-lists/${eb.value.id}`, payload)
    ElMessage.success('已保存'); showEditDlg.value = false; await refreshP()
  }
  catch(e) { ElMessage.error('保存失败') }
  ebIng.value = false
}

async function batchExpire() {
  try { await ElMessageBox.confirm(`将 ${selIds.value.length} 个BOM设为失效？`, '确认', { type: 'warning' }) }
  catch(e) { if (e === 'cancel' || e?.message === 'cancel') return }
  for (const id of selIds.value) { try { await api.put(`/bom-lists/${id}`, { status: '失效' }) } catch {} }
  ElMessage.success('已设为失效'); selIds.value = []; await refreshP()
}

async function batchDeleteBom() {
  try { await ElMessageBox.confirm(`确认删除选中的 ${selIds.value.length} 个BOM？此操作不可恢复`, '批量删除', { type: 'warning' }) }
  catch { return }
  try {
    await api.post('/bom-lists/batch-delete', { ids: selIds.value })
    ElMessage.success(`已删除 ${selIds.value.length} 个BOM`)
    selIds.value = []; await refreshP()
  } catch(e) { ElMessage.error('删除失败: ' + (e?.response?.data?.detail || e?.message || '')) }
}

async function doBatchOp(op) {
  batchOp.value = ''
  if (!selIds.value.length) return
  if (op === 'delete') await batchDeleteBom()
  else if (op === 'expire') await batchExpire()
  else if (op === 'move') openAsc()
}

// ── TAB 2: Archive ──
const alist = ref([]); const la = ref(false); const selAIds = ref([])
const s2 = ref(''); const fc2 = ref('')
const showEdA = ref(false); const editingA = ref(false); const fa = ref({}); const sa = ref(false)
const showImpA = ref(false); const pt = ref(''); const ir = ref(''); const icat = ref('电机类物料')

async function loadA() {
  la.value = true
  try {
    const p = {}
    if (fc2.value) p.category = fc2.value
    if (s2.value.trim()) p.search = s2.value.trim()
    alist.value = (await api.get('/bom/materials', { params: p })).data || []
  } catch { alist.value = [] }
  la.value = false
}

function downloadMatTemplate() {
  const a = document.createElement('a')
  a.href = '/api/bom/materials/template'
  a.download = '物料档案导入模板.xlsx'; a.click()
}

function editA(row) {
  editingA.value = !!row
  fa.value = row ? { ...row } : { category: '电机类物料', code: '', name: '', spec: '', unit: '个', qty: 1, supplier: '', supplier_code: '', price: '', notes: '' }
  showEdA.value = true
}

async function saveA() {
  if (!fa.value.name) { ElMessage.warning('请输入名称'); return }
  sa.value = true
  try {
    if (editingA.value) await api.put(`/bom/materials/${fa.value.id}`, fa.value)
    else await api.post('/bom/materials', fa.value)
    ElMessage.success('已保存'); showEdA.value = false; await loadA()
  } catch (e) { ElMessage.error('保存失败: ' + (e?.response?.data?.detail||e?.message||'')) }
  sa.value = false
}

async function delA(id) {
  try { await ElMessageBox.confirm('删除？','确认',{type:'warning'}); await api.delete(`/bom/materials/${id}`); ElMessage.success('已删除'); await loadA() }
  catch(e) { if(e!=='cancel') ElMessage.error('删除失败') }
}

async function batchDelA() {
  if (!selAIds.value.length) return
  try {
    await ElMessageBox.confirm('确认删除选中的 '+selAIds.value.length+' 条物料？','批量删除',{type:'warning'})
    await api.post('/bom/materials/batch-delete', {ids: selAIds.value})
    ElMessage.success('已删除 '+selAIds.value.length+' 条')
    selAIds.value = []; await loadA()
  } catch(e) { if(e!=='cancel') ElMessage.error('删除失败') }
}

function exportA() {
  const d = alist.value.map(x => [x.code,x.name,x.spec,x.unit,x.qty,x.supplier,x.supplier_code,x.unit_price,x.notes])
  const csv = ['编码,名称,规格,单位,数量,供应商,供应商料号,单价,备注'].concat(d.map(r=>r.map(c=>`"${c||''}"`).join(','))).join('\n')
  const b = new Blob(['﻿'+csv], {type:'text/csv'}); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = '物料档案.csv'; a.click()
}

async function doImpA({ file }) {
  ir.value = '正在上传: ' + (file.name || '未知文件') + '...';
  let hex = '??'
  try {
    const buf = await file.slice(0, 4).arrayBuffer()
    hex = Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('')
  } catch(e) {}

  try {
    const fd = new FormData(); fd.append('file',file); fd.append('category',icat.value)
    const r = await api.post('/bom/import',fd)
    const sample = r.data?.sample || ''
    const dbg = r.data?.debug || {}
    ir.value = `[${file.name}] 导入成功，${r.data?.count||0} 条` + (sample ? ` · 示例: ${sample}` : '')
    if (dbg.first_row) ir.value += `\n首行数据: ${JSON.stringify(dbg.first_row)}`
    ElMessage.success(ir.value)
    await loadA()
  } catch(e) {
    ir.value = `导入失败(hex:${hex}): ` + (e?.response?.data?.detail || e?.message || e?.toString?.() || '未知错误')
    ElMessage.error(ir.value)
  }
}

async function doPasteA() {
  const lines = pt.value.split('\n').filter(l=>l.trim())
  if (lines.length<2) { ElMessage.warning('需要表头+1行'); return }
  try {
    const text = lines.join('\n')
    await api.post('/bom/import-paste', {text: text, category: icat.value})
    ElMessage.success('导入成功'); pt.value=''; await loadA()
  } catch(e) { ElMessage.error('导入失败: ' + (e?.response?.data?.detail||e?.message||'')) }
}

// ── BOM File Attachments ──
const showBomFiles = ref(false)
const bomFiles = ref([])
const bomFilesId = ref('')
const bomFilesName = ref('')
const bomThumbCache = ref({})
const bomFileInput = ref(null)

async function openBomFiles(row) {
  bomFilesId.value = row.id
  bomFilesName.value = row.name || row.product_model || row.id
  try {
    const r = await api.get(`/bom-lists/${row.id}/files`)
    bomFiles.value = r.data || []
    loadBomThumbs()
  } catch { bomFiles.value = [] }
  showBomFiles.value = true
}

async function loadBomThumbs() {
  for (const f of bomFiles.value) {
    if (!isBomImage(f.filename) || bomThumbCache.value[f.id]) continue
    try {
      const res = await api.get(`/bom-lists/${bomFilesId.value}/files/${f.id}/preview`, { responseType: 'blob' })
      bomThumbCache.value[f.id] = URL.createObjectURL(res.data)
    } catch {}
  }
}

function bomThumbUrl(fid) { return bomThumbCache.value[fid] || '' }

function isBomImage(fn) { return /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(fn || '') }

function bomFileIcon(fn) {
  const ext = (fn || '').split('.').pop().toLowerCase()
  return { pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊', ppt: '📽️', zip: '📦', rar: '📦', dwg: '📐', dxf: '📐', mp4: '🎬', mp3: '🎵' }[ext] || '📎'
}

function bomFormatSize(bytes) {
  if (!bytes) return '0 B'
  let s = bytes, i = 0
  while (s >= 1024 && i < 3) { s /= 1024; i++ }
  return s.toFixed(i === 0 ? 0 : 1) + ' ' + ['B', 'KB', 'MB', 'GB'][i]
}

async function bomPreview(fid) {
  try {
    const res = await api.get(`/bom-lists/${bomFilesId.value}/files/${fid}/preview`, { responseType: 'blob' })
    const ct = res.headers['content-type'] || 'text/html; charset=utf-8'
    const blob = new Blob([res.data], { type: ct })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch { ElMessage.error('预览失败') }
}

function bomDownload(fid, filename) {
  api.get(`/bom-lists/${bomFilesId.value}/files/${fid}/download`, { responseType: 'blob' }).then(res => {
    const a = document.createElement('a'); a.href = URL.createObjectURL(res.data); a.download = filename; a.click()
  }).catch(() => ElMessage.error('下载失败'))
}

async function bomDelFile(fid) {
  try {
    await api.delete(`/bom-lists/${bomFilesId.value}/files/${fid}`)
    if (bomThumbCache.value[fid]) { URL.revokeObjectURL(bomThumbCache.value[fid]); delete bomThumbCache.value[fid] }
    const r = await api.get(`/bom-lists/${bomFilesId.value}/files`)
    bomFiles.value = r.data || []
    ElMessage.success('已删除')
  } catch { ElMessage.error('删除失败') }
}

const bomImporting = ref(false)

async function importFromAttachment() {
  if (bomFiles.value.length === 0) return
  const excelFile = bomFiles.value.find(f => /\.(xlsx?|xls|csv)$/i.test(f.filename))
  if (!excelFile) { ElMessage.warning('没有可导入的Excel/CSV附件'); return }
  if (!bomFilesId.value) { ElMessage.warning('BOM ID未设置'); return }
  bomImporting.value = true
  try {
    const url = `/bom-lists/${bomFilesId.value}/files/${excelFile.id}/import`
    const r = await api.post(url)
    const cnt = r.data?.item_count || 0
    if (cnt === 0) {
      ElMessage.warning('导入成功但未解析到数据行，请检查文件内容')
    } else {
      ElMessage.success(`导入完成: ${cnt} 条`)
    }
    showBomFiles.value = false
    // Refresh the BOM list table
    await refreshP()
    // Also refresh detail view if it's open for this BOM
    if (showDet.value && det.value?.id === bomFilesId.value) {
      det.value = (await api.get(`/bom-lists/${bomFilesId.value}`)).data
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || '未知错误'
    ElMessage.error('导入失败: ' + detail)
  }
  bomImporting.value = false
}

async function onBomFileChange() {
  const files = Array.from(bomFileInput.value?.files || [])
  if (!files.length) { ElMessage.warning('未选择文件'); return }
  if (!bomFilesId.value) { ElMessage.warning('BOM ID未设置'); return }
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  try {
    const r = await api.post(`/bom-lists/${bomFilesId.value}/files`, fd)
    if (r.data?.ok) {
      const fresh = await api.get(`/bom-lists/${bomFilesId.value}/files`)
      bomFiles.value = Array.isArray(fresh.data) ? fresh.data : (fresh.data?.files || [])
      loadBomThumbs()
      if (bomFileInput.value) bomFileInput.value.value = ''
      ElMessage.success(`已上传 ${files.length} 个文件`)
    } else {
      ElMessage.error('上传返回异常')
    }
  } catch (e) {
    ElMessage.error('上传失败: ' + (e?.response?.data?.detail || e?.message || '网络错误'))
  }
}

onMounted(() => { refreshP(); loadA(); loadProjs(); loadInternalTpls() })
watch(tab, (v) => { if (v === 'a') loadA(); if (v === 'cost') loadCostTrend() })
</script>

<style scoped>
.bom-v2 { max-width: 1500px; }

/* Cost trend */
.cost-stats { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.cost-stat { background: var(--bg-white); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 18px; min-width: 150px; }
.cost-num { font-size: 20px; font-weight: 700; color: #3b82f6; }
.cost-label { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.cost-chart { background: var(--bg-white); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.cost-bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.cost-bar-label { width: 220px; font-size: 13px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cost-bar-label b { font-weight: 600; }
.t-muted2 { color: var(--text-muted); font-weight: 400; font-size: 12px; }
.cost-bar-track { flex: 1; height: 16px; background: var(--bg); border-radius: 8px; position: relative; overflow: hidden; }
.cost-bar { position: absolute; top: 0; left: 0; height: 50%; border-radius: 0; }
.cost-bar-total { top: 50%; background: #10b981 !important; }
.cost-bar-val { width: 150px; flex-shrink: 0; font-size: 12px; display: flex; flex-direction: column; line-height: 1.35; }
.v-material { color: #3b82f6; }
.v-total { color: #10b981; font-weight: 600; }
.cost-legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.cost-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
.empty-hint2 { color: var(--text-muted); font-size: 13px; padding: 40px; text-align: center; }
</style>
