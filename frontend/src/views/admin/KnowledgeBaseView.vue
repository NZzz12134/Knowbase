<template>
  <div class="admin-page">
    <div class="page-header">
      <div><span class="eyebrow">KNOWLEDGE LIBRARY</span><h1>管理你的知识<span class="page-count">{{ kbs.length }} 个知识库</span></h1><p>给文档一个有序的家，让每次提问都能找到可靠的答案。</p></div>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>&nbsp;新建知识库
      </el-button>
    </div>

    <div class="overview-strip"><div class="overview-cell"><span>知识库总数</span><strong>{{ kbs.length }}</strong></div><div class="overview-cell"><span>已收录文档</span><strong>{{ kbs.reduce((sum,k) => sum + (k.document_count || 0), 0) }}</strong></div><div class="overview-cell"><span>可检索知识分块</span><strong>{{ new Intl.NumberFormat('zh-CN').format(kbs.reduce((sum,k) => sum + (k.chunk_count || 0), 0)) }}</strong></div></div>
    <el-table :data="kbs" v-loading="loading" empty-text="还没有知识库，点击「新建知识库」开始整理知识。">
      <el-table-column prop="name" label="知识库" min-width="190"><template #default="{ row }"><div class="table-name"><span class="file-symbol"><el-icon aria-hidden="true"><FolderOpened /></el-icon></span><strong>{{ row.name }}</strong></div></template></el-table-column>
      <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
      <el-table-column label="文档数" width="100" align="center">
        <template #default="{ row }">{{ row.document_count ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="分块数" width="100" align="center">
        <template #default="{ row }">{{ row.chunk_count ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="解析状态分布" min-width="200">
        <template #default="{ row }">
          <template v-if="row.parse_stats">
            <el-tag size="small" type="success" style="margin-right: 4px">
              成功 {{ row.parse_stats.succeeded || 0 }}
            </el-tag>
            <el-tag size="small" type="danger" style="margin-right: 4px">
              失败 {{ row.parse_stats.failed || 0 }}
            </el-tag>
            <el-tag size="small" type="warning">
              进行中 {{ (row.parse_stats.parsing || 0) + (row.parse_stats.pending || 0) }}
            </el-tag>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="270" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDocuments(row)">管理文档</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link :type="row.is_active ? 'warning' : 'success'" @click="toggleActive(row)">
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑知识库' : '新建知识库'" width="480px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" name="kb-name" aria-label="知识库名称" autocomplete="off" maxlength="100" placeholder="例如：产品手册、团队制度…" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" name="kb-description" aria-label="知识库描述" autocomplete="off" type="textarea" :rows="3" placeholder="描述知识库的内容和用途（可选）…" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Plus } from '@element-plus/icons-vue'
import { kbApi } from '../../api/admin'
import { useRouter } from 'vue-router'
const router = useRouter()
function openDocuments(row) { router.push({ path: '/space/documents', query: { kb: row.id } }) }

const kbs = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = reactive({ name: '', description: '' })

async function fetchList() {
  loading.value = true
  try {
    kbs.value = await kbApi.all()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  form.name = row.name
  form.description = row.description || ''
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await kbApi.update(editing.value.id, { name: form.name, description: form.description })
    } else {
      await kbApi.create({ name: form.name, description: form.description })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    fetchList()
  } finally {
    saving.value = false
  }
}

async function toggleActive(row) {
  try {
    await kbApi.update(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已停用' : '已启用')
    fetchList()
  } catch (_) {
    /* 拦截器已提示 */
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${row.name}」吗？其中的文档、分块与向量索引将一并删除，此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await kbApi.remove(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (_) { /* ignore */ }
}

onMounted(fetchList)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>
