from rest_framework import serializers
from .models import Region, Semester, School, Score, Student, Subject, Teacher, Grade, Exam
from django.utils import timezone

class RegionSerializer(serializers.ModelSerializer):
    """
    区域序列化器，用于序列化区域数据。

    Attributes:
        Meta: 元数据
    """
    class Meta:
        model = Region
        fields = ['region_id', 'region_name']

class SemesterSerializer(serializers.ModelSerializer):
    """
    学期序列化器，用于序列化学期数据。

    Args:
        Meta: 元数据配置

    Returns:
        序列化后的学期数据
    """
    class Meta:
        model = Semester
        fields = '__all__'

class SchoolSerializer(serializers.ModelSerializer):
    """
    学校序列化器，用于序列化学校数据。

    Args:
        Meta: 元数据配置

    Returns:
        序列化后的学校数据
    """
    class Meta:
        model = School
        fields = '__all__'

class ScoreSerializer(serializers.ModelSerializer):
    """
    成绩序列化器，用于序列化成绩数据。

    Attributes:
        Meta: 元数据
    """
    class Meta:
        model = Score
        fields = '__all__'

class StudentSerializer(serializers.ModelSerializer):
    """
    学生序列化器，用于序列化学生数据。
    
    Args:
        Meta: 元数据配置
        
    Returns:
        序列化后的学生数据
        
    Raises:
        ValidationError: 当提供的数据无效时抛出
    """
    class Meta:
        model = Student
        fields = '__all__'

class SubjectSerializer(serializers.ModelSerializer):
    """
    学科序列化器，用于处理学科数据的序列化和反序列化。
    
    Args:
        ModelSerializer: DRF的模型序列化器基类
        
    Returns:
        序列化或反序列化后的学科数据
    """
    class Meta:
        model = Subject
        fields = ['subject_id', 'subject_name', 'subject_type', 'description', 'status']

class TeacherSerializer(serializers.ModelSerializer):
    """
    教师序列化器，用于序列化和反序列化教师数据。
    
    Args:
        ModelSerializer: DRF的模型序列化器基类
        
    Returns:
        序列化或反序列化后的教师数据
        
    Raises:
        ValidationError: 当提供的数据无效时抛出
    """
    class Meta:
        model = Teacher
        fields = '__all__'

class GradeSerializer(serializers.ModelSerializer):
    """
    年级的序列化器。
    
    Args:
        无特殊参数
        
    Returns:
        序列化后的年级数据
        
    Raises:
        无特殊异常
    """
    # 添加届次和学段信息
    graduation_year = serializers.SerializerMethodField()
    education_stage_display = serializers.SerializerMethodField()
    stage_with_year = serializers.SerializerMethodField()
    
    class Meta:
        model = Grade
        fields = ['grade_id', 'grade_name', 'grade_level', 'school_id', 'semester_id', 
                  'graduation_year', 'education_stage_display', 'stage_with_year']
    
    def get_graduation_year(self, obj):
        """计算毕业年份（届次）"""
        try:
            current_year = timezone.now().year
            grade_level = int(obj.grade_level)
            
            # 按学段计算毕业年份
            if grade_level <= 6:  # 小学
                return current_year + (6 - grade_level)
            elif grade_level <= 9:  # 初中
                return current_year + (9 - grade_level)
            else:  # 高中
                return current_year + (12 - grade_level)
        except (ValueError, TypeError):
            return None
    
    def get_education_stage_display(self, obj):
        """获取学段名称"""
        try:
            grade_level = int(obj.grade_level)
            if grade_level <= 6:
                return "小学"
            elif grade_level <= 9:
                return "初中"
            else:
                return "高中"
        except (ValueError, TypeError):
            return "未知学段"
    
    def get_stage_with_year(self, obj):
        """组合届次和学段，例如：2023届初中"""
        graduation_year = self.get_graduation_year(obj)
        stage = self.get_education_stage_display(obj)
        if graduation_year:
            return f"{graduation_year}届{stage}"
        return f"{stage}"

class ExamSerializer(serializers.ModelSerializer):
    """
    考试的序列化器。
    
    Args:
        无特殊参数
        
    Returns:
        序列化后的考试数据
        
    Raises:
        无特殊异常
    """
    # 嵌套序列化其它关联模型数据
    grade = GradeSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    
    class Meta:
        model = Exam
        fields = ['exam_id', 'exam_name', 'exam_type', 'start_time', 'end_time', 
                 'total_score', 'status', 'grade', 'subject', 'semester_id'] 