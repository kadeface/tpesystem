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
"""

import os
import time
import logging
import pandas as pd
from django.core.management.base import BaseCommand
#from core.management.commands.education_data_provider import EducationDataProvider
from core.value_added_models import (
    TVAMValueAddedModel,
    BayesianValueAddedModel,
    FrequentistValueAddedModel,
    FixedEffectsValueAddedModel,
    RandomEffectsValueAddedModel,
    ValueAddedDataProcessor,
    ValueAddedVisualizer,
    NonlinearStudentPotentialEvaluator
)

logger = logging.getLogger(__name__)

# 可用模型映射
MODEL_MAPPING = {
    'tvam': TVAMValueAddedModel,
    'bayesian': BayesianValueAddedModel,
    'frequentist': FrequentistValueAddedModel,
    'fixed': FixedEffectsValueAddedModel,
    'random': RandomEffectsValueAddedModel,
    'nonlinear_potential': 'special_handler'
}

class Command(BaseCommand):
    """测试增值分析模型的Django命令"""
    
    help = '使用不同模型进行增值分析或学生潜力评估并比较结果'
    
    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument('--exams', nargs='+', type=str, required=True, help='考试ID列表')
        parser.add_argument('--subject', type=str, required=True, help='学科ID')
        parser.add_argument('--model', nargs='+', default=['tvam'], help='要测试的模型，可选: tvam, bayesian, frequentist, fixed, random, nonlinear_potential')
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
    
    def handle(self, *args, **options):
        """命令处理入口"""
        try:
            # 配置matplotlib，抑制不必要的输出
            import matplotlib as mpl
            # 设置matplotlib日志级别 - 修复写法
            mpl.set_loglevel('WARNING')  # 正确的方法
            
            # 禁用字体缓存更新
            mpl.rcParams['font.family'] = 'sans-serif'
            
            # 设置后端，避免可能的warning
            mpl.use('Agg')  # 使用非交互式后端
            
            # 其他更严格的日志抑制
            import logging
            logging.getLogger('matplotlib').setLevel(logging.WARNING)
            logging.getLogger('PIL').setLevel(logging.WARNING)
            
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
            processor = ValueAddedDataProcessor()
            processor.load_data(exam_ids=options['exams'], subject_id=options['subject'], 
                               baseline_exam=options.get('baseline'))
            
            # 显示基准考试信息
            if hasattr(processor, 'baseline_exams'):
                self.stdout.write(self.style.SUCCESS(f"- 基准考试: {', '.join(processor.baseline_exams)}"))
            
            self.stdout.write(f"- 获取了{len(processor.data)}条原始数据")
            
            # 2. 创建输出目录
            output_dir = options['output']
            os.makedirs(output_dir, exist_ok=True)
            
            # 存储各模型结果
            results = {}
            
            # 3. 测试每个指定的模型 - 每个模型负责自己的数据准备
            self.stdout.write(self.style.SUCCESS("2. 执行模型分析"))
            for model_name in options['model']:
                self.stdout.write(f"- 使用{model_name}模型进行分析")
                
                # 特殊处理非线性潜力评估模型
                if model_name == 'nonlinear_potential':
                    self._handle_nonlinear_potential(processor, options, output_dir)
                    continue
                
                # 特殊处理TVAM模型
                if model_name == 'tvam':
                    self._handle_tvam_model(processor, options, output_dir)
                    continue
                
                try:
                    # 获取模型类
                    ModelClass = MODEL_MAPPING[model_name]
                    
                    # 构建模型参数
                    model_kwargs = {
                        'data': processor.data,
                        'covariates': options['control'],
                        'use_cohort': options['cohort']
                    }
                    
                    # TVAM模型需要entity_type参数
                    if model_name == 'tvam':
                        model_kwargs['entity_type'] = options['entity']
                    
                    # 实例化模型
                    model = ModelClass(**model_kwargs)
                    
                    # 拟合模型
                    fit_start = time.time()
                    model.fit()
                    fit_time = time.time() - fit_start
                    
                    # 计算增值效应
                    value_added = model.calculate_value_added()
                    
                    # 保存结果
                    model_output_dir = os.path.join(output_dir, model_name)
                    os.makedirs(model_output_dir, exist_ok=True)
                    
                    saved_paths = model.save_results(model_output_dir)
                    
                    # 可视化和结果导出
                    visualizer = ValueAddedVisualizer(value_added, model_name=model_name)
                    try:
                        vis_paths = visualizer.save_complete_results(model_output_dir, model)
                        
                        # 输出Excel报告路径
                        if 'excel_report' in vis_paths:
                            self.stdout.write(f"- Excel报告: {vis_paths['excel_report']}")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"- 导出Excel报告失败: {str(e)}"))
                        # 降级为基本可视化
                        vis_paths = visualizer.visualize(model_output_dir)
                    
                    # 存储结果统计
                    results[model_name] = {
                        'fit_time': fit_time,
                        'metrics': getattr(model, 'metrics', {}),
                        'value_added': value_added
                    }
                    
                    self.stdout.write(self.style.SUCCESS(f"- {model_name}模型分析完成，用时: {fit_time:.2f}秒"))
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"- {model_name}模型分析失败: {str(e)}"))
                    logger.exception(f"{model_name}模型分析出错")
            
            # 5. 比较不同模型结果(如果测试了多个模型)
            if len(results) > 1:
                self.stdout.write(self.style.SUCCESS("5. 比较模型结果"))
                
                # 创建比较表格
                comparison = pd.DataFrame({
                    'model': [],
                    'fit_time': [],
                    'r_squared': [],
                    'entity_count': [],
                    'mean_effect': [],
                    'effect_range': []
                })
                
                # 填充比较数据
                for model_name, result in results.items():
                    # 提取增值效应
                    entity_key = f"{options['entity']}s" if options['entity'] == 'school' else 'classes'
                    if entity_key in result['value_added'] and not result['value_added'][entity_key].empty:
                        effects_df = result['value_added'][entity_key]
                        
                        row = {
                            'model': model_name,
                            'fit_time': result['fit_time'],
                            'r_squared': result['metrics'].get('r_squared', 'N/A'),
                            'entity_count': len(effects_df),
                            'mean_effect': effects_df['mean'].mean(),
                            'effect_range': effects_df['mean'].max() - effects_df['mean'].min()
                        }
                        comparison = comparison.append(row, ignore_index=True)
                
                # 保存比较结果
                comparison_path = os.path.join(output_dir, 'model_comparison.csv')
                comparison.to_csv(comparison_path, index=False)
                self.stdout.write(f"- 模型比较结果已保存至 {comparison_path}")
                
                # 打印比较表格
                self.stdout.write("\n模型比较:")
                self.stdout.write(comparison.to_string())
            
            # 6. 完成
            total_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"\n测试完成！总用时: {total_time:.2f}秒"))
            self.stdout.write(f"结果保存在: {output_dir}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"发生错误: {str(e)}"))
            logger.exception("测试过程中发生错误")
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