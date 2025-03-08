"""
Django Admin数据导入功能模块。

此模块提供了通过Admin界面上传和导入Excel数据的功能，替代命令行导入工具。
"""

from django import forms
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.files.storage import FileSystemStorage
import os
import threading
import uuid
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from .models import  Semester, Region, Teacher
from core.tasks import ProgressTracker
import json

# 创建一个本地的导入函数替代异步任务
def run_import_task_sync(file_path, exam_id, exam_name, exam_type, semester_id, 
                       teacher_id, region_id, sheet_name, create_students, 
                       update_students, skip_teacher, debug, smart_match, force, task_id,
                       import_teacher_history=False, teacher_file=None, 
                       teacher_sheet='Sheet1', auto_create_missing_teachers=False,
                       existing_tracker=None):
    """
    直接运行导入任务，不使用异步方式
    
    Args:
        file_path: 文件路径
        task_id: 任务ID用于跟踪进度
        
    Returns:
        任务执行结果字典
    """
    try:
        # 创建命令参数字典
        kwargs = {
            'file_path': file_path,
            'exam_id': exam_id,
            'exam_name': exam_name,
            'exam_type': exam_type,
            'semester': semester_id,
            'task_id': task_id
        }
        
        # 添加可选参数
        if teacher_id:
            kwargs['teacher_id'] = teacher_id
        if region_id:
            kwargs['region_id'] = region_id
        if sheet_name:
            kwargs['sheet'] = sheet_name
        if create_students:
            kwargs['create_students'] = True
        if update_students:
            kwargs['update_students'] = True
        if skip_teacher:
            kwargs['skip_teacher'] = True
        if debug:
            kwargs['debug'] = True
        if smart_match:
            kwargs['smart_match'] = True
        if force:
            kwargs['force'] = True
            
        # 执行命令
        call_command('import_scores', **kwargs)
        return {'success': True, 'task_id': task_id}
        
    except Exception as e:
        # 记录错误
        import traceback
        error_msg = f"导入过程发生错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        
        # 如果有进度跟踪器，标记为失败
        if existing_tracker:
            existing_tracker.fail(error_msg)
            
        return {'success': False, 'task_id': task_id, 'error': str(e)}

class ScoresImportForm(forms.Form):
    """
    成绩数据导入表单。
    
    提供用户上传成绩数据Excel文件并设置相关参数的界面。
    
    Args:
        forms.Form: Django表单基类
    
    Returns:
        表单实例
    """
    file = forms.FileField(
        label="选择Excel文件",
        help_text="上传包含学生成绩数据的Excel文件"
    )
    
    exam_id = forms.CharField(
        label="考试ID", 
        max_length=100,
        help_text="考试的唯一标识符，如2024-DIST-2-0520"
    )
    
    exam_name = forms.CharField(
        label="考试名称", 
        max_length=200,
        help_text="考试的显示名称，如'23-24学年第二学期八年级区测考试'"
    )
    
    semester = forms.ModelChoiceField(
        label="学期",
        queryset=Semester.objects.all(),
        help_text="选择考试所属学期"
    )
    
    exam_type = forms.ChoiceField(
        label="考试类型",
        choices=[
            ('MIDTERM', '期中考试'),
            ('FINAL', '期末考试'),
            ('MONTHLY', '月考'),
            ('WEEKLY', '周考'),
            ('ENTRANCE', '入学考试'),
            ('GRAD', '毕业考试'),
            ('DIST-TEST', '区测'),
            ('CITY-TEST', '市测'),
            ('OTHER', '其他')
        ],
        help_text="选择考试类型"
    )
    
    region = forms.ModelChoiceField(
        label="所属区域",
        queryset=Region.objects.all(),
        help_text="选择数据所属区域"
    )
    
    sheet_name = forms.CharField(
        label="工作表名称", 
        max_length=100, 
        initial="Sheet1",
        help_text="Excel工作表名称，默认为Sheet1"
    )
    
    create_students = forms.BooleanField(
        label="自动创建学生", 
        required=False, 
        initial=True,
        help_text="如果学生不存在，自动创建学生记录"
    )
    
    update_students = forms.BooleanField(
        label="更新学生信息", 
        required=False, 
        initial=False,
        help_text="更新已存在学生的信息"
    )
    
    skip_teacher = forms.BooleanField(
        label="跳过教师关联", 
        required=False, 
        initial=True,
        help_text="不关联教师信息，适用于只想导入学生和成绩数据的场景"
    )
    
    debug = forms.BooleanField(
        label="调试模式", 
        required=False, 
        initial=True,
        help_text="显示详细的导入过程信息"
    )
    
    # 添加教师选择字段
    teacher_id = forms.ModelChoiceField(
        label="默认教师",
        queryset=Teacher.objects.filter(status='ACTIVE'),
        required=False,
        help_text="选择导入成绩时使用的默认教师"
    )
    
    # 添加smart_match选项
    smart_match = forms.BooleanField(
        label="智能匹配教师", 
        required=False, 
        initial=False,
        help_text="尝试通过多种方式智能匹配教师（仅在不跳过教师关联时有效）"
    )
    
    # 添加强制导入选项
    force = forms.BooleanField(
        label="强制导入", 
        required=False, 
        initial=False,
        help_text="强制导入数据，忽略一些安全检查（如重复导入警告等）"
    )
    
    # 添加教师历史导入选项
    import_teacher_history = forms.BooleanField(
        label="同时导入教师历史记录", 
        required=False, 
        initial=False,
        help_text="导入成绩的同时，自动导入或更新教师授课历史记录"
    )
    
    # 添加教师文件路径选项
    teacher_file = forms.FileField(
        label="教师历史数据文件", 
        required=False,
        help_text="可选。如不提供，将尝试从成绩文件中提取教师信息"
    )
    
    # 添加教师工作表名称
    teacher_sheet = forms.CharField(
        label="教师数据工作表", 
        initial="Sheet1", 
        required=False,
        help_text="教师历史数据所在的Excel工作表名称"
    )
    
    # 添加自动创建教师选项
    auto_create_missing_teachers = forms.BooleanField(
        label="自动创建不存在的教师", 
        required=False, 
        initial=False,
        help_text="自动为找不到匹配记录的教师创建新记录"
    )


class TeacherSubjectsImportForm(forms.Form):
    """
    教师学科班级关联数据导入表单。
    
    提供用户上传教师学科班级关联数据Excel文件并设置相关参数的界面。
    
    Args:
        forms.Form: Django表单基类
    
    Returns:
        表单实例
    """
    file = forms.FileField(
        label="选择Excel文件",
        help_text="上传包含教师学科班级关联数据的Excel文件"
    )
    
    semester = forms.ModelChoiceField(
        label="学期",
        queryset=Semester.objects.all(),
        help_text="选择关联数据所属学期"
    )
    
    sheet_name = forms.CharField(
        label="工作表名称", 
        max_length=100, 
        initial="Sheet1",
        help_text="Excel工作表名称，默认为Sheet1"
    )
    
    update = forms.BooleanField(
        label="更新现有记录", 
        required=False, 
        initial=True,
        help_text="更新已存在的教师学科班级关联记录"
    )
    
    auto_create_teachers = forms.BooleanField(
        label="自动创建教师", 
        required=False, 
        initial=False,
        help_text="自动创建不存在的教师记录"
    )
    
    batch_size = forms.IntegerField(
        label="批处理大小", 
        initial=100,
        min_value=1,
        max_value=1000,
        help_text="设置批量处理的记录数量"
    )
    
    dry_run = forms.BooleanField(
        label="试运行模式", 
        required=False, 
        initial=False,
        help_text="测试导入但不实际写入数据库"
    )
    
    debug = forms.BooleanField(
        label="调试模式", 
        required=False, 
        initial=True,
        help_text="显示详细的导入过程信息"
    )


class ImportDataAdmin(admin.ModelAdmin):
    """
    数据导入管理界面。
    
    提供通过Admin界面上传和导入数据的功能。
    
    Args:
        admin.ModelAdmin: Django Admin模型管理类
    
    Returns:
        管理界面配置类实例
    """
    
    change_list_template = "admin/import_data_changelist.html"
    
    def get_urls(self):
        """集中管理所有Admin相关路由"""
        urls = super().get_urls()
        custom_urls = [
            path('data-import/', self.admin_site.admin_view(self.data_import_view), name='data_import'),
            path('scores-import/', self.admin_site.admin_view(self.scores_import_view), name='scores_import'),
            path('teacher-import/', self.admin_site.admin_view(self.teacher_import_view), name='teacher_import'),
            # 添加其他Admin相关路由...
        ]
        return custom_urls + urls
    
    @admin.display(description='数据导入')
    def data_import_view(self, request):
        """
        数据导入选择界面视图
        
        Args:
            request: HTTP请求对象
            
        Returns:
            渲染后的HTTP响应
        """
        context = dict(
           self.admin_site.each_context(request),
           title="数据导入工具"
        )
        return render(request, 'admin/import_data.html', context)
    
    @staticmethod
    def _build_import_view(form_class, task_handler, title):
        """
        工厂方法，创建导入数据视图函数。
        
        Args:
            form_class: 表单类
            task_handler: 任务处理函数
            title: 页面标题
            
        Returns:
            视图函数
        """
        def view_func(self, request):
            """
            导入数据视图函数
            
            Args:
                request: HTTP请求对象
                
            Returns:
                HTTP响应
            """
            # 获取管理后台URL
            admin_index_url = request.session.get('admin_index_url', '/admin/')
            referer = request.META.get('HTTP_REFERER', '')
            if 'default-admin' in referer:
                admin_index_url = '/default-admin/'
            elif 'admin' in referer:
                admin_index_url = '/admin/'
            request.session['admin_index_url'] = admin_index_url
            
            if request.method == 'POST':
                form = form_class(request.POST, request.FILES)
                if form.is_valid():
                    try:
                        # 保存上传的文件
                        fs = FileSystemStorage(location=settings.MEDIA_ROOT)
                        file = request.FILES['file']
                        file_name = fs.save(file.name, file)
                        file_path = os.path.join(settings.MEDIA_ROOT, file_name)
                        
                        # 获取教师历史导入相关选项（针对成绩导入）
                        teacher_file_path = None
                        teacher_sheet = 'Sheet1'
                        
                        if isinstance(form, ScoresImportForm):
                            import_teacher_history = form.cleaned_data.get('import_teacher_history', False)
                            auto_create_missing_teachers = form.cleaned_data.get('auto_create_missing_teachers', False)
                            
                            if 'teacher_file' in request.FILES and import_teacher_history:
                                teacher_file = request.FILES['teacher_file']
                                teacher_file_name = fs.save(teacher_file.name, teacher_file)
                                teacher_file_path = os.path.join(settings.MEDIA_ROOT, teacher_file_name)
                                teacher_sheet = form.cleaned_data.get('teacher_sheet', 'Sheet1')
                                
                        # 创建任务ID
                        task_id = str(uuid.uuid4())
                        
                        # 准备参数
                        kwargs = ImportDataAdmin._prepare_task_kwargs(form, file_path, task_id, teacher_file_path, teacher_sheet)
                        
                        # 创建进度跟踪器实例
                        tracker = ProgressTracker(task_id=task_id, total_steps=6)
                        tracker.update(status='PROCESSING', message='正在准备导入任务...')
                        
                        # 将现有追踪器传递给任务
                        kwargs['existing_tracker'] = tracker
                        
                        # 在后台线程中执行任务
                        thread = threading.Thread(
                            target=task_handler,
                            kwargs=kwargs,
                            daemon=True
                        )
                        thread.start()

                        # 立即重定向到进度页面，不需要在 session 中存储任务信息
                        return HttpResponseRedirect(
                            reverse('import_progress') + f'?task_id={task_id}'
                        )
                    except Exception as e:
                        # 记录异常
                        print(f"导入初始化错误: {str(e)}")
                        messages.error(request, f"导入过程中发生错误: {str(e)}")
                        return render(request, 'admin/import_error.html', {
                            'title': "导入错误",
                            'error': str(e),
                            'admin_index_url': admin_index_url
                        })
                else:
                    # 表单验证失败
                    print(f"表单验证失败，错误: {form.errors}")
                    return render(request, 'admin/import_form.html', {
                        'form': form,
                        'title': title,
                        'admin_index_url': admin_index_url,
                        'form_errors': form.errors,
                    })
            else:
                # GET请求展示表单
                form = form_class()
                
            return render(request, 'admin/import_form.html', {
                'form': form,
                'title': title,
                'admin_index_url': admin_index_url
            })
        
        return view_func
    
    @staticmethod
    def _prepare_task_kwargs(form, file_path, task_id, teacher_file_path=None, teacher_sheet='Sheet1'):
        """
        准备任务参数。
        
        根据表单类型准备相应的任务参数。
        
        Args:
            form: 表单实例
            file_path: 文件路径
            task_id: 任务ID
            teacher_file_path: 教师文件路径（可选）
            teacher_sheet: 教师工作表名称（可选）
            
        Returns:
            任务参数字典
        """
        kwargs = {
            'file_path': file_path,
            'task_id': task_id,
            'debug': form.cleaned_data.get('debug', False)
        }
        
        if isinstance(form, ScoresImportForm):
            # 成绩导入参数
            
            kwargs.update({
                'exam_id': form.cleaned_data['exam_id'],
                'exam_name': form.cleaned_data['exam_name'], 
                'exam_type': form.cleaned_data['exam_type'],
                'semester_id': form.cleaned_data['semester'].semester_id,
                'teacher_id': str(form.cleaned_data.get('teacher_id', 'T001')),
                'region_id': form.cleaned_data['region'].region_id,
                'sheet_name': form.cleaned_data['sheet_name'],
                'create_students': form.cleaned_data['create_students'],
                'update_students': form.cleaned_data['update_students'],
                'skip_teacher': form.cleaned_data['skip_teacher'],
                'smart_match': form.cleaned_data.get('smart_match', False),
                'force': form.cleaned_data.get('force', False),
                'import_teacher_history': form.cleaned_data.get('import_teacher_history', False),
                'teacher_file': teacher_file_path,
                'teacher_sheet': teacher_sheet,
                'auto_create_missing_teachers': form.cleaned_data.get('auto_create_missing_teachers', False)
            })
        elif isinstance(form, TeacherSubjectsImportForm):
            # 教师学科班级关联数据导入参数
            kwargs.update({
                'semester_id': form.cleaned_data['semester'].semester_id,
                'sheet': form.cleaned_data['sheet_name'],
                'update': form.cleaned_data['update'],
                'auto_create_teachers': form.cleaned_data['auto_create_teachers'],
                'batch_size': form.cleaned_data['batch_size'],
                'dry_run': form.cleaned_data['dry_run']
            })
            
        return kwargs
    
    # 使用工厂方法创建视图函数
    scores_import_view = _build_import_view(
        form_class=ScoresImportForm,
        task_handler=run_import_task_sync,
        title="导入学生成绩数据（如果是学生过去的成绩，可以选择导入教师历史记录）"
    )
    
    teacher_import_view = _build_import_view(
        form_class=TeacherSubjectsImportForm,
        task_handler=run_import_task_sync,  # 使用相同的导入处理器
        title="导入教师学科班级关联数据"
    )

# 注册管理界面类
DataImportToolAdmin = ImportDataAdmin

def convert_semester_format(semester_obj):
    """
    将Semester对象转换为所需的字符串格式
    
    Args:
        semester_obj: Semester模型实例
        
    Returns:
        str: 转换后的学期格式字符串
    """
    # 假设Semester模型有semester_id字段
    if hasattr(semester_obj, 'semester_id'):
        return semester_obj.semester_id
    
    # 如果是字符串，尝试进行格式转换
    if isinstance(semester_obj, str):
        return semester_obj.replace('学年第', '-').replace('学期', '')
    
    # 如果都不是，尝试将对象转换为字符串
    return str(semester_obj)

def import_scores_view(request):
    """处理成绩导入请求的视图函数"""
    if request.method == 'POST':
        # 获取表单数据
        file_path = request.POST.get('file_path')
        exam_id = request.POST.get('exam_id')
        exam_name = request.POST.get('exam_name')
        exam_type = request.POST.get('exam_type', 'MIDTERM')
        semester = request.POST.get('semester')
        teacher_id = request.POST.get('teacher_id')
        region_id = request.POST.get('region_id')
        sheet_name = request.POST.get('sheet_name', 'Sheet1')
        
        # 获取复选框选项
        create_students = 'create_students' in request.POST
        update_students = 'update_students' in request.POST
        skip_teacher = 'skip_teacher' in request.POST
        debug = 'debug' in request.POST
        smart_match = 'smart_match' in request.POST
        force = 'force' in request.POST
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 直接调用命令
        try:
            kwargs = {
                'file_path': file_path,
                'exam_id': exam_id,
                'exam_name': exam_name,
                'exam_type': exam_type,
                'semester': semester,
                'teacher_id': teacher_id,
                'region_id': region_id,
                'sheet': sheet_name,
                'task_id': task_id,
                'debug': debug,
                'smart_match': smart_match,
                'force': force,
            }
            
            # 添加布尔参数
            if create_students:
                kwargs['create_students'] = True
            if update_students:
                kwargs['update_students'] = True
            if skip_teacher:
                kwargs['skip_teacher'] = True
            
            # 调用命令
            call_command('import_scores', **kwargs)
            result = {'success': True, 'task_id': task_id}
        except Exception as e:
            result = {'success': False, 'task_id': task_id, 'error': str(e)}
        
        # 重定向到进度页面
        return HttpResponseRedirect(
            reverse('static_progress') + f'?task_id={task_id}'
        )

def task_progress_view(request, task_id):
    """获取任务进度的API视图"""
    task_id = str(task_id)
    # 直接从文件读取进度信息
    progress_file = os.path.join(settings.MEDIA_ROOT, 'progress', f"{task_id}.json")
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
        except:
            progress_data = {"status": "ERROR", "message": "无法读取进度文件"}
    else:
        progress_data = {"status": "NOT_FOUND", "message": "找不到任务进度"}
    
    return JsonResponse(progress_data)

def import_progress_view(request):
    """显示导入进度页面的视图函数"""
    task_id = request.GET.get('task_id')
    if not task_id:
        return HttpResponseRedirect(reverse('admin:index'))
    
    context = {
        'task_id': task_id,
        'page_title': '导入进度',
    }
    
    # 渲染进度页面模板
    return render(request, 'admin/import_progress.html', context) 