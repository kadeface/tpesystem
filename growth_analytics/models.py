from django.db import models
import uuid
import os
import json
import pandas as pd
import logging

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
    params = models.JSONField()
    results_dir = models.CharField(max_length=255, null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"分析任务 {self.task_id} ({self.get_status_display()})"
        
    def get_results(self):
        """获取分析结果数据"""
        if self.status != 'completed' or not self.results_dir:
            return None
            
        results = {
            'visualizations': {},
            'data': {}
        }
        
        # 读取结果目录中的图表文件
        if os.path.exists(self.results_dir):
            # 获取所有PNG图表
            for file in os.listdir(self.results_dir):
                if file.endswith('.png'):
                    file_path = os.path.join(self.results_dir, file)
                    file_name = os.path.splitext(file)[0]
                    
                    # 将文件路径转换为URL
                    relative_path = os.path.relpath(file_path, 'media')
                    url_path = f'/media/{relative_path}'
                    
                    # 存储图表URL
                    results['visualizations'][file_name] = url_path
                    
            # 读取CSV结果文件
            for file in os.listdir(self.results_dir):
                if file.endswith('.csv'):
                    file_path = os.path.join(self.results_dir, file)
                    file_name = os.path.splitext(file)[0]
                    
                    try:
                        df = pd.read_csv(file_path)
                        results['data'][file_name] = df.to_dict(orient='records')
                    except Exception as e:
                        logger.error(f"读取CSV文件失败 {file_path}: {str(e)}")
                        results['data'][file_name] = {'error': str(e)}
                        
            # 读取JSON结果文件
            for file in os.listdir(self.results_dir):
                if file.endswith('.json'):
                    file_path = os.path.join(self.results_dir, file)
                    file_name = os.path.splitext(file)[0]
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        results['data'][file_name] = data
                    except Exception as e:
                        logger.error(f"读取JSON文件失败 {file_path}: {str(e)}")
                        results['data'][file_name] = {'error': str(e)}
        
        return results 