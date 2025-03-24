"""
多层次线性模型(HLM)分析工具

该模块实现了全面的多层HLM分析，支持时间-学生-班级-学校四层嵌套结构，
可对教育数据进行逐层深入分析，探索不同层级的变异来源。

Args:
    --base-exam: 基线考试ID
    --current-exam: 当前考试ID
    --subject: 学科ID
    --exams: 多个考试ID列表，用逗号分隔
    --date-range: 考试日期范围
    --semester-range: 学期范围
    --min-observations: 每个学生的最小观测次数
    --time-window: 时间窗口限制(月)
    --school: 限制特定学校ID
    --steps: 指定执行步骤
    --diagnostics: 是否进行模型诊断
    --export: 导出结果
    --export-path: 指定导出结果路径

Returns:
    None: 结果通过标准输出和生成的图表/文件提供
    
Raises:
    ValueError: 当提供的参数无效或数据加载失败时
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.formula.api import mixedlm
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import warnings
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Score, Class, Student, Subject, ValueAddedEvaluation, School, Grade, Teacher, Exam, StudentHistory, Semester
import random
from functools import lru_cache
import logging

class Command(BaseCommand):
    """
    多层次线性模型分析管理命令
    
    Args:
        --base-exam: 基线考试ID
        --current-exam: 当前考试ID
        --subject: 学科ID
        --min-observations: 最小观测次数要求
        --time-window: 时间窗口限制(可选)
        --school: 限制特定学校(可选)
        --export: 导出结果(可选)
        --steps: 指定执行步骤(可选)
        --diagnostics: 是否进行模型诊断(可选)
        
    Returns:
        None: 结果通过标准输出和生成的图表/文件提供
    """
    
    help = '执行多层次线性模型(HLM)分析，探索时间-学生-班级-学校层的效应'

    def add_arguments(self, parser):
        """定义命令行参数"""
        # 基本参数
        parser.add_argument('--base-exam', type=str, help='基线考试ID')
        parser.add_argument('--current-exam', type=str, help='当前考试ID')
        parser.add_argument('--subject', type=str, required=True, help='学科ID')
        
        # 多次考试支持
        parser.add_argument('--exams', type=str, help='多个考试ID列表，用逗号分隔，例如: exam1,exam2,exam3')
        parser.add_argument('--date-range', type=str, help='考试日期范围, 格式: 2023-01-01,2023-12-31')
        parser.add_argument('--semester-range', type=str, help='学期范围, 格式: 2022-2023-1,2023-2024-2')
        
        # 数据筛选参数
        parser.add_argument('--student-range', type=str, help='学生年级范围, 例如: 2018-2021')
        parser.add_argument('--min-observations', type=int, default=2, help='每个学生的最小观测次数')
        parser.add_argument('--time-window', type=int, help='时间窗口限制(月)')
        parser.add_argument('--school', type=str, help='限制特定学校ID')
        
        # 分析控制参数
        parser.add_argument('--steps', type=str, help='要执行的分析步骤, 用逗号分隔')
        parser.add_argument('--diagnostics', action='store_true', help='执行模型诊断')
        parser.add_argument('--export', action='store_true', help='导出分析结果')
        parser.add_argument('--export-path', type=str, help='指定导出结果路径')
        
        # 添加数据处理选项
        parser.add_argument('--handle-single-class', action='store_true',
                            help='为单班级学校创建虚拟班级分组')
        parser.add_argument('--exclude-single-class-schools', action='store_true',
                            help='排除只有一个班级的学校')
        parser.add_argument('--use-main-grade-only', action='store_true',
                            help='仅使用主要年级的数据')
        parser.add_argument('--force-school-model', action='store_true',
                            help='强制执行学校层模型，即使数据结构不理想')

    def handle(self, *args, **options):
        """命令执行主函数"""
        self.options = options
        self.stdout.write("开始执行多层次线性模型分析...")
        
        # 提取参数
        subject_id = options['subject']
        base_exam_id = options.get('base_exam')
        current_exam_id = options.get('current_exam')
        exams_list = options.get('exams')
        date_range = options.get('date-range')
        semester_range = options.get('semester-range')
        min_observations = options.get('min_observations', 2)
        school_id = options.get('school')
        export = options.get('export', False)
        diagnostics = options.get('diagnostics', False)
        
        # 步骤控制
        steps = options.get('steps')
        if steps:
            steps = steps.split(',')
        
        # 1. 获取数据
        try:
            data = self._load_data(
                subject_id=subject_id, 
                base_exam_id=base_exam_id,
                current_exam_id=current_exam_id,
                exams_list=exams_list.split(',') if exams_list else None,
                date_range=date_range.split(',') if date_range else None,
                semester_range=semester_range.split(',') if semester_range else None,
                min_observations=min_observations, 
                school_id=school_id
            )
            self.stdout.write(self.style.SUCCESS(f"成功加载数据: {len(data)}条记录"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"数据加载失败: {str(e)}"))
            return
            
        # 2. 初始化分析器
        analyzer = LayeredHLM(
            data=data,
            outcome='standard_score',
            time_var='time_point',
            id_vars={
                'student': 'student_id',
                'class': 'class_id',
                'school': 'school_id'
            }
        )
        
        # 3. 执行分析
        try:
            analyzer.run_analysis(steps=steps)
            self.stdout.write(self.style.SUCCESS("分析完成"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"分析过程中出现错误: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            return
            
        # 4. 输出诊断信息
        if diagnostics:
            self._print_diagnostics(analyzer)
            
        # 5. 导出结果
        if export:
            self._export_results(analyzer, subject_id, base_exam_id, current_exam_id)
            
        self.stdout.write(self.style.SUCCESS("多层次HLM分析任务完成"))

    def _load_data(self, subject_id, base_exam_id=None, current_exam_id=None, 
                  exams_list=None, date_range=None, semester_range=None, 
                  min_observations=2, school_id=None):
        """
        加载并预处理分析数据
        
        Args:
            subject_id: 学科ID
            base_exam_id: 基线考试ID
            current_exam_id: 当前考试ID
            exams_list: 考试ID列表
            date_range: 考试日期范围
            semester_range: 学期范围
            min_observations: 最小观测次数
            school_id: 学校ID
        
        Returns:
            DataFrame: 处理后的分析数据
        """
        self.stdout.write("加载数据...")
        
        # 数据提取逻辑...
        # ...
        
        # 在处理数据之后，添加这段检查代码:
        self.stdout.write("\n数据结构检查:")
        
        # 检查年级分布
        grade_counts = data['current_grade__grade_name'].value_counts()
        self.stdout.write("年级分布:")
        for grade, count in grade_counts.items():
            self.stdout.write(f"  {grade}: {count}名学生")
        
        # 检查学校-班级结构
        school_class_counts = data.groupby('school_id')['class_id'].nunique()
        self.stdout.write("\n学校-班级结构:")
        self.stdout.write(f"  平均每所学校的班级数: {school_class_counts.mean():.2f}")
        self.stdout.write(f"  最少班级数: {school_class_counts.min()}, 最多班级数: {school_class_counts.max()}")
        
        # 标记和处理异常的数据结构
        problem_schools = school_class_counts[school_class_counts < 2].index.tolist()
        if problem_schools:
            self.stdout.write(f"\n警告: 发现{len(problem_schools)}所学校只有1个班级")
            self.stdout.write("这可能导致学校层和班级层效应无法区分")
            
            # 选项1: 为这些学校创建虚拟班级分组
            if self.options.get('handle_single_class', False):
                self.stdout.write("处理方法: 为单班级学校创建虚拟班级分组")
                
                # 为每个只有一个班级的学校，创建2个虚拟班级
                for school_id in problem_schools:
                    school_students = data[data['school_id'] == school_id]
                    unique_class = school_students['class_id'].iloc[0]
                    
                    # 随机将学生分配到两个虚拟班级
                    student_ids = school_students['student_id'].unique()
                    split_point = len(student_ids) // 2
                    
                    # 创建班级映射
                    virtual_class_map = {}
                    for i, sid in enumerate(student_ids):
                        if i < split_point:
                            virtual_class_map[sid] = f"{unique_class}_A"
                        else:
                            virtual_class_map[sid] = f"{unique_class}_B"
                    
                    # 应用虚拟班级
                    data.loc[data['school_id'] == school_id, 'class_id'] = data.loc[
                        data['school_id'] == school_id, 'student_id'
                    ].map(virtual_class_map)
                    
                self.stdout.write("虚拟班级分组已创建")
            
            # 选项2: 排除这些学校
            elif self.options.get('exclude_single_class_schools', False):
                self.stdout.write("处理方法: 排除单班级学校")
                data = data[~data['school_id'].isin(problem_schools)]
                self.stdout.write(f"排除后数据量: {len(data)}条记录")
        
        # 检查年级不平衡问题
        if len(grade_counts) > 1:
            grade_ratio = grade_counts.max() / grade_counts.min()
            if grade_ratio > 10:  # 如果最大年级是最小年级的10倍以上
                self.stdout.write(f"\n警告: 年级分布极不平衡，比例为{grade_ratio:.1f}:1")
                
                # 选项: 仅保留主要年级
                if self.options.get('use_main_grade_only', False):
                    main_grade = grade_counts.idxmax()
                    self.stdout.write(f"处理方法: 仅使用主要年级({main_grade})的数据")
                    data = data[data['current_grade__grade_name'] == main_grade]
                    self.stdout.write(f"筛选后数据量: {len(data)}条记录")
        
        # 再次更新学校和班级统计
        school_count = data['school_id'].nunique()
        class_count = data['class_id'].nunique()
        self.stdout.write(f"\n处理后学校数量: {school_count}, 班级数量: {class_count}")
        self.stdout.write(f"处理后学生数量: {data['student_id'].nunique()}")
        
        return data

    def _print_diagnostics(self, analyzer):
        """输出模型诊断信息"""
        self.stdout.write("\n模型诊断信息:")
        
        if hasattr(analyzer, 'models') and 'null' in analyzer.models:
            null_model = analyzer.models['null']
            self.stdout.write("空模型摘要:")
            self.stdout.write(str(null_model.summary()))
            
        if hasattr(analyzer, 'diagnostics') and 'null_icc' in analyzer.diagnostics:
            icc = analyzer.diagnostics['null_icc']
            self.stdout.write("\nICC值:")
            for level, value in icc.items():
                self.stdout.write(f"  {level}: {value:.4f}")
                
        if hasattr(analyzer, 'results') and 'class_effects' in analyzer.results:
            effects = analyzer.results['class_effects']
            self.stdout.write("\n班级效应分布:")
            self.stdout.write(f"  最小值: {effects['effect'].min():.4f}")
            self.stdout.write(f"  最大值: {effects['effect'].max():.4f}")
            self.stdout.write(f"  均值: {effects['effect'].mean():.4f}")
            self.stdout.write(f"  标准差: {effects['effect'].std():.4f}")

    def _export_results(self, analyzer, subject_id, base_exam_id=None, current_exam_id=None):
        """导出分析结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_path = self.options.get('export_path') or '.'
        
        # 创建导出文件名
        filename_base = f"HLM分析_{subject_id}"
        if base_exam_id and current_exam_id:
            filename_base += f"_{base_exam_id}至{current_exam_id}"
        filename_base += f"_{timestamp}"
        
        # 确保导出目录存在
        os.makedirs(export_path, exist_ok=True)
        
        # 导出结果摘要
        if 'summary' in analyzer.results:
            summary_file = os.path.join(export_path, f"{filename_base}_摘要.txt")
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write("多层次线性模型分析结果摘要\n")
                f.write("=" * 50 + "\n\n")
                
                summary = analyzer.results['summary']
                
                f.write(f"数据概况:\n")
                f.write(f"  观测总数: {summary['data_summary']['observations']}\n")
                f.write(f"  学生数量: {summary['data_summary']['students']}\n")
                f.write(f"  时间点数: {summary['data_summary']['time_points']}\n\n")
                
                if 'variance_components' in summary:
                    f.write("方差分解结果:\n")
                    for level, icc in summary['variance_components'].items():
                        f.write(f"  {level.capitalize()}层贡献: {icc:.1%}\n")
                
                # 添加其他结果...
            
            self.stdout.write(f"结果摘要已导出至: {summary_file}")
        
        # 导出效应数据
        for effect_type in ['class_effects', 'student_effects', 'school_effects']:
            if effect_type in analyzer.results:
                effects_df = analyzer.results[effect_type]
                
                # 对于学校效应，添加置信区间列说明
                if effect_type == 'school_effects' and 'ci_lower_95' in effects_df.columns:
                    # 创建更友好的置信区间显示
                    effects_df['置信区间(95%)'] = effects_df.apply(
                        lambda row: f"[{row['ci_lower_95']:.2f}, {row['ci_upper_95']:.2f}]", 
                        axis=1
                    )
                    
                    # 重命名列以提高可读性
                    column_map = {
                        'school_id': '学校ID',
                        'school_name': '学校名称',
                        'effect': '效应值',
                        'standard_error': '标准误',
                        'value_added': '增值分数',
                        'rating': '评级'
                    }
                    effects_df = effects_df.rename(columns=column_map)
                
                effects_file = os.path.join(export_path, f"{filename_base}_{effect_type}.xlsx")
                effects_df.to_excel(effects_file, index=False)
                self.stdout.write(f"{effect_type}已导出至: {effects_file}")


# LayeredHLM类定义：保持原有实现
class LayeredHLM:
    """
    多层次线性模型(HLM)分析工具
    
    实现时间-学生-班级-学校四层嵌套结构的线性混合效应模型分析。
    
    Args:
        data: 包含多层嵌套数据的DataFrame
        outcome: 结果变量名称
        time_var: 时间变量名称
        id_vars: 包含各层ID的字典，如{'student':'student_id', 'class':'class_id'}
        
    Returns:
        LayeredHLM实例，包含各层分析结果
    """
    
    def __init__(self, data, outcome='standard_score', time_var='time_point', 
                 id_vars=None, subject=None, options=None):
        """
        初始化分层分析器。
        
        Args:
            data: 数据框
            outcome: 结果变量名称
            time_var: 时间变量名称
            id_vars: 各层ID变量字典
        """
        self.data = data
        self.outcome = outcome
        self.time_var = time_var
        self.id_vars = id_vars or {
            'student': 'student_id',
            'class': 'class_id',  # 现在使用复合ID
            'school': 'school_id'
        }
        self.models = {}
        self.diagnostics = {}
        self.results = {}
        
        # 预处理：确保数据中有必要的变量
        self._preprocess_data()

    def _preprocess_data(self):
        """预处理数据，确保符合分析要求"""
        # 中心化处理
        self.data[f'{self.time_var}_centered'] = (
            self.data[self.time_var] - self.data[self.time_var].mean()
        )
        
        # 确保基线成绩变量存在
        if 'base_score' in self.data.columns:
            self.data['base_score_centered'] = (
                self.data['base_score'] - self.data['base_score'].mean()
            )
        
        # 创建班级-学校复合ID
        if self.id_vars['class'] in self.data.columns and self.id_vars['school'] in self.data.columns:
            self.data['class_school'] = (
                self.data[self.id_vars['class']].astype(str) + "_" + 
                self.data[self.id_vars['school']].astype(str)
            )

    def run_analysis(self, steps=None):
        """
        执行完整的分层分析流程
        
        Args:
            steps: 要执行的分析步骤列表，默认执行所有步骤
        """
        default_steps = [
            'quality_check', 'null_model', 'time_model', 
            'student_model', 'class_model', 'school_model',
            'interaction_analysis', 'visualization'
        ]
        steps = steps or default_steps
        
        step_methods = {
            'quality_check': self._quality_check,
            'null_model': self._null_model,
            'time_model': self._time_model,
            'student_model': self._student_model,
            'class_model': self._class_model,
            'school_model': self._school_model,
            'interaction_analysis': self._interaction_analysis,
            'visualization': self._visualize_results
        }
        
        for step in steps:
            if step in step_methods:
                print(f"\n执行分析步骤: {step}")
                step_methods[step]()
            else:
                warnings.warn(f"未知分析步骤: {step}")
                
        # 汇总结果
        self._summarize_results()
        
        return self.results

    def _quality_check(self):
        """
        数据质量检查和层级结构验证
        
        检查数据的分层结构和各层样本量。
        """
        # 时间层检查
        student_id = self.id_vars['student']
        time_stats = self.data.groupby(student_id)[self.time_var].agg(['count', 'min', 'max'])
        
        self.diagnostics['time_layer'] = {
            'obs_count': len(self.data),
            'avg_observations': time_stats['count'].mean(),
            'complete_cases': sum(time_stats['count'] >= 2),
            'time_range': [time_stats['min'].min(), time_stats['max'].max()]
        }
        
        # 学生层检查
        student_count = self.data[student_id].nunique()
        self.diagnostics['student_layer'] = {
            'count': student_count
        }
        
        # 班级层检查
        if self.id_vars['class'] in self.data.columns:
            class_id = self.id_vars['class']
            class_count = self.data[class_id].nunique()
            students_per_class = self.data.groupby(class_id)[student_id].nunique()
            
            self.diagnostics['class_layer'] = {
                'count': class_count,
                'avg_size': students_per_class.mean(),
                'min_size': students_per_class.min(),
                'max_size': students_per_class.max()
            }
        
        # 学校层检查
        if self.id_vars['school'] in self.data.columns:
            school_id = self.id_vars['school']
            school_count = self.data[school_id].nunique()
            classes_per_school = (self.data.groupby(school_id)[class_id].nunique() 
                                 if self.id_vars['class'] in self.data.columns else None)
            
            self.diagnostics['school_layer'] = {
                'count': school_count,
                'avg_size': classes_per_school.mean() if classes_per_school is not None else None
            }
        
        # 输出诊断报告
        print(f"数据质量检查结果:")
        print(f"总观测数: {self.diagnostics['time_layer']['obs_count']}")
        print(f"学生数: {self.diagnostics['student_layer']['count']}")
        print(f"平均每个学生的观测数: {self.diagnostics['time_layer']['avg_observations']:.2f}")
        
        if 'class_layer' in self.diagnostics:
            print(f"班级数: {self.diagnostics['class_layer']['count']}")
            print(f"平均班级规模: {self.diagnostics['class_layer']['avg_size']:.2f}人")
        
        if 'school_layer' in self.diagnostics:
            print(f"学校数: {self.diagnostics['school_layer']['count']}")
            if self.diagnostics['school_layer']['avg_size']:
                print(f"平均每个学校的班级数: {self.diagnostics['school_layer']['avg_size']:.2f}")
                
        # 数据充分性检查
        has_enough_levels = (
            student_count >= 30 and
            self.diagnostics.get('class_layer', {}).get('count', 0) >= 10 and
            self.diagnostics.get('school_layer', {}).get('count', 0) >= 5
        )
        
        if not has_enough_levels:
            warnings.warn("数据层级样本量可能不足，HLM模型结果可能不稳定")

    def _null_model(self):
        """构建空模型（无预测变量的基准模型）"""
        print("执行分析步骤: null_model")
        
        try:
            # 打印关键信息
            print("\n检查分组变量:")
            print(f"学生ID列名: {self.id_vars['student']}")
            print(f"班级ID列名: {self.id_vars['class']}")
            print(f"学校ID列名: {self.id_vars['school']}")
            
            # 打印唯一值计数
            print(f"学生ID唯一值: {self.data[self.id_vars['student']].nunique()}")
            print(f"班级ID唯一值: {self.data[self.id_vars['class']].nunique()}")
            print(f"学校ID唯一值: {self.data[self.id_vars['school']].nunique()}")
            
            # 检查嵌套关系
            print("\n层级关系检查:")
            student_class_counts = self.data.groupby(self.id_vars['student'])[self.id_vars['class']].nunique()
            print(f"每个学生的班级数: 最小={student_class_counts.min()}, 最大={student_class_counts.max()}")
            
            # 使用更简单的模型
            print("\n尝试简化模型构建:")
            formula = f"{self.outcome} ~ 1"
            
            # 仅学生层随机效应
            student_model = mixedlm(
                formula,
                self.data,
                groups=self.data[self.id_vars['student']]
            )
            print("拟合学生层模型...")
            self.models['student_only'] = student_model.fit(reml=True)
            print(self.models['student_only'].summary())
            
            # 完整模型
            print("\n尝试构建完整模型:")
            full_model = mixedlm(
                formula,
                self.data,
                groups=self.data[self.id_vars['school']],
                vc_formula={
                    "class": f"0 + C({self.id_vars['class']})",
                    "student": f"0 + C({self.id_vars['student']})"
                }
            )
            
            print("拟合完整模型...")
            self.models['null'] = full_model.fit(reml=True)
            
            # 提取方差成分
            var_components = self._variance_decomposition(self.models['null'])
            print("\n方差成分提取结果:")
            for k, v in var_components.items():
                print(f"  {k}: {v:.4f}")
            
            return True
        except Exception as e:
            print(f"空模型构建失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False

    def _time_model(self):
        """
        时间模型（加入时间固定效应）
        
        检验整体的时间效应，即学生成绩随时间的总体变化趋势。
        """
        # 公式：outcome ~ time_centered
        time_formula = f"{self.outcome} ~ {self.time_var}_centered"
        student_id = self.id_vars['student']
        
        try:
            # 选择与空模型相同的结构
            if 'null' in self.models and isinstance(self.models['null'], sm.regression.linear_model.RegressionResultsWrapper):
                if ('class_school' in self.data.columns and 
                    self.id_vars['school'] in self.data.columns):
                    
                    school_id = self.id_vars['school']
                    
                    self.models['time'] = mixedlm(
                        time_formula, 
                        self.data,
                        groups=self.data[school_id],
                        vc_formula={
                            "class": "0 + C(class_school)",
                            "student": f"0 + C({student_id})"
                        }
                    ).fit(reml=True)
                    
                else:
                    self.models['time'] = mixedlm(
                        time_formula, 
                        self.data,
                        groups=self.data[student_id],
                        re_formula="1"
                    ).fit(reml=True)
                
                # 提取时间效应
                time_effect = self.models['time'].fe_params[f'{self.time_var}_centered']
                time_p_value = self.models['time'].pvalues[f'{self.time_var}_centered']
                
                self.diagnostics['time_effect'] = {
                    'coefficient': time_effect,
                    'p_value': time_p_value,
                    'significant': time_p_value < 0.05
                }
                
                # 模型改进检验（与空模型比较）
                ll_null = self.models['null'].llf
                ll_time = self.models['time'].llf
                lr_stat = 2 * (ll_time - ll_null)
                lr_p_value = stats.chi2.sf(lr_stat, 1)  # 自由度为1
                
                self.diagnostics['time_model_improvement'] = {
                    'deviance_reduction': lr_stat,
                    'p_value': lr_p_value,
                    'significant': lr_p_value < 0.05
                }
                
                # 输出结果
                print(f"\n时间效应分析结果:")
                print(f"时间固定效应系数: {time_effect:.4f}")
                print(f"p值: {time_p_value:.4f} {'(显著)' if time_p_value < 0.05 else '(不显著)'}")
                print(f"模型改进: χ²({1}) = {lr_stat:.2f}, p = {lr_p_value:.4f}")
                
                # 方差解释量变化
                var_null = self._variance_decomposition(self.models['null'])
                var_time = self._variance_decomposition(self.models['time'])
                
                residual_var_change = (var_null['residual_var'] - var_time['residual_var']) / var_null['residual_var']
                print(f"时间效应解释了 {residual_var_change*100:.2f}% 的残差方差")
                
            else:
                warnings.warn("需要先运行空模型才能进行时间效应分析")
                
        except Exception as e:
            print(f"时间模型构建失败: {str(e)}")
            warnings.warn("时间模型构建失败，请检查数据结构和模型设定")

    def _student_model(self):
        """
        学生随机效应模型
        
        添加学生随机斜率，检验学生成长速率的个体差异。
        """
        # 公式：outcome ~ time_centered + (1 + time_centered | student_id)
        student_id = self.id_vars['student']
        student_formula = f"{self.outcome} ~ {self.time_var}_centered"
        
        try:
            if 'time' in self.models:
                # 添加学生随机斜率
                self.models['student'] = mixedlm(
                    student_formula, 
                    self.data,
                    groups=self.data[student_id],
                    re_formula=f"1 + {self.time_var}_centered"  # 随机截距和随机斜率
                ).fit(reml=True)
                
                # 提取学生随机效应
                random_effects = self.models['student'].random_effects
                student_intercepts = [re[0] for re in random_effects.values()]
                student_slopes = [re[1] if len(re) > 1 else 0 for re in random_effects.values()]
                
                self.diagnostics['student_effects'] = {
                    'intercept_variance': np.var(student_intercepts),
                    'slope_variance': np.var(student_slopes),
                    'intercept_slope_corr': np.corrcoef(student_intercepts, student_slopes)[0, 1]
                }
                
                # 创建学生效应DataFrame
                student_effects_df = pd.DataFrame({
                    'student_id': list(random_effects.keys()),
                    'intercept': student_intercepts,
                    'slope': student_slopes
                })
                
                # 根据斜率识别高成长和低成长学生
                slope_percentiles = np.percentile(student_slopes, [25, 75])
                student_effects_df['growth_group'] = pd.cut(
                    student_effects_df['slope'],
                    bins=[-np.inf, slope_percentiles[0], slope_percentiles[1], np.inf],
                    labels=['低成长', '中等成长', '高成长']
                )
                
                # 保存学生效应
                self.results['student_effects'] = student_effects_df
                
                # 输出结果
                print("\n学生随机效应分析结果:")
                print(f"学生起点差异(随机截距方差): {self.diagnostics['student_effects']['intercept_variance']:.4f}")
                print(f"学生成长速率差异(随机斜率方差): {self.diagnostics['student_effects']['slope_variance']:.4f}")
                print(f"起点与成长速率相关性: {self.diagnostics['student_effects']['intercept_slope_corr']:.4f}")
                
                # 输出各成长组的学生人数
                growth_counts = student_effects_df['growth_group'].value_counts()
                for group, count in growth_counts.items():
                    print(f"{group}学生: {count}人 ({count/len(student_effects_df)*100:.1f}%)")
                
            else:
                warnings.warn("需要先运行时间模型才能进行学生随机效应分析")
                
        except Exception as e:
            print(f"学生模型构建失败: {str(e)}")
            warnings.warn("学生模型构建失败，请检查数据结构和模型设定")

    def _class_model(self):
        """
        班级层模型
        
        分析班级层面的随机效应，检验班级对学生成绩的影响。
        """
        if self.id_vars['class'] not in self.data.columns:
            print("数据中缺少班级信息，跳过班级层分析")
            return
            
        # 公式：outcome ~ time_centered + 班级层预测变量
        class_formula = f"{self.outcome} ~ {self.time_var}_centered"
        
        # 如果数据中有教学相关变量，可以添加到公式中
        # 例如：class_formula += " + teaching_method + class_size"
        
        try:
            student_id = self.id_vars['student']
            class_id = self.id_vars['class']
            
            # 构建班级-时间交互项
            if 'class_size' in self.data.columns:
                class_formula += " + class_size"
                
            # 添加班级随机效应
            self.models['class'] = mixedlm(
                class_formula,
                self.data,
                groups=self.data[class_id],
                re_formula="1",
                vc_formula={
                    "student": f"0 + C({student_id})"
                }
            ).fit(reml=True)
            
            # 提取班级方差成分
            var_components = self._variance_decomposition(self.models['class'])
            
            # 计算班级ICC
            class_icc = var_components.get('class_var', 0) / var_components['total_var']
            
            self.diagnostics['class_effects'] = {
                'class_var': var_components.get('class_var', 0),
                'class_icc': class_icc,
                'class_impact': class_icc * 100  # 班级因素对成绩的影响百分比
            }
            
            # 如果有添加班级预测变量，提取其系数
            if 'class_size' in self.data.columns:
                class_size_effect = self.models['class'].fe_params['class_size']
                class_size_p = self.models['class'].pvalues['class_size']
                
                self.diagnostics['class_effects']['class_size_effect'] = {
                    'coef': class_size_effect,
                    'p_value': class_size_p,
                    'significant': class_size_p < 0.05
                }
            
            # 计算班级残差（班级效应）
            class_random_effects = self.models['class'].random_effects
            
            class_effects_df = pd.DataFrame({
                'class_id': list(class_random_effects.keys()),
                'effect': [re.iloc[0] if hasattr(re, 'iloc') else re[0] for re in class_random_effects.values()]
            })
            
            # 班级效应标准化
            mean_effect = class_effects_df['effect'].mean()
            std_effect = class_effects_df['effect'].std()
            class_effects_df['value_added_t'] = 50 + 10 * (class_effects_df['effect'] - mean_effect) / std_effect
            
            # 班级评级
            class_effects_df['rating'] = pd.cut(
                class_effects_df['value_added_t'],
                bins=[0, 40, 45, 55, 60, 100],
                labels=['显著低于平均', '低于平均', '平均水平', '高于平均', '显著高于平均']
            )
            
            # 保存班级效应
            self.results['class_effects'] = class_effects_df
            
            # 输出结果
            print("\n班级层效应分析结果:")
            print(f"班级方差: {self.diagnostics['class_effects']['class_var']:.4f}")
            print(f"班级ICC: {class_icc:.4f} ({class_icc*100:.1f}%)")
            print(f"班级因素对学生成绩的影响: {self.diagnostics['class_effects']['class_impact']:.1f}%")
            
            if 'class_size_effect' in self.diagnostics['class_effects']:
                size_effect = self.diagnostics['class_effects']['class_size_effect']
                print(f"班级规模效应: {size_effect['coef']:.4f} (p={size_effect['p_value']:.4f})")
            
            # 输出各评级的班级数量
            rating_counts = class_effects_df['rating'].value_counts()
            for rating, count in rating_counts.items():
                print(f"{rating}班级: {count}个 ({count/len(class_effects_df)*100:.1f}%)")
                
        except Exception as e:
            print(f"班级模型构建失败: {str(e)}")
            warnings.warn("班级模型构建失败，请检查数据结构和模型设定")

    def _school_model(self):
        """构建学校层模型"""
        print("执行分析步骤: school_model")
        
        # 检查学校-班级结构是否合适于HLM分析
        school_class_counts = self.data.groupby(self.id_vars['school'])[self.id_vars['class']].nunique()
        single_class_schools = sum(school_class_counts == 1)
        
        if single_class_schools / len(school_class_counts) > 0.5:  # 如果超过50%的学校只有一个班级
            print("警告: 大多数学校只有一个班级，学校效应和班级效应可能无法可靠区分")
            print(f"单班级学校占比: {single_class_schools / len(school_class_counts):.1%}")
            
            # 添加选项允许用户决定是否继续
            if not getattr(self, 'force_school_model', False):
                print("跳过学校层模型。如需强制执行，请设置force_school_model=True")
                self.results['school_effects'] = pd.DataFrame(columns=['school_id', 'effect'])
                return False
            print("已设置强制执行学校层模型")
        
        # 检查是否有足够的学校数量
        if self.data[self.id_vars['school']].nunique() < 5:
            print(f"警告: 只有{self.data[self.id_vars['school']].nunique()}所学校，学校效应估计可能不稳定")
        
        # 继续执行原有的学校模型逻辑
        try:
            # 如果已有班级模型，在其基础上构建
            # 否则，基于时间模型构建
            base_model_key = 'class' if 'class' in self.models else 'time'
            
            if base_model_key not in self.models:
                print(f"无法构建学校模型：需要先运行{base_model_key}模型")
                warnings.warn(f"需要先运行{base_model_key}模型才能进行学校层分析")
                return False
            
            # 构建模型
            formula = f"{self.outcome} ~ {self.time_var}_centered"
            
            # 添加学校层预测变量（如果有）
            if 'school_predictors' in self.data.columns:
                formula += " + school_predictors"
            
            # 创建学校随机效应模型
            school_model = mixedlm(
                formula,
                self.data,
                groups=self.data[self.id_vars['school']],  # 学校层级分组
                vc_formula={
                    'class': f"0 + C({self.id_vars['class']})"
                }
            )
            
            # 拟合模型
            self.models['school'] = school_model.fit(reml=False)
            print("成功拟合学校层模型")
            
            # 提取学校方差成分
            var_components = self._variance_decomposition(self.models['school'])
            
            # 计算学校ICC
            total_var = var_components['total_var']
            school_var = var_components.get('school_var', 0)
            school_icc = school_var / total_var if total_var > 0 else 0
            
            self.diagnostics['school_effects'] = {
                'school_var': school_var,
                'school_icc': school_icc,
                'model_summary': str(self.models['school'].summary())
            }
            
            print(f"学校方差成分: {school_var:.4f} ({school_var/total_var*100:.1f}%)")
            
            # 提取学校随机效应
            re_results = self.models['school'].random_effects
            
            # 创建结果DataFrame
            school_effects = []
            
            for school_id, re in re_results.items():
                # 安全地获取随机效应和标准误
                effect = re.iloc[0] if hasattr(re, 'iloc') else re[0]  # 使用iloc安全获取
                
                # 安全地获取标准误
                try:
                    se = self.models['school'].random_effects_cov[school_id].iloc[0, 0] ** 0.5
                except (KeyError, AttributeError, IndexError):
                    # 如果无法获取正确的标准误，使用估计值
                    se = (school_var ** 0.5) / 10 if school_var > 0 else 0.1
                    print(f"无法获取学校{school_id}的标准误，使用估计值")
                
                # 计算95%置信区间
                ci_lower = effect - 1.96 * se
                ci_upper = effect + 1.96 * se
                
                # 基于随机效应计算增值得分(T分数)
                value_added_t = 50 + (effect / (school_var ** 0.5) * 10) if school_var > 0 else 50
                
                # 评级
                if value_added_t >= 60:
                    rating = "显著高于平均"
                elif value_added_t >= 55:
                    rating = "高于平均"
                elif value_added_t > 45:
                    rating = "平均水平"
                elif value_added_t >= 40:
                    rating = "低于平均"
                else:
                    rating = "显著低于平均"
                
                school_effects.append({
                    'school_id': school_id,
                    'effect': effect,
                    'standard_error': se,
                    'ci_lower_95': ci_lower, 
                    'ci_upper_95': ci_upper,
                    'value_added': value_added_t,
                    'rating': rating
                })
            
            # 如果没有结果，创建空的DataFrame
            if not school_effects:
                print("警告：学校效应为空")
                school_effects_df = pd.DataFrame(columns=[
                    'school_id', 'effect', 'standard_error', 
                    'ci_lower_95', 'ci_upper_95', 'value_added', 'rating'
                ])
            else:
                # 转换为DataFrame并排序
                school_effects_df = pd.DataFrame(school_effects)
                school_effects_df = school_effects_df.sort_values('effect', ascending=False)
            
            # 获取学校名称
            try:
                school_info = School.objects.filter(school_id__in=school_effects_df['school_id'])
                school_names = {school.school_id: school.school_name for school in school_info}
                
                # 添加学校名称
                school_effects_df['school_name'] = school_effects_df['school_id'].map(
                    lambda x: school_names.get(x, '未知学校')
                )
                
                # 调整列顺序，将学校名称放在前面
                cols = ['school_id', 'school_name', 'effect', 'standard_error', 
                        'ci_lower_95', 'ci_upper_95', 'value_added', 'rating']
                available_cols = [col for col in cols if col in school_effects_df.columns]
                school_effects_df = school_effects_df[available_cols]
            except Exception as e:
                print(f"获取学校名称失败: {str(e)}")
            
            # 保存结果
            self.results['school_effects'] = school_effects_df
            
            if not school_effects_df.empty:
                print(f"学校效应分析完成, 共{len(school_effects_df)}所学校")
                print(f"  效应范围: {school_effects_df['effect'].min():.2f} 至 {school_effects_df['effect'].max():.2f}")
                print(f"  增值得分范围: {school_effects_df['value_added'].min():.2f} 至 {school_effects_df['value_added'].max():.2f}")
            
            return True
            
        except Exception as e:
            print(f"学校模型构建失败: {str(e)}")
            import traceback
            print(traceback.format_exc())  # 添加这行来输出完整堆栈
            warnings.warn("学校模型构建失败，请检查数据结构和模型设定")
            return False

    def _interaction_analysis(self):
        """
        跨层交互作用分析
        
        检验不同层级变量之间的交互效应，如班级特征与学生成长的交互。
        """
        # 检查是否有足够的层级数据
        if (self.id_vars['class'] not in self.data.columns or
            'student_effects' not in self.results):
            print("跳过交互分析：需要班级信息和学生效应")
            return
            
        try:
            # 合并学生效应和班级信息
            student_effects = self.results['student_effects']
            
            # 添加班级ID
            student_class_map = self.data[[self.id_vars['student'], self.id_vars['class']]].drop_duplicates()
            student_class_map = student_class_map.set_index(self.id_vars['student'])
            
            student_effects['class_id'] = student_effects['student_id'].map(
                student_class_map[self.id_vars['class']]
            )
            
            # 计算班级级别的学生成长平均值
            class_growth = student_effects.groupby('class_id')['slope'].agg(['mean', 'std']).reset_index()
            class_growth.columns = ['class_id', 'avg_growth', 'growth_std']
            
            # 如果有班级效应，合并数据
            if 'class_effects' in self.results:
                class_growth = pd.merge(
                    class_growth,
                    self.results['class_effects'][['class_id', 'effect', 'value_added_t']],
                    on='class_id',
                    how='left'
                )
                
                # 计算班级效应与学生成长的相关性
                growth_effect_corr = np.corrcoef(
                    class_growth['avg_growth'],
                    class_growth['effect']
                )[0, 1]
                
                self.diagnostics['cross_level'] = {
                    'class_effect_growth_corr': growth_effect_corr
                }
                
                # 构建跨层交互模型
                # 公式：student_growth ~ class_effect
                X = sm.add_constant(class_growth['effect'])
                y = class_growth['avg_growth']
                
                interaction_model = sm.OLS(y, X).fit()
                
                self.diagnostics['cross_level']['interaction_model'] = {
                    'coef': interaction_model.params[1],
                    'p_value': interaction_model.pvalues[1],
                    'r_squared': interaction_model.rsquared
                }
                
                # 输出结果
                print("\n跨层交互分析结果:")
                print(f"班级效应与学生成长相关性: {growth_effect_corr:.4f}")
                print(f"班级效应对学生成长的影响: {interaction_model.params[1]:.4f}")
                print(f"模型解释力(R²): {interaction_model.rsquared:.4f}")
                
                # 保存交互分析结果
                self.results['cross_level'] = {
                    'class_growth': class_growth,
                    'interaction_stats': self.diagnostics['cross_level']
                }
                
        except Exception as e:
            print(f"交互分析失败: {str(e)}")
            warnings.warn("交互分析失败，请检查数据和模型结果")

    def _visualize_results(self):
        """可视化分析结果"""
        try:
            # 禁用matplotlib字体相关的调试输出和PNG流输出
            import logging
            logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
            logging.getLogger('PIL.PngImagePlugin').setLevel(logging.ERROR)
            
            # 设置中文字体支持 - 更完善的方式
            import matplotlib as mpl
            import platform
            
            # 根据操作系统选择合适的字体
            if platform.system() == 'Windows':
                font_list = ['Microsoft YaHei', 'SimHei', 'SimSun']
            elif platform.system() == 'Darwin':  # MacOS
                font_list = ['PingFang SC', 'Heiti SC', 'STHeiti']
            else:  # Linux
                font_list = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'Droid Sans Fallback']
            
            # 添加通用字体
            font_list.extend(['DejaVu Sans', 'Arial Unicode MS', 'sans-serif'])
            
            plt.rcParams['font.sans-serif'] = font_list
            plt.rcParams['axes.unicode_minus'] = False
            
            # 修正seaborn样式设置方式
            sns.set_style('whitegrid')
            
            # 1. 方差分解图
            if 'null_icc' in self.diagnostics:
                fig, ax = plt.subplots(figsize=(8, 6))
                
                icc = self.diagnostics['null_icc']
                labels = []
                values = []
                
                for level, value in icc.items():
                    if value > 0:
                        labels.append(level.capitalize())
                        values.append(value)
                
                colors = plt.cm.viridis(np.linspace(0, 0.8, len(values)))
                ax.bar(labels, values, color=colors)
                ax.set_ylim(0, 1)
                ax.set_ylabel('方差比例')
                ax.set_title('多层次方差分解')
                
                for i, v in enumerate(values):
                    ax.text(i, v + 0.02, f'{v:.1%}', ha='center')
                
                plt.tight_layout()
                plt.savefig('variance_decomposition.png')
                print("方差分解图已保存为 variance_decomposition.png")
            
            # 2. 学生成长轨迹图
            if 'student_effects' in self.results:
                # 选择几个具有代表性的学生
                student_effects = self.results['student_effects']
                
                # 获取高、中、低成长组各选几个学生
                selected_students = []
                for group in student_effects['growth_group'].unique():
                    group_students = student_effects[student_effects['growth_group'] == group]
                    if len(group_students) >= 3:
                        selected_students.extend(group_students.sample(3)['student_id'].tolist())
                    else:
                        selected_students.extend(group_students['student_id'].tolist())
                
                # 绘制这些学生的成长轨迹
                fig, ax = plt.subplots(figsize=(10, 6))
                
                for student_id in selected_students:
                    student_data = self.data[self.data[self.id_vars['student']] == student_id]
                    student_data = student_data.sort_values(by=self.time_var)
                    
                    student_effect = student_effects[student_effects['student_id'] == student_id]
                    growth_group = student_effect['growth_group'].iloc[0]
                    
                    # 确定线条颜色
                    if growth_group == '高成长':
                        color = 'green'
                        alpha = 0.8
                    elif growth_group == '低成长':
                        color = 'red'
                        alpha = 0.8
                    else:
                        color = 'blue'
                        alpha = 0.5
                    
                    ax.plot(student_data[self.time_var], student_data[self.outcome], 
                            marker='o', linestyle='-', alpha=alpha, color=color, 
                            label=f"学生 {student_id} ({growth_group})")
                
                # 添加平均趋势线
                if 'time' in self.models:
                    time_effect = self.models['time'].fe_params[f'{self.time_var}_centered']
                    intercept = self.models['time'].fe_params['Intercept']
                    
                    time_range = np.array([self.data[self.time_var].min(), self.data[self.time_var].max()])
                    score_pred = intercept + time_effect * (time_range - self.data[self.time_var].mean())
                    
                    ax.plot(time_range, score_pred, 'k--', linewidth=2, label='平均趋势')
                
                # 设置图表属性
                ax.set_xlabel('时间点')
                ax.set_ylabel(f'{self.outcome}')
                ax.set_title('学生成长轨迹示例')
                ax.legend(loc='best', ncol=2, fontsize=8)
                
                plt.tight_layout()
                plt.savefig('student_growth_trajectories.png')
                print("学生成长轨迹图已保存为 student_growth_trajectories.png")
            
            # 3. 班级效应分布图
            if 'class_effects' in self.results:
                class_effects = self.results['class_effects']
                
                fig, ax = plt.subplots(figsize=(10, 6))
                
                sns.histplot(class_effects['value_added_t'], kde=True, ax=ax)
                
                # 添加评级区间线
                for x in [40, 45, 55, 60]:
                    ax.axvline(x=x, color='r', linestyle='--', alpha=0.5)
                
                # 添加评级标签
                ax.text(35, ax.get_ylim()[1]*0.9, '显著低于平均', ha='center', rotation=90)
                ax.text(42.5, ax.get_ylim()[1]*0.9, '低于平均', ha='center', rotation=90)
                ax.text(50, ax.get_ylim()[1]*0.9, '平均水平', ha='center', rotation=90)
                ax.text(57.5, ax.get_ylim()[1]*0.9, '高于平均', ha='center', rotation=90)
                ax.text(65, ax.get_ylim()[1]*0.9, '显著高于平均', ha='center', rotation=90)
                
                ax.set_xlabel('班级增值T分')
                ax.set_ylabel('频率')
                ax.set_title('班级增值效应分布')
                
                plt.tight_layout()
                plt.savefig('class_effects_distribution.png')
                print("班级效应分布图已保存为 class_effects_distribution.png")
            
            # 4. 学校-班级效应热力图
            if ('school_effects' in self.results and 
                'class_effects' in self.results):
                
                # 合并班级和学校数据
                class_effects = self.results['class_effects'].copy()
                
                # 获取班级所属学校映射
                class_school_map = self.data[[self.id_vars['class'], self.id_vars['school']]].drop_duplicates()
                class_school_map = class_school_map.set_index(self.id_vars['class'])
                
                class_effects['school_id'] = class_effects['class_id'].map(
                    class_school_map[self.id_vars['school']]
                )
                
                # 合并学校效应数据
                class_effects = pd.merge(
                    class_effects,
                    self.results['school_effects'][['school_id', 'value_added_t']],
                    on='school_id',
                    how='left',
                    suffixes=('_class', '_school')
                )
                
                # 创建热力图
                fig, ax = plt.subplots(figsize=(10, 8))
                
                # 计算学校班级数量
                school_class_counts = class_effects.groupby('school_id').size().reset_index()
                school_class_counts.columns = ['school_id', 'class_count']
                
                # 按班级数量排序学校
                school_order = school_class_counts.sort_values('class_count', ascending=False)['school_id'].tolist()
                
                # 按学校ID和班级效应排序
                class_effects = class_effects.sort_values(['school_id', 'value_added_t_class'])
                
                # 创建学校-班级矩阵
                school_class_matrix = class_effects.pivot_table(
                    index='school_id',
                    columns='class_id',
                    values='value_added_t_class'
                )
                
                # 按学校班级数量重新排序
                school_class_matrix = school_class_matrix.reindex(school_order)
                
                # 绘制热力图
                sns.heatmap(school_class_matrix, cmap='coolwarm', center=50, 
                           vmin=30, vmax=70, ax=ax)
                
                ax.set_xlabel('班级')
                ax.set_ylabel('学校')
                ax.set_title('学校-班级增值效应热力图')
                
                plt.tight_layout()
                plt.savefig('school_class_heatmap.png')
                print("学校-班级效应热力图已保存为 school_class_heatmap.png")
            
            # 5. 跨层交互散点图
            if 'cross_level' in self.results:
                class_growth = self.results['cross_level']['class_growth']
                
                fig, ax = plt.subplots(figsize=(8, 6))
                
                sns.regplot(x='effect', y='avg_growth', data=class_growth, ax=ax)
                
                ax.set_xlabel('班级效应')
                ax.set_ylabel('学生平均成长率')
                ax.set_title('班级效应与学生成长率关系')
                
                # 添加相关系数文本
                if 'interaction_stats' in self.results['cross_level']:
                    stats = self.results['cross_level']['interaction_stats']
                    r = stats.get('class_effect_growth_corr', 0)
                    ax.text(0.05, 0.95, f'r = {r:.3f}', transform=ax.transAxes)
                
                plt.tight_layout()
                plt.savefig('cross_level_interaction.png')
                print("跨层交互散点图已保存为 cross_level_interaction.png")
                
            # 学校效应图
            if 'school_effects' in self.results:
                school_effects = self.results['school_effects'].copy()
                
                # 如果学校太多，只取前20所
                if len(school_effects) > 20:
                    top10 = school_effects.nlargest(10, 'effect')
                    bottom10 = school_effects.nsmallest(10, 'effect')
                    school_effects = pd.concat([top10, bottom10])
                
                fig, ax = plt.subplots(figsize=(10, 8))
                
                # 使用学校名称而不是ID来显示
                if 'school_name' in school_effects.columns:
                    # 截断太长的名称
                    school_effects['display_name'] = school_effects['school_name'].apply(
                        lambda x: x[:12] + '...' if len(x) > 15 else x
                    )
                    y_labels = school_effects['display_name']
                else:
                    y_labels = school_effects['school_id']
                
                # 绘制效应值和置信区间
                if 'ci_lower_95' in school_effects.columns:
                    # 横向误差条形图
                    y_pos = np.arange(len(school_effects))
                    ax.errorbar(
                        school_effects['effect'], 
                        y_pos,
                        xerr=[
                            school_effects['effect'] - school_effects['ci_lower_95'],
                            school_effects['ci_upper_95'] - school_effects['effect']
                        ], 
                        fmt='o', 
                        capsize=5
                    )
                    
                    # 添加零线
                    ax.axvline(x=0, color='gray', linestyle='--')
                    
                    # 设置y轴标签
                    ax.set_yticks(y_pos)
                    ax.set_yticklabels(y_labels)
                    
                    # 设置标题和标签
                    ax.set_title('学校效应值及95%置信区间')
                    ax.set_xlabel('效应值')
                    
                    plt.tight_layout()
                    plt.savefig('school_effects.png')
                    print("学校效应图已保存为 school_effects.png")
            
        except Exception as e:
            print(f"可视化结果失败: {str(e)}")
            warnings.warn("可视化过程中出现错误，部分图表可能无法生成")

    def _summarize_results(self):
        """
        汇总分析结果
        
        综合各层分析结果，形成最终报告。
        """
        summary = {
            'data_summary': {
                'observations': len(self.data),
                'students': self.data[self.id_vars['student']].nunique(),
                'time_points': self.data[self.time_var].nunique()
            },
            'variance_components': {}
        }
        
        # 添加方差分解结果
        if 'null_icc' in self.diagnostics:
            summary['variance_components'] = self.diagnostics['null_icc']
        
        # 添加模型信息
        if self.models:
            summary['model_info'] = {}
            for name, model in self.models.items():
                if hasattr(model, 'llf') and hasattr(model, 'aic'):
                    summary['model_info'][name] = {
                        'log_likelihood': model.llf,
                        'aic': model.aic,
                        'bic': model.bic if hasattr(model, 'bic') else None
                    }
        
        # 添加时间效应
        if 'time_effect' in self.diagnostics:
            summary['time_effect'] = self.diagnostics['time_effect']
        
        # 添加学生成长信息
        if 'student_growth' in self.diagnostics:
            summary['student_growth'] = self.diagnostics['student_growth']
        
        # 添加班级效应
        if 'class_effects' in self.diagnostics:
            summary['class_impact'] = self.diagnostics['class_effects']
        
        # 添加学校效应
        if 'school_effects' in self.diagnostics:
            summary['school_impact'] = self.diagnostics['school_effects']
        
        # 添加跨层交互
        if 'cross_level_interaction' in self.diagnostics:
            summary['cross_level_interaction'] = self.diagnostics['cross_level']
        
        # 输出摘要信息
        print("\n================================================================")
        print("多层次线性模型分析结果摘要")
        print("================================================================")
        
        print(f"\n数据概况:")
        print(f"  观测总数: {summary['data_summary']['observations']}")
        print(f"  学生数量: {summary['data_summary']['students']}")
        print(f"  时间点数: {summary['data_summary']['time_points']}")
        
        if 'variance_components' in summary:
            print("\n方差分解结果:")
            for level, icc in summary['variance_components'].items():
                print(f"  {level.capitalize()}层贡献: {icc:.1%}")
        
        if 'time_effect' in summary:
            print("\n时间效应:")
            effect = summary['time_effect']
            print(f"  时间系数: {effect['coefficient']:.4f} {'(显著)' if effect.get('significant', False) else '(不显著)'}")
            print(f"  p值: {effect['p_value']:.4f}")
        
        if 'class_impact' in summary:
            print("\n班级影响:")
            print(f"  班级方差: {summary['class_impact'].get('class_var', 0):.4f}")
            print(f"  班级ICC: {summary['class_impact'].get('class_icc', 0):.4f}")
        
        if 'school_impact' in summary:
            print("\n学校影响:")
            print(f"  学校方差: {summary['school_impact'].get('school_var', 0):.4f}")
            print(f"  学校ICC: {summary['school_impact'].get('school_icc', 0):.4f}")
        
        if 'cross_level_interaction' in summary:
            print("\n跨层交互:")
            interaction = summary['cross_level_interaction'].get('interaction_model', {})
            print(f"  班级效应对学生成长影响: {interaction.get('coef', 0):.4f}")
            print(f"  解释力(R²): {interaction.get('r_squared', 0):.4f}")
        
        # 保存摘要结果
        self.results['summary'] = summary
        
        # 输出结论
        print("\n================================================================")
        print("主要结论")
        print("================================================================")
        
        # 安全地处理方差贡献
        if 'variance_components' in summary and summary['variance_components']:
            try:
                max_var_level = max(summary['variance_components'].items(), key=lambda x: x[1])
                print(f"1. {max_var_level[0].capitalize()}层是影响学生成绩的最主要来源，贡献了{max_var_level[1]:.1%}的成绩差异。")
            except ValueError:
                print("1. 无法确定最主要的方差来源，请检查模型拟合结果。")
        else:
            print("1. 模型未能成功分解方差，请检查数据质量和模型设定。")
        
        # 时间效应显著性
        if 'time_effect' in summary and summary['time_effect'].get('significant', False):
            time_coef = summary['time_effect']['coefficient']
            direction = "提高" if time_coef > 0 else "下降"
            print(f"2. 随时间推移，学生整体表现呈{direction}趋势，平均每单位时间{abs(time_coef):.2f}分。")
        
        # 班级效应显著性
        if 'class_impact' in summary and summary['class_impact'].get('class_icc', 0) > 0.1:
            print(f"3. 班级因素对学生成绩有显著影响，解释了{summary['class_impact']['class_icc']*100:.1f}%的成绩变异。")
        
        # 交互效应
        if ('cross_level_interaction' in summary and 
            summary['cross_level_interaction'] and  # 添加非空检查
            summary['cross_level_interaction'].get('interaction_model', {}).get('significant', False)):
            print("4. 存在显著的班级-学生跨层交互作用，班级环境对学生个体成长轨迹有重要影响。")
        
        print("\n==== 分析完成 ====")

    def _variance_decomposition(self, model):
        """
        方差分解分析
        
        从模型中提取各层级的方差成分。
        
        Args:
            model: 拟合后的HLM模型
            
        Returns:
            dict: 包含各层级方差成分的字典
        """
        result = {}
        
        # 提取残差方差(时间层/学生内变异)
        result['residual_var'] = model.scale
        
        # 检查是否有随机效应协方差矩阵
        if hasattr(model, 'cov_re') and model.cov_re is not None:
            # 学校/顶层随机截距方差(如果是顶层分组变量)
            if model.cov_re.shape[0] > 0:
                result['school_var'] = model.cov_re.iloc[0, 0]
            
            # 学生随机斜率方差(如果有)
            if model.cov_re.shape[0] > 1:
                result['student_slope_var'] = model.cov_re.iloc[1, 1]
        else:
            result['school_var'] = 0
        
        # 提取方差成分模型(VC)的结果
        if hasattr(model, 'vcomp') and model.vcomp is not None:
            # 班级层方差
            if 'class' in model.vcomp:
                result['class_var'] = model.vcomp['class']
            else:
                result['class_var'] = 0
                
            # 学生层方差(如果在VC中)
            if 'student' in model.vcomp:
                result['student_var'] = model.vcomp['student']
            else:
                result['student_var'] = 0
        else:
            result['class_var'] = 0
            
            # 如果没有使用VC但使用了student作为分组，则可能在cov_re中
            if 'school_var' not in result or result['school_var'] == 0:
                if hasattr(model, 'cov_re') and model.cov_re is not None and model.cov_re.shape[0] > 0:
                    result['student_var'] = model.cov_re.iloc[0, 0]
                else:
                    result['student_var'] = 0
        
        # 计算总方差
        result['total_var'] = (
            result.get('school_var', 0) + 
            result.get('class_var', 0) + 
            result.get('student_var', 0) + 
            result.get('student_slope_var', 0) + 
            result['residual_var']
        )
        
        return result

    # 在LayeredHLM类中添加验证方法
    def _validate_hierarchy(self):
        """验证数据嵌套结构"""
        print("\n=== 层级结构验证 ===")
        
        # 检查学生-班级嵌套
        student_class = self.data.groupby(self.id_vars['student'])[self.id_vars['class']].nunique()
        multi_class_students = student_class[student_class > 1]
        if not multi_class_students.empty:
            print(f"警告: {len(multi_class_students)}名学生存在跨班级记录")
            print("示例学生:", multi_class_students.sample(3).index.tolist())
        else:
            print("学生-班级关系: 严格嵌套")
        
        # 检查班级-学校嵌套
        class_school = self.data.groupby(self.id_vars['class'])[self.id_vars['school']].nunique()
        multi_school_classes = class_school[class_school > 1]
        if not multi_school_classes.empty:
            print(f"警告: {len(multi_school_classes)}个班级存在跨学校记录")
            print("示例班级:", multi_school_classes.sample(3).index.tolist())
        else:
            print("班级-学校关系: 严格嵌套")
        
        # 检查时间点分布
        time_dist = self.data.groupby(self.id_vars['student'])[self.time_var].nunique()
        print("\n时间点分布:")
        print(f"  平均观测次数: {time_dist.mean():.1f}")
        print(f"  最小观测次数: {time_dist.min()}")
        print(f"  最大观测次数: {time_dist.max()}")
        
        # 新增：检查同班级不同年级
        class_grade = self.data.groupby('original_class_id')['student__current_grade'].nunique()
        multi_grade_classes = class_grade[class_grade > 1]
        if not multi_grade_classes.empty:
            print(f"\n警告: {len(multi_grade_classes)}个原始班级包含多个年级:")
            print("示例班级:", multi_grade_classes.sample(3).index.tolist())
            print("已通过复合class_id解决此问题")
        
        # 新增班级ID结构验证
        print("\n班级ID结构验证:")
        sample_classes = self.data['original_class_id'].dropna().sample(5)
        for c in sample_classes:
            grade, _, term = self._parse_class_id(c)
            print(f"  {c} → 年级: {grade}, 学期: {term}")
        
        # 检查同班级不同学期
        class_terms = self.data.groupby('compound_class_id')['term'].nunique()
        multi_term_classes = class_terms[class_terms > 1]
        if not multi_term_classes.empty:
            print(f"\n警告: {len(multi_term_classes)}个复合班级包含多学期数据")
            print("示例班级:", multi_term_classes.sample(3).index.tolist())



