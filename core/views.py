from rest_framework import viewsets, filters
from rest_framework.decorators import action
from .models import Region, Semester, School, Student, Score, Subject, Teacher, TeacherHistory, TeacherSubjectClass
from .serializers import RegionSerializer, SemesterSerializer, SchoolSerializer, StudentSerializer, ScoreSerializer, SubjectSerializer, TeacherSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import IsSchoolAdmin
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count
from django.contrib.admin.views.decorators import staff_member_required
import uuid
import os
import threading
from django.conf import settings
from django.urls import reverse
from django.core.management import call_command
from django.core.cache import cache
import json
from django.views.decorators.http import require_GET, require_POST

class RegionViewSet(viewsets.ModelViewSet):
    """
    区域视图集，提供区域信息的CRUD操作。

    Attributes:
        queryset: 查询集
        serializer_class: 序列化类
    """
    queryset = Region.objects.all()
    serializer_class = RegionSerializer 

class SemesterViewSet(viewsets.ModelViewSet):
    """
    学期视图集，提供学期信息的CRUD操作。

    Args:
        queryset: 查询集
        serializer_class: 序列化类
    """
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer

class SchoolViewSet(viewsets.ModelViewSet):
    """
    学校视图集，提供学校信息的CRUD操作。

    Args:
        queryset: 查询集
        serializer_class: 序列化类
    """
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    filterset_fields = ['region', 'school_type'] 

class ScoreUploadView(APIView):
    def post(self, request):
        file = request.FILES.get('file')
        # 处理上传的Excel文件
        # ...
        return Response({"status": "success"}) 

class StudentViewSet(viewsets.ModelViewSet):
    """
    学生视图集，提供学生信息的CRUD操作。
    """
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    filterset_fields = ['current_school', 'current_grade', 'status']
    search_fields = ['name', 'student_id']
    permission_classes = [IsSchoolAdmin]
    
    @action(detail=True, methods=['get'])
    def scores(self, request, pk=None):
        """获取指定学生的所有成绩"""
        student = self.get_object()
        scores = Score.objects.filter(student=student)
        serializer = ScoreSerializer(scores, many=True)
        return Response(serializer.data) 

@login_required
@permission_required('core.view_teacherhistory')
def teacher_history_view(request):
    """教师历史记录管理界面"""
    # 获取学期列表做筛选
    semesters = Semester.objects.all().order_by('-start_date')
    
    # 获取所有教师，按姓名排序
    teachers = Teacher.objects.filter(status='ACTIVE').order_by('name')
    
    # 获取可能的筛选参数
    semester_id = request.GET.get('semester')
    teacher_id = request.GET.get('teacher')
    
    # 准备查询集
    query = TeacherHistory.objects.all().select_related(
        'teacher', 'school', 'semester', 'subject', 'grade', 'class_field'
    )
    
    # 应用筛选
    if semester_id:
        query = query.filter(semester__semester_id=semester_id)
    
    if teacher_id:
        query = query.filter(teacher__teacher_id=teacher_id)
        
    # 获取分页参数
    page = request.GET.get('page', 1)
    page_size = 50  # 每页显示50条记录
    
    # 使用Django分页器
    paginator = Paginator(query, page_size)
    records = paginator.get_page(page)
    
    return render(request, 'admin/teacher_history.html', {
        'title': '教师历史记录管理',
        'records': records,
        'semesters': semesters,
        'teachers': teachers,
        'selected_semester': semester_id,
        'selected_teacher': teacher_id
    })

@login_required
@permission_required('core.change_teacherhistory')
def rebuild_teacher_history(request):
    """重建教师历史记录"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '只支持POST请求'})
    
    # 获取教师ID，如果没有则尝试重建所有教师的历史记录
    teacher_id = request.POST.get('teacher_id')
    
    try:
        with transaction.atomic():
            if teacher_id:
                # 重建单个教师的历史记录
                teacher = Teacher.objects.get(teacher_id=teacher_id)
                _rebuild_single_teacher_history(teacher)
                message = f"成功重建教师 {teacher.name} 的历史记录"
            else:
                # 限制为最多处理100名教师
                teachers = Teacher.objects.filter(status='ACTIVE')[:100]
                count = 0
                for teacher in teachers:
                    success = _rebuild_single_teacher_history(teacher)
                    if success:
                        count += 1
                message = f"成功重建 {count} 名教师的历史记录"
        
        return JsonResponse({'status': 'success', 'message': message})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"重建过程中出错: {str(e)}"})

def _rebuild_single_teacher_history(teacher):
    """内部函数：重建单个教师的历史记录"""
    try:
        # 清除现有历史记录
        TeacherHistory.objects.filter(teacher=teacher).delete()
        
        # 获取教师任课记录
        tsc_records = TeacherSubjectClass.objects.filter(
            teacher=teacher
        ).select_related('semester', 'subject', 'class_obj', 'class_obj__grade')
        
        if not tsc_records.exists():
            return False
        
        # 重建历史记录
        for tsc in tsc_records:
            status = 'COMPLETED' if tsc.semester.end_date and tsc.semester.end_date < timezone.now().date() else 'ACTIVE'
            
            TeacherHistory.objects.create(
                teacher=teacher,
                school=tsc.school or teacher.current_school,
                semester=tsc.semester,
                subject=tsc.subject,
                grade=tsc.class_obj.grade if tsc.class_obj else None,
                class_field=tsc.class_obj,
                is_class_teacher=teacher.is_class_teacher,
                admin_position=teacher.admin_position,
                start_date=tsc.semester.start_date,
                end_date=tsc.semester.end_date if status == 'COMPLETED' else None,
                status=status
            )
        return True
    except Exception as e:
        print(f"重建教师 {teacher.name} 的历史记录时出错: {str(e)}")
        return False

@login_required
@permission_required('core.view_teacherhistory')
def teacher_history_summary(request):
    """教师历史记录统计摘要"""
    # 按学期分组统计
    semester_stats = TeacherHistory.objects.values(
        'semester__semester_name', 'semester__semester_id'
    ).annotate(
        count=Count('id')
    ).order_by('-semester__start_date')
    
    # 按学校分组统计
    school_stats = TeacherHistory.objects.values(
        'school__school_name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]  # 取前10个学校
    
    # 按教师分组统计
    teacher_stats = TeacherHistory.objects.values(
        'teacher__name', 'teacher__teacher_id'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:20]  # 取前20名教师
    
    return render(request, 'admin/teacher_history_summary.html', {
        'title': '教师历史记录统计',
        'semester_stats': semester_stats,
        'school_stats': school_stats,
        'teacher_stats': teacher_stats,
        'total_records': TeacherHistory.objects.count(),
        'total_teachers': Teacher.objects.filter(status='ACTIVE').count()
    }) 

@login_required
@permission_required('core.change_teachersubjectclass')
def promote_teachers_view(request):
    """教师学期升级界面"""
    # 获取所有学期，按开始日期降序排列
    semesters = Semester.objects.all().order_by('-start_date')
    
    # 预备学期选择列表
    from_semesters = []
    to_semesters = []
    
    # 将学期分组
    for semester in semesters:
        if semester.end_date and semester.end_date < timezone.now().date():
            # 已结束的学期作为来源学期
            from_semesters.append(semester)
        
        # 所有学期都可以作为目标学期
        to_semesters.append(semester)
    
    return render(request, 'admin/promote_teachers.html', {
        'title': '教师学期升级',
        'from_semesters': from_semesters,
        'to_semesters': to_semesters
    })

@login_required
@permission_required('core.change_teachersubjectclass')
def perform_teacher_promotion(request):
    """执行教师升级操作"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '只支持POST请求'})
    
    # 获取参数
    from_semester_id = request.POST.get('from_semester')
    to_semester_id = request.POST.get('to_semester')
    auto_match = request.POST.get('auto_match') == 'true'
    dry_run = request.POST.get('dry_run') == 'true'
    
    # 参数验证
    if not from_semester_id or not to_semester_id:
        return JsonResponse({'status': 'error', 'message': '请选择源学期和目标学期'})
    
    try:
        # 获取学期对象
        from_semester = Semester.objects.get(semester_id=from_semester_id)
        to_semester = Semester.objects.get(semester_id=to_semester_id)
        
        # 验证学期顺序
        if from_semester.start_date >= to_semester.start_date:
            return JsonResponse({'status': 'error', 'message': '源学期必须早于目标学期'})
        
        # 获取教师任课记录
        tsc_records = TeacherSubjectClass.objects.filter(
            semester=from_semester
        ).select_related(
            'teacher', 'subject', 'class_obj', 'class_obj__grade', 'school'
        )
        
        if not tsc_records.exists():
            return JsonResponse({'status': 'error', 'message': f'未找到学期 {from_semester.semester_name} 的任课记录'})
        
        # 预览模式返回统计数据
        if dry_run:
            teacher_count = tsc_records.values('teacher').distinct().count()
            class_count = tsc_records.values('class_obj').distinct().count()
            subject_count = tsc_records.values('subject').distinct().count()
            
            return JsonResponse({
                'status': 'success',
                'message': '预览模式',
                'data': {
                    'teacher_count': teacher_count,
                    'class_count': class_count,
                    'subject_count': subject_count,
                    'record_count': tsc_records.count(),
                    'from_semester': from_semester.semester_name,
                    'to_semester': to_semester.semester_name
                }
            })
        
        # 执行升级
        results = _promote_teachers(from_semester, to_semester, auto_match)
        
        return JsonResponse({
            'status': 'success',
            'message': f'教师升级完成! 成功: {results["success"]}, 跳过: {results["skipped"]}',
            'data': results
        })
        
    except Semester.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '找不到指定的学期，请检查学期ID'})
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'status': 'error', 'message': f'处理过程中出错: {str(e)}'})

def _promote_teachers(from_semester, to_semester, auto_match=False):
    """内部函数：执行教师升级逻辑"""
    promote_count = 0
    skip_count = 0
    
    # 获取教师任课记录
    tsc_records = TeacherSubjectClass.objects.filter(
        semester=from_semester
    ).select_related(
        'teacher', 'subject', 'class_obj', 'class_obj__grade', 'school'
    )
    
    # 记录处理详情
    details = []
    
    with transaction.atomic():
        # 遍历每条任课记录
        for tsc in tsc_records:
            try:
                # 尝试找到对应的目标班级
                target_class = None
                
                # 1. 先检查班级是否已经存在于目标学期
                if tsc.class_obj:
                    target_classes = Class.objects.filter(
                        class_name=tsc.class_obj.class_name,
                        grade__school=tsc.class_obj.grade.school,
                        grade__semester=to_semester
                    )
                    if target_classes.exists():
                        target_class = target_classes.first()
                
                # 2. 如果开启自动匹配，尝试根据年级级别匹配
                if not target_class and auto_match and tsc.class_obj:
                    current_grade_level = tsc.class_obj.grade.grade_level
                    try:
                        # 假设下一学期年级级别+1
                        next_grade_level = str(int(current_grade_level) + 1)
                        target_grades = Grade.objects.filter(
                            school=tsc.class_obj.grade.school,
                            grade_level=next_grade_level,
                            semester=to_semester
                        )
                        
                        if target_grades.exists():
                            target_grade = target_grades.first()
                            # 找到对应班号的班级
                            class_number = tsc.class_obj.class_name.split('(')[0].strip()
                            target_classes = Class.objects.filter(
                                grade=target_grade,
                                class_name__contains=class_number
                            )
                            if target_classes.exists():
                                target_class = target_classes.first()
                    except (ValueError, IndexError):
                        pass
                
                # 如果找不到目标班级，跳过处理
                if not target_class:
                    detail = {
                        'teacher': tsc.teacher.name,
                        'subject': tsc.subject.subject_name,
                        'class_from': tsc.class_obj.class_name if tsc.class_obj else None,
                        'status': 'skipped',
                        'reason': '找不到目标班级'
                    }
                    details.append(detail)
                    skip_count += 1
                    continue
                
                # 创建历史记录
                TeacherHistory.objects.create(
                    teacher=tsc.teacher,
                    school=tsc.school or tsc.teacher.current_school,
                    semester=from_semester,
                    subject=tsc.subject,
                    grade=tsc.class_obj.grade if tsc.class_obj else None,
                    class_field=tsc.class_obj,
                    is_class_teacher=tsc.teacher.is_class_teacher,
                    admin_position=tsc.teacher.admin_position,
                    start_date=from_semester.start_date,
                    end_date=from_semester.end_date,
                    status='COMPLETED'
                )
                
                # 创建新学期任课记录
                TeacherSubjectClass.objects.create(
                    teacher=tsc.teacher,
                    subject=tsc.subject,
                    class_obj=target_class,
                    school=tsc.school or tsc.teacher.current_school,
                    semester=to_semester,
                    is_main=tsc.is_main,
                    status='ACTIVE'
                )
                
                detail = {
                    'teacher': tsc.teacher.name,
                    'subject': tsc.subject.subject_name,
                    'class_from': tsc.class_obj.class_name if tsc.class_obj else None,
                    'class_to': target_class.class_name,
                    'status': 'success'
                }
                details.append(detail)
                promote_count += 1
                
            except Exception as e:
                detail = {
                    'teacher': tsc.teacher.name if tsc else 'Unknown',
                    'status': 'error',
                    'reason': str(e)
                }
                details.append(detail)
                skip_count += 1
    
    return {
        'success': promote_count,
        'skipped': skip_count,
        'details': details[:100]  # 最多返回100条详情记录
    } 

@staff_member_required
def import_scores_view(request):
    """
    成绩导入页面 - 同步处理版本
    """
    # 当前常规表单处理逻辑
    
    if request.method == 'POST':
        # 处理表单提交
        # ...表单验证代码...
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        
        # 保存上传的文件
        file = request.FILES['file']
        file_path = os.path.join(settings.MEDIA_ROOT, file.name)
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        # 获取其他表单数据
        teacher_id = request.POST.get('teacher_id')
        region_id = request.POST.get('region_id')
        sheet_name = request.POST.get('sheet', 'sheet1')  # 默认工作表名
        create_students = request.POST.get('create_students') == 'on'
        update_students = request.POST.get('update_students') == 'on'
        skip_teacher = request.POST.get('skip_teacher') == 'on'
        debug = request.POST.get('debug') == 'on'
        smart_match = request.POST.get('smart_match') == 'on'
        force = request.POST.get('force') == 'on'
        exam_id = request.POST.get('exam_id')
        exam_name = request.POST.get('exam_name')
        exam_type = request.POST.get('exam_type')
        # 确保从POST数据中获取semester
        semester = request.POST.get('semester')

        
        # 直接调用命令，同步执行
        try:
            call_command('import_scores',
                        file_path=file_path,
                        exam_id=exam_id,
                        exam_name=exam_name,
                        exam_type=exam_type,
                        semester=semester,  
                        teacher_id=teacher_id,
                        region_id=region_id,
                        sheet=sheet_name,
                        create_students=create_students,
                        update_students=update_students,
                        skip_teacher=skip_teacher,
                        debug=debug,
                        smart_match=smart_match,
                        force=force,
                        task_id=task_id)
            
            # 导入成功
            messages.success(request, f"成绩导入成功，任务ID: {task_id}")
            
        except Exception as e:
            # 导入失败，显示错误信息
            messages.error(request, f"导入失败: {str(e)}")
        
        # 重定向回导入页面
        return redirect('admin:import_scores')
    
    # 显示导入表单...
    return render(request, 'admin/import_scores.html', context)

@staff_member_required
def import_progress_view(request):
    """
    导入进度展示页面
    
    Args:
        request: HTTP请求对象
        
    Returns:
        渲染的进度页面
    """
    task_id = request.GET.get('task_id', '')
    return render(request, 'admin/import_progress.html', {
        'task_id': task_id,
        'title': '导入进度'
    })

@require_GET
def import_progress(request):
    """获取导入任务的进度信息"""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': '缺少task_id参数'}, status=400)
    
    # 添加请求信息日志
    print(f"收到进度请求: task_id={task_id}, client={request.META.get('REMOTE_ADDR')}")
    
    try:
        # 设置最大处理时间
        import time
        start_time = time.time()
        
        # 从缓存获取进度
        cache_key = f"task_progress_{task_id}"
        progress_data = cache.get(cache_key)
        
        # 如果缓存没有，尝试从文件读取
        if not progress_data:
            progress_file = os.path.join(settings.MEDIA_ROOT, 'progress', f"{task_id}.json")
            if os.path.exists(progress_file):
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
            else:
                # 返回默认进度信息
                progress_data = {
                    "status": "PENDING", 
                    "current": 0, 
                    "total": 100, 
                    "percent": 0,
                    "message": "等待任务开始...", 
                    "details": [], 
                    "errors": []
                }
                
        # 检查处理时间
        processing_time = time.time() - start_time
        if processing_time > 0.1:  # 如果处理超过100ms，记录日志
            print(f"进度API处理较慢: {processing_time:.2f}秒, taskId={task_id}")
            
        # 返回进度数据
        return JsonResponse(progress_data)
    except Exception as e:
        return JsonResponse({
            'error': f'获取进度失败: {str(e)}',
            'status': 'ERROR'
        }, status=500)

@staff_member_required
def debug_trigger_task(request):
    """
    用于调试的任务触发器
    
    Args:
        request: HTTP请求对象
        
    Returns:
        处理结果的JSON响应
    """
    task_id = request.GET.get('task_id', str(uuid.uuid4()))
    action = request.GET.get('action', 'start')
    
    if action == 'start':
        # 模拟启动一个任务
        # 实际实现中，您应该调用真实的任务处理函数
        return JsonResponse({
            'status': 'success',
            'message': f'已启动调试任务 {task_id}',
            'task_id': task_id
        })
    elif action == 'complete':
        # 模拟完成一个任务
        return JsonResponse({
            'status': 'success',
            'message': f'已完成调试任务 {task_id}',
            'task_id': task_id
        })
    elif action == 'fail':
        # 模拟失败的任务
        return JsonResponse({
            'status': 'success',
            'message': f'已将调试任务 {task_id} 标记为失败',
            'task_id': task_id
        })
    else:
        return JsonResponse({
            'status': 'error',
            'message': f'未知操作: {action}'
        })

@staff_member_required
def test_progress_tracker(request):
    """
    测试进度跟踪页面
    
    Args:
        request: HTTP请求对象
        
    Returns:
        用于测试进度跟踪功能的页面
    """
    # 创建一个测试任务ID，如果没有提供
    task_id = request.GET.get('task_id', str(uuid.uuid4()))
    
    # 获取测试模式
    mode = request.GET.get('mode', 'demo')
    
    context = {
        'task_id': task_id,
        'title': '测试进度跟踪器',
        'mode': mode,
        'demo_steps': 10 if mode == 'demo' else 0
    }
    
    return render(request, 'admin/test_progress.html', context)

@staff_member_required
def direct_progress_view(request, task_id):
    """
    直接进度查看页面
    
    Args:
        request: HTTP请求对象
        task_id: 任务ID
        
    Returns:
        渲染的直接进度页面
    """
    if not task_id:
        messages.error(request, '缺少任务ID参数')
        return redirect('admin:index')
        
    return render(request, 'admin/direct_progress.html', {
        'task_id': task_id,
        'title': '任务进度查看',
        'auto_refresh': request.GET.get('refresh', 'true') == 'true'
    })

@staff_member_required
def simple_progress_test(request):
    """
    简单进度测试页面
    
    Args:
        request: HTTP请求对象
        
    Returns:
        简单的进度测试页面
    """
    # 创建一个随机任务ID
    task_id = str(uuid.uuid4())
    
    # 简单的测试上下文
    context = {
        'task_id': task_id,
        'title': '简单进度测试',
        'timestamp': timezone.now().isoformat()
    }
    
    return render(request, 'admin/simple_progress.html', context)

@staff_member_required
def start_simple_test(request):
    """
    启动简单测试任务
    
    Args:
        request: HTTP请求对象
        
    Returns:
        JSON响应或重定向到测试进度页面
    """
    # 创建新的任务ID
    task_id = str(uuid.uuid4())
    
    # 获取任务持续时间参数（默认10秒）
    duration = int(request.GET.get('duration', 10))
    
    # 获取任务步骤数（默认5步）
    steps = int(request.GET.get('steps', 5))
    
    # 是否要求JSON响应
    json_response = request.GET.get('json', 'false') == 'true'
    
    # 模拟启动一个简单测试任务
    # 实际项目中应该启动一个真实的后台任务
    
    if json_response:
        return JsonResponse({
            'status': 'success',
            'message': '简单测试任务已启动',
            'task_id': task_id,
            'details': {
                'duration': duration,
                'steps': steps,
                'start_time': timezone.now().isoformat()
            }
        })
    else:
        # 重定向到进度查看页面
        return redirect(f"{reverse('simple_progress_test')}?task_id={task_id}&duration={duration}&steps={steps}")

@staff_member_required
def check_simple_test(request):
    """
    检查简单测试任务进度
    
    Args:
        request: HTTP请求对象
        
    Returns:
        包含任务进度信息的JSON响应
    """
    task_id = request.GET.get('task_id', '')
    if not task_id:
        return JsonResponse({
            'status': 'error',
            'message': '缺少任务ID参数'
        })
    
    # 在实际应用中，应该从存储中(如Redis或数据库)获取任务进度
    # 这里只返回模拟数据
    
    # 获取当前时间，用于模拟进度计算
    current_time = timezone.now()
    
    # 获取任务开始时间(这里模拟一个开始时间)
    # 在实际应用中应该从存储中获取真实的开始时间
    start_time = current_time - timezone.timedelta(seconds=30)
    
    # 获取任务配置参数(在实际应用中应该从存储中获取)
    duration = int(request.GET.get('duration', 10))
    steps = int(request.GET.get('steps', 5))
    
    # 计算经过的时间(秒)
    elapsed_seconds = (current_time - start_time).total_seconds()
    
    # 计算进度百分比(0-100)
    progress_percent = min(100, int((elapsed_seconds / duration) * 100))
    
    # 计算当前步骤
    current_step = min(steps, int((progress_percent / 100) * steps) + 1)
    
    # 确定任务状态
    task_status = 'running'
    if progress_percent >= 100:
        task_status = 'completed'
    
    # 构建响应数据
    response_data = {
        'status': 'success',
        'task_id': task_id,
        'progress': {
            'percent': progress_percent,
            'current_step': current_step,
            'total_steps': steps,
            'elapsed_time': elapsed_seconds,
            'status': task_status,
            'message': f'正在执行步骤 {current_step}/{steps}' if task_status == 'running' else '任务已完成'
        }
    }
    
    return JsonResponse(response_data)

def run_import_task_async(file_path, exam_id, exam_name, exam_type, semester_id, teacher_id, 
                         region_id, sheet_name, create_students, update_students, 
                         skip_teacher, debug, smart_match, force, task_id):
    """
    异步执行成绩导入任务。
    
    Args:
        file_path: 文件路径
        exam_id: 考试ID
        exam_name: 考试名称
        exam_type: 考试类型
        semester_id: 学期ID字符串
        teacher_id: 教师ID
        region_id: 区域ID
        sheet_name: Excel工作表名称
        create_students: 是否创建新学生
        update_students: 是否更新学生信息
        skip_teacher: 是否跳过教师关联
        debug: 是否开启调试模式
        smart_match: 是否启用智能匹配
        force: 是否强制导入
        task_id: 任务ID
    """
    # 注意：现在我们直接接收semester_id字符串，而不是Semester对象
    
    from django.core.management import call_command
    call_command('import_scores',
                file_path=file_path,
                exam_id=exam_id,
                exam_name=exam_name,
                exam_type=exam_type,
                semester=semester_id,  # 直接传递字符串ID
                teacher_id=teacher_id,
                region_id=region_id,
                sheet=sheet_name,
                create_students=create_students,
                update_students=update_students,
                skip_teacher=skip_teacher,
                debug=debug,
                smart_match=smart_match,
                force=force,
                task_id=task_id)

def debug_form_data(request):
    """表单调试视图"""
    # 从会话中获取保存的表单数据(需要在提交处理时保存)
    form_data = request.session.get('last_form_data', {})
    return render(request, 'admin/debug_form.html', {'form_data': form_data})

def debug_progress_file(request, task_id):
    """直接显示进度文件内容"""
    import json
    import os
    from django.conf import settings
    from django.http import HttpResponse
    
    progress_file = os.path.join(settings.MEDIA_ROOT, 'progress', f"{task_id}.json")
    
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            content = f.read()
        return HttpResponse(f"<pre>{content}</pre>")
    else:
        return HttpResponse(f"进度文件不存在: {progress_file}")

def test_task_launch(request):
    """测试任务启动"""
    task_id = str(uuid.uuid4())
    
    # 创建测试文件
    test_file = os.path.join(settings.MEDIA_ROOT, 'test_data.txt')
    with open(test_file, 'w') as f:
        f.write("测试数据")
    
    # 启动简单测试任务
    thread = threading.Thread(
        target=run_import_task_async,
        args=(test_file, "TEST-001", "测试考试", "TEST", "2022-2023-1", 
              "T001", "6", "Sheet1", False, False, 
              True, True, False, False, task_id)
    )
    thread.daemon = True
    thread.start()
    
    return render(request, 'admin/test_task_launch.html', {
        'task_id': task_id,
        'title': '测试任务启动'
    })
