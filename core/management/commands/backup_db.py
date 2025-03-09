"""
数据库备份管理命令。

此命令创建PostgreSQL数据库的备份，可以在数据清空或其他危险操作前执行。
备份文件将保存在指定目录中，文件名包含时间戳。
"""

import os
import subprocess
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    """
    数据库备份的Django管理命令。
    
    使用PostgreSQL的pg_dump工具创建数据库的完整备份。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '创建数据库的备份，用于在数据清空前保存数据'
    
    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='backups', help='备份文件保存目录')
    
    def handle(self, *args, **options):
        # 获取输出目录
        output_dir = options.get('output_dir')
        
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"db_backup_{timestamp}.sql"
        filepath = os.path.join(output_dir, filename)
        
        # 获取数据库配置
        db_settings = settings.DATABASES['default']
        db_name = db_settings['NAME']
        db_user = db_settings['USER']
        db_password = db_settings.get('PASSWORD', '')
        db_host = db_settings.get('HOST', 'localhost')
        db_port = db_settings.get('PORT', '5432')
        
        # 设置环境变量用于pg_dump
        env = os.environ.copy()
        if db_password:
            env['PGPASSWORD'] = db_password
        
        # 构建pg_dump命令
        command = [
            'pg_dump',
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            '--format=p',  # 纯文本SQL
            '--no-owner',  # 不输出所有者设置命令
            '--no-privileges',  # 不输出权限设置
            f"--file={filepath}",
            db_name
        ]
        
        self.stdout.write(f'开始备份数据库 {db_name} 到 {filepath}...')
        
        try:
            # 执行备份命令
            process = subprocess.run(command, env=env, check=True, stderr=subprocess.PIPE)
            self.stdout.write(self.style.SUCCESS(f'数据库备份成功: {filepath}'))
            
        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f'数据库备份失败: {e.stderr.decode()}'))
            raise 