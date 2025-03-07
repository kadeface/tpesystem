from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
import json

# Create your views here.

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
