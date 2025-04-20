from rest_framework import serializers
from .models import AnalysisTask

class AnalysisTaskSerializer(serializers.ModelSerializer):
    """
    分析任务序列化器
    
    用于API数据转换和验证
    
    Args:
        model: 对应的模型类
        fields: 序列化的字段
    """
    class Meta:
        model = AnalysisTask
        fields = ['task_id', 'status', 'progress', 'params', 'results_dir', 'error', 'created_at', 'updated_at']
        read_only_fields = ['task_id', 'progress', 'status', 'results_dir', 'error', 'created_at', 'updated_at']
