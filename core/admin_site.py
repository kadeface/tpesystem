"""
自定义Django Admin站点配置。

此模块实现了管理界面的逻辑分组和布局优化。
"""

from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _
from django.urls import path
from . import views

class EducationEvaluationAdminSite(AdminSite):
    """
    教育评价系统自定义管理站点。
    
    Args:
        AdminSite: Django管理站点基类
    
    Returns:
        自定义管理站点实例
    """
    site_header = '区域教学增值评价系统'
    site_title = '增值评价管理平台'
    index_title = '系统管理'
    
    # 定义应用分组
    def get_app_list(self, request):
        """
        获取应用列表，并按逻辑进行分组。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            分组后的应用列表
        """
        app_list = super().get_app_list(request)
        
        # 创建自定义分组
        custom_app_list = [
            {
                'name': '基础信息管理',
                'app_label': 'basic_info',
                'models': [],
            },
            {
                'name': '教学主体管理',
                'app_label': 'teaching_entities',
                'models': [],
            },
            {
                'name': '教学内容管理',
                'app_label': 'teaching_content',
                'models': [],
            },
            {
                'name': '评价分析管理',
                'app_label': 'evaluation',
                'models': [],
            },
            {
                'name': '系统设置',
                'app_label': 'system',
                'models': [],
            }
        ]
        
        # 定义模型分组映射
        model_mapping = {
            # 基础信息管理
            'region': 0,  # 区域管理
            'semester': 0,  # 学期管理
            'school': 0,  # 学校管理
            
            # 教学主体管理
            'grade': 1,  # 年级管理
            'class': 1,  # 班级管理
            'teacher': 1,  # 教师管理
            'teacherteam': 1,  # 教师团队管理
            'student': 1,  # 学生管理
            'family': 1,  # 家庭管理
            
            # 教学内容管理
            'subject': 2,  # 学科管理
            'subjectrelation': 2,  # 学科关联管理
            'exam': 2,  # 考试管理
            'score': 2,  # 成绩管理
            
            # 评价分析管理
            'evaluationmetrics': 3,  # 评价指标管理
            'valueaddededucation': 3,  # 增值评价管理
            
            # 系统设置
            'user': 4,  # 用户管理
            'group': 4,  # 组管理
        }
        
        # 将现有模型分配到自定义分组中
        for app in app_list:
            for model in app['models']:
                model_name = model['object_name'].lower()
                if model_name in model_mapping:
                    group_idx = model_mapping[model_name]
                    custom_app_list[group_idx]['models'].append(model)
        
        # 只返回有模型的分组
        return [app for app in custom_app_list if app['models']]

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_data_url'] = '/admin/import-data/'
        return super().index(request, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        from . import views
        
        my_urls = [
            # 添加教师升级URL
            path('promote-teachers/', views.promote_teachers_view, name='promote_teachers'),
            path('teacher-history/', views.teacher_history_view, name='teacher_history'),
            path('rebuild-teacher-history/', views.rebuild_teacher_history, name='rebuild_teacher_history'),
            path('teacher-history-summary/', views.teacher_history_summary, name='teacher_history_summary'),
            path('perform-teacher-promotion/', views.perform_teacher_promotion, name='perform_teacher_promotion'),
        ]
        return my_urls + urls

# 创建自定义管理站点实例
admin_site = EducationEvaluationAdminSite(name='education_admin')

# 如果需要仪表盘视图，请使用不同的变量名
class DashboardView(AdminSite):
    """
    仪表盘管理站点视图。
    
    Args:
        AdminSite: Django 管理站点基类
    
    Returns:
        仪表盘管理站点实例
    """
    site_header = '管理仪表盘'
    site_title = '管理仪表盘'
    index_title = '欢迎使用管理仪表盘'

# 使用不同的变量名
dashboard_site = DashboardView(name='dashboard_admin') 