# API 参考（全量端点）

> 自动生成于 OpenAPI 规范（`GET /openapi.json`），共 **521 个端点、39 个模块**。认证方式：除注明外均需 `Authorization: Bearer <access_token>`。

| 模块 | 端点数 |
|---|--:|
| [AI](#ai) | 6 |
| [audit-logs](#audit-logs) | 1 |
| [auth](#auth) | 22 |
| [bom](#bom) | 21 |
| [bom-lists](#bom-lists) | 31 |
| [changes](#changes) | 14 |
| [client-communications](#client-communications) | 6 |
| [client-contacts](#client-contacts) | 4 |
| [clients](#clients) | 6 |
| [customer-portal](#customer-portal) | 8 |
| [dashboard](#dashboard) | 3 |
| [deliverables](#deliverables) | 15 |
| [departments](#departments) | 4 |
| [documents](#documents) | 13 |
| [export](#export) | 3 |
| [external](#external) | 14 |
| [files](#files) | 2 |
| [financials](#financials) | 6 |
| [gate-reviews](#gate-reviews) | 17 |
| [issue_risks](#issue_risks) | 8 |
| [knowledge](#knowledge) | 112 |
| [lookups](#lookups) | 23 |
| [milestones](#milestones) | 5 |
| [my-work](#my-work) | 1 |
| [ocr](#ocr) | 1 |
| [opportunities](#opportunities) | 5 |
| [plm](#plm) | 15 |
| [product-tech](#product-tech) | 18 |
| [projects](#projects) | 9 |
| [report-gen](#report-gen) | 17 |
| [reports](#reports) | 13 |
| [requirements](#requirements) | 10 |
| [risks](#risks) | 7 |
| [tasks](#tasks) | 5 |
| [team](#team) | 8 |
| [testing](#testing) | 26 |
| [training](#training) | 5 |
| [training-tasks](#training-tasks) | 9 |
| [其他](#其他) | 28 |

## AI

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/ai/config` | Get Ai Config |
| PUT | `/api/ai/config` | Update Ai Config |
| POST | `/api/ai/weekly-report` | Ai Weekly Report |
| POST | `/api/ai/analyze-risk` | Ai Analyze Risk |
| GET | `/api/ai/diagnose/{project_id}` | Ai Diagnose |
| POST | `/api/ai/chat` | Ai Chat |

## audit-logs

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/audit-logs` | List Audit Logs |

## auth

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/refresh` | Refresh Token |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Me |
| PUT | `/api/auth/password` | Change Password |
| GET | `/api/auth/users` | List Users |
| POST | `/api/auth/users` | Create User |
| GET | `/api/auth/name-map` | User Name Map |
| PUT | `/api/auth/users/{user_id}` | Update User |
| DELETE | `/api/auth/users/{user_id}` | Delete User |
| GET | `/api/auth/permission-roles` | List Permission Roles |
| POST | `/api/auth/permission-roles` | Create Permission Role |
| PUT | `/api/auth/permission-roles/{role_id}` | Update Permission Role |
| DELETE | `/api/auth/permission-roles/{role_id}` | Delete Permission Role |
| GET | `/api/auth/roles` | List Roles |
| GET | `/api/auth/permissions` | Get Permission Defs |
| GET | `/api/auth/my-permissions` | My Permissions |
| GET | `/api/auth/dingtalk-login-url` | Dingtalk Login Url |
| GET | `/api/auth/dingtalk-callback` | Dingtalk Callback |
| GET | `/api/auth/bind-dingtalk-url` | Bind Dingtalk Url |
| GET | `/api/auth/dingtalk-bind-callback` | Dingtalk Bind Callback |

## bom

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bom/lists` | List Bom Lists |
| POST | `/api/bom/lists` | Create Bom List |
| GET | `/api/bom/lists/{lid}` | Get Bom List |
| PUT | `/api/bom/lists/{lid}` | Update Bom List |
| DELETE | `/api/bom/lists/{lid}` | Delete Bom List |
| POST | `/api/bom/lists/import` | Import Bom File |
| POST | `/api/bom/lists/compare` | Compare Bom |
| PUT | `/api/bom/lists/batch/associate-project` | Batch Associate |
| GET | `/api/bom/lists/template` | Get Bom Template |
| GET | `/api/bom/materials/template` | Download Materials Template |
| GET | `/api/bom/materials` | List Materials |
| POST | `/api/bom/materials` | Create Material |
| PUT | `/api/bom/materials/{mid}` | Update Material |
| DELETE | `/api/bom/materials/{mid}` | Delete Material |
| POST | `/api/bom/materials/batch-delete` | Batch Delete Materials |
| POST | `/api/bom/import` | Import Materials |
| POST | `/api/bom/import-paste` | Import Materials Paste |
| GET | `/api/bom/projects` | Get Projects |
| POST | `/api/bom/generate` | Generate Bom |
| POST | `/api/bom/from-drawing` | Bom From Drawing |
| POST | `/api/bom/convert-tool-bom` | Convert Tool Bom |

## bom-lists

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bom-lists/internal-templates` | List Internal Templates |
| POST | `/api/bom-lists/internal-templates` | Create Internal Template |
| POST | `/api/bom-lists/internal-template/{tpl_id}` | Replace Internal Template |
| DELETE | `/api/bom-lists/internal-templates/{tpl_id}` | Delete Internal Template |
| GET | `/api/bom-lists/internal-template/meta` | Get Internal Template Meta |
| GET | `/api/bom-lists/internal-template` | Download Internal Template |
| GET | `/api/bom-lists` | List Bom Lists |
| POST | `/api/bom-lists` | Create Bom List |
| GET | `/api/bom-lists/template` | Download Template |
| GET | `/api/bom-lists/cost-trend` | Bom Cost Trend |
| GET | `/api/bom-lists/{list_id}` | Get Bom List |
| PUT | `/api/bom-lists/{list_id}` | Update Bom List |
| DELETE | `/api/bom-lists/{list_id}` | Delete Bom List |
| PUT | `/api/bom-lists/batch/associate-project` | Batch Associate Project |
| POST | `/api/bom-lists/batch-delete` | Batch Delete |
| POST | `/api/bom-lists/preview` | Preview File |
| POST | `/api/bom-lists/import` | Import Bom List |
| GET | `/api/bom-lists/{list_id}/export` | Export Bom List |
| GET | `/api/bom-lists/{list_id}/export-xlsx` | Export Bom List Xlsx |
| POST | `/api/bom-lists/compare` | Compare Bom Lists |
| POST | `/api/bom-lists/ocr-to-table` | Ocr To Table |
| GET | `/api/bom-lists/{list_id}/check` | Check Bom Completeness |
| POST | `/api/bom-lists/{list_id}/ask` | Ask Bom |
| GET | `/api/bom-lists/{list_id}/estimate-cost` | Estimate Bom Cost |
| POST | `/api/bom-lists/compare/generate-ecn` | Generate Ecn |
| POST | `/api/bom-lists/{list_id}/files` | Bom Upload Files |
| GET | `/api/bom-lists/{list_id}/files` | Bom List Files |
| GET | `/api/bom-lists/{list_id}/files/{file_id}/download` | Bom Download File |
| GET | `/api/bom-lists/{list_id}/files/{file_id}/preview` | Bom Preview File |
| POST | `/api/bom-lists/{list_id}/files/{file_id}/import` | Bom Import From Attachment |
| DELETE | `/api/bom-lists/{list_id}/files/{file_id}` | Bom Delete File |

## changes

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/changes` | List All Changes |
| GET | `/api/approvals/pending` | Pending Approvals |
| GET | `/api/projects/{project_id}/changes` | List Changes |
| POST | `/api/projects/{project_id}/changes` | Create Change |
| POST | `/api/changes/{change_id}/withdraw` | Withdraw Change |
| POST | `/api/changes/{change_id}/resubmit` | Resubmit Change |
| PUT | `/api/changes/{change_id}` | Update Change |
| DELETE | `/api/changes/{change_id}` | Delete Change |
| POST | `/api/changes/{change_id}/attachment` | Upload Change Attachment |
| GET | `/api/changes/{change_id}/attachment` | Download Change Attachment |
| DELETE | `/api/changes/{change_id}/attachment` | Delete Change Attachment |
| POST | `/api/changes/preview-attachment` | Preview Attachment Upload |
| POST | `/api/changes/signoffs/{signoff_id}/approve` | Approve Change Signoff |
| POST | `/api/changes/signoffs/{signoff_id}/reject` | Reject Change Signoff |

## client-communications

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/clients/{client_id}/communications` | List Communications |
| POST | `/api/clients/{client_id}/communications` | Create Communication |
| PUT | `/api/communications/{comm_id}` | Update Communication |
| DELETE | `/api/communications/{comm_id}` | Delete Communication |
| DELETE | `/api/communications/remove-image` | Delete Comm Image |
| POST | `/api/clients/{client_id}/communications/upload-images` | Upload Comm Images |

## client-contacts

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/clients/{client_id}/contacts` | List Contacts |
| POST | `/api/clients/{client_id}/contacts` | Create Contact |
| PUT | `/api/contacts/{contact_id}` | Update Contact |
| DELETE | `/api/contacts/{contact_id}` | Delete Contact |

## clients

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/clients/stats` | Client Stats |
| GET | `/api/clients` | List Clients |
| POST | `/api/clients` | Create Client |
| GET | `/api/clients/{client_id}/profile` | Client Profile |
| PUT | `/api/clients/{client_id}` | Update Client |
| DELETE | `/api/clients/{client_id}` | Delete Client |

## customer-portal

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/customer-access` | List Access |
| POST | `/api/admin/customer-access` | Create Access |
| DELETE | `/api/admin/customer-access/{access_id}` | Revoke Access |
| POST | `/api/portal/{access_code}/login` | Portal Login |
| GET | `/api/portal/{access_code}/project` | Portal Project |
| GET | `/api/portal/{access_code}/milestones` | Portal Milestones |
| GET | `/api/portal/{access_code}/deliverables` | Portal Deliverables |
| GET | `/api/portal/{access_code}/documents` | Portal Documents |

## dashboard

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/dashboard` | Dashboard |
| GET | `/api/dashboard/alerts` | Alerts |
| GET | `/api/dashboard/pending-reports` | Pending Reports |

## deliverables

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/deliverables` | List Deliverables |
| POST | `/api/projects/{project_id}/deliverables` | Create Deliverable |
| PUT | `/api/deliverables/{deliverable_id}` | Update Deliverable |
| DELETE | `/api/deliverables/{deliverable_id}` | Delete Deliverable |
| POST | `/api/deliverables/{deliverable_id}/upload-file` | Upload Deliverable File |
| GET | `/api/deliverables/{deliverable_id}/attachments` | List Deliverable Attachments |
| POST | `/api/deliverables/{deliverable_id}/attachments` | Upload Deliverable Attachment |
| DELETE | `/api/deliverables/{deliverable_id}/attachments/{att_id}` | Delete Deliverable Attachment |
| DELETE | `/api/deliverables/{deliverable_id}/file` | Delete Deliverable File |
| GET | `/api/projects/{project_id}/phase-gates` | List Phase Gates |
| PUT | `/api/phase-gates/{pg_id}` | Update Phase Gate |
| GET | `/api/phase-gates/{pg_id}/action-items` | List Action Items |
| POST | `/api/phase-gates/{pg_id}/action-items` | Create Action Item |
| PUT | `/api/action-items/{ai_id}` | Update Action Item |
| DELETE | `/api/action-items/{ai_id}` | Delete Action Item |

## departments

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/departments` | List Departments |
| POST | `/api/departments` | Create Department |
| PUT | `/api/departments/{dept_id}` | Update Department |
| DELETE | `/api/departments/{dept_id}` | Delete Department |

## documents

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/docs` | List Docs |
| POST | `/api/projects/{project_id}/docs` | Create Doc |
| GET | `/api/projects/{project_id}/doc-folders` | List Doc Folders |
| POST | `/api/projects/{project_id}/doc-folders` | Save Doc Folder |
| PUT | `/api/docs/{doc_id}` | Update Doc |
| DELETE | `/api/docs/{doc_id}` | Delete Doc |
| POST | `/api/docs/{doc_id}/deprecate` | Deprecate Doc |
| POST | `/api/docs/{doc_id}/replace` | Replace Doc |
| GET | `/api/docs/{doc_id}/preview` | Preview Doc |
| POST | `/api/projects/{project_id}/docs/batch` | Batch Operate Docs |
| POST | `/api/projects/{project_id}/docs/add-ref` | Add Doc Ref |
| GET | `/api/docs/browse-server` | Browse Server Dir |
| POST | `/api/projects/{project_id}/docs/import-server` | Import Server File |

## export

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/export/projects` | Export Projects |
| GET | `/api/export/projects/{project_id}/reports` | Export Reports |
| GET | `/api/export/projects/{project_id}/risks` | Export Risks |

## external

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/api-keys` | List Api Keys |
| POST | `/api/admin/api-keys` | Create Api Key |
| PUT | `/api/admin/api-keys/{key_id}` | Update Api Key |
| DELETE | `/api/admin/api-keys/{key_id}` | Revoke Api Key |
| GET | `/api/admin/webhooks` | List Webhooks |
| POST | `/api/admin/webhooks` | Create Webhook |
| PUT | `/api/admin/webhooks/{webhook_id}` | Update Webhook |
| DELETE | `/api/admin/webhooks/{webhook_id}` | Delete Webhook |
| POST | `/api/admin/webhooks/{webhook_id}/test` | Test Webhook |
| GET | `/api/external/projects` | Ext List Projects |
| GET | `/api/external/projects/{project_id}` | Ext Get Project |
| GET | `/api/external/milestones` | Ext Milestones |
| GET | `/api/external/risks` | Ext Risks |
| GET | `/api/external/health` | Ext Health |

## files

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/files/upload` | Upload File |
| GET | `/api/files/storage-stats` | Storage Stats |

## financials

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/financials/overview` | Financial Overview |
| GET | `/api/financials/projects` | Project Financials |
| GET | `/api/projects/{project_id}/transactions` | Project Transactions |
| POST | `/api/projects/{project_id}/transactions` | Create Transaction |
| DELETE | `/api/transactions/{trans_id}` | Delete Transaction |
| GET | `/api/report-center/{report_type}` | Generate Report |

## gate-reviews

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/gate-deliverable-standards` | List Standards |
| POST | `/api/gate-deliverable-standards` | Create Standard |
| PUT | `/api/gate-deliverable-standards/{std_id}` | Update Standard |
| DELETE | `/api/gate-deliverable-standards/{std_id}` | Delete Standard |
| GET | `/api/gate-deliverable-standards/{std_id}/template` | Standard Template |
| POST | `/api/gate-deliverable-standards/{std_id}/template` | Upload Standard Template |
| DELETE | `/api/gate-deliverable-standards/{std_id}/template` | Delete Standard Template |
| GET | `/api/gate-reviews/checklist` | Deliverable Checklist |
| GET | `/api/gate-reviews/action-items` | Cross Project Action Items |
| POST | `/api/gate-reviews/{pg_id}/initiate-signoff` | Initiate Signoff |
| POST | `/api/gate-reviews/{pg_id}/withdraw` | Withdraw Gate Signoff |
| GET | `/api/gate-reviews/my-signoffs` | My Signoffs |
| GET | `/api/gate-reviews/signoffs` | All Signoffs |
| POST | `/api/gate-reviews/signoffs/{signoff_id}/approve` | Approve Signoff |
| POST | `/api/gate-reviews/signoffs/{signoff_id}/reject` | Reject Signoff |
| DELETE | `/api/gate-reviews/signoffs/{signoff_id}` | Delete Signoff |
| GET | `/api/gate-reviews/history` | Gate History |

## issue_risks

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/issue-risks/summary` | Get Summary |
| GET | `/api/issue-risks/matrix` | Get Risk Matrix |
| GET | `/api/issue-risks` | List Issue Risks |
| POST | `/api/issue-risks` | Create Issue Risk |
| GET | `/api/issue-risks-projects` | List Projects For Dropdown |
| PUT | `/api/issue-risks/{item_id}` | Update Issue Risk |
| DELETE | `/api/issue-risks/{item_id}` | Delete Issue Risk |
| POST | `/api/issue-risks/extract` | Extract Risks From Reports |

## knowledge

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/knowledge/images/{doc_id}/{filename}` | Serve Image |
| POST | `/api/knowledge/upload` | Upload Document |
| POST | `/api/knowledge/upload-batch` | Batch Upload |
| GET | `/api/knowledge/documents` | List Documents |
| GET | `/api/knowledge/folders` | List Folders |
| POST | `/api/knowledge/folders` | Create Folder |
| GET | `/api/knowledge/tags` | List Tags |
| POST | `/api/knowledge/documents/{doc_id}/tags` | Add Doc Tag |
| PUT | `/api/knowledge/documents/{doc_id}` | Update Document |
| DELETE | `/api/knowledge/documents/{doc_id}` | Delete Document |
| GET | `/api/knowledge/documents/{doc_id}` | Get Document Full |
| POST | `/api/knowledge/documents/batch-delete` | Batch Delete Documents |
| POST | `/api/knowledge/vector-search` | Vector Search |
| POST | `/api/knowledge/ai-search` | Ai Search |
| POST | `/api/knowledge/ask-table` | Ask Table |
| GET | `/api/knowledge/categories` | Get Categories |
| POST | `/api/knowledge/categories` | Add Category |
| DELETE | `/api/knowledge/categories/{name}` | Delete Category |
| PUT | `/api/knowledge/categories/order` | Reorder Categories |
| POST | `/api/knowledge/re-vectorize` | Re Vectorize All |
| POST | `/api/knowledge/summarize` | Smart Summary |
| POST | `/api/knowledge/qa` | Enhanced Qa |
| GET | `/api/knowledge/sessions` | List Sessions |
| DELETE | `/api/knowledge/sessions/{session_id}` | Delete Session |
| GET | `/api/knowledge/config` | Get Config |
| PUT | `/api/knowledge/config` | Update Config |
| GET | `/api/knowledge/share-links` | List Share Links |
| POST | `/api/knowledge/share-links` | Create Share Link |
| PUT | `/api/knowledge/share-links/{share_id}` | Update Share Link |
| DELETE | `/api/knowledge/share-links/{share_id}` | Delete Share Link |
| POST | `/api/knowledge/generate-qa` | Generate Qa |
| GET | `/api/knowledge/qa-pairs` | List Qa Pairs |
| DELETE | `/api/knowledge/qa-pairs` | Clear Qa Pairs |
| POST | `/api/knowledge/report` | Generate Report |
| GET | `/api/knowledge/reports` | List Reports |
| POST | `/api/knowledge/documents/{doc_id}/view` | Log Doc View |
| GET | `/api/knowledge/recommend` | Recommend Docs |
| POST | `/api/knowledge/extract-points` | Extract Core Points |
| GET | `/api/knowledge/spaces` | List Spaces |
| POST | `/api/knowledge/spaces` | Create Space |
| PUT | `/api/knowledge/spaces/{space_id}` | Update Space |
| DELETE | `/api/knowledge/spaces/{space_id}` | Delete Space |
| GET | `/api/knowledge/spaces/{space_id}/members` | List Members |
| POST | `/api/knowledge/spaces/{space_id}/members` | Add Member |
| DELETE | `/api/knowledge/spaces/{space_id}/members/{target_id}` | Remove Member |
| GET | `/api/knowledge/spaces/{space_id}/stats` | Space Stats |
| POST | `/api/knowledge/quick-overview` | Quick Overview |
| GET | `/api/knowledge/spaces/{space_id}/documents` | List Space Documents |
| GET | `/api/knowledge/shared-with-me` | List Shared With Me |
| GET | `/api/knowledge/documents/{doc_id}/shares` | List Document Shares |
| POST | `/api/knowledge/documents/{doc_id}/share` | Share Document |
| DELETE | `/api/knowledge/documents/{doc_id}/shares/{user_id}` | Remove Document Share |
| GET | `/api/knowledge/users/search` | Search Users |
| POST | `/api/knowledge/documents/{doc_id}/send-to-kb` | Send To Knowledge Base |
| GET | `/api/knowledge/members` | List Kb Members |
| POST | `/api/knowledge/members` | Add Kb Member |
| DELETE | `/api/knowledge/members/{user_id}` | Remove Kb Member |
| GET | `/api/knowledge/users/list` | List All Users |
| GET | `/api/knowledge/folders/{path}/members` | List Folder Members |
| POST | `/api/knowledge/folders/{path}/members` | Add Folder Member |
| DELETE | `/api/knowledge/folders/{path}/members/{user_id}` | Remove Folder Member |
| GET | `/api/knowledge/folder-tree` | Get Folder Tree |
| PUT | `/api/knowledge/folders/{path}` | Rename Folder |
| DELETE | `/api/knowledge/folders/{path}` | Delete Folder |
| POST | `/api/knowledge/folders/move` | Move Folder |
| POST | `/api/knowledge/documents/{doc_id}/move` | Move Document |
| POST | `/api/knowledge/documents/batch-move` | Batch Move Documents |
| POST | `/api/knowledge/folders/move-to-space` | Move Folder To Space |
| POST | `/api/knowledge/documents/{doc_id}/permission` | Set Doc Permission |
| GET | `/api/knowledge/activity` | Get Activity |
| POST | `/api/knowledge/activity-log` | Log User Activity |
| GET | `/api/knowledge/graph` | Knowledge Graph |
| GET | `/api/knowledge/preview-file/{doc_id}` | Preview File Html |
| GET | `/api/knowledge/download/{doc_id}` | Download Document |
| GET | `/api/knowledge/documents/{doc_id}/versions` | Doc Versions |
| POST | `/api/knowledge/documents/{doc_id}/save-version` | Save Doc Version |
| GET | `/api/knowledge/health` | Knowledge Health |
| POST | `/api/knowledge/export` | Export Knowledge |
| POST | `/api/knowledge/tags/merge` | Merge Tags |
| POST | `/api/knowledge/reprocess-ocr` | Reprocess Ocr |
| POST | `/api/knowledge/import-url` | Import Url |
| POST | `/api/knowledge/qa-web` | Qa With Web Search |
| GET | `/api/knowledge/external-sources` | List External Sources |
| POST | `/api/knowledge/external-sources` | Add External Source |
| PUT | `/api/knowledge/external-sources/{src_id}` | Update External Source |
| DELETE | `/api/knowledge/external-sources/{src_id}` | Delete External Source |
| POST | `/api/knowledge/external-sources/{src_id}/sync` | Sync External Source |
| GET | `/api/knowledge/dingtalk-config` | Get Dingtalk Config |
| PUT | `/api/knowledge/dingtalk-config` | Update Dingtalk Config |
| GET | `/api/knowledge/documents/{doc_id}/links` | Get Doc Links |
| GET | `/api/knowledge/documents/{doc_id}/backlinks` | Get Doc Backlinks |
| GET | `/api/knowledge/my-documents` | List My Documents |
| PUT | `/api/knowledge/documents/{doc_id}/visibility` | Toggle Doc Visibility |
| GET | `/api/knowledge/notes` | List Notes |
| POST | `/api/knowledge/notes` | Create Note |
| PUT | `/api/knowledge/notes/{note_id}` | Update Note |
| DELETE | `/api/knowledge/notes/{note_id}` | Delete Note |
| POST | `/api/knowledge/clip-url` | Clip Url |
| GET | `/api/knowledge/bookmarklet` | Get Bookmarklet |
| POST | `/api/knowledge/quick-import` | Quick Import |
| POST | `/api/knowledge/ai-tag` | Api Ai Tag |
| POST | `/api/knowledge/split-document` | Api Split Document |
| GET | `/api/knowledge/project-recommend` | Api Project Recommend |
| POST | `/api/knowledge/import-from-project` | Api Import From Project |
| POST | `/api/knowledge/extract-from-weekly` | Api Extract Weekly |
| GET | `/api/knowledge/search-unified` | Api Unified Search |
| GET | `/api/knowledge/relevant-updates` | Api Relevant Updates |
| GET | `/api/knowledge/backup/status` | Get Backup Status |
| POST | `/api/knowledge/backup/create` | Create Backup Manual |
| POST | `/api/knowledge/backup/restore` | Restore Backup |
| PUT | `/api/knowledge/backup/config` | Update Backup Config |
| GET | `/api/knowledge/search/hybrid` | Hybrid Search |

## lookups

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/lookups/phases` | Get Phases |
| POST | `/api/lookups/phases` | Create Phase |
| PUT | `/api/lookups/phases/{item_id}` | Update Phase |
| DELETE | `/api/lookups/phases/{item_id}` | Delete Phase |
| GET | `/api/lookups/gates` | Get Gates |
| POST | `/api/lookups/gates` | Create Gate |
| PUT | `/api/lookups/gates/{item_id}` | Update Gate |
| DELETE | `/api/lookups/gates/{item_id}` | Delete Gate |
| GET | `/api/lookups/technical-lines` | Get Lines |
| POST | `/api/lookups/technical-lines` | Create Line |
| PUT | `/api/lookups/technical-lines/{item_id}` | Update Line |
| DELETE | `/api/lookups/technical-lines/{item_id}` | Delete Line |
| GET | `/api/lookups/roles` | Get Roles |
| POST | `/api/lookups/roles` | Create Role |
| PUT | `/api/lookups/roles/{item_id}` | Update Role |
| DELETE | `/api/lookups/roles/{item_id}` | Delete Role |
| GET | `/api/lookups/doc-types` | Get Doc Types |
| PUT | `/api/lookups/doc-types` | Save Doc Types |
| GET | `/api/lookups/admin/project-phase-groups` | Get Phase Groups |
| GET | `/api/lookups/admin/project-tabs-config` | Get Tabs Config |
| PUT | `/api/lookups/admin/project-tabs-config` | Save Tabs Config |
| GET | `/api/lookups/admin/data-files` | List Data Files |
| POST | `/api/lookups/admin/data-files/restore` | Restore Data File |

## milestones

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/milestones` | List Milestones |
| POST | `/api/projects/{project_id}/milestones` | Create Milestone |
| PUT | `/api/milestones/{milestone_id}` | Update Milestone |
| DELETE | `/api/milestones/{milestone_id}` | Delete Milestone |
| GET | `/api/milestones/all` | All Milestones |

## my-work

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/my-work` | My Work |

## ocr

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ocr/parse-chat` | Parse Chat Image |

## opportunities

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/opportunities` | List Opportunities |
| POST | `/api/opportunities` | Create Opportunity |
| GET | `/api/opportunities/board` | Opportunity Board |
| PUT | `/api/opportunities/{opp_id}` | Update Opportunity |
| DELETE | `/api/opportunities/{opp_id}` | Delete Opportunity |

## plm

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/bom` | List Bom |
| POST | `/api/projects/{project_id}/bom` | Create Bom Item |
| PUT | `/api/bom/{item_id}` | Update Bom Item |
| DELETE | `/api/bom/{item_id}` | Delete Bom Item |
| GET | `/api/projects/{project_id}/ecns` | List Ecns |
| POST | `/api/projects/{project_id}/ecns` | Create Ecn |
| PUT | `/api/ecns/{ecn_id}` | Update Ecn |
| DELETE | `/api/ecns/{ecn_id}` | Delete Ecn |
| POST | `/api/projects/{project_id}/bom/upload` | Upload Bom |
| GET | `/api/projects/{project_id}/bom/export` | Export Bom |
| POST | `/api/prototype-builds/{build_id}/bom-files` | Upload Bom File |
| GET | `/api/prototype-builds/{build_id}/bom-files` | List Bom Files |
| GET | `/api/prototype-builds/{build_id}/bom-files/{file_id}/download` | Download Bom File |
| GET | `/api/prototype-builds/{build_id}/bom-files/{file_id}/preview` | Preview Bom File |
| DELETE | `/api/prototype-builds/{build_id}/bom-files/{file_id}` | Delete Bom File |

## product-tech

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/product-tech/specialties` | List Specialties |
| GET | `/api/product-tech` | List Items |
| POST | `/api/product-tech` | Create Item |
| GET | `/api/product-tech/stats` | Get Stats |
| GET | `/api/product-tech/template` | Download Template |
| GET | `/api/product-tech/{item_id}` | Get Item |
| PUT | `/api/product-tech/{item_id}` | Update Item |
| DELETE | `/api/product-tech/{item_id}` | Delete Item |
| POST | `/api/product-tech/import` | Import Items |
| GET | `/api/product-tech/{item_id}/files` | List Files |
| POST | `/api/product-tech/{item_id}/files` | Upload Files |
| DELETE | `/api/product-tech/{item_id}/files/{file_id}` | Delete File |
| GET | `/api/product-tech/{item_id}/files/{file_id}/download` | Download File |
| GET | `/api/product-tech/{item_id}/files/{file_id}/preview` | Preview File |
| POST | `/api/product-tech/qrcode` | Generate Qrcodes |
| POST | `/api/product-tech/parse-all` | Parse All Products |
| POST | `/api/product-tech/batch-delete` | Batch Delete |
| POST | `/api/product-tech/batch-upload-drawings` | Batch Upload Drawings |

## projects

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects` | List Projects |
| POST | `/api/projects` | Create Project |
| GET | `/api/projects/{project_id}/plan` | Generate Project Plan |
| GET | `/api/projects/search` | Global Search |
| GET | `/api/projects/{project_id}` | Get Project |
| PUT | `/api/projects/{project_id}` | Update Project |
| DELETE | `/api/projects/{project_id}` | Delete Project |
| POST | `/api/projects/{project_id}/copy` | Copy Project |
| GET | `/api/projects/{project_id}/stats` | Project Stats |

## report-gen

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/report-gen/generate/{project_id}` | Generate Report |
| GET | `/api/report-gen/types` | List Report Types |
| POST | `/api/report-gen/export/docx` | Export Docx |
| POST | `/api/report-gen/fill-template` | Fill Template |
| GET | `/api/report-gen/deliverable/{deliverable_id}` | Generate Deliverable Report |
| GET | `/api/report-gen/standard-report/{std_id}` | Generate Standard Report |
| GET | `/api/report-gen/fill-deliverable/{deliverable_id}` | Fill Deliverable Template |
| GET | `/api/report-gen/fill-standard/{std_id}` | Fill Standard Template |
| GET | `/api/report-gen/templates` | List Templates |
| POST | `/api/report-gen/templates/upload` | Upload Template To Library |
| DELETE | `/api/report-gen/templates/{name}` | Delete Template |
| POST | `/api/report-gen/fill-from-library` | Fill From Library |
| POST | `/api/report-gen/export/pptx` | Export Pptx |
| POST | `/api/report-gen/image-to-report` | Image To Report |
| POST | `/api/report-gen/save-image-report` | Save Image Report |
| GET | `/api/report-gen/management-weekly` | Management Weekly Summary |
| POST | `/api/report-gen/ai-fill-baseline` | Ai Fill Baseline |

## reports

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/reports/import-excel` | Import Reports Excel |
| POST | `/api/reports/import-excel-ai` | Import Weekly Ai |
| POST | `/api/reports/import-paste` | Import Weekly Paste |
| POST | `/api/reports/import-excel-ai-confirm` | Import Weekly Ai Confirm |
| GET | `/api/projects/{project_id}/reports` | List Reports |
| POST | `/api/projects/{project_id}/reports` | Create Or Update Report |
| GET | `/api/reports/{report_id}` | Get Report |
| PUT | `/api/reports/{report_id}` | Update Report |
| DELETE | `/api/reports/{report_id}` | Delete Report |
| GET | `/api/projects/{project_id}/reports/latest` | Latest Report |
| GET | `/api/reports` | List All Reports |
| GET | `/api/projects/{project_id}/reports/{report_id}/sync-milestones` | Sync Milestones From Report |
| POST | `/api/projects/{project_id}/milestones/sync-apply` | Apply Milestone Sync |

## requirements

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/requirements` | List Reqs |
| POST | `/api/projects/{project_id}/requirements` | Create Req |
| PUT | `/api/requirements/{req_id}` | Update Req |
| DELETE | `/api/requirements/{req_id}` | Delete Req |
| POST | `/api/requirements/{req_id}/upload-attachment` | Upload Req Attachment |
| DELETE | `/api/requirements/{req_id}/attachment` | Delete Req Attachment |
| POST | `/api/projects/{project_id}/requirements/upload` | Upload Reqs |
| GET | `/api/projects/{project_id}/requirements/template` | Download Template |
| GET | `/api/projects/{project_id}/requirements/export` | Export Reqs |
| POST | `/api/projects/{project_id}/requirements/ai-parse` | Ai Parse Requirements |

## risks

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/risks` | List All Risks |
| GET | `/api/projects/{project_id}/risks` | List Risks |
| POST | `/api/projects/{project_id}/risks` | Create Risk |
| PUT | `/api/risks/{risk_id}` | Update Risk |
| DELETE | `/api/risks/{risk_id}` | Delete Risk |
| POST | `/api/risks/{risk_id}/close` | Close Risk |
| POST | `/api/risks/extract-from-reports` | Extract From Weekly Reports |

## tasks

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/tasks` | List Tasks |
| POST | `/api/projects/{project_id}/tasks` | Create Task |
| PUT | `/api/tasks/{task_id}` | Update Task |
| DELETE | `/api/tasks/{task_id}` | Delete Task |
| POST | `/api/projects/{project_id}/tasks/import` | Import Tasks |

## team

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/team-members` | List Members |
| POST | `/api/team-members` | Create Member |
| PUT | `/api/team-members/{member_id}` | Update Member |
| GET | `/api/projects/{project_id}/members` | List Project Members |
| POST | `/api/projects/{project_id}/members` | Add Project Member |
| PUT | `/api/project-members/{pm_id}` | Update Project Member |
| DELETE | `/api/project-members/{pm_id}` | Remove Project Member |
| GET | `/api/resource-matrix` | Resource Matrix |

## testing

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects/{project_id}/test-plans` | List Test Plans |
| POST | `/api/projects/{project_id}/test-plans` | Create Test Plan |
| POST | `/api/test-plans/{plan_id}/upload` | Upload Test Plan File |
| PUT | `/api/test-plans/{plan_id}` | Update Test Plan |
| DELETE | `/api/test-plans/{plan_id}` | Delete Test Plan |
| GET | `/api/test-plans/{plan_id}/results` | List Test Results |
| POST | `/api/test-plans/{plan_id}/results` | Create Test Result |
| PUT | `/api/test-results/{result_id}` | Update Test Result |
| DELETE | `/api/test-results/{result_id}` | Delete Test Result |
| POST | `/api/test-results/{result_id}/upload` | Upload Test File |
| POST | `/api/projects/{project_id}/test-files/upload-batch` | Upload Test File Batch |
| GET | `/api/projects/{project_id}/test-files` | List Test Files |
| GET | `/api/projects/{project_id}/test-issues` | List Test Issues |
| POST | `/api/projects/{project_id}/test-issues` | Create Test Issue |
| PUT | `/api/test-issues/{issue_id}` | Update Test Issue |
| DELETE | `/api/test-issues/{issue_id}` | Delete Test Issue |
| GET | `/api/projects/{project_id}/prototype-builds` | List Builds |
| POST | `/api/projects/{project_id}/prototype-builds` | Create Build |
| PUT | `/api/prototype-builds/{build_id}` | Update Build |
| DELETE | `/api/prototype-builds/{build_id}` | Delete Build |
| GET | `/api/prototype-builds/{build_id}/materials` | List Materials |
| POST | `/api/prototype-builds/{build_id}/materials` | Create Material |
| PUT | `/api/materials/{mat_id}` | Update Material |
| DELETE | `/api/materials/{mat_id}` | Delete Material |
| POST | `/api/prototype-builds/{build_id}/bom-from-drawing` | Generate Bom From Drawing |
| POST | `/api/prototype-builds/{build_id}/materials/batch` | Batch Create Materials |

## training

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/training/materials` | List Materials |
| POST | `/api/training/materials` | Upload Material |
| GET | `/api/training/categories` | List Categories |
| DELETE | `/api/training/materials/{material_id}` | Delete Material |
| GET | `/api/training/file/{material_id}` | Get Material File |

## training-tasks

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/training/tasks` | List Tasks |
| POST | `/api/training/tasks` | Create Task |
| GET | `/api/training/tasks/stats` | My Stats |
| GET | `/api/training/tasks/reviews` | List Reviews |
| PUT | `/api/training/tasks/{task_id}` | Update Task |
| DELETE | `/api/training/tasks/{task_id}` | Delete Task |
| POST | `/api/training/tasks/visit` | Report Visit |
| POST | `/api/training/tasks/{task_id}/submit` | Submit Task |
| POST | `/api/training/tasks/progress/{progress_id}/review` | Review Progress |

## 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | Health Check |
| GET | `/api/server-info` | Server Info |
| GET | `/api/ai/engines` | Ai Engines Status |
| GET | `/api/presence/{resource_type}/{resource_id}` | Get Presence |
| GET | `/api/tunnel/status` | Tunnel Status |
| POST | `/api/tunnel/start` | Tunnel Start |
| POST | `/api/tunnel/stop` | Tunnel Stop |
| GET | `/api/dingtalk/config` | Api Get Dt Config |
| PUT | `/api/dingtalk/credentials` | Api Save Dt Creds |
| GET | `/api/dingtalk/templates` | Api Get Dt Templates |
| PUT | `/api/dingtalk/templates` | Api Save Dt Templates |
| GET | `/api/dingtalk/templates/available` | Api List Dt Templates |
| POST | `/api/dingtalk/approvals` | Api Create Dt Approval |
| GET | `/api/dingtalk/approvals/{instance_id}` | Api Get Dt Status |
| GET | `/api/dingtalk/instances` | Api List Dt Instances |
| GET | `/api/dingtalk/instances/{instance_id}` | Api Get Dt Instance Detail |
| GET | `/api/dingtalk/users/search` | Api Search Dt User |
| GET | `/api/dingtalk/departments` | Api Get Dt Depts |
| GET | `/api/projects/{project_id}/dingtalk-approvals` | List Dt Approvals |
| POST | `/api/projects/{project_id}/dingtalk-approvals` | Create Dt Approval |
| PUT | `/api/projects/{project_id}/dingtalk-approvals/{approval_id}` | Update Dt Approval |
| DELETE | `/api/projects/{project_id}/dingtalk-approvals/{approval_id}` | Delete Dt Approval |
| POST | `/api/public/kb/{token}/chat` | Public Kb Chat |
| GET | `/api/public/kb/{token}` | Public Kb Info |
| GET | `/api/knowledge/qrcode` | Generate Qrcode |
| GET | `/api/knowledge/share-links/{share_id}/visits` | Get Share Visits |
| GET | `/kb/chat/{token}` | Public Chat Page |
| GET | `/{full_path}` | Spa Fallback |
