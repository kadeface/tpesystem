import subprocess
from django.conf import settings
import os
import sys
from .utils.session_progress_tracker import SessionProgressTracker
import logging
import time
from django.core.cache import cache
import json
import locale
import tempfile
from datetime import datetime
# 配置根日志记录器
logging.basicConfig(level=logging.DEBUG, 
                   format='[%(asctime)s] %(message)s',
                   datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)

class ProgressTracker:
    """
    跟踪任务进度的工具类。
    
    Args:
        task_id: 任务唯一标识符
        total_steps: 总步骤数
        
    Returns:
        ProgressTracker实例
    """
    def __init__(self, task_id, total_steps=6, timeout=3600):
        """
        初始化进度跟踪器。
        
        Args:
            task_id: 任务ID
            total_steps: 总步骤数
            timeout: 缓存超时时间（秒）
        
        Returns:
            无返回值
        """
        self.task_id = task_id
        self.timeout = timeout  # 保留这个属性
        self.total_steps = total_steps
        self.current_step = 0
        self.status = "PENDING"
        self.message = ""
        self.details = []
        self.errors = []
        self.percent = 0
        self.start_time = None
        
        # 初始化进度
        self.save()

    def update(self, message=None, current=None, total=None, status=None, start_time=None):
        """
        更新进度信息。
        
        Args:
            message: 进度消息
            current: 当前步骤
            total: 总步骤数
            status: 状态
            start_time: 开始时间
        
        Returns:
            无返回值
        """
        if message:
            # 确保message是字符串类型
            if isinstance(message, bytes):
                try:
                    message = message.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    try:
                        message = message.decode('cp936', errors='replace')
                    except:
                        message = str(message)
            
            self.message = message
            # 限制详细信息数组大小，避免内存问题
            self.details.append(message)
            if len(self.details) > 100:  # 最多保留最新的100条消息
                self.details = self.details[-100:]
        
        if current is not None:
            self.current_step = current
            # 确保百分比更新
            self.percent = int((self.current_step / self.total_steps) * 100)
        
        if total is not None:
            self.total_steps = total
        
        if status:
            self.status = status
            
        if start_time:  # 添加这个判断
            self.start_time = start_time
            
        # 保存进度
        self.save()
        
        # 打印进度
        print(f"进度更新: {self.task_id} = {self.current_step}/{self.total_steps} ({self.percent}%) - {self.message}")
        logger.info(f"进度更新: {self.task_id} = {self.current_step}/{self.total_steps} ({self.percent}%) - {self.message}")

    def add_error(self, error_message):
        # 检查是否为bytes类型，如果是则进行解码
        if isinstance(error_message, bytes):
            try:
                # 尝试使用utf-8解码
                error_message = error_message.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                try:
                    # 如果失败，尝试使用cp936(中文Windows)解码
                    error_message = error_message.decode('cp936', errors='replace')
                except:
                    # 最后的后备方案，转换为字符串表示
                    error_message = str(error_message)
        
        # 原有逻辑继续处理
        if error_message and hasattr(error_message, 'strip') and error_message.strip():
            self.errors.append(error_message.strip())
            print(f"任务错误: {self.task_id} - {error_message.strip()}")
            logger.error(f"任务错误: {self.task_id} - {error_message.strip()}")
            self.save()

    def complete(self, message="导入完成"):
        """标记任务为完成状态"""
        self.status = 'COMPLETED'
        self.percent = 100
        self.message = message
        self.details.append(message)
        self.current_step = self.total_steps
        self.save()
        print(f"任务完成: {self.task_id} - {message}")
        logger.info(f"任务完成: {self.task_id} - {message}")
        
    def fail(self, message=None, error=None):
        """标记任务为失败状态"""
        if message:
            self.message = message
            self.details.append(message)
        if error:
            self.add_error(str(error))
        self.status = 'FAILED'
        self.save()
        print(f"任务失败: {self.task_id} - {self.message}")
        logger.error(f"任务失败: {self.task_id} - {self.message}")
        
    def save(self):
        """保存进度信息到存储系统"""
        # 准备进度数据
        progress_data = {
            "task_id": self.task_id,
            "status": self.status,
            "current": self.current_step,
            "total": self.total_steps,
            "percent": self.percent,
            "message": self.message,
            "details": self.details,
            "errors": self.errors,
            "start_time": self.start_time
        }
        
        # 使用缓存存储进度
        cache_key = f"task_progress_{self.task_id}"
        cache.set(cache_key, progress_data, 3600)
        
        # 同时保存到文件系统
        progress_file = os.path.join(settings.MEDIA_ROOT, 'progress', f"{self.task_id}.json")
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False)

def run_import_task_async(file_path, exam_id, exam_name, exam_type, semester_id, 
                         teacher_id, region_id, sheet_name, create_students, 
                         update_students, skip_teacher, debug, smart_match, force, task_id,
                         import_teacher_history=False, teacher_file=None, 
                         teacher_sheet='Sheet1', auto_create_missing_teachers=False,
                         existing_tracker=None):
    """
    异步运行导入任务。
    
    Args:
        file_path: 文件路径
        exam_id: 考试ID
        exam_name: 考试名称
        exam_type: 考试类型
        semester_id: 学期ID
        teacher_id: 教师ID
        region_id: 区域ID
        sheet_name: 工作表名称
        create_students: 是否创建学生
        update_students: 是否更新学生
        skip_teacher: 是否跳过教师
        debug: 是否调试模式
        smart_match: 是否智能匹配
        force: 是否强制导入
        task_id: 任务ID
        import_teacher_history: 是否导入教师历史记录
        teacher_file: 教师历史数据文件路径
        teacher_sheet: 教师历史数据工作表名称
        auto_create_missing_teachers: 是否自动创建不存在的教师
        existing_tracker: 可选的现有进度跟踪器实例
    
    Returns:
        任务执行结果字典
    """
    # 使用传入的tracker或创建新的
    if existing_tracker:
        tracker = existing_tracker
    else:
        # 初始化进度跟踪器 - 使用与子进程相同的total_steps=6
        tracker = ProgressTracker(task_id, total_steps=6)
        
        # 设置开始时间
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tracker.update(message=f'开始导入任务...', status='PROCESSING', start_time=start_time)
    
    # 添加这行定义
    manage_py = os.path.join(settings.BASE_DIR, 'manage.py')
    
    # 创建日志目录和文件
    log_dir = os.path.join(settings.MEDIA_ROOT, 'debug')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'task_{task_id}.log')
    
    # 配置文件日志处理器
    file_handler = logging.FileHandler(log_file, 'w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    logger.addHandler(file_handler)
    
    try:
        # 在原日志基础上增加调试信息（保持原有日志结构）
        print(f"[TASK INIT] 开始处理任务 {task_id}")
        logger.info(f"=== 任务初始化 ===\n文件路径: {file_path}\n学期ID: {semester_id}")

        # 保持原有命令构建结构，增加路径引号处理
        args = [
            sys.executable,
            manage_py,
            'import_scores',
            '--file_path', file_path,  
            '--exam_id', exam_id,
            '--exam_name', exam_name,
            '--exam_type', exam_type,
            '--semester', semester_id,
            '--task_id', task_id,
            '--tracker_passed'  # 正确格式：不传递值
        ]

        # 保持原有可选参数添加方式，增加空值过滤
        if teacher_id and teacher_id.strip():  # 原代码增加有效性检查
            args.extend(['--teacher_id', teacher_id.strip()])
        
        if region_id and str(region_id).isdigit():  # 原代码增加验证
            args.extend(['--region_id', str(region_id)])
        
        # 2. 修复临时文件问题
        with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding='utf-8') as tmp:
            tmp_path = tmp.name
            
            # 使用list形式的args避免shell解析问题
            process = subprocess.Popen(
                args,
                stdout=tmp,
                stderr=tmp,
                env=os.environ.copy(),
                shell=False,  # 改为False避免shell解析
                cwd=os.path.dirname(manage_py)
            )
            
            # 确保文件已关闭
            tmp.close()
            
            # 等待进程完成
            process.wait()
            
            # 读取并处理输出
            try:
                # 尝试多种编码方式读取文件
                encodings = ['utf-8', 'gbk', 'cp936', 'latin1']
                output_read = False
                
                for encoding in encodings:
                    try:
                        with open(tmp_path, 'r', encoding=encoding) as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    # 检查是否为进度信息，如果是则跳过
                                    if "进度更新:" in line:
                                        continue
                                    # 其他输出正常记录
                                    logger.info(f"命令输出: {line}")
                                    tracker.update(message=line)
                        output_read = True
                        logger.info(f"成功使用 {encoding} 编码读取输出")
                        break
                    except UnicodeDecodeError:
                        logger.warning(f"使用 {encoding} 解码失败，尝试下一种编码")
                        continue
                
                if not output_read:
                    # 如果所有编码都失败，尝试二进制模式读取
                    with open(tmp_path, 'rb') as f:
                        binary_data = f.read()
                        # 尝试检测编码
                        try:
                            import chardet
                            result = chardet.detect(binary_data)
                            detected_encoding = result['encoding']
                            logger.info(f"检测到编码: {detected_encoding}")
                            text = binary_data.decode(detected_encoding, errors='replace')
                        except ImportError:
                            # 如果没有chardet，使用替换模式解码
                            text = binary_data.decode('utf-8', errors='replace')
                        
                        for line in text.splitlines():
                            if line.strip():
                                # 检查是否为进度信息，如果是则跳过
                                if "进度更新:" in line:
                                    continue
                                # 其他输出正常记录
                                logger.info(f"命令输出: {line.strip()}")
                                tracker.update(message=line.strip())
            finally:
                # 确保文件读取完毕后再尝试删除
                try:
                    os.remove(tmp_path)
                except Exception as e:
                    logger.warning(f"无法删除临时文件: {str(e)}")
                    # 忽略删除错误，不影响主流程
        
        # 检查返回码
        return_code = process.poll()
        if return_code == 0:
            logger.info("导入成功完成！")
            tracker.update(status="COMPLETED", message="导入成功完成！")
            return {'success': True, 'task_id': task_id}
        else:
            error_msg = f"导入失败，返回代码：{return_code}"
            logger.error(error_msg)
            tracker.fail(error_msg)
            return {'success': False, 'task_id': task_id, 'error': "详见日志文件"}
            
    except Exception as e:
        # 记录异常
        import traceback
        error_msg = f"导入过程发生错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        tracker.fail(error_msg)
        return {'success': False, 'task_id': task_id, 'error': str(e)}
    finally:
        # 移除和关闭文件处理器
        logger.removeHandler(file_handler)
        file_handler.close()

    # 在 _historical_import 方法结束前添加
    if hasattr(self, 'tracker') and self.tracker:
        # 强制设置并保存进度
        self.tracker.current_step = 6
        self.tracker.percent = 100
        self.tracker.save()
        
        # 再次调用 complete 以确保更新
        self.tracker.complete("历史数据导入成功完成！")

def run_import_task_async_session(file_path, exam_id, exam_name, exam_type, semester,
                                teacher_id, region, sheet_name, create_students,
                                update_students, skip_teacher, debug, smart_match, force,
                                task_id, session_key):
    """
    异步运行导入任务，使用会话进度跟踪。

    Args:
        file_path: 文件路径
        task_id: 任务ID用于跟踪进度
        session_key: 会话密钥

    Returns:
        任务执行结果字典
    """
    tracker = SessionProgressTracker(task_id, session_key)
    tracker.update(status='PROCESSING', message=f'开始导入任务 {task_id}')

    try:
        # 添加更多调试信息
        tracker.update(message=f"文件路径: {file_path}")
        tracker.update(message=f"会话ID: {session_key}")


        # 构建命令参数
        manage_py = os.path.join(settings.BASE_DIR, 'manage.py')

        args = [
            sys.executable,  # Python 解释器路径
            manage_py,
            'import_scores',
            '--file_path', file_path,
            '--exam_id', exam_id,
            '--exam_name', exam_name,
            '--exam_type', exam_type,
            '--semester', semester,
            '--task_id', task_id  # 传递任务ID给命令
        ]

        # 添加可选参数
        if teacher_id:
            args.extend(['--teacher_id', teacher_id])
        if region:
            args.extend(['--region_id', region])
        if sheet_name:
            args.extend(['--sheet', sheet_name])
        if create_students:
            args.append('--create_students')
        if update_students:
            args.append('--update_students')
        if skip_teacher:
            args.append('--skip_teacher')
        if debug:
            args.append('--debug')
        if smart_match:
            args.append('--smart_match')
        if force:
            args.append('--force')

        # 添加更详细的日志
        print(f"执行命令: {' '.join(args)}")

        env = os.environ.copy()
        env.update({
            'PYTHONIOENCODING': 'utf-8',  # 强制子进程使用UTF-8输出
            'PYTHONUTF8': '1'  # 对于Python 3.7+ 确保UTF-8模式
        })

        # 方法1：使用临时文件捕获输出
        with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding='utf-8') as tmp:
            tmp_path = tmp.name
            # 将输出重定向到文件
            process = subprocess.Popen(
                args,
                stdout=tmp,
                stderr=tmp,
                env=env,
                shell=True,
                cwd=os.path.dirname(manage_py)
            )
            
            # 等待进程完成
            process.wait()
            
            # 重新打开文件读取输出
            with open(tmp_path, 'r', encoding='utf-8') as f:
                output_lines = f.readlines()
                
            # 处理所有输出行
            for line in output_lines:
                line = line.strip()
                if line:
                    # 检查是否为进度信息，如果是则跳过
                    if "进度更新:" in line:
                        continue
                    # 其他输出正常记录
                    logger.info(f"命令输出: {line}")
                    tracker.update(message=line)
            
            # 删除临时文件
            os.unlink(tmp_path)
        
        # 检查返回码
        return_code = process.poll()
        if return_code == 0:
            tracker.complete("导入成功完成！")
            return {'success': True, 'task_id': task_id}
        else:
            tracker.fail(f"导入失败，返回代码：{return_code}")
            return {'success': False, 'task_id': task_id, 'error': "详见日志文件"}

    except Exception as e:
        tracker.fail(f"导入过程发生错误: {str(e)}")
        return {'success': False, 'task_id': task_id, 'error': str(e)}

def get_task_status(task_id):
    """
    获取指定任务的状态信息。
    
    根据任务ID获取当前的执行状态、完成百分比和任何错误信息。
    
    Args:
        task_id: 任务的UUID标识符
        
    Returns:
        dict: 包含任务状态信息的字典，例如：
            {
                'status': 'PENDING|STARTED|SUCCESS|FAILURE',
                'progress': 75,  # 百分比
                'result': {...},  # 仅在状态为SUCCESS时
                'error': '...'   # 仅在状态为FAILURE时
            }
        
    Raises:
        TaskNotFound: 如果找不到指定ID的任务
    """
    # 如果您使用Celery，可以通过以下方式获取任务状态
    # from celery.result import AsyncResult
    # result = AsyncResult(task_id)
    # status_info = {'status': result.status}
    
    # 如果使用自定义的任务跟踪系统，则需相应实现
    # 例如，从数据库或缓存中获取任务状态
    
    # 这里是一个示例实现，您需要根据实际情况修改
    try:
        # 假设您有某种方式存储任务状态
        # 例如，Redis或数据库中
        task_info = get_task_info_from_storage(task_id)
        
        return {
            'status': task_info.get('status', 'UNKNOWN'),
            'progress': task_info.get('progress', 0),
            'result': task_info.get('result'),
            'error': task_info.get('error')
        }
    except Exception as e:
        raise Exception(f"无法找到任务: {str(e)}")

# 这个函数需要根据您的实际存储机制实现
def get_task_info_from_storage(task_id):
    """
    从存储中获取任务信息。
    
    Args:
        task_id: 任务的UUID标识符
        
    Returns:
        dict: 包含任务信息的字典
        
    Raises:
        Exception: 如果找不到任务或访问存储时出错
    """
    # 示例实现 - 需要替换为实际代码
    # 如果使用Redis:
    # import redis
    # import json
    # r = redis.Redis()
    # task_data = r.get(f"task:{task_id}")
    # if task_data:
    #     return json.loads(task_data)
    # raise Exception(f"任务 {task_id} 不存在")
    
    # 如果使用数据库:
    # from myapp.models import ImportTask
    # try:
    #     task = ImportTask.objects.get(id=task_id)
    #     return {
    #         'status': task.status,
    #         'progress': task.progress,
    #         'result': task.result,
    #         'error': task.error_message
    #     }
    # except ImportTask.DoesNotExist:
    #     raise Exception(f"任务 {task_id} 不存在")
    
    # 临时实现，仅用于示例
    raise Exception("尚未实现任务存储机制")



