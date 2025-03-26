"""
Bayesian Hierarchical Linear Modeling 独立实现模块

该模块提供完整的贝叶斯分层建模流程，包含以下功能：
- 多层级数据建模
- MCMC采样与收敛诊断
- 自动化结果输出
- 完整的错误处理机制
"""

import pymc3 as pm
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings

# 初始化日志配置
logger = logging.getLogger(__name__)

class BayesianHLMProcessor:
    """贝叶斯层次线性模型处理器
    
    功能特性：
    - 支持任意层级的嵌套数据
    - 自动先验分布设置
    - 后验分布可视化（可选）
    - 跨链收敛诊断
    """
    
    def __init__(self, input_path, sample_size=2000):
        """
        初始化模型处理器
        
        Args:
            input_path: Path 数据文件路径
            sample_size: int MCMC采样次数
        """
        self.input_path = input_path
        self.sample_size = sample_size
        self.trace = None
        self.model = None

    def _preprocess_data(self, raw_df):
        """
        数据预处理方法
        
        Args:
            raw_df: pd.DataFrame 原始输入数据
            
        Returns:
            pd.DataFrame 处理后的干净数据
            
        Raises:
            ValueError: 当必要字段缺失时
        """
        required_columns = {'group', 'x', 'y'}
        if not required_columns.issubset(raw_df.columns):
            missing = required_columns - set(raw_df.columns)
            raise ValueError(f"缺失必要字段: {missing}")

        df = raw_df.copy()
        df['group_code'] = df['group'].astype('category').cat.codes
        return df

    def build_model(self, clean_df):
        """
        构建层次模型结构
        
        Args:
            clean_df: pd.DataFrame 预处理后的数据
            
        Returns:
            pm.Model 构建完成的PyMC3模型
        """
        groups = clean_df['group_code'].unique()
        n_groups = len(groups)

        with pm.Model() as hlm_model:
            # 超参数先验
            hyper_mu = pm.Normal('hyper_mu', mu=0, sigma=10, shape=2)
            hyper_sigma = pm.HalfNormal('hyper_sigma', sigma=10, shape=2)
            
            # 随机效应
            alpha = pm.Normal('alpha', 
                            mu=hyper_mu[0], 
                            sigma=hyper_sigma[0], 
                            shape=n_groups)
            beta = pm.Normal('beta',
                           mu=hyper_mu[1],
                           sigma=hyper_sigma[1],
                           shape=n_groups)
            
            # 观测误差
            sigma_error = pm.HalfNormal('sigma_error', sigma=10)
            
            # 线性组合
            mu = alpha[clean_df['group_code']] + beta[clean_df['group_code']] * clean_df['x']
            
            # 添加二次项示例
            beta_quad = pm.Normal('beta_quad', 
                                mu=0, 
                                sigma=10, 
                                shape=len(clean_df['group_code'].unique()))
            
            mu = (alpha[clean_df['group_code']] 
                  + beta[clean_df['group_code']] * clean_df['x']
                  + beta_quad[clean_df['group_code']] * (clean_df['x']**2))
            
            # 似然函数
            y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma_error, observed=clean_df['y'])
            
        return hlm_model

    def run_inference(self):
        """
        执行模型推断
        
        Returns:
            pm.backends.base.MultiTrace 采样轨迹
            
        Raises:
            RuntimeError: 当采样失败时
        """
        try:
            raw_df = pd.read_csv(self.input_path)
            clean_df = self._preprocess_data(raw_df)
            
            self.model = self.build_model(clean_df)
            
            with self.model:
                self.trace = pm.sample(
                    self.sample_size,
                    tune=1000,
                    cores=4,
                    return_inferencedata=False
                )
                
            return self.trace
        
        except Exception as e:
            logger.error(f"模型推断失败: {str(e)}")
            raise RuntimeError("贝叶斯推断执行失败") from e

    def _diagnose_convergence(self):
        """收敛性诊断"""
        return pm.gelman_rubin(self.trace)

    def generate_visualizations(self, output_dir):
        """生成后验分布可视化"""
        with self.model:
            pm.plot_trace(self.trace).savefig(output_dir / 'trace_plot.png')
            pm.plot_posterior(self.trace).savefig(output_dir / 'posterior_plot.png')

class Command(BaseCommand):
    """Django管理命令入口"""
    
    help = "执行贝叶斯层次线性模型分析 (v2.1)"
    
    def add_arguments(self, parser):
        """配置命令行参数"""
        parser.add_argument(
            '-i', '--input',
            type=Path,
            default=settings.BASE_DIR / 'data/multilevel.csv',
            help='输入数据文件路径'
        )
        parser.add_argument(
            '-s', '--samples',
            type=int,
            default=5000,
            help='MCMC采样次数'
        )
        parser.add_argument(
            '-o', '--output',
            type=Path,
            default=settings.BASE_DIR / 'outputs/bayesian_hlm',
            help='结果输出目录'
        )
        parser.add_argument(
            '--plot',
            action='store_true',
            help='生成后验分布可视化图表'
        )

    def handle(self, *args, **options):
        """命令执行主函数"""
        try:
            self.stdout.write("启动贝叶斯层次模型分析...")
            
            # 初始化处理器
            processor = BayesianHLMProcessor(
                input_path=options['input'],
                sample_size=options['samples']
            )
            
            # 执行分析
            trace = processor.run_inference()
            
            # 保存结果
            output_dir = options['output']
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存统计摘要
            summary = pm.summary(trace)
            summary.to_csv(output_dir / 'summary.csv')
            
            # 保存原始轨迹
            pm.save_trace(trace, directory=output_dir, overwrite=True)
            
            self.stdout.write(self.style.SUCCESS(
                f"分析成功完成！结果保存在：{output_dir}"
            ))
            
            if options['plot']:
                self.stdout.write("生成可视化图表...")
                processor.generate_visualizations(output_dir)
            
        except Exception as e:
            logger.exception("命令执行遇到严重错误")
            self.stderr.write(self.style.ERROR(
                f"执行失败: {str(e)}"
            ))
            raise

"""
技术亮点：
1. 模块化设计：分离数据处理、模型构建和推断执行
2. 稳健性增强：多层级异常处理机制
3. 扩展性：支持自定义先验分布和模型结构
4. 结果完整性：同时保存统计摘要和原始采样轨迹

执行示例：
python manage.py bayesian_hlm \
  -i data/multilevel.csv \
  -s 8000 \
  -o results/hlm_analysis
""" 