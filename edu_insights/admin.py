from django.contrib import admin
from .models import StudentScoreFeatures
from django import forms
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.urls import path, reverse
from django.shortcuts import render
from core.models import Semester, Grade, Exam, Student, Score, Subject
from django.db.models import Avg, StdDev, Max, Min, Q
from core.admin_site import admin_site


# 定义表单
class StudentFeatureGenerationForm(forms.Form):
    """成绩特征生成表单"""
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.all().order_by('-start_date'),
        label='学期',
        required=True
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.all().order_by('grade_level'),
        label='年级',
        required=False,
        help_text='可选，不选则处理所有年级'
    )
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.none(),  # 初始为空，由JS动态填充
        label='考试',
        required=False,
        help_text='可选，不选则处理所有考试'
    )
    regenerate_existing = forms.BooleanField(
        label='重新生成已有特征',
        required=False,
        initial=False,
        help_text='选中则会更新已有的特征数据，否则只处理新数据'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义年级显示方式
        self.fields['grade'].label_from_instance = lambda obj: f"{obj.grade_level}年级"
        
        # 获取唯一的年级级别
        # 这里改用Python处理而不是在数据库层面
        grade_ids = {}
        for grade in Grade.objects.all().order_by('grade_level'):
            if grade.grade_level not in grade_ids:
                grade_ids[grade.grade_level] = grade.pk
        
        # 使用过滤后的ID列表
        self.fields['grade'].queryset = Grade.objects.filter(
            pk__in=list(grade_ids.values())
        ).order_by('grade_level')
        
        # 如果已提交数据且选择了学期
        if 'semester' in self.data and 'grade' in self.data:
            try:
                semester_id = int(self.data.get('semester'))
                grade_id = int(self.data.get('grade')) if self.data.get('grade') else None
                
                # 根据学期和年级（如果有）筛选考试
                exam_query = Exam.objects.filter(score__semester_id=semester_id)
                if grade_id:
                    exam_query = exam_query.filter(score__student__current_grade_id=grade_id)
                
                self.fields['exam'].queryset = exam_query.distinct()
            except (ValueError, TypeError):
                pass

# 定义管理类
class StudentScoreFeaturesAdmin(admin.ModelAdmin):
    """学生成绩特征管理"""
    list_display = ['student', 'semester', 'avg_raw_score', 'class_rank', 'grade_rank', 
                   'county_rank', 'best_subject', 'weakest_subject']
    list_filter = ['semester', 'learning_pattern_cluster']
    search_fields = ['student__name', 'student__student_id']
    
    def get_urls(self):
        """添加特征生成的URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'generate-features/', 
                self.admin_site.admin_view(self.generate_features_view), 
                name='edu_insights_studentscorefeatures_generate_features'
            ),
        ]
        return custom_urls + urls
    
    def generate_features_view(self, request):
        """特征生成视图"""
        if request.method == 'POST':
            form = StudentFeatureGenerationForm(request.POST)
            if form.is_valid():
                semester = form.cleaned_data['semester']
                grade = form.cleaned_data['grade']
                exam = form.cleaned_data['exam']
                regenerate = form.cleaned_data['regenerate_existing']
                
                # 执行特征生成
                result = self.generate_features(
                    semester=semester,
                    grade=grade,
                    exam=exam,
                    regenerate=regenerate
                )
                
                messages.success(request, f"成功生成 {result['success_count']} 条学生成绩特征记录。")
                if result['error_count'] > 0:
                    messages.warning(request, f"有 {result['error_count']} 条记录生成失败。")
                
                # 重定向到列表页
                return HttpResponseRedirect(
                    reverse('education_admin:edu_insights_studentscorefeatures_changelist')
                )
        else:
            form = StudentFeatureGenerationForm()
        
        # 渲染表单
        context = {
            'title': '生成学生成绩特征',
            'form': form,
            'opts': self.model._meta,
            **self.admin_site.each_context(request),
        }
        return render(request, 'admin/generate_features_form.html', context)
    
    def generate_features(self, semester, grade=None, exam=None, regenerate=False):
        """
        生成学生成绩特征
        
        Args:
            semester: 学期对象
            grade: 可选，年级对象
            exam: 可选，考试对象
            regenerate: 是否重新生成已有特征
            
        Returns:
            dict: 包含成功和失败计数的结果字典
        """
        # 筛选条件
        score_filter = Q(semester_id=semester.semester_id)
        if grade:
            score_filter &= Q(student__current_grade=grade)
        if exam:
            score_filter &= Q(exam=exam)
        
        # 获取符合条件的成绩记录
        scores = Score.objects.filter(score_filter)
        
        # 按学生分组处理
        student_ids = scores.values_list('student', flat=True).distinct()
        
        success_count = 0
        error_count = 0
        
        for student_id in student_ids:
            try:
                # 获取学生对象
                student = Student.objects.get(student_id=student_id)
                
                # 获取或创建特征记录
                feature, created = StudentScoreFeatures.objects.get_or_create(
                    student=student,
                    semester=semester,
                    defaults={
                        'avg_raw_score': 0,
                        'std_dev_score': 0,
                        'max_score': 0,
                        'min_score': 0,
                        'score_range': 0,
                        'class_rank': 0,
                        'grade_rank': 0,
                        'percentile_in_grade': 0,
                        'deviation_from_class_avg': 0,
                        'z_score_avg': 0,
                        'subject_variance': 0,
                        'main_subjects_avg': 0,
                        'minor_subjects_avg': 0,
                        'weighted_performance_index': 0,
                    }
                )
                
                # 如果是新创建的或者需要重新生成
                if created or regenerate:
                    # 计算学生的成绩特征
                    student_scores = scores.filter(student=student)
                    
                    # 计算基础统计特征
                    score_stats = student_scores.aggregate(
                        avg=Avg('raw_score'),
                        std=StdDev('raw_score'),
                        max=Max('raw_score'),
                        min=Min('raw_score')
                    )
                    
                    feature.avg_raw_score = score_stats['avg'] or 0
                    feature.std_dev_score = score_stats['std'] or 0
                    feature.max_score = score_stats['max'] or 0
                    feature.min_score = score_stats['min'] or 0
                    feature.score_range = feature.max_score - feature.min_score
                    
                    # 计算排名
                    self._calculate_rankings(feature, semester, student_scores)
                    
                    # 计算学科特征
                    self._calculate_subject_features(feature, student_scores)
                    
                    # 保存特征记录
                    feature.save()
                    success_count += 1
                
            except Exception as e:
                print(f"处理学生 {student_id} 特征时出错: {str(e)}")
                error_count += 1
        
        return {
            'success_count': success_count,
            'error_count': error_count
        }
        
    def _calculate_rankings(self, feature, semester, student_scores):
        """计算学生各种排名"""
        student = feature.student
        
        # 计算班级排名
        class_scores = Score.objects.filter(
            student__current_class=student.current_class,
            semester_id=semester.semester_id
        ).values('student').annotate(avg_score=Avg('raw_score')).order_by('-avg_score')
        
        # 班级排名和百分位
        student_avg = next((s['avg_score'] for s in class_scores if s['student'] == student.student_id), 0)
        feature.class_rank = next((i+1 for i, s in enumerate(class_scores) if s['student'] == student.student_id), 0)
        class_avg = class_scores.aggregate(Avg('avg_score'))['avg_score__avg'] or 0
        feature.deviation_from_class_avg = student_avg - class_avg
        
        # 计算年级排名
        grade_scores = Score.objects.filter(
            student__current_grade=student.current_grade,
            semester_id=semester.semester_id
        ).values('student').annotate(avg_score=Avg('raw_score')).order_by('-avg_score')
        
        feature.grade_rank = next((i+1 for i, s in enumerate(grade_scores) if s['student'] == student.student_id), 0)
        total_students = grade_scores.count()
        if total_students > 0:
            feature.percentile_in_grade = ((total_students - feature.grade_rank) / total_students) * 100
            
        # 计算区县排名
        try:
            county_students = Student.objects.filter(
                region__parent_id=student.region.parent_id,
                current_grade__grade_level=student.current_grade.grade_level
            )
            county_scores = Score.objects.filter(
                student__in=county_students,
                semester_id=semester.semester_id
            ).values('student').annotate(avg_score=Avg('raw_score')).order_by('-avg_score')
            
            feature.county_rank = next((i+1 for i, s in enumerate(county_scores) if s['student'] == student.student_id), 0)
            total_county_students = county_scores.count()
            if total_county_students > 0:
                feature.county_percentile = ((total_county_students - feature.county_rank) / total_county_students) * 100
        except:
            # 区县排名计算失败，不影响其他特征
            pass
            
    def _calculate_subject_features(self, feature, student_scores):
        """计算学科相关特征"""
        # 按学科分组计算
        subject_scores = {}
        for score in student_scores:
            if score.subject_id not in subject_scores:
                subject_scores[score.subject_id] = []
            subject_scores[score.subject_id].append(score.raw_score)
        
        # 计算各学科平均分
        subject_avgs = {}
        for subject_id, scores in subject_scores.items():
            subject_avgs[subject_id] = sum(scores) / len(scores) if scores else 0
            
        # 找出最优和最弱学科
        if subject_avgs:
            best_subject_id = max(subject_avgs.items(), key=lambda x: x[1])[0]
            weakest_subject_id = min(subject_avgs.items(), key=lambda x: x[1])[0]
            
            # 设置最优和最弱学科
            feature.best_subject_id = best_subject_id
            feature.weakest_subject_id = weakest_subject_id
            
            # 计算学科方差
            if len(subject_avgs) > 1:
                import numpy as np
                feature.subject_variance = np.var(list(subject_avgs.values()))
            else:
                feature.subject_variance = 0
                
            # 计算主科和副科平均分
            main_subjects = Subject.objects.filter(subject_type='MAIN', subject_id__in=subject_avgs.keys())
            minor_subjects = Subject.objects.filter(subject_type='MINOR', subject_id__in=subject_avgs.keys())
            
            main_subject_scores = [subject_avgs[s.subject_id] for s in main_subjects]
            minor_subject_scores = [subject_avgs[s.subject_id] for s in minor_subjects]
            
            feature.main_subjects_avg = sum(main_subject_scores) / len(main_subject_scores) if main_subject_scores else 0
            feature.minor_subjects_avg = sum(minor_subject_scores) / len(minor_subject_scores) if minor_subject_scores else 0

    def changelist_view(self, request, extra_context=None):
        """添加生成特征按钮到列表页"""
        extra_context = extra_context or {}
        extra_context['title'] = '学生成绩特征管理'
        return super().changelist_view(request, extra_context)
    
    # 添加操作
    actions = ['batch_generate_features']
    
    def batch_generate_features(self, request, queryset):
        """批量生成特征的动作"""
        return HttpResponseRedirect(
            reverse('admin:edu_insights_studentscorefeatures_generate_features')
        )
    batch_generate_features.short_description = "生成成绩特征"

# 注册到默认的管理站点
admin_site.register(StudentScoreFeatures, StudentScoreFeaturesAdmin)

