from rest_framework import viewsets, filters
from rest_framework.decorators import action
from .models import Region, Semester, School, Student, Score, Subject, Teacher, TeacherHistory, TeacherSubjectClass, Grade, Exam,Class
from .serializers import RegionSerializer, SemesterSerializer, SchoolSerializer, StudentSerializer, ScoreSerializer, SubjectSerializer, TeacherSerializer, ExamSerializer,GradeSerializer
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
from django.db import connection
import re
import logging
import traceback
from django.db.models import Q
import random
from datetime import datetime, timedelta

# 设置日志记录器
logger = logging.getLogger(__name__)

def infer_graduation_year(grade_id, graduation_grade=9):
    """
    根据 grade_id 推断毕业年份
    
    Args:
        grade_id: 格式如 G02_7_231，其中 7 是年级，231 是学期编码
        graduation_grade: 毕业年级（默认初中为9年级）
        
    Returns:
        毕业年份（整数）
        
    Raises:
        ValueError: 当grade_id格式无效时抛出
    """
    try:
        # 解析 grade_id
        parts = grade_id.split('_')
        if len(parts) != 3:
            raise ValueError("Invalid grade_id format")
        
        current_grade = int(parts[1])          # 当前年级（如7）
        term_code = parts[2]                    # 学期编码（如231）
        
        if len(term_code) != 3 or not term_code.isdigit():
            raise ValueError("Invalid term code")
        
        # 提取学年结束年份（如231中的23对应2023）
        year_suffix = int(term_code[:2])       # 学年结束年份的后两位（如23）
        current_year_end = 2000 + year_suffix  # 完整的学年结束年份（如2023）
        
        # 计算剩余学年数
        remaining_years = graduation_grade - current_grade
        if remaining_years < 0:
            raise ValueError("Current grade exceeds graduation grade")
        
        # 毕业年份 = 当前学年结束年份 + 剩余学年数
        graduation_year = current_year_end + remaining_years
        return graduation_year
    
    except Exception as e:
        print(f"Error processing grade_id {grade_id}: {e}")
        return None

class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    """区域API视图集"""
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    pagination_class = None  # 禁用此视图的分页
    
    def get_queryset(self):
        print("执行RegionViewSet.get_queryset方法")
        queryset = super().get_queryset()
        print(f"查询结果数量: {queryset.count()}")
        parent_id = self.request.query_params.get('parent_id')
        level = self.request.query_params.get('level')
        
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        if level:
            queryset = queryset.filter(level=level)
            
        print(f"过滤后结果数量: {queryset.count()}")
        return queryset

    def list(self, request, *args, **kwargs):
        # 添加日志
        print("RegionViewSet.list被调用")
        # 获取原始查询集
        queryset = self.get_queryset()
        print(f"查询结果: {list(queryset.values())}")
        
        # 调用父类方法完成响应
        return super().list(request, *args, **kwargs)

class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    """学科API视图集"""
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        subject_type = self.request.query_params.get('subject_type')
        
        if subject_type:
            queryset = queryset.filter(subject_type=subject_type)
            
        return queryset

class ExamViewSet(viewsets.ReadOnlyModelViewSet):
    """考试API视图集"""
    queryset = Exam.objects.all().select_related('grade', 'subject', 'semester')
    serializer_class = ExamSerializer
    
    def get_queryset(self):
        # 添加详细日志记录
        import json
        print("\n===== 考试查询开始 =====")
        print(f"请求参数: {dict(self.request.query_params)}")
        
        queryset = super().get_queryset()
        print(f"初始考试数量: {queryset.count()}")
        
        # 记录数据库中的所有考试ID示例
        sample_exams = list(queryset.values('exam_id', 'exam_name', 'grade_id')[:5])
        print(f"考试样本: {json.dumps(sample_exams, ensure_ascii=False)}")
        
        # 获取筛选参数
        subject_id = self.request.query_params.get('subject')
        grade_id = self.request.query_params.get('grade_id')
        education_stage = self.request.query_params.get('education_stage')
        
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
            print(f"按学科筛选后: {queryset.count()}个考试")
        
        # 处理学段筛选
        stage_from_grade = None
        graduation_grade = 9  # 默认初中
        
        if grade_id:
            # 从grade_id解析学段信息
            try:
                grade_level = int(grade_id.split('_')[1])
                if grade_level <= 6:
                    stage_from_grade = 'elementary'
                    graduation_grade = 6  # 小学毕业年级
                elif grade_level <= 9:
                    stage_from_grade = 'junior'
                    graduation_grade = 9  # 初中毕业年级
                else:
                    stage_from_grade = 'senior'
                    graduation_grade = 12  # 高中毕业年级
                print(f"从grade_id推断学段: {stage_from_grade}，毕业年级: {graduation_grade}")
            except (IndexError, ValueError) as e:
                print(f"从grade_id推断学段失败: {e}")
        
        # 优先使用请求中的education_stage参数，如果没有则使用从grade_id推断的值
        stage = education_stage or stage_from_grade
        if stage:
            print(f"使用学段筛选: {stage}")
            
            # 根据学段筛选考试ID
            from django.db.models import Q
            stage_filter = None
            
            if stage == 'elementary':
                # 小学考试ID通常包含P
                stage_filter = (
                    Q(exam_id__contains='P') | 
                    Q(grade__grade_level__in=['1','2','3','4','5','6'])
                )
            elif stage == 'junior':
                # 初中考试ID通常包含M
                stage_filter = (
                    Q(exam_id__contains='M') | 
                    Q(grade__grade_level__in=['7','8','9'])
                )
            elif stage == 'senior':
                # 高中考试ID通常包含H
                stage_filter = (
                    Q(exam_id__contains='H') | 
                    Q(grade__grade_level__in=['10','11','12'])
                )
            
            if stage_filter:
                queryset = queryset.filter(stage_filter)
                print(f"按学段筛选后: {queryset.count()}个考试")
        
        # 毕业年份筛选
        if grade_id:
            # 检查grade_id的格式
            print(f"筛选条件 grade_id: {grade_id}")
            
            try:
                # 使用正确的毕业年级参数推断毕业年份
                graduation_year = infer_graduation_year(grade_id, graduation_grade)
                if graduation_year:
                    print(f"推断毕业年份: {graduation_year}（使用毕业年级: {graduation_grade}）")
                    
                    # 将毕业年份转换为字符串
                    grad_year_str = str(graduation_year)
                    
                    # 构建Q对象进行OR查询
                    from django.db.models import Q
                    
                    # 按照指定规则筛选考试ID
                    # 1. 如果exam_id包含'M'或'P'，前4位应该是毕业年份
                    # 2. 如果exam_id包含'H'，后6位包含年份
                    exam_filter = (
                        # M类型考试ID，前4位是毕业年份
                        Q(exam_id__contains='M', exam_id__startswith=grad_year_str) |
                        # P类型考试ID，前4位是毕业年份
                        Q(exam_id__contains='P', exam_id__startswith=grad_year_str) |
                        # H类型考试ID，后6位包含年份
                        Q(exam_id__contains='H', exam_id__endswith=grad_year_str[-2:])
                    )
                    
                    # 应用筛选条件
                    queryset = queryset.filter(exam_filter)
                    
                    print(f"按毕业年份和考试ID格式筛选后: {queryset.count()}个考试")
                else:
                    print("无法推断毕业年份，不进行筛选")
            except Exception as e:
                print(f"处理grade_id出错: {e}")
                # 出错时不进行筛选，保留所有考试
        
        # 最终结果
        final_count = queryset.count()
        print(f"最终查询结果: {final_count}个考试")
        if final_count > 0:
            final_sample = list(queryset.values('exam_id', 'exam_name', 'grade_id')[:5])
            print(f"最终样本: {json.dumps(final_sample, ensure_ascii=False)}")
        print("===== 考试查询结束 =====\n")
        
        return queryset

    @action(detail=False, methods=['get'])
    def with_graduation_info(self, request):
        # 当前ExamListView的逻辑
        pass

class GradeViewSet(viewsets.ReadOnlyModelViewSet):
    """年级API视图集"""
    queryset = Grade.objects.all().select_related('school', 'semester')
    serializer_class = GradeSerializer
    pagination_class = None  # 禁用分页
    
    def get_queryset(self):
        queryset = super().get_queryset()
        school_id = self.request.query_params.get('school')
        stage = self.request.query_params.get('stage')
        
        if school_id:
            queryset = queryset.filter(school_id=school_id)
            
        if stage:
            # 根据学段过滤
            if stage == 'elementary':
                queryset = queryset.filter(grade_level__in=['1','2','3','4','5','6'])
            elif stage == 'junior':
                queryset = queryset.filter(grade_level__in=['7','8','9'])
            elif stage == 'senior':
                queryset = queryset.filter(grade_level__in=['10','11','12'])
        
        # 使用PostgreSQL的DISTINCT ON获取每个年级的最新记录
        # 排序优先级：年级级别 -> 学期(降序) -> ID(降序)
        return queryset.order_by(
            'grade_level',
            '-semester__semester_id',    # 学期号降序
            'grade_id'                       # ID降序作为最后的排序依据
        ).distinct('grade_level')

    @action(detail=False, methods=['get'])
    def with_graduation_info(self, request):
        """获取年级信息以及计算的毕业年份信息"""
        queryset = self.get_queryset()
        
        # 计算当前学年
        now = timezone.now()
        current_year = now.year
        current_month = now.month
        academic_year = current_year if current_month >= 9 else current_year - 1
        
        # 为每个年级添加毕业年份信息
        grades_with_info = []
        for grade in queryset:
            grade_data = GradeSerializer(grade).data
            try:
                grade_level = int(grade.grade_level)
                
                # 计算毕业年份
                if grade_level <= 6:  # 小学
                    years_to_graduation = 6 - grade_level
                    education_stage = 'elementary'
                    stage_display = '小学'
                elif grade_level <= 9:  # 初中
                    years_to_graduation = 9 - grade_level
                    education_stage = 'junior'
                    stage_display = '初中'
                else:  # 高中
                    years_to_graduation = 12 - grade_level
                    education_stage = 'senior'
                    stage_display = '高中'
                    
                graduation_year = academic_year + years_to_graduation
                
                # 添加信息到年级数据
                grade_data['graduation_year'] = graduation_year
                grade_data['education_stage'] = education_stage
                grade_data['stage_display'] = stage_display
                grade_data['graduation_info'] = f"{graduation_year}届{stage_display}"
                
            except (ValueError, TypeError):
                # 无法计算毕业年份
                grade_data['graduation_year'] = None
                grade_data['graduation_info'] = '未知'
                
            grades_with_info.append(grade_data)
        
        return Response(grades_with_info)

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
    # 定义上下文字典
    context = {}
    
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

def task_status_api(request):
    """任务状态API，返回进度跟踪信息"""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'status': 'error', 'message': '缺少任务ID'})
        
    # 尝试从缓存获取
    cache_key = f"task_progress_{task_id}"
    progress_data = cache.get(cache_key)
    
    # 如果缓存中没有，尝试从文件获取
    if not progress_data:
        progress_file = os.path.join(settings.MEDIA_ROOT, 'progress', f"{task_id}.json")
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
            except:
                pass
    
    if not progress_data:
        return JsonResponse({
            'status': 'error', 
            'message': '任务状态未找到',
            'progress': 0,
            'logs': ['任务状态未找到，可能任务ID无效或者任务已过期']
        })
    
    # 转换为API响应格式
    return JsonResponse({
        'status': progress_data.get('status', 'processing').lower(),
        'progress': progress_data.get('percent', 0),
        'processed_count': progress_data.get('current', 0),
        'logs': progress_data.get('details', []),
        'error': '\n'.join(progress_data.get('errors', [])),
        'start_time': progress_data.get('start_time', '未知')
    })

@staff_member_required
def simple_import_progress_view(request):
    """
    简化版导入进度查看页面
    """
    task_id = request.GET.get('task_id', '')
    return render(request, 'admin/simple_import_progress.html', {
        'task_id': task_id,
        'title': '导入状态查看'
    })

@staff_member_required
def static_progress_view(request):
    """完全静态的进度查看页面，不发送任何API请求"""
    task_id = request.GET.get('task_id', '')
    return render(request, 'admin/static_progress.html', {
        'task_id': task_id,
        'title': '静态任务状态'
    })

def debug_regions(request):
    """调试用API，直接返回区域数据和诊断信息"""
    try:
        # 获取当前区域记录数
        count = Region.objects.count()
        
        # 尝试获取所有区域数据
        regions = list(Region.objects.all().values('region_id', 'region_name'))
        
        # 如果没有数据，添加测试数据（仅用于诊断）
        if not regions:
            # 仅在DEBUG模式下添加测试数据
            if settings.DEBUG:
                try:
                    # 尝试添加一条测试数据
                    region = Region.objects.create(
                        region_id='test001',
                        region_name='测试区域',
                        level='city', 
                        description='测试描述'
                    )
                    regions = [{'region_id': region.region_id, 'region_name': region.region_name}]
                    return JsonResponse({
                        'status': 'success', 
                        'message': '成功创建测试数据',
                        'regions': regions,
                        'original_count': count
                    })
                except Exception as create_error:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'尝试创建测试数据失败: {str(create_error)}',
                        'regions': [],
                        'original_count': count
                    })
            
        return JsonResponse({
            'status': 'success',
            'message': f'找到{len(regions)}条区域记录',
            'regions': regions,
            'count': count
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'status': 'error',
            'message': f'获取区域数据时出错: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)

def raw_regions_debug(request):
    """直接从数据库返回区域原始数据"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM core_region")
        columns = [col[0] for col in cursor.description]
        regions = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return JsonResponse({'raw_regions': regions})

# 考试列表API视图
class ExamListView(APIView):
    def get(self, request):
        # 直接写入调试信息到文件
        with open('exam_debug.log', 'a', encoding='utf-8') as f:
            f.write(f"\n\n===== ExamListView 被调用 =====\n")
            f.write(f"请求参数: {dict(request.query_params)}\n")
        
        # 标准输出和标准错误
        print("\n\n***** ExamListView调试信息开始 *****", flush=True)
        print(f"请求参数: {dict(request.query_params)}", flush=True)
        print("***** ExamListView调试信息结束 *****\n\n", flush=True)
        
        import sys
        sys.stderr.write("\n\n***** ExamListView stderr 输出 *****\n\n")
        sys.stderr.flush()
        
        # 获取查询参数
        grade_id = request.query_params.get('grade_id')
        subject_id = request.query_params.get('subject')
        district_id = request.query_params.get('district')
        education_stage = request.query_params.get('education_stage')
        exam_type = request.query_params.get('exam_type')
        semester = request.query_params.get('semester')
        
        # 是否包含历史年级数据
        include_history = request.query_params.get('include_history') == 'true'
        
        # 基本查询集
        exams = Exam.objects.all()
        
        # 记录查询参数到文件
        with open('exam_debug.log', 'a', encoding='utf-8') as f:
            f.write(f"查询参数: grade_id={grade_id}, include_history={include_history}\n")
        
        # 始终应用毕业年份查询逻辑
        if grade_id:
            try:
                # 1. 从grade_id推断毕业年份
                graduation_year = infer_graduation_year(grade_id)
                
                if graduation_year:
                    with open('exam_debug.log', 'a', encoding='utf-8') as f:
                        f.write(f"从grade_id={grade_id}推断毕业年份: {graduation_year}\n")
                    
                    graduation_year_str = str(graduation_year)
                    
                    # 2. 通过考试ID格式匹配相同毕业年份的考试
                    from django.db.models import Q
                    
                    # 构建查询条件
                    query = Q()
                    
                    # 条件1: 带有M或P字符的考试ID，前四个字符是毕业年份
                    # 例如: 2025-M-xxxx 或 2025-P-xxxx
                    query |= Q(exam_id__startswith=graduation_year_str + '-') & (Q(exam_id__contains='-M-') | Q(exam_id__contains='-P-'))
                    
                    # 条件2: 带有H的考试ID，倒数第6到第2个字符是毕业年份
                    # 例如: xxxx-H-2025-xx
                    h_pattern = r'.*-H-.*' + graduation_year_str + r'.*'
                    query |= Q(exam_id__regex=h_pattern)
                    
                    # 条件3: 直接包含当前年级ID的考试
                    query |= Q(grade_id=grade_id)
                    
                    # 应用查询
                    exams = exams.filter(query)
                    
                    with open('exam_debug.log', 'a', encoding='utf-8') as f:
                        f.write(f"筛选出的包含毕业年份{graduation_year}的考试数量: {exams.count()}\n")
                        # 记录生成的SQL查询
                        f.write(f"SQL查询: {str(exams.query)}\n")
                        
                        # 记录前10个结果
                        f.write("找到的考试:\n")
                        for i, exam in enumerate(exams[:10]):
                            f.write(f"{i+1}. ID: {exam.exam_id}, 名称: {exam.exam_name}, 年级: {exam.grade_id}\n")
                else:
                    with open('exam_debug.log', 'a', encoding='utf-8') as f:
                        f.write(f"无法推断毕业年份，仅筛选当前年级考试\n")
                    
                    exams = exams.filter(grade_id=grade_id)
            except Exception as e:
                import traceback
                with open('exam_debug.log', 'a', encoding='utf-8') as f:
                    f.write(f"处理grade_id时出错: {e}\n")
                    f.write(traceback.format_exc())
                
                exams = exams.filter(grade_id=grade_id)
        
        # 序列化结果
        serializer = ExamSerializer(exams, many=True)
        
        # 返回结果前记录最终结果数量
        with open('exam_debug.log', 'a', encoding='utf-8') as f:
            f.write(f"最终返回考试数量: {len(serializer.data)}\n")
            f.write("===== ExamListView 处理完成 =====\n\n")
        
        return Response(serializer.data)

# 添加一个URL测试视图来确认routing配置正确
def test_exam_view(request):
    debug_info = {
        'message': '测试ExamListView路由成功',
        'params': dict(request.GET),
        'method': request.method,
        'path': request.path,
        'settings': {
            'DEBUG': getattr(settings, 'DEBUG', None),
            'LOGGING': str(getattr(settings, 'LOGGING', {}))[:100] + '...'  # 仅显示部分配置
        }
    }
    
    # 直接打印到控制台
    print("\n\n***** 测试视图被调用 *****")
    print(f"调试信息: {debug_info}")
    print("***** 测试视图结束 *****\n\n")
    
    # 返回详细响应
    return HttpResponse(f"<pre>{json.dumps(debug_info, indent=2)}</pre>", content_type="text/html")

def debug_exam_view(request):
    """简单的调试视图，直接响应详细的调试信息"""
    grade_id = request.GET.get('grade_id')
    include_history = request.GET.get('include_history') == 'true'
    
    debug_info = {
        '调试信息': '考试查询测试',
        '查询参数': {
            'grade_id': grade_id,
            'include_history': include_history
        }
    }
    
    # 如果提供了grade_id，尝试推断毕业年份
    if grade_id:
        try:
            graduation_year = infer_graduation_year(grade_id)
            debug_info['毕业年份'] = graduation_year
            
            # 展示会用于查询的模式
            if graduation_year:
                graduation_year_str = str(graduation_year)
                debug_info['查询模式'] = [
                    f"{graduation_year_str}-M-*", 
                    f"{graduation_year_str}-P-*",
                    f"*-H-*{graduation_year_str}*",
                    f"grade_id={grade_id}"
                ]
                
                # 执行实际查询，但仅用于调试
                from django.db.models import Q
                query = Q()
                query |= Q(exam_id__startswith=graduation_year_str + '-') & (Q(exam_id__contains='-M-') | Q(exam_id__contains='-P-'))
                h_pattern = r'.*-H-.*' + graduation_year_str + r'.*'
                query |= Q(exam_id__regex=h_pattern)
                query |= Q(grade_id=grade_id)
                
                exams = Exam.objects.filter(query)
                debug_info['查询结果数量'] = exams.count()
                
                # 提取前5个考试的信息
                exam_samples = []
                for exam in exams[:5]:
                    exam_samples.append({
                        'exam_id': exam.exam_id,
                        'exam_name': exam.exam_name,
                        'grade_id': exam.grade_id,
                    })
                debug_info['考试样本'] = exam_samples
        except Exception as e:
            debug_info['错误'] = str(e)
    
    # 返回格式化的JSON响应
    return HttpResponse(
        f"<pre>{json.dumps(debug_info, indent=2, ensure_ascii=False)}</pre>", 
        content_type="text/html; charset=utf-8"
    )

