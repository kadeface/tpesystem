from django.core.cache import cache
import json
import uuid
import os
from django.conf import settings
import time

class ProgressTracker:
    """
    进度跟踪器，用于记录和更新任务进度。
    
    Args:
        task_id: 任务ID，默认自动生成
        timeout: 缓存超时时间（秒）
    
    Returns:
        进度跟踪器实例
    """
    
    def __init__(self, task_id, total_steps=6, timeout=3600):
        self.task_id = task_id or str(uuid.uuid4())
        self.timeout = timeout
        self.total_steps = total_steps
        self.current_step = 0
        self.status = 'PENDING'
        self.message = '准备开始导入...'
        self.details = []
        self.errors = []
        self.percent = 0
        self._init_progress()
    
    def _init_progress(self):
        """初始化进度信息"""
        progress_data = {
            'status': 'PENDING',  # PENDING, PROCESSING, COMPLETED, FAILED
            'current': 0,
            'total': 100,
            'percent': 0,
            'message': '准备开始导入...',
            'details': [],
            'errors': []
        }
        self._save_progress(progress_data)
    
    def _save_progress(self, progress_data):
        """保存进度信息到缓存"""
        key = f'task_progress_{self.task_id}'
        value = json.dumps(progress_data)
        print(f"保存进度: {key} = {value}")  # 添加调试信息
        success = cache.set(key, value, self.timeout)
        print(f"缓存设置结果: {success}")  # 检查缓存是否成功设置
    
    def _get_progress(self):
        """获取当前进度信息"""
        data = cache.get(f'task_progress_{self.task_id}')
        return json.loads(data) if data else self._init_progress()
    
    def update(self, current=None, total=None, message=None, status=None):
        """更新进度信息"""
        if total is not None:
            self.total_steps = total
        if current is not None:
            self.current_step = current
        if message is not None:
            self.message = message
            self.details.append(message)
        if status is not None:
            self.status = status
        
        # 计算进度百分比
        self.percent = int((self.current_step / max(self.total_steps, 1)) * 100)
        self._save_progress(self.__dict__)
        
        # 添加额外的调试日志
        print(f"进度更新: task_{self.task_id} = {self.current_step}/{self.total_steps} ({self.percent}%) - {self.message}")
        
    def add_error(self, error_message):
        """添加错误信息"""
        self.errors.append(error_message)
        self._save_progress(self.__dict__)
    
    def get(self):
        """获取当前进度"""
        return self._get_progress()
    
    def complete(self, message="导入完成"):
        """标记任务为完成"""
        self.status = 'COMPLETED'
        self.current_step = self.total_steps
        self.percent = 100
        self.message = message
        self.details.append(message)
        self._save_progress(self.__dict__)
        return self.__dict__
    
    def fail(self, error_message):
        """标记任务为失败"""
        self.status = 'FAILED'
        self.message = f"导入失败: {error_message}"
        self.errors.append(error_message)
        self.details.append(self.message)
        self._save_progress(self.__dict__)
        return self.__dict__
    
    def save(self):
        """保存进度信息到存储系统"""
        # 确保目录存在
        progress_dir = os.path.join(settings.MEDIA_ROOT, 'progress')
        os.makedirs(progress_dir, exist_ok=True)
        
        # 保存到文件
        progress_file = os.path.join(progress_dir, f"{self.task_id}.json")
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, ensure_ascii=False)
        
        # 同时保存到缓存，保证前端可以读取
        cache_key = f"task_progress_{self.task_id}"
        cache_result = cache.set(cache_key, self.__dict__, timeout=3600)  # 1小时缓存
        
        # 记录缓存操作结果
        debug_log_path = os.path.join(settings.MEDIA_ROOT, 'debug', f"task_{self.task_id}.log")
        with open(debug_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 保存进度: {cache_key} = {json.dumps(self.__dict__, ensure_ascii=False)}\n")
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 缓存设置结果: {cache_result}\n") 