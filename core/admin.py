"""
Django Admin 配置模块。

此模块定义了系统中所有模型的 Admin 界面配置，包括字段显示、筛选、搜索和自定义操作。
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Region, Semester, School, Grade, Class, 
    Teacher, TeacherTeam, Student, Family,
    Subject, Exam, Score, EvaluationMetrics, ValueAddedEvaluation, SubjectRelation, DataImportTool,
    TeacherHistory, TeacherSubjectClass
)
from .admin_site import admin_site
from django.contrib.admin import AdminSite, SimpleListFilter
from .admin_imports import ImportDataAdmin
from django.urls import path
from django.db.models import Count, Case, When, IntegerField, Q, Value, F, OuterRef
from django.db import transaction
from django.utils import timezone

class BaseAdmin(admin.ModelAdmin):
    """
    基础管理界面类，为所有管理界面提供通用功能。
    
    Args:
        admin.ModelAdmin: Django的ModelAdmin基类
    
    Returns:
        管理界面配置类实例
    """
    list_per_page = 20  # 每页显示记录数
    
    def get_readonly_fields(self, request, obj=None):
        """
        获取只读字段列表。
        
        Args:
            request: HTTP请求对象
            obj: 当前对象实例，新建时为None
            
        Returns:
            只读字段列表
        """
        # 如果是新建对象，返回空列表
        if obj is None:
            return []
        # 如果对象已存在，主键设为只读
        return ['id'] if 'id' in self.fields else []


class RegionAdmin(BaseAdmin):
    """
    区域管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        区域管理界面配置类实例
    """
    list_display = ['region_id', 'region_name', 'level', 'parent_id', 'description']
    list_filter = ['level']
    search_fields = ['region_name', 'region_id']
    ordering = ['region_id']


class SemesterAdmin(BaseAdmin):
    """
    学期管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        学期管理界面配置类实例
    """
    list_display = ['semester_id', 'year', 'term', 'start_date', 'end_date', 'status']
    list_filter = ['year', 'term', 'status']
    search_fields = ['semester_id', 'year']
    ordering = ['year', 'term']


class SchoolAdmin(BaseAdmin):
    """
    学校管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        学校管理界面配置类实例
    """
    list_display = ['school_id', 'school_name', 'school_type', 'school_nature', 
                   'principal', 'region', 'status']
    list_filter = ['school_type', 'school_nature', 'region', 'status']
    search_fields = ['school_id', 'school_name', 'principal']
    ordering = ['region', 'school_type', 'school_id']


class GradeAdmin(BaseAdmin):
    """
    年级管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        年级管理界面配置类实例
    """
    list_display = ['grade_id', 'grade_name', 'school', 'grade_level', 'semester']
    list_filter = ['school', 'grade_level', 'semester']
    search_fields = ['grade_id', 'grade_name']
    ordering = ['school', 'grade_level']


class ClassAdmin(BaseAdmin):
    """
    班级管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        班级管理界面配置类实例
    """
    list_display = ['class_id', 'class_name', 'grade', 'teacher_id', 'capacity', 'status']
    list_filter = ['grade__school', 'grade', 'status']
    search_fields = ['class_id', 'class_name', 'teacher_id']
    ordering = ['grade', 'class_name']
    
    def grade_school(self, obj):
        """
        获取班级所属学校名称。
        
        Args:
            obj: 班级对象实例
            
        Returns:
            学校名称字符串
        """
        return obj.grade.school.school_name
    grade_school.short_description = '学校'


# 添加自定义过滤器类
class DuplicateTeacherFilter(SimpleListFilter):
    """
    教师重复记录过滤器。
    
    Args:
        SimpleListFilter: Django过滤器基类
    
    Returns:
        过滤器实例
    """
    title = '重复记录'
    parameter_name = 'has_duplicate'
    
    def lookups(self, request, model_admin):
        """
        定义过滤选项。
        
        Args:
            request: HTTP请求对象
            model_admin: 管理对象
            
        Returns:
            过滤选项元组列表
        """
        return (
            ('yes', '有重复记录'),
            ('no', '无重复记录'),
        )
    
    def queryset(self, request, queryset):
        """
        根据过滤选项筛选查询集。
        
        Args:
            request: HTTP请求对象
            queryset: 原始查询集
            
        Returns:
            过滤后的查询集
        """
        # 获取重复记录的教师
        if self.value() == 'yes':
            # 先获取所有教师的名称和学校计数
            duplicates = queryset.values('name', 'current_school').annotate(
                count=Count('teacher_id')
            ).filter(count__gt=1)
            
            # 过滤出匹配这些名称和学校的教师
            duplicate_teachers = []
            for dup in duplicates:
                teachers = queryset.filter(
                    name=dup['name'], 
                    current_school=dup['current_school']
                )
                duplicate_teachers.extend([t.teacher_id for t in teachers])
            
            return queryset.filter(teacher_id__in=duplicate_teachers)
        
        elif self.value() == 'no':
            # 先获取所有教师的名称和学校计数
            duplicates = queryset.values('name', 'current_school').annotate(
                count=Count('teacher_id')
            ).filter(count__gt=1)
            
            # 过滤出匹配这些名称和学校的教师
            duplicate_teachers = []
            for dup in duplicates:
                teachers = queryset.filter(
                    name=dup['name'], 
                    current_school=dup['current_school']
                )
                duplicate_teachers.extend([t.teacher_id for t in teachers])
            
            return queryset.exclude(teacher_id__in=duplicate_teachers)
        
        return queryset


class TeacherHistoryInline(admin.TabularInline):
    """教师历史记录内联显示"""
    model = TeacherHistory
    extra = 0
    readonly_fields = ['history_id', 'semester', 'subject', 'class_field', 'status']
    fields = ['semester', 'subject', 'school', 'grade', 'class_field', 'is_class_teacher', 'status']
    can_delete = False
    max_num = 0  # 禁止通过Admin添加


class TeacherAdmin(BaseAdmin):
    """
    教师管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        教师管理界面配置类实例
    """
    list_display = ['teacher_id', 'name', 'gender', 'current_school', 
                   'qualification', 'status', 'duplicate_count']
    list_filter = ['gender', 'current_school', 'qualification', 'status', DuplicateTeacherFilter]
    search_fields = ['teacher_id', 'name', 'phone', 'email']
    ordering = ['current_school', 'name']
    actions = ['merge_duplicate_teachers', 'rebuild_history_records']
    
    # 添加历史记录内联
    inlines = [TeacherHistoryInline]  # 可能需要添加到现有inlines列表
    
    def get_queryset(self, request):
        """
        获取优化的查询集，附加重复计数。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            优化的查询集
        """
        queryset = super().get_queryset(request)
        # 添加一个重复计数字段
        duplicate_counts = queryset.values('name', 'current_school').annotate(
            count=Count('teacher_id')
        ).filter(count__gt=1)
        
        # 创建一个映射，以便快速查找
        dup_map = {(d['name'], d['current_school']): d['count'] 
                  for d in duplicate_counts}
        
        # 使用Case/When为每个教师添加duplicate_count
        conditions = []
        for (name, school_id), count in dup_map.items():
            conditions.append(
                When(
                    Q(name=name, current_school=school_id),
                    then=Value(count)
                )
            )
        
        # 如果有条件，则应用它们
        if conditions:
            queryset = queryset.annotate(
                duplicate_count=Case(
                    *conditions,
                    default=Value(1),
                    output_field=IntegerField()
                )
            )
        else:
            # 如果没有重复记录，则所有教师的duplicate_count为1
            queryset = queryset.annotate(
                duplicate_count=Value(1, output_field=IntegerField())
            )
        
        return queryset
    
    def duplicate_count(self, obj):
        """
        显示教师在当前学校的重复记录数。
        
        Args:
            obj: 教师对象
            
        Returns:
            格式化的重复计数
        """
        if hasattr(obj, 'duplicate_count') and obj.duplicate_count > 1:
            return format_html('<span style="color:red">{}</span>', obj.duplicate_count)
        return '1'
    duplicate_count.short_description = '重复记录'
    
    def merge_duplicate_teachers(self, request, queryset):
        """
        合并选定的重复教师记录。
        
        保留最旧的记录，将所有关联转移给该记录，然后删除其他重复记录。
        
        Args:
            request: HTTP请求对象
            queryset: 选中的教师查询集
            
        Returns:
            无
        """
        # 按姓名和学校分组教师
        teachers_by_name = {}
        for teacher in queryset:
            key = (teacher.name, teacher.current_school_id)
            if key not in teachers_by_name:
                teachers_by_name[key] = []
            teachers_by_name[key].append(teacher)
        
        merged_count = 0
        with transaction.atomic():
            for (name, school_id), teachers in teachers_by_name.items():
                if len(teachers) > 1:
                    # 选择保留的教师(使用pk替代id)
                    primary_teacher = min(teachers, key=lambda t: t.pk)
                    duplicate_teachers = [t for t in teachers if t.pk != primary_teacher.pk]
                    
                    for dup_teacher in duplicate_teachers:
                        # 转移所有班级关联
                        for cls in dup_teacher.classes.all():
                            if not primary_teacher.classes.filter(pk=cls.pk).exists():
                                primary_teacher.classes.add(cls)
                        
                        # 转移TeacherSubject关联
                        from core.models import TeacherSubject
                        for ts in TeacherSubject.objects.filter(teacher=dup_teacher):
                            # 检查主教师是否已有此学科关联
                            if not TeacherSubject.objects.filter(
                                teacher=primary_teacher, 
                                subject=ts.subject
                            ).exists():
                                # 创建新关联
                                ts.pk = None  # 复制对象
                                ts.teacher = primary_teacher
                                ts.save()
                            
                            # 删除重复关联
                            ts.delete()
                        
                        # 如果有其他需要转移的关联，在这里添加代码
                        
                        # 删除重复教师
                        dup_teacher.delete()
                        merged_count += 1
        
        self.message_user(
            request, 
            f"成功合并了 {merged_count} 条重复的教师记录。", 
            level='SUCCESS'
        )
    merge_duplicate_teachers.short_description = "合并选定的重复教师记录"
    
    def rebuild_history_records(self, request, queryset):
        """重建选中教师的历史记录"""
        success_count = 0
        for teacher in queryset:
            # 调用重建历史记录的逻辑
            success = self._rebuild_teacher_history(teacher)
            if success:
                success_count += 1
                
        self.message_user(
            request, 
            f"成功重建 {success_count} 名教师的历史记录。", 
            level='SUCCESS'
        )
    rebuild_history_records.short_description = "重建选中教师的历史记录"
    
    def _rebuild_teacher_history(self, teacher):
        """
        重建教师历史记录的内部方法
        
        Args:
            teacher: 教师对象
            
        Returns:
            bool: 操作是否成功
        """
        try:
            with transaction.atomic():
                # 删除现有历史记录
                TeacherHistory.objects.filter(teacher=teacher).delete()
                
                # 根据任课记录重建历史
                tsc_records = TeacherSubjectClass.objects.filter(
                    teacher=teacher
                ).select_related('semester', 'subject', 'class_obj', 'class_obj__grade')
                
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


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """
    学生管理界面配置。
    
    Args:
        admin.ModelAdmin: Django的ModelAdmin基类
    
    Returns:
        学生管理界面配置类实例
    """
    list_display = ('name', 'gender', 'admin_id_number', 'masked_school_student_id', 'current_school', 'status')
    list_filter = ['gender', 'current_school', 'current_grade', 'status']
    search_fields = ['student_id', 'name', 'phone', 'email']
    ordering = ['current_school', 'current_grade', 'current_class', 'name']
    
    def get_queryset(self, request):
        """
        获取优化的查询集。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            优化的查询集
        """
        # 使用select_related减少查询次数
        return super().get_queryset(request).select_related(
            'current_school', 'current_grade', 'current_class'
        )


class SubjectAdmin(BaseAdmin):
    """
    学科管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        学科管理界面配置类实例
    """
    list_display = ['subject_id', 'subject_name', 'subject_type', 'description']
    list_filter = ['subject_type']
    search_fields = ['subject_id', 'subject_name']
    ordering = ['subject_type', 'subject_name']


class ExamAdmin(BaseAdmin):
    """
    考试管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        考试管理界面配置类实例
    """
    list_display = ['exam_id', 'exam_name', 'exam_type', 'subject', 
                   'grade', 'semester', 'start_time', 'end_time', 'total_score']
    list_filter = ['exam_type', 'subject', 'grade', 'semester']
    search_fields = ['exam_id', 'exam_name']
    ordering = ['-start_time']
    date_hierarchy = 'start_time'


class ScoreAdmin(BaseAdmin):
    """
    成绩管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        成绩管理界面配置类实例
    """
    list_display = ['score_id', 'student', 'exam', 'subject', 
                   'raw_score', 'standard_score', 'percentile',
                   'grade', 'teacher', 'status']
    list_filter = ['exam', 'subject', 'grade', 'status', 'teacher']
    search_fields = ['score_id', 'student__name', 'student__student_id']
    ordering = ['exam', 'student']
    
    def get_queryset(self, request):
        """
        获取优化的查询集。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            优化的查询集
        """
        return super().get_queryset(request).select_related(
            'student', 'exam', 'subject', 'teacher'
        )


class EvaluationMetricsAdmin(BaseAdmin):
    """
    评价指标管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        评价指标管理界面配置类实例
    """
    list_display = ['metric_id', 'metric_name', 'metric_type', 'weight', 'status']
    list_filter = ['metric_type', 'status']
    search_fields = ['metric_id', 'metric_name']
    ordering = ['metric_type', 'weight']


class ValueAddedEvaluationAdmin(BaseAdmin):
    """
    增值评价管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        增值评价管理界面配置类实例
    """
    list_display = ['eval_id', 'target_type', 'target_id', 'subject', 
                   'semester', 'base_score', 'current_score', 
                   'added_value', 'added_value_display', 'status']
    list_filter = ['target_type', 'subject', 'semester', 'status']
    search_fields = ['eval_id', 'target_id']
    ordering = ['semester', 'target_type', 'target_id']
    
    def added_value_display(self, obj):
        """
        格式化增值分数的显示效果。
        
        Args:
            obj: 增值评价对象实例
            
        Returns:
            格式化后的HTML字符串
        """
        if obj.added_value > 0:
            return format_html('<span style="color:green">+{:.2f}</span>', obj.added_value)
        elif obj.added_value < 0:
            return format_html('<span style="color:red">{:.2f}</span>', obj.added_value)
        return format_html('{:.2f}', obj.added_value)
    added_value_display.short_description = '增值效果'


class SubjectRelationAdmin(BaseAdmin):
    """
    学科关联管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        学科关联管理界面配置类实例
    """
    list_display = ['relation_id', 'subject1', 'subject2', 'relation_type']
    list_filter = ['relation_type']
    search_fields = ['relation_id', 'subject1', 'subject2']
    ordering = ['relation_type', 'relation_id']


# 添加TeacherTeam管理类
class TeacherTeamAdmin(BaseAdmin):
    """
    教师团队管理界面配置。
    
    Args:
        BaseAdmin: 基础管理界面类
    
    Returns:
        教师团队管理界面配置类实例
    """
    list_display = ['team_id', 'team_name', 'leader', 'school', 'subject', 'status']
    list_filter = ['school', 'subject', 'status']
    search_fields = ['team_id', 'team_name', 'leader__name']
    ordering = ['team_id']


# 添加Family管理类
class FamilyAdmin(admin.ModelAdmin):
    """
    家庭信息管理界面配置。
    
    Args:
        admin.ModelAdmin: Django的ModelAdmin基类
    
    Returns:
        家庭信息管理界面配置类实例
    """
    list_display = ('family_id', 'family_name', 'phone', 'email', 'status')
    search_fields = ('family_id', 'family_name', 'phone')
    list_filter = ('status',)  # 移除不存在的income_level和region过滤器


# 使用自定义admin_site注册模型
admin_site.register(Region, RegionAdmin)
admin_site.register(Semester, SemesterAdmin)
admin_site.register(School, SchoolAdmin)
admin_site.register(Grade, GradeAdmin)
admin_site.register(Class, ClassAdmin)
admin_site.register(Teacher, TeacherAdmin)
admin_site.register(TeacherTeam, TeacherTeamAdmin)
admin_site.register(Family, FamilyAdmin)
admin_site.register(Subject, SubjectAdmin)
admin_site.register(SubjectRelation, SubjectRelationAdmin)
admin_site.register(Exam, ExamAdmin)
admin_site.register(Score, ScoreAdmin)
admin_site.register(EvaluationMetrics, EvaluationMetricsAdmin)
admin_site.register(ValueAddedEvaluation, ValueAddedEvaluationAdmin)

# 导入系统用户模型以注册到自定义站点
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)

# 改为使用代理模型
from .models import DataImportTool

class DataImportToolAdmin(ImportDataAdmin):
    """
    数据导入工具管理界面。
    
    使用代理模型提供专用的数据导入入口。
    """
    model = DataImportTool
    
    # 控制在Admin中的显示名称
    def get_model_perms(self, request):
        """
        返回一个字典，用于在admin索引页面显示此模型
        """
        return {
            'add': True,  # 修改为True允许添加操作
            'change': True,
            'delete': False,
            'view': True,
        }

# 使用代理模型注册
admin_site.register(DataImportTool, DataImportToolAdmin)

# 注释掉整个URL自定义部分
# 保存原始方法
# original_get_urls = admin_site.get_urls

# 定义新方法
# def get_urls():
#     urls = original_get_urls()
#     custom_urls = [
#         path('import-data/', DataImportAdmin(Exam, admin_site).import_view, name='import_data')
#     ]
#     return urls + custom_urls

# 替换原始方法
# admin_site.get_urls = get_urls

# 注册TeacherHistory为单独的管理界面
@admin.register(TeacherHistory)
class TeacherHistoryAdmin(admin.ModelAdmin):
    """教师历史记录管理"""
    list_display = ['teacher', 'school', 'semester', 'subject', 'class_field', 'status']
    list_filter = ['semester', 'status', 'school', 'subject']
    search_fields = ['teacher__name', 'teacher__teacher_id', 'school__school_name']
    readonly_fields = ['teacher', 'school', 'semester', 'subject', 'grade', 'class_field']


