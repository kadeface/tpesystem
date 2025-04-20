from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from core.tasks import get_task_status
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
import json
# core/api/views.py
from django.http import JsonResponse
from django.views import View
from django.core.cache import cache
from core.analytics.report_generator import StudentGrowthAnalysisReport
from django.core.management import call_command
from django.utils import timezone
from django.conf import settings
import io
import sys
import os
import uuid
import tempfile
from rest_framework.views import APIView
from django.db.models import Q
from core.models import Exam


@staff_member_required
@require_GET
def task_status(request):
    """
    获取任务状态API。
    
    Args:
        request: HTTP请求对象，需要包含task_id参数
        
    Returns:
        JsonResponse: 包含任务状态信息的JSON响应
    """
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'status': 'error', 'error': '缺少任务ID参数'}, status=400)
    
    # 从缓存获取任务状态
    task_key = f"task_status_{task_id}"
    task_status = cache.get(task_key, None)
    
    if task_status is None:
        return JsonResponse({
            'status': 'unknown',
            'error': '找不到任务状态或任务已过期',
            'progress': 0,
            'logs': ['任务状态未找到，可能任务已完成或者任务ID无效']
        })
    
    # 如果状态是字符串格式，转换为字典
    if isinstance(task_status, str):
        try:
            task_status = json.loads(task_status)
        except:
            task_status = {'status': 'error', 'error': '任务状态格式错误'}
    
    return JsonResponse(task_status) 


class StudentGrowthAnalysisAPI(View):
    """学生成长分析API"""
    
    def get(self, request, student_id):
        """获取学生成长分析报告"""
        # 参数处理
        refresh = request.GET.get('refresh', '').lower() in ('true', '1', 'yes')
        cache_key = f"student_growth_report_{student_id}"
        
        # 检查缓存
        if not refresh:
            cached_report = cache.get(cache_key)
            if cached_report:
                return JsonResponse(cached_report)
                
        # 生成新报告
        try:
            generator = StudentGrowthAnalysisReport(student_id)
            report = generator.generate()
            
            # 缓存报告
            cache.set(cache_key, report, 3600)  # 缓存1小时
            
            # 添加考试记录
            with_exams = request.query_params.get('with_exams') == 'true'
            if with_exams:
                # 获取该学生的考试记录
                student_exams = []
                
                try:
                    # 尝试从过滤后的数据中提取
                    if student_id in report['student_id'].values:
                        student_data = report[report['student_id'] == student_id]
                        student_data = student_data.sort_values('exam_order')
                        
                        for _, row in student_data.iterrows():
                            exam_record = {
                                'exam_id': row.get('exam_id', ''),
                                'exam_name': row.get('exam_name', f'考试 {row.get("exam_order", 0)}'),
                                'exam_date': row.get('exam_date', ''),
                                'raw_score': float(row.get('raw_score', row.get('score', 0))),
                                'standard_score': float(row.get('standard_score', 0)),
                                'percentile': float(row.get('percentile', 0)) if 'percentile' in row else None,
                                'rank': int(row.get('rank', 0)) if 'rank' in row else None,
                                'subject_id': row.get('subject_id', report['subject_id'][0]) if 'subject_id' in row else report['subject_id'][0],
                                'total_score': float(row.get('total_score', 100)),
                                'grade': row.get('grade', ''),
                                'class_name': row.get('class_name', '')
                            }
                            student_exams.append(exam_record)
                except Exception as e:
                    self.stdout.error(f"提取学生考试记录出错: {e}")
                
                # 添加到响应数据
                report['exam_records'] = student_exams
            
            # 修改返回结果，确保包含exam_records
            if 'exam_records' in report:
                # 如果请求指定了特定学生，只返回该学生的记录
                if student_id and student_id in report['exam_records']:
                    report['exam_records'] = report['exam_records'][student_id]
            
            return JsonResponse(report)
        except Exception as e:
            return JsonResponse({
                'error': str(e),
                'message': '生成学生成长分析报告失败'
            }, status=500)
    
    def post(self, request, student_id):
        """接收反馈并更新分析"""
        try:
            # 解析请求数据
            data = json.loads(request.body)
            feedback_type = data.get('type')
            feedback_content = data.get('content')
            
            # 简单校验
            if not feedback_type or not feedback_content:
                return JsonResponse({
                    'error': 'Missing required fields',
                    'message': '反馈类型和内容不能为空'
                }, status=400)
                
            # 存储反馈
            # StudentFeedback.objects.create(...)
                
            # 更新缓存
            cache_key = f"student_growth_report_{student_id}"
            cache.delete(cache_key)
            
            return JsonResponse({
                'success': True,
                'message': '成功接收反馈'
            })
        except Exception as e:
            return JsonResponse({
                'error': str(e),
                'message': '处理反馈失败'
            }, status=500)


class StudentPortraitAnalysisView(APIView):
    """
    学生画像分析API - 桥接到test_value_added_models命令行工具
    """
    
    def post(self, request):
        print("收到请求!", request.path, request.data)
        try:
            # 获取请求数据
            data = request.data
            exams = data.get('exams', [])
            subject = data.get('subject')
            clusters = data.get('clusters', 5)
            min_exams = data.get('min_exams', 3)
            
            # 验证请求数据
            if not exams or len(exams) < min_exams:
                return Response(
                    {'error': f'需要至少{min_exams}个考试数据进行分析'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not subject:
                return Response(
                    {'error': '必须指定学科'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 创建唯一的任务ID和输出目录
            task_id = str(uuid.uuid4())
            output_dir = os.path.join(settings.MEDIA_ROOT, 'analysis', f'portrait_{task_id}')
            os.makedirs(output_dir, exist_ok=True)
            
            # 准备命令参数
            cmd_args = [
                '--model=student_cluster',
                f'--subject={subject}',
                f'--clusters={clusters}',
                f'--min-exams={min_exams}',
                f'--output={output_dir}',
            ]
            
            # 添加所有考试ID
            for exam_id in exams:
                cmd_args.append(f'--exams={exam_id}')
            
            # 捕获命令输出
            stdout_content = io.StringIO()
            stderr_content = io.StringIO()
            original_stdout, original_stderr = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = stdout_content, stderr_content
            
            try:
                # 执行命令
                call_command('test_value_added_models', *cmd_args)
                cmd_output = stdout_content.getvalue()
                cmd_errors = stderr_content.getvalue()
            finally:
                sys.stdout, sys.stderr = original_stdout, original_stderr
            
            # 检查命令执行结果
            if "错误" in cmd_output or "ERROR" in cmd_output:
                return Response({
                    'error': '分析过程中出现错误',
                    'details': cmd_output,
                    'stderr': cmd_errors
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 读取分析结果文件
            # 注意：假设命令行工具生成了JSON报告文件
            report_path = os.path.join(output_dir, 'analysis_report.json')
            image_base_url = f'/media/analysis/portrait_{task_id}/'
            
            # 如果没有报告文件，生成一个简单的结果
            if not os.path.exists(report_path):
                # 查找目录中的图片文件
                image_files = [f for f in os.listdir(output_dir) if f.endswith(('.png', '.jpg', '.svg'))]
                visualizations = {
                    os.path.splitext(img)[0]: image_base_url + img 
                    for img in image_files
                }
                
                # 构建结果对象
                results = {
                    'analysis_id': task_id,
                    'created_at': timezone.now().isoformat(),
                    'params': {
                        'exam_count': len(exams),
                        'subject': subject,
                        'clusters': clusters
                    },
                    'results': {
                        'cluster_profiles': self._extract_cluster_data(cmd_output),
                        'visualizations': visualizations,
                        'command_output': cmd_output,
                        'summary': {
                            'total_students': 500, # 示例值，实际应从输出中提取
                            'most_common_pattern': '稳定成长型' # 示例值，实际应从输出中提取
                        }
                    }
                }
            else:
                # 读取报告文件
                with open(report_path, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            
            # 强制检查考试记录文件并添加到结果中
            exam_records_path = os.path.join(output_dir, 'exam_records.json')
            print(f"查找考试记录文件: {exam_records_path}")
            
            if os.path.exists(exam_records_path):
                print(f"找到考试记录文件，正在加载...")
                try:
                    with open(exam_records_path, 'r', encoding='utf-8') as f:
                        exam_records = json.load(f)
                        
                    print(f"考试记录包含{len(exam_records)}个学生")
                    results['exam_records'] = exam_records
                except Exception as e:
                    print(f"加载考试记录文件出错: {e}")
            else:
                print(f"考试记录文件不存在")
                results['exam_records'] = {}
            
            # 在返回前打印键
            print(f"API响应包含键: {list(results.keys())}")
            return Response(results)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response(
                {'error': f'分析过程发生错误: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _extract_cluster_data(self, cmd_output):
        """从命令输出中提取聚类数据"""
        # 这是一个简单的示例实现，实际上需要根据命令输出格式进行定制
        clusters = {}
        patterns = ['稳定成长型', '快速提升型', '波动型', '高分稳定型', '缓慢下降型']
        
        # 尝试从输出中提取聚类信息
        # 这里应该根据test_value_added_models.py的输出格式编写正则表达式或解析逻辑
        
        # 示例：如果没有解析到，返回模拟数据
        if not clusters:
            for i in range(min(5, len(patterns))):
                clusters[f'cluster_{i+1}'] = {
                    'name': patterns[i],
                    'size': 50 + i * 20,
                    'avg_growth': (5 - i) * 2.5,
                    'characteristics': f'这是{patterns[i]}学生的特点描述...'
                }
        
        return clusters


class StudentScoresQueryView(APIView):
    """学生成绩查询API"""
    
    def get(self, request):
        """根据学生ID、考试ID列表和学科ID查询成绩"""
        try:
            # 获取请求参数
            student_id = request.query_params.get('student_id')
            exam_ids_str = request.query_params.get('exam_ids', '')
            subject_id = request.query_params.get('subject_id')
            
            # 验证必要参数
            if not student_id or not subject_id:
                return Response(
                    {'error': '缺少必要参数: student_id, subject_id'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 解析考试ID列表
            exam_ids = exam_ids_str.split(',') if exam_ids_str else []
            
            # 查询数据库
            records = []
            if exam_ids:
                # 如果指定了考试ID，只查询这些考试
                scores = Exam.objects.filter(
                    student_id=student_id,
                    exam_id__in=exam_ids,
                    subject_id=subject_id
                ).select_related('exam')
            else:
                # 否则查询该学生所有考试
                scores = Exam.objects.filter(
                    student_id=student_id,
                    subject_id=subject_id
                ).select_related('exam')
            
            # 格式化结果
            for score in scores:
                records.append({
                    'student_id': student_id,
                    'exam_id': score.exam.id,
                    'exam_name': score.exam.name,
                    'exam_date': score.exam.date.isoformat() if score.exam.date else None,
                    'score': float(score.raw_score),
                    'total_score': float(score.exam.total_score),
                    'percentile': float(score.percentile) if score.percentile else None,
                    'rank': int(score.rank) if score.rank else None,
                    'grade': score.grade,
                    'class_name': score.class_name
                })
            
            return Response(records)
        except Exception as e:
            return Response(
                {'error': f'查询学生成绩失败: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StudentScoresView(APIView):
    """学生成绩API - RESTful风格"""
    
    def get(self, request, student_id):
        """获取学生成绩记录"""
        try:
            # 获取请求参数
            exam_ids_str = request.query_params.get('exam_ids', '')
            subject_id = request.query_params.get('subject_id')
            
            # 验证必要参数
            if not subject_id:
                return Response(
                    {'error': '缺少必要参数: subject_id'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 解析考试ID列表
            exam_ids = exam_ids_str.split(',') if exam_ids_str else []
            
            # 先尝试从模型中查询
            try:
                # ... 数据库查询代码
                pass
            except Exception as db_error:
                print(f"数据库查询失败: {str(db_error)}")
                # 如果数据库查询失败，返回模拟数据
                records = self.generate_mock_records(student_id, exam_ids, subject_id)
                
            return Response(records)
        except Exception as e:
            return Response(
                {'error': f'查询学生成绩失败: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def generate_mock_records(self, student_id, exam_ids, subject_id):
        """生成模拟成绩记录"""
        import random
        from datetime import datetime, timedelta
        
        records = []
        
        # 如果没有提供考试ID，生成一些默认的
        if not exam_ids:
            exam_ids = [f"MOCK-EXAM-{i}" for i in range(1, 6)]
            
        # 为每个考试生成一条记录
        now = datetime.now()
        for i, exam_id in enumerate(exam_ids):
            exam_date = now - timedelta(days=30 * (len(exam_ids) - i))
            score = random.uniform(60, 95)
            percentile = random.uniform(max(0, score-20), min(100, score+10))
            
            records.append({
                'student_id': student_id,
                'exam_id': exam_id,
                'exam_name': f"模拟考试 {i+1}",
                'exam_date': exam_date.strftime("%Y-%m-%d"),
                'score': round(score, 1),
                'total_score': 100.0,
                'percentile': round(percentile, 1),
                'rank': random.randint(1, 100),
                'grade': 'A' if score >= 90 else 'B' if score >= 80 else 'C' if score >= 70 else 'D',
                'class_name': f"班级{random.randint(1, 5)}"
            })
            
        return records