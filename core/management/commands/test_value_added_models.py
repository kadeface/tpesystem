#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试多种增值分析模型的Django命令

用法示例:
    # 基本用法
    python manage.py test_value_added_models --exams 1001 1002 --subject 2 --model tvam
    
    # 使用贝叶斯模型并控制变量
    python manage.py test_value_added_models --exams 1001 1002 --subject 2 --model bayesian --control gender ses
    
    # 测试多个模型并比较结果
    python manage.py test_value_added_models --exams 1001 1002 --subject 2 --model tvam fixed bayesian
    
    # 使用时间序列贝叶斯模型(基于考试ID指定基线)
    python manage.py test_value_added_models --exams 1001 1002 1003 1004 1005 --subject 2 --model timeseries --baseline-exams 1001 1002 1003 1004 --target-exam 1005

    # 使用学生聚类模型
    python manage.py test_value_added_models --exams 2025-DIST-M-202301 2025-DIST-M-202307 2025-DIST-M-202401 2025-DIST-M-202407 2025-DIST-M-202501 --subject MATH --model student_cluster --clusters 12 --min-exams 5 --visualize-clusters
    
"""

import os
import time
import logging
import pandas as pd
import numpy as np
import json
from django.core.management.base import BaseCommand
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans  
from sklearn.preprocessing import StandardScaler
#from core.management.commands.education_data_provider import EducationDataProvider
from core.value_added_models import (
    TVAMValueAddedModel,
    BayesianValueAddedModel,
    FrequentistValueAddedModel,
    FixedEffectsValueAddedModel,
    RandomEffectsValueAddedModel,
    ValueAddedDataProcessor,
    ValueAddedVisualizer,
    NonlinearStudentPotentialEvaluator,
    TimeSeriesBayesianValueAddedModel,
    StudentProgressClusterAnalyzer
)

logger = logging.getLogger(__name__)

# 可用模型映射
MODEL_MAPPING = {
    'tvam': TVAMValueAddedModel,
    'bayesian': BayesianValueAddedModel,
    'frequentist': FrequentistValueAddedModel,
    'fixed': FixedEffectsValueAddedModel,
    'random': RandomEffectsValueAddedModel,
    'nonlinear_potential': 'special_handler',
    'timeseries': TimeSeriesBayesianValueAddedModel,
    'student_cluster': StudentProgressClusterAnalyzer
}

class Command(BaseCommand):
    """测试增值分析模型的Django命令"""
    
    help = '使用不同模型进行增值分析或学生潜力评估并比较结果'
    
    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument('--exams', nargs='+', type=str, required=True, help='考试ID列表')
        parser.add_argument('--subject', type=str, required=True, help='学科ID')
        parser.add_argument('--model', nargs='+', default=['tvam'], help='要测试的模型，可选: tvam, bayesian, frequentist, fixed, random, nonlinear_potential, timeseries')
        parser.add_argument('--control', nargs='+', default=[], help='控制变量列表')
        parser.add_argument('--entity', choices=['school', 'class'], default='class', 
                           help='分析实体类型')
        parser.add_argument('--output', default='results/value_added/', help='输出目录')
        parser.add_argument('--sample', type=int, default=0, help='样本量(0=全部)')
        parser.add_argument('--verbose', action='store_true', help='显示详细日志')
        parser.add_argument('--cohort', action='store_true', 
                           help='使用学生队列进行跨年级增值分析')
        parser.add_argument('--baseline', type=str, help='指定基准考试ID')
        parser.add_argument('--student-id', type=str, help='用于潜力评估的特定学生ID')
        
        # 添加贝叶斯模型特有参数
        parser.add_argument('--mcmc-samples', type=int, default=1000, 
                           help='贝叶斯MCMC采样次数')
        parser.add_argument('--tune', type=int, default=500, 
                           help='贝叶斯MCMC调整步数')
        parser.add_argument('--random-seed', type=int, default=42, 
                           help='随机数种子，用于重现结果')
        
        # 添加时间序列贝叶斯模型参数
        parser.add_argument('--baseline-count', type=int, default=4, 
                           help='[已弃用] 时间序列模型的基线考试次数')
        parser.add_argument('--decay-factor', type=float, default=0.85, 
                           help='时间序列模型的时间衰减因子(0-1)')
        # 新增参数：通过考试ID指定基线
        parser.add_argument('--baseline-exams', nargs='+', type=str,
                           help='时间序列模型的基线考试ID列表')
        parser.add_argument('--target-exam', type=str,
                           help='时间序列模型的目标考试ID')
        
        # 添加聚类模型特有参数
        parser.add_argument('--clusters', type=int, default=4, 
                           help='聚类分析的分群数量，默认为4')
        parser.add_argument('--min-exams', type=int, default=3, 
                           help='聚类分析所需的最少考试次数，默认为3')
        parser.add_argument('--visualize-clusters', action='store_true',
                           help='是否生成聚类可视化图表')
        parser.add_argument('--find-optimal-clusters', action='store_true',
                           help='自动寻找最优聚类数量')
        parser.add_argument('--max-clusters', type=int, default=12,
                           help='寻找最优聚类时考虑的最大聚类数')
        parser.add_argument('--min-clusters', type=int, default=4,
                           help='最小聚类数量，即使轮廓系数较低')
        parser.add_argument('--task-id', type=str, help='关联的分析任务ID')
    
    def handle(self, *args, **options):
        """命令处理入口"""
        task_id = options.get('task_id')
        
        try:
            # 配置matplotlib，抑制不必要的输出
            import matplotlib as mpl
            mpl.set_loglevel('WARNING')  # 正确的方法
            
            # 禁用字体缓存更新
            mpl.rcParams['font.family'] = 'sans-serif'
            
            # 设置后端，避免可能的warning
            mpl.use('Agg')  # 使用非交互式后端
            
            # 其他更严格的日志抑制
            import logging
            logging.getLogger('matplotlib').setLevel(logging.WARNING)
            logging.getLogger('PIL').setLevel(logging.WARNING)
            
            # 初始化任务
            self.update_task_progress(task_id, 5, status='running')
            
            start_time = time.time()
            
            # 配置日志级别
            log_level = logging.DEBUG if options['verbose'] else logging.INFO
            logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
            
            # 打印参数
            self.stdout.write(self.style.SUCCESS("开始测试增值分析模型"))
            self.stdout.write(f"- 考试ID: {options['exams']}")
            self.stdout.write(f"- 学科ID: {options['subject']}")
            self.stdout.write(f"- 模型: {options['model']}")
            self.stdout.write(f"- 控制变量: {options['control']}")
            
            # 1. 仅获取原始数据，不做处理
            self.stdout.write(self.style.SUCCESS("1. 获取原始数据"))
            # 更新进度 - 10%
            self.update_task_progress(task_id, 10)
            
            processor = ValueAddedDataProcessor()
            processor.load_data(exam_ids=options['exams'], subject_id=options['subject'], 
                               baseline_exam=options.get('baseline'))
            
            # 显示基准考试信息
            if hasattr(processor, 'baseline_exams'):
                self.stdout.write(self.style.SUCCESS(f"- 基准考试: {', '.join(processor.baseline_exams)}"))
            
            self.stdout.write(f"- 获取了{len(processor.data)}条原始数据")
            
            # 更新进度 - 20%
            self.update_task_progress(task_id, 20)
            
            # 2. 创建输出目录
            output_dir = options['output']
            os.makedirs(output_dir, exist_ok=True)
            
            # 存储各模型结果
            results = {}
            
            # 3. 测试每个指定的模型
            self.stdout.write(self.style.SUCCESS("2. 执行模型分析"))
            
            # 更新进度 - 30%
            self.update_task_progress(task_id, 30)
            
            for model_name in options['model']:
                self.stdout.write(f"- 使用{model_name}模型进行分析")
                
                try:
                    # 特殊处理模型的专门函数
                    if model_name == 'nonlinear_potential':
                        # 非线性潜力评估模型
                        self._handle_timeseries_model(processor, options, output_dir)
                    elif model_name == 'tvam':
                        self._handle_tvam_model(processor, options, output_dir)
                    elif model_name == 'student_cluster':
                        # 学生聚类分析
                        self._handle_student_cluster_analyzer(processor, options, output_dir)
                    elif model_name == 'timeseries':
                        # 时间序列贝叶斯模型
                        self._handle_timeseries_model(processor, options, output_dir)
                    else:
                        # 通用增值模型处理
                        self._test_value_added_model(model_name, processor, options, output_dir)
                        
                    # 更新模型处理进度 
                    # (用处理的模型数量更新进度，从30%到70%)
                    models_count = len(options['model'])
                    model_idx = options['model'].index(model_name) + 1
                    progress = 30 + int(40 * model_idx / models_count)
                    self.update_task_progress(task_id, progress)
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"模型 {model_name} 分析失败: {str(e)}"))
                    # 继续执行其他模型
            
            # 4. 如果有多个模型且包含学生聚类，进行模型比较
            if len(options['model']) > 1 and 'student_cluster' in options['model']:
                self.stdout.write(self.style.SUCCESS("3. 比较不同模型"))
                # 模型比较代码...
                
            # 更新进度 - 90%
            self.update_task_progress(task_id, 90)
            
            # 5. 记录执行时间
            end_time = time.time()
            execution_time = end_time - start_time
            self.stdout.write(self.style.SUCCESS(f"分析完成，耗时: {execution_time:.2f}秒"))
            
            # 6. 如果有任务ID，将输出目录记录到任务中
            if task_id:
                try:
                    try:
                        from django.apps import apps
                        AnalysisTask = apps.get_model('edu_insights', 'AnalysisTask')
                        task = AnalysisTask.objects.get(task_id=task_id)
                        task.results_dir = output_dir
                        task.save()
                    except (ImportError, ModuleNotFoundError):
                        self.stdout.write(f"analysis模块不存在，无法更新任务结果路径")
                except Exception as e:
                    self.stderr.write(f"更新任务结果目录失败: {str(e)}")
                    
            # 更新进度 - 100% 完成
            self.update_task_progress(task_id, 100, status='completed')
            
        except Exception as e:
            # 更新进度 - 失败
            self.update_task_progress(task_id, 0, status='failed', error=str(e))
            
            self.stdout.write(self.style.ERROR(f"发生错误: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            raise

    def _handle_nonlinear_potential(self, processor, options, output_dir):
        """处理非线性潜力评估模型"""
        try:
            start_time = time.time()
            
            # 添加数据字段检查
            self.stdout.write(f"- 原始数据字段: {', '.join(processor.data.columns)}")
            
            # 直接创建非线性学习潜力评估器
            self.stdout.write("- 初始化NonlinearStudentPotentialEvaluator...")
            evaluator = NonlinearStudentPotentialEvaluator(
                data=processor.data,
                data_processor=processor,
                baseline_exam=options.get('baseline')
            )
            
            try:
                # 使用模型自己的prepare_data方法
                self.stdout.write("- 准备模型数据...")
                prepared_data = evaluator.prepare_data()
                self.stdout.write(f"- 找到{prepared_data['student_id'].nunique()}名有足够考试记录的学生用于潜力评估")
                logger.info(f"找到{prepared_data['student_id'].nunique()}名有足够考试记录的学生")
                
                # 添加处理后的字段检查
                self.stdout.write(f"- 处理后的数据字段: {', '.join(prepared_data.columns)}")
            except ValueError as e:
                self.stdout.write(self.style.ERROR(f"- 数据准备失败: {str(e)}"))
                return
            
            # 评估潜力
            potential_scores = evaluator.evaluate_potential()
            self.stdout.write(f"- 完成{len(potential_scores)}名学生的潜力评估")
            
            # 分析成长模式
            growth_patterns = evaluator.analyze_growth_patterns()
            self.stdout.write(f"- 识别了{len(growth_patterns)}种不同的学习成长模式")
            
            # 处理输出
            nonlinear_output_dir = os.path.join(output_dir, 'nonlinear_potential')
            os.makedirs(nonlinear_output_dir, exist_ok=True)
            
            # 保存结果
            potential_scores.to_csv(os.path.join(nonlinear_output_dir, 'potential_scores.csv'), index=False)
            growth_patterns.to_csv(os.path.join(nonlinear_output_dir, 'growth_patterns.csv'), index=False)
            
            self.stdout.write(f"- 结果已保存至 {nonlinear_output_dir}")
            
            # 创建可视化器
            visualizer = ValueAddedVisualizer()
            
            # 如果指定了学生ID，使用可视化器生成HTML报告
            if options.get('student_id'):
                student_id = options['student_id']
                
                # 尝试生成HTML报告
                try:
                    html_report = visualizer.generate_student_potential_report(
                        evaluator, 
                        student_id, 
                        nonlinear_output_dir, 
                        include_plots=True
                    )
                    
                    if html_report.startswith("<h2>错误</h2>"):
                        self.stdout.write(self.style.ERROR(f"- 无法生成学生 {student_id} 的报告，可能是数据不存在"))
                    else:
                        report_path = os.path.join(nonlinear_output_dir, f"{student_id}_potential_report.html")
                        self.stdout.write(self.style.SUCCESS(f"- 已生成学生 {student_id} 的潜力评估HTML报告: {report_path}"))
                        
                        # 简要显示学生信息
                        student_report = evaluator.get_student_report(student_id)
                        if 'error' not in student_report:
                            self.stdout.write(f"- 学生 {student_id} 基本信息:")
                            for key in ['name', 'school', 'class', 'grade', 'potential_rating', 'growth_pattern', 'learning_phase']:
                                if key in student_report:
                                    self.stdout.write(f"  * {key}: {student_report[key]}")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"- 生成HTML报告失败: {str(e)}"))
                    logger.exception("生成HTML报告时出错")
                    
                    # 回退到简单文本报告
                    student_report = evaluator.get_student_report(student_id)
                    if 'error' in student_report:
                        self.stdout.write(self.style.ERROR(f"- {student_report['error']}"))
                    else:
                        self.stdout.write(self.style.SUCCESS(f"- 学生 {student_id} 潜力评估报告:"))
                        for key, value in student_report.items():
                            if key not in ['scores_history', 'velocity_history', 'phase_recommendations']:
                                self.stdout.write(f"  * {key}: {value}")
                                
                        self.stdout.write("  * 学习阶段建议:")
                        for rec in student_report['phase_recommendations']:
                            self.stdout.write(f"    - {rec}")
            
            fit_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"- 非线性潜力评估完成，用时: {fit_time:.2f}秒"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"- 非线性潜力评估失败: {str(e)}"))
            logger.exception("非线性潜力评估出错")

    def _handle_tvam_model(self, processor, options, output_dir):
        """
        处理传统增值模型(TVAM)分析
        
        执行TVAM模型的构建、拟合和评估，生成各种报告和可视化
        
        Args:
            processor: 数据处理器实例
            options: 命令行选项
            output_dir: 输出目录
        """
        try:
            start_time = time.time()
            
            # 创建TVAM模型实例
            tvam_model = TVAMValueAddedModel(
                data=processor.data,
                data_processor=processor,
                entity_type=options['entity'],
                covariates=options['control'],
                use_cohort=options['cohort'],
                baseline_exam=options.get('baseline')
            )
            
            # 准备数据
            try:
                prepared_data = tvam_model.prepare_data()
                self.stdout.write(f"- 为TVAM模型准备了{len(prepared_data)}条建模数据")
                
                # 显示数据统计信息
                n_schools = prepared_data['school_id'].nunique() if 'school_id' in prepared_data.columns else 0
                n_classes = prepared_data['class_id'].nunique() if 'class_id' in prepared_data.columns else 0
                n_students = prepared_data['student_id'].nunique() if 'student_id' in prepared_data.columns else 0
                
                self.stdout.write(f"  * 包含 {n_schools} 所学校, {n_classes} 个班级, {n_students} 名学生")
            except ValueError as e:
                self.stdout.write(self.style.ERROR(f"- TVAM数据准备失败: {str(e)}"))
                return
            
            # 拟合模型
            tvam_model.fit()
            self.stdout.write("- TVAM模型拟合完成")
            
            # 获取效果估计
            entity_type = options['entity']
            effect_estimates = tvam_model.get_effect_estimates()
            self.stdout.write(f"- 获取了 {len(effect_estimates)} 个{entity_type}的增值效果估计")
            
            # 获取模型评估指标
            metrics = tvam_model.evaluate_model()
            self.stdout.write("- 模型评估指标:")
            for metric, value in metrics.items():
                self.stdout.write(f"  * {metric}: {value:.4f}")
            
            # 处理输出
            tvam_output_dir = os.path.join(output_dir, 'tvam')
            os.makedirs(tvam_output_dir, exist_ok=True)
            
            # 保存效果估计结果
            effect_estimates.to_csv(os.path.join(tvam_output_dir, f'{entity_type}_effects.csv'), index=False)
            
            # 保存学生级预测和残差
            student_results = tvam_model.get_student_results()
            if student_results is not None:
                student_results.to_csv(os.path.join(tvam_output_dir, 'student_results.csv'), index=False)
                self.stdout.write(f"- 保存了 {len(student_results)} 名学生的预测结果")
            
            # 创建可视化
            try:
                visualizer = ValueAddedVisualizer()
                
                # 生成增值效果排名图
                rank_plot_path = os.path.join(tvam_output_dir, f'{entity_type}_ranks.png')
                visualizer.plot_effect_ranks(effect_estimates, entity_type, 
                                            output_path=rank_plot_path)
                self.stdout.write(f"- 生成了{entity_type}增值效果排名图")
                
                # 生成残差分析图
                if student_results is not None and 'residual' in student_results.columns:
                    residual_plot_path = os.path.join(tvam_output_dir, 'residual_analysis.png')
                    visualizer.plot_residual_analysis(student_results, 
                                                    output_path=residual_plot_path)
                    self.stdout.write("- 生成了模型残差分析图")
                
                # 如果指定了特定实体(如班级或学校)，生成详细报告
                if options.get('entity_id'):
                    entity_id = options['entity_id']
                    entity_report_path = os.path.join(tvam_output_dir, f'{entity_id}_report.html')
                    
                    report_html = visualizer.generate_entity_report(
                        tvam_model, 
                        entity_id,
                        entity_type,
                        output_path=entity_report_path
                    )
                    
                    self.stdout.write(f"- 生成了{entity_type} {entity_id}的详细分析报告")
            except Exception as viz_error:
                self.stdout.write(self.style.WARNING(f"- 生成可视化时出错: {str(viz_error)}"))
                logger.exception("生成TVAM可视化时出错")
            
            self.stdout.write(f"- 结果已保存至 {tvam_output_dir}")
            
            fit_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"- TVAM模型分析完成，用时: {fit_time:.2f}秒"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"- TVAM模型分析失败: {str(e)}"))
            logger.exception("TVAM模型分析过程中发生错误")

    def _handle_bayesian_model(self, processor, options, output_dir):
        """
        处理贝叶斯增值模型分析
        
        执行贝叶斯多层次模型的构建、拟合和评估，生成报告和可视化结果
        
        Args:
            processor: 数据处理器实例
            options: 命令行选项
            output_dir: 输出目录
        """
        try:
            start_time = time.time()
            
            # 验证数据处理器
            if not hasattr(processor, 'data') or processor.data is None:
                self.stdout.write(self.style.ERROR("- 数据处理器中缺少有效数据"))
                return
            
            # 显示数据信息
            self.stdout.write(f"- 贝叶斯模型中，原始数据包含 {len(processor.data)} 条记录")
            mcmc_samples = options.get('mcmc_samples', 1000)
            tune = options.get('tune', 500)
            # 验证baseline参数并确保其在数据中存在
            baseline_exam = options.get('baseline')
            if baseline_exam is not None:
                exam_ids = processor.data['exam_id'].unique() if 'exam_id' in processor.data.columns else []
                if baseline_exam not in exam_ids:
                    self.stdout.write(self.style.WARNING(f"- 指定的基准考试 {baseline_exam} 不存在于数据中，将使用默认考试"))
                    baseline_exam = None
            
            # 记录清晰的流程信息
            self.stdout.write("- 流程概述:")
            self.stdout.write("  1. 初始化模型 (包含原始数据)")
            self.stdout.write("  2. 准备数据 (识别与移除基准考试记录)")
            self.stdout.write("  3. 拟合模型 (基于处理后的数据)")
            
            # 在初始化模型时，确保baseline_exam指向正确值
            bayesian_model = BayesianValueAddedModel(
                data=processor.data,
                data_processor=processor,
                baseline_exam=baseline_exam  # 使用已验证的baseline_exam
            )
            
            # 准备数据
            try:
                self.stdout.write("- 准备贝叶斯模型数据...")
                prepared_data = bayesian_model.prepare_data()  # 显式调用
                
                self.stdout.write(f"- 为贝叶斯模型准备了 {len(prepared_data)} 条建模数据")
                
                # 显示数据统计信息
                n_schools = prepared_data['school_idx'].nunique() if 'school_idx' in prepared_data.columns else 0
                n_classes = prepared_data['class_idx'].nunique() if 'class_idx' in prepared_data.columns else 0
                n_students = prepared_data['student_idx'].nunique() if 'student_idx' in prepared_data.columns else 0
                
                self.stdout.write(f"  * 包含 {n_schools} 所学校, {n_classes} 个班级, {n_students} 名学生")
                
                # 确认班级ID映射是否存在
                if 'class_id' in prepared_data.columns and 'class_idx' in prepared_data.columns:
                    class_map = prepared_data[['class_idx', 'class_id', 'class_name', 'school_name']].drop_duplicates()
                    self.stdout.write(f"  * 找到班级映射: {len(class_map)}个班级")
                else:
                    self.stdout.write(self.style.WARNING("  * 数据中缺少班级映射信息"))
                
                # 然后再拟合模型
                self.stdout.write(f"- 开始贝叶斯模型拟合，MCMC样本数: {mcmc_samples}...")
                bayesian_model.fit()  # 现在只负责拟合，不再处理数据
            except ValueError as e:
                self.stdout.write(self.style.ERROR(f"- 贝叶斯模型拟合失败: {str(e)}"))
                return
            
            # 计算增值效应
            value_added = bayesian_model.calculate_value_added()
            
            # 处理输出
            bayesian_output_dir = os.path.join(output_dir, 'bayesian')
            os.makedirs(bayesian_output_dir, exist_ok=True)
            
            # 保存模型结果 - 传递已计算的value_added
            saved_paths = bayesian_model.save_results(bayesian_output_dir, value_added=value_added)
            self.stdout.write(f"- 模型结果已保存至: {saved_paths}")
            
            # 可视化结果
            try:
                visualizer = ValueAddedVisualizer(value_added, model_name="Bayesian")
                
                # 保存可视化结果
                vis_paths = visualizer.visualize(bayesian_output_dir)
                self.stdout.write(f"- 创建了 {len(vis_paths)} 个可视化图表")
                
                # 导出Excel报告
                try:
                    excel_path = visualizer.export_excel_report(
                        bayesian_output_dir, 
                        params={
                            'mcmc_samples': mcmc_samples,
                            'tune': tune
                        },
                        metrics=bayesian_model.get_metrics(),
                        model_object=bayesian_model
                    )
                    self.stdout.write(f"- Excel完整报告已生成: {bayesian_output_dir}/bayesian_value_added_report.xlsx")
                except Exception as excel_error:
                    self.stdout.write(self.style.WARNING(f"- 导出Excel报告失败: {str(excel_error)}"))
                    logger.exception("导出贝叶斯模型Excel报告时出错")
            
            except Exception as viz_error:
                self.stdout.write(self.style.WARNING(f"- 生成可视化时出错: {str(viz_error)}"))
                logger.exception("生成贝叶斯模型可视化时出错")
            
            # 特殊贝叶斯模型特性：后验分布概要
            if hasattr(bayesian_model, 'get_posterior_summary'):
                try:
                    posterior_summary = bayesian_model.get_posterior_summary()
                    summary_path = os.path.join(bayesian_output_dir, 'posterior_summary.csv')
                    posterior_summary.to_csv(summary_path)
                    self.stdout.write(f"- 后验分布概要已保存至: {summary_path}")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"- 保存后验分布概要失败: {str(e)}"))
            
            fit_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"- 贝叶斯模型分析完成，用时: {fit_time:.2f}秒"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"- 贝叶斯模型分析失败: {str(e)}"))
            logger.exception("贝叶斯模型分析过程中发生错误")

    def _handle_timeseries_model(self, processor, options, output_dir):
        """
        处理时间序列贝叶斯增值模型
        
        Args:
            processor: 数据处理器
            options: 命令行选项
            output_dir: 输出目录
        """
        start_time = time.time()
        
        try:
            # 创建输出目录
            timeseries_output_dir = os.path.join(output_dir, 'timeseries')
            os.makedirs(timeseries_output_dir, exist_ok=True)
            
            # 检查是否有指定的基线考试ID和目标考试ID
            baseline_exams = options.get('baseline_exams')
            target_exam = options.get('target_exam')
            
            # 如果没有指定基线和目标考试，使用默认计数方式
            if not baseline_exams or not target_exam:
                self.stdout.write(self.style.WARNING("- 未指定基线考试ID或目标考试ID，将使用传统的基线数量方式"))
                
                # 使用原有的baseline_count方式
                # 初始化模型
                timeseries_model = TimeSeriesBayesianValueAddedModel(
                    baseline_exams_count=options['baseline_count'],
                    decay_factor=options['decay_factor'],
                    data=processor.data,
                    data_processor=processor
                )
                
                self.stdout.write(f"- 使用时间序列贝叶斯模型，基线考试次数: {options['baseline_count']}")
            else:
                # 使用指定的考试ID作为基线
                self.stdout.write(f"- 使用指定基线考试: {', '.join(baseline_exams)}")
                self.stdout.write(f"- 目标考试: {target_exam}")
                
                # 初始化模型(使用考试ID模式)
                timeseries_model = TimeSeriesBayesianValueAddedModel(
                    use_exam_ids=True,
                    baseline_exam_ids=baseline_exams,
                    target_exam_id=target_exam,
                    decay_factor=options['decay_factor'],
                    data=processor.data,
                    data_processor=processor
                )
            
            self.stdout.write(f"- 时间衰减因子: {options['decay_factor']}")
            
            # 设置MCMC参数
            mcmc_samples = options['mcmc_samples']
            tune_samples = options['tune']
            random_seed = options['random_seed']
            
            # 拟合模型
            self.stdout.write("- 开始时间序列贝叶斯模型拟合...")
            
            # 执行模型拟合
            results = timeseries_model.fit(
                processor.data,
                draws=mcmc_samples,
                tune=tune_samples,
                random_seed=random_seed,
                cores=4  # 利用多核心
            )
            
            self.stdout.write("- 时间序列贝叶斯模型拟合完成")
            
            # 获取学校名称映射
            school_names = {}
            for _, row in processor.data.iterrows():
                school_names[row['school_id']] = row['school_name']
            
            processor._ensure_class_names(processor.data)
            
            # 获取班级信息映射
            class_info = {}
            for _, row in processor.data.iterrows():
                if row['class_id'] not in class_info:
                    class_info[row['class_id']] = {
                        'school_id': row['school_id'],
                        'school_name': row['school_name'],
                        # 班级名称处理 - 根据实际数据格式选择合适的字段
                        'class_name': row.get('class_name', f"班级{row['class_id']}")
                    }
            
            # 保存学校效应，增加school_name字段
            school_effects = []
            for school_id, effect in results['school_effects'].items():
                school_effects.append({
                    'school_id': school_id,
                    'school_name': school_names.get(school_id, f"未知学校({school_id})"),
                    'effect': round(float(effect['effect']), 3),
                    'ci_lower': round(float(effect['ci_lower']), 3),
                    'ci_upper': round(float(effect['ci_upper']), 3),
                    'significant': effect['significant']
                })
            
            school_effects_df = pd.DataFrame(school_effects)
            school_effects_path = os.path.join(timeseries_output_dir, 'school_effects.csv')
            school_effects_df.to_csv(school_effects_path, index=False)
            self.stdout.write(f"- 学校效应结果已保存至: {school_effects_path}")
            
            # 保存班级效应，增加school_name和class_name字段
            class_effects = []
            for class_id, effect in results['class_effects'].items():
                # 获取班级信息
                info = class_info.get(class_id, {})
                
                class_effects.append({
                    'class_id': class_id,
                    'class_name': info.get('class_name', f"未知班级({class_id})"),
                    'school_id': info.get('school_id', None),
                    'school_name': info.get('school_name', "未知学校"),
                    'effect': round(float(effect['effect']), 3),
                    'ci_lower': round(float(effect['ci_lower']), 3),
                    'ci_upper': round(float(effect['ci_upper']), 3),
                    'significant': effect['significant']
                })
            
            class_effects_df = pd.DataFrame(class_effects)
            class_effects_path = os.path.join(timeseries_output_dir, 'class_effects.csv')
            class_effects_df.to_csv(class_effects_path, index=False)
            self.stdout.write(f"- 班级效应结果已保存至: {class_effects_path}")
            
            # 保存模型摘要
            if 'model_summary' in results:
                summary_path = os.path.join(timeseries_output_dir, 'model_summary.csv')
                results['model_summary'].to_csv(summary_path)
                self.stdout.write(f"- 模型摘要已保存至: {summary_path}")
            
            # 可视化效应
            try:
                import matplotlib.pyplot as plt
                
                # 学校效应可视化
                if len(school_effects) > 0:
                    school_effects_df = school_effects_df.sort_values('effect')
                    plt.figure(figsize=(10, 6))
                    plt.errorbar(
                        range(len(school_effects_df)),
                        school_effects_df['effect'],
                        yerr=[
                            school_effects_df['effect'] - school_effects_df['ci_lower'],
                            school_effects_df['ci_upper'] - school_effects_df['effect']
                        ],
                        fmt='o',
                        capsize=5
                    )
                    plt.grid(True, alpha=0.3)
                    plt.axhline(y=0, color='r', linestyle='-', alpha=0.3)
                    plt.title('学校增值效应(时间序列贝叶斯模型)')
                    plt.xlabel('学校排名')
                    plt.ylabel('增值效应')
                    
                    school_plot_path = os.path.join(timeseries_output_dir, 'school_effects.png')
                    plt.tight_layout()
                    plt.savefig(school_plot_path, dpi=300)
                    plt.close()
                    self.stdout.write(f"- 学校效应可视化已保存至: {school_plot_path}")
                
                # 班级效应可视化
                if len(class_effects) > 0:
                    class_effects_df = class_effects_df.sort_values('effect')
                    plt.figure(figsize=(10, 6))
                    plt.errorbar(
                        range(len(class_effects_df)),
                        class_effects_df['effect'],
                        yerr=[
                            class_effects_df['effect'] - class_effects_df['ci_lower'],
                            class_effects_df['ci_upper'] - class_effects_df['effect']
                        ],
                        fmt='o',
                        capsize=5
                    )
                    plt.grid(True, alpha=0.3)
                    plt.axhline(y=0, color='r', linestyle='-', alpha=0.3)
                    plt.title('班级增值效应(时间序列贝叶斯模型)')
                    plt.xlabel('班级排名')
                    plt.ylabel('增值效应')
                    
                    class_plot_path = os.path.join(timeseries_output_dir, 'class_effects.png')
                    plt.tight_layout()
                    plt.savefig(class_plot_path, dpi=300)
                    plt.close()
                    self.stdout.write(f"- 班级效应可视化已保存至: {class_plot_path}")
            except Exception as viz_error:
                self.stdout.write(self.style.WARNING(f"- 生成可视化时出错: {str(viz_error)}"))
            
            fit_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"- 时间序列贝叶斯模型分析完成，用时: {fit_time:.2f}秒"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"- 时间序列贝叶斯模型分析失败: {str(e)}"))
            logger.exception("时间序列贝叶斯模型分析出错")

    def _handle_student_cluster_analyzer(self, processor, options, output_dir):
        """
        处理学生进步模式聚类分析
        
        Args:
            processor: 数据处理器
            options: 命令行选项
            output_dir: 输出目录
        """
        try:
            start_time = time.time()
            
            # 创建输出目录
            cluster_output_dir = os.path.join(output_dir, 'student_cluster')
            os.makedirs(cluster_output_dir, exist_ok=True)
            
            # 使用原始数据，避免processor的默认处理逻辑
            self.stdout.write("- 准备聚类分析数据...")
            
            # 检查processor.data是否存在
            if processor.data is None:
                self.stdout.write(self.style.ERROR("- processor.data 为空！"))
                return
            
            self.stdout.write(f"- 原始数据字段: {list(processor.data.columns)}")
            
            # 尝试处理类ID
            try:
                processor.model_data = processor._process_class_ids(processor.data)
                self.stdout.write(f"- 处理后数据字段: {list(processor.model_data.columns)}")
                self.stdout.write(f"- 处理后数据形状: {processor.model_data.shape}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"- 处理class_id时出错: {str(e)}"))
                import traceback
                self.stdout.write(traceback.format_exc())
                # 降级处理 - 直接使用原始数据
                processor.model_data = processor.data.copy()
            
            raw_data = processor.model_data.copy()
            
            
            # 检查并处理分数字段
            score_field = None
            if 'standard_score' in raw_data.columns:
                score_field = 'standard_score'
                self.stdout.write("- 使用已有的标准化分数")
            elif 'raw_score' in raw_data.columns:
                score_field = 'raw_score'
                self.stdout.write("- 找到原始分数字段，将计算标准化分数")
                # 计算标准化分数
                raw_data['standard_score'] = raw_data.groupby('exam_id')[score_field].transform(
                    lambda x: (x - x.mean()) / x.std() if x.std() != 0 else 0
                )

            else:
                self.stdout.write(self.style.ERROR("- 错误: 数据中没有找到任何分数字段"))
                self.stdout.write(f"- 请确保数据中包含以下字段之一: score, standard_score, 或其他包含'score'的字段")
                return
            
            # 确保有exam_order字段
            if 'exam_order' in raw_data.columns:
                self.stdout.write("- 使用已有的exam_order字段")
            elif 'exam_date' in raw_data.columns:
                # 按日期排序考试
                exam_dates = raw_data.groupby('exam_id')['exam_date'].first().sort_values()
                exam_order = {exam: i for i, exam in enumerate(exam_dates.index)}
                raw_data['exam_order'] = raw_data['exam_id'].map(exam_order)
                baseline_exam = exam_dates.index[0]
                self.stdout.write(f"- 根据考试日期计算exam_order")
            else:
                # 按考试ID排序
                exam_ids = sorted(raw_data['exam_id'].unique())
                exam_order = {exam: i for i, exam in enumerate(exam_ids)}
                raw_data['exam_order'] = raw_data['exam_id'].map(exam_order)
                baseline_exam = exam_ids[0]
                self.stdout.write(f"- 根据考试ID顺序计算exam_order")
            
            self.stdout.write(f"- 使用基准考试: {baseline_exam}")
            
            # 检查每个学生的考试次数
            exam_counts = raw_data.groupby('student_id')['exam_id'].nunique()
            eligible_students = exam_counts[exam_counts >= options['min_exams']].index
            
            # 仅保留符合条件的学生
            filtered_data = raw_data[raw_data['student_id'].isin(eligible_students)]
            self.stdout.write(f"- 聚类数据字段: {list(filtered_data.columns)}")
            # 检查结果
            student_count = filtered_data['student_id'].nunique()

            self.stdout.write(f"- 筛选出参加至少{options['min_exams']}次考试的{student_count}名学生")
            
            if student_count < 5:
                self.stdout.write(self.style.ERROR(f"- 错误: 参加足够考试的学生数量太少({student_count})，无法进行有效聚类"))
                return
            
            # 创建一个简化的data_processor
            from types import SimpleNamespace
            custom_processor = SimpleNamespace()
            custom_processor.data = filtered_data
            custom_processor.get_data_processors = lambda: {}
            
            # 重要：直接将数据浅拷贝到一个新对象
            cluster_data = filtered_data.copy(deep=False)

            # 初始化聚类分析模型 - 确保数据被正确传递
            self.stdout.write(f"- 初始化学生进步模式聚类分析模型，聚类数量: {options['clusters']}")
            
            # 使用强制传入的数据初始化，避免可能的属性覆盖
            cluster_model = StudentProgressClusterAnalyzer(
                # 确保数据直接传递并在类内部不被覆盖
                data=cluster_data,
                data_processor=custom_processor,
                n_clusters=options['clusters'],
                min_exams=options['min_exams'],
                random_state=options['random_seed']
            )
            
            # 确保数据被正确绑定
            self.stdout.write(f"- 验证数据绑定: {cluster_model.data is not None}")
            
            # 先调用prepare_data，但不覆盖原始数据
            try:
                prepared_data = cluster_model.prepare_data(data=cluster_data)
                print(prepared_data.columns)
                self.stdout.write(f"- 准备了{len(prepared_data)}条数据")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"- prepare_data警告: {str(e)}"))
                prepared_data = cluster_data
            
            # 确保模型仍然有数据
            if cluster_model.data is None:
                self.stdout.write("- 警告: 模型的data属性被重置为None，重新赋值")
                cluster_model.data = cluster_data.copy()
            
            # 手动绕过提取特征可能的问题
            try:
                # 保持使用StudentProgressClusterAnalyzer类的方法提取特征
                self.stdout.write("- 使用StudentProgressClusterAnalyzer提取学习轨迹特征...")
                features = cluster_model._extract_clustering_features()
                self.stdout.write(f"- 成功提取{len(features)}名学生的特征")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"- 使用原始特征提取方法失败: {str(e)}"))
                import traceback
                self.stdout.write(traceback.format_exc())
                
                # 尝试直接调用方法，传入数据
                self.stdout.write("- 尝试直接传入数据...")
                
                # 保存原来的self.data
                original_data = cluster_model.data
                
                # 直接调用方法并传入数据
                try:
                    # 尝试使用prepare_data的结果
                    features = cluster_model._extract_clustering_features(data=prepared_data)
                except Exception as inner_e:
                    self.stdout.write(self.style.ERROR(f"- 直接传入数据仍然失败: {str(inner_e)}"))
                    # 最后尝试使用我们的自定义特征提取
                    self.stdout.write("- 回退到自定义特征提取...")
                    features = self._manually_extract_clustering_features(filtered_data, options['min_exams'])
                finally:
                    # 恢复原来的self.data
                    cluster_model.data = original_data
            
            # 如果上面的方法都失败了...
            if features is None or len(features) == 0:
                self.stdout.write(self.style.ERROR("- 无法提取特征，无法继续聚类分析"))
                return
            
            # 确保数据是数值型
            numeric_cols = ['growth_rate', 'volatility', 'acceleration', 
                        'max_improvement', 'max_decline', 'start_level', 
                        'end_level', 'total_improvement', 'rank_change']
            
            for col in numeric_cols:
                if col in features.columns:
                    features[col] = pd.to_numeric(features[col], errors='coerce')
                    features[col] = features[col].fillna(features[col].median())
            
            # 在聚类前添加此代码检查分布
            self.stdout.write("- 学生起点水平分布统计:")
            self.stdout.write(f"  * 最小值: {features['start_level'].min():.2f}")
            self.stdout.write(f"  * 第一四分位数: {features['start_level'].quantile(0.25):.2f}")
            self.stdout.write(f"  * 中位数: {features['start_level'].median():.2f}")
            self.stdout.write(f"  * 第三四分位数: {features['start_level'].quantile(0.75):.2f}")
            self.stdout.write(f"  * 最大值: {features['start_level'].max():.2f}")
            
            # 在此处提前定义聚类特征
            clustering_features = [
                'growth_rate', 'volatility', 'acceleration', 
                'max_improvement', 'max_decline', 'total_improvement',
                'start_level', 'end_level', 'rank_change'
            ]
            
            # 在执行K-means聚类分析前添加最优聚类数评估
            if options.get('find_optimal_clusters', False):
                self.stdout.write("- 评估最优聚类数量...")
                
                scores = []
                for k in range(2, 12):  # 测试2到11个聚类
                    kmeans = KMeans(n_clusters=k, random_state=options['random_seed'], n_init=10)
                    cluster_labels = kmeans.fit_predict(features[clustering_features])
                    try:
                        score = silhouette_score(features[clustering_features], cluster_labels)
                        scores.append((k, score))
                        self.stdout.write(f"  * {k}个聚类的轮廓系数: {score:.4f}")
                    except:
                        self.stdout.write(f"  * {k}个聚类评估失败")
                
                # 找出最佳聚类数量
                best_k = max(scores, key=lambda x: x[1])
                self.stdout.write(f"- 最优聚类数量为: {best_k[0]} (轮廓系数: {best_k[1]:.4f})")
                
                # 如果用户没有明确指定聚类数，则使用最优值
                if not options.get('clusters_specified', False):
                    options['clusters'] = best_k[0]
                    self.stdout.write(f"- 将使用最优聚类数: {options['clusters']}")
                if best_k[0] < options.get('min_clusters', 4):
                    self.stdout.write(f"- 数学上最优聚类数为{best_k[0]}，但为满足教育分析需求，将使用{options.get('min_clusters', 4)}个聚类")
                    options['clusters'] = options.get('min_clusters', 4)
                else:
                    options['clusters'] = best_k[0]
            

            
            # 执行聚类
            self.stdout.write(f"- 执行K-means聚类分析 (k={options['clusters']})...")
            try:
                # 执行聚类

                
                # 选择用于聚类的特征
                clustering_features = [
                    'growth_rate', 'volatility', 'acceleration', 
                    'max_improvement', 'max_decline', 'total_improvement',
                    'start_level', 'end_level', 'rank_change'
                ]
                
                if not clustering_features:
                    self.stdout.write("- 未找到标准化特征，将使用原始特征...")
                    clustering_features = numeric_cols
                    
                    # 手动执行标准化
                    from sklearn.preprocessing import StandardScaler
                    scaler = StandardScaler()
                    scaled_features = scaler.fit_transform(features[clustering_features])
                    
                    # 添加标准化特征
                    scaled_df = pd.DataFrame(
                        scaled_features, 
                        columns=[f"{col}_scaled" for col in clustering_features],
                        index=features.index
                    )
                    features = pd.concat([features, scaled_df], axis=1)
                    clustering_features = [f"{col}_scaled" for col in clustering_features]
                    
                # 执行聚类
                kmeans = KMeans(
                    n_clusters=options['clusters'],
                    random_state=options['random_seed'],
                    n_init=10
                )
                features['cluster'] = kmeans.fit_predict(features[clustering_features])
                
                # 保存到模型
                cluster_model.cluster_model = kmeans
                cluster_model.features_df = features
                
                # 解释聚类 - 使用StudentProgressClusterAnalyzer的方法
                try:
                    cluster_profiles = cluster_model._interpret_clusters()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"- 使用原始解释方法失败: {str(e)}"))
                    # 使用自定义解释方法
                    cluster_profiles = self._interpret_clusters(features, options['clusters'])
                
                # 输出聚类结果摘要
                self.stdout.write("- 聚类结果:")
                for cluster_id, profile in cluster_profiles.items():
                    count = len(features[features['cluster'] == cluster_id])
                    percent = (count / len(features)) * 100
                    self.stdout.write(f"  * 聚类 {cluster_id} - {profile['label']}: {count}名学生 ({percent:.1f}%)")
                    self.stdout.write(f"    - {profile['description']}")
                
                # 保存聚类结果
                results_df = features[['student_id', 'cluster']]
                if 'student_name' in features.columns:
                    results_df['student_name'] = features['student_name']
                if 'class_name' in features.columns:
                    results_df['class_name'] = features['class_name']
                if 'school_name' in features.columns:
                    results_df['school_name'] = features['school_name']
                
                # 保存结果
                result_path = os.path.join(cluster_output_dir, 'student_clusters.csv')
                results_df.to_csv(result_path, index=False)
                self.stdout.write(f"- 聚类结果已保存至: {result_path}")
                
                # 找到聚类分析中保存特征数据的代码部分
                # 在保存特征数据前添加聚类描述字段
                try:
                    # 创建聚类ID到描述的映射
                    cluster_descriptions = {
                        cluster_id: profile['description'] 
                        for cluster_id, profile in cluster_profiles.items()
                    }
                    
                    # 添加聚类标签和描述列
                    features['cluster_label'] = features['cluster'].map(
                        {cluster_id: profile['label'] for cluster_id, profile in cluster_profiles.items()}
                    )
                    features['cluster_description'] = features['cluster'].map(cluster_descriptions)
                    
                    # 保存特征数据
                    features_path = os.path.join(cluster_output_dir, 'student_features.csv')
                    features.to_csv(features_path, index=False)
                    self.stdout.write(f"- 学生特征数据已保存至: {features_path}")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"- 添加聚类描述失败: {str(e)}"))
                    # 备份方案：不添加描述列直接保存
                    features_path = os.path.join(cluster_output_dir, 'student_features.csv')
                    features.to_csv(features_path, index=False)
                    self.stdout.write(f"- 学生特征数据已保存至: {features_path} (无聚类描述)")
                
                # 可视化结果
                if options['visualize_clusters']:
                    self._visualize_cluster_results(
                        features, 
                        cluster_profiles, 
                        filtered_data, 
                        clustering_features, 
                        cluster_output_dir
                    )
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"- 聚类分析失败: {str(e)}"))
                import traceback
                self.stdout.write(traceback.format_exc())
            
            # 输出完成信息
            fit_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"- 学生进步模式聚类分析完成，用时: {fit_time:.2f}秒"))
            
            # 在聚类分析完成后添加对极高起点学生的分析
            # 直接计算94%分位数作为极高起点阈值
            very_high_threshold = features['start_level'].quantile(0.94)

            # 调用极高起点学生分析函数
            self._analyze_top_students(
                features, 
                raw_data, 
                very_high_threshold,  # 现在已定义
                cluster_output_dir
            )
            
            # 分析学生分层特征和变化
            features_with_layers, layer_growth_dict = self._analyze_student_layers(features, filtered_data, cluster_output_dir)
            
            # 转换为前端期望的格式
            layer_growth_dict = {}
            for level in layer_growth_dict.index:
                for trend in layer_growth_dict.columns:
                    key = f"{level}，{trend}型"
                    layer_growth_dict[key] = float(layer_growth_dict.loc[level, trend])
            
            # 保存转换后的数据
            growth_dict_path = os.path.join(output_dir, 'student_layer_growth_dict.json')
            with open(growth_dict_path, 'w', encoding='utf-8') as f:
                json.dump(layer_growth_dict, f, ensure_ascii=False, indent=2)
            
            self.stdout.write(f"- 分层成长键值对已保存至: {growth_dict_path}")
            
            # 修改ValueAddedModelAnalyzer.analyze方法，确保返回这个字典而不是交叉表
            
            # 在返回结果前处理考试记录数据
            try:
                self.stdout.write("- 处理学生考试记录数据...")
                
                # 创建考试记录字典（按学生ID分组）
                exam_records = {}
                
                # 从filtered_data中提取考试记录（这里filtered_data应该包含原始考试数据）
                for student_id, student_data in filtered_data.groupby('student_id'):
                    # 按考试顺序排序
                    student_exams = student_data.sort_values('exam_order')
                    
                    # 提取关键字段
                    student_records = []
                    for _, row in student_exams.iterrows():
                        exam_record = {
                            'exam_id': row.get('exam_id', ''),
                            'exam_name': row.get('exam_name', f'考试 {row.get("exam_order", 0)}'),
                            'exam_date': row.get('exam_date', ''),
                            'raw_score': float(row.get('raw_score', row.get('score', 0))),
                            'standard_score': float(row.get('standard_score', 0)),
                            'percentile': float(row.get('percentile', 0)) if 'percentile' in row else None,
                            'rank': int(row.get('rank', 0)) if 'rank' in row else None,
                            'subject_id': row.get('subject_id', options.get('subject', '')),
                            'total_score': float(row.get('total_score', 100)),
                            'grade': row.get('grade', ''),
                            'class_name': row.get('class_name', '')
                        }
                        student_records.append(exam_record)
                    
                    # 保存到总字典
                    exam_records[student_id] = student_records
                
                self.stdout.write(f"- 处理了{len(exam_records)}名学生的考试记录")
                
                # 将考试记录数据保存到文件
                exam_records_path = os.path.join(output_dir, 'exam_records.json')
                with open(exam_records_path, 'w', encoding='utf-8') as f:
                    json.dump(exam_records, f, ensure_ascii=False, indent=2)
                
                self.stdout.write(f"- 考试记录数据已保存至: {exam_records_path}")
                
                # 准备完整结果对象
                full_result = {
                    'student_clusters': features_with_layers, 
                    'student_features': processor.cluster_analyzer.student_features, 
                    'student_layer_growth': layer_growth_dict,
                    'exam_records': exam_records  # 添加考试记录
                }

                # 保存完整结果
                result_path = os.path.join(output_dir, 'analysis_result.json')
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(full_result, f, ensure_ascii=False, indent=2)

                self.stdout.write(f"- 完整分析结果已保存至: {result_path}")

                # 返回完整结果
                return full_result
                
            except Exception as e:
                self.stderr.write(f"处理考试记录数据出错: {str(e)}")
                # 如果出错，仍返回其他数据
                return {
                    'student_clusters': features_with_layers, 
                    'student_features': processor.cluster_analyzer.student_features, 
                    'student_layer_growth': layer_growth_dict
                }
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"- 学生进步模式聚类分析失败: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            logger.exception("学生进步模式聚类分析出错")

    def _manually_extract_clustering_features(self, data, min_exams=3):
        """
        手动提取学生学习轨迹特征
        
        Args:
            data: 包含学生考试记录的DataFrame
            min_exams: 每个学生需要的最少考试次数
            
        Returns:
            DataFrame: 包含学生特征的数据框
        """
        # 确保数据包含必要字段
        required_fields = ['student_id', 'exam_id', 'standard_score', 'exam_order']
        for field in required_fields:
            if field not in data.columns:
                raise ValueError(f"数据中缺少必要字段: {field}")
        
        # 存储所有学生的特征
        student_features = []
        
        # 按学生ID分组
        for student_id, group in data.groupby('student_id'):
            # 跳过参加考试次数不足的学生
            if group['exam_id'].nunique() < min_exams:
                continue
            
            # 按考试顺序排序
            student_data = group.sort_values('exam_order')
            
            # 提取学生基本信息
            student_info = {
                'student_id': student_id,
                'student_name': student_data['student_name'].iloc[0] if 'student_name' in student_data.columns else 'Unknown',
                'class_name': student_data['class_name'].iloc[0] if 'class_name' in student_data.columns else 'Unknown',
                'school_name': student_data['school_name'].iloc[0] if 'school_name' in student_data.columns else 'Unknown',
                'grade': student_data['grade'].iloc[0] if 'grade' in student_data.columns else 'Unknown'
            }
            
            # 计算成长指标
            scores = student_data['standard_score'].values
            
            # 计算基本统计量
            features = {
                'start_level': scores[0],                                  # 起始水平
                'end_level': scores[-1],                                   # 结束水平
                'total_improvement': scores[-1] - scores[0],               # 总成长量
                'volatility': np.std(scores),                              # 波动性
                'max_improvement': np.max(np.diff(scores)) if len(scores) > 1 else 0,  # 最大进步
                'max_decline': np.min(np.diff(scores)) if len(scores) > 1 else 0,      # 最大下滑
            }
            
            # 计算平均增长率(线性回归斜率)
            x = np.arange(len(scores))
            features['growth_rate'] = np.polyfit(x, scores, 1)[0] if len(scores) > 1 else 0
            
            # 计算加速度(二次项系数)
            if len(scores) > 2:
                features['acceleration'] = np.polyfit(x, scores, 2)[0]
            else:
                features['acceleration'] = 0
            
            # 计算排名变化(如果有排名信息)
            if 'rank' in student_data.columns:
                ranks = student_data['rank'].values
                features['rank_change'] = ranks[0] - ranks[-1]  # 排名提升为正
            else:
                features['rank_change'] = 0
            
            # 合并学生信息和特征
            student_features.append({**student_info, **features})
        
        # 创建特征数据框
        features_df = pd.DataFrame(student_features)
        
        # 标准化特征

        feature_columns = ['growth_rate', 'volatility', 'acceleration', 
                          'max_improvement', 'max_decline', 'start_level', 
                          'end_level', 'total_improvement', 'rank_change']
        
        # 确保所有特征列存在
        for col in feature_columns:
            if col not in features_df.columns:
                features_df[col] = 0
        
        # 执行标准化
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features_df[feature_columns])
        
        # 添加标准化特征
        scaled_df = pd.DataFrame(
            scaled_features, 
            columns=[f"{col}_scaled" for col in feature_columns],
            index=features_df.index
        )
        
        # 合并原始和标准化特征
        return pd.concat([features_df, scaled_df], axis=1)

    def _interpret_clusters(self, features, n_clusters):
        """
        解释聚类结果，使用六分位数细化起点分类
        
        Args:
            features: 带有聚类标签的特征数据框
            n_clusters: 聚类数量
            
        Returns:
            dict: 聚类描述
        """
        # 计算每个聚类的特征均值
        cluster_means = {}
        for i in range(n_clusters):
            cluster_data = features[features['cluster'] == i]
            if len(cluster_data) > 0:
                # 提取主要特征的均值
                means = {
                    'growth_rate': cluster_data['growth_rate'].mean(),
                    'volatility': cluster_data['volatility'].mean(),
                    'total_improvement': cluster_data['total_improvement'].mean(),
                    'start_level': cluster_data['start_level'].mean(),
                    'end_level': cluster_data['end_level'].mean()
                }
                cluster_means[i] = means
        
        # 计算分位数作为动态阈值 - 进一步细分高起点
        very_low_threshold = features['start_level'].quantile(0.2)
        low_threshold = features['start_level'].quantile(0.4)
        medium_threshold = features['start_level'].quantile(0.6)
        high_threshold = features['start_level'].quantile(0.8)
        very_high_threshold = features['start_level'].quantile(0.94)  # 新增极高起点阈值
        
        # 打印阈值信息作为参考
        print(f"起点分位数阈值: 极低(<{very_low_threshold:.1f}), 低({very_low_threshold:.1f}-{low_threshold:.1f}), "
              f"中({low_threshold:.1f}-{medium_threshold:.1f}), 中高({medium_threshold:.1f}-{high_threshold:.1f}), "
              f"高({high_threshold:.1f}-{very_high_threshold:.1f}), 极高(>{very_high_threshold:.1f})")
        
        # 基于聚类均值和分位阈值判断
        cluster_profiles = {}
        for cluster_id, means in cluster_means.items():
            # 细化增长趋势
            if means['growth_rate'] > 0.3:
                growth_trend = "快速上升"
            elif means['growth_rate'] > 0.1:
                growth_trend = "稳步上升"
            elif means['growth_rate'] > 0.02:
                growth_trend = "略有上升"
            elif means['growth_rate'] > -0.02:
                growth_trend = "基本稳定"
            elif means['growth_rate'] > -0.1:
                growth_trend = "略有下降"
            elif means['growth_rate'] > -0.3:
                growth_trend = "缓慢下降"
            else:
                growth_trend = "明显下降"
            
            # 确定波动性
            if means['volatility'] > 0.8:
                stability = "波动较大"
            elif means['volatility'] > 0.5:
                stability = "有一定波动"
            elif means['volatility'] > 0.3:
                stability = "略有波动"
            else:
                stability = "非常稳定"
            
            # 使用六分位数细化起始水平
            if means['start_level'] > very_high_threshold:
                start_level = "极高起点"
            elif means['start_level'] > high_threshold:
                start_level = "高起点"
            elif means['start_level'] > medium_threshold:
                start_level = "中高起点"
            elif means['start_level'] > low_threshold:
                start_level = "中等起点"
            elif means['start_level'] > very_low_threshold:
                start_level = "中低起点"
            else:
                start_level = "低起点"
            
            # 细化总体进步描述
            if means['total_improvement'] > 1.0:
                improvement = "显著进步"
            elif means['total_improvement'] > 0.5:
                improvement = "明显进步"
            elif means['total_improvement'] > 0.2:
                improvement = "稳步提升"
            elif means['total_improvement'] > -0.2:
                improvement = "基本保持水平"
            elif means['total_improvement'] > -0.5:
                improvement = "轻微下滑"
            elif means['total_improvement'] > -1.0:
                improvement = "有所退步"
            else:
                improvement = "显著退步"
            
            # 添加更多的学习模式描述
            learning_pattern = "未知模式"

            # 根据起点和增长趋势确定学习模式
            if means['start_level'] > high_threshold:
                if means['total_improvement'] > 0.5:
                    learning_pattern = "优等生保持领先"
                elif means['total_improvement'] < -0.5:
                    learning_pattern = "优等生渐失优势"
                else:
                    learning_pattern = "优等生稳定型"
            elif means['start_level'] < low_threshold:
                if means['total_improvement'] > 0.5:
                    learning_pattern = "后进生迎头赶上"
                elif means['growth_rate'] > 0.1:
                    learning_pattern = "后进生稳步进步"
                else:
                    learning_pattern = "后进生持续挣扎"
            else:
                if means['growth_rate'] > 0.2:
                    learning_pattern = "中游生快速提升"
                elif means['growth_rate'] < -0.2:
                    learning_pattern = "中游生明显下滑"
                elif means['volatility'] > 0.6:
                    learning_pattern = "中游生不稳定型"
                else:
                    learning_pattern = "中游生稳定型"
            
            # 生成标签和描述
            label = f"{start_level}，{growth_trend}型"
            description = f"{start_level}学生，成绩{growth_trend}，{stability}，整体表现{improvement}。属于{learning_pattern}。"
            
            # 保存聚类描述
            cluster_profiles[cluster_id] = {
                'label': label,
                'description': description,
                'means': means
            }
        
        return cluster_profiles

    def _visualize_cluster_results(self, features, cluster_profiles, raw_data, clustering_features, output_dir):
        """
        生成聚类结果可视化
        
        Args:
            features: 特征数据框
            cluster_profiles: 聚类描述
            raw_data: 原始数据
            clustering_features: 用于聚类的特征列
            output_dir: 输出目录
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            from sklearn.decomposition import PCA
            
            # 设置绘图样式
            sns.set_style("whitegrid")
            plt.rcParams['font.sans-serif'] = ['SimHei']  # 中文字体
            plt.rcParams['axes.unicode_minus'] = False    # 正常显示负号
            
            self.stdout.write("- 生成聚类可视化...")
            
            # 1. PCA降维可视化
            try:
                # 执行PCA降维
                pca = PCA(n_components=2)
                pca_result = pca.fit_transform(features[clustering_features])
                
                # 创建PCA数据框
                pca_df = pd.DataFrame(data=pca_result, columns=['PC1', 'PC2'])
                pca_df['cluster'] = features['cluster']
                pca_df['cluster_label'] = pca_df['cluster'].map(
                    {k: f"{k}: {v['label']}" for k, v in cluster_profiles.items()}
                )
                
                # 绘制PCA散点图
                plt.figure(figsize=(10, 8))
                sns.scatterplot(
                    x='PC1', y='PC2',
                    hue='cluster_label',
                    palette='tab10',
                    data=pca_df,
                    s=80,
                    alpha=0.7
                )
                
                plt.title('学生进步模式聚类分析 (PCA降维可视化)', fontsize=15)
                plt.xlabel(f'主成分1 (解释方差: {pca.explained_variance_ratio_[0]:.2%})', fontsize=12)
                plt.ylabel(f'主成分2 (解释方差: {pca.explained_variance_ratio_[1]:.2%})', fontsize=12)
                plt.legend(title='学生类型', fontsize=10)
                
                # 保存图表
                pca_path = os.path.join(output_dir, 'cluster_pca_visualization.png')
                plt.tight_layout()
                plt.savefig(pca_path, dpi=300)
                plt.close()
                self.stdout.write(f"- PCA聚类可视化已保存至: {pca_path}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"- PCA可视化生成失败: {str(e)}"))
            
            # 2. 典型学生轨迹图
            try:
                # 选择每个聚类中的典型学生
                typical_students = []
                
                for cluster_id in range(len(cluster_profiles)):
                    # 获取该聚类的学生
                    cluster_students = features[features['cluster'] == cluster_id]
                    
                    if len(cluster_students) > 0:
                        # 简单选择前3个学生
                        typical = cluster_students.head(3)
                        for _, student in typical.iterrows():
                            typical_students.append({
                                'student_id': student['student_id'],
                                'cluster_id': cluster_id
                            })
                
                # 创建子图
                fig, axes = plt.subplots(
                    min(2, len(cluster_profiles)), 
                    min(2, (len(cluster_profiles) + 1) // 2), 
                    figsize=(14, 10)
                )
                axes = np.array(axes).flatten()
                
                # 为每个聚类画轨迹
                for i, cluster_id in enumerate(sorted(cluster_profiles.keys())):
                    if i >= len(axes):  # 防止索引越界
                        break
                    
                    ax = axes[i]
                    
                    # 获取该聚类的典型学生
                    cluster_typical = [s for s in typical_students if s['cluster_id'] == cluster_id]
                    
                    # 为每个典型学生画轨迹
                    for student in cluster_typical:
                        student_id = student['student_id']
                        student_data = raw_data[raw_data['student_id'] == student_id]
                        student_data = student_data.sort_values('exam_order')
                        
                        # 绘制轨迹
                        ax.plot(
                            student_data['exam_order'],
                            student_data['standard_score'],
                            'o-',
                            label=f"学生 {student_id}",
                            linewidth=2,
                            alpha=0.8
                        )
                    
                    # 设置图表标题和标签
                    ax.set_title(f"聚类 {cluster_id}: {cluster_profiles[cluster_id]['label']}", fontsize=12)
                    ax.set_xlabel('考试序号')
                    ax.set_ylabel('标准化分数')
                    ax.grid(True, alpha=0.3)
                    ax.legend(loc='best')
                
                # 保存图表
                plt.tight_layout()
                trajectory_path = os.path.join(output_dir, 'typical_student_trajectories.png')
                plt.savefig(trajectory_path, dpi=300)
                plt.close()
                self.stdout.write(f"- 典型学生轨迹图已保存至: {trajectory_path}")
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"- 轨迹图生成失败: {str(e)}"))
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"- 可视化生成失败: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())

    def _analyze_top_students(self, features, raw_data, very_high_threshold, output_dir):
        """
        分析极高起点学生的变化情况
        
        Args:
            features: 特征数据框
            raw_data: 原始考试数据
            very_high_threshold: 极高起点阈值
            output_dir: 输出目录
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            
            # 设置绘图样式
            sns.set_style("whitegrid")
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            self.stdout.write("- 分析极高起点学生变化...")
            
            # 1. 找出极高起点学生
            top_students = features[features['start_level'] > very_high_threshold]
            self.stdout.write(f"- 找到{len(top_students)}名极高起点学生（>{very_high_threshold:.1f}分）")
            
            # 2. 计算极高起点学生的统计信息
            growth_stats = {
                '上升': len(top_students[top_students['growth_rate'] > 0.02]),
                '基本稳定': len(top_students[(top_students['growth_rate'] >= -0.02) & (top_students['growth_rate'] <= 0.02)]),
                '下降': len(top_students[top_students['growth_rate'] < -0.02])
            }
            
            # 打印统计信息
            self.stdout.write("- 极高起点学生变化情况:")
            for category, count in growth_stats.items():
                percentage = count / len(top_students) * 100 if len(top_students) > 0 else 0
                self.stdout.write(f"  * {category}: {count}人 ({percentage:.1f}%)")
            
            # 3. 可视化极高起点学生的变化趋势
            plt.figure(figsize=(12, 8))
            
            # 按成长率排序
            top_students_sorted = top_students.sort_values('growth_rate')
            
            # 将学生分为三组：下降、稳定、上升
            colors = []
            for rate in top_students_sorted['growth_rate']:
                if rate > 0.02:
                    colors.append('green')  # 上升
                elif rate < -0.02:
                    colors.append('red')    # 下降
                else:
                    colors.append('blue')   # 稳定
            
            # 绘制条形图
            plt.barh(
                range(len(top_students_sorted)), 
                top_students_sorted['growth_rate'],
                color=colors,
                alpha=0.7
            )
            
            # 添加学生ID标签
            for i, (_, student) in enumerate(top_students_sorted.iterrows()):
                plt.text(
                    student['growth_rate'] + (0.01 if student['growth_rate'] >= 0 else -0.04), 
                    i, 
                    f"{student['student_id'][-4:]}...",  # 显示ID后4位
                    verticalalignment='center',
                    fontsize=8
                )
            
            # 设置图表标题和标签
            plt.title('极高起点学生成长率分布', fontsize=15)
            plt.xlabel('成长率（正值=上升，负值=下降）', fontsize=12)
            plt.ylabel('学生（按成长率排序）', fontsize=12)
            plt.axvline(x=0, color='gray', linestyle='--', alpha=0.7)  # 添加零线
            plt.grid(True, alpha=0.3)
            
            # 保存图表
            top_students_path = os.path.join(output_dir, 'top_students_growth.png')
            plt.tight_layout()
            plt.savefig(top_students_path, dpi=300)
            plt.close()
            self.stdout.write(f"- 极高起点学生成长分析已保存至: {top_students_path}")
            
            # 4. 绘制极高起点学生的轨迹图
            # 选择最具代表性的几个学生（最大上升、最大下降和中间值）
            if len(top_students) >= 3:
                best_growth = top_students.nlargest(1, 'growth_rate').iloc[0]
                worst_growth = top_students.nsmallest(1, 'growth_rate').iloc[0]
                middle_growth = top_students.iloc[len(top_students)//2]
                selected_students = [best_growth, middle_growth, worst_growth]
                
                plt.figure(figsize=(12, 6))
                
                for i, student in enumerate(selected_students):
                    student_id = student['student_id']
                    student_data = raw_data[raw_data['student_id'] == student_id]
                    student_data = student_data.sort_values('exam_order')
                    
                    label = (f"最大上升: {student['growth_rate']:.2f}" if i == 0 else
                             f"中等变化: {student['growth_rate']:.2f}" if i == 1 else
                             f"最大下降: {student['growth_rate']:.2f}")
                    
                    plt.plot(
                        student_data['exam_order'],
                        student_data['standard_score'],
                        'o-',
                        label=f"{label} (ID:{student_id[-4:]}...)",
                        linewidth=2,
                        markersize=8
                    )
                
                plt.title('极高起点学生典型轨迹对比', fontsize=15)
                plt.xlabel('考试序号', fontsize=12)
                plt.ylabel('分数', fontsize=12)
                plt.legend(loc='best')
                plt.grid(True, alpha=0.3)
                
                # 保存图表
                trajectories_path = os.path.join(output_dir, 'top_students_trajectories.png')
                plt.tight_layout()
                plt.savefig(trajectories_path, dpi=300)
                plt.close()
                self.stdout.write(f"- 极高起点学生轨迹对比已保存至: {trajectories_path}")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"- 极高起点学生分析失败: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())

    def _analyze_student_layers(self, features, raw_data, output_dir):
        """
        分析学生分层特征和变化
        
        Args:
            features: 聚类特征数据
            raw_data: 原始考试数据
            output_dir: 输出目录
        """
        
        self.stdout.write("- 开始学生分层分析...")
        
        # 按起点水平分层
        level_bins = [-np.inf, -1, -0.25, 0.25, 1, np.inf]
        level_labels = ['极低', '较低', '中等', '较高', '极高']
        
        features['start_level_category'] = pd.cut(
            features['start_level'], 
            bins=level_bins, 
            labels=level_labels
        )
        
        # 按成长率分层
        growth_bins = [-np.inf, -0.1, -0.02, 0.02, 0.1, np.inf]
        growth_labels = ['大幅下降', '小幅下降', '稳定', '小幅上升', '大幅上升']
        
        features['growth_category'] = pd.cut(
            features['growth_rate'], 
            bins=growth_bins, 
            labels=growth_labels
        )
        
        # 1. 分析每个起点层级的学生分布
        level_stats = features['start_level_category'].value_counts().sort_index()
        
        # 输出分层统计
        self.stdout.write("- 学生起点分层统计:")
        for level, count in level_stats.items():
            percentage = count / len(features) * 100
            self.stdout.write(f"  * {level}起点: {count}人 ({percentage:.1f}%)")
        
        # 2. 分析各层级学生的成长情况
        layer_growth = pd.crosstab(
            features['start_level_category'], 
            features['growth_category'], 
            normalize='index'
        ) * 100
        
        # 添加调试信息，检查层级分布
        self.stdout.write("\n- 学生层级分布检查:")
        self.stdout.write(f"层级标签: {level_labels}")
        self.stdout.write(f"层级分箱: {level_bins}")
        self.stdout.write(f"层级统计: {features['start_level_category'].value_counts().to_dict()}")
        self.stdout.write(f"层级唯一值: {features['start_level_category'].unique().tolist()}")
        
        # 确保所有层级都在交叉表中
        for level in level_labels:
            if level not in layer_growth.index:
                self.stdout.write(f"警告: '{level}'层级在交叉表中缺失")
                # 可以添加一行零值数据以确保所有层级都存在
                empty_row = pd.Series(0, index=layer_growth.columns)
                layer_growth.loc[level] = empty_row
        
        # 确保交叉表按照定义的层级顺序排序
        layer_growth = layer_growth.reindex(level_labels)
        
        self.stdout.write("\n- 各层级学生成长率分布(修正后):")
        self.stdout.write(f"{layer_growth}")
        
        # 3. 导出交叉表
        cross_table_path = os.path.join(output_dir, 'student_layer_growth.csv')
        layer_growth.to_csv(cross_table_path)
        
        # 4. 可视化各层级学生的成长情况
        self._visualize_layer_growth(features, layer_growth, raw_data, output_dir)
        
        # 转换为前端期望的格式
        layer_growth_dict = {}
        for level in layer_growth.index:
            for trend in layer_growth.columns:
                key = f"{level}，{trend}型"
                layer_growth_dict[key] = float(layer_growth.loc[level, trend])
        
        # 保存转换后的数据
        growth_dict_path = os.path.join(output_dir, 'student_layer_growth_dict.json')
        with open(growth_dict_path, 'w', encoding='utf-8') as f:
            json.dump(layer_growth_dict, f, ensure_ascii=False, indent=2)
        
        self.stdout.write(f"- 分层成长键值对已保存至: {growth_dict_path}")
        
        # 修改ValueAddedModelAnalyzer.analyze方法，确保返回这个字典而不是交叉表
        
        return features, layer_growth_dict  # 返回转换后的字典

    def _visualize_layer_growth(self, features, layer_growth, raw_data, output_dir):
        """可视化各层级学生成长情况"""
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # 设置绘图样式
        sns.set_style("whitegrid")
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 1. 热力图 - 显示各层级学生成长率分布
        plt.figure(figsize=(12, 8))
        sns.heatmap(
            layer_growth, 
            annot=True, 
            fmt='.1f', 
            cmap='RdYlGn', 
            linewidths=0.5
        )
        plt.title('不同起点层级学生的成长情况(%)', fontsize=15)
        plt.tight_layout()
        heatmap_path = os.path.join(output_dir, 'layer_growth_heatmap.png')
        plt.savefig(heatmap_path, dpi=300)
        plt.close()
        
        # 2. 各层级典型轨迹对比图
        plt.figure(figsize=(15, 10))
        
        # 为每个起点层级选择3个典型学生
        level_categories = features['start_level_category'].unique()
        
        for i, level in enumerate(sorted(level_categories)):
            # 创建子图
            plt.subplot(3, 2, i+1)
            
            # 获取该层级的学生
            level_students = features[features['start_level_category'] == level]
            
            # 选择三种成长类型的代表性学生
            for growth in ['大幅上升', '稳定', '大幅下降']:
                students = level_students[level_students['growth_category'] == growth]
                if len(students) > 0:
                    # 选择一个代表学生
                    student = students.iloc[len(students)//2]
                    student_id = student['student_id']
                    
                    # 获取学生考试轨迹
                    student_data = raw_data[raw_data['student_id'] == student_id]
                    student_data = student_data.sort_values('exam_order')
                    
                    # 绘制轨迹
                    plt.plot(
                        student_data['exam_order'],
                        student_data['standard_score'],
                        'o-',
                        label=f"{growth} (增长率:{student['growth_rate']:.2f})",
                        linewidth=2
                    )
            
            plt.title(f'{level}起点学生的典型轨迹', fontsize=12)
            plt.xlabel('考试序号')
            plt.ylabel('标准化分数')
            plt.grid(True, alpha=0.3)
            plt.legend(loc='best')
        
        plt.tight_layout()
        trajectories_path = os.path.join(output_dir, 'layer_typical_trajectories.png')
        plt.savefig(trajectories_path, dpi=300)
        plt.close()
        
        self.stdout.write(f"- 分层分析热力图已保存至: {heatmap_path}")
        self.stdout.write(f"- 分层典型轨迹已保存至: {trajectories_path}")

    def update_task_progress(self, task_id, progress, status='running', error=None):
        """更新分析任务进度"""
        if not task_id:
            return
            
        try:
            from django.apps import apps
            AnalysisTask = apps.get_model('edu_insights', 'AnalysisTask')
            task = AnalysisTask.objects.get(task_id=task_id)
                
            # 更新任务状态
            task.progress = progress
            if status:
                task.status = status
            if error:
                task.error = error
            task.save()
            self.stdout.write(f"更新任务进度: {progress}%")
        except Exception as e:
            self.stderr.write(f"更新任务进度失败: {str(e)}")