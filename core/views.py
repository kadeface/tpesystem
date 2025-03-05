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

def import_scores_view(request):
    # 查看这个函数中使用的模板
    return render(request, 'core/import_scores.html', context)  # 实际模板路径在这里 

def import_progress(request):
    """返回当前导入进度"""
    progress_data = request.session.get('import_progress', {
        'current_step': 0,
        'progress': 0,
        'message': '未开始',
        'is_complete': False
    })
    return JsonResponse(progress_data) 