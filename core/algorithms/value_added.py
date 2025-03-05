"""
增值评价算法模块，实现教学质量增值评价的核心计算逻辑。
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

def standardize_scores(scores_df):
    """
    将原始分数标准化为Z分数。

    Args:
        scores_df: 包含原始分数的DataFrame
            columns=['student_id', 'raw_score', ...]

    Returns:
        添加了标准分的DataFrame
    """
    scaler = StandardScaler()
    scores_df['standard_score'] = scaler.fit_transform(scores_df[['raw_score']])
    return scores_df

def calculate_value_added(baseline_df, current_df, method='z_score'):
    """
    计算增值分数。

    Args:
        baseline_df: 基线分数DataFrame
        current_df: 当前分数DataFrame
        method: 计算方法，可选 'z_score', 'percentile'

    Returns:
        包含增值分数的DataFrame
    """
    # 合并基线和当前数据
    merged_df = pd.merge(
        baseline_df, current_df, 
        on='student_id', 
        suffixes=('_base', '_current')
    )
    
    # 计算增值分
    if method == 'z_score':
        merged_df['value_added'] = merged_df['standard_score_current'] - merged_df['standard_score_base']
    else:
        merged_df['value_added'] = merged_df['percentile_current'] - merged_df['percentile_base']
    
    return merged_df 