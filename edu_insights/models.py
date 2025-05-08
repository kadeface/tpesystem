from django.db import models
import uuid
import os
import pandas as pd
import logging
from core.models import Student, Score
from django.db.models import Avg, StdDev, Max, Min
logger = logging.getLogger(__name__)

class AnalysisTask(models.Model):
    """
    分析任务模型
    
    用于跟踪学生成长画像分析任务的状态和进度
    
    Args:
        task_id: 任务唯一标识符
        status: 任务状态（等待中/运行中/已完成/失败）
        progress: 完成百分比 (0-100)
        params: 分析参数JSON
        results_dir: 结果文件目录
        error: 错误信息
        created_at: 创建时间
        updated_at: 最后更新时间
    """
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '失败')
    ]
    
    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    params = models.JSONField(default=dict)
    results_dir = models.CharField(max_length=255, null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"分析任务 {self.task_id} ({self.get_status_display()})"
        
    def get_results(self):
        """
        获取分析结果数据
        
        根据分析类型读取不同的结果文件
        
        Returns:
            dict: 包含可视化和数据的结果字典，如果没有结果则返回None
        """
        results = {'visualizations': {}, 'data': {}}
        
        # 从参数中获取模型类型
        model_param = self.params.get('model', [])
        if isinstance(model_param, list) and model_param:
            model_param = model_param[0]
        
        # 根据模型类型确定分析类型
        is_clustering = model_param == 'student_cluster'
        
        # 确定结果目录路径
        if is_clustering:
            # 检查学生聚类特定目录
            clustering_dir = os.path.join("results", "value_added", "student_cluster")
            if os.path.exists(clustering_dir):
                results_dir = clustering_dir
            else:
                return None
        else:
            # 其他模型使用标准目录查找逻辑
            # ... 原有的结果目录查找代码 ...
            return None
        
        try:
            # 读取数据文件
            if is_clustering:
                # 聚类特定的数据文件 - 检查XLS和CSV两种格式
                cluster_files = {
                    'student_clusters': ['student_clusters.xls', 'student_clusters.csv'],
                    'student_features': ['student_features.xls', 'student_features.csv'],
                    'student_layer_growth': ['student_layer_growth.xls', 'student_layer_growth.csv']
                }
                
                for data_key, file_options in cluster_files.items():
                    for file_name in file_options:
                        file_path = os.path.join(results_dir, file_name)
                        if os.path.exists(file_path):
                            try:
                                if file_name.endswith('.xls') or file_name.endswith('.xlsx'):
                                    df = pd.read_excel(file_path)
                                else:
                                    df = pd.read_csv(file_path)
                                results['data'][data_key] = df.to_dict(orient='records')
                                break  # 找到第一个匹配文件后停止
                            except Exception as e:
                                results['data'][data_key] = {'error': str(e)}
            else:
                # 标准增值模型数据文件处理
                # ... 原有的CSV读取代码 ...
                pass
            
            # 检查可视化图片 - 对所有模型通用
            viz_files = os.listdir(results_dir)
            for f in viz_files:
                if f.endswith(('.png', '.jpg', '.jpeg', '.svg')):
                    img_name = os.path.splitext(f)[0]
                    img_url = f"/static/results/value_added/{model_param}/{f}"
                    results['visualizations'][img_name] = img_url
                
        except Exception as e:
            results['error'] = str(e)
        
        return results 

class StudentScoreFeatures(models.Model):
    """
    学生成绩特征模型，存储基于原始成绩计算的各种特征指标。
    
    用于存储基于学生考试成绩计算的统计特征和衍生特征，支持学生聚类和增值分析。
    
    Args:
        feature_id: 特征记录ID，主键
        student: 关联学生
        semester: 关联学期
        avg_raw_score: 原始成绩平均分
        std_dev_score: 成绩标准差
        max_score: 最高分
        min_score: 最低分
        score_range: 分数范围
        class_rank: 班级排名
        grade_rank: 年级排名
        subject_variance: 学科间方差
        best_subject: 最优学科
        weakest_subject: 最弱学科
        improvement_rate: 进步率
        consistency_index: 稳定性指数
        underperformed_count: 低于预期表现次数
        z_score_avg: Z分数平均值
        
    Returns:
        学生成绩特征实例
    """
    feature_id = models.AutoField(primary_key=True)
    student = models.ForeignKey('core.Student', on_delete=models.CASCADE, related_name='score_features')
    semester = models.ForeignKey('core.Semester', on_delete=models.CASCADE)
    
    # 基础统计特征
    avg_raw_score = models.FloatField(verbose_name='原始平均分')  # 原始成绩平均值
    std_dev_score = models.FloatField(verbose_name='标准差')  # 成绩标准差
    max_score = models.FloatField(verbose_name='最高分')  # 最高分
    min_score = models.FloatField(verbose_name='最低分')  # 最低分
    score_range = models.FloatField(verbose_name='分数范围')  # 最高分与最低分差值
    
    # 相对表现特征
    class_rank = models.IntegerField(verbose_name='班级排名')  # 班级内排名
    grade_rank = models.IntegerField(verbose_name='年级排名')  # 年级内排名
    percentile_in_grade = models.FloatField(verbose_name='年级百分位')  # 年级百分位
    deviation_from_class_avg = models.FloatField(verbose_name='班级平均分差值')  # 与班级平均分差值
    z_score_avg = models.FloatField(verbose_name='Z分数均值')  # 标准化Z分数均值
    county_rank = models.IntegerField(verbose_name='区县排名', null=True, blank=True)  # 区县内排名
    city_rank = models.IntegerField(verbose_name='地市排名', null=True, blank=True)  # 地市内排名
    county_percentile = models.FloatField(verbose_name='区县百分位', null=True, blank=True)  # 区县百分位
    city_percentile = models.FloatField(verbose_name='地市百分位', null=True, blank=True)  # 地市百分位
    
    # 学科特征
    subject_variance = models.FloatField(verbose_name='学科方差')  # 学科间成绩方差
    best_subject = models.ForeignKey('core.Subject', on_delete=models.SET_NULL, related_name='+', null=True, verbose_name='最优学科')
    weakest_subject = models.ForeignKey('core.Subject', on_delete=models.SET_NULL, related_name='+', null=True, verbose_name='最弱学科')
    main_subjects_avg = models.FloatField(verbose_name='主科平均分')  # 主要学科平均分
    minor_subjects_avg = models.FloatField(verbose_name='副科平均分')  # 次要学科平均分
    
    # 时间序列特征（如果有历史数据）
    improvement_rate = models.FloatField(null=True, blank=True, verbose_name='进步率')  # 与上学期相比的进步率
    consistency_index = models.FloatField(null=True, blank=True, verbose_name='稳定性指数')  # 成绩稳定性指数
    underperformed_count = models.IntegerField(default=0, verbose_name='低表现次数')  # 低于预期表现的次数
    
    # 复合指标
    weighted_performance_index = models.FloatField(verbose_name='加权表现指数')  # 综合加权的表现指数
    learning_pattern_cluster = models.IntegerField(null=True, blank=True, verbose_name='学习模式聚类')  # 学习模式聚类ID
    
    # 元数据
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    feature_version = models.CharField(max_length=10, default='1.0')  # 特征版本，便于追踪特征计算方法变更
    
    class Meta:
        verbose_name = '学生成绩特征'
        verbose_name_plural = '学生成绩特征管理'
        unique_together = [['student', 'semester']]  # 每个学生每学期一条记录
        
    def __str__(self):
        return f"{self.student.name}的{self.semester}成绩特征"
        
    def calculate_features(self, scores=None):
        """
        计算学生的所有成绩特征。
        
        可以传入特定的成绩集合，否则会查询该学生在该学期的所有成绩。
        
        Args:
            scores: 可选，指定的成绩记录集合
            
        Returns:
            bool: 是否成功计算了特征
        """

        
        if not scores:
            # 获取该学生该学期的所有成绩
            scores = Score.objects.filter(
                student=self.student,
                semester_id=self.semester.semester_id
            )
            
        if not scores.exists():
            return False
            
        # 计算基础统计特征
        score_stats = scores.aggregate(
            avg=Avg('raw_score'),
            std=StdDev('raw_score'),
            max=Max('raw_score'),
            min=Min('raw_score')
        )
        
        self.avg_raw_score = score_stats['avg']
        self.std_dev_score = score_stats['std'] or 0
        self.max_score = score_stats['max']
        self.min_score = score_stats['min']
        self.score_range = self.max_score - self.min_score
        
        # 计算区县排名
        county_students = Student.objects.filter(
            region__parent_id=self.student.region.parent_id,  # 同一区县的学生
            current_grade__grade_level=self.student.current_grade.grade_level  # 同年级
        )
        county_scores = Score.objects.filter(
            student__in=county_students,
            semester_id=self.semester.semester_id
        ).values('student').annotate(avg_score=Avg('raw_score')).order_by('-avg_score')
        
        # 计算地市排名
        # 类似逻辑...
        
        self.save()
        return True 

class DistrictExamFeature(models.Model):
    """
    区域考试特征模型
    """
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey('core.Exam', on_delete=models.CASCADE, verbose_name='关联考试')
    subject_id = models.CharField(max_length=20, default='TOTAL', verbose_name='科目ID')  # 添加科目字段
    avg_score = models.FloatField(verbose_name='平均分')
    avg_standard_score = models.FloatField(default=0, verbose_name='标准分均值')  # 添加标准分字段
    std_dev = models.FloatField(verbose_name='标准差')
    total_students = models.IntegerField(verbose_name='学生总数')
    max_score = models.FloatField(verbose_name='最高分')
    min_score = models.FloatField(verbose_name='最低分')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '区域考试特征'
        verbose_name_plural = '区域考试特征管理'
        unique_together = [['exam', 'subject_id']]  # 修改唯一约束

class SchoolExamFeature(models.Model):
    """
    校级考试特征模型
    """
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey('core.Exam', on_delete=models.CASCADE, verbose_name='关联考试')
    district_feature = models.ForeignKey(DistrictExamFeature, on_delete=models.CASCADE, verbose_name='区级特征')
    school = models.ForeignKey('core.School', on_delete=models.CASCADE, verbose_name='关联学校')
    subject_id = models.CharField(max_length=20, default='TOTAL', verbose_name='科目ID')  # 添加科目字段
    avg_score = models.FloatField(verbose_name='校平均分')
    avg_standard_score = models.FloatField(default=0, verbose_name='标准分均值')  # 添加标准分字段
    std_dev = models.FloatField(verbose_name='校标准差')
    rank = models.IntegerField(verbose_name='排名')
    percentile = models.FloatField(verbose_name='百分位')
    student_count = models.IntegerField(verbose_name='学生数')
    grade_count = models.IntegerField(default=1, verbose_name='年级数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '校级考试特征'
        verbose_name_plural = '校级考试特征管理'
        unique_together = [['exam', 'school', 'subject_id']]  # 修改唯一约束
        indexes = [
            models.Index(fields=['rank']),
        ]

class ClassExamFeature(models.Model):
    """
    班级考试特征模型
    """
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey('core.Exam', on_delete=models.CASCADE, verbose_name='关联考试')
    school_feature = models.ForeignKey(SchoolExamFeature, on_delete=models.CASCADE, verbose_name='校级特征')
    class_obj = models.ForeignKey('core.Class', on_delete=models.CASCADE, verbose_name='关联班级')
    subject_id = models.CharField(max_length=20, default='TOTAL', verbose_name='科目ID')
    
    # 保持现有字段
    avg_score = models.FloatField(verbose_name='班级平均分')
    std_dev = models.FloatField(verbose_name='班级标准差')
    school_rank = models.IntegerField(verbose_name='校内排名')
    school_percentile = models.FloatField(verbose_name='校内百分位')
    student_count = models.IntegerField(verbose_name='学生数')
    
    # 添加新字段
    avg_standard_score = models.FloatField(default=0, verbose_name='标准分均值')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '班级考试特征'
        verbose_name_plural = '班级考试特征管理'
        unique_together = [['exam', 'class_obj', 'subject_id']]  # 修改唯一约束
        indexes = [
            models.Index(fields=['school_rank']),
        ]

class StudentExamFeature(models.Model):
    """
    学生考试特征模型，存储学生在单次考试中的个体表现。
    
    关联区、校、班级特征，提供学生在不同层级中的相对表现数据。
    
    Args:
        exam: 关联考试
        student: 关联学生
        district_feature: 关联区级特征
        school_feature: 关联校级特征
        class_feature: 关联班级特征
        total_score: 学生考试总分
        class_rank: 班级内排名
        school_rank: 校内排名
        district_rank: 区内排名
        best_subject: 最优学科
        best_subject_score: 最优学科得分
        weakest_subject: 最弱学科
        weakest_subject_score: 最弱学科得分
    
    Returns:
        学生考试特征实例
        
    Raises:
        ValidationError: 当数据验证失败时抛出
    """
    id = models.AutoField(primary_key=True)
    exam = models.ForeignKey('core.Exam', on_delete=models.CASCADE, verbose_name='关联考试')
    student = models.ForeignKey('core.Student', on_delete=models.CASCADE, verbose_name='关联学生')
    district_feature = models.ForeignKey(DistrictExamFeature, on_delete=models.CASCADE, verbose_name='区级特征')
    school_feature = models.ForeignKey(SchoolExamFeature, on_delete=models.CASCADE, verbose_name='校级特征')
    class_feature = models.ForeignKey(ClassExamFeature, on_delete=models.CASCADE, verbose_name='班级特征')
    
    # 个体表现
    total_score = models.FloatField(verbose_name='考试总分')
    class_rank = models.IntegerField(verbose_name='班级排名')
    school_rank = models.IntegerField(verbose_name='校内排名')
    district_rank = models.IntegerField(verbose_name='区内排名')
    
    # 学科表现
    best_subject = models.ForeignKey('core.Subject', on_delete=models.SET_NULL, 
                                    related_name='+', null=True, verbose_name='最优学科')
    best_subject_score = models.FloatField(verbose_name='最优学科得分')
    weakest_subject = models.ForeignKey('core.Subject', on_delete=models.SET_NULL, 
                                       related_name='+', null=True, verbose_name='最弱学科')
    weakest_subject_score = models.FloatField(verbose_name='最弱学科得分')
    
    # 元数据
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '学生考试特征'
        verbose_name_plural = '学生考试特征管理'
        unique_together = [['exam', 'student']]
        indexes = [
            models.Index(fields=['district_rank']),
            models.Index(fields=['school_rank']),
            models.Index(fields=['class_rank']),
        ]
    
    def __str__(self):
        return f"{self.student.name} - {self.exam.exam_name} 考试特征"
    
    @property
    def z_score_district(self):
        """
        计算学生相对于区级的Z分数。
        
        Returns:
            float: 区级标准化Z分数
        """
        if self.district_feature.std_dev == 0:
            return 0
        return (self.total_score - self.district_feature.avg_score) / self.district_feature.std_dev
    
    @property
    def z_score_school(self):
        """
        计算学生相对于学校的Z分数。
        
        Returns:
            float: 校级标准化Z分数
        """
        if self.school_feature.std_dev == 0:
            return 0
        return (self.total_score - self.school_feature.avg_score) / self.school_feature.std_dev
    
    @property
    def z_score_class(self):
        """
        计算学生相对于班级的Z分数。
        
        Returns:
            float: 班级标准化Z分数
        """
        if self.class_feature.std_dev == 0:
            return 0
        return (self.total_score - self.class_feature.avg_score) / self.class_feature.std_dev
    
    @property
    def deviation_from_class_avg(self):
        """
        计算与班级平均分的差值。
        
        Returns:
            float: 与班级平均分的差值
        """
        return self.total_score - self.class_feature.avg_score 