"""
基于累积分布函数的学习波动分析系统

功能特点：
1. 学生成绩波动性分析
2. T分布累积概率计算
3. 学习趋势识别
4. 多时间点纵向分析
"""

import scipy.stats as stats
import numpy as np
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Student, Score, Exam
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

class CDFAnalyzer:
    """CDF分析核心类"""
    
    def __init__(self, min_scores=3, trend_threshold=0.05):
        """
        初始化分析器
        
        Args:
            min_scores: int 分析所需最低成绩数量
            trend_threshold: float 趋势判断阈值
        """
        self.min_scores = min_scores
        self.trend_threshold = trend_threshold

    def calculate_cdf(self, scores):
        """计算学生成绩序列的T分布累积分布值
        
        使用学生T分布拟合成绩数据，计算每个分数对应的CDF值，
        反映该分数在整体分布中的位置
        
        Args:
            scores: list - 学生的历史成绩列表
            
        Returns:
            list - 每个成绩对应的CDF值列表
            
        Raises:
            ValueError: 当输入数据不足时抛出异常
        """
        if len(scores) < self.min_scores:
            raise ValueError(f"至少需要{self.min_scores}个成绩数据点")

        # 计算样本统计量
        df = len(scores) - 1  # 自由度
        loc = np.mean(scores)  # 位置参数
        scale = np.std(scores, ddof=1)  # 尺度参数

        return [stats.t.cdf(x, df, loc, scale) for x in scores]

    def analyze_volatility(self, cdf_values):
        """分析CDF值序列的波动特征
        
        Args:
            cdf_values: list - 通过calculate_cdf计算的CDF值列表
            
        Returns:
            dict: 包含波动特征的字典
                {
                    'range': 值域范围,
                    'std_dev': 标准差,
                    'trend': 趋势方向（1=上升，-1=下降，0=稳定）,
                    'volatility_level': 波动等级
                }
        """
        # 计算基础统计量
        cdf_range = max(cdf_values) - min(cdf_values)
        std_dev = np.std(cdf_values)
        
        # 趋势分析
        slope = self._calculate_trend(cdf_values)
        
        # 波动等级评估
        volatility_level = self._assess_volatility_level(cdf_range, std_dev)
        
        return {
            'range': round(cdf_range, 3),
            'std_dev': round(std_dev, 3),
            'trend': self._classify_trend(slope),
            'volatility_level': volatility_level
        }

    def _calculate_trend(self, values):
        """使用线性回归计算趋势斜率"""
        x = np.arange(len(values))
        return stats.linregress(x, values).slope

    def _classify_trend(self, slope):
        """分类趋势方向"""
        if slope > self.trend_threshold:
            return 1
        elif slope < -self.trend_threshold:
            return -1
        return 0

    def _assess_volatility_level(self, cdf_range, std_dev):
        """评估波动等级"""
        if cdf_range > 0.3 or std_dev > 0.15:
            return 3  # 高波动
        elif cdf_range > 0.2 or std_dev > 0.1:
            return 2  # 中波动
        return 1  # 低波动


class Command(BaseCommand):
    """学习波动分析管理命令"""
    
    help = "执行基于CDF的学习波动分析"
    
    def add_arguments(self, parser):
        parser.add_argument('-s', '--student', 
                          help='指定学生ID进行分析')
        parser.add_argument('-e', '--exam', 
                          help='指定考试ID，多个用逗号分隔')
        parser.add_argument('-o', '--output', type=Path,
                          default=settings.BASE_DIR / 'results' / 'cdf_analysis')
    
    def handle(self, *args, **options):
        try:
            # 获取分析数据
            student_scores = self._get_student_scores(
                options['student'], 
                options['exam']
            )
            
            # 执行分析
            analyzer = CDFAnalyzer()
            results = {}
            
            for student_id, scores in student_scores.items():
                try:
                    cdf = analyzer.calculate_cdf(scores)
                    volatility = analyzer.analyze_volatility(cdf)
                    results[student_id] = {
                        'cdf_sequence': cdf,
                        'volatility': volatility,
                        'scores': scores
                    }
                except ValueError as e:
                    logger.warning(f"学生{student_id}分析失败: {str(e)}")
            
            # 保存结果
            self._save_results(results, options['output'])
            
            self.stdout.write(
                self.style.SUCCESS(f"成功分析{len(results)}名学生数据")
            )
            
        except Exception as e:
            logger.exception("CDF分析失败")
            self.stderr.write(self.style.ERROR(f"执行失败: {str(e)}"))

    def _get_student_scores(self, student_id=None, exam_ids=None):
        """获取学生成绩数据"""
        # 构建查询
        query = Score.objects.select_related('student', 'exam')
        
        if student_id:
            query = query.filter(student_id=student_id)
            
        if exam_ids:
            exam_list = [e.strip() for e in exam_ids.split(',')]
            query = query.filter(exam_id__in=exam_list)
            
        # 组织数据
        student_scores = {}
        for score in query:
            student_id = score.student_id
            if student_id not in student_scores:
                student_scores[student_id] = []
            student_scores[student_id].append(score.standard_score)
            
        return student_scores

    def _save_results(self, results, output_dir):
        """保存分析结果"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成报告文件
        report_path = output_dir / 'cdf_analysis_report.csv'
        
        report_data = []
        for student_id, data in results.items():
            report_data.append({
                'student_id': student_id,
                'score_count': len(data['scores']),
                'cdf_range': data['volatility']['range'],
                'cdf_std': data['volatility']['std_dev'],
                'trend': data['volatility']['trend'],
                'volatility_level': data['volatility']['volatility_level'],
                'latest_score': data['scores'][-1]
            })
        
        pd.DataFrame(report_data).to_csv(report_path, index=False)
        logger.info(f"分析报告已保存至: {report_path}") 