"""
Django Admin 仪表盘模块。

此模块提供自定义的管理仪表盘功能，包括数据概览和快速操作。
"""

from django.contrib import admin
from django.core.cache import cache
from django.db.models import Count, Avg
from django.urls import path
from django.shortcuts import render
from .models import School, Teacher, Student, Score

class DashboardView(admin.AdminSite):
    """
    自定义管理仪表盘视图。
    
    Args:
        admin.AdminSite: Django的AdminSite基类
    
    Returns:
        管理仪表盘实例
    """
    site_header = '区域教学增值评价系统'
    site_title = '增值评价管理'
    index_title = '管理仪表盘'
    
    def get_urls(self):
        """
        获取仪表盘URL配置。
        
        Returns:
            URL模式列表
        """
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
        """
        仪表盘视图函数。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            渲染的HTTP响应
        """
        # 使用缓存避免频繁查询数据库
        stats = cache.get('admin_dashboard_stats')
        if not stats:
            stats = {
                'school_count': School.objects.count(),
                'teacher_count': Teacher.objects.count(),
                'student_count': Student.objects.count(),
                'score_count': Score.objects.count(),
                'avg_score': Score.objects.aggregate(avg=Avg('raw_score'))['avg'],
                'schools_by_type': School.objects.values('school_type').annotate(count=Count('school_id')),
                'teachers_by_qualification': Teacher.objects.values('qualification').annotate(count=Count('teacher_id')),
            }
            cache.set('admin_dashboard_stats', stats, 60*5)  # 缓存5分钟
            
        context = {
            **self.each_context(request),
            'title': '系统概览',
            'stats': stats,
        }
        return render(request, 'admin/dashboard.html', context) 