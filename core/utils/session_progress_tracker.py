from django.contrib.sessions.backends.db import SessionStore
import json
import uuid
import os
from django.conf import settings

class SessionProgressTracker:
    """
    基于会话的进度跟踪器，用于记录和更新任务进度。
    
    Args:
        task_id: 任务ID，默认自动生成
        session_key: 会话密钥
    
    Returns:
        进度跟踪器实例
    """
    
    def __init__(self, task_id=None, session_key=None):
        self.task_id = task_id or str(uuid.uuid4())
        self.session_key = session_key
        self.session_store = SessionStore(session_key=session_key) if session_key else None
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
        """保存进度信息到会话和文件系统"""
        # 确保进度目录存在
        try:
            progress_dir = os.path.join(settings.MEDIA_ROOT, 'progress')
            os.makedirs(progress_dir, exist_ok=True)
            
            # 保存到文件
            file_path = os.path.join(progress_dir, f'{self.task_id}.json')
            with open(file_path, 'w') as f:
                json.dump(progress_data, f)
            print(f"进度已保存到文件: {file_path}")
        except Exception as e:
            print(f"保存进度到文件系统失败: {str(e)}")
        
        # 继续尝试保存到会话
        if self.session_store:
            try:
                key = f'task_progress_{self.task_id}'
                self.session_store[key] = progress_data
                self.session_store.save()
            except Exception as e:
                print(f"保存进度到会话失败: {str(e)}")
    
    def _get_progress(self):
        """获取当前进度信息"""
        try:
            if self.session_store:
                key = f'task_progress_{self.task_id}'
                data = self.session_store.get(key)
                if data:
                    return data
            return self._get_default_progress()
        except Exception as e:
            print(f"获取进度时出错: {str(e)}")
            return self._get_default_progress()
    
    def _get_default_progress(self):
        """获取默认进度信息"""
        return {
            'status': 'PENDING', 
            'current': 0,
            'total': 100,
            'percent': 0,
            'message': '准备开始导入...',
            'details': [],
            'errors': []
        }
    
    def update(self, current=None, total=None, message=None, status=None):
        """更新进度信息"""
        progress = self._get_progress()
        
        if current is not None:
            progress['current'] = current
        
        if total is not None:
            progress['total'] = total
        
        if message is not None:
            progress['message'] = message
            if 'details' not in progress:
                progress['details'] = []
            progress['details'].append(message)
            # 只保留最近的50条消息
            if len(progress['details']) > 50:
                progress['details'] = progress['details'][-50:]
        
        if status is not None:
            progress['status'] = status
        
        # 计算百分比
        if progress['total'] > 0:
            progress['percent'] = round((progress['current'] / progress['total']) * 100, 1)
        
        self._save_progress(progress)
        return progress
    
    def add_error(self, error_message):
        """添加错误信息"""
        progress = self._get_progress()
        if 'errors' not in progress:
            progress['errors'] = []
        progress['errors'].append(error_message)
        self._save_progress(progress)
    
    def get(self):
        """获取当前进度"""
        return self._get_progress()
    
    def complete(self, message="导入完成"):
        """标记任务为完成"""
        progress = self._get_progress()
        progress['status'] = 'COMPLETED'
        progress['current'] = progress['total']
        progress['percent'] = 100
        progress['message'] = message
        if 'details' not in progress:
            progress['details'] = []
        progress['details'].append(message)
        self._save_progress(progress)
        return progress
    
    def fail(self, message="导入失败"):
        """标记任务为失败"""
        progress = self._get_progress()
        progress['status'] = 'FAILED'
        progress['message'] = message
        if 'details' not in progress:
            progress['details'] = []
        progress['details'].append(message)
        self._save_progress(progress)
        return progress 