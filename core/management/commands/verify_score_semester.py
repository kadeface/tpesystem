from django.core.management.base import BaseCommand
from core.models import Score

class Command(BaseCommand):
    help = '验证Score记录的semester_id字段'

    def handle(self, *args, **options):
        # 检查总记录数
        total = Score.objects.count()
        
        # 检查没有semester_id的记录
        missing = Score.objects.filter(semester_id__isnull=True).count()
        
        # 检查semester_id与exam.semester_id不一致的记录
        inconsistent = 0
        for score in Score.objects.select_related('exam').all():
            if score.exam and score.semester_id != score.exam.semester_id:
                inconsistent += 1
        
        self.stdout.write(f"总记录数: {total}")
        self.stdout.write(f"缺少semester_id记录数: {missing}")
        self.stdout.write(f"不一致记录数: {inconsistent}") 