import pandas as pd
import os
from typing import Dict, List, Tuple
import logging
import tkinter as tk
from tkinter import filedialog

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_output_directory(directory: str = "output") -> None:
    """
    创建输出目录。

    Args:
        directory: 要创建的目录路径

    Raises:
        OSError: 当目录创建失败时
    """
    try:
        os.makedirs(directory, exist_ok=True)
        logging.info(f"成功创建输出目录: {directory}")
    except OSError as e:
        logging.error(f"创建目录失败: {e}")
        raise

def rank_and_score(df: pd.DataFrame, column: str, ascending: bool = True) -> pd.Series:
    """
    根据排名计算得分。

    Args:
        df: 输入的DataFrame
        column: 用于排名的列名
        ascending: 是否升序排序

    Returns:
        包含计算得分的Series

    Raises:
        KeyError: 当指定的列不存在时
    """
    try:
        ranked = df[column].rank(ascending=ascending, method="min")
        scores = ranked.apply(lambda x: 8 if 1 <= x <= 22 else
                            6 if 23 <= x <= 52 else
                            5 if 53 <= x <= 89 else
                            4 if 90 <= x <= 127 else
                            3 if 128 <= x <= 164 else
                            2 if 165 <= x <= 194 else 0)
        return scores
    except KeyError as e:
        logging.error(f"列名不存在: {e}")
        raise

def load_excel_file(file_path: str) -> pd.DataFrame:
    """
    加载Excel文件并进行预处理。

    Args:
        file_path: Excel文件路径

    Returns:
        处理后的DataFrame

    Raises:
        FileNotFoundError: 当文件不存在时
        pd.errors.EmptyDataError: 当文件为空时
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        df = pd.read_excel(
            file_path, 
            engine="xlrd", 
            dtype={"xxh": str, "bb": str}
        )
        
        # 打印原始数据信息
        logging.info(f"加载文件 {file_path}")
        logging.info(f"原始数据形状: {df.shape}")
        logging.info(f"列名: {df.columns.tolist()}")
        
        # 统一列名为小写
        df.columns = df.columns.str.lower()
        
        # 删除空行和空列
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        
        # 确保必要的列存在
        required_cols = ["xxh", "bb"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise KeyError(f"缺少必要的列: {missing_cols}")
            
        # 打印处理后的数据信息
        logging.info(f"处理后数据形状: {df.shape}")
        
        return df
        
    except Exception as e:
        logging.error(f"加载文件失败 {file_path}: {str(e)}")
        raise

def calculate_subject_scores(df: pd.DataFrame, score_fields: List[str], 
                           include_teacher: bool = True, teacher_field: str = None) -> pd.DataFrame:
    """
    计算学科得分。

    Args:
        df: 输入的DataFrame
        score_fields: 成绩相关字段列表 [平均分, 优秀率, 合格率, 低分率]
        include_teacher: 是否包含教师信息
        teacher_field: 教师字段名称

    Returns:
        包含计算结果的DataFrame
    """
    # 基础字段
    fields_to_include = ["xxh", "xxmc", "bb"] + score_fields

    # 检查教师字段
    if include_teacher and teacher_field:
        if teacher_field in df.columns:
            fields_to_include.append(teacher_field)
        else:
            logging.warning(f"教师字段 {teacher_field} 不存在，将使用空值代替")
    
    result_df = df[fields_to_include].copy()
    
    # 如果教师字段不存在但需要，添加空值列
    if include_teacher and teacher_field and teacher_field not in df.columns:
        result_df[teacher_field] = ""
    
    # 检查是否所有成绩都是0
    all_zeros = all(result_df[field].fillna(0).eq(0).all() for field in score_fields)
    
    if all_zeros:
        # 如果所有成绩都是0，直接设置所有得分为0
        logging.info("检测到所有成绩为0，设置总得分为0")
        result_df["平均分赋分"] = 0
        result_df["优秀率赋分"] = 0
        result_df["合格率赋分"] = 0
        result_df["低分率赋分"] = 0
        result_df["总得分"] = 0
    else:
        # 正常计算得分
        result_df.loc[:, "平均分赋分"] = rank_and_score(result_df, score_fields[0], ascending=False).astype(float)
        result_df.loc[:, "优秀率赋分"] = rank_and_score(result_df, score_fields[1], ascending=False).astype(float)
        result_df.loc[:, "合格率赋分"] = rank_and_score(result_df, score_fields[2], ascending=False).astype(float)
        result_df.loc[:, "低分率赋分"] = rank_and_score(result_df, score_fields[3], ascending=True).astype(float)

        # 处理无低分率情况
        result_df["无低分率"] = result_df[score_fields[3]] == 0
        bonus_columns = ["平均分赋分", "优秀率赋分", "合格率赋分"]
        result_df.loc[result_df["无低分率"], bonus_columns] *= 1.33

        # 计算总分
        score_columns = ["平均分赋分", "优秀率赋分", "合格率赋分", "低分率赋分"]
        result_df["总得分"] = result_df[score_columns].sum(axis=1)
    
    return result_df

def check_and_handle_duplicates(df, subset):
    """
    检查数据框中是否存在重复值，并根据需要删除或合并重复项。
    """
    duplicates = df.duplicated(subset=subset, keep=False)
    if duplicates.any():
        print(f"数据框中存在重复的 {subset} 组合:")
        print(df[duplicates])
        # 删除重复项（可根据业务需求调整为其他处理方式）
        df = df.drop_duplicates(subset=subset)
        print("已删除重复项")
    return df

def calculate_progress_scores(df_a: pd.DataFrame, df_b: pd.DataFrame, score_fields: List[str]) -> pd.DataFrame:
    """
    计算进步分数，基于对应班级之间的比较。

    Args:
        df_a: 上学期数据，包含已计算好的班级指标
        df_b: 本学期数据，包含已计算好的班级指标
        score_fields: 指标字段列表 [平均分字段, 优秀率字段, 合格率字段, 低分率字段, 教师字段]

    Returns:
        包含进步分数的DataFrame
    """
    # 保存原始df_a和df_b的副本
    df_a_original = df_a.copy()
    df_b_original = df_b.copy()
    
    # 分离教师字段和成绩字段
    teacher_field = score_fields[-1]  # 最后一个字段是教师字段
    score_fields = score_fields[:-1]  # 其余是成绩字段
    
    # 将分数字段转换为数值类型
    for field in score_fields:
        df_a[field] = pd.to_numeric(df_a[field], errors='coerce')
        df_b[field] = pd.to_numeric(df_b[field], errors='coerce')
    
    # 检查并处理重复项
    df_a = check_and_handle_duplicates(df_a, subset=['xxh', 'bb'])
    df_b = check_and_handle_duplicates(df_b, subset=['xxh', 'bb'])

    # 确保 ('xxh', 'bb') 是唯一的索引
    df_a.set_index(['xxh', 'bb'], inplace=True)
    df_b.set_index(['xxh', 'bb'], inplace=True)

    # 找到两个数据框中共有的班级组合
    common_classes = df_a.index.intersection(df_b.index)
    logging.info(f"共有 {len(common_classes)} 个共同班级")

    # 初始化班级进步值数据框
    class_progress = pd.DataFrame(index=common_classes, columns=score_fields)

    # 遍历每个班级，计算进步值
    for class_id in common_classes:
        a_scores = df_a.loc[class_id, score_fields]
        b_scores = df_b.loc[class_id, score_fields]
        progress_values = b_scores - a_scores
        class_progress.loc[class_id] = progress_values

    # 对班级进步值进行排名赋分
    class_scores = pd.DataFrame(index=class_progress.index)
    
    # 获取特殊学校的索引
    special_school_mask = class_progress.index.get_level_values('xxh') == 78319
    
    for i, field in enumerate(score_fields):
        # 跳过低分率字段对特殊学校的处理
        if field.endswith('dfl'):
            # 对非特殊学校计算低分率排名和赋分
            non_special_mask = ~special_school_mask
            ranked = pd.Series(index=class_progress.index)
            
            # 只对非特殊学校的数据进行排名
            non_special_data = class_progress[field][non_special_mask]
            non_null_mask = non_special_data.notnull()
            
            if non_null_mask.any():
                non_null_ranks = non_special_data[non_null_mask].rank(
                    ascending=True,  # 低分率使用升序
                    method="min"
                )
                ranked[non_special_mask & non_special_data.notnull()] = non_null_ranks
                ranked[special_school_mask] = float('nan')  # 特殊学校设为NaN
        else:
            # 对于非低分率字段（平均分、优秀率、合格率）
            # 特殊学校的进步值乘以1.333
            values = class_progress[field].copy()
            values[special_school_mask] = values[special_school_mask] * 1.333
            
            # 计算排名
            ranked = pd.Series(index=class_progress.index)
            non_null_mask = values.notnull()
            
            if non_null_mask.any():
                non_null_ranks = values[non_null_mask].rank(
                    ascending=False,  # 这些指标使用降序
                    method="min"
                )
                ranked[non_null_mask] = non_null_ranks
        
        # 应用分层逻辑
        scores = ranked.apply(lambda x: 8 if pd.notnull(x) and 1 <= x <= 22 else
                            6 if pd.notnull(x) and 23 <= x <= 52 else
                            5 if pd.notnull(x) and 53 <= x <= 89 else
                            4 if pd.notnull(x) and 90 <= x <= 127 else
                            3 if pd.notnull(x) and 128 <= x <= 164 else
                            2 if pd.notnull(x) and 165 <= x <= 194 else 0)
        
        class_scores[f"{field}_进步赋分"] = scores

    # 计算班级进步总分
    class_scores["进步总分"] = class_scores[[f"{field}_进步赋分" for field in score_fields]].sum(axis=1)

    # 创建最终结果DataFrame，使用df_b的索引
    progress_df = df_b_original.reset_index()[['xxh', 'xxmc', 'bb', teacher_field]]
    
    # 创建MultiIndex用于映射
    idx = pd.MultiIndex.from_arrays([progress_df['xxh'], progress_df['bb']])
    
    # 确保df_a_original和df_b_original使用相同的索引
    df_a_original.set_index(['xxh', 'bb'], inplace=True)
    df_b_original.set_index(['xxh', 'bb'], inplace=True)
    
    # 对本学期成绩进行排名分层
    current_term_scores = pd.DataFrame(index=df_b_original.index)
    
    # 获取特殊学校的索引
    special_school_mask = df_b_original.index.get_level_values('xxh') == 78319
    
    for i, field in enumerate(score_fields):
        # 跳过低分率字段对特殊学校的处理
        if field.endswith('dfl'):
            # 对非特殊学校计算低分率排名和赋分
            non_special_mask = ~special_school_mask
            ranked = pd.Series(index=df_b_original.index)
            
            # 只对非特殊学校的数据进行排名
            non_special_data = df_b_original[field][non_special_mask]
            non_null_mask = non_special_data.notnull()
            
            if non_null_mask.any():
                non_null_ranks = non_special_data[non_null_mask].rank(
                    ascending=True,  # 低分率使用升序
                    method="min"
                )
                ranked[non_special_mask & non_special_data.notnull()] = non_null_ranks
                ranked[special_school_mask] = float('nan')  # 特殊学校设为NaN
        else:
            # 对于非低分率字段（平均分、优秀率、合格率）
            # 特殊学校的值乘以1.333
            values = df_b_original[field].copy()
            values[special_school_mask] = values[special_school_mask] * 1.333
            
            # 计算排名
            ranked = pd.Series(index=df_b_original.index)
            non_null_mask = values.notnull()
            
            if non_null_mask.any():
                non_null_ranks = values[non_null_mask].rank(
                    ascending=False,  # 这些指标使用降序
                    method="min"
                )
                ranked[non_null_mask] = non_null_ranks
        
        # 应用分层逻辑
        scores = ranked.apply(lambda x: 8 if pd.notnull(x) and 1 <= x <= 22 else
                            6 if pd.notnull(x) and 23 <= x <= 52 else
                            5 if pd.notnull(x) and 53 <= x <= 89 else
                            4 if pd.notnull(x) and 90 <= x <= 127 else
                            3 if pd.notnull(x) and 128 <= x <= 164 else
                            2 if pd.notnull(x) and 165 <= x <= 194 else 0)
        
        current_term_scores[f"{field}_本期赋分"] = scores
    
    # 计算本学期总分
    current_term_scores["本期总分"] = current_term_scores[[f"{field}_本期赋分" for field in score_fields]].sum(axis=1)
    
    # 添加原始分数、进步值和进步赋分
    for field in score_fields:
        # 使用reindex确保数据对齐
        progress_df[f"{field}_上学期"] = df_a_original[field].reindex(idx).values
        progress_df[f"{field}_本学期"] = df_b_original[field].reindex(idx).values
        progress_df[f"{field}_本期赋分"] = current_term_scores[f"{field}_本期赋分"].reindex(idx).values
        progress_df[f"{field}_进步值"] = class_progress[field].reindex(idx).values
        progress_df[f"{field}_进步赋分"] = class_scores[f"{field}_进步赋分"].reindex(idx).values

    # 添加总分
    progress_df["本期总分"] = current_term_scores["本期总分"].reindex(idx).values
    progress_df["本期总分排名"] = progress_df["本期总分"].rank(method="min", ascending=False)
    progress_df["进步总分"] = class_scores["进步总分"].reindex(idx).values
    progress_df["进步总分排名"] = progress_df["进步总分"].rank(method="min", ascending=False)

    # 计算综合得分 (本期总分40% + 进步总分60%)
    progress_df["综合得分"] = (progress_df["本期总分"] * 0.4 + 
                              progress_df["进步总分"] * 0.6)
    
    # 计算综合得分排名
    progress_df["综合排名"] = progress_df["综合得分"].rank(method="min", ascending=False)

    # 重新排列列顺序
    columns_order = [
        'xxh', 'xxmc', 'bb', teacher_field  # 基础信息
    ]
    
    # 添加其他列
    for field in score_fields:
        columns_order.extend([
            f"{field}_上学期",
            f"{field}_本学期",
            f"{field}_本期赋分",
            f"{field}_进步值",
            f"{field}_进步赋分"
        ])
    
    # 添加总分列
    columns_order.extend([
        "本期总分",
        "本期总分排名",
        "进步总分",
        "进步总分排名",
        "综合得分",
        "综合排名"
    ])

    # 重新排序列
    progress_df = progress_df[columns_order]

    # 按综合得分降序排序
    progress_df = progress_df.sort_values(['综合得分'], ascending=[False])

    logging.info(f"处理完成，共 {len(progress_df)} 条记录")

    return progress_df

def process_subjects(df_a: pd.DataFrame, df_b: pd.DataFrame, subject_config: dict):
    """
    处理各个学科的数据。

    Args:
        df_a: 上学期数据
        df_b: 本学期数据
        subject_config: 学科配置字典
    """
    results = {}
    
    for subject, fields in subject_config.items():
        try:
            logging.info(f"\n开始处理学科: {subject}")
            logging.info(f"处理字段: {fields}")
            
            # 在设置索引之前获取需要的列
            df_b_with_keys = df_b.reset_index() if df_b.index.names != [None] else df_b.copy()
            df_a_with_keys = df_a.reset_index() if df_a.index.names != [None] else df_a.copy()
            
            # 修改必要列的检查，移除 student_key
            required_columns = ['xxh', 'bb'] + fields
            if not all(col in df_b_with_keys.columns for col in required_columns):
                logging.error(f"缺少必要的列。现有列: {df_b_with_keys.columns.tolist()}")
                continue
                
            # 计算进步分数
            progress_df = calculate_progress_scores(
                df_a_with_keys,
                df_b_with_keys,
                fields
            )
            
            results[subject] = progress_df
            
        except Exception as e:
            logging.error(f"{subject} 处理失败: {str(e)}")
            logging.error("错误详情:", exc_info=True)
            continue
            
    return results

def save_results(results: Dict[str, pd.DataFrame], output_file: str) -> None:
    """
    保存处理结果到Excel文件。

    Args:
        results: 包含所有学科结果的字典
        output_file: 输出文件路径

    Raises:
        ValueError: 当没有有效数据可保存时
        PermissionError: 当文件无法写入时
    """
    try:
        # 检查是否有结果数据
        if not results:
            raise ValueError("没有任何处理结果可保存")

        # 检查是否有非空的DataFrame
        valid_results = {subject: df for subject, df in results.items() if not df.empty}
        if not valid_results:
            raise ValueError("所有处理结果都是空的")

        # 打印每个学科的数据情况
        for subject, df in valid_results.items():
            logging.info(f"{subject} 数据: {len(df)} 行")

        # 保存非空的结果
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            for subject, df in valid_results.items():
                df.to_excel(writer, sheet_name=subject, index=False)
                logging.info(f"已保存 {subject} 数据到工作表")

        logging.info(f"结果已保存到: {output_file}")
        
    except ValueError as e:
        logging.error(f"保存失败: {str(e)}")
        raise
    except PermissionError:
        logging.error(f"无法写入文件: {output_file}")
        raise
    except Exception as e:
        logging.error(f"保存过程中发生错误: {str(e)}")
        raise

def select_files():
    """
    使用文件选择对话框获取输入文件。

    Returns:
        tuple: (上学期文件路径, 本学期文件路径)
    """
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 选择上学期文件
    logging.info("请选择上学期数据文件...")
    file_a = filedialog.askopenfilename(
        title="选择上学期数据文件",
        filetypes=[("Excel files", "*.xls;*.xlsx"), ("All files", "*.*")]
    )
    
    if not file_a:
        raise ValueError("未选择上学期数据文件")

    # 选择本学期文件
    logging.info("请选择本学期数据文件...")
    file_b = filedialog.askopenfilename(
        title="选择本学期数据文件",
        filetypes=[("Excel files", "*.xls;*.xlsx"), ("All files", "*.*")]
    )
    
    if not file_b:
        raise ValueError("未选择本学期数据文件")

    return file_a, file_b

def main():
    """
    主函数，协调整个程序的执行流程。
    
    功能说明：
    1. 定义输入输出路径
    2. 配置各学科的字段映射
    3. 加载和处理Excel数据
    4. 生成分析结果
    
    处理流程：
    1. 设置输入输出目录
    2. 定义学科字段映射（包括平均分、优秀率、合格率、低分率、教师字段）
    3. 读取上下学期数据文件
    4. 处理数据并生成结果
    5. 保存结果到输出文件
    """
    # 定义输出目录
    OUTPUT_DIR = "output"
    OUTPUT_FILE = os.path.join(OUTPUT_DIR, "result.xlsx")

    # 学科字段映射配置
    # 每个学科包含：[平均分, 优秀率, 合格率, 低分率, 教师]字段
    # 综合学科不包含教师字段
    subject_fields = {
        "语文": ["ywpjf", "ywyxl", "ywhgl", "ywdfl", "ywkr"],  # 语文学科字段
        "数学": ["sxpjf", "sxyxl", "sxhgl", "sxdfl", "sxkr"],  # 数学学科字段
        "英语": ["yypjf", "yyyxl", "yyhgl", "yydfl", "yykr"],  # 英语学科字段
        "科学": ["kxpjf", "kxyxl", "kxhgl", "kxdfl", "kxkr"],  # 物理学科字段
    #    "物理": ["wlpjf", "wlyxl", "wlhgl", "wldfl", "wlkr"],  # 物理学科字段
    #    "化学": ["hxpjf", "hxyxl", "hxhgl", "hxdfl", "hxkr"],  # 化学学科字段
    #    "政治": ["zzpjf", "zzyxl", "zzhgl", "zzdfl", "zzkr"],  # 政治学科字段
    #    "历史": ["lspjf", "lsyxl", "lshgl", "lsdfl", "lskr"],  # 历史学科字段
        "综合": ["zfpjf", "zfyxl", "zfhgl", "zfdfl"]           # 总分字段（无教师）
    }

    try:
        # 创建输出目录
        setup_output_directory(OUTPUT_DIR)
        
        # 通过对话框选择文件
        FILE_A, FILE_B = select_files()
        logging.info(f"选择的文件：\n上学期：{FILE_A}\n本学期：{FILE_B}")
        
        # 加载Excel文件数据
        df_a = load_excel_file(FILE_A)  # 加载上学期数据
        df_b = load_excel_file(FILE_B)  # 加载本学期数据
        
        # 打印列名用于调试
        print("df_b的列名:", df_b.columns.tolist())

        # 检查并重命名必要的列
        if '学校' in df_b.columns and '班级' in df_b.columns:
            df_b = df_b.rename(columns={
                '学校': 'xxh',    # 学校列重命名为xxh
                '班级': 'bb'      # 班级列重命名为bb
            })

        # 验证关键列存在
        df_b[['xxh', 'bb']]

        # 记录数据表的列名（用于调试）
        logging.info("A表列名: %s", df_a.columns.tolist())
        logging.info("B表列名: %s", df_b.columns.tolist())
        
        # 处理各学科数据并生成结果
        results = process_subjects(df_a, df_b, subject_fields)
        
        # 保存处理结果到Excel文件
        save_results(results, OUTPUT_FILE)

    except Exception as e:
        # 记录错误信息
        logging.error(f"程序执行出错: {str(e)}")
        raise  # 重新抛出异常，确保错误不被隐藏

if __name__ == "__main__":
    main()
