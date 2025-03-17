from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from core.tasks import get_task_status
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
import json
# core/api/views.py
from django.http import JsonResponse
from django.views import View
from django.core.cache import cache
from core.analytics.report_generator import StudentGrowthAnalysisReport


@staff_member_required
@require_GET
def task_status(request):
    """
    获取任务状态API。
    
    Args:
        request: HTTP请求对象，需要包含task_id参数
        
    Returns:
        JsonResponse: 包含任务状态信息的JSON响应
    """
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'status': 'error', 'error': '缺少任务ID参数'}, status=400)
    
    # 从缓存获取任务状态
    task_key = f"task_status_{task_id}"
    task_status = cache.get(task_key, None)
    
    if task_status is None:
        return JsonResponse({
            'status': 'unknown',
            'error': '找不到任务状态或任务已过期',
            'progress': 0,
            'logs': ['任务状态未找到，可能任务已完成或者任务ID无效']
        })
    
    # 如果状态是字符串格式，转换为字典
    if isinstance(task_status, str):
        try:
            task_status = json.loads(task_status)
        except:
            task_status = {'status': 'error', 'error': '任务状态格式错误'}
    
    return JsonResponse(task_status) 


class StudentGrowthAnalysisAPI(View):
    """学生成长分析API"""
    
    def get(self, request, student_id):
        """获取学生成长分析报告"""
        # 参数处理
        refresh = request.GET.get('refresh', '').lower() in ('true', '1', 'yes')
        cache_key = f"student_growth_report_{student_id}"
        
        # 检查缓存
        if not refresh:
            cached_report = cache.get(cache_key)
            if cached_report:
                return JsonResponse(cached_report)
                
        # 生成新报告
        try:
            generator = StudentGrowthAnalysisReport(student_id)
            report = generator.generate()
            
            # 缓存报告
            cache.set(cache_key, report, 3600)  # 缓存1小时
            
            return JsonResponse(report)
        except Exception as e:
            return JsonResponse({
                'error': str(e),
                'message': '生成学生成长分析报告失败'
            }, status=500)
    
    def post(self, request, student_id):
        """接收反馈并更新分析"""
        try:
            # 解析请求数据
            data = json.loads(request.body)
            feedback_type = data.get('type')
            feedback_content = data.get('content')
            
            # 简单校验
            if not feedback_type or not feedback_content:
                return JsonResponse({
                    'error': 'Missing required fields',
                    'message': '反馈类型和内容不能为空'
                }, status=400)
                
            # 存储反馈
            # StudentFeedback.objects.create(...)
                
            # 更新缓存
            cache_key = f"student_growth_report_{student_id}"
            cache.delete(cache_key)
            
            return JsonResponse({
                'success': True,
                'message': '成功接收反馈'
            })
        except Exception as e:
            return JsonResponse({
                'error': str(e),
                'message': '处理反馈失败'
            }, status=500)