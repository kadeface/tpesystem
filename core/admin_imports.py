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

import tempfile
import os
import io
import time
import threading
import uuid
from .tasks import run_import_task_async

# 导入admin_site

from .models import  Semester, Region, Teacher

from .management.commands.import_teacher_subjects import Command as ImportTeacherSubjectsCommand


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
        """
        获取URL配置。
        
        添加自定义URL路由以支持数据导入功能。
        
        Returns:
            URL路由配置列表
        """
        urls = super().get_urls()
        custom_urls = [
            path('import-scores/', self.admin_site.admin_view(self.import_scores_view), name='import-scores'),
            path('import-teacher-subjects/', self.admin_site.admin_view(self.import_teacher_subjects_view), name='import-teacher-subjects'),
            path('import-data/', self.admin_site.admin_view(self.import_data_view), name='import-data'),
        ]
        return custom_urls + urls
    
    def import_data_view(self, request):
        """
        数据导入选择界面视图。
        
        提供选择不同数据导入功能的入口界面。
        
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
    
    def import_scores_view(self, request):
        """
        处理成绩数据导入的视图函数。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            HttpResponse: 导入结果页面
            
        Raises:
            ValidationError: 当文件格式或数据无效时抛出
        """
        if request.method == 'POST':
            # 添加调试信息
            print("接收到POST请求")
            print(f"表单数据: {request.POST}")
            print(f"文件数据: {request.FILES}")
            
            form = ScoresImportForm(request.POST, request.FILES)
            if form.is_valid():
                # 获取表单数据
                file = request.FILES['file']
                
                # 检查文件大小，提供更好的用户提示
                file_size_mb = file.size / (1024 * 1024)  # 转换为MB
                is_large_file = file_size_mb > 5  # 超过5MB认为是大文件
                
                if is_large_file:
                    print(f"处理大文件: {file.name} ({file_size_mb:.2f}MB)")
                
                exam_id = form.cleaned_data['exam_id']
                exam_name = form.cleaned_data['exam_name']
                semester = form.cleaned_data['semester']
                exam_type = form.cleaned_data['exam_type']
                region = form.cleaned_data['region']
                sheet_name = form.cleaned_data['sheet_name']
                create_students = form.cleaned_data['create_students']
                update_students = form.cleaned_data['update_students']
                skip_teacher = form.cleaned_data['skip_teacher']
                debug = form.cleaned_data['debug']
                
                # 获取smart_match选项
                smart_match = form.cleaned_data.get('smart_match', False)
                
                # 获取force选项
                force = form.cleaned_data.get('force', False)
                
                # 正确处理teacher_id字段
                if form.cleaned_data.get('teacher_id'):
                    teacher_id = str(form.cleaned_data['teacher_id'])
                else:
                    # 如果未选择教师，使用默认值T001
                    teacher_id = 'T001'
                
                # 保存上传的文件
                fs = FileSystemStorage(location=settings.MEDIA_ROOT)
                file_name = fs.save(file.name, file)
                file_path = os.path.join(settings.MEDIA_ROOT, file_name)
                
                # 添加调试输出
                print("===== 表单数据 =====")
                print(f"文件名: {file.name}, 大小: {file.size}")
                print(f"考试ID: {exam_id}")
                print(f"考试名称: {exam_name}")
                print(f"学期: {semester}")
                print(f"教师ID: {teacher_id}")
                # ...其他字段...
                
                # 添加开始处理提示
                print(f"开始处理文件: {file_path}")
                
                # 准备命令参数
                output = io.StringIO()
                
                # 修改为异步处理，支持进度反馈
                import threading
                import time
                
                # 创建一个进度存储对象
                if not hasattr(request.session, 'import_progress'):
                    request.session['import_progress'] = {
                        'current_step': 0,
                        'total_steps': 7,
                        'progress': 0,
                        'message': '准备开始导入...',
                        'is_complete': False
                    }
                    request.session.save()
                
                # 定义进度更新函数
                def update_progress(step, progress, message):
                    request.session['import_progress'] = {
                        'current_step': step,
                        'total_steps': 7,
                        'progress': progress,
                        'message': message,
                        'is_complete': False
                    }
                    request.session.save()
                
                # 导入完成后的回调
                def import_complete(output):
                    request.session['import_progress'] = {
                        'current_step': 7,
                        'total_steps': 7,
                        'progress': 100,
                        'message': '导入完成!',
                        'is_complete': True,
                        'output': output.getvalue()
                    }
                    request.session.save()
                
                # 创建任务ID
                task_id = str(uuid.uuid4())
                
                # 启动异步任务而非直接执行
                thread = threading.Thread(
                    target=run_import_task_async,
                    args=(file_path, exam_id, exam_name, exam_type, semester.semester_id, 
                         teacher_id, region.region_id, sheet_name, create_students, 
                         update_students, skip_teacher, debug, smart_match, force, task_id)
                )
                thread.daemon = True
                thread.start()
                
                # 添加调试输出
                print(f"启动异步任务，任务ID: {task_id}")
                
                # 返回确认页面
                return render(request, 'admin/import_progress.html', {
                    'title': '导入进行中',
                })
            else:
                # 表单验证失败
                print(f"表单验证失败，错误: {form.errors}")
                return render(request, 'admin/import_form.html', {
                    'form': form,
                    'title': "导入学生成绩数据",
                    'admin_index_url': request.session.get('admin_index_url', '/admin/'),
                    'form_errors': form.errors,  # 传递表单错误到模板
                })
        else:
            # GET请求展示表单
            form = ScoresImportForm()
            return render(request, 'admin/import_form.html', {'form': form})
    
    def import_teacher_subjects_view(self, request):
        """
        教师学科班级关联数据导入界面视图。
        
        处理教师学科班级关联数据导入表单的提交和文件处理。
        
        Args:
            request: HTTP请求对象
            
        Returns:
            渲染后的HTTP响应
        """
        if request.method == 'POST':
            form = TeacherSubjectsImportForm(request.POST, request.FILES)
            if form.is_valid():
                # 保存上传的文件
                upload_file = request.FILES['file']
                fs = FileSystemStorage(location=tempfile.gettempdir())
                filename = fs.save(upload_file.name, upload_file)
                file_path = os.path.join(tempfile.gettempdir(), filename)
                
                # 准备导入参数
                import_args = {
                    'file_path': file_path,
                    'semester_id': form.cleaned_data['semester'].semester_id,
                    'sheet': form.cleaned_data['sheet_name'],
                    'update': form.cleaned_data['update'],
                    'auto_create_teachers': form.cleaned_data['auto_create_teachers'],
                    'batch_size': form.cleaned_data['batch_size'],
                    'dry_run': form.cleaned_data['dry_run'],
                    'debug': form.cleaned_data['debug'],
                }
                
                # 捕获输出
                output = io.StringIO()
                
                try:
                    # 调用导入命令
                    cmd = ImportTeacherSubjectsCommand(stdout=output, stderr=output)
                    cmd.handle(**import_args)
                    
                    # 显示成功消息
                    messages.success(request, "教师学科班级关联数据导入成功！")
                    
                    # 在上下文中添加命令输出
                    context = dict(
                        self.admin_site.each_context(request),
                        title="教师学科班级关联数据导入结果",
                        output=output.getvalue(),
                    )
                    
                    # 清理临时文件
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    
                    return render(request, 'admin/import_result.html', context)
                    
                except Exception as e:
                    messages.error(request, f"导入过程中发生错误: {str(e)}")
                    
                    # 在上下文中添加错误信息和命令输出
                    context = dict(
                        self.admin_site.each_context(request),
                        title="教师学科班级关联数据导入错误",
                        error=str(e),
                        output=output.getvalue(),
                    )
                    
                    # 清理临时文件
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    
                    return render(request, 'admin/import_result.html', context)
        else:
            form = TeacherSubjectsImportForm()
        
        context = dict(
            self.admin_site.each_context(request),
            title="导入教师学科班级关联数据",
            form=form,
        )
        return render(request, 'admin/import_form.html', context)

    @classmethod
    def get_import_data_view(cls, request):
        """提供数据导入选择界面视图"""
        # 从会话中获取管理站点URL，默认为标准admin
        admin_index_url = request.session.get('admin_index_url', '/admin/')
        
        # 检查referer以确定正确的管理站点URL
        referer = request.META.get('HTTP_REFERER', '')
        if 'default-admin' in referer:
            admin_index_url = '/default-admin/'
        elif 'admin' in referer:
            admin_index_url = '/admin/'
        
        # 保存到会话
        request.session['admin_index_url'] = admin_index_url
        
        return render(request, 'admin/import_data.html', {
            'title': "数据导入工具",
            'admin_index_url': admin_index_url
        })

    @classmethod
    def get_import_scores_view(cls, request):
        """提供成绩导入界面视图"""
        admin_index_url = request.session.get('admin_index_url', '/admin/')
        
        if request.method == 'POST':
            form = ScoresImportForm(request.POST, request.FILES)
            if form.is_valid():
                # 获取表单数据
                file = request.FILES['file']
                exam_id = form.cleaned_data['exam_id']
                exam_name = form.cleaned_data['exam_name']
                semester = form.cleaned_data['semester']
                exam_type = form.cleaned_data['exam_type']
                region = form.cleaned_data['region']
                sheet_name = form.cleaned_data['sheet_name']
                create_students = form.cleaned_data['create_students']
                update_students = form.cleaned_data['update_students']
                skip_teacher = form.cleaned_data['skip_teacher']
                debug = form.cleaned_data['debug']
                
                # 获取smart_match选项
                smart_match = form.cleaned_data.get('smart_match', False)
                
                # 获取force选项
                force = form.cleaned_data.get('force', False)
                
                # 正确处理teacher_id字段
                if form.cleaned_data.get('teacher_id'):
                    teacher_id = str(form.cleaned_data['teacher_id'])
                else:
                    # 如果未选择教师，使用默认值T001
                    teacher_id = 'T001'
                
                # 保存上传的文件
                fs = FileSystemStorage(location=settings.MEDIA_ROOT)
                file_name = fs.save(file.name, file)
                file_path = os.path.join(settings.MEDIA_ROOT, file_name)
                
                # 确保使用semester_id
                semester_id = semester.semester_id if hasattr(semester, 'semester_id') else semester
                
                # 创建任务ID
                task_id = str(uuid.uuid4())
                
                # 启动异步任务而非直接执行
                thread = threading.Thread(
                    target=run_import_task_async,
                    args=(file_path, exam_id, exam_name, exam_type, semester_id, 
                         teacher_id, region.region_id, sheet_name, create_students, 
                         update_students, skip_teacher, debug, smart_match, force, task_id)
                )
                thread.daemon = True
                thread.start()
                
                # 添加调试输出
                print(f"启动异步任务，任务ID: {task_id}")
                
                # 重定向到进度页面
                return redirect(f"/core/import-progress/?task_id={task_id}")
                
        # 显示表单
        else:
            form = ScoresImportForm()
        
        return render(request, 'admin/import_form.html', {
            'title': "导入学生成绩数据",
            'form': form,
            'admin_index_url': admin_index_url
        })

    @classmethod
    def get_import_teacher_subjects_view(cls, request):
        """提供教师学科班级关联导入界面视图"""
        # 从会话中获取管理站点URL
        admin_index_url = request.session.get('admin_index_url', '/admin/')
        
        form = TeacherSubjectsImportForm()
        context = {
            'title': "导入教师学科班级关联数据",
            'form': form,
            'admin_index_url': admin_index_url
        }
        return render(request, 'admin/import_form.html', context)

DataImportToolAdmin = ImportDataAdmin 

def convert_semester_format(semester_display):
    # 实现从用户界面格式到数据库格式的转换逻辑
    # 这里需要根据实际需求实现转换逻辑
    # 这里只是一个示例，实际实现需要根据具体情况
    return semester_display.replace('学年第', '-').replace('学期', '') 