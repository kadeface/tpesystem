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
    ValueAddedVisualizer
)

logger = logging.getLogger(__name__)

# 可用模型映射
MODEL_MAPPING = {
    'tvam': TVAMValueAddedModel,
    'bayesian': BayesianValueAddedModel,
    'frequentist': FrequentistValueAddedModel,
    'fixed': FixedEffectsValueAddedModel,
    'random': RandomEffectsValueAddedModel
}

class Command(BaseCommand):
    """测试增值分析模型的Django命令"""
    
    help = '使用不同模型进行增值分析并比较结果'
    
    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument('--exams', nargs='+', type=str, required=True, help='考试ID列表')
        parser.add_argument('--subject', type=str, required=True, help='学科ID')
        parser.add_argument('--model', nargs='+', choices=MODEL_MAPPING.keys(), default=['tvam'],
                           help='要测试的模型类型')
        parser.add_argument('--control', nargs='+', default=[], help='控制变量列表')
        parser.add_argument('--entity', choices=['school', 'class'], default='class', 
                           help='分析实体类型')
        parser.add_argument('--output', default='results/value_added/', help='输出目录')
        parser.add_argument('--sample', type=int, default=0, help='样本量(0=全部)')
        parser.add_argument('--verbose', action='store_true', help='显示详细日志')
        parser.add_argument('--cohort', action='store_true', 
                           help='使用学生队列进行跨年级增值分析')
        parser.add_argument('--baseline', type=str, help='指定基准考试ID')
    
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
            
            # 1. 直接使用数据处理器获取和处理数据
            self.stdout.write(self.style.SUCCESS("1. 获取和准备数据"))
            processor = ValueAddedDataProcessor()
            processor.load_data(exam_ids=options['exams'], subject_id=options['subject'], 
                               baseline_exam=options.get('baseline'))
            processor.prepare_model_data()
            
            # 显示基准考试信息
            if hasattr(processor, 'baseline_exams'):
                self.stdout.write(self.style.SUCCESS(f"- 基准考试: {', '.join(processor.baseline_exams)}"))
            
            self.stdout.write(f"- 准备了{len(processor.model_data)}条建模数据")
            
            # 2. 数据处理
            self.stdout.write(self.style.SUCCESS("2. 准备建模数据"))
            model_data = processor.prepare_model_data()

            # 验证数据是否满足所有指定模型的需求
            model_classes = [MODEL_MAPPING[model_name] for model_name in options['model']]
            processor.validate_for_models(model_classes)

            self.stdout.write(f"- 准备了{len(model_data)}条建模数据")
            
            # 3. 创建输出目录
            output_dir = options['output']
            os.makedirs(output_dir, exist_ok=True)
            
            # 存储各模型结果
            results = {}
            
            # 4. 测试每个指定的模型
            for model_name in options['model']:
                self.stdout.write(self.style.SUCCESS(f"4. 测试{model_name}模型"))
                
                try:
                    # 获取模型类
                    ModelClass = MODEL_MAPPING[model_name]
                    
                    # 构建模型参数
                    model_kwargs = {
                        'data': model_data,
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