<template>
  <div id="app">
    <el-container class="app-container">
      <!-- 顶部导航栏 -->
      <el-header height="70px" class="app-header">
        <div class="header-left">
          <div class="logo-area">
            <img src="@/assets/logo.png" alt="系统Logo" class="logo-img">
            <div class="logo-text">
              <h1 class="system-title">江门市开平市教学质量综合评价管理平台</h1>
              <span class="system-subtitle">Teaching Quality Evaluation System</span>
            </div>
          </div>
        </div>
        
        <el-menu 
          mode="horizontal" 
          :router="true" 
          class="main-menu"
          :default-active="activeMenu"
          @select="handleMenuSelect"
        >
          <el-menu-item index="/" class="menu-item">
            <el-icon><HomeFilled /></el-icon>
            <span>首页</span>
          </el-menu-item>
          <el-sub-menu index="2" class="menu-item">
            <template #title>
              <el-icon><DataAnalysis /></el-icon>
              <span>数据分析</span>
            </template>
            <el-menu-item index="/school-value-added">
              <el-icon><School /></el-icon>
              <span>学校增值分析</span>
            </el-menu-item>
            <el-menu-item index="/teacher-value-added">
              <el-icon><User /></el-icon>
              <span>教师增值分析</span>
            </el-menu-item>
            <el-menu-item index="/student-portrait">
              <el-icon><Avatar /></el-icon>
              <span>学生成长画像</span>
            </el-menu-item>
            <el-menu-item index="/feature-analysis">
              <el-icon><TrendCharts /></el-icon>
              <span>特征分析</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item index="/results" class="menu-item">
            <el-icon><Document /></el-icon>
            <span>分析报告</span>
          </el-menu-item>
          <el-menu-item index="/data-management" class="menu-item">
            <el-icon><Setting /></el-icon>
            <span>数据管理</span>
          </el-menu-item>
        </el-menu>

        <div class="header-right">
          <div class="user-info">
            <el-dropdown trigger="click">
              <div class="user-avatar">
                <el-avatar :size="36" class="avatar-img">
                  <el-icon><User /></el-icon>
                </el-avatar>
                <span class="user-name">管理员</span>
                <el-icon class="arrow-down"><ArrowDown /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item divided>
                    <el-icon><User /></el-icon>
                    <span>个人设置</span>
                  </el-dropdown-item>
                  <el-dropdown-item>
                    <el-icon><Bell /></el-icon>
                    <span>消息通知</span>
                  </el-dropdown-item>
                  <el-dropdown-item>
                    <el-icon><QuestionFilled /></el-icon>
                    <span>帮助中心</span>
                  </el-dropdown-item>
                  <el-dropdown-item divided class="logout-item">
                    <el-icon><SwitchButton /></el-icon>
                    <span>退出登录</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-header>
      
      <!-- 主内容区域 -->
      <el-container class="main-container">
        <el-main class="main-content">
          <router-view v-slot="{ Component }">
            <transition name="fade-transform" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </el-main>
      </el-container>
      
      <!-- 底部信息栏 -->
      <el-footer height="50px" class="app-footer">
        <div class="footer-content">
          <span class="footer-text">© 2025 江门市开平市教学质量综合评价管理平台</span>
          <span class="footer-divider">|</span>
          <span class="footer-text">版本 v1.0.0</span>
          <span class="footer-divider">|</span>
          <span class="footer-text">技术支持：教育大数据分析团队</span>
        </div>
      </el-footer>
    </el-container>
  </div>
</template>

<script>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { 
  HomeFilled, 
  DataAnalysis, 
  School, 
  User, 
  Avatar, 
  TrendCharts,
  Document,
  Setting,
  Bell,
  QuestionFilled,
  ArrowDown,
  SwitchButton
} from '@element-plus/icons-vue'

export default {
  name: 'App',
  components: {
    HomeFilled,
    DataAnalysis,
    School,
    User,
    Avatar,
    TrendCharts,
    Document,
    Setting,
    Bell,
    QuestionFilled,
    ArrowDown,
    SwitchButton
  },
  setup() {
    const route = useRoute()
    const activeMenu = computed(() => route.path)
    
    const handleMenuSelect = (index) => {
      console.log('Selected menu:', index)
    }
    
    return {
      activeMenu,
      handleMenuSelect
    }
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  height: 100vh;
  overflow: hidden;
}

.app-container {
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  background-size: 400% 400%;
  animation: gradientBG 15s ease infinite;
}

@keyframes gradientBG {
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
}

/* 顶部导航栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(90deg, #1a237e 0%, #2c3e50 100%);
  color: #fff;
  padding: 0 30px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  position: relative;
  z-index: 1000;
}

.app-header::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
}

.header-left {
  display: flex;
  align-items: center;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 15px;
}

.logo-img {
  width: 45px;
  height: 45px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  padding: 8px;
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.system-title {
  font-size: 20px;
  font-weight: 600;
  color: #fff;
  margin: 0;
  letter-spacing: 1px;
}

.system-subtitle {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 400;
  letter-spacing: 2px;
  text-transform: uppercase;
}

/* 主菜单 */
.main-menu {
  flex: 1;
  margin: 0 40px;
  border-bottom: none;
  background: transparent;
}

.main-menu .menu-item {
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  font-weight: 500;
  padding: 0 20px;
  height: 70px;
  line-height: 70px;
  border-radius: 0;
  transition: all 0.3s ease;
  position: relative;
}

.main-menu .menu-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.main-menu .menu-item.is-active {
  background: rgba(79, 172, 254, 0.2);
  color: #4facfe;
  font-weight: 600;
}

.main-menu .menu-item.is-active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 60%;
  height: 3px;
  background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
  border-radius: 2px;
}

.main-menu .el-sub-menu__title {
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  font-weight: 500;
  padding: 0 20px;
  height: 70px;
  line-height: 70px;
  transition: all 0.3s ease;
}

.main-menu .el-sub-menu__title:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.main-menu .el-icon {
  margin-right: 6px;
}

/* 用户信息区域 */
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-info {
  margin-left: 0;
}

.user-avatar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 25px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.user-avatar:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(79, 172, 254, 0.5);
  transform: translateY(-2px);
}

.avatar-img {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: #fff;
}

.user-name {
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}

.arrow-down {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  transition: transform 0.3s ease;
}

.user-avatar:hover .arrow-down {
  transform: rotate(180deg);
}

/* 主内容区域 */
.main-container {
  background: transparent;
  height: calc(100vh - 120px);
}

.main-content {
  background: #f5f7fa;
  border-radius: 20px 20px 0 0;
  margin: 0;
  padding: 30px;
  box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.1);
  overflow-y: auto;
  height: 100%;
}

/* 底部 */
.app-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(90deg, #1a237e 0%, #2c3e50 100%);
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  padding: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.footer-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.footer-text {
  font-weight: 400;
}

.footer-divider {
  color: rgba(255, 255, 255, 0.3);
}

/* 下拉菜单样式 */
.el-dropdown-menu {
  background: rgba(42, 65, 82, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(79, 172, 254, 0.3);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.el-dropdown-menu__item {
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
}

.el-dropdown-menu__item:hover {
  background: rgba(79, 172, 254, 0.2);
  color: #fff;
}

.el-dropdown-menu__item.is-divided {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.logout-item {
  color: #ff6b6b;
}

.logout-item:hover {
  background: rgba(255, 107, 107, 0.2) !important;
  color: #ff6b6b !important;
}

/* 页面切换动画 */
.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all 0.3s ease;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .system-title {
    font-size: 18px;
  }
  
  .system-subtitle {
    display: none;
  }
  
  .main-menu {
    margin: 0 20px;
  }
  
  .main-menu .menu-item {
    padding: 0 15px;
    font-size: 14px;
  }
}

@media (max-width: 768px) {
  .header-left {
    flex: 1;
  }
  
  .logo-text {
    display: none;
  }
  
  .main-menu {
    display: none;
  }
  
  .user-name {
    display: none;
  }
}
</style>
