<template>
  <div class="main-layout">
    <el-container>
      <el-aside width="200px">
        <el-menu
          :router="true"
          default-active="/"
        >
          <el-menu-item index="/">
            <el-icon><i-ep-home /></el-icon>
            <span>首页</span>
          </el-menu-item>
          <el-menu-item index="/schools">
            <el-icon><i-ep-school /></el-icon>
            <span>学校管理</span>
          </el-menu-item>
          <el-menu-item index="/analysis">
            <el-icon><i-ep-data-analysis /></el-icon>
            <span>增值评价</span>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-container>
        <el-header>
          <h2>区域教学增值评价系统</h2>
        </el-header>
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template> 