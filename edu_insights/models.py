from django.db import models
import uuid
import os
import json
import pandas as pd
import logging
from django.conf import settings

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