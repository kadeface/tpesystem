import os
import django
import subprocess
import sys

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'evaluation_system.settings')
django.setup()

# 设置UTF-8编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

# 执行导出命令
from django.core.management import call_command
call_command('dumpdata', output='full_backup.json')

print("备份完成，保存在full_backup.json") 