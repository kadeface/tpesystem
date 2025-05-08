from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.management import call_command
import uuid
import json
from .models import AnalysisTask
from .serializers import AnalysisTaskSerializer
from rest_framework.views import APIView
import random
from datetime import datetime, timedelta
from core.value_added_models import TVAMValueAddedModel, ValueAddedDataProcessor
from core.management.commands.education_data_provider import EducationDataProvider
import pandas as pd
import numpy as np
import logging
import os
from django.http import JsonResponse, HttpResponse
from core.models import Grade, Exam, Score, Student, Semester, StudentHistory
import re
from django.core.exceptions import FieldError
from django.conf import settings
from edu_insights.models import DistrictExamFeature, SchoolExamFeature, ClassExamFeature, StudentExamFeature
from threading import Thread
from django.db.models import Avg, Count, Max, Min, StdDev
from django.db import transaction
import statistics
from django.db.models import Avg, StdDev, Count, Max, F

logger = logging.getLogger(__name__)

class AnalysisTaskViewSet(viewsets.ModelViewSet):
    """
    分析任务API视图集
    
    提供分析任务创建、查询和状态更新API
    
    Args:
        queryset: 查询集
        serializer_class: 序列化器类
    """
    queryset = AnalysisTask.objects.all()
    serializer_class = AnalysisTaskSerializer
    
    def create(self, request):
        """
        创建新分析任务
        
        Args:
            request: 包含分析参数的请求
            
        Returns:
            Response: 包含新建任务信息的响应
        """
        try:
            # 获取参数
            params = request.data
            
            # 创建任务记录
            task = AnalysisTask.objects.create(params=params)
            
            # 启动后台任务
            # 使用Python进程或Celery (在生产环境推荐)
            from threading import Thread
            thread = Thread(target=self._run_analysis_task, args=(task.task_id, params))
            thread.setDaemon(True)
            thread.start()
            
            serializer = self.serializer_class(task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def _run_analysis_task(self, task_id, params):
        """
        运行分析任务
        
        Args:
            task_id: 任务ID
            params: 分析参数
        """
        try:
            # 从参数中提取命令行参数
            exams = params.get('exams', [])
            subject = params.get('subject')
            models = params.get('model', [])
            control = params.get('control', [])
            baseline = params.get('baseline')
            
            # 确保exams是列表
            exams_list = exams if isinstance(exams, list) else [exams]
            
            # 确保models是列表
            models_list = models if isinstance(models, list) else [models]
            
            # 构建命令参数 - 保持列表格式不变!
            cmd_kwargs = {
                'exams': exams_list,
                'subject': subject,
                'model': models_list,  # 直接传递列表，不要转为字符串
                'task_id': task_id
            }
            
            # 添加其他参数
            if control:
                control_list = control if isinstance(control, list) else [control]
                cmd_kwargs['control'] = control_list
                
            if baseline:
                cmd_kwargs['baseline'] = baseline
            
            # 添加聚类参数（如果存在）
            for cluster_param in ['clusters', 'min_exams', 'max_clusters', 'min_clusters']:
                if cluster_param in params:
                    # 直接使用参数名称，不进行格式转换
                    cmd_kwargs[cluster_param] = params[cluster_param]
            
            # 添加布尔标志参数
            for flag_param in ['visualize_clusters', 'find_optimal_clusters']:
                if params.get(flag_param):
                    # 直接使用参数名称，不进行格式转换
                    cmd_kwargs[flag_param] = True
            
            # 调用Django命令
            call_command('test_value_added_models', **cmd_kwargs)
        except Exception as e:
            # 更新任务状态为失败
            task = AnalysisTask.objects.get(task_id=task_id)
            task.status = 'failed'
            task.error = str(e)
            task.save()
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        获取任务状态
        
        Args:
            request: HTTP请求
            pk: 任务ID
            
        Returns:
            Response: 包含任务状态的响应
        """
        task = get_object_or_404(AnalysisTask, task_id=pk)
        data = {
            'task_id': task.task_id,
            'status': task.status,
            'progress': task.progress,
            'created_at': task.created_at,
            'updated_at': task.updated_at
        }
        
        if task.error:
            data['error'] = task.error
            
        return Response(data)
    
    @action(detail=True, methods=['get'])
    def results(self, request, pk=None):
        """
        获取分析结果
        
        Args:
            request: HTTP请求
            pk: 任务ID
            
        Returns:
            Response: 包含分析结果的响应
        """
        task = get_object_or_404(AnalysisTask, task_id=pk)
        
        if task.status != 'completed':
            return Response({
                'status': task.status,
                'progress': task.progress,
                'message': '任务尚未完成，无法获取结果'
            })
            
        results = task.get_results()
        if not results:
            return Response({'error': '无法获取结果或结果文件不存在'}, status=status.HTTP_404_NOT_FOUND)
            
        return Response(results)

class StudentExamScoresView(APIView):
    """学生考试成绩API"""
    
    def get(self, request, student_id):
        """获取学生的考试成绩记录"""
        try:
            # 获取查询参数
            exam_ids_str = request.query_params.get('exam_ids', '')
            subject_id = request.query_params.get('subject_id')
            
            # 验证参数
            if not subject_id:
                return Response({'error': '缺少必要参数: subject_id'}, status=status.HTTP_400_BAD_REQUEST)
            
            # 解析考试ID列表
            exam_ids = exam_ids_str.split(',') if exam_ids_str else []
            
            # 尝试数据库查询，但任何错误都回退到模拟数据
            try:
                # Debug信息
                print(f"开始查询学生 {student_id} 的成绩, 考试ID: {exam_ids}, 学科: {subject_id}")
                
                # 尝试查询，但不依赖于具体模型
                # 这里采用安全的导入方式
                try:
                    from core.models import Score
                    model_exists = True
                except ImportError:
                    print("Score模型不存在，将使用模拟数据")
                    model_exists = False
                
                records = []
                
                if model_exists:
                    # 构建查询参数
                    query_params = {
                        'student_id': student_id,
                    }
                    
                    if subject_id:
                        query_params['subject_id'] = subject_id
                    
                    if exam_ids:
                        query_params['exam_id__in'] = exam_ids
                    
                    # 尝试查询
                    try:
                        # 使用select_related获取关联的考试信息
                        records_queryset = Score.objects.filter(**query_params).select_related('exam', 'subject')
                        
                        # 将查询结果转换为列表
                        for record in records_queryset:
                            # 使用ORM方法从数据库中安全获取值
                            records.append({
                                'student_id': student_id,
                                'exam_id': str(getattr(record.exam, 'exam_id', '')),
                                'exam_name': getattr(record.exam, 'exam_name', ''),
                                'exam_date': getattr(record.exam, 'start_time', datetime.now()).strftime('%Y-%m-%d'),
                                'score': float(record.raw_score if record.raw_score is not None else 0),
                                'standard_score': float(record.standard_score if record.standard_score is not None else 0),
                                'percentile': float(record.percentile if record.percentile is not None else 0),
                                'is_real_data': True
                            })
                    except Exception as db_error:
                        print(f"数据库查询失败: {str(db_error)}")
                        # 使用模拟数据
                
                # 如果没有找到真实记录，使用模拟数据
                if not records:
                    print(f"未找到学生 {student_id} 的真实成绩记录，使用模拟数据")
                    records = self._generate_mock_records(student_id, exam_ids, subject_id)
                
                return Response(records)
            
            except Exception as e:
                # 捕获所有异常，确保API不会崩溃
                print(f"查询处理失败: {str(e)}")
                records = self._generate_mock_records(student_id, exam_ids, subject_id)
                return Response(records)
        
        except Exception as outer_e:
            # 最外层错误处理
            print(f"API处理异常: {str(outer_e)}")
            try:
                # 尝试生成模拟数据
                records = self._generate_mock_records(student_id, [], '')
                return Response(records)
            except:
                # 如果连模拟数据都无法生成，返回空数组
                return Response([])
    
    def _generate_mock_records(self, student_id, exam_ids, subject_id):
        """生成模拟成绩记录数据"""
        records = []
        
        # 如果没有提供考试ID，生成一些默认的
        if not exam_ids:
            exam_ids = [f"MOCK-EXAM-{i}" for i in range(1, 6)]
        
        # 获取学生所属聚类(如果有)，为模拟数据添加特点
        score_pattern = 'random'
        try:
            from core.models import StudentProfile
            profile = StudentProfile.objects.filter(student_id=student_id).first()
            if profile and profile.cluster_label:
                if '上升' in profile.cluster_label:
                    score_pattern = 'increase'
                elif '下降' in profile.cluster_label:
                    score_pattern = 'decrease'
                elif '波动' in profile.cluster_label:
                    score_pattern = 'fluctuate'
                elif '稳定' in profile.cluster_label:
                    score_pattern = 'stable'
        except:
            pass
            
        # 为每个考试生成一条记录
        now = datetime.now()
        base_score = 65 + random.random() * 15
        
        for i, exam_id in enumerate(exam_ids):
            # 计算考试日期：从当前时间开始，每个考试往前推一个月
            exam_date = now - timedelta(days=30 * (len(exam_ids) - i))
            
            # 根据模式生成分数
            score = base_score
            if score_pattern == 'increase':
                # 稳步上升
                score += i * 5 + (random.random() * 3 - 1)
            elif score_pattern == 'decrease':
                # 稳步下降
                score -= i * 4 + (random.random() * 3 - 1)  
            elif score_pattern == 'fluctuate':
                # 大幅波动
                score += (random.random() * 20 - 10)
            elif score_pattern == 'stable':
                # 稳定，小幅波动
                score += (random.random() * 6 - 3)
            else:
                # 随机波动
                score += (random.random() * 10 - 5)
                
            # 确保分数在合理范围内
            score = max(40, min(100, score))
            
            # 计算百分位
            percentile = min(99, max(1, score - 10 + random.random() * 20))
            
            # 生成记录
            records.append({
                'student_id': student_id,
                'exam_id': exam_id,
                'exam_name': f"考试 {i+1}",
                'exam_date': exam_date.strftime("%Y-%m-%d"),
                'score': round(score, 1),
                'total_score': 100.0,
                'percentile': round(percentile, 1),
                'rank': random.randint(1, 100),
                'grade': 'A' if score >= 90 else 'B' if score >= 80 else 'C' if score >= 70 else 'D',
                'class_name': f"班级{random.randint(1, 5)}",
                'is_mock_data': True  # 标记为模拟数据
            })
            
        return records 

class TeacherValueAddedView(APIView):
    """
    教师增值分析视图
    
    根据用户选择的参数动态生成教师增值分析结果
    """
    def get(self, request):
        """
        处理教师增值分析请求
        
        Args:
            request: 包含筛选条件的HTTP请求
            
        Returns:
            Response: 包含分析结果的HTTP响应
        """
        try:
            # 获取筛选参数
            region = request.query_params.get('region')
            stage = request.query_params.get('stage')
            subject = request.query_params.get('subject')
            grade = request.query_params.get('grade')
            target_exam = request.query_params.get('target_exam')
            baseline_exam = request.query_params.get('baseline_exam')
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
            
            # 构建过滤条件
            filters = {}
            if region:
                filters['region_id'] = region
            if stage:
                # 如果有学段筛选，根据学段筛选年级
                if stage == 'elementary':
                    filters['grade_level__lte'] = 6
                elif stage == 'junior':
                    filters['grade_level__gt'] = 6
                    filters['grade_level__lte'] = 9
                elif stage == 'senior':
                    filters['grade_level__gt'] = 9
            if subject:
                filters['subject_id'] = subject
            if grade:
                filters['grade'] = grade
            if target_exam or baseline_exam:
                exam_ids = []
                if target_exam:
                    exam_ids.append(target_exam)
                if baseline_exam:
                    exam_ids.append(baseline_exam)
                filters['exam_id__in'] = exam_ids
            
            # 获取数据
            data_provider = EducationDataProvider()
            
            # 从数据提供者获取数据
            logger.info(f"获取教师增值分析数据，过滤条件: {filters}")
            raw_data = data_provider.get_scores_data(filters)
            
            if raw_data is None or len(raw_data) == 0:
                logger.warning("没有找到符合条件的数据")
                return Response({
                    'overview': {'regionAvg': 0, 'schoolAvg': 0, 'subjectAvg': 0},
                    'teacherRanking': [],
                    'schoolRanking': [],
                    'teacherTrend': {'teachers': [], 'timePoints': [], 'series': []},
                    'total': 0
                })
            
            # 准备数据处理器
            data_processor = ValueAddedDataProcessor()
            
            # 确定基准考试
            if baseline_exam:
                data_processor.baseline_exam = baseline_exam
            
            # 创建并配置TVAM模型
            tvam_model = TVAMValueAddedModel(raw_data, data_processor)
            tvam_model.configure(entity_type='teacher', covariates=['gender', 'ses'])
            
            # 执行分析
            tvam_model.fit()
            
            # 获取分析结果
            effect_estimates = tvam_model.get_effect_estimates()
            student_results = tvam_model.get_student_results()
            
            # 处理教师排名数据
            teacher_ranking = []
            if effect_estimates is not None and len(effect_estimates) > 0:
                # 确保必要的列存在
                required_columns = ['teacher_id', 'teacher_name', 'effect']
                for col in required_columns:
                    if col not in effect_estimates.columns:
                        logger.warning(f"缺少必要的列: {col}")
                        effect_estimates[col] = 'Unknown' if col != 'effect' else 0
                
                # 排序并添加排名
                effect_estimates = effect_estimates.sort_values('effect', ascending=False).reset_index(drop=True)
                effect_estimates['rank'] = effect_estimates.index + 1
                
                # 计算百分位数
                effect_estimates['percentile'] = effect_estimates['effect'].rank(pct=True) * 100
                
                # 准备教师排名数据
                for _, row in effect_estimates.iterrows():
                    teacher_ranking.append({
                        'rank': int(row['rank']),
                        'teacherName': row['teacher_name'],
                        'school': row.get('school_name', 'Unknown'),
                        'subject': subject,
                        'valueAdded': float(row['effect']),
                        'percentile': float(row['percentile'])
                    })
            
            # 处理学校排名数据
            school_ranking = []
            if raw_data is not None and 'school_id' in raw_data.columns and 'school_name' in raw_data.columns:
                # 按学校分组计算平均分
                school_data = raw_data.groupby(['school_id', 'school_name']).agg({
                    'standard_score': ['mean', 'count']
                }).reset_index()
                school_data.columns = ['school_id', 'school_name', 'avg_score', 'count']
                
                # 排序
                school_data = school_data.sort_values('avg_score', ascending=False).reset_index(drop=True)
                
                # 准备学校排名数据
                for _, row in school_data.iterrows():
                    school_ranking.append({
                        'schoolName': row['school_name'],
                        'valueAdded': float(row['avg_score'])
                    })
            
            # 处理教师趋势数据
            teacher_trend = {
                'teachers': [],
                'timePoints': [],
                'series': []
            }
            
            # 如果有多个考试，则可以显示趋势
            if raw_data is not None and 'exam_id' in raw_data.columns and 'teacher_id' in raw_data.columns:
                # 获取唯一的时间点（考试）
                time_points = sorted(raw_data['exam_id'].unique().tolist())
                teacher_trend['timePoints'] = time_points
                
                # 选择前5名教师（如果不足5名则全部选择）
                top_teachers = effect_estimates.head(min(5, len(effect_estimates)))
                
                for _, teacher in top_teachers.iterrows():
                    teacher_id = teacher['teacher_id']
                    teacher_name = teacher['teacher_name']
                    teacher_trend['teachers'].append(teacher_name)
                    
                    # 计算该教师在每个时间点的平均分
                    teacher_data = raw_data[raw_data['teacher_id'] == teacher_id]
                    values = []
                    
                    for tp in time_points:
                        tp_data = teacher_data[teacher_data['exam_id'] == tp]
                        if len(tp_data) > 0:
                            values.append(float(tp_data['standard_score'].mean()))
                        else:
                            values.append(None)  # 没有数据的时间点
                    
                    teacher_trend['series'].append({
                        'name': teacher_name,
                        'type': 'line',
                        'data': values
                    })
            
            # 计算平均值
            region_avg = np.mean([t['valueAdded'] for t in teacher_ranking]) if teacher_ranking else 0
            school_avg = np.mean([t['valueAdded'] for t in teacher_ranking if t['school'] == region]) if region and teacher_ranking else 0
            subject_avg = np.mean([t['valueAdded'] for t in teacher_ranking]) if teacher_ranking else 0
            
            # 分页
            total_count = len(teacher_ranking)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_teacher_ranking = teacher_ranking[start_index:end_index] if teacher_ranking else []
            
            # 构建响应
            response_data = {
                'overview': {
                    'regionAvg': round(region_avg, 2),
                    'schoolAvg': round(school_avg, 2),
                    'subjectAvg': round(subject_avg, 2)
                },
                'teacherRanking': paginated_teacher_ranking,
                'schoolRanking': school_ranking,
                'teacherTrend': teacher_trend,
                'total': total_count
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.exception(f"教师增值分析请求处理失败: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def teacher_value_added(request):
    """
    基于已有增值分析结果计算教师增值分析
    """
    # 获取筛选参数
    region_id = request.GET.get('region')
    grade_id = request.GET.get('grade')
    subject_id = request.GET.get('subject')
    exams = request.GET.getlist('exams[]')
    
    if len(exams) < 2:
        return Response({"error": "需要至少选择两次考试"}, status=400)
    
    target_exam_id = exams[0]
    baseline_exam_id = exams[1]
    
    try:
        # 1. 查找与当前条件匹配的分析任务
        matching_tasks = find_matching_analysis_tasks(
            region_id=region_id,
            grade_id=grade_id,
            subject_id=subject_id,
            target_exam_id=target_exam_id,
            baseline_exam_id=baseline_exam_id
        )
        
        if not matching_tasks:
            # 如果没有找到匹配的任务，创建一个新的分析任务
            task = create_value_added_analysis_task(
                region_id=region_id,
                grade_id=grade_id, 
                subject_id=subject_id,
                target_exam_id=target_exam_id,
                baseline_exam_id=baseline_exam_id
            )
            
            # 等待任务完成（设置超时时间）
            task_results = wait_for_task_completion(task.id, timeout=30)
        else:
            # 使用找到的最新任务
            latest_task = matching_tasks.order_by('-created_at').first()
            task_results = latest_task.get_results()
        
        # 2. 从任务结果中提取学生数据
        student_data = extract_student_data_from_results(task_results)
        
        # 3. 按班级聚合而不是按教师 - 使用新函数
        # teacher_data = aggregate_by_teacher(student_data) - 旧代码
        # teacher_value_added = calculate_teacher_value_added(teacher_data) - 旧代码
        
        # 使用新的按班级聚合函数
        class_data = aggregate_by_class(student_data)
        
        # 4. 计算排名和百分位 - 使用与教师相同的排名函数
        ranked_classes = rank_teachers(class_data)  # 函数名保持不变
        
        return Response({
            'data': ranked_classes,
            'status': 'success',
            'message': '成功获取班级增值数据'
        })
    
    except Exception as e:
        logger.error(f"计算教师增值失败: {str(e)}")
        return Response({"error": f"计算教师增值失败: {str(e)}"}, status=500)

def find_matching_analysis_tasks(region_id, grade_id, subject_id, target_exam_id, baseline_exam_id):
    """
    查找匹配当前筛选条件的分析任务
    """
    # 过滤完成的任务
    tasks = AnalysisTask.objects.filter(
        status='completed',
        task_type='value_added'
    )
    
    # 进一步过滤满足条件的任务
    matching_tasks = []
    for task in tasks:
        params = task.parameters
        if (params.get('region') == region_id and
            params.get('grade') == grade_id and
            params.get('subject') == subject_id and
            params.get('target_exam') == target_exam_id and
            params.get('baseline_exam') == baseline_exam_id):
            matching_tasks.append(task)
    
    return matching_tasks

def create_value_added_analysis_task(region_id, grade_id, subject_id, target_exam_id, baseline_exam_id):
    """
    创建并启动新的增值分析任务
    """
    task_id = str(uuid.uuid4())
    task = AnalysisTask.objects.create(
        id=task_id,
        task_type='value_added',
        status='pending',
        parameters={
            'region': region_id,
            'grade': grade_id,
            'subject': subject_id,
            'target_exam': target_exam_id,
            'baseline_exam': baseline_exam_id
        }
    )
    
    # 构建命令参数
    cmd_kwargs = {
        'task_id': task_id,
        'region': region_id,
        'grade': grade_id,
        'subject': subject_id,
        'target_exam': target_exam_id,
        'baseline_exam': baseline_exam_id
    }
    
    # 调用命令启动分析任务
    call_command('test_value_added_models', **cmd_kwargs)
    
    return task

def wait_for_task_completion(task_id, timeout=30):
    """
    等待任务完成
    """
    import time
    start_time = time.time()
    
    while True:
        task = AnalysisTask.objects.get(id=task_id)
        
        if task.status == 'completed':
            return task.get_results()
        
        if task.status == 'failed':
            raise Exception(f"任务执行失败: {task.error_message}")
        
        if time.time() - start_time > timeout:
            raise Exception("任务执行超时")
        
        time.sleep(1)  # 等待1秒后重新检查

def extract_student_data_from_results(results):
    """
    从分析结果中提取学生数据
    """
    student_data = []
    
    # 提取学生层次（聚类）和增值数据
    if 'clusters' in results and 'valueAdded' in results:
        clusters = results['clusters']
        value_added = results['valueAdded']
        
        for student_id, cluster in clusters.items():
            if student_id in value_added:
                student_data.append({
                    'student_id': student_id,
                    'cluster': cluster,
                    'value_added': value_added[student_id],
                    'baseline_score': results.get('baselineScores', {}).get(student_id, 0),
                    'target_score': results.get('targetScores', {}).get(student_id, 0),
                    # 提取其他需要的学生信息
                    'teacher_id': results.get('studentInfo', {}).get(student_id, {}).get('teacher_id'),
                    'class_id': results.get('studentInfo', {}).get(student_id, {}).get('class_id')
                })
    
    return student_data

def aggregate_by_class(student_data):
    """
    按班级聚合学生数据并计算增值指标
    
    Args:
        student_data: 学生增值数据列表
        
    Returns:
        list: 班级增值数据列表
    """
    class_map = {}
    
    # 1. 按班级分组学生数据
    for student in student_data:
        class_key = f"{student.get('school_name')}-{student.get('class_name')}"
        if class_key not in class_map:
            class_map[class_key] = {
                'className': student.get('class_name'),
                'schoolName': student.get('school_name'),
                'students': [],
                'clusters': {}
            }
        
        class_map[class_key]['students'].append(student)
        
        # 按聚类分组
        cluster = student.get('cluster')
        if cluster is not None:
            cluster_label = student.get('cluster_label', f'类别{cluster}')
            if cluster not in class_map[class_key]['clusters']:
                class_map[class_key]['clusters'][cluster] = {
                    'label': cluster_label,
                    'students': []
                }
            class_map[class_key]['clusters'][cluster]['students'].append(student)
    
    # 2. 计算班级增值指标
    class_results = []
    for class_idx, (class_key, class_data) in enumerate(class_map.items()):
        # 跳过没有学生的班级
        if not class_data['students']:
            continue
            
        # 计算班级总体增值分
        total_improvement = sum(student.get('total_improvement', 0) for student in class_data['students'])
        overall_value_added = total_improvement / len(class_data['students']) if class_data['students'] else 0
        
        # 计算分层增值数据
        layer_value_added = []
        for cluster, cluster_data in class_data['clusters'].items():
            if not cluster_data['students']:
                continue
                
            # 层次学生的平均增值
            layer_improvement = sum(student.get('total_improvement', 0) for student in cluster_data['students'])
            layer_avg_value = layer_improvement / len(cluster_data['students'])
            
            # 基准和目标分数
            baseline_scores = [student.get('start_level', 0) for student in cluster_data['students']]
            target_scores = [student.get('end_level', 0) for student in cluster_data['students']]
            
            baseline_avg = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0
            target_avg = sum(target_scores) / len(target_scores) if target_scores else 0
            
            # 贡献率
            contribution = len(cluster_data['students']) / len(class_data['students'])
            
            layer_value_added.append({
                'layer': cluster_data['label'],
                'studentCount': len(cluster_data['students']),
                'valueAdded': layer_avg_value,
                'contribution': contribution,
                'baselineScore': baseline_avg,
                'targetScore': target_avg
            })
        
        # 按基准分数排序
        layer_value_added = sorted(layer_value_added, key=lambda x: x['baselineScore'], reverse=True)
        
        # 计算能力维度
        ability_dimensions = calculate_ability_dimensions(layer_value_added)
        
        # 生成教学建议
        teaching_advice = generate_teaching_advice(layer_value_added, ability_dimensions)
        
        # 构建班级结果
        class_results.append({
            'classId': f"class-{class_idx + 1}",
            'className': class_data['className'],
            'schoolName': class_data['schoolName'],
            'totalStudents': len(class_data['students']),
            'overallValueAdded': overall_value_added,
            'layerValueAdded': layer_value_added,
            'abilityDimensions': ability_dimensions,
            'teachingAdvice': teaching_advice
        })
    
    return class_results

def generate_teaching_advice(layer_value_added, ability_dimensions):
    """生成教学建议"""
    strengths = []
    improvements = []
    
    # 识别优势
    ability_scores = list(ability_dimensions.items())
    ability_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 添加前两项作为优势
    if len(ability_scores) >= 1 and ability_scores[0][1] > 60:
        if ability_scores[0][0] == 'topStudentTeaching':
            strengths.append('优等生培养能力突出，善于发掘学生潜能')
        elif ability_scores[0][0] == 'middleStudentImprovement':
            strengths.append('中等生提升效果显著，教学方法针对性强')
        elif ability_scores[0][0] == 'weakStudentSupport':
            strengths.append('后进生帮扶成效明显，关注学习困难学生')
        elif ability_scores[0][0] == 'balancedDevelopment':
            strengths.append('各层次学生均衡发展，教学资源分配合理')
        elif ability_scores[0][0] == 'potentialExploration':
            strengths.append('善于激发学生潜能，教学效果显著')
    
    # 添加改进建议
    if len(ability_scores) >= 2 and ability_scores[-1][1] < 70:
        if ability_scores[-1][0] == 'topStudentTeaching':
            improvements.append('可加强优等生培养策略，提供更多挑战性任务')
        elif ability_scores[-1][0] == 'middleStudentImprovement':
            improvements.append('可进一步关注中等生的学习需求，提供针对性辅导')
        elif ability_scores[-1][0] == 'weakStudentSupport':
            improvements.append('建议加强后进生基础知识巩固，提供更多个性化帮扶')
        elif ability_scores[-1][0] == 'balancedDevelopment':
            improvements.append('可进一步平衡教学资源分配，关注不同层次学生需求')
        elif ability_scores[-1][0] == 'potentialExploration':
            improvements.append('建议尝试更多元化教学方法，挖掘学生多方面潜能')
    
    # 通用建议
    strategies = [
        '结合学生层次数据，实施分层教学，提供差异化学习材料和任务',
        '关注学生学习过程，及时调整教学策略，实现精准教学',
        '建立完善的学习支持体系，为不同层次学生提供适当的学习资源',
        '定期分析学生学习数据，识别学习问题，开展有针对性的教学干预'
    ]
    
    return {
        'strengths': strengths or ['班级整体教学质量良好'],
        'improvements': improvements or ['建议结合学生具体情况，进一步优化教学策略'],
        'strategies': strategies
    }

def rank_teachers(class_data):
    """
    计算班级排名和百分位
    
    Args:
        class_data: 班级数据列表
        
    Returns:
        list: 添加了排名和百分位的班级数据列表
    """
    # 按整体增值排序
    sorted_classes = sorted(
        class_data, 
        key=lambda x: x['overallValueAdded'], 
        reverse=True
    )
    
    total_classes = len(sorted_classes)
    
    for i, class_info in enumerate(sorted_classes, 1):
        rank = i + 1
        class_info['rank'] = rank
        class_info['percentile'] = ((total_classes - rank) / total_classes) * 100 if total_classes > 0 else 0
    
    return sorted_classes 

def calculate_ability_dimensions(layer_value_added):
    """
    计算教学能力维度指标
    
    Args:
        layer_value_added: 分层增值数据
        
    Returns:
        dict: 教学能力维度指标
    """
    # 防御性编程 - 确保输入有效
    if not layer_value_added:
        return {
            'topStudentTeaching': 50,
            'middleStudentImprovement': 50,
            'weakStudentSupport': 50,
            'balancedDevelopment': 50,
            'potentialExploration': 50
        }
    
    # 按照基准分数将层次分为高中低三组
    sorted_layers = sorted(layer_value_added, key=lambda x: x['baselineScore'], reverse=True)
    
    # 初始化能力维度指标
    ability_dimensions = {
        'topStudentTeaching': 0,
        'middleStudentImprovement': 0,
        'weakStudentSupport': 0,
        'balancedDevelopment': 0,
        'potentialExploration': 0
    }
    
    if len(sorted_layers) >= 3:
        # 划分层次
        top_layer = sorted_layers[0]
        middle_layers = sorted_layers[1:-1]
        bottom_layer = sorted_layers[-1]
        
        # 1. 优等生培养能力 - 基于顶层学生的增值
        ability_dimensions['topStudentTeaching'] = normalize_score(top_layer['valueAdded'] * 20 + 50)
        
        # 2. 中等生提升能力 - 基于中间层学生的增值
        middle_value_added = 0
        middle_students = 0
        for layer in middle_layers:
            middle_value_added += layer['valueAdded'] * layer['studentCount']
            middle_students += layer['studentCount']
        
        avg_middle_value_added = middle_value_added / middle_students if middle_students > 0 else 0
        ability_dimensions['middleStudentImprovement'] = normalize_score(avg_middle_value_added * 20 + 50)
        
        # 3. 后进生帮扶能力 - 基于底层学生的增值
        ability_dimensions['weakStudentSupport'] = normalize_score(bottom_layer['valueAdded'] * 20 + 60)
        
        # 4. 均衡发展能力 - 各层次增值差异性越小，得分越高
        layer_values = [layer['valueAdded'] for layer in sorted_layers]
        weights = [layer['studentCount'] for layer in sorted_layers]
        
        std_dev = calculate_weighted_std(layer_values, weights)
        balance_score = 100 - (std_dev * 50)  # 标准差越小，均衡性越好
        ability_dimensions['balancedDevelopment'] = normalize_score(balance_score)
        
        # 5. 潜能激发能力 - 全班最大增值
        max_value_added = max(layer['valueAdded'] for layer in sorted_layers)
        ability_dimensions['potentialExploration'] = normalize_score(max_value_added * 15 + 50)
    else:
        # 层次少于三个时使用简化计算
        avg_value_added = sum(layer['valueAdded'] * layer['studentCount'] for layer in sorted_layers) / sum(layer['studentCount'] for layer in sorted_layers) if sorted_layers else 0
        
        for key in ability_dimensions:
            ability_dimensions[key] = normalize_score(avg_value_added * 20 + 50)
    
    return ability_dimensions

def exams_by_semester(request, semester_id):
    """获取学期相关的考试列表"""
    logger.info(f"获取学期ID {semester_id} 的考试")
    
    try:
        exams = Exam.objects.filter(
            score__semester_id=semester_id
        ).distinct().values('id', 'name')
        
        exams_list = list(exams)
        logger.info(f"找到 {len(exams_list)} 个考试: {exams_list}")
        
        return JsonResponse(exams_list, safe=False)
    except Exception as e:
        logger.error(f"获取考试数据出错: {e}")
        return HttpResponse(status=500, content=str(e))

def exams_by_semester_grade(request, semester_id, grade_id):
    """获取学期和年级相关的考试列表"""
    try:
        print(f"查询参数: semester_id={semester_id}, grade_id={grade_id}")
        
        # 从年级ID中提取级别
        grade_level = None
        match = re.search(r'_(\d+)_', grade_id)
        if match:
            grade_level = match.group(1)
            print(f"从年级ID {grade_id} 中提取出级别: {grade_level}")
        else:
            print(f"无法从年级ID {grade_id} 提取级别")
            return JsonResponse([], safe=False)
        
        # 查找包含相同级别的所有年级ID
        matching_grades = Grade.objects.filter(grade_id__contains=f"_{grade_level}_")
        matched_grade_ids = list(matching_grades.values_list('grade_id', flat=True))
        
        if not matched_grade_ids:
            print(f"未找到级别为 {grade_level} 的年级")
            return JsonResponse([], safe=False)
            
        print(f"找到匹配年级: {matched_grade_ids}")
        
        # 查询满足条件的考试
        scores = Score.objects.filter(
            semester_id=semester_id,
            student__current_grade_id__in=matched_grade_ids
        )
        
        print(f"找到 {scores.count()} 条成绩记录")
        
        exam_ids = scores.values_list('exam_id', flat=True).distinct()
        print(f"找到 {len(exam_ids)} 个唯一考试ID")
        
        exams = Exam.objects.filter(exam_id__in=list(exam_ids))
        print(f"找到 {exams.count()} 个考试记录")
        
        result = [{'id': exam.exam_id, 'name': exam.exam_name} for exam in exams]
        return JsonResponse(result, safe=False)
    except Exception as e:
        import traceback
        print(f"获取考试数据出错: {e}")
        print(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)

def exams_by_current_grade(request, current_grade_id):
    """
    获取当前年级学生的所有历史考试记录
    
    返回按历史年级组织的考试记录，包含时间轴所需信息
    """
    try:
        # 从当前grade_id提取年级级别
        grade_parts_match = re.search(r'G\d+_(\d+)_(\d+)', current_grade_id)
        if not grade_parts_match:
            return JsonResponse({"error": "无效的年级ID格式"}, status=400)
            
        current_grade_level = int(grade_parts_match.group(1))  # 例如：10
        school_code = re.search(r'(G\d+)_', current_grade_id).group(1)  # 提取学校代码，如G06
        
        print(f"处理年级级别: {current_grade_level}, 学校代码: {school_code}")
        
        # 1. 查找系统中最新的已完成学期
        latest_semester = Semester.objects.filter(status='COMPLETED').order_by('-start_date').first()
        if not latest_semester:
            return JsonResponse({"error": "系统中没有可用的已完成学期数据"}, status=404)
            
        print(f"找到最新已完成学期: {latest_semester.semester_id}")
        
        # 提取最新学期代码
        semester_code_match = re.search(r'(\d+)-(\d+)-(\d+)', latest_semester.semester_id)
        if semester_code_match:
            year2 = semester_code_match.group(2)[-2:]
            term = semester_code_match.group(3)
            latest_semester_code = f"{year2}{term}"  # 例如：251
            print(f"最新学期代码: {latest_semester_code}")
        else:
            latest_semester_code = "000"  # 默认值
        
        # 2. 构建当前年级在最新学期的年级ID
        current_grade_latest_id = f"{school_code}_{current_grade_level}_{latest_semester_code}"
        print(f"构建的最新年级ID: {current_grade_latest_id}")
        
        # 3. 获取当前年级下的学生
        students = []
        try:
            #grade = Grade.objects.get(grade_id=current_grade_latest_id)
            students = StudentHistory.objects.filter(grade_id=current_grade_latest_id)
            print(f"通过最新年级ID查询，找到 {students.count()} 名学生")
        except Grade.DoesNotExist:
            print(f"未找到年级 {current_grade_latest_id}，尝试替代方法")
               
        # 4. 优化：选择多名学生并筛选共同考试
        student_exam_count = {}
        for student in students[:50]:  # 限制检查前50名学生提高性能
            count = Score.objects.filter(student_id=student.student_id).count()
            if count > 0:  # 只统计有考试记录的学生
                student_exam_count[student.student_id] = count
        
        # 如果没有找到有考试记录的学生
        if not student_exam_count:
            print("没有学生有考试记录")
            return JsonResponse([], safe=False)
        
        # 按考试数量排序并选取考试数量最多的前5名学生
        sorted_students = sorted(student_exam_count.items(), key=lambda x: x[1], reverse=True)
        representative_students = [student_id for student_id, _ in sorted_students[:5]]
        print(f"选择了 {len(representative_students)} 名代表学生")
        
        # 获取这些学生的所有考试记录
        scores = Score.objects.filter(student_id__in=representative_students)
        
        # 统计哪些考试至少有2名学生共同参加，过滤个别学生特有的考试
        exam_frequency = {}
        for score in scores:
            if score.exam_id not in exam_frequency:
                exam_frequency[score.exam_id] = set()
            exam_frequency[score.exam_id].add(score.student_id)
        
        # 筛选至少有2名学生参加的考试
        common_exam_ids = [exam_id for exam_id, students in exam_frequency.items() 
                          if len(students) >= 2]
        
        # 过滤scores只保留共同考试
        scores = scores.filter(exam_id__in=common_exam_ids)
        
        # 获取所有考试信息
        exam_ids = common_exam_ids
        exams = Exam.objects.filter(exam_id__in=exam_ids)
        
        # 6. 收集考试信息并确定其所属年级
        exams_by_grade_level = {}  # 按年级分组的考试列表
        
        for exam in exams:
            # 获取此考试的学期信息
            exam_score = scores.filter(exam_id=exam.exam_id).first()
            if not exam_score:
                continue
                
            semester_id = exam_score.semester_id
            
            # 获取学期信息
            try:
                semester = Semester.objects.get(semester_id=semester_id)
                semester_name = semester.semester_id
                semester_date = semester.start_date
            except Semester.DoesNotExist:
                semester_name = semester_id
                semester_date = None
            
            # 解析学期ID获取学期代码
            semester_code = None
            semester_code_match = re.search(r'(\d+)-(\d+)-(\d+)', semester_id)
            if semester_code_match:
                year2 = semester_code_match.group(2)[-2:]
                term = semester_code_match.group(3)
                semester_code = f"{year2}{term}"  # 例如：232
            
            # ----- 确定此考试对应的年级级别 -----
            exam_grade_level = None
            
            # 方法1: 从考试名称中提取年级信息
            name_patterns = [
                (r'高三|高3|12年级|毕业班', 12),  # 高三
                (r'高二|高2|11年级', 11),        # 高二
                (r'高一|高1|10年级', 10),        # 高一
                (r'初三|初3|9年级', 9),          # 初三
                (r'初二|初2|8年级', 8),          # 初二
                (r'初一|初1|7年级', 7),          # 初一
                (r'六年级|6年级', 6),            # 小学六年级
                (r'五年级|5年级', 5),            # 以此类推
                (r'四年级|4年级', 4),
                (r'三年级|3年级', 3),
                (r'二年级|2年级', 2),
                (r'一年级|1年级', 1),
            ]
            
            for pattern, grade in name_patterns:
                if re.search(pattern, exam.exam_name):
                    exam_grade_level = grade
                    print(f"从考试名称 '{exam.exam_name}' 识别到年级: {exam_grade_level}")
                    break
            
            # 方法2: 基于学期代码估算年级
            if not exam_grade_level and semester_code and latest_semester_code:
                try:
                    # 解析学期代码
                    current_year = int(latest_semester_code[:2])
                    exam_year = int(semester_code[:2])
                    
                    # 计算年级差异
                    year_diff = current_year - exam_year
                    
                    # 如果差异合理，计算考试时的年级
                    if 0 <= year_diff <= current_grade_level:
                        exam_grade_level = current_grade_level - year_diff
                        print(f"从学期代码 '{semester_code}' 推算年级: {exam_grade_level}")
                except (ValueError, IndexError):
                    pass
            
            # 方法3: 兜底方案 - 使用当前年级
            if not exam_grade_level:
                exam_grade_level = current_grade_level
                print(f"无法确定考试 '{exam.exam_name}' 的年级，默认为当前年级: {current_grade_level}")
            
            # 构建考试信息对象
            exam_info = {
                'id': exam.exam_id,
                'name': exam.exam_name,
                'semester': semester_name,
                'date': semester_date.strftime('%Y-%m-%d') if semester_date else None
            }
            
            # 按年级分组存储考试
            if exam_grade_level not in exams_by_grade_level:
                exams_by_grade_level[exam_grade_level] = []
            
            exams_by_grade_level[exam_grade_level].append(exam_info)
        
        # 7. 构建最终的时间轴数据
        timeline = []
        
        # 只包含有考试数据的年级，按年级从低到高排序
        for grade_level in sorted(exams_by_grade_level.keys()):
            # 获取年级对应的学段信息
            if grade_level <= 6:
                grade_name = f"{grade_level}年级"  # 小学
            elif grade_level <= 9:
                grade_name = f"初{grade_level-6}"  # 初中
            else:
                grade_name = f"高{grade_level-9}"  # 高中
            
            # 添加到时间轴
            timeline.append({
                'grade_level': grade_level,
                'grade_name': grade_name,
                'exams': exams_by_grade_level[grade_level]
            })
        
        return JsonResponse(timeline, safe=False)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"获取年级时间轴考试数据出错: {e}")
        print(error_trace)
        return JsonResponse({"error": str(e), "trace": error_trace if settings.DEBUG else None}, status=500)

class GenerateExamFeaturesView(APIView):
    """
    考试特征生成API
    """
    def post(self, request):
        """
        生成考试的分层特征数据
        
        Args:
            exam_id: 考试ID
            regenerate: 是否重新生成已存在的特征
            
        Returns:
            Response: 包含处理状态的响应
        """
        exam_id = request.data.get('exam_id')
        regenerate = request.data.get('regenerate', True)
        
        if not exam_id:
            return Response({"error": "缺少必要参数: exam_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        # 检查考试是否存在
        try:
            exam = Exam.objects.get(exam_id=exam_id)
        except Exam.DoesNotExist:
            return Response({"error": f"考试 {exam_id} 不存在"}, status=status.HTTP_404_NOT_FOUND)
        
        # 检查是否已存在特征数据
        if not regenerate and DistrictExamFeature.objects.filter(exam=exam).exists():
            return Response({
                "exists": True,
                "message": "该考试已存在特征数据，设置regenerate=true可重新生成"
            })
        
        # 在后台线程中处理特征生成
        thread = Thread(target=self._generate_exam_features, args=(exam_id,))
        thread.setDaemon(True)
        thread.start()
        
        return Response({
            "status": "processing",
            "message": f"正在为考试 {exam_id} 生成分层特征数据"
        })
        
    def _generate_exam_features(self, exam_id):
        """在后台处理特征生成"""
        try:
            # 获取考试信息
            exam = Exam.objects.get(exam_id=exam_id)
            
            # 获取考试相关的所有分数记录
            scores = Score.objects.filter(exam=exam).select_related('student', 'subject')
            
            if not scores.exists():
                logger.error(f"考试 {exam_id} 没有关联的分数记录")
                return
            
            # 1. 生成区级特征
            district_feature = self._generate_district_feature(exam, scores)
            
            # 2. 生成学校特征
            school_features = self._generate_school_features(exam, scores, district_feature)
            
            # 3. 生成班级特征
            class_features = self._generate_class_features(exam, scores, school_features)
            
            # 4. 生成学生特征
            student_features = self._generate_student_features(exam, scores, district_feature, school_features, class_features)
            
            # 生成完成后立即验证
            final_count = StudentExamFeature.objects.filter(exam__exam_id=exam_id).count()
            print(f"特征生成完成后最终验证 - 学生特征数量: {final_count}")
            
            # 记录完成情况
            print(f"考试 {exam_id} 的分层特征生成完成")
            
        except Exception as e:
            print(f"生成考试特征时出错: {str(e)}")
            raise
    
    def _generate_district_feature(self, exam, scores):
        """
        生成区域特征（包括总分和各科目）
        
        Args:
            exam: 考试对象
            scores: 分数记录集合
            
        Returns:
            DistrictExamFeature: 区域总分特征对象
        """
        print(f"开始生成区域特征，考试ID: {exam.exam_id}")
        
        try:
            # 1. 获取所有科目列表
            subjects = list(set([score.subject_id for score in scores]))
            print(f"本次考试包含科目: {subjects}")
            
            # 2. 按科目分组统计成绩
            subject_stats = {}
            
            for subject_id in subjects:
                # 筛选该科目的分数记录
                subject_scores = [score for score in scores if score.subject_id == subject_id]
                
                if not subject_scores:
                    continue
                    
                # 计算统计指标
                raw_scores = [score.raw_score for score in subject_scores]
                standard_scores = [score.standard_score for score in subject_scores]
                student_count = len(set([score.student_id for score in subject_scores]))
                
                # 统计结果
                stats = {
                    'avg_score': sum(raw_scores) / len(raw_scores) if raw_scores else 0,
                    'avg_standard_score': sum(standard_scores) / len(standard_scores) if standard_scores else 0,
                    'std_dev': statistics.stdev(standard_scores) if len(standard_scores) > 1 else 0,
                    'max_score': max(raw_scores) if raw_scores else 0,
                    'min_score': min(raw_scores) if raw_scores else 0,
                    'student_count': student_count
                }
                
                subject_stats[subject_id] = stats
            
            # 3. 创建区域特征对象
            features_to_create = []
            district_feature = None
            
            for subject_id, stats in subject_stats.items():
                feature = DistrictExamFeature(
                    exam=exam,
                    subject_id=subject_id,
                    avg_score=stats['avg_score'],
                    avg_standard_score=stats['avg_standard_score'],
                    std_dev=stats['std_dev'],
                    max_score=stats['max_score'],
                    min_score=stats['min_score'],
                    total_students=stats['student_count']
                )
                
                features_to_create.append(feature)
                
                # 保存总分特征作为主返回值
                if subject_id == 'TOTAL':
                    district_feature = feature
            
            # 4. 批量保存
            with transaction.atomic():
                # 先删除已存在的记录
                DistrictExamFeature.objects.filter(exam=exam).delete()
                
                # 执行批量创建
                DistrictExamFeature.objects.bulk_create(features_to_create)
            
            print(f"成功保存{len(features_to_create)}个区域特征，包含{len(subject_stats)}个科目")
            
            # 确保有总分特征作为返回值
            if not district_feature:
                print(f"警告：未找到TOTAL总分特征记录")
                if features_to_create:
                    district_feature = features_to_create[0]
            
            return district_feature
            
        except Exception as e:
            print(f"生成区域特征时发生错误: {str(e)}")
            raise
    
    def _generate_school_features(self, exam, scores, district_feature):
        """
        生成学校特征（包括总分和各科目）
        
        Args:
            exam: 考试对象
            scores: 分数记录集合
            district_feature: 区域特征对象
            
        Returns:
            dict: 学校ID到特征对象的映射
        """
        print(f"开始生成学校特征，考试ID: {exam.exam_id}")
        
        # 获取考试对应的学期ID
        semester_id = exam.semester_id
        
        # 1. 查询学生历史记录，获取学校信息
        student_ids = list(set([score.student_id for score in scores]))
        
        student_histories = StudentHistory.objects.filter(
            student_id__in=student_ids,
            semester_id=semester_id
        ).select_related('school', 'grade')
        
        # 建立学生ID到学校ID和年级的映射
        student_schools = {}
        school_grades = {}  # 记录每个学校包含哪些年级
        
        for history in student_histories:
            if history.school_id:  # 确保有学校信息
                student_schools[history.student_id] = {
                    'school_id': history.school_id,
                    'grade_id': history.grade_id
                }
                
                # 记录学校包含的年级
                if history.school_id not in school_grades:
                    school_grades[history.school_id] = set()
                if history.grade_id:
                    school_grades[history.school_id].add(history.grade_id)
        
        print(f"找到{len(student_schools)}个学生的学校信息")
        
        # 2. 获取所有科目列表（包括TOTAL）
        subjects = list(set([score.subject_id for score in scores]))
        print(f"本次考试包含科目: {subjects}")
        
        # 3. 按学校和科目分组统计成绩
        school_subject_stats = {}  # 学校各科目统计
        school_total_stats = {}    # 学校总分统计（用于排名）
        
        for score in scores:
            student_id = score.student_id
            subject_id = score.subject_id
            
            # 跳过没有学校信息的学生
            if student_id not in student_schools:
                continue
                
            school_id = student_schools[student_id]['school_id']
            
            # 初始化学校统计
            if school_id not in school_subject_stats:
                school_subject_stats[school_id] = {}
            
            # 初始化科目统计
            if subject_id not in school_subject_stats[school_id]:
                school_subject_stats[school_id][subject_id] = {
                    'total_score': 0,
                    'total_standard_score': 0,
                    'student_count': 0,
                    'score_list': []
                }
                
            # 累加分数
            stats = school_subject_stats[school_id][subject_id]
            stats['total_score'] += score.raw_score
            stats['total_standard_score'] += score.standard_score
            stats['student_count'] += 1
            stats['score_list'].append(score.standard_score)
            
            # 如果是总分，用于学校排名
            if subject_id == 'TOTAL':
                school_total_stats[school_id] = {
                    'avg_standard_score': stats['total_standard_score'] / stats['student_count'],
                    'grade_count': len(school_grades.get(school_id, set()))
                }
        
        # 4. 计算各科目平均分和标准差
        for school_id, subjects in school_subject_stats.items():
            for subject_id, stats in subjects.items():
                if stats['student_count'] > 0:
                    stats['avg_score'] = stats['total_score'] / stats['student_count']
                    stats['avg_standard_score'] = stats['total_standard_score'] / stats['student_count']
                    
                    # 计算标准差
                    if len(stats['score_list']) > 1:
                        stats['stddev'] = statistics.stdev(stats['score_list'])
                    else:
                        stats['stddev'] = 0
        
        # 5. 计算学校总分排名
        all_schools = [(school_id, stats['avg_standard_score']) 
                       for school_id, stats in school_total_stats.items()]
        
        # 按平均分排序
        all_schools.sort(key=lambda x: x[1], reverse=True)
        
        # 计算排名和百分位
        total_schools = len(all_schools)
        school_ranks = {}
        
        for rank, (school_id, _) in enumerate(all_schools, 1):
            # 百分位计算
            percentile = 100 * (total_schools - rank) / total_schools if total_schools > 1 else 50
            school_ranks[school_id] = {
                'rank': rank,
                'percentile': percentile
            }
        
        # 6. 创建学校特征对象
        school_features = {}
        features_to_create = []
        
        for school_id, subjects in school_subject_stats.items():
            # 只有同时有总分和排名的学校才创建特征
            if 'TOTAL' not in subjects or school_id not in school_ranks:
                continue
                
            total_stats = subjects['TOTAL']
            rank_info = school_ranks[school_id]
            
            # 创建学校总分特征
            school_feature = SchoolExamFeature(
                exam=exam,
                district_feature=district_feature,
                school_id=school_id,
                subject_id='TOTAL',
                avg_score=total_stats['avg_score'],
                avg_standard_score=total_stats['avg_standard_score'],
                std_dev=total_stats['stddev'],
                rank=rank_info['rank'],
                percentile=rank_info['percentile'],
                student_count=total_stats['student_count'],
                grade_count=school_total_stats[school_id]['grade_count']
            )
            
            features_to_create.append(school_feature)
            school_features[school_id] = school_feature
            
            # 创建各科目特征
            for subject_id, stats in subjects.items():
                if subject_id == 'TOTAL':  # 跳过总分，已创建
                    continue
                    
                subject_feature = SchoolExamFeature(
                    exam=exam,
                    district_feature=district_feature,
                    school_id=school_id,
                    subject_id=subject_id,
                    avg_score=stats['avg_score'],
                    avg_standard_score=stats['avg_standard_score'],
                    std_dev=stats['stddev'],
                    rank=0,  # 科目不计算排名
                    percentile=0,
                    student_count=stats['student_count']
                )
                
                features_to_create.append(subject_feature)
        
        # 7. 批量保存
        try:
            with transaction.atomic():
                # 先删除已存在的记录
                SchoolExamFeature.objects.filter(exam=exam).delete()
                
                # 执行批量创建
                SchoolExamFeature.objects.bulk_create(features_to_create)
            
            print(f"成功保存{len(features_to_create)}个学校特征，包含{len(school_features)}所学校")
        except Exception as e:
            print(f"保存学校特征时出错: {e}")
        
        return school_features
    
    def _generate_class_features(self, exam, scores, school_features):
        """生成班级特征（含各科目）"""
        print(f"开始生成班级特征，考试ID: {exam.exam_id}")
        
        # 获取考试学期
        semester_id = exam.semester_id
        print(f"考试学期ID: {semester_id}")
        
        # 获取所有科目
        subjects = list(set([score.subject_id for score in scores]))
        print(f"本次考试包含科目: {subjects}")
        
        # 1. 先通过StudentHistory表获取该学期每个学生的班级和学校信息
        student_ids = list(set([score.student_id for score in scores]))
        
        # 批量查询学生历史记录
        student_histories = StudentHistory.objects.filter(
            student_id__in=student_ids,
            semester_id=semester_id
        ).select_related('class_field', 'school', 'grade')
        
        # 建立学生ID到班级ID和年级的映射
        student_to_class = {}
        for history in student_histories:
            if history.class_field_id:  # 确保有班级信息
                student_to_class[history.student_id] = {
                    'class_id': history.class_field_id,
                    'school_id': history.school_id,
                    'grade_id': history.grade_id
                }
        
        print(f"找到{len(student_to_class)}个学生的班级信息")
        
        # 2. 按科目处理数据
        all_features = []  # 存储所有特征对象
        
        # 记录班级所属学校和年级
        class_schools = {}
        class_grades = {}
        
        # 首先按班级、年级分类所有学生
        for student_id, info in student_to_class.items():
            class_id = info['class_id']
            school_id = info['school_id']
            grade_id = info['grade_id']
            
            # 记录班级所属学校和年级
            class_schools[class_id] = school_id
            class_grades[class_id] = grade_id
        
        # 为每个科目生成特征
        for subject_id in subjects:
            print(f"处理 {subject_id} 科目的班级特征...")
            
            # 按班级分组统计成绩
            class_stats = {}
            
            # 使用指定科目分数计算班级平均分
            for score in scores:
                if score.subject_id == subject_id:
                    student_id = score.student_id
                    
                    # 跳过没有班级信息的学生
                    if student_id not in student_to_class:
                        continue
                    
                    # 获取班级信息
                    class_info = student_to_class[student_id]
                    class_id = class_info['class_id']
                    
                    # 统计班级成绩
                    if class_id not in class_stats:
                        class_stats[class_id] = {
                            'total_score': 0,
                            'total_standard_score': 0,
                            'student_count': 0,
                            'score_list': []
                        }
                        
                    # 统计分数
                    class_stats[class_id]['total_score'] += score.raw_score
                    class_stats[class_id]['total_standard_score'] += score.standard_score
                    class_stats[class_id]['student_count'] += 1
                    class_stats[class_id]['score_list'].append(score.standard_score)
            
            # 计算每个班级的平均分和标准差
            for class_id, stats in class_stats.items():
                if stats['student_count'] > 0:
                    stats['avg_score'] = stats['total_score'] / stats['student_count']
                    stats['avg_standard_score'] = stats['total_standard_score'] / stats['student_count']
                    
                    # 计算标准差
                    if len(stats['score_list']) > 1:
                        stats['stddev'] = statistics.stdev(stats['score_list'])
                    else:
                        stats['stddev'] = 0
            
            # 3. 筛选学生人数少于阈值的班级
            MIN_STUDENTS = 10  # 最小学生人数阈值
            filtered_class_ids = []
            filtered_out_classes = 0
            
            for class_id, stats in class_stats.items():
                if stats['student_count'] < MIN_STUDENTS:
                    filtered_out_classes += 1
                    filtered_class_ids.append(class_id)
            
            # 打印筛选信息
            if filtered_out_classes > 0:
                print(f"{subject_id} 科目过滤掉{filtered_out_classes}个人数少于{MIN_STUDENTS}人的班级")
            
            # 4. 按年级分组进行排名
            grade_class_features = {}
            
            # 获取所有涉及到的年级
            grades = set(class_grades.values())
            
            for grade in grades:
                # 获取该年级的所有班级（排除已过滤的）
                grade_classes = [cid for cid, gid in class_grades.items() 
                                if gid == grade and cid not in filtered_class_ids and cid in class_stats]
                
                # 该年级的班级平均分列表
                grade_class_scores = [(cid, class_stats[cid]['avg_standard_score']) 
                                     for cid in grade_classes if cid in class_stats]
                
                # 按平均分排序
                grade_class_scores.sort(key=lambda x: x[1], reverse=True)
                
                # 计算每个班级的排名和百分位
                total_classes = len(grade_class_scores)
                for rank, (class_id, _) in enumerate(grade_class_scores, 1):
                    # 百分位计算
                    percentile = 100 * (total_classes - rank) / total_classes if total_classes > 1 else 50
                    
                    # 检查是否有对应的学校特征
                    school_id = class_schools.get(class_id)
                    
                    # 创建班级特征对象
                    class_feature = ClassExamFeature(
                        exam=exam,
                        school_feature=school_features[school_id],  
                        class_obj_id=class_id,                     
                        subject_id=subject_id,                   
                        avg_score=class_stats[class_id]['avg_score'],
                        std_dev=class_stats[class_id]['stddev'],
                        school_rank=rank,                
                        school_percentile=percentile,    
                        student_count=class_stats[class_id]['student_count'],
                        avg_standard_score=class_stats[class_id]['avg_standard_score']
                    )
                    
                    # 添加到列表
                    all_features.append(class_feature)
                    
                    # 添加到年级的班级特征列表（用于统计）
                    if grade not in grade_class_features:
                        grade_class_features[grade] = []
                    grade_class_features[grade].append(class_feature)
            
            # 打印每个年级的特征数量
            for grade, features in grade_class_features.items():
                print(f"{subject_id}科目 - {grade}年级生成了{len(features)}个班级特征")
        
        # 5. 批量保存所有班级特征
        try:
            # 先删除之前的记录
            ClassExamFeature.objects.filter(exam=exam).delete()
            
            # 执行批量创建
            ClassExamFeature.objects.bulk_create(all_features)
            print(f"成功保存{len(all_features)}个班级特征，包含{len(subjects)}个科目")
        except Exception as e:
            print(f"保存班级特征时出错: {e}")
        
        # 创建特征字典用于返回 (使用composite key以支持多科目)
        class_features_dict = {}
        for feature in all_features:
            class_id = feature.class_obj_id
            if class_id not in class_features_dict:
                class_features_dict[class_id] = feature  # 默认使用第一个特征，通常是TOTAL
        
        return class_features_dict
    
    def _generate_student_features(self, exam, scores, district_feature, school_features, class_features):
        """
        生成学生考试特征
        
        Args:
            exam: 考试对象  
            scores: 分数记录集合
            district_feature: 区域特征
            school_features: 学校特征字典
            class_features: 班级特征字典
            
        Returns:
            dict: 学生特征字典
        """
        # 获取考试对应的学期ID
        semester_id = exam.semester_id
        print(f"开始生成学生特征，考试ID: {exam.exam_id}, 学期ID: {semester_id}")
        
        # 1. 从分数记录中获取参加本次考试的学生ID列表
        total_subject_scores = [score for score in scores if score.subject_id == 'TOTAL']
        student_ids = [score.student_id for score in total_subject_scores]
        
        print(f"找到{len(student_ids)}个参加考试的学生记录")
        
        if not student_ids:
            print("没有找到学生总分记录，无法生成特征")
            return {}
        
        # 2. 查询这些学生在当前学期的历史记录
        student_histories = StudentHistory.objects.filter(
            student_id__in=student_ids,
            semester_id=semester_id
        ).select_related('class_field', 'school', 'grade')
        
        # 建立学生ID到班级、学校和年级的映射
        student_info = {}
        for history in student_histories:
            student_info[history.student_id] = {
                'class_id': history.class_field_id,
                'school_id': history.school_id,
                'grade_id': history.grade_id
            }
        
        print(f"找到{len(student_info)}个学生的历史记录信息，占比{len(student_info)/len(student_ids)*100:.2f}%")
        
        # 3. 预处理学生成绩
        total_scores = {}
        student_subjects = {}
        
        # 处理总分记录
        for score in total_subject_scores:
            student_id = score.student_id
            total_scores[student_id] = {
                'total_score': score.standard_score
                # 移除 raw_score 字段，它现在不被使用
            }
        
        # 处理学科分数
        for score in scores:
            if score.subject_id != 'TOTAL':
                student_id = score.student_id
                if student_id not in student_subjects:
                    student_subjects[student_id] = []
                
                student_subjects[student_id].append({
                    'subject_id': score.subject_id,
                    'score': score.standard_score
                })
        
        # 4. 按年级分组学生
        students_by_grade = {}
        
        for student_id in total_scores.keys():
            # 跳过没有历史记录的学生
            if student_id not in student_info:
                continue
            
            grade_id = student_info[student_id]['grade_id']
            if not grade_id:
                continue
            
            if grade_id not in students_by_grade:
                students_by_grade[grade_id] = []
            
            students_by_grade[grade_id].append(student_id)
        
        print(f"按年级分组学生数据，共{len(students_by_grade)}个年级")
        
        # 5. 筛选年级 - 移除人数过少的年级
        MIN_GRADE_STUDENTS = 20  # 年级最低学生数阈值
        filtered_grades = []
        
        for grade_id, grade_students in list(students_by_grade.items()):
            if len(grade_students) < MIN_GRADE_STUDENTS:
                print(f"⚠️ 年级 {grade_id} 仅有 {len(grade_students)} 名学生，低于阈值 {MIN_GRADE_STUDENTS}，将被排除")
                filtered_grades.append(grade_id)
                del students_by_grade[grade_id]
        
        if filtered_grades:
            print(f"共过滤掉 {len(filtered_grades)} 个人数不足的年级: {filtered_grades}")
        
        # 6. 在每个年级内计算排名
        grade_rankings = {}
        
        for grade_id, grade_students in students_by_grade.items():
            print(f"处理{grade_id}年级的排名，共{len(grade_students)}个学生")
            
            # 年级内排名
            grade_scores = [(sid, total_scores[sid]['total_score']) 
                            for sid in grade_students if sid in total_scores]
            grade_scores.sort(key=lambda x: x[1], reverse=True)
            district_ranks = {sid: rank for rank, (sid, _) in enumerate(grade_scores, 1)}
            
            # 按学校分组
            school_students = {}
            for student_id in grade_students:
                if student_id not in student_info:
                    continue
                
                school_id = student_info[student_id]['school_id']
                if not school_id:
                    continue
                
                if school_id not in school_students:
                    school_students[school_id] = []
                
                school_students[school_id].append(student_id)
            
            # 学校内排名
            school_ranks = {}
            for school_id, students in school_students.items():
                school_scores = [(sid, total_scores[sid]['total_score']) 
                                for sid in students if sid in total_scores]
                school_scores.sort(key=lambda x: x[1], reverse=True)
                
                for rank, (sid, _) in enumerate(school_scores, 1):
                    school_ranks[sid] = rank
            
            # 按班级分组
            class_students = {}
            for student_id in grade_students:
                if student_id not in student_info:
                    continue
                
                class_id = student_info[student_id]['class_id']
                if not class_id:
                    continue
                
                if class_id not in class_students:
                    class_students[class_id] = []
                
                class_students[class_id].append(student_id)
            
            # 班级内排名
            class_ranks = {}
            for class_id, students in class_students.items():
                class_scores = [(sid, total_scores[sid]['total_score']) 
                               for sid in students if sid in total_scores]
                class_scores.sort(key=lambda x: x[1], reverse=True)
                
                for rank, (sid, _) in enumerate(class_scores, 1):
                    class_ranks[sid] = rank
            
            # 保存该年级的排名结果
            grade_rankings[grade_id] = {
                'district': district_ranks,
                'school': school_ranks,
                'class': class_ranks
            }
        
        # 7. 生成学生特征
        missing_school = 0
        missing_class = 0
        missing_features = 0
        student_features = []
        
        for student_id, score_data in total_scores.items():
            # 跳过没有历史记录的学生
            if student_id not in student_info:
                print(f"警告：学生 {student_id} 在考试 {exam.exam_id} 中有成绩，但在{semester_id}学期没有历史记录")
                continue
            
            info = student_info[student_id]
            school_id = info['school_id']
            class_id = info['class_id']
            grade_id = info['grade_id']
            
            if not school_id:
                missing_school += 1
                continue
            
            if not class_id:
                missing_class += 1
                continue
            
            # 获取关联特征
            school_feature = school_features.get(school_id)
            class_feature = class_features.get(class_id)
            
            if not (school_feature and class_feature):
                missing_features += 1
                continue
            
            # 确定最优和最弱学科
            subject_records = student_subjects.get(student_id, [])
            best_subject_id = None
            best_subject_score = 0
            weakest_subject_id = None
            weakest_subject_score = float('inf')
            
            if subject_records:
                for subject in subject_records:
                    if subject['score'] > best_subject_score:
                        best_subject_score = subject['score']
                        best_subject_id = subject['subject_id']
                    
                    if subject['score'] < weakest_subject_score:
                        weakest_subject_score = subject['score']
                        weakest_subject_id = subject['subject_id']
            
            # 获取排名
            rank_info = grade_rankings.get(grade_id, {'district': {}, 'school': {}, 'class': {}})
            district_rank = rank_info['district'].get(student_id, 0)
            school_rank = rank_info['school'].get(student_id, 0)
            class_rank = rank_info['class'].get(student_id, 0)
            
            # 创建学生特征 (移除raw_score参数)
            student_feature = StudentExamFeature(
                exam=exam,
                student_id=student_id,
                district_feature=district_feature,
                school_feature=school_feature,
                class_feature=class_feature,
                total_score=score_data['total_score'],
                # raw_score 参数已移除
                class_rank=class_rank,
                school_rank=school_rank,
                district_rank=district_rank,
                best_subject_id=best_subject_id,
                best_subject_score=best_subject_score,
                weakest_subject_id=weakest_subject_id,
                weakest_subject_score=weakest_subject_score
            )
            
            student_features.append(student_feature)
        
        # 记录诊断信息
        print(f"学生特征生成统计: 总分记录数 {len(total_scores)}, 历史记录数 {len(student_info)}, 缺学校ID {missing_school}, 缺班级ID {missing_class}, 缺关联特征 {missing_features}")
        
        # 批量保存
        student_features_dict = {}
        if student_features:
            try:
                with transaction.atomic():
                    # 先删除已存在的记录
                    StudentExamFeature.objects.filter(exam=exam).delete()
                    
                    # 执行批量创建
                    StudentExamFeature.objects.bulk_create(student_features, batch_size=500)
                    
                    # 事务内验证
                    actual_count = StudentExamFeature.objects.filter(exam=exam).count()
                    print(f"事务内验证: 数据库中学生特征数量: {actual_count}")
                
                # 验证并创建特征字典
                path_count = StudentExamFeature.objects.filter(exam__exam_id=exam.exam_id).count()
                print(f"最终验证: 数据库中学生特征数量: {path_count}")
                
                student_features_dict = {f.student_id: f for f in student_features}
                
            except Exception as e:
                print(f"批量创建学生特征失败: {e}")
        else:
            print("没有学生特征记录可创建")
        
        return student_features_dict

@api_view(['GET'])
def exam_feature_status(request, exam_id):
    """获取考试特征计算状态"""
    try:
        print(f"检查考试 {exam_id} 的特征状态")
        
        # 检查是否存在区级特征
        district_exists = DistrictExamFeature.objects.filter(exam__exam_id=exam_id).exists()
        
        # 如果存在区级特征，继续检查其他层级
        if district_exists:
            school_count = SchoolExamFeature.objects.filter(exam__exam_id=exam_id).count()
            class_count = ClassExamFeature.objects.filter(exam__exam_id=exam_id).count()
            student_count = StudentExamFeature.objects.filter(exam__exam_id=exam_id).count()
            
            print(f"学校特征数量: {school_count}")
            print(f"班级特征数量: {class_count}")
            print(f"学生特征数量: {student_count}")
            
            # 修改：只有当学生特征也存在时，才认为完成
            if student_count > 0:
                return JsonResponse({
                    'status': 'completed',
                    'data': {
                        'district_feature': district_exists,
                        'school_features': school_count,
                        'class_features': class_count,
                        'student_features': student_count
                    }
                })
            else:
                # 如果学生特征尚未生成，返回处理中状态
                return JsonResponse({
                    'status': 'processing',
                    'data': {
                        'district_feature': district_exists,
                        'school_features': school_count,
                        'class_features': class_count,
                        'student_features': 0,
                        'message': '学生特征正在生成中...'
                    }
                })
        else:
            print(f"未找到区级特征，返回not_found状态")
            return JsonResponse({
                'status': 'not_found'
            })
            
    except Exception as e:
        print(f"获取特征状态时出错: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)