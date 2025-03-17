# core/analytics/algorithms.py
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

class TrendAnalysisAlgorithm:
    """趋势分析算法"""
    
    def calculate(self, time_series_data):
        """
        计算学科趋势指标
        
        Args:
            time_series_data: 时间序列数据框
            
        Returns:
            dict: 各学科趋势分析结果
        """
        if time_series_data.empty:
            return {}
            
        # 按学科和学期排序
        df = time_series_data.sort_values(['subject_name', 'semester_id'])
        
        trends = {}
        for subject in df['subject_name'].unique():
            subject_data = df[df['subject_name'] == subject]
            
            if len(subject_data) < 2:
                continue  # 需要至少两个时间点
                
            # 提取时间点和分数
            x = np.arange(len(subject_data)).reshape(-1, 1)
            y = subject_data['raw_score_mean'].values
            
            # 线性回归获取趋势
            model = LinearRegression()
            model.fit(x, y)
            
            # 提取趋势系数
            slope = model.coef_[0]
            
            # 计算R方值
            y_pred = model.predict(x)
            ss_total = np.sum((y - np.mean(y))**2)
            ss_residual = np.sum((y - y_pred)**2)
            r_squared = 1 - (ss_residual / ss_total) if ss_total != 0 else 0
            
            # 检测波动性
            volatility = subject_data['raw_score_std'].mean()
            
            trends[subject] = {
                'direction': 'up' if slope > 0 else 'down',
                'slope': slope,
                'r_squared': r_squared,
                'volatility': volatility,
                'is_stable': r_squared > 0.7 and volatility < 10
            }
            
        return trends

class StabilityIndexAlgorithm:
    """稳定性指数算法"""
    
    def calculate(self, scores_data):
        """
        计算学生成绩稳定性指数
        
        Args:
            scores_data: 成绩数据
            
        Returns:
            dict: 各学科稳定性指数
        """
        if scores_data.empty:
            return {}
            
        # 按学科分组
        grouped = scores_data.groupby('subject_name')
        
        stability = {}
        for subject, group in grouped:
            # 计算变异系数(CV)
            cv = group['raw_score'].std() / group['raw_score'].mean() if group['raw_score'].mean() > 0 else np.nan
            
            # 计算波动率
            if len(group) >= 2:
                diffs = np.abs(np.diff(group['raw_score'].values))
                avg_diff = np.mean(diffs) if len(diffs) > 0 else 0
                max_potential_diff = (group['raw_score'].max() - group['raw_score'].min()) 
                volatility = (avg_diff / max_potential_diff * 100) if max_potential_diff > 0 else 0
            else:
                volatility = 0
                
            # 计算稳定性指数 (0-100)
            if np.isnan(cv):
                stability_index = 50  # 默认中等稳定性
            else:
                # 变异系数越小，稳定性越高
                stability_index = 100 - min(100, cv * 100)
                
            # 调整波动因素
            stability_index = max(0, stability_index - volatility * 0.5)
            
            stability[subject] = {
                'stability_index': stability_index,
                'volatility': volatility,
                'cv': cv
            }
            
        return stability