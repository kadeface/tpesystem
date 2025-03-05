from django.core.management.base import BaseCommand
from core.models import Score

class Command(BaseCommand):
    help = '更新所有Score记录的semester_id字段'

    def handle(self, *args, **options):
        count = 0
        for score in Score.objects.filter(semester_id="UNKNOWN"):
            if score.exam:
                score.semester_id = score.exam.semester_id
                score.save()
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f'成功更新 {count} 条成绩记录')) 