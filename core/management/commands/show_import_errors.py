from django.core.management.base import BaseCommand
import json
import os

class Command(BaseCommand):
    help = '显示最近一次导入产生的错误记录'
    
    def handle(self, *args, **options):
        error_file = 'import_errors.json'
        
        if not os.path.exists(error_file):
            self.stdout.write(self.style.ERROR("未找到错误记录文件"))
            return
            
        with open(error_file, 'r') as f:
            errors = json.load(f)
            
        self.stdout.write(f"共有 {len(errors)} 条错误记录:")
        for idx, error in enumerate(errors):
            self.stdout.write(f"{idx+1}. {error['学校']} {error['年级']} {error['班级']} - {error['错误']}") 