<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <div style="text-align:center;margin-bottom:24px">
        <div style="font-size:24px;font-weight:700;color:#303133">麦科斯韦研发项目管理平台</div>
        <div style="font-size:13px;color:#909399;margin-top:8px">{{ isRegister ? '注册新账号' : '请登录以继续' }}</div>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-width="0" @submit.prevent>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" prefix-icon="Lock"
            @keyup.enter="submit" show-password />
        </el-form-item>
        <el-form-item v-if="isRegister" prop="memberName">
          <el-input v-model="form.memberName" placeholder="姓名（可选）" size="large" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" style="width:100%" :loading="loading" @click="submit">
            {{ isRegister ? '注册' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div style="text-align:center">
        <el-button type="primary" link @click="isRegister = !isRegister">
          {{ isRegister ? '已有账号？登录' : '没有账号？注册' }}
        </el-button>
        <span style="color:#c0c4cc;margin:0 8px">|</span>
        <el-popover trigger="click" :width="280">
          <div style="font-size:13px;line-height:1.8">
            <p><b>方式一：联系管理员</b></p>
            <p style="color:#909399">联系系统管理员（admin）在「资源管理 → 人员与账号」中重置密码</p>
            <p style="margin-top:8px"><b>方式二：管理员本地重置</b></p>
            <p style="color:#909399">管理员在服务器上运行：</p>
            <p style="font-family:monospace;background:#f5f5f5;padding:4px;font-size:11px"> python -c "from backend_v2.routes.auth import reset_password; reset_password('用户名','新密码')"</p>
          </div>
          <template #reference>
            <el-button type="warning" link style="font-size:12px">忘记密码？</el-button>
          </template>
        </el-popover>
      </div>

      <div style="font-size:11px;color:#c0c4cc;text-align:center;margin-top:12px">
        演示账号：admin/admin123（管理员）| pm/pm123（项目经理）
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref(null)
const loading = ref(false)
const isRegister = ref(false)

const form = reactive({ username: '', password: '', memberName: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(form.username, form.password, form.memberName)
      ElMessage.success('注册成功')
    } else {
      await auth.login(form.username, form.password)
      ElMessage.success('登录成功')
    }
    router.replace('/my-work')
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1d1e2c 0%, #2d3a4a 100%);
}
.login-card {
  width: 400px;
  padding: 16px;
}
</style>
