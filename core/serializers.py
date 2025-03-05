from rest_framework import serializers
from .models import Region, Semester, School, Score, Student, Subject, Teacher

class RegionSerializer(serializers.ModelSerializer):
    """
    区域序列化器，用于序列化区域数据。

    Attributes:
        Meta: 元数据
    """
    class Meta:
        model = Region
        fields = '__all__'

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