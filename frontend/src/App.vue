<template>
  <div id="app">
    <el-container>
      <el-header height="64px">
        <div class="header-logo">
          <img src="@/assets/logo.png" alt="系统Logo" height="40">
          <h1 class="system-title">江门市开平市教学质量综合评价管理平台</h1>
        </div>
        <el-menu mode="horizontal" :router="true" background-color="#545c64" text-color="#fff" active-text-color="#ffd04b">
          <el-menu-item index="/">首页</el-menu-item>
          <el-sub-menu index="2">
            <template #title>数据分析</template>
            <el-menu-item index="/school-value-added">学校增值分析</el-menu-item>
            <el-menu-item index="/teacher-value-added">教师增值分析</el-menu-item>
            <el-menu-item index="/student-portrait">学生成长画像</el-menu-item>
            <el-menu-item index="/feature-analysis">特征分析</el-menu-item>
          </el-sub-menu>
          <el-menu-item index="/results">分析报告</el-menu-item>
          <el-menu-item index="/data-management">数据管理</el-menu-item>
        </el-menu>
        <div class="user-info">
          <el-dropdown>
            <span class="user-dropdown">
              管理员 <i class="el-icon-arrow-down"></i>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>个人设置</el-dropdown-item>
                <el-dropdown-item>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <el-container>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
      
      <el-footer height="50px">
        江门市开平市教学质量综合评价管理平台 v1.0 © 2025
                廖作东 2025年4月7日
      </el-footer>
    </el-container>
  </div>
</template>

<script>
export default {
  name: 'App'
}
</script>

<style>
.header-logo {
  display: flex;
  align-items: center;
}
.system-title {
  margin-left: 10px;
  font-size: 18px;
  color: #fff;
}
.user-info {
  margin-left: auto;
}
.user-dropdown {
  color: #fff;
  cursor: pointer;
}
.el-header {
  display: flex;
  align-items: center;
  background-color: #545c64;
  color: #fff;
  padding: 0 20px;
}
.el-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f7fa;
  color: #909399;
}
</style>
